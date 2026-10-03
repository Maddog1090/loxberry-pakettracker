"""Ende-zu-Ende: alle Anbieter über E-Mail, Duplikate, Gesundheit, MQTT-Topics, MQTT-Ausfall."""
import json
import shutil
from datetime import date
import sys
import types

from pakettracker import config, engine
from pakettracker.outputs import mqtt

from conftest import FIXTURES


def _cfg(paths, eml_dir, **general):
    settings = config.defaults()
    settings["general"].update({"mock_mode": False, "max_age_days": 365, **general})
    settings["mqtt"]["enabled"] = False
    settings["email"].update({"enabled": True, "source": "eml_dir", "eml_dir": str(eml_dir), "lookback_days": 90})
    paths.settings_file.write_text(json.dumps(settings))
    return config.load(paths)


def _state(paths):
    return json.loads(paths.state_file.read_text())


def test_all_carriers_from_mails(plugin_root):
    cfg = _cfg(plugin_root, FIXTURES)
    # Stichtag der Testmails: Hermes meldet am 02.10. „heute in Zustellung“
    assert engine.run(plugin_root, cfg, force=True, today=date(2026, 10, 2)) == 0
    state = _state(plugin_root)
    ids = sorted(s["id"] for s in state["shipments"])
    assert ids == sorted([
        "amazon:TBA000000000001", "amazon:TBA000000000003",
        "dhl:00340434000000000001", "dhl:00340434000000000003", "dhl:00340434000000000005",
        "dpd:01234567890123", "gls:12345678901", "hermes:H1000000000000000001", "ups:1Z999AA10123456784",
    ])  # keine Duplikate (doppelte DHL-Mail), kein Amazon-Platzhalter, Werbemail ignoriert
    by_id = {s["id"]: s for s in state["shipments"]}
    assert by_id["dhl:00340434000000000003"]["reference"] == "302-0000000-0000002"
    assert by_id["amazon:TBA000000000003"]["description"] == "Buch XY"

    providers = state["providers"]
    assert providers["hermes"]["health"] == "ok" and providers["hermes"]["source"] == "email"
    assert providers["ups"]["credentials"] == "missing" and providers["ups"]["health"] == "email_only"
    assert providers["dhl"]["shipment_count"] == 3
    assert "fedex" not in providers  # standardmäßig deaktiviert

    topics = dict(mqtt.messages(state, "pakettracker"))
    assert topics["pakettracker/provider/hermes/active"] == "1"
    assert topics["pakettracker/provider/hermes/shipment_count"] == "1"
    assert topics["pakettracker/provider/hermes/error"] == ""
    assert topics["pakettracker/provider/hermes/last_success"].startswith("20")
    assert topics["pakettracker/slot/1/status_code"] == "3"  # Hermes „heute in Zustellung“ zuerst


