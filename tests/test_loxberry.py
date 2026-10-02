import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

from pakettracker import loxberry
from pakettracker.outputs import mqtt

BIN = Path(__file__).resolve().parents[1] / "bin"
log = logging.getLogger("test")


def test_paths_derived_from_installation(tmp_path):
    """Im LoxBerry-Layout ergeben sich alle Pfade aus dem Installationsort (kein /opt/loxberry im Code)."""
    plugin_bin = tmp_path / "bin" / "plugins" / "pakettracker_abc"
    shutil.copytree(BIN, plugin_bin, ignore=shutil.ignore_patterns("__pycache__"))
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from pakettracker.loxberry import get_paths; "
            "p = get_paths(); print(p.config); print(p.data)")
    out = subprocess.run([sys.executable, "-c", code, str(plugin_bin)], capture_output=True, text=True,
                         check=True, env={"PATH": "/usr/bin:/bin"}).stdout.split()
    assert out == [str(tmp_path / "config/plugins/pakettracker_abc"), str(tmp_path / "data/plugins/pakettracker_abc")]


def test_system_broker_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("LBSCONFIG", str(tmp_path))
    assert loxberry.system_broker() is None  # keine general.json
    (tmp_path / "general.json").write_text(json.dumps({"Base": {}}))
    assert loxberry.system_broker() is None  # kein Mqtt-Abschnitt
    (tmp_path / "general.json").write_text(json.dumps({"Mqtt": {"Brokerhost": "localhost", "Brokerport": "1883",
                                                                 "Brokeruser": "loxberry", "Brokerpass": "x"}}))
    assert loxberry.system_broker() == {"host": "localhost", "port": 1883, "user": "loxberry", "password": "x"}


def test_mqtt_skipped_without_broker(tmp_path, monkeypatch):
    monkeypatch.setenv("LBSCONFIG", str(tmp_path))
    assert mqtt._connection({"use_system_broker": True}, log) is None
    assert mqtt._connection({"use_system_broker": False, "host": ""}, log) is None
