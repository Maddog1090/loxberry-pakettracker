# Sicherheit

## Sicherheitsprobleme melden

**Bitte melden Sie Sicherheitslücken nicht öffentlich** (keine GitHub-Issues, keine Forenbeiträge), damit sie behoben werden können, bevor sie ausgenutzt werden.

Stattdessen bitte vertraulich:

- über GitHub: Repository → **Security** → **Report a vulnerability** (private Meldung), oder
- per E-Mail an **existenzz-cod2@gmx.de** mit dem Betreff „Pakettracker Sicherheit“.

Hilfreich sind: betroffene Version, Beschreibung, Schritte zum Nachvollziehen und mögliche Auswirkungen. **Senden Sie keine echten Zugangsdaten, Tokens oder Mailinhalte mit** – anonymisierte Beispiele genügen.

Sie erhalten möglichst innerhalb einer Woche eine Rückmeldung. Nach der Behebung erscheint ein Hinweis im [CHANGELOG](CHANGELOG.md).

## Unterstützte Versionen

| Version | Sicherheitsupdates |
|---|---|
| neueste 0.2.x | ja |
| ältere Versionen | nein – bitte aktualisieren |

## Sicherheitskonzept (Kurzfassung)

- Zugangsdaten (API-Keys, Secrets, Passwörter, REST-Token) liegen nur auf dem LoxBerry in `credentials.json` (Rechte 0600) und werden nie an den Browser gesendet, nie geloggt und sind nie Teil des Repositorys oder Release-ZIPs.
- Die Weboberfläche liegt im passwortgeschützten LoxBerry-Adminbereich und ist zusätzlich gegen CSRF geschützt.
- Die optionale REST-API ist per Token geschützt.
- Der IMAP-Abruf arbeitet nur lesend.
- Der Release-Build prüft das Paket auf private IP-Adressen, lokale Pfade und fest gesetzte Geheimnisse.
