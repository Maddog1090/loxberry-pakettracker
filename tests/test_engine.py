import json
from datetime import date

from pakettracker import config, engine
from pakettracker.models import Shipment, Status
from pakettracker.outputs import mqtt, snapshot

from conftest import FIXTURES


def _settings(paths, **overrides):
    settings = config.defaults()
    settings["mqtt"]["enabled"] = False
    for section, values in overrides.items():
        settings[section].update(values)
    paths.settings_file.write_text(json.dumps(settings))
    return config.load(paths)


def test_run_mock_mode_writes_state(plugin_root):
    cfg = _settings(plugin_root)
    plugin_root.tracked_file.write_text(json.dumps([
        {"provider": "auto", "tracking_number": "00340434000000000001", "description": "Bücher"},
        {"provider": "auto", "tracking_number": "UNBEKANNT"},
    ]))
    assert engine.run(plugin_root, cfg, force=True) == 0
    state = json.loads(plugin_root.state_file.read_text())
    [shipment] = state["shipments"]
    assert shipment["description"] == "Bücher"
    assert shipment["status_text"].startswith("[Testmodus]")
    assert len(state["slots"]) == 5


def test_interval_is_respected(plugin_root):
    cfg = _settings(plugin_root)
    engine.run(plugin_root, cfg, force=True)
    plugin_root.state_file.unlink()
    engine.run(plugin_root, cfg)
    assert not plugin_root.state_file.exists()


def test_removed_manual_entry_disappears(plugin_root):
    cfg = _settings(plugin_root)
    plugin_root.tracked_file.write_text(json.dumps([{"provider": "dhl", "tracking_number": "123456789012"}]))
    engine.run(plugin_root, cfg, force=True)
    plugin_root.tracked_file.write_text("[]")
    engine.run(plugin_root, cfg, force=True)
    assert json.loads(plugin_root.state_file.read_text())["shipments"] == []


def test_emails_from_directory(plugin_root):
    cfg = _settings(plugin_root,
                    general={"mock_mode": False, "max_age_days": 365},
                    email={"enabled": True, "source": "eml_dir", "eml_dir": str(FIXTURES), "lookback_days": 90})
    shipments = {s.id: s for s in engine.collect(cfg, plugin_root, today=date(2026, 10, 3))}
    assert shipments["dhl:00340434000000000001"].status == Status.ANNOUNCED
    assert shipments["amazon:TBA000000000001"].status == Status.DELIVERED
    assert "dhl:00340434000000000099" not in shipments  # fremder Absender


def test_snapshot_slots_prioritised():
    today = date(2026, 10, 2)
    shipments = [
        Shipment("dhl", "1", status=Status.ANNOUNCED, eta="2026-10-05"),
        Shipment("dhl", "2", status=Status.OUT_FOR_DELIVERY, eta="2026-10-02"),
        Shipment("amazon", "3", status=Status.DELIVERED, delivered_at="2026-10-02T10:00:00+02:00"),
        Shipment("amazon", "4", status=Status.DELIVERED, delivered_at="2026-09-20T10:00:00+02:00"),
    ]
    snap = snapshot.build(shipments, ["dhl", "amazon"], slots=4, mock_mode=False, today=today)
    assert [s["tracking_number"] for s in snap["slots"]] == ["2", "1", "3", ""]
    assert snap["summary"]["active"] == 2
    assert snap["summary"]["delivered_today"] == 1
    assert snap["summary"]["arriving_today"] == 1
    assert snap["summary"]["next_eta"] == "2026-10-02"

    topics = dict(mqtt.messages(snap, "pakettracker/"))
    assert topics["pakettracker/slot/1/status_code"] == "3"
    assert topics["pakettracker/slot/4/used"] == "0"
    assert topics["pakettracker/provider/dhl/active"] == "2"
    assert topics["pakettracker/mock_mode"] == "0"
