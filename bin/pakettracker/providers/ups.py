"""UPS.

Live-Tracking: offizielle UPS Tracking API (developer.ups.com, Spezifikation
github.com/UPS-API/api-documentation: OAuthClientCredentials.yaml, Tracking.yaml).
  1. Token:  POST <base>/security/v1/oauth/token  (Basic-Auth Client-ID:Secret,
             grant_type=client_credentials) → access_token, expires_in
  2. Status: GET  <base>/api/track/v1/details/{inquiryNumber}?locale=de_DE
             (Termin: package.deliveryDate[], Zeitfenster: package.deliveryTime.startTime/endTime)
             Header: Authorization: Bearer …, transId (eindeutig), transactionSrc
  base = https://onlinetools.ups.com (Produktion) bzw. https://wwwcie.ups.com (Testumgebung)
Der Token bleibt nur im Arbeitsspeicher des jeweiligen Laufs.
Ankündigungen: UPS-Benachrichtigungsmails (ups.com).
"""
from __future__ import annotations

import base64
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid

from ..models import Shipment, Status, TrackingEvent
from ..registry import register
from ..schema import Field
from ..sources.mail import Mail
from . import checkdigits
from .apibase import ApiProvider, throttle_fields
from .base import ProviderError, status_from_keywords
from .mailparse import parse_carrier_email

_BASE_URLS = {"production": "https://onlinetools.ups.com", "test": "https://wwwcie.ups.com"}

# currentStatus.type / activity.status.type (UPS-Statustypen)
_TYPE_STATUS = {
    "M": Status.ANNOUNCED,         # Sendungsdaten übermittelt (Manifest)
    "MV": Status.UNKNOWN,          # Manifest storniert
    "P": Status.IN_TRANSIT,        # abgeholt
    "I": Status.IN_TRANSIT,        # unterwegs
    "W": Status.IN_TRANSIT,        # Lager
    "DO": Status.IN_TRANSIT,
    "DD": Status.IN_TRANSIT,
    "O": Status.OUT_FOR_DELIVERY,  # in Zustellung
    "D": Status.DELIVERED,
    "X": Status.EXCEPTION,
    "RS": Status.RETURNED,         # zurück an Absender
    "NA": Status.UNKNOWN,
}
_TEXT_RULES = (
    (Status.OUT_FOR_DELIVERY, ("out for delivery", "in zustellung", "zustellung heute", "heute zugestellt")),
    (Status.PICKUP_READY, ("access point", "abholbereit", "ready for pickup", "zur abholung")),
)


def _iso_date(value: object) -> str:
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if re.fullmatch(r"\d{8}", text) else ""


def _hhmm(value: object) -> str:
    text = str(value or "")
    return f"{text[:2]}:{text[2:4]}" if re.fullmatch(r"\d{4}(\d{2})?", text) and text[:4] != "0000" else ""


def _window(delivery_time: object) -> str:
    """deliveryTime (startTime/endTime als HHMMSS, Ortszeit des Empfängers) → "10:30–14:00" bzw. "bis 12:00"."""
    if not isinstance(delivery_time, dict):
        return ""
    start, end = _hhmm(delivery_time.get("startTime")), _hhmm(delivery_time.get("endTime"))
    if start and end and start < end:
        return f"{start}–{end}"
    return f"bis {end}" if end else ""


def _activity_ts(activity: dict) -> str:
    gmt_date, gmt_time = str(activity.get("gmtDate") or ""), str(activity.get("gmtTime") or "")
    if re.fullmatch(r"\d{8}", gmt_date) and re.fullmatch(r"\d{1,6}", gmt_time):
        t = gmt_time.zfill(6)
        return f"{_iso_date(gmt_date)}T{t[:2]}:{t[2:4]}:{t[4:6]}+00:00"
    day, time = str(activity.get("date") or ""), str(activity.get("time") or "")
    if re.fullmatch(r"\d{8}", day):
        t = time.zfill(6) if re.fullmatch(r"\d{1,6}", time) else "000000"
        return f"{_iso_date(day)}T{t[:2]}:{t[2:4]}:{t[4:6]}"
    return ""


