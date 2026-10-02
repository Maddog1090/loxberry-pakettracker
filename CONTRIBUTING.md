# Mitwirken

Danke für Ihr Interesse am Pakettracker! Fehlerberichte, Verbesserungen und neue Paketdienste sind willkommen.

## Fehler melden

- GitHub → **Issues** → neues Issue. Bitte angeben: Plugin-Version, LoxBerry-Version, betroffener Paketdienst, was erwartet wurde und was passiert ist, passende Zeilen aus dem Plugin-Log.
- **Keine Zugangsdaten, Tokens, Sendungsnummern oder echten Mailinhalte posten.** Sendungsnummern und persönliche Daten vorher unkenntlich machen.
- Sicherheitslücken bitte vertraulich melden, siehe [SECURITY.md](SECURITY.md).
- **Mail-Layouts:** Erkennt das Plugin eine Paketmail nicht, hilft eine anonymisierte Beispielmail (`.eml`, Namen/Adressen/Nummern ersetzt) am meisten.

## Entwicklung

Voraussetzungen: Python ≥ 3.9 (auf dem LoxBerry z.B. 3.11/3.13), für Tests `pytest`.

```bash
export PAKETTRACKER_ROOT=$PWD/dev        # außerhalb von LoxBerry Pflicht
python3 bin/pakettracker.py init
python3 bin/pakettracker.py run --force -v
python3 -m pytest tests
```

- **Architektur:** [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Neuer Paketdienst:** eine Datei in `bin/pakettracker/providers/` (Beispiel im Abschnitt „Neuen Anbieter ergänzen“). Nur offizielle, dokumentierte Schnittstellen verwenden – kein Screen-Scraping, keine Login-Automatisierung.
- **Tests:** Sie dürfen nie echte APIs aufrufen (`tests/conftest.py` sperrt die URLs). HTTP gegen `tests/fakehttp.py`, IMAP gegen die Fake-Klasse in `tests/test_imap.py`.
- **Testdaten:** Nur fiktive, anonymisierte Daten in `tests/fixtures/`.
- **Kompatibilität:** Die Weboberfläche muss unter PHP 7.4 laufen (LoxBerry 4 nutzt für Apache teils PHP 7.4), das Backend unter Python ≥ 3.9.
- **Stabile Schnittstellen:** Status-Codes 0–7, MQTT-Topics und REST-Felder nur rückwärtskompatibel erweitern.

## Pull Requests

1. Branch anlegen, Änderung mit Tests umsetzen.
2. `python3 -m pytest tests` muss grün sein.
3. Benutzerrelevante Änderungen in `CHANGELOG.md` unter einer neuen Version bzw. „Unveröffentlicht“ eintragen.
4. Dokumentation anpassen (`docs/ANLEITUNG_DE.md`, ggf. README).

Mit dem Einreichen eines Beitrags stimmen Sie zu, dass er unter der [MIT-Lizenz](LICENSE) des Projekts veröffentlicht wird.
