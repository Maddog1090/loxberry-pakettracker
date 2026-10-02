#!/usr/bin/env python3
"""Baut das installierbare LoxBerry-Plugin-ZIP.

  python3 tools/build_release.py

Erzeugt vorher die Anleitung webfrontend/htmlauth/anleitung.html aus
docs/ANLEITUNG_DE.md sowie release.cfg/prerelease.cfg (LoxBerry-Auto-Update) und prüft:
einheitliche Version (plugin.cfg, Python, README, Anleitung, CHANGELOG), Auto-Update-URLs
in plugin.cfg passend zu GITHUB_REPO, LF-Zeilenenden, UTF-8, keine fest codierten
/opt/loxberry-Pfade, keine Zugangsdaten/privaten Adressen/lokalen Pfade im Paket.
Setzt Rechte (Verzeichnisse 755, Dateien 644, Skripte 755) und legt plugin.cfg direkt
in den ZIP-Root.
Ergebnis: <projekt>/pakettracker-<VERSION>.zip und pakettracker-<VERSION>.zip.sha256
"""
from __future__ import annotations

import configparser
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import md_to_html  # noqa: E402

# GitHub-Repository für Auto-Updates und Support-Link – die EINZIGE Stelle, an der er gepflegt wird.
# Ändert sich das Repository, hier anpassen; der Build prüft plugin.cfg und erzeugt release.cfg.
GITHUB_REPO = "Maddog1090/loxberry-pakettracker"
GITHUB_BRANCH = "main"

# Was ins Paket gehört (alles andere – tests/, docs/, tools/, dev/ – bleibt draußen)
INCLUDE = ["plugin.cfg", "preinstall.sh", "postinstall.sh", "preupgrade.sh", "postupgrade.sh",
           "bin", "config", "cron", "dpkg", "icons", "templates", "uninstall", "webfrontend"]
EXECUTABLE = {"preinstall.sh", "postinstall.sh", "preupgrade.sh", "postupgrade.sh",
              "uninstall/uninstall", "cron/cron.05min", "bin/pakettracker.py"}
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache"}
FORBIDDEN_NAMES = {"credentials.json", "state.json", "tracked.json", "provider_state.json"}
BINARY_SUFFIXES = {".png"}
# Wie der LoxBerry-Installer (plugininstall.pl): Dokumentation darf Systempfade nennen
DOC_SUFFIXES = {".md", ".html", ".txt", ".dat", ".log"}


def collect() -> list[Path]:
    files = []
    for entry in INCLUDE:
        path = ROOT / entry
        if not path.exists():
            sys.exit(f"Fehlt: {entry}")
        candidates = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
        files += [p for p in candidates if not EXCLUDE_PARTS & set(p.relative_to(ROOT).parts)]
    return files


