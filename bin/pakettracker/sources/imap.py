"""IMAP-Abruf von Versand- und Tracking-Mails.

Grundsätze:
- nur lesend: Ordner werden read-only geöffnet, Inhalte mit BODY.PEEK geholt
  (setzt kein \\Seen), es wird nie gelöscht oder verschoben
- optional („als verarbeitet markieren“): eigenes Schlüsselwort $Pakettracker
  per STORE – dafür wird der Ordner beschreibbar geöffnet
- nur neue Mails: je Ordner werden UIDVALIDITY und die höchste gesehene UID gemerkt
- nur relevante Mails: zuerst nur der From-Header, Inhalte nur von Absendern aktiver Anbieter
- Zugangsdaten und Mailinhalte werden nie geloggt
"""
from __future__ import annotations

import email
import email.policy
import imaplib
import logging
import re
import socket
import ssl
from datetime import date, timedelta
from typing import Any, Callable

from .mail import MAX_MAIL_BYTES, Mail, SenderFilter, from_bytes

TIMEOUT = 30
FETCH_BATCH = 100
PROCESSED_FLAG = "$Pakettracker"
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


class ImapSourceError(Exception):
    """Verständliche Fehlermeldung ohne Zugangsdaten."""


def encode_folder(name: str) -> str:
    """Ordnername als IMAP-String (modifiziertes UTF-7 nach RFC 3501, in Anführungszeichen)."""
    out, buffer = [], ""

    def flush() -> None:
        nonlocal buffer
        if buffer:
            import base64
            encoded = base64.b64encode(buffer.encode("utf-16-be")).decode().rstrip("=").replace("/", ",")
            out.append(f"&{encoded}-")
            buffer = ""

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buffer += ch
    flush()
    quoted = "".join(out).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{quoted}"'


def imap_date(day: date) -> str:
    return f"{day.day:02d}-{_MONTHS[day.month - 1]}-{day.year}"


def _describe(exc: BaseException) -> str:
    text = exc.args[0] if exc.args else exc.__class__.__name__
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return re.sub(r"\s+", " ", str(text))[:160]


