"""Hermes-Live-Abfrage (Sendungsverfolgung myhermes.de) gegen einen lokalen Testserver."""
import json
import logging
from datetime import datetime, timezone

import pytest

from pakettracker import config, engine
from pakettracker.models import Status
from pakettracker.providers.base import ProviderError, local_window
from pakettracker.providers.hermes import HermesProvider

from fakehttp import server

NUMBER = "01234567890128"


def progress(code, text, ts, status="HAPPY"):
    return {"parcelStatus": code, "historyText": text, "headlineText": text, "status": status, "timestamp": ts}


def hermes_search(events=None, number=NUMBER, forecast=True, attributes=None, view=None):
    item = {
        "barcode": number,
        "parcelProgress": events if events is not None else [
            progress("ANNOUNCED", "Die Sendung wurde Hermes elektronisch angekündigt.", "2026-09-30T19:25:10.984Z"),
            progress("SORTED", "Die Sendung wurde in Musterstadt für den Weiterversand vorbereitet.",
                     "2026-10-02T05:58:50.992Z"),
        ],
        "parcelAttributes": {"delivered": False, "directionEnum": "DELIVERY", **(attributes or {})},
        "viewParameters": {"readyForCollection": False, **(view or {})},
    }
    if forecast:
        item["forecast"] = {"deliveryTimeFromUTC": "2026-10-05T08:00:00Z", "deliveryTimeToUTC": "2026-10-05T12:00:00Z"}
    return [item]


def make_provider(**settings) -> HermesProvider:
    base = {"live_lookup": True, "check_interval_minutes": 60, "daily_limit": 200}
    base.update(settings)
    provider = HermesProvider(base, mock=False, log=logging.getLogger("test.hermes"), state={})
    provider.API_URL = server().url + "/tnt/v2/shipments/search"
    provider._sleep = lambda s: None
    return provider


def error_of(provider, number=NUMBER) -> ProviderError:
    try:
        provider.track(number)
    except ProviderError as exc:
        return exc
    raise AssertionError("ProviderError erwartet")


def test_success_status_window_and_history():
    provider = make_provider()
    server().respond((200, hermes_search()))
    shipment = provider.track(NUMBER)

    [request] = server().requests
    assert request["path"] == f"/tnt/v2/shipments/search/{NUMBER}"
    assert request["headers"]["Accept"] == "application/json"
    assert shipment.status == Status.IN_TRANSIT
    assert shipment.status_text == "Die Sendung wurde in Musterstadt für den Weiterversand vorbereitet."
    assert (shipment.eta, shipment.eta_window) == local_window("2026-10-05T08:00:00Z", "2026-10-05T12:00:00Z")
    assert shipment.last_update == "2026-10-02T05:58:50.992Z"
    assert [e.timestamp for e in shipment.events] == ["2026-10-02T05:58:50.992Z", "2026-09-30T19:25:10.984Z"]
    assert provider.state["usage"]["count"] == 1 and NUMBER in provider.state["last_checked"]


@pytest.mark.parametrize("events,attributes,view,expected", [
    ([progress("ANNOUNCED", "angekündigt", "2026-10-01T10:00:00Z")], {}, {}, Status.ANNOUNCED),
    ([progress("OUT_FOR_DELIVERY", "in Zustellung", "2026-10-02T06:00:00Z")], {}, {}, Status.OUT_FOR_DELIVERY),
    ([progress("SORTED", "sortiert", "2026-10-02T06:00:00Z")], {"handedOverOnTour": True}, {},
     Status.OUT_FOR_DELIVERY),
    ([progress("DELIVERED", "zugestellt", "2026-10-02T11:00:00Z")], {}, {}, Status.DELIVERED),
    ([progress("SORTED", "sortiert", "2026-10-02T06:00:00Z")], {"delivered": True}, {}, Status.DELIVERED),
    ([progress("NOT_DELIVERED", "nicht zugestellt", "2026-10-02T11:00:00Z")], {}, {}, Status.EXCEPTION),
    ([progress("SORTED", "verzögert", "2026-10-02T06:00:00Z", status="UNHAPPY")], {}, {}, Status.EXCEPTION),
    ([progress("PARCELSHOP_DELIVERED", "im PaketShop", "2026-10-02T11:00:00Z")], {}, {}, Status.PICKUP_READY),
    ([progress("SORTED", "x", "2026-10-02T06:00:00Z")], {}, {"readyForCollection": True}, Status.PICKUP_READY),
    ([progress("SORTED", "x", "2026-10-02T06:00:00Z")], {"directionEnum": "RETURN"}, {}, Status.RETURNED),
    # Abgabe/Abholung im PaketShop durch Absender bzw. Fahrer ist kein „abholbereit“
    ([progress("PARCELSHOP_COLLECTED_BY_DRIVER", "Die Sendung wurde von Hermes im PaketShop abgeholt.",
               "2026-10-01T16:06:16Z")], {}, {}, Status.IN_TRANSIT),
    ([progress("PARCELSHOP_DROP_OFF", "im PaketShop abgegeben", "2026-09-30T14:59:53Z")], {}, {},
     Status.IN_TRANSIT),
    ([], {}, {}, Status.UNKNOWN),
])
def test_status_mapping(events, attributes, view, expected):
    shipment = HermesProvider.map_shipment(hermes_search(events, attributes=attributes, view=view)[0], NUMBER)
    assert shipment.status == expected