@register
class UpsProvider(ApiProvider):
    id = "ups"
    name = "UPS"
    detection_priority = 50
    email_domains = ("ups.com",)
    required_secrets = ("client_id", "client_secret")
    supports_test = True
    settings_schema = (
        Field("client_id", "Client-ID", secret=True, help="Aus developer.ups.com → Apps → Ihre App (Credentials)."),
        Field("client_secret", "Client-Secret", secret=True),
        Field("environment", "Umgebung", "select", "production", options=("production", "test"),
              help="test = UPS-Testumgebung (CIE) mit Beispieldaten"),
        Field("language", "Sprache der Statustexte", "select", "de", options=("de", "en")),
        *throttle_fields(60, 250, "Eigenes Sicherheitslimit; UPS veröffentlicht für die Tracking-API kein festes "
                                  "Tageskontingent."),
    )
    strong_patterns = (re.compile(r"1Z[0-9A-Z]{16}"),)
    tracking_url_template = "https://www.ups.com/track?loc=de_DE&tracknum={number}"

    BASE_URL = ""  # nur für Tests überschreiben
    MIN_SPACING = 1.0

    def __init__(self, settings: dict, mock: bool, log: logging.Logger, state: dict | None = None):
        super().__init__(settings, mock, log, state)
        self._access_token = ""
        self._token_expiry = 0.0

    @classmethod
    def check_digit_ok(cls, number: str) -> bool | None:
        return checkdigits.ups_1z(number) if number.startswith("1Z") else None

    def _base(self) -> str:
        return self.BASE_URL or _BASE_URLS.get(self.settings.get("environment"), _BASE_URLS["production"])

    def _secrets(self) -> list[str]:
        return super()._secrets() + ([self._access_token] if self._access_token else [])

    @staticmethod
    def _error_detail(data: object) -> str:
        errors = ((data or {}).get("response") or {}).get("errors") if isinstance(data, dict) else None
        if not isinstance(errors, list):
            return ""
        texts = [f"{e.get('code', '')} {e.get('message', '')}".strip() for e in errors if isinstance(e, dict)]
        return ApiProvider._short("; ".join(t for t in texts if t))

    # --- OAuth ---------------------------------------------------------------

    def _token(self) -> str:
        if self._access_token and self._clock() < self._token_expiry:
            return self._access_token
        client = f"{self.settings.get('client_id', '').strip()}:{self.settings.get('client_secret', '').strip()}"
        request = urllib.request.Request(
            f"{self._base()}/security/v1/oauth/token",
            data=b"grant_type=client_credentials",
            method="POST",
            headers={
                "Authorization": "Basic " + base64.b64encode(client.encode()).decode(),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            body = self._send(request)
        except urllib.error.HTTPError as exc:
            detail = self._error_detail(self._read_json_error(exc))
            if exc.code in (400, 401, 403):
                raise ProviderError(f"UPS lehnt die Anmeldung ab (HTTP {exc.code}){detail}. Client-ID/Secret und "
                                    "freigegebene Produkte der App (Tracking) prüfen.",
                                    abort=True, level=logging.ERROR) from None
            if exc.code == 429:
                raise self._rate_limited(exc, detail) from None
            raise ProviderError(f"UPS-Anmeldung fehlgeschlagen (HTTP {exc.code}){detail}", abort=True) from None
        data = self._load_json(body)
        token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token:
            raise ProviderError("Ungültige Token-Antwort von UPS", abort=True)
        try:
            lifetime = int(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            lifetime = 3600
        self._access_token = token
        self._token_expiry = self._clock() + max(60, lifetime - 60)
        return token

    # --- Abfrage -------------------------------------------------------------

    def _fetch(self, tracking_number: str) -> Shipment:
        token = self._token()
        self._reserve_call()
        locale = "de_DE" if self.settings.get("language", "de") == "de" else "en_US"
        query = urllib.parse.urlencode({"locale": locale, "returnSignature": "false",
                                        "returnMilestones": "false", "returnPOD": "false"})
        request = urllib.request.Request(
            f"{self._base()}/api/track/v1/details/{urllib.parse.quote(tracking_number, safe='')}?{query}",
            headers={
                "Authorization": f"Bearer {token}",
                "transId": uuid.uuid4().hex,
                "transactionSrc": "LoxBerryPakettracker",
                "Accept": "application/json",
            },
        )
        try:
            body = self._send(request)
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc, tracking_number) from None
        self._mark_checked(tracking_number)
        shipment = self._parse(body, tracking_number)
        usage = self.state["usage"]
        self.log.info("%s abgefragt: %s (heute %d/%d Abfragen)", tracking_number, shipment.status.label,
                      usage["count"], self.settings.get("daily_limit", 250))
        return shipment

    def _test(self) -> str:
        self._token()
        env = "Testumgebung" if self.settings.get("environment") == "test" else "Produktion"
        return f"UPS-Anmeldung erfolgreich ({env}, Token erhalten – keine Tracking-Abfrage verbraucht)."

    def _http_error(self, exc: urllib.error.HTTPError, tracking_number: str) -> ProviderError:
        code = exc.code
        detail = self._error_detail(self._read_json_error(exc))
        if code in (401, 403):
            self._access_token = ""
            return ProviderError(f"UPS verweigert den Zugriff (HTTP {code}){detail}. Zugangsdaten und Freigabe "
                                 "der Tracking-API in der App prüfen.", abort=True, level=logging.ERROR)
        if code == 404:
            self._mark_checked(tracking_number)
            return ProviderError(f"Sendung bei UPS (noch) nicht gefunden{detail} – bisherige Daten bleiben erhalten",
                                 level=logging.INFO)
        if code == 400:
            self._mark_checked(tracking_number)
            return ProviderError(f"UPS lehnt die Anfrage ab (HTTP 400){detail} – Sendungsnummer prüfen")
        if code == 429:
            return self._rate_limited(exc, detail)
        if code >= 500:
            return ProviderError(f"UPS-Serverfehler (HTTP {code}) – neuer Versuch im nächsten Lauf", abort=True)
        return ProviderError(f"Unerwartete Antwort von UPS (HTTP {code}){detail}")

    def _parse(self, body: bytes, tracking_number: str) -> Shipment:
        data = self._load_json(body)
        if data is None:
            raise ProviderError("Ungültige Antwort von UPS (kein gültiges JSON)")
        shipments = ((data.get("trackResponse") or {}).get("shipment")
                     if isinstance(data, dict) and isinstance(data.get("trackResponse"), dict) else None)
        candidates = [s for s in shipments if isinstance(s, dict)] if isinstance(shipments, list) else []
        if not candidates:
            raise ProviderError("Antwort von UPS enthält keine Sendungsdaten")
        shipment = next((s for s in candidates if str(s.get("inquiryNumber", "")).upper() == tracking_number),
                        candidates[0])
        packages = [p for p in shipment.get("package") or [] if isinstance(p, dict)]
        if not packages:
            warnings = [w.get("message", "") for w in shipment.get("warnings") or [] if isinstance(w, dict)]
            raise ProviderError(f"Sendung bei UPS (noch) nicht gefunden{self._short('; '.join(warnings))}",
                                level=logging.INFO)
        package = next((p for p in packages if str(p.get("trackingNumber", "")).upper() == tracking_number),
                       packages[0])
        try:
            return self.map_package(package, tracking_number)
        except (AttributeError, TypeError, ValueError):
            raise ProviderError("Unerwartetes Antwortformat von UPS") from None

    @classmethod
    def map_package(cls, package: dict, tracking_number: str) -> Shipment:
        current = package.get("currentStatus") if isinstance(package.get("currentStatus"), dict) else {}
        status = _TYPE_STATUS.get(str(current.get("type") or "").upper(), Status.UNKNOWN)
        text = str(current.get("description") or current.get("simplifiedTextDescription") or "")
        if status in (Status.IN_TRANSIT, Status.UNKNOWN):
            status = status_from_keywords(text, _TEXT_RULES) or status

        activities = [a for a in package.get("activity") or [] if isinstance(a, dict)]
        events = []
        for activity in activities:
            st = activity.get("status") if isinstance(activity.get("status"), dict) else {}
            location = activity.get("location") if isinstance(activity.get("location"), dict) else {}
            address = location.get("address") if isinstance(location.get("address"), dict) else {}
            events.append(TrackingEvent(timestamp=_activity_ts(activity), description=str(st.get("description") or ""),
                                        location=str(address.get("city") or "")))

        dates = {d.get("type"): _iso_date(d.get("date"))
                 for d in package.get("deliveryDate") or [] if isinstance(d, dict)}
        eta = dates.get("DEL") if status == Status.DELIVERED else dates.get("RDD") or dates.get("SDD")
        return Shipment(
            provider=cls.id,
            tracking_number=tracking_number,
            status=status,
            status_text=text,
            eta=eta or "",
            eta_window=_window(package.get("deliveryTime")) if eta and status != Status.DELIVERED else "",
            last_update=_activity_ts(activities[0]) if activities else "",
            events=events,
        )

    # --- E-Mail --------------------------------------------------------------

    def parse_email(self, mail: Mail) -> list[Shipment]:
        if not self.handles_sender(mail.sender):
            return []
        return parse_carrier_email(self, mail)
