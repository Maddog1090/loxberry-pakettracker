"""Tests der DHL-Live-Abfrage gegen einen lokalen HTTP-Server (kein Zugriff auf DHL)."""
import json
import logging
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from pakettracker import config, engine
from pakettracker.models import Status
from pakettracker.providers.base import ProviderError
from pakettracker.providers.dhl import DhlProvider

API_KEY = "test-key-NICHT-ECHT-0123456789"
NUMBER = "00340434000000000001"


class FakeDhl(BaseHTTPRequestHandler):
    """Antwortet der Reihe nach mit den Einträgen aus `responses` (status, body, headers, delay)."""

    responses: list = []
    requests: list = []

    def do_GET(self):
        url = urlparse(self.path)
        FakeDhl.requests.append({"path": url.path, "query": parse_qs(url.query), "headers": self.headers})
        status, body, headers, delay = FakeDhl.responses.pop(0) if FakeDhl.responses else (500, b"", {}, 0)
        if delay:
            time.sleep(delay)
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def log_message(self, *args):
        pass


_server = None


def server_url() -> str:
    global _server
    if _server is None:
        _server = ThreadingHTTPServer(("127.0.0.1", 0), FakeDhl)
        _server.daemon_threads = True
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{_server.server_address[1]}/track/shipments"


def respond(*items):
    FakeDhl.requests = []
    FakeDhl.responses = [(s, b if isinstance(b, bytes) else json.dumps(b).encode(), h, d)
                         for s, b, h, d in ((list(i) + [{}, 0])[:4] for i in items)]


def api_shipment(number=NUMBER, code="transit", text="Die Sendung wurde im Paketzentrum bearbeitet.",
                 ts="2026-10-02T09:15:00Z"):
    return {"shipments": [{
        "id": number, "service": "parcel-de",
        "status": {"timestamp": ts, "statusCode": code, "status": "Unterwegs", "description": text},
        "estimatedTimeOfDelivery": "2026-10-03T14:00:00+02:00",
        "events": [{"timestamp": ts, "description": text,
                    "location": {"address": {"addressLocality": "Musterstadt"}}}],
    }]}


def problem(status, title, detail=""):
    return {"type": "about:blank", "status": status, "title": title, "detail": detail}


def make_provider(**settings) -> DhlProvider:
    base = {"api_key": API_KEY, "language": "de", "recipient_postal_code": "", "check_interval_minutes": 60,
            "daily_limit": 250}
    base.update(settings)
    provider = DhlProvider(base, mock=False, log=logging.getLogger("test.dhl"), state={})
    provider.API_URL = server_url()
    provider.sleeps = []
    provider._sleep = provider.sleeps.append
    return provider


def fetch_error(provider, number=NUMBER) -> ProviderError:
    try:
        provider.track(number)
    except ProviderError as exc:
        return exc
    raise AssertionError("ProviderError erwartet")


# --- Erfolg ------------------------------------------------------------------

def test_success_request_and_mapping():
    provider = make_provider(recipient_postal_code="12345")
    respond((200, api_shipment(text="Die Sendung wurde in das Zustellfahrzeug geladen.")))
    shipment = provider.track(NUMBER)

    req = FakeDhl.requests[0]
    assert req["path"] == "/track/shipments"
    assert req["query"] == {"trackingNumber": [NUMBER], "language": ["de"], "recipientPostalCode": ["12345"]}
    assert req["headers"]["DHL-API-Key"] == API_KEY
    assert shipment.status == Status.OUT_FOR_DELIVERY
    assert shipment.status_text == "Die Sendung wurde in das Zustellfahrzeug geladen."
    assert shipment.eta == "2026-10-03"
    assert shipment.last_update == "2026-10-02T09:15:00Z"
    assert shipment.events[0].location == "Musterstadt"
    assert provider.state["usage"]["count"] == 1
    assert NUMBER in provider.state["last_checked"]


def test_invalid_postal_code_not_sent():
    provider = make_provider(recipient_postal_code="12a45")
    respond((200, api_shipment()))
    provider.track(NUMBER)
    assert "recipientPostalCode" not in FakeDhl.requests[0]["query"]


def test_matching_shipment_selected_from_multiple():
    provider = make_provider()
    body = api_shipment(number="OTHER", code="delivered")
    body["shipments"].append(api_shipment(code="pre-transit")["shipments"][0])
    respond((200, body))
    assert provider.track(NUMBER).status == Status.ANNOUNCED


def test_status_without_timestamp_does_not_override():
    provider = make_provider()
    respond((200, {"shipments": [{"id": NUMBER, "status": {"statusCode": "unknown"}}]}))
    assert provider.track(NUMBER).last_update == ""


# --- Fehlerfälle -------------------------------------------------------------

@pytest.mark.parametrize("code", [401, 403])
def test_auth_errors_abort_without_leaking_key(code):
    provider = make_provider()
    respond((code, problem(code, "Unauthorized", f"Invalid key {API_KEY}")),
            (code, problem(code, "Unauthorized", f"Invalid key {API_KEY}")))
    exc = fetch_error(provider)
    assert exc.abort and exc.level == logging.ERROR
    assert "API-Key" in str(exc) and API_KEY not in str(exc)
    assert NUMBER not in provider.state.get("last_checked", {})  # nach Korrektur sofort erneut abfragbar


