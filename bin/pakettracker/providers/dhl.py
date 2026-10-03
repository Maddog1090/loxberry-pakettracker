"""DHL (Deutschland).

Zwei offizielle Schnittstellen von developer.dhl.com, beide optional:

1. Shipment Tracking – Unified (Standard, Self-Service, kostenloser API-Key)
   GET https://api-eu.dhl.com/track/shipments?trackingNumber=…&language=de[&recipientPostalCode=…]
   Header "DHL-API-Key: <Consumer Key aus My Apps>"
   Termin: estimatedTimeOfDelivery bzw. estimatedDeliveryTimeFrame (estimatedFrom/estimatedThrough)
   Kostenloser Zugang: 250 Abfragen/Tag, höchstens 1 Abfrage alle 5 Sekunden (sonst HTTP 429).
   Fehler kommen als application/problem+json (RFC 7807: title, detail, status).

2. Parcel DE Tracking (Post & Parcel Germany) – "public"-Abfrage get-status-for-public-user
   GET https://api-eu.dhl.com/parcel/de/tracking/v0/shipments?xml=<data request="get-status-for-public-user" …>
   Gateway: API-Key + API-Secret als HTTP Basic Auth (zusätzlich Header dhl-api-key, wie DHLs Postman-Sammlung).
   Antwort: XML (<data name="piece-status-public-list" code="…"><data name="piece-status-public" …/>).
   Laut DHL-Doku wird die produktive Nutzung von DHL freigeschaltet; je nach Abschnitt der Doku sind zusätzlich
   eine Benutzerkennung (appname) und ein Passwort nötig, die DHL vergibt. Beides ist daher optional
   konfigurierbar. Mit Empfänger-PLZ liefert DHL u.a. Ort und Adresse von Filiale/Packstation; Zustelltag und
   -zeitfenster nur mit gesondertem Recht. Limit laut DHL: 1000 Abfragen/Tag, 3 pro Sekunde, zugestellte
   Sendungen nicht erneut abfragen. Die Business-Abfrage (d-get-piece-detail) liefert nur Sendungen aus dem
   eigenen Nummernkreis eines Geschäftskunden und wird deshalb nicht genutzt.

Auswahl ("api"): auto = Parcel DE, wenn ein API-Secret hinterlegt ist, sonst Unified. Lehnt Parcel DE die
Anmeldung ab, wird Parcel DE für einige Stunden pausiert und Unified verwendet (nur im Modus auto).
Funktioniert ohne E-Mail-Eingang: manuell eingetragene Nummern werden direkt abgefragt.
Ankündigungen (optional): Benachrichtigungsmails von DHL / Deutsche Post.
"""
from __future__ import annotations

import base64
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from .. import __version__
from ..models import LOCAL_TZ, Shipment, Status, TrackingEvent, parse_ts
from ..registry import register
from ..schema import Field
from ..sources.mail import Mail
from . import checkdigits
from .apibase import ApiProvider, throttle_fields
from .base import ProviderError, local_window, status_from_keywords
from .mailparse import parse_carrier_email

# Für den Verbindungstest: gültiges Format, existiert aber nicht → Unified 404, Parcel DE Code 100
_TEST_NUMBER = "00340434000000000000"

UNIFIED = "unified"
PARCEL_DE = "parcel_de"
API_LABELS = {UNIFIED: "Shipment Tracking – Unified", PARCEL_DE: "Parcel DE Tracking"}


class _AuthError(ProviderError):
    """Zugang zur gewählten DHL-Schnittstelle abgelehnt (Gateway 401/403 oder Parcel-DE-Anmeldefehler)."""

    def __init__(self, message: str):
        super().__init__(message, abort=True, level=logging.ERROR)


def _local_iso(value: str) -> str:
    """DHL-Zeitangabe ("16.03.2012 15:29", "2012-03-16 15:29:00", ISO) → ISO-Zeitstempel; Ortszeit Europe/Berlin."""
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(value, fmt)
        except ValueError:
            continue
        dt = dt.replace(tzinfo=LOCAL_TZ) if LOCAL_TZ else dt.astimezone()
        return dt.isoformat(timespec="seconds")
    dt = parse_ts(value.replace(" ", "T", 1))
    return dt.isoformat(timespec="seconds") if dt else ""


