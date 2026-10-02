"""Hermes (Deutschland).

Eine offizielle Tracking-API bietet Hermes nur Geschäftskunden mit Vertrag
(HSI/myHermes Business). Daher zwei Quellen:

Live-Abfrage (optional, standardmäßig aus): die JSON-Schnittstelle, die auch die
Sendungsverfolgung auf myhermes.de nutzt. Sie ist öffentlich und braucht keinen
Schlüssel, ist aber nicht dokumentiert und kann sich ohne Ankündigung ändern.
  GET https://api.my-deliveries.de/tnt/v2/shipments/search/{Sendungsnummer}
  200: Liste von Sendungen (barcode, parcelProgress[], forecast, parcelAttributes, viewParameters)
  404: Sendung unbekannt; 400: Nummer ungültig ({"reason": …})

Benachrichtigungsmails (Paketankündigung, „heute in Zustellung“, Zustellung,
PaketShop) werden immer ausgewertet.
"""
from __future__ import annotations

import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from .. import __version__
from ..models import Shipment, Status, TrackingEvent
from ..registry import register
from ..schema import Field
from ..sources.mail import Mail
from .apibase import ApiProvider, throttle_fields
from .base import ProviderError, local_window
from .mailparse import parse_carrier_email

# Für den Verbindungstest: existiert nicht → Hermes antwortet mit 400 (ungültig) bzw. 404 (unbekannt)
_TEST_NUMBER = "00000000000000"

# parcelProgress[].parcelStatus → Status. Hermes dokumentiert die Werte nicht; geprüft wird
# der Reihe nach auf Bestandteile des Namens (spezifische zuerst, "NOT_DELIVERED" vor "DELIVERED").
_PROGRESS_RULES: tuple[tuple[Status, tuple[str, ...]], ...] = (
    (Status.RETURNED, ("RETURN",)),
    (Status.EXCEPTION, ("NOT_DELIVERED", "UNDELIVER", "FAILED", "DAMAGE", "LOST", "DELAY", "STOPPED",
                        "REFUSED", "ADDRESS")),
    (Status.PICKUP_READY, ("READY_FOR_COLLECTION", "PARCELSHOP_DELIVERED", "DELIVERED_TO_PARCELSHOP",
                           "PARCELSHOP_ARRIVED", "ARRIVED_AT_PARCELSHOP", "PARCELBOX")),
    (Status.DELIVERED, ("DELIVERED",)),
    (Status.OUT_FOR_DELIVERY, ("OUT_FOR_DELIVERY", "IN_DELIVERY", "ON_TOUR", "LOADED")),
    (Status.ANNOUNCED, ("ANNOUNCED", "NOTIFIED", "DATA_RECEIVED")),
)
# parcelProgress[].status: "HAPPY" = normaler Verlauf, alles andere deutet auf ein Problem hin
_OK_EVENT = {"", "HAPPY", "NEUTRAL", "INFO"}


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _progress_status(code: str) -> Status:
    code = code.upper()
    for status, parts in _PROGRESS_RULES:
        if any(p in code for p in parts):
            return status
    return Status.IN_TRANSIT  # z.B. SORTED, PARCELSHOP_DROP_OFF, PARCELSHOP_COLLECTED_BY_DRIVER


