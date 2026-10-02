"""Datenmodell: normalisierter Sendungsstatus und Sendungen."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import IntEnum


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
        self.events = []

    def merge(self, other: Shipment) -> None:
        """Übernimmt Informationen aus `other`, sofern diese nicht älter sind."""
        for origin in other.origins:
            if origin not in self.origins:
                self.origins.append(origin)
        if other.description and not self.description:
            self.description = other.description
        if other.reference and not self.reference:
            self.reference = other.reference
        if other.eta and not self.eta:  # ein (älterer) Termin ist besser als keiner
            self.eta, self.eta_window = other.eta, other.eta_window

        mine, theirs = parse_ts(self.last_update), parse_ts(other.last_update)
        if theirs is None or (mine is not None and theirs < mine):
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> Shipment:
        return cls(
            provider=str(data["provider"]),
            tracking_number=str(data["tracking_number"]),
            description=data.get("description", ""),
            status=Status.from_key(data.get("status")),
            status_text=data.get("status_text", ""),
            eta=data.get("eta", ""),
            eta_window=data.get("eta_window", ""),
            last_update=data.get("last_update", ""),
            delivered_at=data.get("delivered_at", ""),
            first_seen=data.get("first_seen", ""),
            reference=data.get("reference", ""),
            origins=list(data.get("origins", [])),
            events=[TrackingEvent(**e) for e in data.get("events", [])],
        )
