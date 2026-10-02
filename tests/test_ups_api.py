"""UPS Tracking API (OAuth Client Credentials) gegen einen lokalen Testserver."""
import base64
import logging
from datetime import datetime, timedelta, timezone

import pytest

from pakettracker.models import Status
from pakettracker.providers.base import ProviderError
from pakettracker.providers.ups import UpsProvider

from fakehttp import server

CLIENT_ID = "test-client-NICHT-ECHT"
CLIENT_SECRET = "test-secret-NICHT-ECHT-987"
NUMBER = "1Z999AA10123456784"
TOKEN = {"access_token": "tok-NICHT-ECHT-xyz", "token_type": "Bearer", "expires_in": "14399"}


def ups_track(type_="I", desc="Unterwegs", number=NUMBER, dates=None, activities=True):
    package = {
        "trackingNumber": number,
        "currentStatus": {"type": type_, "code": "005", "description": desc},
        "deliveryDate": dates if dates is not None else [{"type": "SDD", "date": "20261005"}],
    }
    if activities:
        package["activity"] = [{
            "date": "20261002", "time": "081500", "gmtDate": "20261002", "gmtTime": "61500", "gmtOffset": "+02:00",
            "status": {"type": type_, "description": desc}, "location": {"address": {"city": "Köln"}},
        }]
    return {"trackResponse": {"shipment": [{"inquiryNumber": number, "package": [package]}]}}


def ups_error(code, message):
    return {"response": {"errors": [{"code": code, "message": message}]}}


def make_provider(**settings) -> UpsProvider:
    base = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "environment": "production", "language": "de",
            "check_interval_minutes": 60, "daily_limit": 250}
    base.update(settings)
    provider = UpsProvider(base, mock=False, log=logging.getLogger("test.ups"), state={})
    provider.BASE_URL = server().url
    provider._sleep = lambda s: None
    return provider


def error_of(provider, number=NUMBER) -> ProviderError:
    try:
        provider.track(number)
    except ProviderError as exc:
        return exc
    raise AssertionError("ProviderError erwartet")


def test_success_oauth_and_tracking():
    provider = make_provider()
    server().respond((200, TOKEN), (200, ups_track()))
    shipment = provider.track(NUMBER)

    token_req, track_req = server().requests
    assert token_req["method"] == "POST" and token_req["path"] == "/security/v1/oauth/token"
    assert token_req["body"] == b"grant_type=client_credentials"
    assert token_req["headers"]["Authorization"] == "Basic " + base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    assert track_req["path"] == f"/api/track/v1/details/{NUMBER}"
    assert track_req["query"]["locale"] == ["de_DE"]
    assert track_req["headers"]["Authorization"] == "Bearer tok-NICHT-ECHT-xyz"
    assert len(track_req["headers"]["transId"]) == 32 and track_req["headers"]["transactionSrc"]

    assert (shipment.status, shipment.status_text, shipment.eta) == (Status.IN_TRANSIT, "Unterwegs", "2026-10-05")
    assert shipment.last_update == "2026-10-02T06:15:00+00:00"
    assert shipment.events[0].location == "Köln"


def test_token_reused_within_run():
    provider = make_provider()
    server().respond((200, TOKEN), (200, ups_track()), (200, ups_track()))
    provider.track(NUMBER)
    provider.track(NUMBER)
    assert [r["path"].split("/")[1] for r in server().requests] == ["security", "api", "api"]


@pytest.mark.parametrize("type_, desc, dates, expected, eta", [
    ("O", "Zustellung heute", None, Status.OUT_FOR_DELIVERY, "2026-10-05"),
    ("D", "Zugestellt", [{"type": "SDD", "date": "20261005"}, {"type": "DEL", "date": "20261002"}],
     Status.DELIVERED, "2026-10-02"),
    ("RS", "Zurück an Absender", [], Status.RETURNED, ""),
    ("X", "Adresse unvollständig", None, Status.EXCEPTION, "2026-10-05"),
    ("M", "Sendungsdaten übermittelt", [{"type": "RDD", "date": "20261007"}, {"type": "SDD", "date": "20261005"}],
     Status.ANNOUNCED, "2026-10-07"),
    ("I", "Im UPS Access Point abholbereit", None, Status.PICKUP_READY, "2026-10-05"),
])
def test_status_mapping(type_, desc, dates, expected, eta):
    provider = make_provider()
    server().respond((200, TOKEN), (200, ups_track(type_, desc, dates=dates)))
    shipment = provider.track(NUMBER)
    assert (shipment.status, shipment.eta) == (expected, eta)