@register
class HermesProvider(ApiProvider):
    id = "hermes"
    name = "Hermes"
    detection_priority = 20
    email_domains = ("myhermes.de", "hermesworld.com", "hermes-europe.de", "hermes-logistik-gruppe.de")
    supports_test = True
    settings_schema = (
        Field("live_lookup", "Live-Abfrage über myhermes.de", "bool", False,
              help="Fragt Status, Verlauf und Zustellzeitfenster bei der Sendungsverfolgung von myhermes.de ab – "
                   "ohne Zugangsdaten. Die Schnittstelle ist öffentlich, aber nicht offiziell dokumentiert und "
                   "kann sich jederzeit ändern. Übertragen wird nur die Sendungsnummer."),
        *throttle_fields(60, 200, "Eigenes Sicherheitslimit; Hermes veröffentlicht kein Kontingent."),
    )
    strong_patterns = (re.compile(r"H\d{19}"),)          # neues Format, z.B. H1000…
    tracking_patterns = (re.compile(r"\d{14}"), re.compile(r"\d{16}"))
    tracking_url_template = "https://www.myhermes.de/empfangen/sendungsverfolgung/sendungsinformation#{number}"
    source_note = ("Keine offizielle API für Privatkunden – Benachrichtigungsmails plus optional die (inoffizielle) "
                   "Live-Abfrage über die Sendungsverfolgung von myhermes.de.")

    API_URL = "https://api.my-deliveries.de/tnt/v2/shipments/search"
    MIN_SPACING = 2.0

    def __init__(self, settings: dict, mock: bool, log: logging.Logger, state: dict | None = None):
        super().__init__(settings, mock, log, state)
        # Ohne Live-Abfrage verhält sich Hermes wie ein reiner E-Mail-Anbieter (Engine, Zustand)
        self.live_tracking = bool(settings.get("live_lookup"))

    # --- Abfrage -----------------------------------------------------------

    def _request(self, tracking_number: str) -> urllib.request.Request:
        return urllib.request.Request(
            f"{self.API_URL}/{urllib.parse.quote(tracking_number, safe='')}",
            headers={"Accept": "application/json", "User-Agent": f"LoxBerry-Pakettracker/{__version__}"},
        )

    def _fetch(self, tracking_number: str) -> Shipment:
        if not self.live_tracking:
            raise NotImplementedError("Hermes: Live-Abfrage ist ausgeschaltet (Einstellungen → Hermes) – "
                                      "Sendungen werden nur per E-Mail aktualisiert")
        self._reserve_call()
        try:
            body = self._send(self._request(tracking_number))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, tracking_number) from None
        self._mark_checked(tracking_number)
        shipment = self._parse(body, tracking_number)
        usage = self.state["usage"]
        self.log.info("%s abgefragt: %s (heute %d/%d Abfragen)", tracking_number, shipment.status.label,
                      usage["count"], self.settings.get("daily_limit", 200))
        return shipment

    def _test(self) -> str:
        self._reserve_call()
        try:
            self._send(self._request(_TEST_NUMBER))
        except urllib.error.HTTPError as exc:
            if exc.code not in (400, 404):
                raise self._http_error(exc, _TEST_NUMBER) from None
        hint = "" if self.live_tracking else " Die Live-Abfrage ist noch ausgeschaltet."
        return f"Sendungsverfolgung von myhermes.de ist erreichbar.{hint}"

    def _http_error(self, exc: urllib.error.HTTPError, tracking_number: str) -> ProviderError:
        code = exc.code
        data = self._read_json_error(exc)
        detail = self._short(str(data.get("reason") or "")) if isinstance(data, dict) else ""
        if code == 404:
            self._mark_checked(tracking_number)
            return ProviderError("Sendung bei Hermes (noch) nicht gefunden – bisherige Daten bleiben erhalten",
                                 level=logging.INFO)
        if code == 400:
            self._mark_checked(tracking_number)
            return ProviderError(f"Hermes lehnt die Sendungsnummer ab (HTTP 400){detail} – Nummer prüfen")
        if code in (401, 403):
            return ProviderError(f"Hermes verweigert die Abfrage (HTTP {code}). Die inoffizielle Schnittstelle "
                                 "wurde evtl. geändert – Live-Abfrage ausschalten, falls das so bleibt.",
                                 abort=True, level=logging.ERROR)
        if code == 429:
            return self._rate_limited(exc, detail)
        if code >= 500:
            return ProviderError(f"Hermes-Serverfehler (HTTP {code}) – neuer Versuch im nächsten Lauf", abort=True)
        return ProviderError(f"Unerwartete Antwort von Hermes (HTTP {code}){detail}")

    def _parse(self, body: bytes, tracking_number: str) -> Shipment:
        data = self._load_json(body)
        if data is None:
            raise ProviderError("Ungültige Antwort von Hermes (kein gültiges JSON)")
        candidates = [s for s in data if isinstance(s, dict)] if isinstance(data, list) else []
        if not candidates:
            raise ProviderError("Sendung bei Hermes (noch) nicht gefunden – bisherige Daten bleiben erhalten",
                                level=logging.INFO)
        match = next((s for s in candidates if str(s.get("barcode", "")).upper() == tracking_number),
                     candidates[0])
        try:
            return self.map_shipment(match, tracking_number)
        except (AttributeError, TypeError, ValueError):
            raise ProviderError("Unerwartetes Antwortformat von Hermes") from None

    @classmethod
    def map_shipment(cls, data: dict, tracking_number: str) -> Shipment:
        progress = sorted((p for p in data.get("parcelProgress") or [] if isinstance(p, dict)),
                          key=lambda p: str(p.get("timestamp") or ""), reverse=True)
        latest = progress[0] if progress else {}
        attributes, view = _dict(data.get("parcelAttributes")), _dict(data.get("viewParameters"))

        status = _progress_status(str(latest.get("parcelStatus") or "")) if latest else Status.UNKNOWN
        if attributes.get("delivered"):
            status = Status.DELIVERED
        if view.get("readyForCollection") or view.get("readyForParcelBoxCollection"):
            status = Status.PICKUP_READY
        if "RETURN" in str(attributes.get("directionEnum") or "").upper():
            status = Status.RETURNED
        if str(latest.get("status") or "").upper() not in _OK_EVENT and status in (Status.IN_TRANSIT, Status.ANNOUNCED):
            status = Status.EXCEPTION
        if attributes.get("handedOverOnTour") and status in (Status.IN_TRANSIT, Status.ANNOUNCED):
            status = Status.OUT_FOR_DELIVERY

        eta, window = "", ""
        if status == Status.DELIVERED:
            eta = local_window(str(latest.get("timestamp") or ""), "")[0]
        else:
            forecast = _dict(data.get("forecast"))
            eta, window = local_window(str(forecast.get("deliveryTimeFromUTC") or ""),
                                       str(forecast.get("deliveryTimeToUTC") or ""))

        events = [TrackingEvent(timestamp=str(p.get("timestamp") or ""),
                                description=str(p.get("historyText") or p.get("headlineText") or ""))
                  for p in progress]
        return Shipment(
            provider=cls.id,
            tracking_number=tracking_number,
            status=status,
            status_text=str(latest.get("historyText") or latest.get("headlineText") or ""),
            eta=eta,
            eta_window=window,
            # Ohne Zeitstempel keine Statusübernahme – sonst würde "unbekannt" bessere Daten überschreiben
            last_update=str(latest.get("timestamp") or ""),
            events=events,
        )

    # --- E-Mail --------------------------------------------------------------

    def parse_email(self, mail: Mail) -> list[Shipment]:
        if not self.handles_sender(mail.sender):
            return []
        return parse_carrier_email(self, mail)