def test_not_found_keeps_running():
    provider = make_provider()
    respond((404, problem(404, "No shipment with given tracking number found.")),
            (404, problem(404, "No shipment with given tracking number found.")))
    exc = fetch_error(provider)
    assert not exc.abort and exc.level == logging.INFO
    assert "nicht gefunden" in str(exc) and "No shipment" in str(exc)
    assert NUMBER in provider.state["last_checked"]


def test_bad_request():
    provider = make_provider()
    respond((400, problem(400, "Bad Request")), (400, problem(400, "Bad Request")))
    exc = fetch_error(provider)
    assert not exc.abort and "HTTP 400" in str(exc)


def test_rate_limit_with_retry_after_pauses_provider():
    provider = make_provider()
    respond((429, problem(429, "Too Many Requests"), {"Retry-After": "120"}))
    assert fetch_error(provider).abort
    until = datetime.fromisoformat(provider.state["cooldown_until"])
    assert timedelta(seconds=100) < until - datetime.now(timezone.utc) <= timedelta(seconds=120)

    exc = fetch_error(provider)  # während der Pause keine weitere HTTP-Anfrage
    assert exc.abort and "Pause" in str(exc)
    assert len(FakeDhl.requests) == 1


def test_rate_limit_without_retry_after_uses_default_pause():
    provider = make_provider()
    respond((429, problem(429, "Too Many Requests")))
    exc = fetch_error(provider)
    assert exc.abort and "HTTP 429" in str(exc) and "Too Many Requests" in str(exc)
    until = datetime.fromisoformat(provider.state["cooldown_until"])
    assert until - datetime.now(timezone.utc) > timedelta(minutes=29)


def test_timeout():
    provider = make_provider()
    provider.TIMEOUT = 0.3
    respond((200, api_shipment(), {}, 1.5), (200, api_shipment(), {}, 1.5))
    exc = fetch_error(provider)
    assert exc.abort and "Zeitüberschreitung" in str(exc)


def test_server_error_aborts():
    provider = make_provider()
    respond((503, b"Service Unavailable"), (503, b"Service Unavailable"))
    exc = fetch_error(provider)
    assert exc.abort and "HTTP 503" in str(exc)


def test_connection_refused():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    provider = make_provider()
    provider.API_URL = f"http://127.0.0.1:{port}/track/shipments"
    exc = fetch_error(provider)
    assert exc.abort and "nicht erreichbar" in str(exc)


@pytest.mark.parametrize("body", [b"<html>Wartung</html>", b"{\"shipments\": ", b"\xff\xfe", b"[]",
                                  b"{\"shipments\": []}", b"{\"shipments\": [\"x\"]}"])
def test_invalid_responses(body):
    provider = make_provider()
    respond((200, body), (200, body))
    exc = fetch_error(provider)
    assert not exc.abort


def test_missing_api_key():
    provider = make_provider(api_key="  ")
    respond()
    exc = fetch_error(provider)
    assert exc.abort and "API-Key" in str(exc)
    assert FakeDhl.requests == []


# --- Drosselung --------------------------------------------------------------

def test_spacing_between_requests():
    provider = make_provider()
    now = [1000.0]
    provider._clock = lambda: now[0]
    respond((200, api_shipment("111111111111")), (200, api_shipment("222222222222")))
    provider.track("111111111111")
    now[0] += 1.0
    provider.track("222222222222")
    assert len(provider.sleeps) == 1 and abs(provider.sleeps[0] - 4.0) < 1e-6


def test_daily_limit():
    provider = make_provider(daily_limit=1)
    respond((200, api_shipment()))
    provider.track(NUMBER)
    exc = fetch_error(provider, "222222222222")
    assert exc.abort and "Tageslimit" in str(exc)
    assert len(FakeDhl.requests) == 1


def test_daily_counter_resets_next_day():
    provider = make_provider(daily_limit=1)
    provider.state["usage"] = {"day": "2000-01-01", "count": 999}
    respond((200, api_shipment()))
    provider.track(NUMBER)
    assert provider.state["usage"]["count"] == 1


def test_max_requests_per_run():
    provider = make_provider()
    provider.MAX_PER_RUN = 2
    respond((200, api_shipment()), (200, api_shipment()))
    provider.track(NUMBER)
    provider.track(NUMBER)
    exc = fetch_error(provider)
    assert exc.abort and "nächsten Lauf" in str(exc)


def test_due_and_forget():
    provider = make_provider(check_interval_minutes=60)
    assert provider.due(NUMBER)
    provider.state["last_checked"] = {NUMBER: datetime.now(timezone.utc).isoformat(), "OLD": "2026-01-01T00:00:00+00:00"}
    assert not provider.due(NUMBER)
    assert provider.due("OLD")
    provider.forget({NUMBER})
    assert list(provider.state["last_checked"]) == [NUMBER]