def test_placeholder_replaced_across_runs(plugin_root, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(FIXTURES / "amazon_order_only.eml", inbox)
    cfg = _cfg(plugin_root, inbox)
    engine.run(plugin_root, cfg, force=True)
    assert [s["tracking_number"] for s in _state(plugin_root)["shipments"]] == ["ORDER-302-0000000-0000003"]

    shutil.copy(FIXTURES / "amazon_order_shipped_tba.eml", inbox)
    engine.run(plugin_root, cfg, force=True)
    [shipment] = _state(plugin_root)["shipments"]
    assert shipment["tracking_number"] == "TBA000000000003" and shipment["eta"] == "2026-10-09"


def test_manual_choice_wins_over_mail_provider(plugin_root, tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    shutil.copy(FIXTURES / "gls_pickup.eml", inbox)
    cfg = _cfg(plugin_root, inbox)
    plugin_root.tracked_file.write_text(json.dumps([{"provider": "dpd", "tracking_number": "12345678901"}]))
    engine.run(plugin_root, cfg, force=True)
    [shipment] = _state(plugin_root)["shipments"]
    assert shipment["id"] == "dpd:12345678901" and shipment["status"] == "pickup_ready"


def test_unknown_and_disabled_manual_entries_do_not_break(plugin_root, tmp_path):
    cfg = _cfg(plugin_root, tmp_path)
    plugin_root.tracked_file.write_text(json.dumps([
        {"provider": "auto", "tracking_number": "UNBEKANNT"},
        {"provider": "fedex", "tracking_number": "123456789012"},   # Anbieter deaktiviert
        {"provider": "gibtsnicht", "tracking_number": "123456789012"},
        {"provider": "hermes", "tracking_number": "H1000000000000000009", "description": "Schuhe"},
        "kaputter Eintrag",
    ]))
    assert engine.run(plugin_root, cfg, force=True) == 0
    assert [s["id"] for s in _state(plugin_root)["shipments"]] == ["hermes:H1000000000000000009"]


def test_missing_eml_dir_is_logged_not_fatal(plugin_root, tmp_path):
    cfg = _cfg(plugin_root, tmp_path / "gibtsnicht")
    assert engine.run(plugin_root, cfg, force=True) == 0
    state = _state(plugin_root)
    assert "nicht gefunden" in state["email"]["error"] and state["errors"] == 1


def test_mock_mode_unchanged_with_new_providers(plugin_root):
    settings = config.defaults()
    settings["mqtt"]["enabled"] = False
    plugin_root.settings_file.write_text(json.dumps(settings))
    plugin_root.tracked_file.write_text(json.dumps([
        {"provider": p, "tracking_number": n} for p, n in
        [("dhl", "00340434000000000001"), ("ups", "1Z999AA10123456784"), ("hermes", "H1000000000000000001")]]))
    engine.run(plugin_root, config.load(plugin_root), force=True)
    state = _state(plugin_root)
    assert state["mock_mode"] is True
    assert all(s["status_text"].startswith("[Testmodus]") for s in state["shipments"])


# --- MQTT-Ausfall --------------------------------------------------------------

class _Info:
    def wait_for_publish(self, timeout=None):
        pass

    def is_published(self):
        return True


def _fake_paho(mode):
    class Client:
        published = []
        details = []

        def __init__(self, *args, **kwargs):
            self.on_connect = None

        def username_pw_set(self, *args):
            pass

        def connect_async(self, host, port, keepalive=60):
            if mode == "dns":
                raise OSError("Name or service not known")

        def loop_start(self):
            if mode == "refused":
                self.on_connect(self, None, {}, 5)
            elif mode == "ok":
                self.on_connect(self, None, {}, 0)

        def publish(self, topic, payload, qos=0, retain=False):
            Client.published.append(topic)
            Client.details.append((topic, payload, retain))
            return _Info()

        def disconnect(self):
            pass

        def loop_stop(self):
            pass

    module = types.ModuleType("paho.mqtt.client")
    module.Client = Client
    return module


def _with_paho(mode, fn):
    saved = {k: sys.modules.get(k) for k in ("paho", "paho.mqtt", "paho.mqtt.client")}
    module = _fake_paho(mode)
    sys.modules.update({"paho": types.ModuleType("paho"), "paho.mqtt": types.ModuleType("paho.mqtt"),
                        "paho.mqtt.client": module})
    sys.modules["paho.mqtt"].client = module
    old_timeout = mqtt.CONNECT_TIMEOUT
    mqtt.CONNECT_TIMEOUT = 0.2
    try:
        return fn(), module.Client.published
    finally:
        mqtt.CONNECT_TIMEOUT = old_timeout
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value


def _mqtt_cfg(paths):
    settings = config.defaults()
    settings["mqtt"].update({"enabled": True, "use_system_broker": False, "host": "broker.invalid"})
    paths.settings_file.write_text(json.dumps(settings))
    paths.tracked_file.write_text(json.dumps([{"provider": "dhl", "tracking_number": "00340434000000000001"}]))
    return config.load(paths)


def test_mqtt_broker_unreachable_does_not_break_run(plugin_root):
    cfg = _mqtt_cfg(plugin_root)
    for mode in ("timeout", "refused", "dns"):
        plugin_root.state_file.unlink(missing_ok=True)
        rc, published = _with_paho(mode, lambda: engine.run(plugin_root, cfg, force=True))
        assert rc == 1 and published == []
        assert _state(plugin_root)["shipments"]  # state.json/REST trotzdem aktuell


def test_mqtt_publishes_new_provider_topics(plugin_root):
    cfg = _mqtt_cfg(plugin_root)
    rc, published = _with_paho("ok", lambda: engine.run(plugin_root, cfg, force=True))
    assert rc == 0
    for topic in ("pakettracker/provider/dhl/active", "pakettracker/provider/dhl/error",
                  "pakettracker/provider/dhl/last_success", "pakettracker/provider/dhl/shipment_count",
                  "pakettracker/slot/1/status_code", "pakettracker/summary/active"):
        assert topic in published


def test_mqtt_empty_values_are_sent_retained(plugin_root):
    """Dokumentiertes Verhalten: auch leere Werte werden (retained) gesendet und leeren so den Broker-Wert."""
    cfg = _mqtt_cfg(plugin_root)
    holder = {}

    def run():
        rc = engine.run(plugin_root, cfg, force=True)
        holder["details"] = list(sys.modules["paho.mqtt.client"].Client.details)
        return rc

    _with_paho("ok", run)
    sent = {topic: (payload, retain) for topic, payload, retain in holder["details"]}
    assert sent["pakettracker/provider/dhl/error"] == ("", True)
    assert sent["pakettracker/slot/2/description"] == ("", True)
    assert sent["pakettracker/slot/1/status_code"][1] is True
