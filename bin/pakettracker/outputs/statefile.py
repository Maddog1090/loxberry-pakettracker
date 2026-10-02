"""state.json: Gesamtstand für api.php und die Weboberfläche, zugleich Gedächtnis zwischen Läufen."""
from __future__ import annotations

import logging
from pathlib import Path

from ..models import Shipment
from ..util import read_json, write_json

log = logging.getLogger(__name__)


def write(path: Path, snapshot: dict) -> None:
    write_json(path, snapshot)


def load_shipments(path: Path) -> list[Shipment]:
    data = read_json(path, {})
    result = []
    for item in data.get("shipments", []) if isinstance(data, dict) else []:
        try:
            result.append(Shipment.from_dict(item))
        except (KeyError, TypeError):
            log.warning("Ungültiger Eintrag in %s ignoriert", path)
    return result
