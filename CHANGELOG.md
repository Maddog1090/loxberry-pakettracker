# Changelog

Alle nennenswerten Änderungen am Plugin. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [Semantic Versioning](https://semver.org/lang/de/) (Details: [docs/RELEASE_LOXBERRY.md](docs/RELEASE_LOXBERRY.md#versionsschema)).

> Die Versionen bis einschließlich 0.2.2 entstanden am 2026-10-02 während der Entwicklung und wurden nicht öffentlich veröffentlicht. Die Datumsangaben sind die Build-Daten. 0.2.2 ist die erste zur Veröffentlichung vorgesehene Version.

## [0.2.2] – 2026-10-02

### Hinzugefügt
- Automatische Updates über GitHub Releases: `plugin.cfg` enthält `RELEASECFG`, `PRERELEASECFG` und `WEBSITE`; `release.cfg`/`prerelease.cfg` werden beim Build erzeugt
- `LICENSE` (MIT), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md`, `docs/RELEASE_LOXBERRY.md`
- Build (`tools/build_release.py`) prüft zusätzlich Changelog-Eintrag, Auto-Update-URLs sowie das Paket auf private IP-Adressen, lokale Pfade und fest gesetzte Geheimnisse; erzeugt eine `.sha256`-Datei

### Geändert
- Dokumentation: Leere MQTT-Werte (z.B. `provider/<id>/error` ohne Fehler) werden nach MQTT-Standard nicht im Broker gespeichert – Hinweis in Anleitung, Hilfe-Seite, README und Architektur; Feldhilfe „Retained senden“ ergänzt. Das Verhalten selbst ist unverändert.

### Getestet
- Auf echtem LoxBerry 4.0.0.15 (Debian 13, Apache mit PHP 7.4, Python 3.13, paho-mqtt 2.1) mit Version 0.2.1: Upgrade von 0.1.1, Weboberfläche, Cron, MQTT, Hilfe-Seite, REST (deaktiviert)

## [0.2.1] – 2026-10-02

### Hinzugefügt
- Ausführliche Benutzeranleitung `docs/ANLEITUNG_DE.md`
- Seite **Hilfe** in der Weboberfläche (Kurzanleitung, de/en) mit Knopf „Ausführliche Anleitung öffnen“
- Anleitung wird als HTML-Seite mitinstalliert (`anleitung.html`, beim Build aus der Markdown-Datei erzeugt)

### Geändert
- Build prüft, dass alle Versionsangaben übereinstimmen

## [0.2.0] – 2026-10-02

### Hinzugefügt
- Anbieter UPS (offizielle Tracking API mit OAuth + E-Mail), Hermes, DPD, GLS (E-Mail); FedEx und TNT vorbereitet (standardmäßig aus)
- Produktiver IMAP-Abruf: SSL/STARTTLS, mehrere Ordner, nur lesend, nur neue und relevante Mails, optionale Markierung, Verbindungstest
- Anbieter-Erkennung mit Prüfziffern (UPS 1Z, UPU S10, GS1) und Hinweis bei mehrdeutigen Nummern; manuelle Anbieterwahl hat Vorrang
- Duplikat-Erkennung über Anbieter und Quellen hinweg, Amazon-Platzhalter bis zur Versandmail
- Gesundheitsstatus je Anbieter: Oberfläche, MQTT `provider/<id>/error|last_success|shipment_count`, REST
- Weboberfläche: Anbieter-Übersicht, Verbindungstests, aufklappbare Anbieter-Einstellungen

### Geändert
- Amazon-Mail-Parser neu (Bestellnummer, Artikel, Termin, TBA, Weiterleitung an den ausliefernden Paketdienst)
- DHL intern auf gemeinsame API-Basis umgestellt (Verhalten unverändert)
- E-Mail-Einstellung „SSL“ durch „Verschlüsselung“ (ssl/starttls/none) ersetzt

## [0.1.1] – 2026-10-02

### Hinzugefügt
- DHL-Live-Tracking über die offizielle „Shipment Tracking – Unified“ API
- Drosselung für das DHL-Kontingent (5 s Abstand, max. 10 Abfragen pro Lauf, Tageslimit, Mindestabstand je Sendung, Pause nach HTTP 429)

### Behoben
- Beim Abschalten des Testmodus werden simulierte Statusdaten verworfen, damit echte Daten sofort übernommen werden
- Zeitstempel mit `Z` werden auch unter Python < 3.11 korrekt gelesen

## [0.1.0] – 2026-10-02

### Hinzugefügt
- Erste Testversion: Plugin-Grundstruktur für LoxBerry, Testmodus, manuelle Sendungen, MQTT- und REST-Ausgabe, Weboberfläche
