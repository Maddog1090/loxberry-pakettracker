import json
import stat

from pakettracker import config


def test_init_creates_private_credentials_with_token(plugin_root):
    mode = stat.S_IMODE(plugin_root.credentials_file.stat().st_mode)
    assert mode == 0o600
    creds = json.loads(plugin_root.credentials_file.read_text())
    assert len(creds["rest"]["token"]) >= 24


def test_init_keeps_existing_token(plugin_root):
    token = json.loads(plugin_root.credentials_file.read_text())["rest"]["token"]
    config.init(plugin_root)
    assert json.loads(plugin_root.credentials_file.read_text())["rest"]["token"] == token


def test_secrets_never_in_settings_or_describe(plugin_root):
    creds = json.loads(plugin_root.credentials_file.read_text())
    creds["providers"] = {"dhl": {"api_key": "geheim"}}
    plugin_root.credentials_file.write_text(json.dumps(creds))

    assert "api_key" not in json.dumps(config.defaults())
    described = config.describe(plugin_root)
    assert "geheim" not in json.dumps(described)
    assert described["secrets_set"]["providers.dhl"]["api_key"] is True
    assert config.load(plugin_root).get("providers.dhl", "api_key") == "geheim"


def test_values_are_coerced_and_clamped(plugin_root):
    plugin_root.settings_file.write_text(json.dumps({
        "general": {"interval_minutes": "1", "loglevel": "verbose", "mock_mode": "0"},
        "mqtt": [],  # kaputter Abschnitt → Defaults
    }))
    cfg = config.load(plugin_root)
    assert cfg.get("general", "interval_minutes") == 5
    assert cfg.get("general", "loglevel") == "info"
    assert cfg.get("general", "mock_mode") is False
    assert cfg.get("mqtt", "base_topic") == "pakettracker"


def test_providers_are_discovered():
    ids = [s.id for s in config.all_sections()]
    assert "providers.dhl" in ids and "providers.amazon" in ids
