"""Beschreibung aller Einstellungen.

Aus diesem Schema erzeugt die PHP-Weboberfläche ihre Formulare (über
`pakettracker.py describe`). Felder mit `secret=True` landen in
credentials.json (0600) statt in settings.json und werden nie an den Browser
zurückgegeben – außer `reveal=True` ist gesetzt (nur für den REST-Token).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    type: str = "text"  # text | int | bool | select
    default: Any = ""
    secret: bool = False
    reveal: bool = False
    options: tuple[str, ...] = ()
    min: int | None = None
    max: int | None = None
    help: str = ""

    def coerce(self, raw: Any) -> Any:
        if self.type == "bool":
            return raw in (True, 1, "1", "true", "on", "yes")
        if self.type == "int":
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = int(self.default)
            if self.min is not None:
                value = max(self.min, value)
            if self.max is not None:
                value = min(self.max, value)
            return value
        if self.type == "select":
            return raw if raw in self.options else self.default
        return "" if raw is None else str(raw).strip()


@dataclass(frozen=True)
class Section:
    id: str  # z.B. "mqtt" oder "providers.dhl" (Pfad in den JSON-Dateien)
    title: str
    fields: tuple[Field, ...]
    meta: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "fields": [asdict(f) for f in self.fields],
            **dict(self.meta),
        }


CORE_SECTIONS: tuple[Section, ...] = (
    Section("general", "Allgemein", (
        Field("interval_minutes", "Abfrageintervall (Minuten)", "int", 15, min=5, max=1440,
              help="Der Cronjob läuft alle 5 Minuten; kleinere Werte sind nicht möglich."),
        Field("keep_delivered_days", "Zugestellte Sendungen behalten (Tage)", "int", 1, min=0, max=30,
              help="0 = nur am Tag der Zustellung anzeigen."),
        Field("max_age_days", "Sendungen ohne Aktualisierung entfernen nach (Tagen)", "int", 30, min=1, max=365),
        Field("mock_mode", "Testmodus (keine echten Anbieter-Abfragen)", "bool", True,
              help="Anbieter liefern simulierte Statuswerte. Zum Einrichten der Loxone-Anbindung gedacht."),
        Field("loglevel", "Loglevel", "select", "info", options=("debug", "info", "warning", "error")),
    )),
    Section("mqtt", "MQTT", (
        Field("enabled", "MQTT-Ausgabe aktiv", "bool", True),
        Field("use_system_broker", "Broker von LoxBerry verwenden", "bool", True,
              help="Nutzt die MQTT-Einstellungen aus LoxBerry. Die Felder darunter gelten nur, wenn dies aus ist."),
        Field("host", "Broker-Host", default="localhost"),
        Field("port", "Broker-Port", "int", 1883, min=1, max=65535),
        Field("user", "Benutzer"),
        Field("password", "Passwort", secret=True),
        Field("base_topic", "Basis-Topic", default="pakettracker",
              help="Bei Änderung die Subscription im LoxBerry MQTT Gateway anpassen."),
        Field("retain", "Retained senden", "bool", True,
              help="Der Broker speichert den letzten Wert. Leere Werte werden nach MQTT-Standard nicht gespeichert."),
        Field("slots", "Anzahl Slots für Loxone", "int", 5, min=0, max=20,
              help="Feste Topics slot/1 … slot/N mit den wichtigsten Sendungen."),
    )),
    Section("rest", "REST / HTTP", (
        Field("enabled", "REST-Schnittstelle aktiv", "bool", True),
        Field("require_token", "Token erforderlich", "bool", True),
        Field("token", "Zugriffs-Token", secret=True, reveal=True,
              help="Wird bei der Installation zufällig erzeugt. Als ?token=… an die URL anhängen."),
    )),
    Section("email", "E-Mail-Eingang (Paketankündigungen)", (
        Field("enabled", "E-Mails auswerten", "bool", False,
              help="Versand- und Zustellmails (Amazon, DHL, Hermes, DPD, GLS, UPS …) werden nach Sendungen "
                   "durchsucht. Mails werden nur gelesen, nie gelöscht oder verschoben."),
        Field("source", "Quelle", "select", "imap", options=("imap", "eml_dir"),
              help="eml_dir = lokaler Ordner mit .eml-Dateien (zum Testen)."),
        Field("host", "IMAP-Server", help="z.B. imap.gmx.net, imap.web.de, imap.gmail.com"),
        Field("port", "IMAP-Port", "int", 993, min=1, max=65535, help="993 bei SSL/TLS, 143 bei STARTTLS"),
        Field("security", "Verschlüsselung", "select", "ssl", options=("ssl", "starttls", "none"),
              help="ssl = SSL/TLS (empfohlen), starttls = STARTTLS, none = unverschlüsselt (nicht empfohlen)"),
        Field("user", "IMAP-Benutzer"),
        Field("password", "IMAP-Passwort", secret=True,
              help="Bei Anbietern mit Zwei-Faktor-Anmeldung ein App-Passwort verwenden."),
        Field("folder", "Ordner", default="INBOX", help="Mehrere Ordner mit Komma trennen, z.B. INBOX, Pakete"),
        Field("lookback_days", "Zeitraum (Tage)", "int", 14, min=1, max=90,
              help="Beim ersten Abruf werden Mails dieses Zeitraums gelesen, danach nur neue."),
        Field("mark_processed", "Verarbeitete Mails markieren", "bool", False,
              help="Setzt das IMAP-Schlüsselwort $Pakettracker (nicht „gelesen“). Braucht Schreibrechte im Ordner."),
        Field("eml_dir", "Ordner mit .eml-Dateien"),
    )),
)