def test_delivered_uses_delivery_date_without_window():
    data = hermes_search([progress("DELIVERED", "zugestellt", "2026-10-02T11:00:00Z")])[0]
    shipment = HermesProvider.map_shipment(data, NUMBER)
    assert shipment.eta == local_window("2026-10-02T11:00:00Z", "")[0] and shipment.eta_window == ""


def test_no_forecast_no_eta():
    shipment = HermesProvider.map_shipment(hermes_search(forecast=False)[0], NUMBER)
    assert (shipment.eta, shipment.eta_window) == ("", "")


def test_picks_matching_barcode():
    other = hermes_search(number="09999999999999", events=[progress("DELIVERED", "zugestellt", "2026-10-02T11:00:00Z")])
    provider = make_provider()
    server().respond((200, other + hermes_search()))
    assert provider.track(NUMBER).status == Status.IN_TRANSIT


@pytest.mark.parametrize("status,body,level,abort", [
    (404, b"", logging.INFO, False),
    (200, [], logging.INFO, False),
    (400, {"reason": "Barcode is not valid\n"}, logging.WARNING, False),
    (403, b"", logging.ERROR, True),
    (503, b"", logging.WARNING, True),
])
def test_errors(status, body, level, abort):
    provider = make_provider()
    server().respond((status, body))
    exc = error_of(provider)
    assert (exc.level, exc.abort) == (level, abort)
    if status == 400:
        assert "Barcode is not valid" in str(exc)


def test_rate_limit_sets_cooldown():
    provider = make_provider()
    server().respond((429, b"", {"Retry-After": "120"}))
    exc = error_of(provider)
    assert exc.abort and "429" in str(exc)
    assert provider.state["cooldown_until"] > datetime.now(timezone.utc).isoformat()


def test_invalid_json():
    provider = make_provider()
    server().respond((200, b"<html>"))
    assert "kein gültiges JSON" in str(error_of(provider))


def test_connection_test_accepts_unknown_number():
    provider = make_provider(live_lookup=False)
    server().respond((400, {"reason": "Barcode is not valid"}))
    message = provider.test_connection()
    assert "erreichbar" in message and "ausgeschaltet" in message
    server().respond((404, b""))
    assert "erreichbar" in make_provider().test_connection()


def test_live_lookup_off_by_default_behaves_like_email_provider():
    provider = HermesProvider({}, mock=False, log=logging.getLogger("test.hermes"), state={})
    assert provider.live_tracking is False
    assert HermesProvider.section().to_dict()["fields"][1]["key"] == "live_lookup"
    assert HermesProvider.section().to_dict()["fields"][1]["default"] is False


def _cfg(paths, live_lookup):
    settings = config.defaults()
    settings["general"].update({"mock_mode": False})
    settings["mqtt"]["enabled"] = False
    settings["email"]["enabled"] = False
    settings["providers"]["hermes"]["live_lookup"] = live_lookup
    paths.settings_file.write_text(json.dumps(settings))
    return config.load(paths)


def test_engine_queries_hermes_only_when_enabled(plugin_root, monkeypatch):
    plugin_root.tracked_file.write_text(json.dumps([{"provider": "hermes", "tracking_number": NUMBER}]))
    monkeypatch.setattr(HermesProvider, "API_URL", server().url + "/tnt/v2/shipments/search")
    monkeypatch.setattr(HermesProvider, "MIN_SPACING", 0.0)

    server().respond()
    [shipment] = engine.collect(_cfg(plugin_root, False), plugin_root)
    assert server().requests == [] and shipment.status == Status.UNKNOWN

    server().respond((200, hermes_search()))
    [shipment] = engine.collect(_cfg(plugin_root, True), plugin_root)
    assert len(server().requests) == 1
    assert shipment.status == Status.IN_TRANSIT and shipment.eta_window
