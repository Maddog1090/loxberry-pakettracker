"""1.0.1: Tagesbezogene Texte, abgelaufene (stale) Sendungen, Vorrang des Live-Trackings, Europe/Berlin."""
import json
import logging
from datetime import date, datetime, timedelta, timezone

import pytest

import test_dhl_api as dhl
from pakettracker import config
from pakettracker.models import Shipment, Status, local_date, local_today, parse_date, render_relative
from pakettracker.outputs import mqtt, snapshot, statefile
from pakettracker.providers.mailparse import mail_reference_date
from pakettracker.sources.mail import Mail
from pakettracker.store import ShipmentStore

TODAY = date(2026, 10, 3)
NOW = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)  # 12:00 Uhr in Berlin


def amazon(eta, status=Status.OUT_FOR_DELIVERY, text="In Zustellung – kommt heute", ts=None, number="TBA000000000001"):
    """Rein mailbasierte Sendung; ts = Zeitpunkt der Mail (Standard: 07:00 Uhr am ETA-Tag)."""
    return Shipment("amazon", number, description="HP 305XL Druckerpatrone", status=status, status_text=text,
                    eta=eta, last_update=ts or f"{eta}T07:00:00+02:00", origins=["email"])


def build(shipments, today=TODAY, now=NOW, slots=3):
    return snapshot.build(shipments, ["amazon", "dhl"], slots=slots, mock_mode=False, today=today, now=now)


# --- 1. ETA gestern + mailbasierte Sendung → nicht mehr aktiv ------------------

def test_mail_shipment_with_past_eta_is_not_active():
    snap = build([amazon("2026-10-01")])
    summary = snap["summary"]
    assert summary["active"] == 0 and summary["out_for_delivery"] == 0 and summary["arriving_today"] == 0
    assert summary["next_eta"] == "" and summary["stale"] == 1
    assert snap["providers"]["amazon"]["active"] == 0 and snap["providers"]["amazon"]["shipment_count"] == 1
    assert [s["used"] for s in snap["slots"]] == [0, 0, 0]
    [shipment] = snap["shipments"]  # bleibt intern erhalten (bis max_age_days)
    assert shipment["stale"] is True
    assert shipment["eta_text"] == "Termin 01.10. überschritten"
    assert "heute" not in shipment["status_text"]


def test_newer_information_after_eta_keeps_shipment_active():
    late_mail = amazon("2026-10-01", Status.EXCEPTION, "Lieferung verzögert", ts="2026-10-02T09:00:00+02:00")
    snap = build([late_mail])
    assert snap["summary"]["active"] == 1 and snap["summary"]["stale"] == 0


def test_pickup_ready_does_not_expire():
    snap = build([amazon("2026-10-01", Status.PICKUP_READY, "Liegt im PaketShop")])
    assert snap["summary"]["pickup_ready"] == 1 and snap["summary"]["stale"] == 0


# --- 2./3. ETA heute / morgen ---------------------------------------------------

def test_eta_today():
    snap = build([amazon("2026-10-03")])
    [slot] = [s for s in snap["slots"] if s["used"]]
    assert slot["status_text"] == "In Zustellung – kommt heute"
    assert slot["eta_text"] == "kommt heute"
    assert snap["summary"]["arriving_today"] == 1 and snap["summary"]["next_eta"] == "2026-10-03"


def test_eta_tomorrow_and_later():
    shipments = [amazon("2026-10-04", Status.IN_TRANSIT, "Versandt", number="TBA000000000002"),
                 amazon("2026-10-09", Status.IN_TRANSIT, "Versandt", number="TBA000000000003")]
    snap = build(shipments)
    assert [s["eta_text"] for s in snap["slots"][:2]] == ["kommt morgen", "kommt am Fr 09.10."]
    assert snap["summary"]["arriving_today"] == 0 and snap["summary"]["next_eta"] == "2026-10-04"


