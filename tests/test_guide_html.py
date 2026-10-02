"""Ausführliche Anleitung als HTML im Plugin und Versionskonsistenz."""
import html.parser
import re
import sys
from pathlib import Path

from pakettracker import __version__

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import build_release  # noqa: E402
import md_to_html  # noqa: E402

GUIDE_HTML = REPO / "webfrontend" / "htmlauth" / "anleitung.html"


class _Collector(html.parser.HTMLParser):
    VOID = {"meta", "br", "hr", "img", "input", "link"}

    def __init__(self):
        super().__init__()
        self.ids, self.hrefs, self.stack, self.errors, self.tags = set(), [], [], [], {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags[tag] = self.tags.get(tag, 0) + 1
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a":
            self.hrefs.append(attrs.get("href", ""))
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.errors.append(tag)


def _parsed():
    collector = _Collector()
    collector.feed(GUIDE_HTML.read_text(encoding="utf-8"))
    return collector


def test_installed_guide_is_up_to_date():
    expected = md_to_html.convert((REPO / "docs" / "ANLEITUNG_DE.md").read_text(encoding="utf-8"))
    assert GUIDE_HTML.read_text(encoding="utf-8") == expected, "tools/md_to_html.py ausführen"


def test_guide_html_is_well_formed_and_complete():
    md = (REPO / "docs" / "ANLEITUNG_DE.md").read_text(encoding="utf-8")
    page = _parsed()
    assert page.errors == [] and page.stack == []
    assert sum(page.tags.get(f"h{i}", 0) for i in range(1, 7)) == len(re.findall(r"(?m)^#{1,6} ", md))
    assert page.tags.get("table", 0) == len(re.findall(r"(?m)^\|[\s:|-]+\|\s*$", md))
    text = re.sub(r"<pre>.*?</pre>", "", GUIDE_HTML.read_text(encoding="utf-8"), flags=re.S)
    assert not any(token in text for token in ("**", "](", "```", "\x00"))
    assert f"Version {__version__}" in text


def test_guide_links_work_on_loxberry():
    page = _parsed()
    for href in page.hrefs:
        if href.startswith("#"):
            assert href[1:] in page.ids, href
        else:
            assert href == "index.php?page=help", href   # keine Links auf Projektdateien wie docs/…


def test_help_page_links_installed_guide():
    php = (REPO / "webfrontend" / "htmlauth" / "inc" / "page_help.php").read_text()
    assert 'href="anleitung.html"' in php and "HELP.OPEN_GUIDE" in php
    assert "webfrontend" in build_release.INCLUDE          # anleitung.html liegt darin → wird installiert
    for lang in ("de", "en"):
        ini = (REPO / "templates" / "lang" / f"language_{lang}.ini").read_text()
        assert "OPEN_GUIDE=" in ini
        assert "docs/" not in (REPO / "templates" / lang / "help_page.html").read_text()
    assert 'OPEN_GUIDE="Ausführliche Anleitung öffnen"' in (REPO / "templates/lang/language_de.ini").read_text()


def test_versions_consistent():
    assert build_release.version_problems(__version__) == []
    assert f"VERSION={__version__}" in (REPO / "plugin.cfg").read_text()
    cfg = (REPO / "plugin.cfg").read_text()
    assert "NAME=ToRe90" in cfg and "EMAIL=existenzz-cod2@gmx.de" in cfg
