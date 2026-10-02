"""Laden, Beschreiben und Initialisieren der Konfiguration.

settings.json     – alle nicht geheimen Einstellungen (von der Weboberfläche geschrieben)
credentials.json  – Passwörter, API-Keys, Token; Dateirechte 0600
Fehlende Werte werden immer aus den Defaults im Schema ergänzt.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any

from . import __version__, registry
from .loxberry import Paths
from .schema import CORE_SECTIONS, Section
from .util import read_json, write_json

CREDENTIALS_MODE = 0o600


def all_sections() -> list[Section]:
    return [*CORE_SECTIONS, *(cls.section() for cls in registry.provider_classes())]


def _subtree(data: Any, section_id: str) -> dict:
    for part in section_id.split("."):
        data = data.get(part) if isinstance(data, dict) else None
    return data if isinstance(data, dict) else {}


def _set_subtree(data: dict, section_id: str, values: dict) -> None:
    *parents, last = section_id.split(".")
    for part in parents:
        data = data.setdefault(part, {})
    data[last] = values


@dataclass
class Config:
    values: dict[str, dict[str, Any]]

    def section(self, section_id: str) -> dict[str, Any]:
        return dict(self.values.get(section_id, {}))

    def get(self, section_id: str, key: str) -> Any:
        return self.values[section_id][key]


def load(paths: Paths) -> Config:
    settings = read_json(paths.settings_file, {})
    creds = read_json(paths.credentials_file, {})
    values: dict[str, dict[str, Any]] = {}
    for sec in all_sections():
        stored, stored_secret = _subtree(settings, sec.id), _subtree(creds, sec.id)
        values[sec.id] = {
            f.key: f.coerce((stored_secret if f.secret else stored).get(f.key, f.default))
            for f in sec.fields
        }
    return Config(values)


def describe(paths: Paths) -> dict:
    """Schema + aktuelle Werte für die Weboberfläche. Geheimnisse nur als 'gesetzt ja/nein'."""
    cfg = load(paths)
    values: dict[str, dict] = {}
    secrets_set: dict[str, dict] = {}
    for sec in all_sections():
        for f in sec.fields:
            value = cfg.values[sec.id][f.key]
            if f.secret:
                secrets_set.setdefault(sec.id, {})[f.key] = bool(value)
                if not f.reveal:
                    continue
            values.setdefault(sec.id, {})[f.key] = value
    return {
        "version": __version__,
        "sections": [sec.to_dict() for sec in all_sections()],
        "values": values,
        "secrets_set": secrets_set,
    }


def defaults() -> dict:
    """Nicht geheime Default-Einstellungen (Inhalt einer frischen settings.json)."""
    out: dict = {}
    for sec in all_sections():
        _set_subtree(out, sec.id, {f.key: f.default for f in sec.fields if not f.secret})
    return out


def init(paths: Paths) -> None:
    """Legt fehlende Dateien an, erzeugt den REST-Token und setzt Dateirechte."""
    for directory in (paths.config, paths.data, paths.log):
        directory.mkdir(parents=True, exist_ok=True)

    if not paths.settings_file.exists():
        write_json(paths.settings_file, defaults())

    creds = read_json(paths.credentials_file, {})
    if not isinstance(creds, dict):
        creds = {}
    rest = creds.setdefault("rest", {})
    if not rest.get("token"):
        rest["token"] = secrets.token_urlsafe(24)
    write_json(paths.credentials_file, creds, CREDENTIALS_MODE)

    if not paths.tracked_file.exists():
        write_json(paths.tracked_file, [])

    os.chmod(paths.credentials_file, CREDENTIALS_MODE)