def test_relative_word_follows_the_calendar():
    """Mail vom 02.10. „kommt morgen“ → am 03.10. „kommt heute“, am 04.10. ohne Tagesangabe."""
    s = amazon("2026-10-03", Status.IN_TRANSIT, "Ihr Paket kommt morgen", ts="2026-10-02T18:00:00+02:00")
    assert s.display_text(date(2026, 10, 2)) == "Ihr Paket kommt morgen"
    assert s.display_text(date(2026, 10, 3)) == "Ihr Paket kommt heute"
    assert s.display_text(date(2026, 10, 4)) == "Ihr Paket"


@pytest.mark.parametrize("text, expected", [
    ("In Zustellung – kommt heute", "In Zustellung"),
    ("Ihre Sendung wird heute zugestellt", "Ihre Sendung wird zugestellt"),
    ("Paket kommt übermorgen · DHL", "Paket · DHL"),
    ("Arriving today", ""),
    ("Guten Morgen, Ihr Paket ist unterwegs", "Guten Morgen, Ihr Paket ist unterwegs"),
    ("Zugestellt", "Zugestellt"),
])
def test_render_relative_removes_outdated_words(text, expected):
    assert render_relative(text, date(2026, 9, 28), TODAY) == expected


def test_text_consisting_only_of_outdated_words_falls_back_to_label():
    snap = build([amazon("2026-10-01", text="Kommt heute", ts="2026-10-02T09:00:00+02:00")])
    assert snap["shipments"][0]["status_text"] == "In Zustellung"


# --- 4. alter gespeicherter Text „kommt heute“ + ETA gestern ----------------------

def test_old_state_text_loses_today(tmp_path):
    state_file = tmp_path / "state.json"
    # Format von 1.0.0: status_text ist der Originaltext, kein status_text_raw/live_checked
    old = amazon("2026-10-02").to_dict()
    del old["live_checked"]
    state_file.write_text(json.dumps({"shipments": [old]}))
    [loaded] = statefile.load_shipments(state_file)

    snap = build([loaded])
    shipment = snap["shipments"][0]
    assert shipment["status_text"] == "In Zustellung" and shipment["stale"] is True
    assert shipment["status_text_raw"] == "In Zustellung – kommt heute"

    # Nächster Lauf liest das Original wieder ein – nichts geht verloren, nichts wird doppelt umgerechnet
    state_file.write_text(json.dumps(snap))
    [again] = statefile.load_shipments(state_file)
    assert again.status_text == "In Zustellung – kommt heute"
    assert again.display_text(date(2026, 10, 2)) == "In Zustellung – kommt heute"


# --- 5. ETA gestern + aktueller DHL-Live-Status → bleibt aktiv ----------------------

def test_live_tracked_shipment_with_past_eta_stays_active():
    s = Shipment("dhl", dhl.NUMBER, status=Status.IN_TRANSIT, status_text="Unterwegs", eta="2026-10-01",
                 last_update="2026-09-30T18:00:00+02:00", live_checked="2026-10-03T09:00:00+00:00",
                 origins=["manual"])
    snap = build([s])
    assert snap["summary"]["active"] == 1 and snap["summary"]["stale"] == 0
    assert snap["slots"][0]["eta_text"] == "verspätet – ursprünglicher Termin 01.10."
    assert snap["summary"]["next_eta"] == ""  # verstrichener Termin ist keine „nächste Zustellung“


def test_outdated_live_check_no_longer_protects():
    s = Shipment("dhl", dhl.NUMBER, status=Status.IN_TRANSIT, eta="2026-10-01",
                 last_update="2026-09-30T18:00:00+02:00", live_checked="2026-10-01T05:00:00+00:00")
    assert s.is_stale(TODAY, NOW)


def _seed_state(paths, *shipments):
    paths.state_file.write_text(json.dumps({"shipments": [s.to_dict() for s in shipments]}))