def check(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        rel = f.relative_to(ROOT).as_posix()
        if f.name in FORBIDDEN_NAMES:
            problems.append(f"{rel}: darf nicht ausgeliefert werden")
        if f.suffix in BINARY_SUFFIXES:
            continue
        data = f.read_bytes()
        if b"\r" in data:
            problems.append(f"{rel}: CR-Zeilenenden")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{rel}: kein UTF-8")
            continue
        if "/opt/loxberry" in text and f.suffix not in DOC_SUFFIXES:
            problems.append(f"{rel}: fest codierter Pfad /opt/loxberry")
        if rel in EXECUTABLE and not text.startswith("#!"):
            problems.append(f"{rel}: Shebang fehlt")
    return problems


# Inhalte, die nie in ein öffentliches Paket gehören
_LEAK_PATTERNS = {
    "private IP-Adresse": re.compile(r"\b(?:192\.168|10\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    "lokaler Home-Pfad": re.compile(r"/home/[a-z_][a-z0-9_-]*/|C:\\Users\\", re.I),
    "privater Schlüssel": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub-/API-Token": re.compile(r"\b(?:ghp|gho|github_pat|sk|xox[bp])_[A-Za-z0-9_]{16,}"),
    "fest gesetztes Geheimnis": re.compile(r"""(?i)\b(?:api_?key|password|passwd|secret|token)\b\s*[:=]\s*["'][^"'\s{}$<]{6,}["']"""),
}


def leak_problems(files: list[Path]) -> list[str]:
    problems = []
    for f in files:
        if f.suffix in BINARY_SUFFIXES:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for label, pattern in _LEAK_PATTERNS.items():
            if m := pattern.search(text):
                problems.append(f"{f.relative_to(ROOT)}: {label} gefunden ({m.group(0)[:40]})")
    return problems


def release_urls(version: str) -> dict[str, str]:
    base = f"https://github.com/{GITHUB_REPO}"
    raw = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}"
    return {
        "website": base,
        "releasecfg": f"{raw}/release.cfg",
        "prereleasecfg": f"{raw}/prerelease.cfg",
        "archive": f"{base}/releases/download/v{version}/pakettracker-{version}.zip",
        "info": f"{base}/releases/tag/v{version}",
    }


def autoupdate_problems(cfg: configparser.ConfigParser, version: str) -> list[str]:
    urls = release_urls(version)
    expected = {
        ("PLUGIN", "WEBSITE"): urls["website"],
        ("AUTOUPDATE", "AUTOMATIC_UPDATES"): "true",
        ("AUTOUPDATE", "RELEASECFG"): urls["releasecfg"],
        ("AUTOUPDATE", "PRERELEASECFG"): urls["prereleasecfg"],
        ("AUTHOR", "NAME"): "ToRe90",
        ("AUTHOR", "EMAIL"): "existenzz-cod2@gmx.de",
        ("PLUGIN", "NAME"): "pakettracker",
        ("PLUGIN", "FOLDER"): "pakettracker",
    }
    return [f"plugin.cfg: {sec}.{key} = {cfg.get(sec, key, fallback='?')!r}, erwartet {value!r}"
            for (sec, key), value in expected.items() if cfg.get(sec, key, fallback=None) != value]


def write_release_cfgs(version: str) -> None:
    """release.cfg/prerelease.cfg im Format von LoxBerry (sbin/pluginsupdate.pl, [AUTOUPDATE])."""
    urls = release_urls(version)
    for name, label in (("release.cfg", "Release"), ("prerelease.cfg", "Pre-Release")):
        (ROOT / name).write_text(
            "[AUTOUPDATE]\n"
            f"# {label}-Information für das LoxBerry-Auto-Update (Plugin Pakettracker).\n"
            "# Wird von tools/build_release.py erzeugt – nicht von Hand bearbeiten.\n"
            f"# LoxBerry lädt diese Datei über die URL aus plugin.cfg ({name.split('.')[0].upper()}CFG).\n"
            + ("# Ohne eigenes Pre-Release zeigt sie auf das aktuelle Release.\n" if name == "prerelease.cfg" else "")
            + f"VERSION={version}\n"
            f"ARCHIVEURL={urls['archive']}\n"
            f"INFOURL={urls['info']}\n",
            encoding="utf-8")


def changelog_problems(version: str) -> list[str]:
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists() or f"## [{version}]" not in changelog.read_text(encoding="utf-8"):
        return [f"CHANGELOG.md: kein Eintrag „## [{version}]“"]
    return []


def version_problems(version: str) -> list[str]:
    """Alle sichtbaren Versionsangaben müssen zu plugin.cfg passen."""
    sources = {
        "bin/pakettracker/__init__.py": r'__version__ = "([^"]+)"',
        "README.md": r"\*\*Version ([0-9.]+)\*\*",
        "docs/ANLEITUNG_DE.md": r"^Version ([0-9.]+) ·",
    }
    problems = []
    for rel, pattern in sources.items():
        m = re.search(pattern, (ROOT / rel).read_text(encoding="utf-8"), re.M)
        if not m or m.group(1) != version:
            problems.append(f"{rel}: Version {m.group(1) if m else '?'} statt {version}")
    return problems


def main() -> int:
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / "plugin.cfg", encoding="utf-8")
    version, name = cfg["PLUGIN"]["VERSION"], cfg["PLUGIN"]["NAME"]

    md_to_html.build()  # Anleitung für den LoxBerry immer aus der aktuellen Markdown-Datei
    files = collect()
    problems = (version_problems(version) + changelog_problems(version) + autoupdate_problems(cfg, version)
                + check(files) + leak_problems(files))
    if problems:
        print("\n".join(problems))
        return 1

    target = ROOT / f"{name}-{version}.zip"
    target.unlink(missing_ok=True)
    dirs = set()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            rel = f.relative_to(ROOT)
            for parent in list(rel.parents)[:-1]:
                dirs.add(parent.as_posix())
            mode = 0o755 if rel.as_posix() in EXECUTABLE else 0o644
            f.chmod(mode)
            info = zipfile.ZipInfo(rel.as_posix(), date_time=(2026, 10, 2, 0, 0, 0))
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, f.read_bytes())
        for d in sorted(dirs):
            info = zipfile.ZipInfo(d + "/", date_time=(2026, 10, 2, 0, 0, 0))
            info.external_attr = (0o040755 << 16) | 0x10
            zf.writestr(info, b"")
    write_release_cfgs(version)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    Path(f"{target}.sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
    print(f"{target} ({len(files)} Dateien, Version {version})")
    print(f"SHA-256 {digest}  → {target.name}.sha256")
    print(f"release.cfg/prerelease.cfg → {release_urls(version)['archive']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
