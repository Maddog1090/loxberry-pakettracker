#!/usr/bin/env python3
"""Wandelt docs/ANLEITUNG_DE.md in eine eigenständige HTML-Seite für den LoxBerry um.

  python3 tools/md_to_html.py        → webfrontend/htmlauth/anleitung.html

Unterstützt genau den Markdown-Umfang der Anleitung (ohne externe Bibliotheken):
Überschriften (mit GitHub-kompatiblen Sprungmarken), Absätze, verschachtelte
Listen, Tabellen, Codeblöcke, Zitate, Trennlinien, `Code`, **fett**, *kursiv*, Links.
tools/build_release.py ruft die Umwandlung vor jedem Release automatisch auf.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "ANLEITUNG_DE.md"
TARGET = ROOT / "webfrontend" / "htmlauth" / "anleitung.html"

_LIST = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
_FENCE = re.compile(r"^\s*```")


# --- Inline ------------------------------------------------------------------

def slugify(text: str) -> str:
    """Sprungmarke wie bei GitHub: Kleinbuchstaben, Satzzeichen weg, Leerzeichen → '-'."""
    text = re.sub(r"[`*]", "", text).strip().lower()
    return re.sub(r"[^\w\- ]", "", text).replace(" ", "-")


def inline(text: str) -> str:
    # Code-Abschnitte zuerst durch Platzhalter ersetzen, damit **fett** auch um `Code` herum funktioniert
    codes: list[str] = []

    def stash(m: re.Match) -> str:
        codes.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]*)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)",
                  lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)([^*]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


def split_row(line: str) -> list[str]:
    """Tabellenzeile in Zellen zerlegen; '|' innerhalb von `Code` zählt nicht."""
    cells, current, in_code = [], "", False
    for ch in line.strip().strip("|"):
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(current.strip())
            current = ""
        else:
            current += ch
    cells.append(current.strip())
    return cells


# --- Blöcke ------------------------------------------------------------------

class Renderer:
    def __init__(self) -> None:
        self.slugs: dict[str, int] = {}

    def heading(self, level: int, text: str) -> str:
        slug = slugify(text)
        count = self.slugs.get(slug, 0)
        self.slugs[slug] = count + 1
        if count:
            slug = f"{slug}-{count}"
        top = ' <a class="top" href="#top" title="nach oben">↑</a>' if level == 2 else ""
        return f'<h{level} id="{slug}">{inline(text)}{top}</h{level}>'

    def blocks(self, lines: list[str], tight: bool = False) -> str:
        out: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
                continue

            if _FENCE.match(line):
                indent = len(line) - len(line.lstrip())
                lang = line.strip()[3:].strip()
                code = []
                i += 1
                while i < len(lines) and not _FENCE.match(lines[i]):
                    code.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                    i += 1
                i += 1
                cls = f' class="language-{html.escape(lang)}"' if lang else ""
                out.append(f"<pre><code{cls}>{html.escape(chr(10).join(code))}</code></pre>")
                continue

            if m := _HEADING.match(line):
                out.append(self.heading(len(m.group(1)), m.group(2)))
                i += 1
                continue

            if re.fullmatch(r"\s*(-{3,}|\*{3,})\s*", line):
                out.append("<hr>")
                i += 1
                continue

            if line.lstrip().startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*",
                                                                                      lines[i + 1]):
                header = split_row(line)
                i += 2
                rows = []
                while i < len(lines) and lines[i].lstrip().startswith("|"):
                    rows.append(split_row(lines[i]))
                    i += 1
                head = "".join(f"<th>{inline(c)}</th>" for c in header)
                body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows)
                out.append(f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
                continue

            if line.lstrip().startswith(">"):
                quote = []
                while i < len(lines) and lines[i].lstrip().startswith(">"):
                    quote.append(re.sub(r"^\s*>\s?", "", lines[i]))
                    i += 1
                out.append(f"<blockquote>{self.blocks(quote)}</blockquote>")
                continue

            if _LIST.match(line):
                block, i = self._collect_list(lines, i)
                out.append(self._list(block))
                continue

            para = []
            while i < len(lines) and lines[i].strip() and not self._starts_block(lines, i):
                para.append(lines[i].strip())
                i += 1
            text = inline(" ".join(para))
            out.append(text if tight else f"<p>{text}</p>")
        return "\n".join(out)

    @staticmethod
    def _starts_block(lines: list[str], i: int) -> bool:
        line = lines[i]
        return bool(_FENCE.match(line) or _HEADING.match(line) or _LIST.match(line)
                    or line.lstrip().startswith((">", "|")) or re.fullmatch(r"\s*-{3,}\s*", line))

    @staticmethod
    def _collect_list(lines: list[str], i: int) -> tuple[list[str], int]:
        base = len(lines[i]) - len(lines[i].lstrip())
        block = []
        while i < len(lines):
            line = lines[i]
            indent = len(line) - len(line.lstrip())
            if not line.strip():
                nxt = next((l for l in lines[i + 1:] if l.strip()), "")
                nxt_indent = len(nxt) - len(nxt.lstrip())
                if nxt and (nxt_indent > base or (nxt_indent == base and _LIST.match(nxt))):
                    block.append(line)
                    i += 1
                    continue
                break
            if indent < base or (indent == base and not _LIST.match(line)):
                break
            block.append(line)
            i += 1
        return block, i

    def _list(self, block: list[str]) -> str:
        first = _LIST.match(block[0])
        base = len(first.group(1))
        ordered = first.group(2)[0].isdigit()
        items: list[list[str]] = []
        offset = 0
        for line in block:
            m = _LIST.match(line)
            if m and len(m.group(1)) == base:
                offset = len(line) - len(m.group(3))
                items.append([m.group(3)])
            else:
                strip = min(offset, len(line) - len(line.lstrip()))
                items[-1].append(line[strip:])
        tag = "ol" if ordered else "ul"
        start = int(first.group(2)[:-1]) if ordered else 1
        attrs = f' start="{start}"' if ordered and start != 1 else ""
        body = "".join(f"<li>{self.blocks(item, tight=True)}</li>" for item in items)
        return f"<{tag}{attrs}>{body}</{tag}>"


# --- Seite -------------------------------------------------------------------

CSS = """
:root { --bg:#ffffff; --fg:#1d1f21; --muted:#5f6368; --line:#d9dce0; --code:#f3f4f6; --accent:#6dac20; --head:#f7f8fa; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16181b; --fg:#e6e6e6; --muted:#a0a4a8; --line:#3a3e44; --code:#24272c; --accent:#8fd14f; --head:#1e2125; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
header.bar { position:sticky; top:0; background:var(--accent); color:#fff; padding:10px 16px; display:flex; gap:16px; align-items:center; z-index:2; }
header.bar a { color:#fff; text-decoration:none; font-weight:600; }
main { max-width:960px; margin:0 auto; padding:16px 16px 64px; }
h1 { font-size:1.9em; margin:.6em 0 .3em; }
h2 { font-size:1.45em; margin:2em 0 .6em; padding-bottom:.25em; border-bottom:2px solid var(--line); }
h3 { font-size:1.15em; margin:1.5em 0 .5em; }
a { color:var(--accent); }
a.top { font-size:.7em; text-decoration:none; color:var(--muted); margin-left:.4em; }
code { background:var(--code); padding:.1em .35em; border-radius:4px; font-size:.92em; font-family:ui-monospace, Menlo, Consolas, monospace; }
pre { background:var(--code); padding:12px 14px; border-radius:6px; overflow-x:auto; }
pre code { background:none; padding:0; }
.table { overflow-x:auto; margin:1em 0; }
table { border-collapse:collapse; width:100%; font-size:.95em; }
th, td { border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:top; }
th { background:var(--head); }
blockquote { margin:1em 0; padding:.6em 1em; border-left:4px solid var(--accent); background:var(--head); }
blockquote p { margin:.2em 0; }
hr { border:0; border-top:1px solid var(--line); margin:2em 0; }
li { margin:.2em 0; }
@media print { header.bar, a.top { display:none; } body { font-size:12pt; } }
"""


def convert(markdown: str) -> str:
    body = Renderer().blocks(markdown.splitlines())
    title = next((m.group(1) for m in (re.match(r"#\s+(.*)", l) for l in markdown.splitlines()) if m),
                 "Benutzeranleitung")
    return f"""<!DOCTYPE html>
<!-- Automatisch erzeugt aus docs/ANLEITUNG_DE.md (tools/md_to_html.py) – bitte nicht von Hand bearbeiten. -->
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{CSS}</style>
</head>
<body id="top">
<header class="bar"><a href="index.php?page=help">← Zurück zum Plugin</a><span>{html.escape(title)}</span></header>
<main>
{body}
</main>
</body>
</html>
"""


def build(source: Path = SOURCE, target: Path = TARGET) -> Path:
    target.write_text(convert(source.read_text(encoding="utf-8")), encoding="utf-8")
    return target


if __name__ == "__main__":
    print(build())
    sys.exit(0)
