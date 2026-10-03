"""Basisklasse und Hilfsfunktionen für Anbieter.

Neuen Anbieter ergänzen:
  1. Datei `providers/<id>.py` anlegen
  2. Klasse von `Provider` (nur E-Mail: `MailCarrierProvider`, mit API: `ApiProvider`)
     ableiten und mit `@register` dekorieren
  3. `id`, `name`, `email_domains`, `tracking_patterns`/`strong_patterns`, ggf. `settings_schema` setzen
  4. `fetch()` (Live-Tracking) und/oder `parse_email()` (Ankündigungen) implementieren
Weboberfläche, Konfiguration, Erkennung, MQTT und REST übernehmen den Anbieter automatisch.
"""
from __future__ import annotations

import hashlib
import logging
import re
from abc import ABC
from datetime import date, timedelta
from typing import ClassVar

from ..models import Shipment, Status, local_now, local_today, now_iso, parse_ts
from ..schema import Field, Section
from ..sources.mail import Mail


class ProviderError(Exception):
    """Erwarteter Fehler bei einer Abfrage (z.B. fehlender API-Key, Sendung unbekannt).

    abort=True: Der Anbieter wird für den Rest des Laufs nicht mehr abgefragt
                (z.B. ungültiger API-Key, Netzwerk weg, Rate-Limit).
    level:      Log-Level, mit dem die Engine den Fehler protokolliert.
    Die Meldung darf keine Zugangsdaten enthalten.
    """

    def __init__(self, message: str, *, abort: bool = False, level: int = logging.WARNING):
        super().__init__(message)
        self.abort = abort
        self.level = level


# Erkennungssicherheit einer Sendungsnummer
CONFIDENCE_NONE = 0
CONFIDENCE_WEAK = 1    # passt nur zum Format (z.B. „12 Ziffern“) – oft mehrdeutig
CONFIDENCE_STRONG = 3  # eindeutiges Präfix oder gültige Prüfziffer


