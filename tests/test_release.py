"""Veröffentlichung: Auto-Update-Konfiguration, Projektdateien, keine privaten Daten in Doku/Paket."""
import configparser
import sys
from pathlib import Path

from pakettracker import __version__

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import build_release  # noqa: E402


def _cfg(name: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(REPO / name, encoding="utf-8")
    return cfg


def test_plugin_cfg_autoupdate_matches_repo():
    assert build_release.autoupdate_problems(_cfg("plugin.cfg"), __version__) == []


def test_release_cfgs_point_to_current_release():
    urls = build_release.release_urls(__version__)
    for name in ("release.cfg", "prerelease.cfg"):
        section = _cfg(name)["AUTOUPDATE"]
        assert section["VERSION"] == __version__, name
        assert section["ARCHIVEURL"] == urls["archive"], name
        assert section["INFOURL"] == urls["info"], name
    assert urls["archive"].endswith(f"/v{__version__}/pakettracker-{__version__}.zip")


def test_project_files_present():
    for name in ("LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "README.md",
                 "docs/ANLEITUNG_DE.md", "docs/RELEASE_LOXBERRY.md", "docs/ARCHITECTURE.md"):
        assert (REPO / name).is_file(), name
    assert "MIT License" in (REPO / "LICENSE").read_text() and "ToRe90" in (REPO / "LICENSE").read_text()
    assert build_release.changelog_problems(__version__) == []


def test_no_private_data_in_package_and_docs():
    files = build_release.collect()
    docs = [REPO / n for n in ("README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md")] \
        + sorted((REPO / "docs").rglob("*.md"))
    assert build_release.leak_problems(files + docs) == []


def test_gitignore_keeps_secrets_and_builds_out():
    ignore = (REPO / ".gitignore").read_text()
    for pattern in ("credentials.json", "*.zip", "*.zip.sha256", "dev/", "log/", "__pycache__/"):
        assert pattern in ignore, pattern