def test_oauth_rejected_without_leaking_secret():
    provider = make_provider()
    server().respond((401, ups_error("10401", f"ClientId {CLIENT_ID} / {CLIENT_SECRET} invalid")))
    exc = error_of(provider)
    assert exc.abort and exc.level == logging.ERROR
    assert CLIENT_ID not in str(exc) and CLIENT_SECRET not in str(exc) and "Client-ID" in str(exc)


@pytest.mark.parametrize("code", [401, 403])
def test_tracking_auth_errors(code):
    provider = make_provider()
    server().respond((200, TOKEN), (code, ups_error("250002", "Invalid Authentication Information.")))
    exc = error_of(provider)
    assert exc.abort and exc.level == logging.ERROR and f"HTTP {code}" in str(exc)
    assert "tok-NICHT-ECHT" not in str(exc)
    assert provider._access_token == ""  # beim nächsten Versuch neuer Token
    assert NUMBER not in provider.state.get("last_checked", {})


def test_not_found_keeps_data():
    provider = make_provider()
    server().respond((200, TOKEN), (404, ups_error("151018", "Tracking number not found")))
    exc = error_of(provider)
    assert not exc.abort and exc.level == logging.INFO and "151018" in str(exc)
    assert NUMBER in provider.state["last_checked"]


def test_no_package_with_warning_is_not_found():
    provider = make_provider()
    body = {"trackResponse": {"shipment": [{"inquiryNumber": NUMBER,
                                            "warnings": [{"code": "TW0001", "message": "Tracking Information Not Found"}]}]}}
    server().respond((200, TOKEN), (200, body))
    exc = error_of(provider)
    assert exc.level == logging.INFO and "Not Found" in str(exc)


def test_rate_limit():
    provider = make_provider()
    server().respond((200, TOKEN), (429, ups_error("429", "Too Many Requests"), {"Retry-After": "60"}))
    exc = error_of(provider)
    assert exc.abort and "HTTP 429" in str(exc)
    until = datetime.fromisoformat(provider.state["cooldown_until"])
    assert until - datetime.now(timezone.utc) <= timedelta(seconds=60)
    assert "Pause" in str(error_of(provider)) and len(server().requests) == 2


def test_timeout():
    provider = make_provider()
    provider.TIMEOUT = 0.3
    server().respond((200, TOKEN), (200, ups_track(), {}, 1.5))
    exc = error_of(provider)
    assert exc.abort and "Zeitüberschreitung" in str(exc)


@pytest.mark.parametrize("token_body, track_body, message", [
    (TOKEN, b"<html>", "kein gültiges JSON"),
    (TOKEN, {"trackResponse": {}}, "keine Sendungsdaten"),
    (b"{]", None, "Token-Antwort"),
    ({"token_type": "Bearer"}, None, "Token-Antwort"),
])
def test_invalid_responses(token_body, track_body, message):
    provider = make_provider()
    items = [(200, token_body)] + ([(200, track_body)] if track_body is not None else [])
    server().respond(*items)
    assert message in str(error_of(provider))


def test_missing_credentials_no_request():
    provider = make_provider(client_secret="")
    server().respond()
    exc = error_of(provider)
    assert exc.abort and exc.level == logging.INFO and "Client-Secret" in str(exc)
    assert server().requests == []


def test_connection_test_uses_only_token():
    provider = make_provider()
    server().respond((200, TOKEN))
    assert "erfolgreich" in provider.test_connection()
    assert len(server().requests) == 1 and provider.state.get("usage", {}).get("count", 0) == 0


def test_environment_urls():
    """Nur die URL-Auswahl – es wird kein Request gesendet (conftest sperrt die echten URLs)."""
    for env, url in (("test", "https://wwwcie.ups.com"), ("production", "https://onlinetools.ups.com")):
        provider = UpsProvider({"environment": env}, False, logging.getLogger("t"))
        provider.BASE_URL = ""
        assert provider._base() == url
