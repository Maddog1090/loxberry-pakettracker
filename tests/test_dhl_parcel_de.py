"""1.0.2: DHL Parcel DE Tracking (public-Abfrage, XML) neben Shipment Tracking – Unified – nur gegen lokale Testserver."""
import base64
import json
import logging
import socket
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

import fakehttp
import test_dhl_api as unified
from pakettracker import config
from pakettracker.models import Status
from pakettracker.providers.base import ProviderError
from pakettracker.providers.dhl import DhlProvider

KEY = "test-key-NICHT-ECHT-0123456789"
SECRET = "test-secret-NICHT-ECHT-9876"
NUMBER = "00340434000000000001"


def piece(number=NUMBER, status="Die Sendung wurde im Ziel-Paketzentrum bearbeitet.", ts="03.10.2026 05:43",
          ice="ULFMV", standard="EE", delivered="0", extra="", events=""):
    return (f'<?xml version="1.0" encoding="UTF-8" ?><data request-id="t-1">'
            f'<data name="piece-status-public-list" code="0" _piece-code="{number}">'
            f'<data name="piece-status-public" piece-code="{number}" searched-piece-code="{number}" error-status="0" '
            f'status="{status}" last-event-timestamp="{ts}" delivery-event-flag="{delivered}" ice="{ice}" ric="" '
            f'standard-event-code="{standard}" product-name="DHL PAKET" event-location="" {extra}>{events}</data>'
            f'</data></data>').encode()


def event(ts, text, ice="LDTMV", standard="AA", location=""):
    return (f'<data name="pieceevent" event-timestamp="{ts}" event-status="{text}" event-text="{text}" ice="{ice}" '
            f'ric="" event-location="{location}" event-country="DE" standard-event-code="{standard}"/>')


def code(value, error=""):
    return f'<?xml version="1.0" encoding="UTF-8" ?><data name="piece-status-public-list" code="{value}" ' \
           f'error="{error}"/>'.encode()


def server():
    srv = fakehttp.server()
    return srv


def make(**settings) -> DhlProvider:
    base = {"api_key": KEY, "api_secret": SECRET, "api": "auto", "tracking_user": "", "tracking_password": "",
            "language": "de", "recipient_postal_code": "", "check_interval_minutes": 60, "daily_limit": 250}
    base.update(settings)
    provider = DhlProvider(base, mock=False, log=logging.getLogger("test.dhl.parcel"), state={})
    provider.PARCEL_URL = server().url + "/parcel/de/tracking/v0/shipments"
    provider.API_URL = server().url + "/track/shipments"
    provider._sleep = lambda s: None
    return provider


def sent_xml(request) -> ET.Element:
    return ET.fromstring(request["query"]["xml"][0])


def failure(provider, number=NUMBER) -> ProviderError:
    with pytest.raises(ProviderError) as info:
        provider.track(number)
    return info.value


# --- 1. Authentifizierung und Request-Format ------------------------------------

def test_parcel_de_request_auth_and_xml():
    provider = make()
    server().respond((200, piece()))
    shipment = provider.track(NUMBER)

    [req] = server().requests
    assert req["path"] == "/parcel/de/tracking/v0/shipments"
    assert req["headers"]["Authorization"] == "Basic " + base64.b64encode(f"{KEY}:{SECRET}".encode()).decode()
    assert req["headers"]["dhl-api-key"] == KEY
    outer = sent_xml(req)
    assert outer.get("request") == "get-status-for-public-user" and outer.get("language-code") == "de"
    assert outer.get("appname") is None and outer.get("password") is None  # nur wenn von DHL vergeben
    assert outer.find("data").get("piece-code") == NUMBER and outer.find("data").get("zip-code") is None
    assert shipment.status == Status.IN_TRANSIT and shipment.last_update == "2026-10-03T05:43:00+02:00"
    assert provider.live_details()["live_api"] == "parcel_de" and provider.live_details()["live_api_confirmed"]
    assert provider.state["usage"]["count"] == 1