def test_engine_live_status_overrides_newer_mail_forecast(plugin_root):
    today = local_today()
    yesterday = (today - timedelta(days=2)).isoformat()
    cfg = dhl._engine_setup(plugin_root, [dhl.NUMBER])
    # Mailprognose (neuer als das letzte DHL-Ereignis) sagte „kommt heute“ – vor zwei Tagen
    _seed_state(plugin_root, Shipment("dhl", dhl.NUMBER, status=Status.OUT_FOR_DELIVERY,
                                      status_text="Ihr Paket kommt heute", eta=yesterday,
                                      last_update=f"{yesterday}T07:00:00+02:00", origins=["email", "manual"]))
    event = f"{(today - timedelta(days=3)).isoformat()}T18:00:00+02:00"
    body = dhl.api_shipment(code="transit", text="Die Sendung wurde im Paketzentrum bearbeitet.", ts=event)
    del body["shipments"][0]["estimatedTimeOfDelivery"]
    dhl.respond((200, body))
    state, _ = dhl._run(plugin_root, cfg)

    [shipment] = state["shipments"]
    assert shipment["status_code"] == 2 and shipment["status_text"] == "Die Sendung wurde im Paketzentrum bearbeitet."
    assert shipment["stale"] is False and shipment["live_checked"]
    assert shipment["eta_text"].startswith("verspätet – ursprünglicher Termin")
    assert state["summary"]["active"] == 1 and state["slots"][0]["tracking_number"] == dhl.NUMBER


def test_mail_does_not_override_fresh_live_status():
    live = Shipment("dhl", "N1", status=Status.IN_TRANSIT, status_text="Unterwegs (API)",
                    last_update="2026-10-02T08:00:00+00:00", live_checked=datetime.now(timezone.utc).isoformat(),
                    origins=["manual"])
    store = ShipmentStore([live], ["dhl"], logging.getLogger("test"))
    store.add(Shipment("dhl", "N1", description="Kabel", status=Status.OUT_FOR_DELIVERY, status_text="kommt heute",
                       eta="2026-10-02", last_update="2026-10-02T09:00:00+00:00", origins=["email"]))
    [s] = store.values()
    assert s.status == Status.IN_TRANSIT and s.status_text == "Unterwegs (API)" and s.eta == ""
    assert s.description == "Kabel" and set(s.origins) == {"manual", "email"}


# --- 6. DHL-Live-Tracking ohne IMAP --------------------------------------------------

def test_dhl_live_tracking_without_imap(plugin_root):
    cfg = dhl._engine_setup(plugin_root, [dhl.NUMBER])
    assert cfg.get("email", "enabled") is False and cfg.get("email", "host") == ""
    dhl.respond((200, dhl.api_shipment(code="transit", text="Die Sendung wurde in das Zustellfahrzeug geladen.",
                                       ts=datetime.now(timezone.utc).isoformat())))
    state, lines = dhl._run(plugin_root, cfg)

    [shipment] = state["shipments"]
    assert shipment["status_code"] == 3 and shipment["origins"] == ["manual"]
    assert shipment["live_checked"]
    info = state["providers"]["dhl"]
    assert info["source"] == "api" and info["live"] is True and info["health"] == "ok"
    assert info["live_last_success"] and info["error"] == "" and info["credentials"] == "ok"
    assert state["email"]["enabled"] is False
    assert len(dhl.FakeDhl.requests) == 1
    assert all(dhl.API_KEY not in line for line in lines)


def test_provider_source_reflects_configuration(plugin_root):
    cfg = dhl._engine_setup(plugin_root, [])
    settings = json.loads(plugin_root.settings_file.read_text())
    settings["email"].update({"enabled": True, "source": "eml_dir", "eml_dir": str(plugin_root.data)})
    plugin_root.settings_file.write_text(json.dumps(settings))
    dhl.respond()
    state, _ = dhl._run(plugin_root, config.load(plugin_root))
    assert state["providers"]["dhl"]["source"] == "api+email"
    assert state["providers"]["amazon"]["source"] == "email" and state["providers"]["amazon"]["live"] is False

    creds = json.loads(plugin_root.credentials_file.read_text())
    creds["providers"] = {}
    plugin_root.credentials_file.write_text(json.dumps(creds))
    settings["email"]["enabled"] = False
    plugin_root.settings_file.write_text(json.dumps(settings))
    state, _ = dhl._run(plugin_root, config.load(plugin_root))
    assert state["providers"]["dhl"]["source"] == "none" and state["providers"]["dhl"]["health"] == "no_source"