def _local_day(value: str) -> str:
    """Zustelltag ("2026-10-05", "05.10.2026") → JJJJ-MM-TT, sonst leer."""
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return ""


@register
class DhlProvider(ApiProvider):
    id = "dhl"
    name = "DHL"
    detection_priority = 10
    email_domains = ("dhl.de", "dhl.com", "deutschepost.de")
    required_secrets = ("api_key",)
    supports_test = True
    settings_schema = (
        Field("api_key", "API-Key (DHL Developer App)", secret=True,
              help="Consumer Key aus developer.dhl.com → My Apps. Gilt für jede DHL-API, für die die App "
                   "freigeschaltet ist (Shipment Tracking – Unified und/oder Parcel DE Tracking). "
                   "Wird nur genutzt, wenn der Testmodus aus ist."),
        Field("api", "DHL-Schnittstelle", "select", "auto", options=("auto", PARCEL_DE, UNIFIED),
              help="auto = Parcel DE Tracking, wenn ein API-Secret hinterlegt ist, sonst Shipment Tracking – "
                   "Unified. Lehnt DHL Parcel DE ab, nutzt auto vorübergehend Unified."),
        Field("api_secret", "API-Secret (nur Parcel DE Tracking)", secret=True,
              help="Secret derselben App aus My Apps. Parcel DE Tracking muss DHL für die Produktion "
                   "freischalten („Die produktive Verwendung wird durch DHL freigeschaltet“)."),
        Field("tracking_user", "Tracking-Benutzerkennung (Parcel DE, nur falls von DHL vergeben)", secret=True,
              help="appname laut DHL-Doku. Nur eintragen, wenn DHL Ihnen eine Benutzerkennung für die "
                   "Sendungsverfolgung gegeben hat; sonst leer lassen."),
        Field("tracking_password", "Tracking-Passwort (Parcel DE, nur falls von DHL vergeben)", secret=True),
        Field("language", "Sprache der Statustexte", "select", "de", options=("de", "en")),
        Field("recipient_postal_code", "Postleitzahl des Empfängers (optional)",
              help="Wird nur an DHL übertragen und nur bei Einzelabfragen mitgeschickt. Parcel DE liefert damit "
                   "z.B. Ort und Adresse von Filiale/Packstation, Unified ausführlichere Sendungsdaten."),
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
    PARCEL_URL = "https://api-eu.dhl.com/parcel/de/tracking/v0/shipments"
    RATE_LIMIT_PAUSE = 30
    PARCEL_AUTH_PAUSE = timedelta(hours=6)  # nach abgelehnter Anmeldung bei Parcel DE (Modus auto)
    MAX_XML_BYTES = 500_000

    # Parcel DE: "International Coded Event" (Codeliste ICE/RIC von DHL, Stand 05/2026) → Status.
    # Nur eindeutige Codes; alles andere über Statustext und Standard-Ereigniscode.
    _ICE_STATUS = {
        "DLVRD": Status.DELIVERED,          # Ausgeliefert
        "RETRN": Status.RETURNED,           # Rücksendung
        "HLDCC": Status.PICKUP_READY,       # Sendung liegt zur Abholung bereit
        "CNRFC": Status.PICKUP_READY,       # Benachrichtigt (Filiale/Lagerung)
        "DLVRF": Status.EXCEPTION,          # Annahme verweigert
        "NTDEL": Status.EXCEPTION,          # Nicht ausgeliefert
        "LDEXC": Status.EXCEPTION,          # Ladungsrückstellung
        "MSRTD": Status.EXCEPTION,          # Routingfehler
        "MVTEX": Status.EXCEPTION,          # Problem beim Transport
        "DMGDS": Status.EXCEPTION,          # Beschädigt
        "CANCL": Status.EXCEPTION,          # Versand vom Absender storniert
        "DSPSD": Status.EXCEPTION,          # Vernichtung
        "PARCV": Status.ANNOUNCED,          # Elektronische Sendungsdaten liegen vor
    }
    # Parcel DE: standard-event-code → Status
    _STANDARD_EVENT_STATUS = {
        "ZU": Status.DELIVERED,             # Zugestellt
        "ZN": Status.EXCEPTION,             # Zustellversuch nicht erfolgreich
        "ZF": Status.PICKUP_READY,          # Zustellung Filiale
        "PO": Status.OUT_FOR_DELIVERY,      # Im Zustellprozess
        "VA": Status.ANNOUNCED,             # Vorankündigung (per EDI)
        "AA": Status.IN_TRANSIT, "EE": Status.IN_TRANSIT, "NB": Status.IN_TRANSIT,
        "ES": Status.IN_TRANSIT, "AE": Status.IN_TRANSIT, "ZO": Status.IN_TRANSIT,
    }
    # Parcel DE: code der Antwort → (Meldung, Art); Art: auth | not_found | number | zip | technical
    _PARCEL_CODES = {
        5: ("Anmeldung fehlgeschlagen", "auth"),
        6: ("Zu viele ungültige Anmeldungen – später erneut versuchen", "auth"),
        62: ("Bearbeitung wegen fehlender Berechtigung abgebrochen", "auth"),
        64: ("Recht zur Anfrage ohne Prüfziffer fehlt", "auth"),
        41: ("IDC-Prüfsumme ungültig", "number"),
        45: ("Keine Sendungsnummer übergeben", "number"),
        59: ("Keine Sendungsnummer übergeben", "number"),
        57: ("Zur angegebenen PLZ sind keine Informationen verfügbar", "zip"),
        100: ("Keine Daten gefunden", "not_found"),
        200: ("Es liegen keine elektronischen Sendungsdaten vor", "not_found"),
    }

    # statusCode der Unified API → normalisierter Status
    _API_STATUS = {
        "pre-transit": Status.ANNOUNCED,
        "transit": Status.IN_TRANSIT,
        "delivered": Status.DELIVERED,
        "failure": Status.EXCEPTION,
        "unknown": Status.UNKNOWN,
    }

    # Feinere Einordnung über den Statustext: Die API meldet Zustellung, Zustellversuch, Abholbereitschaft
    # und Rücksendung meist nur als "transit" bzw. "failure". Spezifische Formulierungen zuerst.
    _TEXT_RULES = (
        (Status.RETURNED, ("rücksendung", "zurück an den absender", "an den absender zurück", "returned to sender",
                           "return to sender", "being returned")),
        (Status.EXCEPTION, ("konnte nicht zugestellt", "nicht angetroffen", "zustellversuch", "nicht zustellbar",
                            "could not be delivered", "delivery attempt", "unsuccessful delivery")),
        (Status.OUT_FOR_DELIVERY, ("zustellfahrzeug", "in zustellung", "out for delivery")),
        (Status.PICKUP_READY, ("abholbereit", "zur abholung", "ready for pick", "packstation eingeliefert",
                               "in der packstation", "available for pick")),
    )

    @classmethod
    def check_digit_ok(cls, number: str) -> bool | None:
        if re.fullmatch(r"[A-Z]{2}\d{9}DE", number):
            return checkdigits.upu_s10(number)
        if re.fullmatch(r"0034\d{16}", number):
            return checkdigits.gs1_mod10(number)
        return None

    # --- Auswahl der Schnittstelle --------------------------------------------

    def _setting(self, key: str) -> str:
        return str(self.settings.get(key) or "").strip()

    def parcel_configured(self) -> bool:
        """API-Key + API-Secret vorhanden; Benutzerkennung/Passwort entweder beide oder keines."""
        return bool(self._setting("api_key") and self._setting("api_secret")) and \
            bool(self._setting("tracking_user")) == bool(self._setting("tracking_password"))

    def _mode(self) -> str:
        mode = self._setting("api") or "auto"
        return mode if mode in ("auto", PARCEL_DE, UNIFIED) else "auto"

    def _parcel_paused(self) -> bool:
        until = parse_ts(self.state.get("parcel_de_paused_until"))
        return until is not None and datetime.now(timezone.utc) < until

    def _plan(self) -> list[str]:
        """Reihenfolge der Schnittstellen für eine Abfrage (die zweite nur nach abgelehnter Anmeldung)."""
        mode = self._mode()
        if mode == UNIFIED:
            return [UNIFIED]
        if mode == PARCEL_DE:
            return [PARCEL_DE]
        if self.parcel_configured() and not self._parcel_paused():
            return [PARCEL_DE, UNIFIED]
        return [UNIFIED]

    def live_details(self) -> dict:
        mode = self._mode()
        missing = []
        if not self._setting("api_key"):
            missing.append("api_key")
        if mode == PARCEL_DE and not self._setting("api_secret"):
            missing.append("api_secret")
        if bool(self._setting("tracking_user")) != bool(self._setting("tracking_password")):
            missing.append("tracking_password" if self._setting("tracking_user") else "tracking_user")
        plan = self._plan()
        api = plan[0] if "api_key" not in missing and "api_secret" not in missing else ""
        show_parcel = mode != UNIFIED and bool(self._setting("api_secret"))
        last = self.state.get("last_api_success") if isinstance(self.state.get("last_api_success"), dict) else {}
        return {
            "live_api": api,
            "live_api_label": API_LABELS.get(api, ""),
            # erst nach einer erfolgreichen Antwort dieser Schnittstelle gilt sie als aktiv
            "live_api_confirmed": bool(api and last.get(api)),
            "live_api_mode": mode,
            "live_missing": missing,
            "parcel_de_configured": self.parcel_configured(),
            "parcel_de_error": str(self.state.get("parcel_de_error") or "") if show_parcel else "",
            "parcel_de_paused_until": str(self.state.get("parcel_de_paused_until") or "")
            if show_parcel and self._parcel_paused() else "",
        }

    def _api_success(self, api: str) -> None:
        self.state.setdefault("last_api_success", {})[api] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if api == PARCEL_DE:
            self.state.pop("parcel_de_error", None)
            self.state.pop("parcel_de_paused_until", None)

    def _pause_parcel(self, message: str) -> None:
        until = datetime.now(timezone.utc) + self.PARCEL_AUTH_PAUSE
        self.state["parcel_de_error"] = message[:300]
        self.state["parcel_de_paused_until"] = until.isoformat(timespec="seconds")

    # --- Abfrage -----------------------------------------------------------

    def _fetch(self, tracking_number: str) -> Shipment:
        plan = self._plan()
        for index, api in enumerate(plan):
            try:
                shipment = self._fetch_parcel(tracking_number) if api == PARCEL_DE else \
                    self._fetch_unified(tracking_number)
            except _AuthError as exc:
                if api == PARCEL_DE:
                    self.state["parcel_de_error"] = str(self._redact(exc))[:300]
                if api == PARCEL_DE and index + 1 < len(plan):
                    self._pause_parcel(str(self._redact(exc)))
                    self.log.warning("%s – Parcel DE pausiert, verwende %s", self._redact(exc), API_LABELS[UNIFIED])
                    continue
                raise
            self._api_success(api)
            return shipment
        raise ProviderError("DHL: keine Schnittstelle verfügbar", abort=True)  # nicht erreichbar

    def _request(self, tracking_number: str) -> urllib.request.Request:
        """Request an Shipment Tracking – Unified."""
        params = {"trackingNumber": tracking_number, "language": self.settings.get("language") or "de"}
        postal_code = self._setting("recipient_postal_code")
        if re.fullmatch(r"\d{5}", postal_code):
            params["recipientPostalCode"] = postal_code
        return urllib.request.Request(
            f"{self.API_URL}?{urllib.parse.urlencode(params)}",
            headers={
                "DHL-API-Key": self._setting("api_key"),
                "Accept": "application/json",
                "User-Agent": f"LoxBerry-Pakettracker/{__version__}",
            },
        )

    def _fetch_unified(self, tracking_number: str) -> Shipment:
        self._reserve_call()
        try:
            body = self._send(self._request(tracking_number))
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, tracking_number) from None
        # Ab hier gilt die Sendung als abgefragt (auch wenn die Antwort unbrauchbar ist)
        self._mark_checked(tracking_number)
        shipment = self._parse(body, tracking_number)
        self._log_success(tracking_number, shipment, UNIFIED)
        return shipment

    def _log_success(self, tracking_number: str, shipment: Shipment, api: str) -> None:
        usage = self.state["usage"]
        self.log.info("%s abgefragt (%s): %s (heute %d/%d Abfragen)", tracking_number, API_LABELS[api],
                      shipment.status.label, usage["count"], self.settings.get("daily_limit", 250))

    # --- Parcel DE Tracking -----------------------------------------------------

    def parcel_xml(self, tracking_number: str) -> str:
        """XML der public-Abfrage wie in der DHL-Doku; Werte werden von ElementTree maskiert."""
        outer = ET.Element("data", {"request": "get-status-for-public-user"})
        user, password = self._setting("tracking_user"), self._setting("tracking_password")
        if user and password:
            outer.set("appname", user)
            outer.set("password", password)
        outer.set("language-code", self._setting("language") or "de")
        inner = ET.SubElement(outer, "data", {"piece-code": tracking_number})
        postal_code = self._setting("recipient_postal_code")
        if re.fullmatch(r"\d{5}", postal_code):
            inner.set("zip-code", postal_code)
        return '<?xml version="1.0" encoding="UTF-8" standalone="no"?>' + ET.tostring(outer, encoding="unicode")

    def _parcel_request(self, tracking_number: str) -> urllib.request.Request:
        key, secret = self._setting("api_key"), self._setting("api_secret")
        token = base64.b64encode(f"{key}:{secret}".encode()).decode("ascii")
        return urllib.request.Request(
            f"{self.PARCEL_URL}?{urllib.parse.urlencode({'xml': self.parcel_xml(tracking_number)})}",
            headers={
                "Authorization": f"Basic {token}",
                "dhl-api-key": key,
                "Accept": "application/xml, text/xml",
                "User-Agent": f"LoxBerry-Pakettracker/{__version__}",
            },
        )

    def _parcel_preconditions(self) -> None:
        if not self._setting("api_secret"):
            raise ProviderError("DHL Parcel DE Tracking: API-Secret nicht hinterlegt (Einstellungen → DHL)",
                                abort=True, level=logging.INFO)
        if bool(self._setting("tracking_user")) != bool(self._setting("tracking_password")):
            raise ProviderError("DHL Parcel DE Tracking: Tracking-Benutzerkennung und Tracking-Passwort nur "
                                "gemeinsam angeben (Einstellungen → DHL)", abort=True, level=logging.INFO)

    def _fetch_parcel(self, tracking_number: str) -> Shipment:
        self._parcel_preconditions()
        self._reserve_call()
        try:
            body = self._send(self._parcel_request(tracking_number))
        except urllib.error.HTTPError as exc:
            raise self._parcel_http_error(exc, tracking_number) from None
        self._mark_checked(tracking_number)
        shipment = self.parse_parcel(body, tracking_number)
        self._log_success(tracking_number, shipment, PARCEL_DE)
        return shipment

    def _parcel_http_error(self, exc: urllib.error.HTTPError, tracking_number: str) -> ProviderError:
        code = exc.code
        detail = self._problem_detail(exc)
        if code in (401, 403):
            verb = "abgelehnt" if code == 401 else "verweigert"
            return _AuthError(
                f"DHL Parcel DE Tracking: Zugang {verb} (HTTP {code}){detail}. Bitte prüfen: API-Key und "
                "API-Secret derselben App korrekt, App unter developer.dhl.com → My Apps für „Parcel DE Tracking“ "
                "(Produktion) freigegeben – die produktive Nutzung muss DHL freischalten.")
        return self._http_error(exc, tracking_number, PARCEL_DE)

    @classmethod
    def _xml_root(cls, body: bytes) -> ET.Element:
        if not body or not body.strip():
            raise ProviderError("Leere Antwort von DHL (Parcel DE Tracking)")
        head = body[:4096].upper()
        if b"<!DOCTYPE" in head or b"<!ENTITY" in body.upper():
            raise ProviderError("Antwort von DHL (Parcel DE Tracking) abgelehnt: DTD/Entities sind nicht erlaubt")
        if len(body) > cls.MAX_XML_BYTES:
            raise ProviderError("Antwort von DHL (Parcel DE Tracking) ist zu groß")
        try:
            return ET.fromstring(body)
        except ET.ParseError:
            raise ProviderError("Ungültige Antwort von DHL (Parcel DE Tracking, kein gültiges XML)") from None

    def parse_parcel(self, body: bytes, tracking_number: str) -> Shipment:
        root = self._xml_root(body)
        status_el = next((e for e in root.iter() if e.get("code") not in (None, "")), None)
        if status_el is None:
            raise ProviderError("Unerwartetes Antwortformat von DHL (Parcel DE Tracking, kein Statuscode)")
        try:
            code = int(status_el.get("code"))
        except ValueError:
            raise ProviderError("Unerwartetes Antwortformat von DHL (Parcel DE Tracking)") from None
        if code != 0:
            raise self._parcel_code_error(code, status_el.get("error") or "")
        pieces = [e for e in root.iter() if e.get("piece-code") is not None
                  and (e.get("status") is not None or e.get("delivery-event-flag") is not None)]
        if not pieces:
            raise ProviderError("Antwort von DHL (Parcel DE Tracking) enthält keine Sendungsdaten")
        number = tracking_number.upper()
        piece = next((e for e in pieces if number in (str(e.get("piece-code", "")).upper(),
                                                      str(e.get("searched-piece-code", "")).upper())), pieces[0])
        error_status = (piece.get("error-status") or "0").strip()
        if error_status not in ("", "0"):
            try:
                raise self._parcel_code_error(int(error_status), piece.get("status") or "")
            except ValueError:
                raise ProviderError(f"DHL Parcel DE Tracking: Fehlerstatus {error_status[:20]}") from None
        events = [e for e in root.iter() if e.get("event-timestamp")]
        return self.map_parcel_piece(dict(piece.attrib), [dict(e.attrib) for e in events], tracking_number)

    def _parcel_code_error(self, code: int, text: str) -> ProviderError:
        message, kind = self._PARCEL_CODES.get(code, (text or "Fehler", "technical" if code < 0 else "other"))
        prefix = f"DHL Parcel DE Tracking: {message} (Code {code})"
        if kind == "auth":
            hint = (" – Tracking-Benutzerkennung/-Passwort prüfen bzw. bei DHL erfragen; die public-Abfrage in der "
                    "Produktion schaltet DHL frei." if code in (5, 6) else " – Berechtigung bei DHL klären.")
            return _AuthError(prefix + hint)
        if kind == "not_found":
            return ProviderError(f"{prefix} – Sendung (noch) nicht bekannt, bisherige Daten bleiben erhalten",
                                 level=logging.INFO)
        if kind == "zip":
            return ProviderError(f"{prefix} – Postleitzahl in den Einstellungen prüfen")
        if kind == "number":
            return ProviderError(f"{prefix} – Sendungsnummer prüfen")
        if kind == "technical":
            return ProviderError(f"{prefix} – DHL-Sendungsverfolgung vorübergehend gestört, neuer Versuch im "
                                 "nächsten Lauf", abort=True)
        return ProviderError(prefix)

    @classmethod
    def map_parcel_piece(cls, piece: dict, events: list[dict], tracking_number: str) -> Shipment:
        """Wandelt piece-status-public (bzw. pieceshipment) samt Ereignissen in eine Sendung um."""
        history = sorted(
            (TrackingEvent(timestamp=_local_iso(e.get("event-timestamp", "")),
                           description=(e.get("event-text") or e.get("event-status") or "").strip(),
                           location=(e.get("event-location") or "").strip())
             for e in events),
            key=lambda e: e.timestamp, reverse=True)
        latest_raw = max(events, key=lambda e: _local_iso(e.get("event-timestamp", "")), default={})
        text = (piece.get("status") or piece.get("short-status") or
                (history[0].description if history else "")).strip()
        timestamp = _local_iso(piece.get("last-event-timestamp") or piece.get("status-timestamp") or "") or \
            (history[0].timestamp if history else "")
        ice = (piece.get("ice") or latest_raw.get("ice") or "").strip().upper()
        standard = (piece.get("standard-event-code") or latest_raw.get("standard-event-code") or "").strip().upper()

        if (piece.get("delivery-event-flag") or "").strip() == "1":
            status = Status.DELIVERED
        elif (piece.get("ruecksendung") or "").strip().lower() == "true":
            status = Status.RETURNED
        else:
            status = (cls._ICE_STATUS.get(ice) or status_from_keywords(text, cls._TEXT_RULES)
                      or cls._STANDARD_EVENT_STATUS.get(standard)
                      or (Status.IN_TRANSIT if timestamp else Status.UNKNOWN))

        eta = _local_day(piece.get("delivery-date") or "")
        window = ""
        start, finish = (piece.get("delivery-timeframe-from") or "").strip(), \
            (piece.get("delivery-timeframe-to") or "").strip()
        if eta and re.fullmatch(r"\d{1,2}:\d{2}", start) and re.fullmatch(r"\d{1,2}:\d{2}", finish):
            window = f"{start.zfill(5)}–{finish.zfill(5)}"
        elif start and finish:
            day, window = local_window(_local_iso(start), _local_iso(finish))
            eta = eta or day
        return Shipment(
            provider=cls.id,
            tracking_number=tracking_number,
            status=status,
            status_text=text,
            eta=eta if status != Status.DELIVERED else "",
            eta_window=window if status != Status.DELIVERED else "",
            last_update=timestamp,  # ohne Zeitstempel keine Statusübernahme
            events=history,
        )

    # --- Verbindungstest -------------------------------------------------------

    def _test_api(self, api: str, number: str) -> tuple[bool, str]:
        label = API_LABELS[api]
        try:
            if api == PARCEL_DE:
                self._parcel_preconditions()
            self._reserve_call()
            request = self._parcel_request(number) if api == PARCEL_DE else self._request(number)
            try:
                body = self._send(request)
            except urllib.error.HTTPError as exc:
                if api == UNIFIED and exc.code in (400, 404):
                    return True, f"{label}: ✓ API erreichbar · ✓ Authentifizierung erfolgreich · Sendung unbekannt"
                raise (self._parcel_http_error(exc, number) if api == PARCEL_DE
                       else self._http_error(exc, number)) from None
            if api == PARCEL_DE:
                try:
                    shipment = self.parse_parcel(body, number)
                except ProviderError as exc:
                    if isinstance(exc, _AuthError) or exc.abort:
                        raise
                    return True, f"{label}: ✓ API erreichbar · ✓ Authentifizierung erfolgreich · {exc}"
            else:
                shipment = self._parse(body, number)
            self._api_success(api)
            return True, (f"{label}: ✓ API erreichbar · ✓ Authentifizierung erfolgreich · ✓ Sendungsdaten "
                          f"empfangen ({shipment.status.label})")
        except ProviderError as exc:
            return False, f"{label}: ✗ {self._redact(exc)}"

    def test_connection(self, tracking_number: str = "") -> str:
        """Testet jede konfigurierte Schnittstelle (je 1 Abfrage). Mit tracking_number (aktive eigene Sendung)
        werden echte Sendungsdaten geprüft, sonst eine nicht existierende Testnummer."""
        if self.credentials_status() == "missing":
            raise ProviderError(self._missing_credentials())
        number = tracking_number or _TEST_NUMBER
        apis = ([PARCEL_DE] if self._setting("api_secret") or self._mode() == PARCEL_DE else []) + \
            ([UNIFIED] if self._mode() != PARCEL_DE else [])
        results = [self._test_api(api, number) for api in apis]
        message = " | ".join(text for _, text in results)
        used = self._plan()[0]
        ok = dict(zip(apis, (r[0] for r in results)))
        if not ok.get(used, False) and not (self._mode() == "auto" and any(ok.values())):
            raise ProviderError(message)
        return message

    def _problem_detail(self, exc: urllib.error.HTTPError) -> str:
        """Kurzer Text aus einer RFC-7807-Fehlerantwort (title/detail), ohne Header."""
        data = self._read_json_error(exc)
        if not isinstance(data, dict):
            return ""
        return self._short(" – ".join(str(data[k]) for k in ("title", "detail") if data.get(k)))

    def _http_error(self, exc: urllib.error.HTTPError, tracking_number: str, api: str = UNIFIED) -> ProviderError:
        code = exc.code
        detail = self._problem_detail(exc)
        if code in (401, 403):
            # Der Gateway-Fehler sagt nicht, ob der Key falsch oder die App nicht freigeschaltet ist – nicht raten
            verb = "abgelehnt" if code == 401 else "verweigert"
            return _AuthError(f"DHL hat die Authentifizierung mit HTTP {code} {verb}{detail}. Bitte prüfen: API-Key "
                              "korrekt kopiert (Produktions-Key, kein Sandbox-Key) und App unter developer.dhl.com → "
                              "My Apps für „Shipment Tracking – Unified“ freigegeben.")
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
            return ProviderError(f"DHL-Serverfehler (HTTP {code}, {API_LABELS[api]}) – neuer Versuch im nächsten "
                                 "Lauf", abort=True)
        return ProviderError(f"Unerwartete Antwort von DHL (HTTP {code}, {API_LABELS[api]}){detail}")

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
        # Die API kennt kein eigenes "in Zustellung"/"abholbereit" – aus dem Text ableiten
        if status == Status.IN_TRANSIT:
            status = status_from_keywords(text, cls._TEXT_RULES) or status
        elif status == Status.EXCEPTION:
            status = status_from_keywords(text, cls._TEXT_RULES[:1]) or status  # Rücksendung statt "Problem"
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