def test_mock_mode_unchanged():
    provider = DhlProvider({"api_key": API_KEY}, mock=True, log=logging.getLogger("t"), state={})
    provider.API_URL = server_url()
    respond()
    shipment = provider.track(NUMBER)
    assert shipment.status_text.startswith("[Testmodus]")
    assert FakeDhl.requests == [] and provider.state == {}


# --- Integration mit der Engine ---------------------------------------------

class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def _engine_setup(paths, numbers, **dhl):
    settings = config.defaults()
    settings["general"]["mock_mode"] = False
    settings["mqtt"]["enabled"] = False
    settings["providers"]["dhl"].update(dhl)
    paths.settings_file.write_text(json.dumps(settings))
    creds = json.loads(paths.credentials_file.read_text())
    creds["providers"] = {"dhl": {"api_key": API_KEY}}
    paths.credentials_file.write_text(json.dumps(creds))
    paths.tracked_file.write_text(json.dumps([{"provider": "dhl", "tracking_number": n} for n in numbers]))
    return config.load(paths)


def _run(paths, cfg):
    capture = _Capture()
    logger = logging.getLogger("pakettracker")
    logger.addHandler(capture)
    logger.setLevel(logging.DEBUG)
    old = (DhlProvider.API_URL, DhlProvider.MIN_SPACING)
    DhlProvider.API_URL, DhlProvider.MIN_SPACING = server_url(), 0
    try:
        assert engine.run(paths, cfg, force=True) == 0
    finally:
        DhlProvider.API_URL, DhlProvider.MIN_SPACING = old
        logger.removeHandler(capture)
    return json.loads(paths.state_file.read_text()), capture.lines


def test_engine_multiple_shipments_and_partial_failure(plugin_root):
    a, b, c = "111111111111", "222222222222", "333333333333"
    cfg = _engine_setup(plugin_root, [a, b, c])
    respond((200, api_shipment(a, "transit")), (404, problem(404, "No shipment found")),
            (200, api_shipment(c, "delivered", "Zugestellt", datetime.now(timezone.utc).isoformat())))
    state, lines = _run(plugin_root, cfg)

    by_number = {s["tracking_number"]: s for s in state["shipments"]}
    assert by_number[a]["status_code"] == 2
    assert by_number[b]["status_code"] == 0  # nicht gefunden – bleibt erhalten
    assert by_number[c]["status_code"] == 4
    assert state["summary"]["delivered_today"] == 1
    assert [s["tracking_number"] for s in state["slots"][:3]] == [a, b, c]
    assert len(FakeDhl.requests) == 3
    assert all(API_KEY not in line for line in lines)
    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    assert provider_state["dhl"]["usage"]["count"] == 3


def test_engine_keeps_last_known_data_on_auth_error(plugin_root):
    a, b = "111111111111", "222222222222"
    cfg = _engine_setup(plugin_root, [a, b])
    respond((200, api_shipment(a, "transit")), (200, api_shipment(b, "pre-transit")))
    _run(plugin_root, cfg)

    # Zweiter Lauf: Intervall abgelaufen, Key inzwischen ungültig
    provider_state = json.loads(plugin_root.provider_state_file.read_text())
    provider_state["dhl"]["last_checked"] = {}
    plugin_root.provider_state_file.write_text(json.dumps(provider_state))
    respond((401, problem(401, "Unauthorized")), (401, problem(401, "Unauthorized")))
    state, lines = _run(plugin_root, cfg)

    assert len(FakeDhl.requests) == 1  # nach 401 keine weiteren Abfragen
    by_number = {s["tracking_number"]: s for s in state["shipments"]}
    assert by_number[a]["status_code"] == 2 and by_number[b]["status_code"] == 1
    assert any("API-Key" in line for line in lines)


def test_engine_respects_check_interval(plugin_root):
    cfg = _engine_setup(plugin_root, [NUMBER], check_interval_minutes=60)
    respond((200, api_shipment()))
    _run(plugin_root, cfg)
    respond((200, api_shipment()))
    _run(plugin_root, cfg)
    assert FakeDhl.requests == []  # zweiter Lauf: Sendung noch nicht wieder fällig


def test_engine_switch_from_mock_to_live(plugin_root):
    cfg = _engine_setup(plugin_root, [NUMBER])
    settings = json.loads(plugin_root.settings_file.read_text())
    settings["general"]["mock_mode"] = True
    plugin_root.settings_file.write_text(json.dumps(settings))
    mock_state, _ = _run(plugin_root, config.load(plugin_root))
    assert mock_state["shipments"][0]["status_text"].startswith("[Testmodus]")

    # Echte DHL-Daten sind älter als der simulierte Zeitstempel – müssen trotzdem übernommen werden
    respond((200, api_shipment(code="pre-transit", text="Elektronisch angekündigt", ts="2026-09-30T08:00:00+02:00")))
    state, _ = _run(plugin_root, cfg)
    [shipment] = state["shipments"]
    assert shipment["status_code"] == 1
    assert shipment["status_text"] == "Elektronisch angekündigt"
    assert state["mock_mode"] is False