# --- 7. DHL zugestellt → keine weiteren Abfragen ------------------------------------

def test_delivered_dhl_shipment_is_not_polled_again(plugin_root):
    cfg = dhl._engine_setup(plugin_root, [dhl.NUMBER])
    dhl.respond((200, dhl.api_shipment(code="delivered", text="Die Sendung wurde zugestellt.",
                                       ts=datetime.now(timezone.utc).isoformat())))
    state, _ = dhl._run(plugin_root, cfg)
    assert state["shipments"][0]["status_code"] == 4

    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    provider_state["dhl"]["last_checked"] = {}  # Intervall wäre abgelaufen
    plugin_root.provider_state_file.write_text(json.dumps(provider_state))
    dhl.respond((200, dhl.api_shipment(code="transit")))
    state, _ = dhl._run(plugin_root, cfg)
    assert dhl.FakeDhl.requests == []
    assert state["shipments"][0]["status_code"] == 4


# --- 8. DHL-API-Fehler → letzter gültiger Status bleibt -----------------------------

@pytest.mark.parametrize("failure", [
    (503, b"Service Unavailable"),
    (200, b"<html>Wartung</html>"),
    (200, b"{}"),
    (429, dhl.problem(429, "Too Many Requests")),
    (403, dhl.problem(403, "Forbidden")),
])
def test_api_error_keeps_last_good_status(plugin_root, failure):
    cfg = dhl._engine_setup(plugin_root, [dhl.NUMBER])
    good = dhl.api_shipment(code="transit", text="Im Paketzentrum bearbeitet",
                            ts=datetime.now(timezone.utc).isoformat())
    dhl.respond((200, good))
    before, _ = dhl._run(plugin_root, cfg)

    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    provider_state["dhl"]["last_checked"] = {}
    plugin_root.provider_state_file.write_text(json.dumps(provider_state))
    dhl.respond(failure)
    after, _ = dhl._run(plugin_root, cfg)

    keep = ("status_code", "status_text", "eta", "last_update", "live_checked", "events")
    assert {k: after["shipments"][0][k] for k in keep} == {k: before["shipments"][0][k] for k in keep}
    assert after["providers"]["dhl"]["error"]
    assert after["summary"]["active"] == 1


def test_dhl_text_mapping():
    def status(code, text):
        data = dhl.api_shipment(code=code, text=text)["shipments"][0]
        return dhl.DhlProvider.map_api_shipment(data, dhl.NUMBER).status

    assert status("transit", "Die Sendung konnte nicht zugestellt werden. Der Empfänger wurde nicht angetroffen.") \
        == Status.EXCEPTION
    assert status("transit", "Die Sendung wurde in die PACKSTATION eingeliefert.") == Status.PICKUP_READY
    assert status("transit", "Die Sendung liegt in der Filiale zur Abholung bereit.") == Status.PICKUP_READY
    assert status("transit", "Die Rücksendung an den Absender wurde eingeleitet.") == Status.RETURNED
    assert status("failure", "Die Sendung wird an den Absender zurückgesendet. Rücksendung") == Status.RETURNED
    assert status("failure", "Adresse unbekannt") == Status.EXCEPTION
    assert status("transit", "Die Sendung wurde im Paketzentrum bearbeitet.") == Status.IN_TRANSIT


# --- 9. stale Paket verschwindet aus den MQTT-Slots ----------------------------------

