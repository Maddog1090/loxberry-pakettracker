"""DHL (Deutschland).

Live-Tracking: DHL "Shipment Tracking – Unified" API (developer.dhl.com, kostenloser API-Key).
  GET https://api-eu.dhl.com/track/shipments?trackingNumber=…&language=de[&recipientPostalCode=…]
  Header "DHL-API-Key: <Consumer Key aus My Apps>"
  Termin: estimatedTimeOfDelivery bzw. estimatedDeliveryTimeFrame (estimatedFrom/estimatedThrough)
  Kostenloser Zugang: 250 Abfragen/Tag, höchstens 1 Abfrage alle 5 Sekunden (sonst HTTP 429).
  Fehler kommen als application/problem+json (RFC 7807: title, detail, status).
Ankündigungen: Benachrichtigungsmails von DHL / Deutsche Post.
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
from . import checkdigits
from .apibase import ApiProvider, throttle_fields
from .base import ProviderError, local_window, status_from_keywords
from .mailparse import parse_carrier_email

# Für den Verbindungstest: gültiges Format, existiert aber nicht → DHL antwortet mit 404
_TEST_NUMBER = "00340434000000000000"


@register
class DhlProvider(ApiProvider):
    id = "dhl"
    name = "DHL"
    detection_priority = 10
    email_domains = ("dhl.de", "dhl.com", "deutschepost.de")
    required_secrets = ("api_key",)
    supports_test = True
    settings_schema = (
        Field("api_key", "API-Key (Shipment Tracking – Unified)", secret=True,
              help="Consumer Key aus developer.dhl.com → My Apps. Wird nur genutzt, wenn der Testmodus aus ist."),
        Field("language", "Sprache der Statustexte", "select", "de", options=("de", "en")),
        Field("recipient_postal_code", "Postleitzahl des Empfängers (optional)",
              help="Laut DHL liefert die API damit ausführlichere Sendungsdaten. Wird nur an DHL übertragen."),
        *throttle_fields(60, 250, "Kostenloser DHL-Zugang: 250. Nur erhöhen, wenn DHL ein höheres Kontingent "
                                  "freigegeben hat. Bei 60 Minuten reicht das für etwa 10 aktive Sendungen."),
    )
    strong_patterns = (
        re.compile(r"0034\d{16}"),                 # DHL Paket (NVE/SSCC mit Präfix 00340…)
        re.compile(r"JJD\d{18,20}"),               # DHL Express / Paket international
        re.compile(r"JVGL\d{16,20}"),
        re.compile(r"[A-Z]{2}\d{9}DE"),            # Deutsche Post / DHL (UPU S10, z.B. RR…DE)
    )
    tracking_patterns = (
        re.compile(r"\d{12}"),                     # DHL Paket (12-stellig) – auch GLS/FedEx möglich
        re.compile(r"\d{20}"),
    )
    tracking_url_template = "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={number}"

    API_URL = "https://api-eu.dhl.com/track/shipments"
    RATE_LIMIT_PAUSE = 30

    # statusCode der Unified API → normalisierter Status
    _API_STATUS = {
        "pre-transit": Status.ANNOUNCED,
        "transit": Status.IN_TRANSIT,
        "delivered": Status.DELIVERED,
        "failure": Status.EXCEPTION,
        "unknown": Status.UNKNOWN,
    }

    @classmethod
    def check_digit_ok(cls, number: str) -> bool | None:
        if re.fullmatch(r"[A-Z]{2}\d{9}DE", number):
            return checkdigits.upu_s10(number)
        if re.fullmatch(r"0034\d{16}", number):
            return checkdigits.gs1_mod10(number)
        return None

    # --- Abfrage -----------------------------------------------------------

    def _request(self, tracking_number: str) -> urllib.request.Request:
        params = {"trackingNumber": tracking_number, "language": self.settings.get("language") or "de"}
        postal_code = (self.settings.get("recipient_postal_code") or "").strip()
        if re.fullmatch(r"\d{5}", postal_code):
            params["recipientPostalCode"] = postal_code
        return urllib.request.Request(
            f"{self.API_URL}?{urllib.parse.urlencode(params)}",
            headers={
                "DHL-API-Key": (self.settings.get("api_key") or "").strip(),
                "Accept": "application/json",
                "User-Agent": f"LoxBerry-Pakettracker/{__version__}",
            },
        )

    def _fetch(self, tracking_number: str) -> Shipment:
        self._reserve_call()
        try:
            body = self._send(self._request(tracking_number))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, tracking_number) from None
        # Ab hier gilt die Sendung als abgefragt (auch wenn die Antwort unbrauchbar ist)
        self._mark_checked(tracking_number)
        shipment = self._parse(body, tracking_number)
        usage = self.state["usage"]
        self.log.info("%s abgefragt: %s (heute %d/%d Abfragen)", tracking_number, shipment.status.label,
                      usage["count"], self.settings.get("daily_limit", 250))
        return shipment

    def _test(self) -> str:
        self._reserve_call()
        try:
            self._send(self._request(_TEST_NUMBER))
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return "DHL hat den API-Key akzeptiert (1 Abfrage verbraucht)."
            raise self._http_error(exc, _TEST_NUMBER) from None
        return "DHL hat den API-Key akzeptiert (1 Abfrage verbraucht)."

    def _problem_detail(self, exc: urllib.error.HTTPError) -> str:
        """Kurzer Text aus einer RFC-7807-Fehlerantwort (title/detail), ohne Header."""
        data = self._read_json_error(exc)
        if not isinstance(data, dict):
            return ""
        return self._short(" – ".join(str(data[k]) for k in ("title", "detail") if data.get(k)))

    def _http_error(self, exc: urllib.error.HTTPError, tracking_number: str) -> ProviderError:
        code = exc.code
        detail = self._problem_detail(exc)
        if code in (401, 403):
            return ProviderError(f"DHL lehnt den API-Key ab (HTTP {code}){detail}. Key prüfen und sicherstellen, "
                                 "dass die App für 'Shipment Tracking – Unified' freigegeben ist.",
                                 abort=True, level=logging.ERROR)
        if code == 404:
            self._mark_checked(tracking_number)
            return ProviderError(f"Sendung bei DHL (noch) nicht gefunden{detail} – bisherige Daten bleiben erhalten",
                                 level=logging.INFO)
        if code == 400:
            self._mark_checked(tracking_number)
            return ProviderError(f"DHL lehnt die Anfrage ab (HTTP 400){detail} – Sendungsnummer prüfen")
        if code == 429:
            return self._rate_limited(exc, detail)
        if code >= 500:
            return ProviderError(f"DHL-Serverfehler (HTTP {code}) – neuer Versuch im nächsten Lauf", abort=True)
        return ProviderError(f"Unerwartete Antwort von DHL (HTTP {code}){detail}")

    def _parse(self, body: bytes, tracking_number: str) -> Shipment:
        data = self._load_json(body)
        if data is None:
            raise ProviderError("Ungültige Antwort von DHL (kein gültiges JSON)")
        shipments = data.get("shipments") if isinstance(data, dict) else None
        if not isinstance(shipments, list) or not any(isinstance(s, dict) for s in shipments):
            raise ProviderError("Antwort von DHL enthält keine Sendungsdaten")
        candidates = [s for s in shipments if isinstance(s, dict)]
        match = next((s for s in candidates if str(s.get("id", "")).upper() == tracking_number.upper()),
                     candidates[0])
        try:
            return self.map_api_shipment(match, tracking_number)
        except (AttributeError, TypeError, ValueError):
            raise ProviderError("Unerwartetes Antwortformat von DHL") from None

    @classmethod
    def map_api_shipment(cls, data: dict, tracking_number: str) -> Shipment:
        """Wandelt ein Element aus `shipments[]` der Unified-API-Antwort um."""
        st = data.get("status") if isinstance(data.get("status"), dict) else {}
        status = cls._API_STATUS.get(st.get("statusCode", ""), Status.UNKNOWN)
        text = str(st.get("description") or st.get("status") or "")
        # Die API kennt kein eigenes "in Zustellung" – aus dem Text ableiten
        if status == Status.IN_TRANSIT:
            status = status_from_keywords(text, (
                (Status.OUT_FOR_DELIVERY, ("zustellfahrzeug", "in zustellung", "out for delivery")),
                (Status.PICKUP_READY, ("abholbereit", "zur abholung", "ready for pick")),
            )) or status
        events = [
            TrackingEvent(
                timestamp=e.get("timestamp", ""),
                description=e.get("description") or e.get("status", ""),
                location=((e.get("location") or {}).get("address") or {}).get("addressLocality", ""),
            )
            for e in data.get("events") or []
            if isinstance(e, dict)
        ]
        eta = data.get("estimatedTimeOfDelivery")
        eta = eta[:10] if isinstance(eta, str) else ""
        frame = data.get("estimatedDeliveryTimeFrame")
        window = ""
        if isinstance(frame, dict):
            day, window = local_window(str(frame.get("estimatedFrom") or ""), str(frame.get("estimatedThrough") or ""))
            eta = day or eta
        return Shipment(
            provider=cls.id,
            tracking_number=tracking_number,
            status=status,
            status_text=text,
            eta=eta,
            eta_window=window if status != Status.DELIVERED else "",
            # Ohne Zeitstempel keine Statusübernahme – sonst würde "unbekannt" bessere Daten überschreiben
            last_update=st.get("timestamp") or "",
            events=events,
        )

    # --- E-Mail --------------------------------------------------------------

    def parse_email(self, mail: Mail) -> list[Shipment]:
        if not self.handles_sender(mail.sender):
            return []
        return parse_carrier_email(self, mail)
