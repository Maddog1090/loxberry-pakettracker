"""REST-API (webfrontend/html/api.php) und Hilfe-Abschnitt „Loxone per HTTP/REST“.

Läuft gegen den eingebauten PHP-Webserver (echte HTTP-Statuscodes und Header) mit einer
Ersatz-loxberry_system.php. Ohne PHP werden die Tests übersprungen.
"""
import json
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pakettracker.outputs import snapshot

REPO = Path(__file__).resolve().parents[1]
PHP = shutil.which("php")
pytestmark = pytest.mark.skipif(PHP is None, reason="PHP nicht installiert")

TOKEN = "Tok3n-geheim_xyz"
SECRETS = {"rest": {"token": TOKEN}, "imap": {"password": "imap-passwort-geheim"},
           "dhl": {"api_key": "dhl-key-geheim"}, "ups": {"client_secret": "ups-secret-geheim"}}


def _slot(n, **values):
    data = snapshot._slot(n, None)
    data.update(values)
    return data


STATE = {
    "updated": "2026-10-02T10:00:00+00:00", "updated_epoch": 1790935200, "mock_mode": False,
    "summary": {"active": 2, "announced": 0, "in_transit": 1, "out_for_delivery": 1, "pickup_ready": 0,
                "exception": 0, "delivered_today": 3, "next_eta": "2026-10-02", "arriving_today": 1},
    "providers": {"dhl": {"active": 1, "shipment_count": 1, "error": "", "last_success": ""}},
    "slots": [
        _slot(1, used=1, provider="dhl", tracking_number="00340434000000000001",
              description="  Bücher &amp; Kaffeetasse – Größe XL\n", status="out_for_delivery",
              status_code=3, status_label="In Zustellung", status_text="Zustellung heute", eta="2026-10-02"),
        _slot(2, used=1, provider="amazon", tracking_number="TBA123",
              description="Kabel&#x20;USB-C \"5 m\" <rot> 100 % ✓", status="in_transit", status_code=2,
              status_label="  Unterwegs\t", eta=""),
        _slot(3),
    ],
    "shipments": [],
}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    root = tmp_path_factory.mktemp("lb")
    for name in ("config", "data", "log", "stub"):
        (root / name).mkdir()
    (root / "stub" / "loxberry_system.php").write_text(
        "<?php\n"
        f"define('LBPCONFIGDIR', '{root / 'config'}');\n"
        f"define('LBPDATADIR', '{root / 'data'}');\n"
        f"define('LBPLOGDIR', '{root / 'log'}');\n"
        f"define('LBPBINDIR', '{REPO / 'bin'}');\n"
        f"define('LBPHTMLAUTHDIR', '{REPO / 'webfrontend' / 'htmlauth'}');\n"
        "define('LBPPLUGINDIR', 'pakettracker');\n", encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [PHP, "-d", f"include_path={root / 'stub'}", "-d", "display_errors=1", "-d", "error_reporting=-1",
         "-S", f"127.0.0.1:{port}", "-t", str(REPO / "webfrontend" / "html")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)
    yield {"root": root, "base": f"http://127.0.0.1:{port}/api.php"}
    proc.terminate()
    proc.wait(5)


@pytest.fixture
def api(server):
    """Setzt Standardzustand (REST an, Token an) und liefert get(query) → (status, headers, body)."""
    root = server["root"]

    def configure(enabled=True, require_token=True, state=STATE, secrets=SECRETS):
        (root / "config" / "settings.json").write_text(
            json.dumps({"rest": {"enabled": enabled, "require_token": require_token}}), encoding="utf-8")
        (root / "config" / "credentials.json").write_text(json.dumps(secrets), encoding="utf-8")
        state_file = root / "data" / "state.json"
        state_file.unlink(missing_ok=True)
        if state is not None:
            state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def get(query, token=TOKEN, method="GET"):
        url = server["base"] + "?" + query + (f"&token={token}" if token is not None else "")
        req = urllib.request.Request(url, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.headers, err.read()

    configure()
    get.configure = configure
    return get


def text(api, query, **kw):
    status, headers, body = api(query + "&format=text", **kw)
    return status, headers, body.decode("utf-8")


# --- Einzelwerte -------------------------------------------------------------------------------

@pytest.mark.parametrize("field, expected", [
    ("active", "2"), ("out_for_delivery", "1"), ("delivered_today", "3"), ("next_eta", "2026-10-02"),
])
def test_summary_single_value(api, field, expected):
    status, headers, body = text(api, f"q=summary&field={field}")
    assert status == 200
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert body == expected + "\n"


@pytest.mark.parametrize("field, expected", [
    ("used", "1"), ("provider", "dhl"), ("status_code", "3"), ("status", "out_for_delivery"),
    ("status_label", "In Zustellung"), ("eta", "2026-10-02"), ("tracking_number", "00340434000000000001"),
])
def test_slot_single_value(api, field, expected):
    assert text(api, f"q=slot&n=1&field={field}")[::2] == (200, expected + "\n")


def test_utf8_entities_and_whitespace_are_cleaned(api):
    status, _, body = text(api, "q=slot&n=1&field=description")
    assert status == 200
    assert body == "Bücher & Kaffeetasse – Größe XL\n"          # Entity aufgelöst, NBSP/Zeilenumbruch → Leerzeichen
    assert body.encode("utf-8") == "Bücher & Kaffeetasse – Größe XL\n".encode("utf-8")


def test_special_characters_are_plain_text(api):
    body = text(api, "q=slot&n=2&field=description")[2]
    assert body == 'Kabel USB-C "5 m" <rot> 100 % ✓\n'           # &#x20; → Leerzeichen, nichts HTML-kodiert
    assert "&#" not in body and "&amp;" not in body and "&lt;" not in body
    assert text(api, "q=slot&n=2&field=status_label")[2] == "Unterwegs\n"   # Leerzeichen/Tab am Rand weg


def test_single_value_has_no_surrounding_whitespace(api):
    for query in ("q=summary&field=active", "q=slot&n=1&field=description", "q=slot&n=2&field=status_label"):
        body = text(api, query)[2]
        assert body.endswith("\n") and body.count("\n") == 1
        assert body[:-1] == body[:-1].strip()


@pytest.mark.parametrize("field, expected", [
    ("used", "0"), ("status_code", "0"), ("provider", ""), ("description", ""), ("eta", ""),
    ("status_label", ""), ("tracking_number", ""),
])
def test_empty_slot(api, field, expected):
    assert text(api, f"q=slot&n=3&field={field}")[::2] == (200, expected + "\n")


def test_single_value_as_json(api):
    status, headers, body = api("q=slot&n=1&field=status_code")
    assert status == 200 and headers["Content-Type"] == "application/json; charset=utf-8"
    assert json.loads(body) == {"q": "slot", "n": 1, "field": "status_code", "value": 3}


# --- Fehler --------------------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    "q=summary&field=gibtsnicht", "q=summary&field=../token", "q=slot&n=1&field=token",
    "q=slot&n=1&field=gibtsnicht", "q=summary&field=ACTIVE",
])
def test_unknown_field_is_400(api, query):
    status, headers, body = text(api, query)
    assert status == 400 and body == "Unbekanntes Feld\n"
    assert headers["Content-Type"] == "text/plain; charset=utf-8"


