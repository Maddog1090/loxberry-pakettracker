"""Datenmodell: normalisierter Sendungsstatus und Sendungen."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import IntEnum

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Europe/Berlin")
except Exception:  # Python ohne zoneinfo/tzdata: Systemzeitzone (auf dem LoxBerry ebenfalls Europe/Berlin)
    LOCAL_TZ = None


class Status(IntEnum):
    """Anbieterunabhängiger Status.

    Die Zahlenwerte werden 1:1 an Loxone übergeben und dürfen sich nicht ändern.
    """

    UNKNOWN = 0
    ANNOUNCED = 1
    IN_TRANSIT = 2
    OUT_FOR_DELIVERY = 3
    DELIVERED = 4
    PICKUP_READY = 5
    EXCEPTION = 6
    RETURNED = 7

    @property
    def key(self) -> str:
        return self.name.lower()

    @property
    def label(self) -> str:
        return STATUS_LABELS[self]

    @classmethod
    def from_key(cls, key: object) -> Status:
        try:
            return cls[str(key).upper()]
        except KeyError:
            return cls.UNKNOWN


STATUS_LABELS = {
    Status.UNKNOWN: "Unbekannt",
    Status.ANNOUNCED: "Angekündigt",
    Status.IN_TRANSIT: "Unterwegs",
    Status.OUT_FOR_DELIVERY: "In Zustellung",
    Status.DELIVERED: "Zugestellt",
    Status.PICKUP_READY: "Abholbereit",
    Status.EXCEPTION: "Problem",
    Status.RETURNED: "Rücksendung",
}

# Sortierung der Loxone-Slots: das für heute Relevante zuerst
STATUS_PRIORITY = (
    Status.OUT_FOR_DELIVERY,
    Status.PICKUP_READY,
    Status.EXCEPTION,
    Status.IN_TRANSIT,
    Status.ANNOUNCED,
    Status.UNKNOWN,
    Status.RETURNED,
    Status.DELIVERED,
)


# So lange gilt eine erfolgreiche Live-Abfrage als aktuell (größter Abfrageabstand 24 h plus Reserve)
LIVE_FRESH = timedelta(hours=48)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    if value.endswith(("Z", "z")):  # vor Python 3.11 versteht fromisoformat kein "Z"
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def local_now(now: datetime | None = None) -> datetime:
    """Zeitpunkt in Ortszeit (Europe/Berlin)."""
    now = now or datetime.now(timezone.utc)
    return now.astimezone(LOCAL_TZ) if LOCAL_TZ else now.astimezone()


def local_today(now: datetime | None = None) -> date:
    """Heutiger Kalendertag in Europe/Berlin – Grundlage aller Tagesvergleiche."""
    return local_now(now).date()


def local_date(value: str | None) -> date | None:
    """Kalendertag (Europe/Berlin) eines ISO-Zeitstempels."""
    dt = parse_ts(value)
    return local_now(dt).date() if dt else None


def parse_date(value: str | None) -> date | None:
    """Termin im Format JJJJ-MM-TT; alles andere (leer, ungültig) → None."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


# Relative Tagesangaben in Statustexten (meist Mail-Betreffs wie „In Zustellung – kommt heute“).
# Sie gelten nur am Tag der Statusinformation und werden deshalb bei jeder Ausgabe neu berechnet.
_RELATIVE = re.compile(r"(?<!guten )(?P<lead>\b(?:kommt|arriving|arrives)\s+)?"
                       r"\b(?P<word>übermorgen|heute|morgen|today|tomorrow)\b", re.I)
_RELATIVE_OFFSET = {"heute": 0, "morgen": 1, "übermorgen": 2, "today": 0, "tomorrow": 1}
_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_SEPARATORS = "–—\\-·:,|"


