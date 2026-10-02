"""E-Mail-Eingang für Paketankündigungen.

Die Quellen liefern anbieterneutrale `Mail`-Objekte; die Auswertung übernimmt
jeder Provider in `parse_email()`. Quellen: IMAP (sources/imap.py) oder ein
Ordner mit .eml-Dateien (Tests/Entwicklung). Mailinhalte werden nie geloggt.
"""
from __future__ import annotations

import email
import email.policy
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

from ..models import parse_ts

# Vorfilter: bekommt den From-Header, True = Mail ist für einen aktiven Anbieter relevant
SenderFilter = Callable[[str], bool]

MAX_MAIL_BYTES = 1_500_000


@dataclass(frozen=True)
class Mail:
    sender: str
    subject: str
    date: str  # ISO-Zeitstempel
    text: str  # Klartext; Link-Ziele aus HTML-Mails sind enthalten
    message_id: str = ""  # für die Duplikaterkennung


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "a":
            href = dict(attrs).get("href")
            if href:
                # Sendungsnummern stecken oft nur im Link (z.B. ?piececode=…)
                self.parts.append(f" {href} ")
        elif tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return unescape("".join(parser.parts))


def _body_text(msg: EmailMessage) -> str:
    """Text einer Mail; verträgt kaputte MIME-Strukturen und unbekannte Zeichensätze."""
    try:
        body = msg.get_body(preferencelist=("plain", "html"))
    except Exception:
        body = None
    parts = [body] if body is not None else [p for p in msg.walk() if p.get_content_maintype() == "text"]
    for part in parts:
        try:
            content = part.get_content()
        except Exception:  # z.B. LookupError bei unbekanntem Charset
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else str(payload)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")
        if not isinstance(content, str) or not content.strip():
            continue
        return html_to_text(content) if part.get_content_type() == "text/html" else content
    raw = msg.get_payload()  # letzter Rückfall, z.B. multipart ohne gültige Boundary
    return raw if isinstance(raw, str) else ""


def from_message(msg: EmailMessage) -> Mail:
    try:
        date = parsedate_to_datetime(str(msg["Date"])).isoformat()
    except (TypeError, ValueError, IndexError):
        date = ""
    return Mail(
        sender=str(msg.get("From") or ""),
        subject=str(msg.get("Subject") or ""),
        date=date,
        text=_body_text(msg),
        message_id=str(msg.get("Message-ID") or "").strip(),
    )


def from_bytes(raw: bytes) -> Mail:
    return from_message(email.message_from_bytes(raw, policy=email.policy.default))


class EmlDirectorySource:
    """Liest .eml-Dateien aus einem lokalen Ordner – für Tests und Entwicklung."""

    def __init__(self, directory: str, lookback_days: int, log: logging.Logger,
                 sender_filter: SenderFilter | None = None):
        self.directory = Path(directory)
        self.lookback = timedelta(days=lookback_days)
        self.log = log
        self.sender_filter = sender_filter

    def fetch(self) -> list[Mail]:
        if not self.directory.is_dir():
            raise OSError(f"Ordner {self.directory} nicht gefunden")
        cutoff = datetime.now(timezone.utc) - self.lookback
        mails = []
        for path in sorted(self.directory.glob("*.eml")):
            try:
                mail = from_bytes(path.read_bytes()[:MAX_MAIL_BYTES])
            except Exception:
                self.log.warning("E-Mail-Datei %s nicht lesbar – übersprungen", path.name)
                continue
            sent = parse_ts(mail.date)
            if sent and sent < cutoff:
                continue
            if self.sender_filter and not self.sender_filter(mail.sender):
                continue
            mails.append(mail)
        return mails


def make_source(settings: dict, log: logging.Logger, state: dict | None = None,
                sender_filter: SenderFilter | None = None):
    """Quelle laut Einstellungen oder None (E-Mail-Eingang aus)."""
    if not settings.get("enabled"):
        return None
    if settings.get("source") == "eml_dir":
        if not settings.get("eml_dir"):
            log.warning("E-Mail-Quelle 'eml_dir' gewählt, aber kein Ordner angegeben")
            return None
        return EmlDirectorySource(settings["eml_dir"], settings["lookback_days"], log, sender_filter)
    from .imap import ImapSource

    return ImapSource(settings, log, state if state is not None else {}, sender_filter)