@pytest.mark.parametrize("n", ["0", "-1", "4", "99", "abc", "1.5", ""])
def test_invalid_slot_is_400(api, n):
    status, _, body = text(api, f"q=slot&n={n}&field=used")
    assert status == 400 and body == "Ungültiger Slot\n"


@pytest.mark.parametrize("token", [None, "", "falsch", TOKEN + "x", TOKEN.upper()])
def test_wrong_or_missing_token_is_403(api, token):
    status, _, body = text(api, "q=summary&field=active", token=token)
    assert status == 403 and body == "Ungültiger Token\n"


def test_token_not_needed_when_protection_off(api):
    api.configure(require_token=False)
    assert text(api, "q=summary&field=active", token=None)[::2] == (200, "2\n")


def test_rest_disabled_is_403(api):
    api.configure(enabled=False)
    for fmt in ("text", "json"):
        status, _, body = api(f"q=summary&field=active&format={fmt}")
        assert status == 403 and b"deaktiviert" in body


def test_no_data_is_503(api):
    api.configure(state=None)
    assert text(api, "q=summary&field=active")[0] == 503


def test_only_get_allowed(api):
    status, headers, _ = api("q=summary&field=active&format=text", method="POST")
    assert status == 405 and "GET" in headers["Allow"]


def test_array_parameters_do_not_cause_php_warnings(api):
    for query in ("q[]=summary&format=text", "q=slot&n[]=1&field=used&format=text",
                  "q=summary&field[]=active&format=text"):
        status, _, body = api(query)
        assert status in (200, 400)
        assert b"<b>" not in body and b"Warning" not in body and b"Notice" not in body