def test_tracking_user_and_zip_are_sent_and_escaped():
    provider = make(tracking_user="kunde<&>", tracking_password='pa"ss&wort', recipient_postal_code="53113")
    server().respond((200, piece()))
    provider.track(NUMBER)
    outer = sent_xml(server().requests[0])
    assert outer.get("appname") == "kunde<&>" and outer.get("password") == 'pa"ss&wort'
    assert outer.find("data").get("zip-code") == "53113"
    raw = server().requests[0]["query"]["xml"][0]
    assert "kunde&lt;&amp;&gt;" in raw  # sauber maskiert, kein XML-Bruch


def test_tracking_user_without_password_is_rejected_without_request():
    provider = make(api="parcel_de", tracking_user="kunde")
    server().respond()
    exc = failure(provider)
    assert "gemeinsam" in str(exc) and server().requests == []
    assert provider.live_details()["live_missing"] == ["tracking_password"]


# --- 2./3./4. Anmeldung abgelehnt ----------------------------------------------

@pytest.mark.parametrize("status", [401, 403])
def test_gateway_rejects_key_or_secret(status):
    provider = make(api="parcel_de")
    server().respond((status, {"title": "Unauthorized", "detail": f"Access denied {KEY} {SECRET}"}))
    exc = failure(provider)
    assert exc.abort and exc.level == logging.ERROR and f"HTTP {status}" in str(exc)
    assert "API-Secret" in str(exc) and "freischalten" in str(exc)
    assert KEY not in str(exc) and SECRET not in str(exc)
    assert provider.live_details()["parcel_de_error"]
    assert NUMBER not in provider.state.get("last_checked", {})


def test_missing_tracking_login_code_5():
    provider = make(api="parcel_de")
    server().respond((200, code(5, "Anmeldung fehlgeschlagen.")))
    exc = failure(provider)
    assert exc.abort and "Anmeldung fehlgeschlagen (Code 5)" in str(exc) and "Benutzerkennung" in str(exc)
    assert not provider.live_details()["live_api_confirmed"]


def test_missing_secret_in_parcel_mode():
    provider = make(api="parcel_de", api_secret="")
    server().respond()
    exc = failure(provider)
    assert "API-Secret nicht hinterlegt" in str(exc) and server().requests == []
    assert provider.live_details()["live_missing"] == ["api_secret"] and provider.live_details()["live_api"] == ""


# --- 5.–14. Sendungsdaten und Statusmapping --------------------------------------

def test_history_sorted_newest_first_with_locations():
    events = (event("02.10.2026 19:20", "Die Sendung wurde von DHL bearbeitet.", location="Bonn")
              + event("03.10.2026 08:12", "Die Sendung wurde in das Zustellfahrzeug geladen.", "LDTMV", "PO",
                      "Köln")
              + event("03.10.2026 05:43", "Die Sendung wurde im Ziel-Paketzentrum bearbeitet.", "ULFMV", "EE"))
    provider = make()
    server().respond((200, piece(status="Die Sendung wurde in das Zustellfahrzeug geladen.", ts="03.10.2026 08:12",
                                 ice="LDTMV", standard="PO", events=events)))
    shipment = provider.track(NUMBER)
    assert shipment.status == Status.OUT_FOR_DELIVERY
    assert [e.timestamp for e in shipment.events] == ["2026-10-03T08:12:00+02:00", "2026-10-03T05:43:00+02:00",
                                                      "2026-10-02T19:20:00+02:00"]
    assert shipment.events[0].location == "Köln" and shipment.events[2].description.startswith("Die Sendung wurde von")


def test_delivery_day_and_time_window():
    provider = make()
    server().respond((200, piece(extra='delivery-date="2026-10-05" delivery-timeframe-from="10:00" '
                                       'delivery-timeframe-to="13:00"')))
    shipment = provider.track(NUMBER)
    assert (shipment.eta, shipment.eta_window) == ("2026-10-05", "10:00–13:00")