class Provider(ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    # Zusätzliche Einstellungen; "enabled" wird automatisch ergänzt
    settings_schema: ClassVar[tuple[Field, ...]] = ()
    enabled_by_default: ClassVar[bool] = True
    # True, wenn fetch() einzelne Sendungen live abfragen kann
    live_tracking: ClassVar[bool] = False
    # Nummernformate zur automatischen Anbietererkennung (fullmatch, Großbuchstaben, ohne Leerzeichen)
    tracking_patterns: ClassVar[tuple[re.Pattern[str], ...]] = ()   # schwach (nur Format)
    strong_patterns: ClassVar[tuple[re.Pattern[str], ...]] = ()     # eindeutig (Präfix/Prüfziffer)
    # Bei gleicher Sicherheit gewinnt der kleinere Wert (verbreitetere Anbieter zuerst)
    detection_priority: ClassVar[int] = 100
    # Absender-Domains der Benachrichtigungsmails (auch Subdomains)
    email_domains: ClassVar[tuple[str, ...]] = ()
    # Geheime Felder, ohne die keine Live-Abfrage möglich ist
    required_secrets: ClassVar[tuple[str, ...]] = ()
    # Bietet test_connection() an (Button in der Oberfläche)
    supports_test: ClassVar[bool] = False
    # Link zur Sendungsverfolgung beim Anbieter, {number} wird ersetzt
    tracking_url_template: ClassVar[str] = ""
    # Abweichender Hinweistext zur Datenquelle in den Einstellungen (leer = Standardtext)
    source_note: ClassVar[str] = ""

    def __init__(self, settings: dict, mock: bool, log: logging.Logger, state: dict | None = None):
        self.settings = settings  # inkl. Geheimnisse aus credentials.json
        self.mock = mock
        self.log = log
        # Bleibt zwischen Läufen erhalten (data/provider_state.json), z.B. für Rate-Limits
        self.state = state if state is not None else {}

    @classmethod
    def section(cls) -> Section:
        enabled = Field("enabled", "Aktiviert", "bool", cls.enabled_by_default)
        return Section(
            id=f"providers.{cls.id}",
            title=cls.name,
            fields=(enabled, *cls.settings_schema),
            meta=(
                ("provider_id", cls.id),
                ("live_tracking", cls.live_tracking),
                ("data_source", cls.data_source()),
                ("required_secrets", list(cls.required_secrets)),
                ("supports_test", cls.supports_test),
                ("tracking_url_template", cls.tracking_url_template),
                ("source_note", cls.source_note),
            ),
        )

    @classmethod
    def data_source(cls) -> str:
        return cls._source(cls.live_tracking)

    def current_source(self) -> str:
        """Wie data_source(), berücksichtigt aber eine per Einstellung abschaltbare Live-Abfrage."""
        return self._source(self.live_tracking)

    @classmethod
    def _source(cls, live: bool) -> str:
        if live:
            return "api+email" if cls.email_domains else "api"
        return "email"

    @staticmethod
    def normalize(tracking_number: str) -> str:
        return re.sub(r"[\s-]+", "", str(tracking_number)).upper()

    @classmethod
    def check_digit_ok(cls, number: str) -> bool | None:
        """Prüfziffer für starke Muster: True/False, None = kein Verfahren bekannt."""
        return None

    @classmethod
    def match_confidence(cls, tracking_number: str) -> int:
        number = cls.normalize(tracking_number)
        if any(p.fullmatch(number) for p in cls.strong_patterns):
            return CONFIDENCE_WEAK if cls.check_digit_ok(number) is False else CONFIDENCE_STRONG
        if any(p.fullmatch(number) for p in cls.tracking_patterns):
            return CONFIDENCE_WEAK
        return CONFIDENCE_NONE

    @classmethod
    def recognizes(cls, tracking_number: str) -> bool:
        return cls.match_confidence(tracking_number) > CONFIDENCE_NONE

    def handles_sender(self, sender: str) -> bool:
        """Stammt die Mail von diesem Anbieter? (Vorfilter für den E-Mail-Abruf)"""
        return sender_matches(sender, self.email_domains)

    def credentials_status(self) -> str:
        """"ok", "missing" oder "none" (Anbieter braucht keine Zugangsdaten)."""
        if not self.required_secrets:
            return "none"
        return "ok" if all(str(self.settings.get(k) or "").strip() for k in self.required_secrets) else "missing"

    def test_connection(self) -> str:
        """Prüft Zugangsdaten/Erreichbarkeit; liefert eine Meldung oder wirft ProviderError."""
        raise ProviderError(f"{self.name}: kein Verbindungstest verfügbar")

    def due(self, tracking_number: str) -> bool:
        """Soll die Sendung in diesem Lauf live abgefragt werden? (Nur außerhalb des Testmodus.)"""
        return True

    def forget(self, active_numbers: set[str]) -> None:
        """Gibt Zustandsdaten zu Sendungen frei, die nicht mehr verfolgt werden."""

    def track(self, tracking_number: str) -> Shipment:
        if self.mock:
            return mock_shipment(self.id, tracking_number)
        return self.fetch(tracking_number)

    def fetch(self, tracking_number: str) -> Shipment:
        """Live-Abfrage beim Anbieter. Wirft ProviderError bei erwartbaren Fehlern."""
        raise NotImplementedError(f"{self.name}: Live-Abfrage nicht verfügbar")

    def parse_email(self, mail: Mail) -> list[Shipment]:
        """Erkennt Sendungen in einer E-Mail. Standard: keine."""
        return []


# --- Hilfsfunktionen für Provider -------------------------------------------

# Reihenfolge ist wichtig: spezifische Formulierungen zuerst
# ("wird heute zugestellt" darf nicht als "zugestellt" erkannt werden).
DEFAULT_EMAIL_RULES: tuple[tuple[Status, tuple[str, ...]], ...] = (
    (Status.OUT_FOR_DELIVERY, ("heute zugestellt", "kommt heute", "in zustellung", "zustellung heute",
                               "zustellung erfolgt heute", "heute geliefert", "out for delivery",
                               "arriving today", "delivery today")),
    (Status.PICKUP_READY, ("abholbereit", "zur abholung bereit", "abholen", "im paketshop", "im parcelshop",
                           "access point", "abholstation", "ready for pickup", "ready for collection")),
    (Status.EXCEPTION, ("nicht zugestellt", "konnte nicht", "zustellversuch", "verzögert", "problem",
                        "delayed", "exception", "delivery attempt")),
    (Status.RETURNED, ("rücksendung", "zurückgesendet", "zurück an den absender", "returned")),
    (Status.DELIVERED, ("zugestellt", "geliefert", "delivered")),
    (Status.IN_TRANSIT, ("versandt", "verschickt", "unterwegs", "auf dem weg", "shipped", "on the way",
                         "in transit")),
    (Status.ANNOUNCED, ("angekündigt", "paketankündigung", "kommt am", "kommt bald", "sendungsdaten",
                        "bestellung", "bestellt", "ordered", "label created", "information received")),
)


def status_from_keywords(text: str,
                         rules: tuple[tuple[Status, tuple[str, ...]], ...] = DEFAULT_EMAIL_RULES) -> Status | None:
    low = text.lower()
    for status, words in rules:
        if any(w in low for w in words):
            return status
    return None


def sender_matches(sender: str, domains: list[str] | tuple[str, ...]) -> bool:
    match = re.search(r"@([\w.-]+)", sender)
    host = (match.group(1) if match else sender).lower()
    return any(host == d or host.endswith("." + d) for d in domains if d)


_MONTHS = {
    "januar": 1, "jan": 1, "februar": 2, "feb": 2, "märz": 3, "maerz": 3, "mär": 3,
    "april": 4, "apr": 4, "mai": 5, "juni": 6, "jun": 6, "juli": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9, "oktober": 10, "okt": 10,
    "november": 11, "nov": 11, "dezember": 12, "dez": 12,
}
_ETA_HINT = re.compile(r"voraussichtlich|zustellung|lieferung|geliefert|ankunft|kommt|erwartet", re.I)
_RELATIVE = re.compile(r"\b(heute|übermorgen|morgen)\b", re.I)
_WEEKDAYS = ("montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag")
_WEEKDAY = re.compile(r"\bam\s+(" + "|".join(_WEEKDAYS) + r")\b(?!,?\s*\d)", re.I)
_NUM_DATE = re.compile(r"\b(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?(?!\d)")
_NAME_DATE = re.compile(r"\b(\d{1,2})\.\s*(" + "|".join(sorted(_MONTHS, key=len, reverse=True))
                        + r")\b\.?(?:\s+(\d{4}))?", re.I)


def _build_date(day: int, month: int, year: int | None, reference: date) -> date | None:
    try:
        result = date(year or reference.year, month, day)
    except ValueError:
        return None
    if year is None and result < reference - timedelta(days=30):
        result = result.replace(year=result.year + 1)  # Jahreswechsel
    return result


def extract_eta(text: str, reference: date) -> str:
    """Sucht hinter typischen Formulierungen nach einem Zustelltermin (YYYY-MM-DD)."""
    for hint in _ETA_HINT.finditer(text):
        end = hint.end() + 60
        while end < len(text) and not text[end].isspace():  # kein Datum mitten im Wort abschneiden
            end += 1
        window = text[hint.end(): end]
        found: list[tuple[int, date]] = []
        if m := _RELATIVE.search(window):
            offset = {"heute": 0, "morgen": 1, "übermorgen": 2}[m.group(1).lower()]
            found.append((m.start(), reference + timedelta(days=offset)))
        if m := _WEEKDAY.search(window):  # „am Montag“ ohne Datum → nächster solcher Tag
            days_ahead = (_WEEKDAYS.index(m.group(1).lower()) - reference.weekday()) % 7
            found.append((m.start(), reference + timedelta(days=days_ahead)))
        if m := _NUM_DATE.search(window):
            year = int(m.group(3)) if m.group(3) else None
            if year is not None and year < 100:
                year += 2000
            if d := _build_date(int(m.group(1)), int(m.group(2)), year, reference):
                found.append((m.start(), d))
        if m := _NAME_DATE.search(window):
            month = _MONTHS[m.group(2).lower()]
            if d := _build_date(int(m.group(1)), month, int(m.group(3)) if m.group(3) else None, reference):
                found.append((m.start(), d))
        if found:
            return min(found)[1].isoformat()
    return ""


def local_window(start: str, end: str) -> tuple[str, str]:
    """Zeitfenster aus zwei ISO-Zeitstempeln → (Datum, "HH:MM–HH:MM") in Ortszeit (Europe/Berlin).

    Ohne gültigen Beginn: ("", ""). Ohne gültiges Ende oder über Mitternacht: nur das Datum.
    """
    begin, finish = parse_ts(start), parse_ts(end)
    if begin is None:
        return "", ""
    begin = local_now(begin)
    day = begin.date().isoformat()
    if finish is None or local_now(finish).date() != begin.date() or finish <= begin:
        return day, ""
    return day, f"{begin:%H:%M}–{local_now(finish):%H:%M}"


_MOCK_FLOW = (Status.ANNOUNCED, Status.IN_TRANSIT, Status.OUT_FOR_DELIVERY, Status.PICKUP_READY, Status.DELIVERED)


def mock_shipment(provider_id: str, tracking_number: str) -> Shipment:
    """Deterministischer Fake-Status für den Testmodus (gleiche Nummer → gleicher Status)."""
    h = int(hashlib.sha256(f"{provider_id}:{tracking_number}".encode()).hexdigest(), 16)
    status = _MOCK_FLOW[h % len(_MOCK_FLOW)]
    days = 0 if status in (Status.OUT_FOR_DELIVERY, Status.PICKUP_READY, Status.DELIVERED) else 1 + h % 3
    return Shipment(
        provider=provider_id,
        tracking_number=tracking_number,
        status=status,
        status_text=f"[Testmodus] {status.label}",
        eta=(local_today() + timedelta(days=days)).isoformat(),
        last_update=now_iso(),
    )
