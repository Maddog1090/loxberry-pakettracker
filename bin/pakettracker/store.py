"""Sammelt Sendungen eines Laufs und verhindert Duplikate.

Regeln:
- gleiche ID (anbieter:nummer)              → zusammenführen
- gleiche Nummer bei anderem Anbieter      → dieselbe Sendung; eine manuelle Anbieterwahl hat Vorrang
- Platzhalter ORDER-<referenz> (Amazon-Mail ohne Sendungsnummer)
                                            → wird durch die echte Sendung mit gleicher Referenz ersetzt
- Sendung eines deaktivierten Anbieters     → wird dem meldenden Anbieter zugeordnet (z.B. Amazon) oder verworfen
"""
from __future__ import annotations

import logging
from typing import Iterable

from .models import Shipment, now_iso

PLACEHOLDER_PREFIX = "ORDER-"


def is_placeholder(shipment: Shipment) -> bool:
    return shipment.tracking_number.startswith(PLACEHOLDER_PREFIX)


class ShipmentStore:
    def __init__(self, shipments: Iterable[Shipment], enabled: Iterable[str], log: logging.Logger):
        self.enabled = set(enabled)
        self.log = log
        self.items: dict[str, Shipment] = {s.id: s for s in shipments if s.provider in self.enabled}

    def values(self) -> list[Shipment]:
        return list(self.items.values())

    def remove(self, shipment_id: str) -> None:
        self.items.pop(shipment_id, None)

    def _rekey(self, shipment: Shipment, provider_id: str) -> None:
        self.items.pop(shipment.id, None)
        shipment.provider = provider_id
        self.items[shipment.id] = shipment

    def add(self, shipment: Shipment, reported_by: str | None = None) -> Shipment | None:
        if shipment.provider not in self.enabled:
            if reported_by and reported_by in self.enabled:
                shipment.provider = reported_by
            else:
                self.log.debug("Sendung eines deaktivierten Anbieters ignoriert")
                return None

        existing = self.items.get(shipment.id)
        if existing is None:
            existing = next((s for s in self.items.values() if s.tracking_number == shipment.tracking_number), None)
            if existing is not None and existing.provider != shipment.provider and "manual" in shipment.origins:
                self._rekey(existing, shipment.provider)  # manuelle Anbieterwahl gewinnt
        if existing is not None:
            existing.merge(shipment)
            return existing

        if shipment.reference:
            related = [s for s in self.items.values() if s.reference == shipment.reference]
            if is_placeholder(shipment):
                real = next((s for s in related if not is_placeholder(s)), None)
                if real is not None:
                    real.merge(shipment)
                    return real
            else:
                placeholder = next((s for s in related if is_placeholder(s)), None)
                if placeholder is not None:
                    del self.items[placeholder.id]
                    shipment.first_seen = placeholder.first_seen
                    shipment.merge(placeholder)

        shipment.first_seen = shipment.first_seen or now_iso()
        self.items[shipment.id] = shipment
        return shipment