def test_broken_state_file_gives_plain_503(api, server):
    (server["root"] / "data" / "state.json").write_text("{kaputt", encoding="utf-8")
    status, headers, body = text(api, "q=slot&n=1&field=provider")
    assert status == 503 and headers["Content-Type"].startswith("text/plain")


def test_old_state_without_slots_gives_400_not_warning(api):
    api.configure(state={"updated": "", "updated_epoch": 0, "mock_mode": False, "summary": {"active": 0}})
    status, _, body = text(api, "q=slot&n=1&field=used")
    assert status == 400 and body == "Ungültiger Slot\n"


# --- Rückwärtskompatibilität ---------------------------------------------------------------------

def test_legacy_text_format_unchanged(api):
    body = text(api, "q=summary")[2]
    assert "summary.active=2\n" in body and "providers.dhl.error=\n" in body and "mock_mode=0\n" in body
    slot = text(api, "q=slot&n=1")[2]
    assert "status_code=3\n" in slot and "description=Bücher & Kaffeetasse – Größe XL\n" in slot


def test_legacy_json_and_missing_slot(api):
    status, _, body = api("q=slots")
    assert status == 200 and len(json.loads(body)["slots"]) == 3
    assert api("q=slot&n=9")[0] == 404
    assert api("q=gibtsnicht")[0] == 400


# --- Keine sensiblen Daten -----------------------------------------------------------------------

def test_no_secrets_in_any_response(api):
    queries = ["q=summary", "q=slots", "q=slot&n=1", "q=shipments", "q=all", "q=summary&field=active",
               "q=slot&n=1&field=gibtsnicht", "q=summary&field=token"]
    secrets = [TOKEN] + [v for section in SECRETS.values() for v in section.values()]
    for query in queries:
        for fmt in ("text", "json"):
            body = api(f"{query}&format={fmt}")[2].decode("utf-8")
            assert not any(secret in body for secret in secrets), query
    body = text(api, "q=summary&field=active", token="falsch")[2]
    assert TOKEN not in body


def test_api_never_logs():
    php = (REPO / "webfrontend" / "html" / "api.php").read_text(encoding="utf-8")
    assert "error_log" not in php and "LOGSTART" not in php and "file_put_contents" not in php


# --- Hilfe-Seite ---------------------------------------------------------------------------------