def _relative_word(word: str, target: date, today: date) -> str:
    english = word.lower() in ("today", "tomorrow")
    delta = (target - today).days
    if delta < 0:
        return ""
    if delta == 0:
        result = "today" if english else "heute"
    elif delta == 1:
        result = "tomorrow" if english else "morgen"
    elif delta == 2 and not english:
        result = "übermorgen"
    else:
        result = f"on {target:%d.%m.}" if english else f"am {target:%d.%m.}"
    return result[0].upper() + result[1:] if word[:1].isupper() else result


def render_relative(text: str, reference: date | None, today: date) -> str:
    """Löst „heute/morgen/übermorgen“ bezogen auf den Tag der Statusinformation auf.

    Liegt der gemeinte Tag in der Vergangenheit (oder ist der Bezugstag unbekannt), wird die
    Angabe samt „kommt“ entfernt – ein alter Text sagt so nie wieder „kommt heute“.
    """
    if not text or not _RELATIVE.search(text):
        return text

    def replace(m: re.Match) -> str:
        if reference is None:
            return ""
        target = reference + timedelta(days=_RELATIVE_OFFSET[m.group("word").lower()])
        word = _relative_word(m.group("word"), target, today)
        return (m.group("lead") or "") + word if word else ""

    result = _RELATIVE.sub(replace, text)
    result = re.sub(rf"\s+([{_SEPARATORS}])(?:\s*[{_SEPARATORS}])+", r" \1", result)  # doppelte Trenner
    result = re.sub(r"\s{2,}", " ", result)
    return result.strip().strip(_SEPARATORS.replace("\\", "")).strip()


@dataclass
class TrackingEvent:
    timestamp: str
    description: str
    location: str = ""


