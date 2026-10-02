# Pakettracker – LoxBerry-Plugin

**Paketverfolgung für Loxone:** Pakettracker sammelt Ankündigungen und Sendungsstatus von **DHL, Amazon, Hermes, DPD, GLS und UPS** und stellt sie dem Loxone Miniserver über **MQTT** (und optional REST) bereit – z.B. für „Heute kommt ein Paket“ in der Loxone-App oder eine Erinnerung, ein Paket abzuholen.

**Version 0.2.3** · LoxBerry ≥ 3.0 (getestet mit 4.0) · Autor: ToRe90 · [MIT-Lizenz](LICENSE)

📖 **Ausführliche Anleitung (Deutsch): [docs/ANLEITUNG_DE.md](docs/ANLEITUNG_DE.md)** – auf dem LoxBerry unter Plugin → **Hilfe** → **Ausführliche Anleitung öffnen**.

---

## Unterstützte Paketdienste

| Anbieter | Datenquelle | Was Sie brauchen |
|---|---|---|
| **DHL** | Offizielle API + E-Mail | kostenloser API-Key (developer.dhl.com) und/oder E-Mail-Eingang |
| **UPS** | Offizielle API (OAuth) + E-Mail | kostenlose Client-ID + Secret (developer.ups.com) und/oder E-Mail-Eingang |
| **Amazon** | E-Mail (IMAP) | E-Mail-Eingang |
| **Hermes** | E-Mail (IMAP) | E-Mail-Eingang |
| **DPD** | E-Mail (IMAP) | E-Mail-Eingang |
| **GLS** | E-Mail (IMAP) | E-Mail-Eingang |
| FedEx, TNT | E-Mail (vorbereitet, standardmäßig aus) | E-Mail-Eingang |

Amazon, Hermes, DPD und GLS bieten Privatkunden keine offizielle Tracking-API. Pakettracker nutzt deshalb deren Benachrichtigungsmails – **kein Screen-Scraping, keine Login-Automatisierung, nur offizielle Wege.**

## Funktionen

- **Sechs Paketdienste**, automatische Anbieter-Erkennung (mit Prüfziffern, Hinweis bei mehrdeutigen Nummern, manuelle Wahl hat Vorrang)
- **E-Mail-Eingang (IMAP):** nur lesend, nur neue Mails von Paketdiensten, mehrere Ordner, Verbindungstest
- **Loxone-gerecht:** feste Status-Codes 0–7, Zähler, feste Slots (wichtigste Sendung zuerst), Zustand je Paketdienst
- **Robust:** Fällt ein Paketdienst, das Postfach oder MQTT aus, läuft der Rest weiter; Duplikate werden zusammengeführt
- **Testmodus** zum Einrichten ohne Zugangsdaten
- **Sicher:** Zugangsdaten nur auf dem LoxBerry (0600), nie im Browser oder Log; DHL-Kontingent wird automatisch eingehalten
- **Weboberfläche** mit Status, Sendungen, Einstellungen, Anbieter-Übersicht und Hilfe; **automatische Updates** über die LoxBerry-Plugin-Verwaltung

## Screenshots

Screenshots liegen in [`docs/screenshots/`](docs/screenshots/) (Dateinamen siehe dortige README) und werden hier eingebunden, sobald vorhanden.

<!--
![Status](docs/screenshots/status.png)
![Anbieter](docs/screenshots/anbieter.png)
![Einstellungen](docs/screenshots/einstellungen.png)
![Hilfe](docs/screenshots/hilfe.png)
-->

## Voraussetzungen

- LoxBerry ab Version 3.0 (entwickelt gegen die Konventionen von LoxBerry 3, getestet auf LoxBerry 4.0.0.15)
- MQTT Gateway des LoxBerry (bei LoxBerry 3/4 enthalten) für die Loxone-Anbindung
- Für Amazon, Hermes, DPD, GLS: ein Postfach mit IMAP-Zugang
- Optional: DHL-API-Key, UPS-Zugangsdaten

## Installation