def test_stale_shipment_leaves_mqtt_slot():
    a = amazon("2026-10-03")                                            # Slot 1 am 03.10.
    b = amazon("2026-10-06", Status.IN_TRANSIT, "Versandt", number="TBA000000000009")
    day1 = dict(mqtt.messages(build([a]), "pakettracker"))
    assert day1["pakettracker/slot/1/used"] == "1"
    assert day1["pakettracker/slot/1/description"] == "HP 305XL Druckerpatrone"

    day3 = dict(mqtt.messages(build([a], today=date(2026, 10, 5), now=NOW + timedelta(days=2)), "pakettracker"))
    for field in ("provider", "tracking_number", "description", "status", "status_label", "status_text",
                  "eta", "eta_window", "eta_text"):
        assert day3[f"pakettracker/slot/1/{field}"] == "", field  # retained leer → alter Text gelöscht
    assert day3["pakettracker/slot/1/used"] == "0" and day3["pakettracker/slot/1/status_code"] == "0"
    assert day3["pakettracker/summary/active"] == "0" and day3["pakettracker/summary/stale"] == "1"
    assert set(day1) <= set(day3)  # jedes zuvor gesendete Topic wird wieder überschrieben

    moved = dict(mqtt.messages(build([a, b], today=date(2026, 10, 5), now=NOW + timedelta(days=2)), "pakettracker"))
    assert moved["pakettracker/slot/1/tracking_number"] == "TBA000000000009"   # nächstes Paket rückt auf
    assert moved["pakettracker/slot/1/eta_text"] == "kommt morgen"
    assert moved["pakettracker/slot/2/used"] == "0" and moved["pakettracker/slot/2/description"] == ""


# --- 10. Europe/Berlin und Tageswechsel ----------------------------------------------

@pytest.mark.parametrize("utc, expected", [
    ("2026-10-02T21:59:00+00:00", date(2026, 10, 2)),   # 23:59 Sommerzeit (CEST)
    ("2026-10-02T22:01:00+00:00", date(2026, 10, 3)),   # 00:01 – in UTC noch der 02.10.
    ("2026-12-01T22:59:00+00:00", date(2026, 12, 1)),   # 23:59 Winterzeit (CET)
    ("2026-12-01T23:01:00+00:00", date(2026, 12, 2)),
    ("2026-10-24T22:30:00+00:00", date(2026, 10, 25)),  # Nacht der Zeitumstellung (Ende Sommerzeit)
    ("2026-10-25T22:59:00+00:00", date(2026, 10, 25)),  # danach gilt +01:00
    ("2026-03-28T23:30:00+00:00", date(2026, 3, 29)),   # Beginn Sommerzeit
])
def test_local_calendar_day(utc, expected):
    now = datetime.fromisoformat(utc)
    assert local_today(now) == expected
    assert local_date(utc) == expected


def test_day_change_at_midnight_berlin():
    s = amazon("2026-10-02")
    before = datetime(2026, 10, 2, 21, 59, tzinfo=timezone.utc)   # 23:59 Uhr
    after = datetime(2026, 10, 2, 22, 1, tzinfo=timezone.utc)     # 00:01 Uhr
    assert build([s], today=None, now=before)["slots"][0]["eta_text"] == "kommt heute"
    snap = build([s], today=None, now=after)
    assert snap["summary"]["active"] == 0 and snap["summary"]["stale"] == 1


def test_mail_reference_date_uses_berlin_day():
    late = Mail(sender="versand@amazon.de", subject="kommt heute", text="", date="2026-10-02T23:30:00+00:00")
    assert mail_reference_date(late) == date(2026, 10, 3)


@pytest.mark.parametrize("eta", ["", "2026-13-01", "morgen", "2026-10-1", None])
def test_missing_or_invalid_eta(eta):
    s = Shipment("amazon", "TBA000000000001", status=Status.IN_TRANSIT, eta=eta or "",
                 last_update="2026-09-01T10:00:00+02:00", origins=["email"])
    assert parse_date(eta) is None
    assert not s.is_stale(TODAY, NOW)
    assert s.eta_text(TODAY) == ""
    assert build([s])["summary"]["active"] == 1


def test_mock_mode_never_counts_as_live_tracking(plugin_root):
    cfg = dhl._engine_setup(plugin_root, [dhl.NUMBER])
    settings = json.loads(plugin_root.settings_file.read_text())
    settings["general"]["mock_mode"] = True
    plugin_root.settings_file.write_text(json.dumps(settings))
    mock_state, _ = dhl._run(plugin_root, config.load(plugin_root))
    assert mock_state["shipments"][0]["live_checked"] == ""

    s = Shipment("dhl", "N1", status=Status.IN_TRANSIT, live_checked=datetime.now(timezone.utc).isoformat())
    s.reset_status()  # Ende des Testmodus
    assert s.live_checked == "" and not s.live_fresh()