class ImapSource:
    # Für Tests austauschbar: (host, port, security, ssl_context, timeout) -> IMAP-Verbindung
    FACTORY: Callable[..., Any] | None = None

    def __init__(self, settings: dict, log: logging.Logger, state: dict,
                 sender_filter: SenderFilter | None = None,
                 imap_factory: Callable[..., Any] | None = None):
        self.settings = settings
        self.log = log
        self.state = state  # {"folders": {name: {"uidvalidity": "...", "last_uid": n}}}
        self.sender_filter = sender_filter
        self._factory = imap_factory or type(self).FACTORY

    # --- Verbindung ----------------------------------------------------------

    def folders(self) -> list[str]:
        names = [f.strip() for f in str(self.settings.get("folder") or "").split(",")]
        return [f for f in names if f] or ["INBOX"]

    def _connect(self):
        host = str(self.settings.get("host") or "").strip()
        user = str(self.settings.get("user") or "").strip()
        password = str(self.settings.get("password") or "")
        port = int(self.settings.get("port") or 993)
        security = self.settings.get("security") or "ssl"
        if not host or not user or not password:
            raise ImapSourceError("IMAP-Server, Benutzer oder Passwort fehlen (Einstellungen → E-Mail-Eingang)")

        context = ssl.create_default_context()
        try:
            if self._factory is not None:
                conn = self._factory(host, port, security, context, TIMEOUT)
            elif security == "ssl":
                conn = imaplib.IMAP4_SSL(host, port, ssl_context=context, timeout=TIMEOUT)
            else:
                conn = imaplib.IMAP4(host, port, timeout=TIMEOUT)
                if security == "starttls":
                    conn.starttls(ssl_context=context)
        except (socket.timeout, TimeoutError):
            raise ImapSourceError(f"IMAP-Server {host}:{port} antwortet nicht (Zeitüberschreitung)") from None
        except ssl.SSLError as exc:
            raise ImapSourceError(f"TLS-Fehler bei {host}:{port}: {_describe(exc)}") from None
        except (OSError, imaplib.IMAP4.error) as exc:
            raise ImapSourceError(f"IMAP-Server {host}:{port} nicht erreichbar: {_describe(exc)}") from None

        try:
            conn.login(user, password)
        except imaplib.IMAP4.error:
            self._logout(conn)
            raise ImapSourceError("IMAP-Anmeldung fehlgeschlagen – Benutzer/Passwort prüfen") from None
        except (OSError, socket.timeout) as exc:
            self._logout(conn)
            raise ImapSourceError(f"IMAP-Verbindung abgebrochen: {_describe(exc)}") from None
        return conn

    @staticmethod
    def _logout(conn) -> None:
        try:
            conn.logout()
        except Exception:
            pass

    # --- Abruf ---------------------------------------------------------------

    def fetch(self) -> list[Mail]:
        conn = self._connect()
        mails: list[Mail] = []
        errors = []
        try:
            for folder in self.folders():
                try:
                    mails.extend(self._fetch_folder(conn, folder))
                except (ImapSourceError, imaplib.IMAP4.error, OSError) as exc:
                    errors.append(f"Ordner '{folder}': {_describe(exc)}")
        finally:
            self._logout(conn)
        if errors and not mails and len(errors) == len(self.folders()):
            raise ImapSourceError("; ".join(errors))
        for error in errors:
            self.log.warning("IMAP: %s", error)
        return mails

    def _select(self, conn, folder: str, readonly: bool) -> str:
        typ, _ = conn.select(encode_folder(folder), readonly=readonly)
        if typ != "OK":
            raise ImapSourceError("Ordner nicht gefunden oder nicht lesbar")
        _, data = conn.response("UIDVALIDITY")
        value = data[0] if data and data[0] else b""
        return value.decode() if isinstance(value, bytes) else str(value)

    def _search_since(self, conn) -> list[int]:
        since = date.today() - timedelta(days=int(self.settings.get("lookback_days") or 14))
        typ, data = conn.uid("SEARCH", None, "SINCE", imap_date(since))
        if typ != "OK":
            raise ImapSourceError("Suche im Ordner fehlgeschlagen")
        return sorted(int(x) for x in (data[0] or b"").split()) if data else []

    def _relevant(self, conn, uids: list[int]) -> list[int]:
        """Filtert per From-Header und Größe, ohne Mailinhalte zu laden."""
        relevant = []
        for start in range(0, len(uids), FETCH_BATCH):
            batch = ",".join(str(u) for u in uids[start:start + FETCH_BATCH])
            typ, data = conn.uid("FETCH", batch, "(UID RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM)])")
            if typ != "OK":
                raise ImapSourceError("Kopfzeilen konnten nicht gelesen werden")
            for item in data or []:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                meta = item[0].decode(errors="replace") if isinstance(item[0], bytes) else str(item[0])
                uid_match = re.search(r"UID (\d+)", meta)
                size_match = re.search(r"RFC822\.SIZE (\d+)", meta)
                if not uid_match:
                    continue
                if size_match and int(size_match.group(1)) > MAX_MAIL_BYTES:
                    continue
                header = email.message_from_bytes(item[1] or b"", policy=email.policy.default)
                sender = str(header.get("From") or "")
                if self.sender_filter is None or self.sender_filter(sender):
                    relevant.append(int(uid_match.group(1)))
        return relevant

    def _fetch_folder(self, conn, folder: str) -> list[Mail]:
        mark = bool(self.settings.get("mark_processed"))
        uidvalidity = self._select(conn, folder, readonly=not mark)
        folders = self.state.setdefault("folders", {})
        known = folders.get(folder) if isinstance(folders.get(folder), dict) else {}
        last_uid = int(known.get("last_uid") or 0) if known.get("uidvalidity") == uidvalidity else 0

        uids = self._search_since(conn)
        new = [u for u in uids if u > last_uid]
        mails = []
        for uid in self._relevant(conn, new):
            typ, data = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
            raw = next((item[1] for item in data or [] if isinstance(item, tuple) and len(item) > 1), None)
            if typ != "OK" or not raw:
                self.log.warning("IMAP: Mail (UID %s) konnte nicht geladen werden – übersprungen", uid)
                continue
            try:
                mails.append(from_bytes(raw[:MAX_MAIL_BYTES]))
            except Exception:
                self.log.warning("IMAP: Mail (UID %s) ist fehlerhaft – übersprungen", uid)
                continue
            if mark:
                try:
                    conn.uid("STORE", str(uid), "+FLAGS.SILENT", f"({PROCESSED_FLAG})")
                except (imaplib.IMAP4.error, OSError):
                    self.log.info("IMAP: Markierung nicht möglich (Server erlaubt keine eigenen Flags)")
                    mark = False
        folders[folder] = {"uidvalidity": uidvalidity, "last_uid": max([last_uid, *uids])}
        self.log.info("IMAP: Ordner '%s': %d neue Mails, davon %d relevant und gelesen", folder, len(new), len(mails))
        return mails

    # --- Verbindungstest -----------------------------------------------------

    def test(self) -> str:
        """Anmeldung + Zählung relevanter Mails je Ordner; verändert nichts."""
        conn = self._connect()
        lines = []
        try:
            for folder in self.folders():
                try:
                    self._select(conn, folder, readonly=True)
                    uids = self._search_since(conn)
                    relevant = self._relevant(conn, uids)
                    lines.append(f"Ordner '{folder}': {len(uids)} Mails im Zeitraum, {len(relevant)} von Paketdiensten")
                except (ImapSourceError, imaplib.IMAP4.error, OSError) as exc:
                    lines.append(f"Ordner '{folder}': Fehler – {_describe(exc)}")
        finally:
            self._logout(conn)
        return "Anmeldung erfolgreich. " + "; ".join(lines)
