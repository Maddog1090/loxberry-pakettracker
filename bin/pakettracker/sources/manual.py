"""Manuell in der Weboberfläche erfasste Sendungsnummern (data/tracked.json).

Format: [{"provider": "dhl" | "auto", "tracking_number": "...", "description": "..."}]
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable

from .. import registry
from ..models import Shipment
from ..util import read_json


def load(path: Path) -> list[dict]:
    data = read_json(path, [])
    return [e for e in data if isinstance(e, dict) and e.get("tracking_number")] if isinstance(data, list) else []


def to_shipment(entry: dict, log: logging.Logger, enabled: Iterable[str] | None = None) -> Shipment | None:
    """Ein explizit gewählter Anbieter hat immer Vorrang; "auto" wird erkannt (nur aktive Anbieter)."""
    number = re.sub(r"[\s-]+", "", str(entry["tracking_number"])).upper()
    provider_id = entry.get("provider") or "auto"
    if provider_id == "auto":
        found = registry.candidates(number, enabled)
        if not found:
            log.warning("Anbieter für Sendungsnummer %s nicht erkennbar – bitte in der Oberfläche manuell wählen",
                        number)
            return None
        if registry.is_ambiguous(found):
            log.info("Sendungsnummer %s ist mehrdeutig (%s) – verwende %s; bei Bedarf Anbieter manuell wählen",
                     number, ", ".join(c.provider.name for c in found), found[0].provider.name)
        provider_id = found[0].provider.id
    return Shipment(
        provider=provider_id,
        tracking_number=number,
        description=str(entry.get("description") or ""),
        origins=["manual"],
    )
