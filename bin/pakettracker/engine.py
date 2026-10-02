"""Ablaufsteuerung eines Abfragezyklus.

1. bisherigen Stand aus state.json laden
2. E-Mails abrufen und von allen aktiven Anbietern auswerten lassen
3. manuell erfasste Sendungen übernehmen, entfernte verwerfen
4. nicht abgeschlossene Sendungen live beim Anbieter abfragen (DHL, UPS)
5. Aufräumen (zugestellt / veraltet)
6. Ausgabe: state.json, MQTT
Fehler einzelner Anbieter oder des E-Mail-Abrufs werden protokolliert und im
Gesundheitszustand vermerkt – der Lauf geht immer weiter.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import registry
from .config import Config
from .health import EMAIL, Health
from .loxberry import Paths
from .models import Shipment, Status, now_iso, parse_ts
from .outputs import mqtt, snapshot, statefile
from .providers.base import Provider, ProviderError
from .sources import mail, manual
from .store import ShipmentStore
from .util import exclusive_lock, read_json, write_json

log = logging.getLogger("pakettracker")


@dataclass
class CollectResult:
    shipments: list[Shipment]
    provider_info: dict[str, dict] = field(default_factory=dict)
    email_info: dict = field(default_factory=dict)
    errors: int = 0


def _is_due(paths: Paths, interval_minutes: int) -> bool:
    try:
        last = parse_ts(paths.last_run_file.read_text().strip())
    except OSError:
        return True
    if last is None:
        return True
    # 30 s Toleranz, damit der 5-Minuten-Cron das Intervall nicht knapp verpasst
    return datetime.now(timezone.utc) - last >= timedelta(minutes=interval_minutes, seconds=-30)


def _enabled_providers(cfg: Config, states: dict) -> dict[str, Provider]:
    mock = cfg.get("general", "mock_mode")
    providers = {}
    for cls in registry.provider_classes():
        settings = cfg.section(f"providers.{cls.id}")
        if settings.get("enabled"):
            if not isinstance(states.get(cls.id), dict):
                states[cls.id] = {}
            providers[cls.id] = cls(settings, mock, log.getChild(cls.id), state=states[cls.id])
    return providers


def _sub_state(states: dict, key: str) -> dict:
    if not isinstance(states.get(key), dict):
        states[key] = {}
    return states[key]


def _mail_key(m: mail.Mail) -> str:
    if m.message_id:
        return m.message_id
    return hashlib.sha256(f"{m.sender}|{m.subject}|{m.date}|{m.text[:500]}".encode()).hexdigest()


def _read_mails(cfg: Config, states: dict, providers: dict[str, Provider], health: Health) -> list[mail.Mail]:
    def relevant(sender: str) -> bool:
        return any(p.handles_sender(sender) for p in providers.values())

    try:
        source = mail.make_source(cfg.section("email"), log, _sub_state(states, "_imap"), relevant)
    except Exception as exc:
        log.error("E-Mail-Eingang: %s", exc)
        health.failure(EMAIL, str(exc))
        return []
    if source is None:
        return []
    try:
        mails = source.fetch()
    except Exception as exc:  # IMAP-/Dateifehler stoppen den Lauf nie
        log.error("E-Mail-Abruf fehlgeschlagen: %s", exc)
        health.failure(EMAIL, str(exc))
        return []
    health.success(EMAIL)
    unique: dict[str, mail.Mail] = {}
    for m in mails:
        unique.setdefault(_mail_key(m), m)
    if len(unique) < len(mails):
        log.debug("E-Mail: %d doppelte Mails übersprungen", len(mails) - len(unique))
    return sorted(unique.values(), key=lambda m: parse_ts(m.date) or datetime.min.replace(tzinfo=timezone.utc))


def _collect(cfg: Config, paths: Paths, today: date | None = None) -> CollectResult:
    today = today or date.today()
    mock = cfg.get("general", "mock_mode")
    states = read_json(paths.provider_state_file, {})
    if not isinstance(states, dict):
        states = {}
    providers = _enabled_providers(cfg, states)
    health = Health(_sub_state(states, "_health"))
    store = ShipmentStore(statefile.load_shipments(paths.state_file), providers, log)

    previous = read_json(paths.state_file, {})
    if isinstance(previous, dict) and previous.get("mock_mode") and not mock:
        # Simulierte Status tragen den Zeitstempel ihres Laufs und würden echte Daten überdecken
        log.info("Testmodus wurde beendet – simulierte Statusdaten werden verworfen")
        for shipment in store.values():
            shipment.reset_status()

    # E-Mails
    for m in _read_mails(cfg, states, providers, health):
        for provider in providers.values():
            try:
                for shipment in provider.parse_email(m):
                    store.add(shipment, reported_by=provider.id)
            except Exception:
                log.exception("%s: Fehler beim Auswerten einer E-Mail (Inhalt wird nicht protokolliert)",
                              provider.name)
                health.failure(provider.id, "Fehler beim Auswerten einer E-Mail")

    # Manuell erfasste Sendungen – die Anbieterwahl der Oberfläche hat Vorrang
    manual_ids = set()
    for entry in manual.load(paths.tracked_file):
        shipment = manual.to_shipment(entry, log, enabled=providers.keys())
        if shipment is None or shipment.provider not in providers:
            continue
        merged = store.add(shipment)
        if merged is None:
            continue
        manual_ids.add(merged.id)
        if shipment.description:  # Beschreibung aus der Weboberfläche hat Vorrang
            merged.description = shipment.description
    for shipment in store.values():
        if "manual" in shipment.origins and shipment.id not in manual_ids:
            shipment.origins.remove("manual")
        if not shipment.origins:
            store.remove(shipment.id)

    # Live-Tracking – Fehler betreffen nur die jeweilige Sendung bzw. den Anbieter;
    # bisherige Daten bleiben dann unverändert erhalten.
    unavailable: set[str] = set()
    for shipment in store.values():
        provider = providers[shipment.provider]
        if shipment.is_final or not (provider.live_tracking or provider.mock) or provider.id in unavailable:
            continue
        if not provider.mock and not provider.due(shipment.tracking_number):
            continue
        try:
            shipment.merge(provider.track(shipment.tracking_number))
            if not provider.mock:
                health.success(provider.id)
        except NotImplementedError as exc:
            unavailable.add(provider.id)
            log.info("%s", exc)
        except ProviderError as exc:
            log.log(exc.level, "%s: %s", shipment.id, exc)
            if exc.level >= logging.WARNING:
                health.failure(provider.id, str(exc))
            if exc.abort:
                unavailable.add(provider.id)
                log.info("%s: weitere Abfragen in diesem Lauf ausgesetzt", provider.name)
        except Exception:
            log.exception("%s: unerwarteter Fehler bei der Abfrage", shipment.id)
            health.failure(provider.id, "Unerwarteter Fehler (Details im Log)")

    for provider in providers.values():
        if not provider.mock:
            provider.forget({s.tracking_number for s in store.values() if s.provider == provider.id})
    try:
        write_json(paths.provider_state_file, states)
    except OSError as exc:
        log.error("Anbieter-Zustand konnte nicht gespeichert werden: %s", exc)

    # Aufräumen
    keep_delivered = timedelta(days=cfg.get("general", "keep_delivered_days"))
    max_age = timedelta(days=cfg.get("general", "max_age_days"))
    now = datetime.now(timezone.utc)
    result = []
    for shipment in store.values():
        delivered = parse_ts(shipment.delivered_at)
        if shipment.status == Status.DELIVERED and delivered and delivered.astimezone().date() < today - keep_delivered:
            continue
        seen = parse_ts(shipment.last_update) or parse_ts(shipment.first_seen)
        if "manual" not in shipment.origins and seen and now - seen > max_age:
            continue
        result.append(shipment)

    email_enabled = bool(cfg.get("email", "enabled"))
    return CollectResult(
        shipments=result,
        provider_info={pid: health.provider_info(p, email_enabled) for pid, p in providers.items()},
        email_info=health.email_info(email_enabled),
        errors=health.errors_this_run,
    )


def collect(cfg: Config, paths: Paths, today: date | None = None) -> list[Shipment]:
    return _collect(cfg, paths, today).shipments


def run(paths: Paths, cfg: Config, force: bool = False) -> int:
    with exclusive_lock(paths.lock_file) as acquired:
        if not acquired:
            log.info("Ein anderer Lauf ist noch aktiv – übersprungen")
            return 0
        if not force and not _is_due(paths, cfg.get("general", "interval_minutes")):
            log.debug("Intervall noch nicht erreicht")
            return 0

        mock = cfg.get("general", "mock_mode")
        log.info("Abfrage gestartet%s", " (Testmodus)" if mock else "")
        previous = read_json(paths.state_file, {})
        result = _collect(cfg, paths)
        provider_ids = [cls.id for cls in registry.provider_classes()
                        if cfg.get(f"providers.{cls.id}", "enabled")]
        mqtt_settings = cfg.section("mqtt")
        snap = snapshot.build(result.shipments, provider_ids, mqtt_settings["slots"], mock,
                              provider_info=result.provider_info)
        snap["email"] = result.email_info
        snap["errors"] = result.errors
        last_full = previous.get("last_full_success", "") if isinstance(previous, dict) else ""
        snap["last_full_success"] = snap["updated"] if result.errors == 0 else last_full
        statefile.write(paths.state_file, snap)
        ok = True
        if mqtt_settings["enabled"]:
            ok = mqtt.publish(snap, mqtt_settings, log)
        paths.last_run_file.write_text(now_iso() + "\n")
        log.info("Abfrage beendet: %d Sendungen, davon %d aktiv%s", len(result.shipments),
                 snap["summary"]["active"], f", {result.errors} Fehler" if result.errors else "")
        return 0 if ok else 1
