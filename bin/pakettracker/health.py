"""Gesundheitszustand je Anbieter und für den E-Mail-Eingang.

Gespeichert in data/provider_state.json unter "_health":
  {"dhl": {"last_success": iso, "last_error": text, "last_error_at": iso}, "email": {...}}
provider_info() meldet die tatsächlich genutzte Datenquelle ("api", "email", "api+email", "none").
Fehlermeldungen enthalten nie Zugangsdaten oder Mailinhalte.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import parse_ts
from .providers.base import Provider

EMAIL = "email"


def _now() -> str:
    # Mikrosekunden: Erfolg und Fehler können in derselben Sekunde liegen
    return datetime.now(timezone.utc).isoformat()


class Health:
    def __init__(self, data: dict):
        self.data = data
        self.errors_this_run = 0

    def _entry(self, key: str) -> dict:
        entry = self.data.get(key)
        if not isinstance(entry, dict):
            entry = self.data[key] = {}
        return entry

    def success(self, key: str) -> None:
        self._entry(key)["last_success"] = _now()

    def failure(self, key: str, message: str) -> None:
        entry = self._entry(key)
        entry["last_error"] = str(message)[:200]
        entry["last_error_at"] = _now()
        self.errors_this_run += 1

    def last_success(self, key: str) -> str:
        return self._entry(key).get("last_success", "")

    def current_error(self, key: str) -> str:
        """Letzter Fehler, sofern danach kein Erfolg mehr kam."""
        entry = self._entry(key)
        error_at, success_at = parse_ts(entry.get("last_error_at")), parse_ts(entry.get("last_success"))
        if error_at and (success_at is None or error_at > success_at):
            return entry.get("last_error", "")
        return ""

    def email_info(self, enabled: bool) -> dict:
        return {"enabled": enabled, "last_success": self.last_success(EMAIL), "error": self.current_error(EMAIL)}

    def provider_info(self, provider: Provider, email_enabled: bool) -> dict:
        """Zusatzfelder für snapshot["providers"][id] (Oberfläche, MQTT, REST)."""
        uses_email = email_enabled and bool(provider.email_domains)
        successes = [self.last_success(provider.id)] if provider.live_tracking else []
        if uses_email:
            successes.append(self.last_success(EMAIL))
        last_success = max((s for s in successes if s), key=lambda s: parse_ts(s), default="")
        error = self.current_error(provider.id) or (self.current_error(EMAIL) if uses_email else "")
        credentials = provider.credentials_status()
        live = provider.live_tracking and credentials != "missing"
        if error:
            health = "error"
        elif not uses_email and (not provider.live_tracking or credentials == "missing"):
            health = "no_source"  # weder API-Zugang noch E-Mail-Eingang
        elif credentials == "missing":
            health = "email_only"
        elif last_success:
            health = "ok"
        else:
            health = "idle"
        # Tatsächlich genutzte Quelle: DHL mit API-Key und ohne E-Mail-Eingang → "api"
        source = ("api+email" if uses_email else "api") if live else ("email" if uses_email else "none")
        return {
            "source": source,
            "live": live,
            "live_last_success": self.last_success(provider.id) if provider.live_tracking else "",
            "live_error": self.current_error(provider.id) if provider.live_tracking else "",
            "credentials": credentials,
            "last_success": last_success,
            "error": error,
            "health": health,
        }
