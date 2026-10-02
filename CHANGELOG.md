# Changelog

Alle nennenswerten Änderungen am Plugin. Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionen nach [Semantic Versioning](https://semver.org/lang/de/) (Details: [docs/RELEASE_LOXBERRY.md](docs/RELEASE_LOXBERRY.md#versionsschema)).

> Die Versionen bis einschließlich 0.2.2 entstanden am 2026-10-02 während der Entwicklung und wurden nicht öffentlich veröffentlicht. Die Datumsangaben sind die Build-Daten. 0.2.2 ist die erste zur Veröffentlichung vorgesehene Version.

## [1.0.0] – 2026-10-02

Erste stabile Version: MQTT-Topics, Status-Codes 0–7 und REST-Felder gelten ab jetzt als feste Schnittstelle.

### Hinzugefügt
- Hermes: optionale **Live-Abfrage** über die Sendungsverfolgung von myhermes.de (Einstellungen → Hermes → *Live-Abfrage über myhermes.de*, standardmäßig aus). Liefert Status, Originaltext, Verlauf und Zustellzeitfenster auch ohne Benachrichtigungsmail – z.B. für manuell eingetragene Nummern. Ohne Zugangsdaten; die Schnittstelle ist öffentlich, aber nicht offiziell dokumentiert. Drosselung wie bei DHL/UPS (Mindestabstand je Sendung, Tageslimit), Verbindungstest.
- Neues Feld **Zustellzeitfenster** `eta_window` (z.B. `10:00–14:00`, Ortszeit): in Sendungsliste, Slots, MQTT (`slot/<n>/eta_window`) und REST. Befüllt von Hermes (Live), DHL (`estimatedDeliveryTimeFrame`) und UPS (`deliveryTime`).
- Sendungsliste: Originaltext des Paketdienstes direkt unter dem Status und aufklappbarer Sendungsverlauf.

### Geändert
- Termine werden in der Oberfläche als TT.MM.JJJJ angezeigt (MQTT/REST unverändert JJJJ-MM-TT).
- Zustand je Anbieter: Die Datenquelle berücksichtigt, ob eine optionale Live-Abfrage eingeschaltet ist.

## [0.2.3] – 2026-10-02

### Hinzugefügt
- REST-API: Einzelwert-Abfragen für Loxone, z.B. `api.php?q=summary&field=active&format=text` oder `api.php?q=slot&n=1&field=description&format=text`. Die Antwort ist genau der Wert als UTF-8-Klartext (ohne Feldnamen, JSON oder HTML, ohne Leerzeichen am Rand, HTML-Entities aufgelöst). Leere Slots liefern `0` bzw. einen leeren Text. Mit JSON-Format: `{"q":…,"field":…,"value":…}`
- Hilfe: Abschnitt „Loxone per HTTP/REST“ mit fertigen Adressen (aktuelle LoxBerry-Adresse, Token nur bei aktivem Token-Schutz) und Tabelle der empfohlenen Loxone-Eingänge
- Tests für die REST-API gegen den PHP-Webserver und für die Hilfe-Seite

### Geändert
- REST-API: Ist die Schnittstelle ausgeschaltet, kommt **403** statt 404. Unbekanntes Feld oder ungültiger Slot bei `field=…` → 400. Nur GET/HEAD erlaubt (405).
- REST-API: `api.php` sendet nie PHP-Warnungen oder HTML-Fehlerseiten; Parameter als Array (`q[]=…`) werden abgefangen. Die bisherige Zeilenausgabe (`format=text`) bereinigt Werte genauso.
- Einstellungen → REST-Beispiele: Token nur bei aktivem Token-Schutz, zusätzliche Einzelwert-Beispiele. Die Adressen nutzen die IP-Adresse des LoxBerry, wenn die Oberfläche über einen Hostnamen geöffnet wurde.

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
