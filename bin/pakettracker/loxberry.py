"""Anbindung an die LoxBerry-Umgebung: Plugin-Pfade und System-MQTT-Broker.

Die Pfade werden aus dem Installationsort abgeleitet
(<LBHOMEDIR>/bin/plugins/<folder>/pakettracker/loxberry.py). So stimmen sie auch,
wenn LoxBerry den Plugin-Ordner bei einer Namenskollision umbenennt, und es
gibt keine fest codierten Systempfade.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

_PLUGIN_BIN = Path(__file__).resolve().parent.parent  # .../bin/plugins/<folder>


def _installation() -> tuple[Path, str] | None:
    """(LBHOMEDIR, Plugin-Ordner), wenn das Backend in einer LoxBerry-Installation liegt."""
    if _PLUGIN_BIN.parent.name == "plugins" and _PLUGIN_BIN.parent.parent.name == "bin":
        return _PLUGIN_BIN.parents[2], _PLUGIN_BIN.name
    return None


def _home() -> Path:
    if os.environ.get("LBHOMEDIR"):
        return Path(os.environ["LBHOMEDIR"])
    inst = _installation()
    if inst:
        return inst[0]
    raise RuntimeError("LoxBerry-Installation nicht gefunden – für Tests PAKETTRACKER_ROOT setzen")


@dataclass(frozen=True)
class Paths:
    config: Path
    data: Path
    log: Path

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def credentials_file(self) -> Path:
        return self.config / "credentials.json"

    @property
    def tracked_file(self) -> Path:
        """Manuell in der Weboberfläche erfasste Sendungsnummern."""
        return self.data / "tracked.json"

    @property
    def state_file(self) -> Path:
        """Aktueller Gesamtstand – wird von api.php und der Weboberfläche gelesen."""
        return self.data / "state.json"

    @property
    def provider_state_file(self) -> Path:
        """Zustand der Anbieter zwischen Läufen (z.B. DHL-Tageskontingent, zuletzt abgefragt)."""
        return self.data / "provider_state.json"

    @property
    def last_run_file(self) -> Path:
        return self.data / "last_run"

    @property
    def lock_file(self) -> Path:
        return self.data / "run.lock"

    @property
    def log_file(self) -> Path:
        return self.log / "pakettracker.log"


def get_paths() -> Paths:
    # Für Entwicklung/Tests: alles unterhalb von PAKETTRACKER_ROOT ablegen
    dev_root = os.environ.get("PAKETTRACKER_ROOT")
    if dev_root:
        root = Path(dev_root)
        return Paths(config=root / "config", data=root / "data", log=root / "log")
    inst = _installation()
    if inst is None:
        raise RuntimeError("LoxBerry-Installation nicht gefunden – für Tests PAKETTRACKER_ROOT setzen")
    home, folder = inst
    return Paths(
        config=home / "config" / "plugins" / folder,
        data=home / "data" / "plugins" / folder,
        log=home / "log" / "plugins" / folder,
    )


def system_broker() -> dict | None:
    """MQTT-Broker aus LoxBerrys general.json (Abschnitt "Mqtt", LoxBerry >= 3.0).

    Liefert None, wenn kein Broker konfiguriert ist – das ist kein Fehler.
    """
    try:
        sysconfig = Path(os.environ["LBSCONFIG"]) if os.environ.get("LBSCONFIG") else _home() / "config" / "system"
        mqtt = json.loads((sysconfig / "general.json").read_text(encoding="utf-8"))["Mqtt"]
        if not mqtt.get("Brokerhost"):
            return None
        return {
            "host": mqtt["Brokerhost"],
            "port": int(mqtt.get("Brokerport") or 1883),
            "user": mqtt.get("Brokeruser") or "",
            "password": mqtt.get("Brokerpass") or "",
        }
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return None
