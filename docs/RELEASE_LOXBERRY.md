# Veröffentlichung: GitHub-Release und LoxBerry

Leitfaden für Maintainer: Version festlegen, Release bauen, auf GitHub veröffentlichen, Auto-Update prüfen und das Plugin für LoxBerry (Wiki/App Store, Forum) einreichen.

Repository: **https://github.com/Maddog1090/loxberry-pakettracker** (gepflegt in `tools/build_release.py`, Konstante `GITHUB_REPO`).

---

## Versionsschema

Pakettracker folgt [Semantic Versioning](https://semver.org/lang/de/) `MAJOR.MINOR.PATCH`:

| Teil | Wann erhöhen | Beispiele |
|---|---|---|
| **PATCH** (0.2.2 → 0.2.3) | Fehlerbehebungen, Dokumentation, kleine Verbesserungen ohne neue Funktion | Mail-Parser an neues Layout angepasst, Tippfehler, Sicherheitskorrektur |
| **MINOR** (0.2.x → 0.3.0) | neue Paketdienste oder Funktionen, rückwärtskompatibel | FedEx-API, neue MQTT-Topics, neue Einstellung |
| **MAJOR** (0.x → 1.0.0, 1.x → 2.0.0) | inkompatible Änderungen | Status-Codes 0–7 oder bestehende MQTT-Topics/REST-Felder geändert oder entfernt, Konfiguration muss migriert werden |

- **Vorabversionen:** `0.3.0-beta.1`. LoxBerry vergleicht Versionen nach SemVer und bietet Vorabversionen nur Nutzern an, die Pre-Releases aktiviert haben (`prerelease.cfg`).
- **Version 1.0.0:** sobald das Plugin stabil im Einsatz ist. Ab dann gelten MQTT-Topics, Status-Codes und REST-Felder als feste Schnittstelle.

**Die Version steht an fünf Stellen.** Der Build bricht ab, wenn sie nicht übereinstimmen:
- `plugin.cfg` → `VERSION=`
- `bin/pakettracker/__init__.py` → `__version__`
- `README.md` → `**Version x.y.z**`
- `docs/ANLEITUNG_DE.md` → `Version x.y.z · …`
- `CHANGELOG.md` → Abschnitt `## [x.y.z]`

**Niemals ändern:** `AUTHOR.NAME`, `AUTHOR.EMAIL`, `PLUGIN.NAME`, `PLUGIN.FOLDER` in `plugin.cfg`. LoxBerry erkennt das Plugin daran; eine Änderung würde Updates bestehender Installationen brechen. Der Build prüft auch das.

---

## Release-Checkliste

**Vorbereitung**
- [ ] Alle Änderungen sind in `CHANGELOG.md` unter der neuen Version beschrieben (Hinzugefügt/Geändert/Behoben).
- [ ] Die Version ist an allen fünf Stellen erhöht (siehe oben).
- [ ] Die Dokumentation ist aktuell (`docs/ANLEITUNG_DE.md`, Hilfe-Seite `templates/*/help_page.html`, README).
- [ ] `python3 -m pytest tests` ist grün.

**Build**
- [ ] `python3 tools/build_release.py` läuft ohne Meldungen durch. Er prüft und erzeugt:
  - Prüfungen: Versionen, Changelog, Auto-Update-URLs, LF-Zeilenenden, Secret-/IP-/Pfad-Scan
  - erzeugt: `pakettracker-x.y.z.zip`, `pakettracker-x.y.z.zip.sha256`, `release.cfg`, `prerelease.cfg`, `webfrontend/htmlauth/anleitung.html`
- [ ] Im ZIP liegt `plugin.cfg` direkt im Root, es enthält keine `tests/`, `docs/`, `tools/` und keine `credentials.json`/`state.json` (der Build prüft das).

**Test auf einem LoxBerry** (siehe unten)
- [ ] Frische Installation funktioniert.
- [ ] Upgrade von der vorherigen Version behält Einstellungen, Zugangsdaten und Sendungen.

**Veröffentlichung**
- [ ] Commit und Push nach `main`, inklusive `release.cfg`, `prerelease.cfg` und `anleitung.html`.
- [ ] Direkt danach das GitHub-Release `vx.y.z` anlegen, ZIP und `.sha256` anhängen.
- [ ] Prüfen, dass die `release.cfg`-URL die neue Version liefert und der ZIP-Link funktioniert.
- [ ] Forum-Thread und Wiki/App-Store-Eintrag aktualisieren (Version, Änderungen).

---

## Einmalig: GitHub-Repository anlegen

**Im Browser:**
1. github.com → **+** → **New repository**.
2. Owner `Maddog1090`, Name **`loxberry-pakettracker`**, Beschreibung: „LoxBerry-Plugin: Paketverfolgung (DHL, Amazon, Hermes, DPD, GLS, UPS) für Loxone per MQTT“.
3. **Public**. *Kein* README, *keine* .gitignore, *keine* Lizenz anlegen lassen, das Projekt bringt alles mit.
4. **Create repository**.
5. **Settings → General → Features:** Issues an.
6. **Settings → Security → Private vulnerability reporting:** **Enable**. Darauf verweist `SECURITY.md`.
7. Auf der Startseite unter **About** (Zahnrad) Topics setzen: `loxberry`, `loxone`, `mqtt`, `smarthome`, `parcel-tracking`, `dhl`, `ups`.

**Alternativ per Kommandozeile:**
```bash
cd ~/projects/loxberry-pakettracker
git init -b main
git add .
git status                      # prüfen: keine ZIPs, keine dev/-Daten, keine credentials.json
git commit -m "Pakettracker 0.2.2"
gh repo create Maddog1090/loxberry-pakettracker --public --source . --push \
  --description "LoxBerry-Plugin: Paketverfolgung (DHL, Amazon, Hermes, DPD, GLS, UPS) für Loxone per MQTT"
```

Heißt das Repository anders, gilt: **vor dem Build** `GITHUB_REPO` in `tools/build_release.py` und die drei URLs in `plugin.cfg` (`WEBSITE`, `RELEASECFG`, `PRERELEASECFG`) anpassen, außerdem die Links in README, `SECURITY.md` und dieser Datei. Der Build meldet, wenn `plugin.cfg` und `GITHUB_REPO` nicht zusammenpassen.

---

## GitHub-Release erstellen

```bash
python3 -m pytest tests
python3 tools/build_release.py
git add -A && git commit -m "Release 0.2.2" && git push
gh release create v0.2.2 pakettracker-0.2.2.zip pakettracker-0.2.2.zip.sha256 \
  --target main --title "Pakettracker 0.2.2" --notes-file <(sed -n '/^## \[0.2.2\]/,/^## \[/p' CHANGELOG.md | sed '$d')
```

**Im Browser:**
1. Repository → **Releases** → **Draft a new release**.
2. **Choose a tag** → `v0.2.2` eingeben → **Create new tag on publish**, Target `main`.
3. Titel: `Pakettracker 0.2.2`. Beschreibung: den Abschnitt `## [0.2.2]` aus `CHANGELOG.md` einfügen, dazu die SHA-256 aus der `.sha256`-Datei.
4. Unter **Attach binaries** die Dateien `pakettracker-0.2.2.zip` und `pakettracker-0.2.2.zip.sha256` hochladen.
5. Bei Vorabversionen **Set as a pre-release** anhaken.
6. **Publish release**.

**Wichtig:**
- Der Tag muss genau `v<Version>` heißen und der Dateiname genau `pakettracker-<Version>.zip`. Daraus besteht die `ARCHIVEURL` in `release.cfg`.
- **Reihenfolge:** `release.cfg` nennt die neue Version, sobald sie auf `main` liegt. Das Release deshalb **direkt nach dem Push** veröffentlichen. Prüft ein LoxBerry genau dazwischen, schlägt nur dieser eine Download fehl, und er versucht es bei der nächsten Prüfung erneut.

---

## release.cfg und Auto-Update

So funktioniert es (LoxBerry `sbin/pluginsupdate.pl`):
1. Bei der Installation übernimmt LoxBerry `RELEASECFG`/`PRERELEASECFG` aus `plugin.cfg` in die Plugin-Datenbank.
2. LoxBerry lädt regelmäßig `https://raw.githubusercontent.com/Maddog1090/loxberry-pakettracker/main/release.cfg`.
3. Ist dort `VERSION` neuer als die installierte Version, benachrichtigt LoxBerry oder installiert automatisch die `ARCHIVEURL`, je nach Einstellung in der Plugin-Verwaltung.

`release.cfg` und `prerelease.cfg` erzeugt der Build, nicht von Hand bearbeiten:
```
[AUTOUPDATE]
VERSION=0.2.2
ARCHIVEURL=https://github.com/Maddog1090/loxberry-pakettracker/releases/download/v0.2.2/pakettracker-0.2.2.zip
INFOURL=https://github.com/Maddog1090/loxberry-pakettracker/releases/tag/v0.2.2
```
Ohne eigenes Pre-Release zeigt `prerelease.cfg` auf das aktuelle Release.

**Für ein Pre-Release:** `plugin.cfg` `VERSION=0.3.0-beta.1` setzen und bauen. Danach `release.cfg` aus Git wiederherstellen, damit der stabile Kanal unverändert bleibt (`git checkout release.cfg`), und nur `prerelease.cfg` committen. Das GitHub-Release als Pre-Release markieren.

### Auto-Update testen
1. Nach dem Veröffentlichen prüfen:
   ```bash
   curl -fsSL https://raw.githubusercontent.com/Maddog1090/loxberry-pakettracker/main/release.cfg
   curl -fsSIL "$(curl -fsSL https://raw.githubusercontent.com/Maddog1090/loxberry-pakettracker/main/release.cfg | sed -n 's/^ARCHIVEURL=//p')" | head -1   # HTTP 200 erwartet
   ```
2. Auf einem Test-LoxBerry die **vorherige** Version installieren. Wichtig: Sie muss bereits eine `plugin.cfg` mit `RELEASECFG` enthalten. Das gilt ab 0.2.2; 0.1.x bis 0.2.1 hatten keine Update-URL und werden einmal von Hand aktualisiert.
3. Plugin-Verwaltung → Pakettracker → Update-Einstellung auf „Benachrichtigen“ oder „Releases automatisch installieren“ setzen.
4. Nach der nächsten Update-Prüfung des LoxBerry muss die Benachrichtigung erscheinen bzw. die neue Version installiert sein. Das Protokoll steht in der LoxBerry-Logverwaltung unter „Plugin Update“ bzw. `plugininstall`.

Der erste echte Auto-Update-Test ist also erst mit dem **übernächsten** Release möglich (0.2.2 installiert → 0.2.3 veröffentlicht).

---

## Tests vor der Freigabe

### Frischer LoxBerry
- [ ] ZIP über die Plugin-Verwaltung installieren. Im Protokoll stehen nur OK-Meldungen, kein Hinweis auf fest codierte Pfade.
- [ ] Alle fünf Seiten öffnen (Status, Sendungen, Einstellungen, Anbieter, Hilfe), keine PHP-Fehler. Die Weboberfläche muss auch unter **PHP 7.4** laufen, LoxBerry 4 nutzt für Apache teils 7.4.
- [ ] Hilfe → **Ausführliche Anleitung öffnen** lädt die Anleitung.
- [ ] Testsendung eintragen → **Jetzt aktualisieren** → Slot 1 belegt, MQTT-Werte unter `pakettracker/…` im MQTT Gateway.
- [ ] Nach höchstens 15 Minuten läuft der Cron (Zeitstempel „Letzte Aktualisierung“ ändert sich).
- [ ] REST ist standardmäßig an und tokengeschützt; ohne Token kommt HTTP 403.
- [ ] Per SSH als `loxberry`: `find /opt/loxberry/*/plugins/pakettracker ! -user loxberry` liefert nichts, `credentials.json` hat 600.

### Upgrade von einer älteren Version
- [ ] Vorher Einstellungen ändern, Zugangsdaten setzen (Testwerte) und Sendungen anlegen; Prüfsummen von `settings.json`, `credentials.json`, `tracked.json` notieren.
- [ ] Neue ZIP darüber installieren. Im Protokoll stehen „Sicherung abgeschlossen“ und „Konfiguration wiederhergestellt“.
- [ ] Die Prüfsummen sind unverändert, die Version in der Plugin-Verwaltung ist neu.

### Automatische Tests
- `tests/test_upgrade.py` spielt Installation, Upgrade (0.1.x und 0.2.0) und Deinstallation mit den echten Skripten durch.
- Die übrigen Tests decken Provider, IMAP, MQTT-Ausfall, Duplikate und Erkennung ab.

---

## Einreichung bei LoxBerry

### Wege
1. **LoxForum** (www.loxforum.com, Bereich LoxBerry → Plugins): Vorstellungs-Thread eröffnen. Text siehe unten. Dort bekommen Sie auch Rückmeldung von Nutzern und den Wiki-Admins.
2. **LoxBerry-Wiki** (wiki.loxberry.de): Plugin-Seite anlegen, Inhalt aus README und Anleitung kürzen. Für Schreibrechte ggf. im Forum oder bei den Wiki-Admins anfragen.
3. **App Store in LoxBerry 4:** Er lädt seinen Katalog aus dem Wiki (`https://wiki.loxberry.de/_media/appstore/plugins.json`). Wie man aufgenommen wird, im Forum-Thread bzw. bei den Wiki-Admins erfragen und die Angaben aus der Tabelle unten bereitstellen.

### Angaben für Wiki/App Store
Der LoxBerry-App-Store (`templates/system/appstore.html`) zeigt je Plugin diese Felder:

| Feld | Wert für Pakettracker |
|---|---|
| Titel (`title`) | Pakettracker (muss dem `TITLE` aus `plugin.cfg` entsprechen, daran erkennt der Store installierte Plugins) |
| Autor (`author`) | ToRe90 |
| Beschreibung (`description`) | Kurztext, siehe unten |
| Status (`status`) | **BETA** (Werte: STABLE, BETA, ALPHA, UNSTABLE, STOPPED). STABLE ab 1.0.0 empfohlen. |
| Version (`version`) | 0.2.2 |
| Min. LoxBerry (`min_lb_version`) | 3.0.0 |
| ZIP (`zip`) | `https://github.com/Maddog1090/loxberry-pakettracker/releases/download/v0.2.2/pakettracker-0.2.2.zip` (muss http/https sein, sonst ist das Plugin im Store nicht installierbar) |
| Repository (`repo`) | `https://github.com/Maddog1090/loxberry-pakettracker` |
| Wiki (`wiki`) | Link zur Wiki-Seite, sobald angelegt |
| Forum (`forum`) | Link zum Vorstellungs-Thread, sobald angelegt |
| Logo (`logo`) | `https://raw.githubusercontent.com/Maddog1090/loxberry-pakettracker/main/icons/icon_256.png` (derzeit ein schlichtes Platzhalter-Icon) |
| Sprachen (`languages`) | Deutsch, Englisch (Oberfläche); Anleitung Deutsch |

### Kurzer Plugin-Text (≤ 200 Zeichen)
> Paketverfolgung für Loxone: DHL, UPS (API) sowie Amazon, Hermes, DPD, GLS (E-Mail/IMAP). Status, Termine und „Paket kommt heute“ per MQTT, mit Testmodus und Hilfe.

### Ausführliche Beschreibung
> **Pakettracker** bringt Ihre Paketsendungen in die Loxone-Welt. Das Plugin sammelt Ankündigungen und Sendungsstatus von DHL, Amazon, Hermes, DPD, GLS und UPS und stellt sie dem Miniserver über das LoxBerry MQTT Gateway bereit – als Zähler (z.B. „heute in Zustellung“), als feste Slots mit der jeweils wichtigsten Sendung und mit einem einheitlichen Status-Code 0–7 für alle Paketdienste.
>
> DHL und UPS werden über ihre offiziellen Schnittstellen abgefragt (kostenlose Entwicklerzugänge). Für Amazon, Hermes, DPD und GLS, die Privatkunden keine Tracking-API anbieten, wertet das Plugin die Benachrichtigungsmails per IMAP aus – nur lesend, nur neue Mails von Paketdiensten. Es gibt kein Screen-Scraping und keine Anmeldung auf Kundenportalen.
>
> Sendungsnummern lassen sich auch von Hand eintragen; der Paketdienst wird automatisch erkannt. Ein Testmodus erzeugt Beispieldaten zum Einrichten von MQTT und Loxone. Zugangsdaten bleiben auf dem LoxBerry und werden nie angezeigt oder protokolliert. Eine Hilfe-Seite und eine ausführliche deutsche Anleitung sind im Plugin enthalten. Optional gibt es eine REST-API.

### Kontakt und Support
- **Autor:** ToRe90 · existenzz-cod2@gmx.de
- **Support:** https://github.com/Maddog1090/loxberry-pakettracker/issues (sowie der Forum-Thread)
- **Sicherheit:** vertraulich, siehe `SECURITY.md`

### Unterstützte LoxBerry-Versionen
- `LB_MINIMUM=3.0.0`, kein Maximum.
- Getestet auf **LoxBerry 4.0.0.15** (Raspberry Pi, aarch64, Debian 13, Apache mit PHP 7.4, Python 3.13, paho-mqtt 2.1).
- Entwickelt gegen die Installer-Konventionen von LoxBerry 3 (`sbin/plugininstall.pl`).
- Auf einem echten LoxBerry 3 noch **nicht** getestet.

### Unterstützte Paketdienste
DHL (API + E-Mail), UPS (API + E-Mail), Amazon, Hermes, DPD, GLS (E-Mail/IMAP); FedEx, TNT vorbereitet.

---

## Vorlage: Forumspost zur Vorstellung

```
Titel: [Plugin] Pakettracker – Paketverfolgung (DHL, UPS, Amazon, Hermes, DPD, GLS) für Loxone

Hallo zusammen,

ich möchte euch mein neues LoxBerry-Plugin „Pakettracker“ vorstellen (Version 0.2.2, Beta).

Was es macht:
Pakettracker sammelt Ankündigungen und den Sendungsstatus eurer Pakete und gibt sie per MQTT an den Miniserver weiter. In Loxone könnt ihr damit z.B. anzeigen „Heute kommt ein Paket“, euch ans Abholen erinnern lassen oder in der App die nächste Sendung mit Termin anzeigen.

Paketdienste:
- DHL und UPS über die offiziellen Schnittstellen (kostenlose Entwicklerzugänge)
- Amazon, Hermes, DPD und GLS über die Benachrichtigungsmails (IMAP, nur lesend)
- FedEx/TNT vorbereitet

Highlights:
- einheitlicher Status-Code 0–7 für alle Paketdienste, Zähler und feste „Slots“ für Loxone
- automatische Erkennung des Paketdienstes anhand der Sendungsnummer
- Testmodus zum Einrichten ohne Zugangsdaten
- Zugangsdaten bleiben auf dem LoxBerry, werden nie angezeigt oder geloggt
- kein Screen-Scraping, keine Anmeldung auf Kundenportalen
- Hilfe-Seite und ausführliche deutsche Anleitung im Plugin, automatische Updates über die Plugin-Verwaltung

Voraussetzungen: LoxBerry ab 3.0 (getestet auf 4.0), MQTT Gateway; für Amazon/Hermes/DPD/GLS ein Postfach mit IMAP.

Download und Anleitung:
https://github.com/Maddog1090/loxberry-pakettracker

Bekannte Einschränkungen:
Amazon/Hermes/DPD/GLS nur per E-Mail (weitergeleitete Mails werden nicht erkannt), 12-/14-stellige Nummern sind mehrdeutig (dann Anbieter manuell wählen), DHL-Gratiszugang 250 Abfragen/Tag.

Über Rückmeldungen freue ich mich – gerne auch anonymisierte Beispielmails, falls eine Paketmail nicht erkannt wird. Fehler bitte als GitHub-Issue oder hier im Thread melden (bitte ohne Zugangsdaten oder Sendungsnummern).

Viele Grüße
ToRe90
```
