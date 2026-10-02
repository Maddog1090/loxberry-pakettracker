"""Installations-, Upgrade- und Deinstallationspfad mit den echten Shell-Skripten.

Nachgebildet wird, was der LoxBerry-Installer (sbin/plugininstall.pl) tut:
preupgrade → Plugin-Ordner löschen → Dateien kopieren (+ REPLACE-Platzhalter) →
postinstall → postupgrade. Es finden keine Netzwerkzugriffe statt (Testmodus).
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from pathlib import Path

from pakettracker import __version__

REPO = Path(__file__).resolve().parents[1]
FOLDER = "pakettracker"
OLD_CREDENTIALS = {"rest": {"token": "alter-token-0.1.1"}, "mqtt": {"password": "mqtt-NICHT-ECHT"},
                   "providers": {"dhl": {"api_key": "dhl-key-NICHT-ECHT"}}}


def _dirs(lb: Path, kind: str) -> Path:
    return lb / kind / "plugins" / FOLDER


def _copy_plugin(lb: Path) -> None:
    for kind in ("config", "bin", "templates"):
        target = _dirs(lb, kind)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(REPO / kind, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
    for kind in ("data", "log"):
        _dirs(lb, kind).mkdir(parents=True, exist_ok=True)
    for sub in ("htmlauth", "html"):
        target = lb / "webfrontend" / sub / "plugins" / FOLDER
        shutil.copytree(REPO / "webfrontend" / sub, target, dirs_exist_ok=True)
    cron = lb / "system" / "cron" / "cron.05min"
    cron.mkdir(parents=True, exist_ok=True)
    text = (REPO / "cron" / "cron.05min").read_text().replace("REPLACELBPBINDIR", str(_dirs(lb, "bin")))
    (cron / FOLDER).write_text(text)
    for path in _dirs(lb, "bin").rglob("*"):
        path.chmod(0o755 if path.is_dir() or path.suffix == ".py" else 0o644)


def _script(name: str, lb: Path, tmpid: str, version: str = __version__) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LBSCONFIG": str(lb / "config" / "system")}
    result = subprocess.run(["bash", str(REPO / name), tmpid, FOLDER, FOLDER, version, str(lb), str(REPO)],
                            cwd=REPO, env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _backend(lb: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LBSCONFIG": str(lb / "config" / "system")}
    return subprocess.run([sys.executable, str(_dirs(lb, "bin") / "pakettracker.py"), *args],
                          env=env, capture_output=True, text=True, timeout=60)


def _old_installation(lb: Path) -> None:
    """Stand einer 0.1.1-Installation mit Nutzerdaten."""
    (lb / "config" / "system").mkdir(parents=True)
    (lb / "config" / "system" / "general.json").write_text('{"Base": {}}')
    _copy_plugin(lb)
    config = _dirs(lb, "config")
    (config / "settings.json").write_text(json.dumps({
        "general": {"interval_minutes": 30, "mock_mode": True, "loglevel": "debug"},
        "mqtt": {"enabled": False, "base_topic": "paket"},
        "email": {"enabled": False, "use_ssl": True, "folder": "INBOX"},   # Feld aus 0.1.x
        "providers": {"dhl": {"enabled": True, "check_interval_minutes": 45}, "amazon": {"enabled": False}},
    }))
    (config / "credentials.json").write_text(json.dumps(OLD_CREDENTIALS))
    (config / "credentials.json").chmod(0o600)
    data = _dirs(lb, "data")
    (data / "tracked.json").write_text(json.dumps([{"provider": "auto", "tracking_number": "00340434000000000001",
                                                    "description": "Altbestand"}]))
    (data / "provider_state.json").write_text(json.dumps({"dhl": {"usage": {"day": "2026-10-01", "count": 17}}}))
    (data / "state.json").write_text(json.dumps({"mock_mode": True, "shipments": [{
        "provider": "dhl", "tracking_number": "00340434000000000001", "status": "in_transit",
        "description": "Altbestand", "origins": ["manual"], "last_update": "2026-10-01T10:00:00+00:00"}]}))


def test_upgrade_from_0_1_x_keeps_config_data_credentials(tmp_path):
    lb = tmp_path / "lb"
    _old_installation(lb)
    tmpid = f"pttest{uuid.uuid4().hex[:8]}"
    backup = Path(f"/tmp/{tmpid}_upgrade")

    _script("preupgrade.sh", lb, tmpid)
    assert backup.is_dir()
    for kind in ("config", "data", "bin"):          # purge_installation des Installers
        shutil.rmtree(_dirs(lb, kind))
    _copy_plugin(lb)
    _script("postinstall.sh", lb, tmpid)
    _script("postupgrade.sh", lb, tmpid)
    assert not backup.exists()

    creds_file = _dirs(lb, "config") / "credentials.json"
    assert json.loads(creds_file.read_text()) == OLD_CREDENTIALS
    assert stat.S_IMODE(creds_file.stat().st_mode) == 0o600
    settings = json.loads((_dirs(lb, "config") / "settings.json").read_text())
    assert settings["general"]["interval_minutes"] == 30 and settings["mqtt"]["base_topic"] == "paket"
    assert json.loads((_dirs(lb, "data") / "provider_state.json").read_text())["dhl"]["usage"]["count"] == 17

    described = json.loads(_backend(lb, "describe").stdout)
    assert described["version"] == __version__
    values = described["values"]
    assert values["providers.dhl"]["check_interval_minutes"] == 45     # alter Wert
    assert values["providers.amazon"]["enabled"] is False                # alter Wert
    assert values["providers.ups"]["enabled"] is True                    # neuer Anbieter mit Default
    assert values["email"]["security"] == "ssl"                          # neues Feld mit Default
    assert described["secrets_set"]["providers.dhl"]["api_key"] is True
    assert "dhl-key-NICHT-ECHT" not in json.dumps(described)

    # Lauf mit der neuen Version (Testmodus aus der alten Konfiguration – kein Netzwerk)
    assert _backend(lb, "run", "--force").returncode == 0
    state = json.loads((_dirs(lb, "data") / "state.json").read_text())
    [shipment] = state["shipments"]
    assert shipment["id"] == "dhl:00340434000000000001" and shipment["description"] == "Altbestand"
    assert "health" in state["providers"]["dhl"]


OLD_CREDENTIALS_020 = {
    "rest": {"token": "token-aus-0.2.0"}, "mqtt": {"password": "mqtt-NICHT-ECHT"},
    "email": {"password": "imap-NICHT-ECHT"},
    "providers": {"dhl": {"api_key": "dhl-key-NICHT-ECHT"},
                  "ups": {"client_id": "ups-id-NICHT-ECHT", "client_secret": "ups-secret-NICHT-ECHT"}},
}
OLD_SETTINGS_020 = {
    "general": {"interval_minutes": 20, "keep_delivered_days": 2, "max_age_days": 40, "mock_mode": False,
                "loglevel": "info"},
    "mqtt": {"enabled": True, "use_system_broker": False, "host": "192.0.2.10", "port": 1884, "user": "lox",
             "base_topic": "pakete", "retain": True, "slots": 7},
    "rest": {"enabled": True, "require_token": True},
    "email": {"enabled": True, "source": "imap", "host": "imap.example.invalid", "port": 143, "security": "starttls",
              "user": "max@example.invalid", "folder": "INBOX, Pakete", "lookback_days": 21,
              "mark_processed": True, "eml_dir": ""},
    "providers": {"dhl": {"enabled": True, "language": "de", "recipient_postal_code": "12345",
                          "check_interval_minutes": 90, "daily_limit": 200},
                  "ups": {"enabled": True, "environment": "test", "language": "en"},
                  "hermes": {"enabled": False}, "amazon": {"enabled": True, "sender_domains": "amazon.de, amazon.at"},
                  "fedex": {"enabled": True}},
}
OLD_DATA_020 = {
    "tracked.json": [{"provider": "gls", "tracking_number": "123456789012", "description": "Manuell GLS"},
                     {"provider": "ups", "tracking_number": "1Z999AA10123456784", "description": ""}],
    "provider_state.json": {
        "dhl": {"usage": {"day": "2026-10-01", "count": 42}, "last_checked": {"00340434000000000001": "x"}},
        "_imap": {"folders": {"INBOX": {"uidvalidity": "7", "last_uid": 1234}}},
        "_health": {"email": {"last_success": "2026-10-01T10:00:00+00:00"}},
    },
    "state.json": {"mock_mode": False, "last_full_success": "2026-10-01T10:00:00+00:00", "shipments": [
        {"provider": "amazon", "tracking_number": "TBA000000000003", "status": "in_transit",
         "description": "Buch XY", "reference": "302-0000000-0000003", "origins": ["email"],
         "last_update": "2026-10-01T08:00:00+00:00"}]},
}


def test_upgrade_from_0_2_0_keeps_everything(tmp_path):
    """Upgrade 0.2.0 → aktuelle Version: alle Einstellungen, Zugangsdaten und Daten bleiben unverändert."""
    lb = tmp_path / "lb"
    (lb / "config" / "system").mkdir(parents=True)
    (lb / "config" / "system" / "general.json").write_text('{"Base": {}}')
    _copy_plugin(lb)
    config, data = _dirs(lb, "config"), _dirs(lb, "data")
    (config / "settings.json").write_text(json.dumps(OLD_SETTINGS_020))
    (config / "credentials.json").write_text(json.dumps(OLD_CREDENTIALS_020))
    (config / "credentials.json").chmod(0o600)
    for name, content in OLD_DATA_020.items():
        (data / name).write_text(json.dumps(content))
    tmpid = f"pttest{uuid.uuid4().hex[:8]}"

    _script("preupgrade.sh", lb, tmpid, "0.2.0")
    for kind in ("config", "data", "bin"):
        shutil.rmtree(_dirs(lb, kind))
    shutil.rmtree(lb / "webfrontend")
    _copy_plugin(lb)
    _script("postinstall.sh", lb, tmpid)
    _script("postupgrade.sh", lb, tmpid)
    assert not Path(f"/tmp/{tmpid}_upgrade").exists()

    assert json.loads((config / "settings.json").read_text()) == OLD_SETTINGS_020
    assert json.loads((config / "credentials.json").read_text()) == OLD_CREDENTIALS_020
    assert stat.S_IMODE((config / "credentials.json").stat().st_mode) == 0o600
    for name, content in OLD_DATA_020.items():
        assert json.loads((data / name).read_text()) == content, name

    described = json.loads(_backend(lb, "describe").stdout)
    assert described["version"] == __version__
    values = described["values"]
    assert values["email"]["security"] == "starttls" and values["email"]["folder"] == "INBOX, Pakete"
    assert values["providers.ups"]["environment"] == "test" and values["providers.hermes"]["enabled"] is False
    assert values["mqtt"]["base_topic"] == "pakete" and values["general"]["mock_mode"] is False
    assert all(described["secrets_set"][s][k] for s, k in (("email", "password"), ("providers.dhl", "api_key"),
                                                           ("providers.ups", "client_id"),
                                                           ("providers.ups", "client_secret")))
    dumped = json.dumps(described)
    assert not any(secret in dumped for secret in ("NICHT-ECHT",))
    # neue Hilfe-Seite und Anleitung sind mitinstalliert
    htmlauth = lb / "webfrontend" / "htmlauth" / "plugins" / FOLDER
    assert (htmlauth / "anleitung.html").is_file() and (htmlauth / "inc" / "page_help.php").is_file()


def test_fresh_install_and_uninstall(tmp_path):
    lb = tmp_path / "lb"
    (lb / "config" / "system").mkdir(parents=True)
    _copy_plugin(lb)
    _script("preinstall.sh", lb, "fresh")
    out = _script("postinstall.sh", lb, "fresh").stdout
    assert "<OK>" in out

    creds = _dirs(lb, "config") / "credentials.json"
    assert stat.S_IMODE(creds.stat().st_mode) == 0o600
    assert len(json.loads(creds.read_text())["rest"]["token"]) >= 24
    settings = json.loads((_dirs(lb, "config") / "settings.json").read_text())
    assert settings["general"]["mock_mode"] is True                     # Testmodus ab Werk

    cron = lb / "system" / "cron" / "cron.05min" / FOLDER
    assert "REPLACE" not in cron.read_text()
    assert _backend(lb, "run", "--force").returncode in (0, 1)          # 1 = MQTT ohne Broker
    assert (_dirs(lb, "data") / "state.json").exists()

    _script("uninstall/uninstall", lb, "fresh")
