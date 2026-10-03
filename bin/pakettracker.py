#!/usr/bin/env python3
"""Kommandozeile des Pakettrackers.

  pakettracker.py run [--force] [-v]   Abfragezyklus (Cron; --force ignoriert das Intervall)
  pakettracker.py describe             Schema + Werte als JSON für die Weboberfläche
  pakettracker.py init                 Dateien anlegen, REST-Token erzeugen (postinstall)
  pakettracker.py defaults             Default-settings.json ausgeben
  pakettracker.py detect <nummer>      Anbieter erkennen (JSON, für die Weboberfläche)
  pakettracker.py test imap|<anbieter> Verbindung/Zugangsdaten prüfen (JSON, für die Weboberfläche)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pakettracker import config, engine, registry  # noqa: E402
from pakettracker.loxberry import Paths, get_paths  # noqa: E402
from pakettracker.outputs import statefile  # noqa: E402
from pakettracker.providers.base import Provider  # noqa: E402
from pakettracker.util import read_json, write_json  # noqa: E402


def setup_logging(paths: Paths, level: str, verbose: bool) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    try:
        paths.log.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = RotatingFileHandler(paths.log_file, maxBytes=512_000, backupCount=2,
                                                       encoding="utf-8")
    except OSError:
        handler = logging.StreamHandler(sys.stderr)
        verbose = False
    handler.setFormatter(fmt)
    root.addHandler(handler)
    if verbose:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        root.addHandler(console)


def _enabled_ids(cfg: config.Config) -> list[str]:
    return [cls.id for cls in registry.provider_classes() if cfg.get(f"providers.{cls.id}", "enabled")]


def cmd_detect(cfg: config.Config, number: str) -> dict:
    found = registry.candidates(number, _enabled_ids(cfg))
    return {
        "number": Provider.normalize(number),
        "best": found[0].provider.id if found else None,
        "ambiguous": registry.is_ambiguous(found),
        "candidates": [{"id": c.provider.id, "name": c.provider.name, "confidence": c.confidence} for c in found],
    }


def cmd_test(cfg: config.Config, paths: Paths, target: str) -> dict:
    """Verbindungstest; das Ergebnis enthält nie Zugangsdaten."""
    log = logging.getLogger("pakettracker.test")
    if target == "imap":
        from pakettracker.sources.imap import ImapSource

        providers = engine._enabled_providers(cfg, {})
        source = ImapSource(cfg.section("email"), log, {},
                            lambda sender: any(p.handles_sender(sender) for p in providers.values()))
        try:
            return {"ok": True, "message": source.test()}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    cls = registry.get(target)
    if cls is None:
        return {"ok": False, "message": f"Unbekannter Anbieter: {target}"}
    states = read_json(paths.provider_state_file, {})
    if not isinstance(states, dict):
        states = {}
    state = states.setdefault(cls.id, {}) if isinstance(states.get(cls.id, {}), dict) else {}
    provider = cls(cfg.section(f"providers.{cls.id}"), False, log.getChild(cls.id), state=state)
    try:
        if cls.id == "dhl":
            # Mit einer eigenen aktiven DHL-Sendung prüft der Test auch echte Sendungsdaten
            active = [s.tracking_number for s in statefile.load_shipments(paths.state_file)
                      if s.provider == "dhl" and not s.is_final and not s.tracking_number.startswith("ORDER-")]
            result = {"ok": True, "message": provider.test_connection(active[0] if active else "")}
        else:
            result = {"ok": True, "message": provider.test_connection()}
    except Exception as exc:
        result = {"ok": False, "message": str(exc)}
    try:
        write_json(paths.provider_state_file, states)  # z.B. verbrauchte DHL-Abfrage zählen
    except OSError:
        pass
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pakettracker")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="Abfragezyklus ausführen")
    run.add_argument("--force", action="store_true", help="Intervall ignorieren")
    run.add_argument("-v", "--verbose", action="store_true", help="Log zusätzlich auf stderr")
    sub.add_parser("describe", help="Schema und Werte als JSON ausgeben")
    sub.add_parser("init", help="Konfiguration initialisieren")
    sub.add_parser("defaults", help="Default-Einstellungen ausgeben")
    detect = sub.add_parser("detect", help="Anbieter einer Sendungsnummer erkennen")
    detect.add_argument("number")
    test = sub.add_parser("test", help="Verbindung prüfen (imap oder Anbieter-ID)")
    test.add_argument("target")
    args = parser.parse_args(argv)

    paths = get_paths()
    if args.cmd == "describe":
        print(json.dumps(config.describe(paths), ensure_ascii=False))
        return 0
    if args.cmd == "defaults":
        print(json.dumps(config.defaults(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "init":
        config.init(paths)
        return 0

    cfg = config.load(paths)
    if args.cmd == "detect":
        print(json.dumps(cmd_detect(cfg, args.number), ensure_ascii=False))
        return 0
    if args.cmd == "test":
        setup_logging(paths, cfg.get("general", "loglevel"), False)
        print(json.dumps(cmd_test(cfg, paths, args.target), ensure_ascii=False))
        return 0
    setup_logging(paths, cfg.get("general", "loglevel"), args.verbose)
    try:
        return engine.run(paths, cfg, force=args.force)
    except Exception:
        logging.getLogger("pakettracker").exception("Abbruch durch unerwarteten Fehler")
        return 2


if __name__ == "__main__":
    sys.exit(main())