1. Unter [Releases](https://github.com/Maddog1090/loxberry-pakettracker/releases) die Datei `pakettracker-<Version>.zip` herunterladen (nicht entpacken).
2. LoxBerry → **Plugin-Verwaltung** → ZIP auswählen → **Installieren**.
3. Das Plugin startet im **Testmodus**.

## Update

- **Automatisch:** In der LoxBerry-Plugin-Verwaltung beim Pakettracker die gewünschte Update-Einstellung wählen. LoxBerry prüft dann selbst auf neue Releases.
- **Manuell:** Die neue ZIP wie bei der Installation einspielen.

Einstellungen, Zugangsdaten und Sendungen bleiben bei jedem Update erhalten.

## Schnellstart

1. Plugin öffnen → **Sendungen** → Testnummer `00340434000000000001` eintragen → **Status** → **Jetzt aktualisieren**.
2. Im **MQTT Gateway** prüfen, ob Werte unter `pakettracker/…` ankommen.
3. Loxone einrichten (siehe unten), solange der Testmodus läuft.
4. **Einstellungen → E-Mail-Eingang** einrichten und testen.
5. Optional DHL-API-Key und UPS-Zugangsdaten eintragen.
6. **Testmodus ausschalten** und auf der Seite **Anbieter** kontrollieren.

Schritt für Schritt: [Anleitung, Abschnitt 4](docs/ANLEITUNG_DE.md#4-erste-inbetriebnahme).

## MQTT-Ausgabe

Basis-Topic `pakettracker` (einstellbar), retained für Werte mit Inhalt:

| Topic | Inhalt |
|---|---|
| `pakettracker/summary/active`, `out_for_delivery`, `pickup_ready`, `delivered_today`, `next_eta` … | Zähler und nächster Termin |
| `pakettracker/slot/<n>/status_code`, `status_label`, `description`, `eta`, `used` … | feste Slots 1…N, wichtigste Sendung zuerst |
| `pakettracker/provider/<id>/active`, `shipment_count`, `error`, `last_success` | je Paketdienst (`error` leer = ok) |

Status-Codes: 0 unbekannt · 1 angekündigt · 2 unterwegs · 3 in Zustellung · 4 zugestellt · 5 abholbereit · 6 Problem · 7 Rücksendung.
Alle Topics: [Anleitung, Abschnitt 18](docs/ANLEITUNG_DE.md#18-wichtige-mqtt-topics). Optional gibt es eine token-geschützte REST-API ([Abschnitt 20](docs/ANLEITUNG_DE.md#20-rest-api-und-rest-token)).

## Loxone-Integration

Das LoxBerry MQTT Gateway leitet die Werte als virtuelle Eingänge an den Miniserver (aus `/` wird `_`):

- `pakettracker_summary_out_for_delivery` (virtueller Eingang) → z.B. „> 0“ → Push „Paket kommt heute“
- `pakettracker_slot_1_status_code` (virtueller Eingang, 0–7) → Status-Baustein
- `pakettracker_slot_1_description`, `…_status_label` (virtueller Texteingang) → Anzeige in der App

Beispiele: [Anleitung, Abschnitt 19](docs/ANLEITUNG_DE.md#19-einbindung-in-loxone).

## Bekannte Einschränkungen

- Amazon, Hermes, DPD, GLS nur über E-Mail – ohne Benachrichtigungsmail kein Status; weitergeleitete Mails werden nicht erkannt.
- 12- und 14-stellige Nummern sind mehrdeutig (DHL/GLS bzw. Hermes/DPD) – dann Anbieter manuell wählen.
- Kostenloser DHL-Zugang: 250 Abfragen pro Tag (ca. 10 aktive Sendungen bei 60 Minuten Abstand).
- Leere MQTT-Werte werden nach MQTT-Standard nicht im Broker gespeichert.
- Outlook.com/Hotmail-Postfächer (nur OAuth-Anmeldung) werden in der Regel nicht unterstützt.
- FedEx/TNT nur vorbereitet.

Vollständige Liste: [Anleitung, Abschnitt 24](docs/ANLEITUNG_DE.md#24-bekannte-einschränkungen).

## Support und Kontakt

- **Fragen und Fehler:** [GitHub Issues](https://github.com/Maddog1090/loxberry-pakettracker/issues) – bitte ohne Zugangsdaten, Sendungsnummern oder echte Mailinhalte
- **Sicherheitslücken:** vertraulich melden, siehe [SECURITY.md](SECURITY.md)
- **Kontakt:** ToRe90 · existenzz-cod2@gmx.de

## Mitwirken und Entwicklung

[CONTRIBUTING.md](CONTRIBUTING.md) · [Architektur](docs/ARCHITECTURE.md) · [Release-Prozess](docs/RELEASE_LOXBERRY.md) · [Änderungen](CHANGELOG.md)

```bash
python3 -m pytest tests              # Tests (greifen nie auf echte APIs zu)
python3 tools/build_release.py       # Release-ZIP + SHA-256 + release.cfg
```

## Lizenz

[MIT](LICENSE) © 2026 ToRe90