def test_no_window_is_invented():
    provider = make()
    server().respond((200, piece()))
    shipment = provider.track(NUMBER)
    assert (shipment.eta, shipment.eta_window) == ("", "")


@pytest.mark.parametrize("attrs, expected", [
    (dict(status="Die Sendungsdaten wurden elektronisch übermittelt.", ice="PARCV", standard="VA"),
     Status.ANNOUNCED),
    (dict(status="Die Sendung wurde im Start-Paketzentrum bearbeitet.", ice="LDTMV", standard="AA"),
     Status.IN_TRANSIT),
    (dict(status="Die Sendung wurde im Ziel-Paketzentrum bearbeitet.", ice="ULFMV", standard="EE"),
     Status.IN_TRANSIT),
    (dict(status="Die Sendung wurde in das Zustellfahrzeug geladen.", ice="LDTMV", standard="PO"),
     Status.OUT_FOR_DELIVERY),
    (dict(status="Der Empfänger wurde nicht angetroffen.", ice="NTDEL", standard="ZN"), Status.EXCEPTION),
    (dict(status="Die Sendung liegt in der Filiale zur Abholung bereit.", ice="HLDCC", standard="ZF"),
     Status.PICKUP_READY),
    (dict(status="Die Sendung wurde in die PACKSTATION eingeliefert.", ice="", standard=""), Status.PICKUP_READY),
    (dict(status="Der Empfänger wurde benachrichtigt, die Sendung liegt in der Filiale.", ice="CNRFC",
          standard="ZF"), Status.PICKUP_READY),
    (dict(status="Die Sendung wurde erfolgreich zugestellt.", ice="DLVRD", standard="ZU", delivered="1"),
     Status.DELIVERED),
    (dict(status="Die Sendung wird an den Absender zurückgesendet.", ice="RETRN", standard="BV"), Status.RETURNED),
    (dict(status="Rücksendung", ice="OFWRD", standard="AA", extra='ruecksendung="true"'), Status.RETURNED),
    (dict(status="Die Sendung wurde beschädigt.", ice="DMGDS", standard="BV"), Status.EXCEPTION),
])
def test_status_mapping(attrs, expected):
    provider = make()
    server().respond((200, piece(**attrs)))
    assert provider.track(NUMBER).status == expected


def test_delivered_without_eta():
    provider = make()
    server().respond((200, piece(status="zugestellt", ice="DLVRD", standard="ZU", delivered="1",
                                 extra='delivery-date="2026-10-03"')))
    shipment = provider.track(NUMBER)
    assert shipment.status == Status.DELIVERED and shipment.eta == ""


# --- 16. Fehlerfälle ---------------------------------------------------------------

@pytest.mark.parametrize("response, abort, text", [
    ((200, code(100, "Keine Daten gefunden.")), False, "Code 100"),
    ((200, code(200)), False, "keine elektronischen Sendungsdaten"),
    ((200, code(57)), False, "PLZ"),
    ((200, code(41)), False, "Sendungsnummer prüfen"),
    ((200, code(-1)), True, "vorübergehend gestört"),
    ((200, b""), False, "Leere Antwort"),
    ((200, b"<data><kaputt"), False, "kein gültiges XML"),
    ((200, b'{"json": true}'), False, "kein gültiges XML"),
    ((200, b'<?xml version="1.0"?><data request-id="x"/>'), False, "kein Statuscode"),
    ((200, b'<?xml version="1.0"?><data name="piece-status-public-list" code="0"/>'), False, "keine Sendungsdaten"),
    ((400, b"bad"), False, "HTTP 400"),
    ((404, b"none"), False, "nicht gefunden"),
    ((500, b"oops"), True, "HTTP 500"),
    ((503, b"wartung"), True, "HTTP 503"),
    ((429, b"slow down", {"Retry-After": "60"}), True, "HTTP 429"),
])
def test_error_cases(response, abort, text):
    provider = make(api="parcel_de")
    server().respond(response)
    exc = failure(provider)
    assert exc.abort is abort and text in str(exc)


