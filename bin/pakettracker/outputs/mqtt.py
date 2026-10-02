"""MQTT-Ausgabe.

Topics (Basis-Topic konfigurierbar, Standard "pakettracker"):
  <base>/summary/<key>              Zähler, z.B. active, out_for_delivery, delivered_today, next_eta
  <base>/provider/<id>/active       aktive Sendungen je Anbieter
  <base>/provider/<id>/shipment_count  alle Sendungen je Anbieter (inkl. heute zugestellt)
  <base>/provider/<id>/error        letzter aktueller Fehler (leer = ok)
  <base>/provider/<id>/last_success Zeitpunkt des letzten erfolgreichen Abrufs (ISO)
  <base>/slot/<n>/<feld>            feste Slots (used, status_code, status_label, description, eta, …)
  <base>/updated, <base>/updated_epoch, <base>/mock_mode
  <base>/json                       Zusammenfassung + Slots als JSON (für andere Systeme)
Alle Nachrichten werden (konfigurierbar) retained gesendet, damit Loxone nach
einem Neustart sofort den aktuellen Stand hat. Leere Werte löschen dabei nach
MQTT-Standard den gespeicherten Wert (gewollt: keine veralteten Texte im Broker).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Iterator

from ..loxberry import system_broker


def messages(snapshot: dict, base: str) -> Iterator[tuple[str, str]]:
    base = base.strip("/")

    def fmt(value) -> str:
        if isinstance(value, bool):
            return "1" if value else "0"
        return str(value)

    for key, value in snapshot["summary"].items():
        yield f"{base}/summary/{key}", fmt(value)
    for pid, data in snapshot["providers"].items():
        yield f"{base}/provider/{pid}/active", fmt(data["active"])
        for key in ("shipment_count", "error", "last_success"):
            if key in data:
                yield f"{base}/provider/{pid}/{key}", fmt(data[key])
    for slot in snapshot["slots"]:
        for key, value in slot.items():
            if key != "slot":
                yield f"{base}/slot/{slot['slot']}/{key}", fmt(value)
    yield f"{base}/updated", snapshot["updated"]
    yield f"{base}/updated_epoch", fmt(snapshot["updated_epoch"])
    yield f"{base}/mock_mode", fmt(snapshot["mock_mode"])
    compact = {k: snapshot[k] for k in ("updated", "summary", "providers", "slots")}
    yield f"{base}/json", json.dumps(compact, ensure_ascii=False)


CONNECT_TIMEOUT = 10  # Sekunden
PUBLISH_TIMEOUT = 15  # Sekunden für alle Nachrichten zusammen


def _connection(settings: dict, log: logging.Logger) -> dict | None:
    if settings.get("use_system_broker"):
        broker = system_broker()
        if broker is None:
            log.warning("MQTT: In LoxBerry ist kein Broker konfiguriert – MQTT-Ausgabe übersprungen. "
                        "Broker in LoxBerry einrichten oder eigenen Broker im Plugin eintragen.")
        return broker
    if not settings.get("host"):
        log.warning("MQTT: Kein Broker-Host eingetragen – MQTT-Ausgabe übersprungen")
        return None
    return {k: settings.get(k) for k in ("host", "port", "user", "password")}


def publish(snapshot: dict, settings: dict, log: logging.Logger) -> bool:
    """Sendet den Stand an den Broker. Fehler werden nur protokolliert, nie weitergereicht."""
    try:
        import paho.mqtt.client as mqtt
    except ImportError:
        log.error("MQTT: python3-paho-mqtt ist nicht installiert – MQTT-Ausgabe übersprungen")
        return False

    conn = _connection(settings, log)
    if conn is None:
        return False
    target = f"{conn['host']}:{conn['port']}"

    connected = threading.Event()
    result: dict = {}

    def on_connect(client, userdata, flags, reason_code, properties=None):
        result["rc"] = reason_code
        connected.set()

    try:
        if hasattr(mqtt, "CallbackAPIVersion"):  # paho-mqtt >= 2.0
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pakettracker")
        else:
            client = mqtt.Client(client_id="pakettracker")
        client.on_connect = on_connect
        if conn.get("user"):
            client.username_pw_set(conn["user"], conn.get("password") or None)
        client.connect_async(conn["host"], int(conn["port"]), keepalive=30)
        client.loop_start()
    except Exception as exc:
        log.error("MQTT: Verbindung zu %s nicht möglich: %s", target, exc)
        return False

    try:
        if not connected.wait(CONNECT_TIMEOUT):
            log.error("MQTT: Broker %s antwortet nicht (Timeout %d s)", target, CONNECT_TIMEOUT)
            return False
        rc = result.get("rc")
        failed = rc.is_failure if hasattr(rc, "is_failure") else rc != 0
        if failed:
            log.error("MQTT: Broker %s lehnt die Verbindung ab: %s", target, rc)
            return False

        infos = [client.publish(topic, payload, qos=1, retain=bool(settings.get("retain")))
                 for topic, payload in messages(snapshot, settings["base_topic"])]
        deadline = time.monotonic() + PUBLISH_TIMEOUT
        for info in infos:
            info.wait_for_publish(timeout=max(0.1, deadline - time.monotonic()))
        sent = sum(1 for info in infos if info.is_published())
        if sent < len(infos):
            log.error("MQTT: nur %d von %d Nachrichten an %s bestätigt", sent, len(infos), target)
            return False
        log.info("MQTT: %d Nachrichten an %s gesendet", sent, target)
        return True
    except Exception as exc:
        log.error("MQTT: Fehler beim Senden an %s: %s", target, exc)
        return False
    finally:
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass
