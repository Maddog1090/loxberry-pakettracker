"""Gemeinsame Basis für Anbieter mit offizieller Tracking-API (DHL, UPS, …).

Enthält, was jede API-Anbindung braucht:
- Drosselung: Mindestabstand zwischen Abfragen, max. Abfragen pro Lauf,
  Tageskontingent, Mindestabstand je Sendung, Pause nach HTTP 429
- HTTP mit Timeout und Übersetzung von Netzwerkfehlern in ProviderError
- Schwärzen aller Geheimnisse in Fehlermeldungen
Der Zustand liegt in `self.state` (data/provider_state.json) und übersteht Neustarts.
"""
from __future__ import annotations

import http.client
import json
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import ClassVar

from ..models import Shipment, local_today, now_iso, parse_ts
from ..schema import Field
from .base import Provider, ProviderError


def throttle_fields(interval_default: int, limit_default: int, limit_help: str) -> tuple[Field, ...]:
    return (
        Field("check_interval_minutes", "Mindestabstand je Sendung (Minuten)", "int", interval_default,
              min=15, max=1440, help="Schont das Kontingent; zugestellte Sendungen werden nicht mehr abgefragt."),
        Field("daily_limit", "Max. API-Abfragen pro Tag", "int", limit_default, min=1, max=100000, help=limit_help),
    )


class ApiProvider(Provider):
    live_tracking: ClassVar[bool] = True
    TIMEOUT: ClassVar[float] = 15          # Sekunden je Verbindungs-/Leseschritt
    MIN_SPACING: ClassVar[float] = 5.0     # Sekunden zwischen zwei Abfragen
    MAX_PER_RUN: ClassVar[int] = 10        # begrenzt die Laufzeit; weitere Sendungen im nächsten Lauf
    RATE_LIMIT_PAUSE: ClassVar[int] = 30   # Minuten Pause nach HTTP 429 ohne Retry-After
    MAX_RESPONSE_BYTES: ClassVar[int] = 2_000_000

    def __init__(self, settings: dict, mock: bool, log: logging.Logger, state: dict | None = None):
        super().__init__(settings, mock, log, state)
        self._calls_this_run = 0
        # Austauschbar für Tests
        self._urlopen = urllib.request.urlopen
        self._sleep = time.sleep
        self._clock = time.time

    # --- Drosselung --------------------------------------------------------

    def due(self, tracking_number: str) -> bool:
        last = parse_ts(self.state.get("last_checked", {}).get(tracking_number))
        interval = timedelta(minutes=self.settings.get("check_interval_minutes", 60))
        return last is None or datetime.now(timezone.utc) - last >= interval

    def forget(self, active_numbers: set[str]) -> None:
        checked = self.state.get("last_checked", {})
        for number in [n for n in checked if n not in active_numbers]:
            del checked[number]

    def _usage(self) -> dict:
        today = local_today().isoformat()
        usage = self.state.get("usage")
        if not isinstance(usage, dict) or usage.get("day") != today:
            usage = self.state["usage"] = {"day": today, "count": 0}
        return usage

    def _reserve_call(self) -> None:
        """Prüft Pause, Tages- und Laufkontingent, hält den Mindestabstand ein und zählt die Abfrage."""
        until = parse_ts(self.state.get("cooldown_until"))
        if until and datetime.now(timezone.utc) < until:
            raise ProviderError(f"Rate-Limit-Pause bis {until.astimezone():%H:%M} Uhr", abort=True, level=logging.INFO)
        usage = self._usage()
        limit = self.settings.get("daily_limit", 250)
        if usage["count"] >= limit:
            raise ProviderError(f"Tageslimit von {limit} Abfragen erreicht – weiter ab morgen",
                                abort=True, level=logging.INFO)
        if self._calls_this_run >= self.MAX_PER_RUN:
            raise ProviderError(f"{self.MAX_PER_RUN} Abfragen in diesem Lauf erreicht – weitere Sendungen folgen im "
                                "nächsten Lauf", abort=True, level=logging.INFO)
        self._wait_spacing()
        self._calls_this_run += 1
        usage["count"] += 1

    def _wait_spacing(self) -> None:
        last = self.state.get("last_call_epoch")
        if isinstance(last, (int, float)):
            wait = self.MIN_SPACING - (self._clock() - last)
            if wait > 0:
                self._sleep(min(wait, self.MIN_SPACING))

    def _mark_checked(self, tracking_number: str) -> None:
        self.state.setdefault("last_checked", {})[tracking_number] = now_iso()

    def _rate_limited(self, exc: urllib.error.HTTPError, detail: str) -> ProviderError:
        pause = timedelta(minutes=self.RATE_LIMIT_PAUSE)
        retry_after = (exc.headers.get("Retry-After") or "").strip() if exc.headers else ""
        if retry_after.isdigit():
            pause = timedelta(seconds=min(int(retry_after), 86400))
        until = datetime.now(timezone.utc) + pause
        self.state["cooldown_until"] = until.isoformat(timespec="seconds")
        return ProviderError(f"{self.name}-Rate-Limit erreicht (HTTP 429){detail} – Pause bis "
                             f"{until.astimezone():%H:%M} Uhr", abort=True)

    # --- HTTP ----------------------------------------------------------------

    def _send(self, request: urllib.request.Request) -> bytes:
        """Führt den Request aus. HTTPError wird an den Aufrufer durchgereicht."""
        try:
            with self._urlopen(request, timeout=self.TIMEOUT) as response:
                return response.read(self.MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError:
            raise
        except (TimeoutError, socket.timeout):
            raise ProviderError(f"{self.name} antwortet nicht (Zeitüberschreitung nach {self.TIMEOUT:g} s)",
                                abort=True) from None
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, (TimeoutError, socket.timeout)):
                raise ProviderError(f"{self.name} antwortet nicht (Zeitüberschreitung nach {self.TIMEOUT:g} s)",
                                    abort=True) from None
            raise ProviderError(f"{self.name} nicht erreichbar: {exc.reason}", abort=True) from None
        except (http.client.HTTPException, OSError) as exc:
            raise ProviderError(f"Verbindung zu {self.name} fehlgeschlagen: {exc.__class__.__name__}",
                                abort=True) from None
        finally:
            self.state["last_call_epoch"] = self._clock()

    @staticmethod
    def _read_json_error(exc: urllib.error.HTTPError) -> object:
        try:
            return json.loads(exc.read(4096).decode("utf-8"))
        except Exception:
            return None

    @staticmethod
    def _short(text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()[:160]
        return f" ({text})" if text else ""

    @staticmethod
    def _load_json(body: bytes) -> object:
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None

    # --- Geheimnisse ---------------------------------------------------------

    def _secrets(self) -> list[str]:
        values = [str(self.settings.get(f.key) or "") for f in self.settings_schema if f.secret]
        return [v for v in values if len(v) >= 4]

    def _redact(self, exc: ProviderError) -> ProviderError:
        message = str(exc)
        for secret in self._secrets():
            message = message.replace(secret, "***")
        if message == str(exc):
            return exc
        return ProviderError(message, abort=exc.abort, level=exc.level)

    def _missing_credentials(self) -> str:
        labels = [f.label.split(" (")[0] for f in self.settings_schema if f.key in self.required_secrets]
        return f"{self.name}: {' / '.join(labels)} nicht hinterlegt (Einstellungen → {self.name})"

    def fetch(self, tracking_number: str) -> Shipment:
        if self.credentials_status() == "missing":
            raise ProviderError(f"{self._missing_credentials()} – keine Live-Abfrage (nur E-Mail, falls eingerichtet)",
                                abort=True, level=logging.INFO)
        try:
            return self._fetch(tracking_number)
        except ProviderError as exc:
            raise self._redact(exc) from None

    def test_connection(self) -> str:
        if self.credentials_status() == "missing":
            raise ProviderError(self._missing_credentials())
        try:
            return self._test()
        except ProviderError as exc:
            raise self._redact(exc) from None

    def _fetch(self, tracking_number: str) -> Shipment:
        raise NotImplementedError

    def _test(self) -> str:
        raise ProviderError(f"{self.name}: kein Verbindungstest verfügbar")