@dataclass
class Shipment:
    provider: str
    tracking_number: str
    description: str = ""
    status: Status = Status.UNKNOWN
    status_text: str = ""
    eta: str = ""  # YYYY-MM-DD oder leer
    eta_window: str = ""  # Zustellzeitfenster in Ortszeit, z.B. "10:00–14:00" (nur zusammen mit eta)
    last_update: str = ""  # Zeitstempel der letzten Statusinformation
    delivered_at: str = ""
    first_seen: str = ""
    # Bestell- oder Kundenreferenz (z.B. Amazon-Bestellnummer) – verbindet Mails ohne Sendungsnummer
    reference: str = ""
    # Wie die Sendung in die Liste kam: "manual" (Weboberfläche) und/oder "email"
    origins: list[str] = field(default_factory=list)
    events: list[TrackingEvent] = field(default_factory=list)
    # Zeitpunkt der letzten erfolgreichen Live-Abfrage (API lieferte einen Status)
    live_checked: str = ""

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.tracking_number}"

    @property
    def is_final(self) -> bool:
        return self.status in (Status.DELIVERED, Status.RETURNED)

    def reset_status(self) -> None:
        """Verwirft Statusdaten (z.B. simulierte aus dem Testmodus), Identität und Herkunft bleiben."""
        self.status = Status.UNKNOWN
        self.status_text = self.eta = self.eta_window = self.last_update = self.delivered_at = ""
        self.live_checked = ""
        self.events = []

    def live_fresh(self, now: datetime | None = None) -> bool:
        """Hat eine Live-Abfrage kürzlich einen Status geliefert? Dann hat sie Vorrang vor Mails."""
        checked = parse_ts(self.live_checked)
        return checked is not None and (now or datetime.now(timezone.utc)) - checked <= LIVE_FRESH

    def is_stale(self, today: date, now: datetime | None = None) -> bool:
        """Termin verstrichen, seitdem keine neue Information und kein aktuelles Live-Tracking.

        Solche Sendungen (typisch: Amazon-/DPD-/GLS-Mails ohne Zustellmail) gelten nicht mehr als
        aktiv. Abholbereite Sendungen bleiben sichtbar – sie warten unabhängig vom Termin.
        """
        if self.is_final or self.status == Status.PICKUP_READY:
            return False
        eta = parse_date(self.eta)
        if eta is None or eta >= today or self.live_fresh(now):
            return False
        updated = local_date(self.last_update)
        return not (updated and updated > eta)

    def display_text(self, today: date) -> str:
        """Statustext mit relativen Tagesangaben, die zum heutigen Tag passen."""
        return render_relative(self.status_text, local_date(self.last_update), today)

    def eta_text(self, today: date, stale: bool = False) -> str:
        """Termin als Text, bei jedem Lauf neu: „kommt heute“, „kommt morgen“, „kommt am Fr 09.10.“ …"""
        eta = parse_date(self.eta)
        if self.is_final or eta is None:
            return ""
        delta = (eta - today).days
        if delta == 0:
            return "kommt heute"
        if delta == 1:
            return "kommt morgen"
        if delta > 1:
            return f"kommt am {_WEEKDAYS[eta.weekday()]} {eta:%d.%m.}"
        if stale:
            return f"Termin {eta:%d.%m.} überschritten"
        return f"verspätet – ursprünglicher Termin {eta:%d.%m.}"

    def merge(self, other: Shipment, authoritative: bool = False, status: bool = True) -> None:
        """Übernimmt Informationen aus `other`, sofern diese nicht älter sind.

        authoritative: Ergebnis einer Live-Abfrage – gilt auch, wenn sein Ereigniszeitpunkt älter
                       ist als eine zwischenzeitlich eingegangene Mail (Live-Status hat Vorrang).
        status=False:  nur Herkunft/Beschreibung/Referenz übernehmen (Mail bei aktivem Live-Tracking).
        """
        if other.live_checked and (parse_ts(other.live_checked) or datetime.min.replace(tzinfo=timezone.utc)) \
                > (parse_ts(self.live_checked) or datetime.min.replace(tzinfo=timezone.utc)):
            self.live_checked = other.live_checked
        for origin in other.origins:
            if origin not in self.origins:
                self.origins.append(origin)
        if other.description and not self.description:
            self.description = other.description
        if other.reference and not self.reference:
            self.reference = other.reference
        if not status:
            return
        if other.eta and not self.eta:  # ein (älterer) Termin ist besser als keiner
            self.eta, self.eta_window = other.eta, other.eta_window

        mine, theirs = parse_ts(self.last_update), parse_ts(other.last_update)
        if theirs is None or (not authoritative and mine is not None and theirs < mine):
            return
        self.status = other.status
        self.status_text = other.status_text
        self.last_update = other.last_update
        if other.eta:
            self.eta, self.eta_window = other.eta, other.eta_window
        if other.events:
            self.events = list(other.events)
        if self.status == Status.DELIVERED and not self.delivered_at:
            self.delivered_at = other.delivered_at or other.last_update

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "provider": self.provider,
            "tracking_number": self.tracking_number,
            "description": self.description,
            "status": self.status.key,
            "status_code": int(self.status),
            "status_label": self.status.label,
            "status_text": self.status_text,
            "eta": self.eta,
            "eta_window": self.eta_window,
            "last_update": self.last_update,
            "delivered_at": self.delivered_at,
            "first_seen": self.first_seen,
            "reference": self.reference,
            "origins": list(self.origins),
            "events": [asdict(e) for e in self.events],
            "live_checked": self.live_checked,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Shipment:
        return cls(
            provider=str(data["provider"]),
            tracking_number=str(data["tracking_number"]),
            description=data.get("description", ""),
            status=Status.from_key(data.get("status")),
            # state.json enthält seit 1.0.1 den aufbereiteten Text; gespeichert wird das Original
            status_text=data.get("status_text_raw", data.get("status_text", "")),
            eta=data.get("eta", ""),
            eta_window=data.get("eta_window", ""),
            last_update=data.get("last_update", ""),
            delivered_at=data.get("delivered_at", ""),
            first_seen=data.get("first_seen", ""),
            reference=data.get("reference", ""),
            origins=list(data.get("origins", [])),
            events=[TrackingEvent(**e) for e in data.get("events", [])],
            live_checked=data.get("live_checked", ""),
        )