def test_xxe_and_entities_are_rejected():
    provider = make(api="parcel_de")
    evil = (b'<?xml version="1.0"?><!DOCTYPE data [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
            b'<data name="piece-status-public-list" code="0"><data piece-code="1" status="&x;"/></data>')
    server().respond((200, evil))
    exc = failure(provider)
    assert "DTD/Entities" in str(exc)


def test_timeout_and_dns_errors():
    provider = make(api="parcel_de")
    provider.TIMEOUT = 0.3
    server().respond((200, piece(), {}, 1.5))
    assert "Zeitüberschreitung" in str(failure(provider))

    provider = make(api="parcel_de")
    provider.PARCEL_URL = "http://host.invalid/parcel"
    exc = failure(provider)
    assert exc.abort and "nicht erreichbar" in str(exc)

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    provider = make(api="parcel_de")
    provider.PARCEL_URL = f"http://127.0.0.1:{port}/parcel"
    assert "nicht erreichbar" in str(failure(provider))


# --- 17./18. Priorität und Fallback ------------------------------------------------

def test_parcel_de_preferred_in_auto_mode():
    provider = make()
    server().respond((200, piece()))
    provider.track(NUMBER)
    assert [r["path"] for r in server().requests] == ["/parcel/de/tracking/v0/shipments"]


def test_unified_used_without_secret_and_in_unified_mode():
    for settings in ({"api_secret": ""}, {"api": "unified"}):
        provider = make(**settings)
        server().respond((200, unified.api_shipment()))
        provider.track(NUMBER)
        assert [r["path"] for r in server().requests] == ["/track/shipments"]
        assert provider.live_details()["live_api"] == "unified"