def _render_help(tmp_path, lang, rest, server_addr="192.168.178.65", http_host="loxberry"):
    script = tmp_path / "render.php"
    script.write_text(f"""<?php
define('LBPTEMPLATEDIR', '{REPO / 'templates'}');
define('LBPHTMLAUTHDIR', '{REPO / 'webfrontend' / 'htmlauth'}');
define('LBPPLUGINDIR', 'pakettracker');
class LBSystem {{ public static function lblanguage() {{ return '{lang}'; }} }}
require '{REPO / 'webfrontend' / 'htmlauth' / 'inc' / 'common.php'}';
$L = []; $sec = '';   // wie LBSystem::readlanguage (YES/NO sind für parse_ini_file reserviert)
foreach (file('{REPO / 'templates' / 'lang'}/language_{lang}.ini') as $line) {{
    if (preg_match('/^\\[(\\w+)\\]/', $line, $m)) {{ $sec = $m[1]; }}
    elseif (preg_match('/^(\\w+)="(.*)"\\s*$/', $line, $m)) {{ $L["$sec.$m[1]"] = $m[2]; }}
}}
$_SERVER['HTTP_HOST'] = '{http_host}';
$_SERVER['SERVER_ADDR'] = '{server_addr}';
$describe = json_decode('{json.dumps({"version": "x", "values": {"rest": rest, "mqtt": {}, "general": {}}})}', true);
require '{REPO / 'webfrontend' / 'htmlauth' / 'inc' / 'page_help.php'}';
""", encoding="utf-8")
    result = subprocess.run([PHP, "-d", "display_errors=1", "-d", "error_reporting=-1", str(script)],
                            capture_output=True, text=True, check=True)
    assert "Warning" not in result.stdout and "Notice" not in result.stdout and "Deprecated" not in result.stdout
    return result.stdout


def test_help_shows_loxone_urls_with_token(tmp_path):
    page = _render_help(tmp_path, "de", {"enabled": True, "require_token": True, "token": "a+b/c"})
    assert "<h3>Loxone per HTTP/REST</h3>" in page
    base = "http://192.168.178.65/plugins/pakettracker/api.php?"
    for query in ("q=summary&amp;field=active", "q=summary&amp;field=out_for_delivery",
                  "q=slot&amp;n=1&amp;field=provider", "q=slot&amp;n=1&amp;field=description",
                  "q=slot&amp;n=1&amp;field=status_code", "q=slot&amp;n=1&amp;field=status_label",
                  "q=slot&amp;n=1&amp;field=eta"):
        assert f'href="{base}{query}&amp;format=text&amp;token=a%2Bb%2Fc"' in page
    for name in ("Paket_Anzahl_Aktiv", "Paket_In_Zustellung", "Paket_Heute_Zugestellt") + tuple(
            f"Paket{n}_{k}" for n in (1, 2, 3) for k in ("Aktiv", "Status", "Anbieter", "Beschreibung", "Lieferdatum")):
        assert f"<td>{name}</td>" in page
    assert "{{" not in page


def test_help_urls_without_token_when_protection_off(tmp_path):
    page = _render_help(tmp_path, "de", {"enabled": True, "require_token": False, "token": "geheim123"},
                        server_addr="", http_host="10.1.2.3:8080")
    assert "http://10.1.2.3:8080/plugins/pakettracker/api.php?q=summary&amp;field=active&amp;format=text\"" in page
    assert "geheim123" not in page and "token=" not in page.split("Empfohlene")[0].split("REST</h3>")[1]


def test_help_warns_when_rest_disabled(tmp_path):
    page = _render_help(tmp_path, "de", {"enabled": False, "require_token": True, "token": "t"})
    assert "ausgeschaltet" in page and 'class="pt-msg error"' in page


def test_help_english_has_section(tmp_path):
    page = _render_help(tmp_path, "en", {"enabled": True, "require_token": True, "token": "t"})
    assert "Loxone via HTTP/REST" in page and "{{" not in page
    assert "q=slot&amp;n=1&amp;field=eta&amp;format=text&amp;token=t" in page


def test_help_ignores_hostile_host_header(tmp_path):
    page = _render_help(tmp_path, "de", {"enabled": True, "require_token": False, "token": ""},
                        server_addr="", http_host='evil"><script>')
    assert "<script>" not in page and "http://loxberry/plugins/pakettracker/api.php" in page