def test_fallback_to_unified_after_parcel_auth_error_and_pause():
    provider = make()
    server().respond((401, b"Unauthorized"), (200, unified.api_shipment(code="transit")))
    shipment = provider.track(NUMBER)
    assert [r["path"] for r in server().requests] == ["/parcel/de/tracking/v0/shipments", "/track/shipments"]
    assert shipment.status == Status.IN_TRANSIT
    details = provider.live_details()
    assert details["live_api"] == "unified" and details["live_api_confirmed"]
    assert "HTTP 401" in details["parcel_de_error"] and details["parcel_de_paused_until"]

    server().respond((200, unified.api_shipment()))  # während der Pause keine Parcel-DE-Abfrage
    provider.state["last_checked"] = {}
    provider.track(NUMBER)
    assert [r["path"] for r in server().requests] == ["/track/shipments"]

    provider.state["parcel_de_paused_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    server().respond((200, piece()))
    provider.track(NUMBER)
    assert [r["path"] for r in server().requests] == ["/parcel/de/tracking/v0/shipments"]
    assert "parcel_de_error" not in provider.state


def test_no_fallback_for_temporary_errors_or_unknown_shipments():
    for response in ((503, b"down"), (200, code(100))):
        provider = make()
        server().respond(response, (200, unified.api_shipment()))
        failure(provider)
        assert len(server().requests) == 1  # keine unnötige Doppelabfrage


def test_no_fallback_in_explicit_parcel_mode():
    provider = make(api="parcel_de")
    server().respond((401, b"Unauthorized"), (200, unified.api_shipment()))
    failure(provider)
    assert len(server().requests) == 1


# --- 19. Rate Limit ------------------------------------------------------------------

def test_rate_limit_shared_with_existing_throttle():
    provider = make()
    server().respond((429, b"Too Many Requests", {"Retry-After": "120"}))
    assert failure(provider).abort
    assert "cooldown_until" in provider.state
    exc = failure(provider)
    assert "Pause" in str(exc) and len(server().requests) == 1


def test_daily_limit_counts_parcel_calls():
    provider = make(daily_limit=1)
    server().respond((200, piece()))
    provider.track(NUMBER)
    exc = failure(provider, "00340434000000000002")
    assert "Tageslimit" in str(exc) and len(server().requests) == 1


# --- Verbindungstest -------------------------------------------------------------

def test_connection_test_with_unknown_test_number():
    provider = make()
    server().respond((200, code(100)), (404, {"title": "No shipment found"}))
    message = provider.test_connection()
    assert "Parcel DE Tracking: ✓ API erreichbar · ✓ Authentifizierung erfolgreich" in message
    assert "Shipment Tracking – Unified: ✓ API erreichbar · ✓ Authentifizierung erfolgreich" in message
    assert KEY not in message and SECRET not in message


def test_connection_test_with_own_shipment_reports_data():
    provider = make(api="parcel_de")
    server().respond((200, piece(number="JVGL00000000000000000001")))
    message = provider.test_connection("JVGL00000000000000000001")
    assert "✓ Sendungsdaten empfangen (Unterwegs)" in message
    assert sent_xml(server().requests[0]).find("data").get("piece-code") == "JVGL00000000000000000001"


def test_connection_test_reports_failure_without_secrets():
    provider = make(api="parcel_de")
    server().respond((401, {"title": "Unauthorized", "detail": f"key {KEY}"}))
    with pytest.raises(ProviderError) as info:
        provider.test_connection()
    assert "✗" in str(info.value) and "HTTP 401" in str(info.value) and KEY not in str(info.value)


def test_connection_test_auto_mode_ok_if_unified_works():
    provider = make()
    server().respond((401, b"no"), (404, {"title": "No shipment found"}))
    message = provider.test_connection()
    assert "Parcel DE Tracking: ✗" in message and "Unified: ✓" in message


# --- 15./16./20. Engine: IMAP aus, alter Status bleibt, zugestellt nicht erneut abfragen

def _engine(paths, numbers, **dhl):
    settings = config.defaults()
    settings["general"]["mock_mode"] = False
    settings["mqtt"]["enabled"] = False
    settings["providers"]["dhl"].update(dhl)
    paths.settings_file.write_text(json.dumps(settings))
    creds = json.loads(paths.credentials_file.read_text())
    creds["providers"] = {"dhl": {"api_key": KEY, "api_secret": SECRET}}
    paths.credentials_file.write_text(json.dumps(creds))
    paths.tracked_file.write_text(json.dumps([{"provider": "auto", "tracking_number": n} for n in numbers]))
    return config.load(paths)


def _run(paths, cfg):
    old = (DhlProvider.PARCEL_URL, DhlProvider.API_URL, DhlProvider.MIN_SPACING)
    DhlProvider.PARCEL_URL = server().url + "/parcel/de/tracking/v0/shipments"
    DhlProvider.API_URL = server().url + "/track/shipments"
    DhlProvider.MIN_SPACING = 0
    try:
        from pakettracker import engine
        assert engine.run(paths, cfg, force=True) == 0
    finally:
        DhlProvider.PARCEL_URL, DhlProvider.API_URL, DhlProvider.MIN_SPACING = old
    return json.loads(paths.state_file.read_text())


def _now_ts():
    return datetime.now(timezone.utc).astimezone().strftime("%d.%m.%Y %H:%M")


def test_engine_parcel_de_without_imap(plugin_root):
    cfg = _engine(plugin_root, ["JVGL00000000000000000001"])
    assert cfg.get("email", "enabled") is False
    server().respond((200, piece(number="JVGL00000000000000000001", ts=_now_ts(),
                                 events=event(_now_ts(), "Die Sendung wurde im Ziel-Paketzentrum bearbeitet."))))
    state = _run(plugin_root, cfg)
    [shipment] = state["shipments"]
    assert shipment["provider"] == "dhl" and shipment["status_code"] == 2 and shipment["live_checked"]
    assert shipment["events"][0]["description"] == "Die Sendung wurde im Ziel-Paketzentrum bearbeitet."
    info = state["providers"]["dhl"]
    assert info["source"] == "api" and info["live_api"] == "parcel_de" and info["live_api_confirmed"] is True
    assert info["live_api_label"] == "Parcel DE Tracking" and info["health"] == "ok"
    dumped = json.dumps(state)
    assert KEY not in dumped and SECRET not in dumped


def test_engine_error_keeps_last_good_status_and_delivered_is_not_polled(plugin_root):
    cfg = _engine(plugin_root, [NUMBER])
    server().respond((200, piece(ts=_now_ts())))
    good = _run(plugin_root, cfg)["shipments"][0]

    for response in ((503, b"down"), (200, code(-1)), (200, b"<kaputt")):
        provider_state = json.loads(plugin_root.provider_state_file.read_text())
        provider_state["dhl"]["last_checked"] = {}
        plugin_root.provider_state_file.write_text(json.dumps(provider_state))
        server().respond(response)
        after = _run(plugin_root, cfg)["shipments"][0]
        assert {k: after[k] for k in ("status_code", "status_text", "last_update", "live_checked")} == \
            {k: good[k] for k in ("status_code", "status_text", "last_update", "live_checked")}

    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    provider_state["dhl"]["last_checked"] = {}
    plugin_root.provider_state_file.write_text(json.dumps(provider_state))
    server().respond((200, piece(status="zugestellt", ice="DLVRD", standard="ZU", delivered="1", ts=_now_ts())))
    assert _run(plugin_root, cfg)["shipments"][0]["status_code"] == 4

    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    provider_state["dhl"]["last_checked"] = {}
    plugin_root.provider_state_file.write_text(json.dumps(provider_state))
    server().respond((200, piece()))
    _run(plugin_root, cfg)
    assert server().requests == []  # zugestellt → keine weitere Abfrage


def test_existing_unified_setup_unchanged_after_update(plugin_root):
    """1.0.1-Konfiguration (nur API-Key, kein api-Feld) fragt weiterhin ausschließlich Unified ab."""
    settings = config.defaults()
    settings["general"]["mock_mode"] = False
    settings["mqtt"]["enabled"] = False
    del settings["providers"]["dhl"]["api"]
    plugin_root.settings_file.write_text(json.dumps(settings))
    creds = json.loads(plugin_root.credentials_file.read_text())
    creds["providers"] = {"dhl": {"api_key": KEY}}
    plugin_root.credentials_file.write_text(json.dumps(creds))
    plugin_root.tracked_file.write_text(json.dumps([{"provider": "dhl", "tracking_number": NUMBER}]))
    cfg = config.load(plugin_root)
    assert cfg.get("providers.dhl", "api") == "auto" and cfg.get("providers.dhl", "api_secret") == ""

    server().respond((200, unified.api_shipment(ts=datetime.now(timezone.utc).isoformat())))
    state = _run(plugin_root, cfg)
    assert [r["path"] for r in server().requests] == ["/track/shipments"]
    assert state["providers"]["dhl"]["live_api"] == "unified"
    assert json.loads(plugin_root.credentials_file.read_text())["providers"]["dhl"] == {"api_key": KEY}


def test_incomplete_tracking_login_in_auto_mode_uses_unified():
    provider = make(tracking_password="nur-passwort")
    server().respond((200, unified.api_shipment()))
    provider.track(NUMBER)
    assert [r["path"] for r in server().requests] == ["/track/shipments"]
    details = provider.live_details()
    assert details["live_api"] == "unified" and details["live_missing"] == ["tracking_user"]


def test_old_parcel_error_hidden_in_unified_mode():
    provider = make(api="unified")
    provider.state["parcel_de_error"] = "alter Fehler"
    assert provider.live_details()["parcel_de_error"] == ""
