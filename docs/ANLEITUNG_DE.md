# Pakettracker für LoxBerry – Benutzeranleitung

Version 1.0.2 · Autor: ToRe90 · Kontakt: existenzz-cod2@gmx.de

Diese Anleitung richtet sich an Anwender, die das Plugin einrichten und nutzen möchten. Programmierkenntnisse sind nicht nötig. Für einige Schritte (Logs per SSH, Backup) sind Grundkenntnisse im Umgang mit dem LoxBerry hilfreich.

> Diese Anleitung ist auch direkt auf Ihrem LoxBerry verfügbar: Plugin öffnen → Seite **Hilfe** → **Ausführliche Anleitung öffnen**.

---

## Inhalt

1. [Was macht das Plugin?](#1-was-macht-das-plugin)
2. [Voraussetzungen](#2-voraussetzungen)
3. [Installation](#3-installation)
4. [Erste Inbetriebnahme](#4-erste-inbetriebnahme)
5. [Die Weboberfläche im Überblick](#5-die-weboberfläche-im-überblick)
6. [Testmodus](#6-testmodus)
7. [Statuscodes 0–7](#7-statuscodes-07)
8. [Sendungen manuell hinzufügen](#8-sendungen-manuell-hinzufügen)
9. [Automatische Anbieter-Erkennung](#9-automatische-anbieter-erkennung)
10. [E-Mail-Eingang (IMAP) einrichten](#10-e-mail-eingang-imap-einrichten)
11. [DHL einrichten](#11-dhl-einrichten)
12. [Amazon einrichten](#12-amazon-einrichten)
13. [Hermes einrichten](#13-hermes-einrichten)
14. [DPD einrichten](#14-dpd-einrichten)
15. [GLS einrichten](#15-gls-einrichten)
16. [UPS einrichten](#16-ups-einrichten)
17. [MQTT einrichten](#17-mqtt-einrichten)
18. [Wichtige MQTT-Topics](#18-wichtige-mqtt-topics)
19. [Einbindung in Loxone](#19-einbindung-in-loxone)
20. [REST-API und REST-Token](#20-rest-api-und-rest-token)
21. [Sicherheit und Umgang mit Zugangsdaten](#21-sicherheit-und-umgang-mit-zugangsdaten)
22. [Logs und Fehlersuche](#22-logs-und-fehlersuche)
23. [Backup und Update](#23-backup-und-update)
24. [Bekannte Einschränkungen](#24-bekannte-einschränkungen)
25. [Alle Einstellungen auf einen Blick](#25-alle-einstellungen-auf-einen-blick)

---

## 1. Was macht das Plugin?

Der Pakettracker sammelt Informationen über Ihre Paketsendungen und stellt sie Ihrem Loxone Miniserver zur Verfügung. So können Sie in der Loxone-App z.B. anzeigen, dass heute ein Paket kommt, oder sich erinnern lassen, ein Paket in der Filiale abzuholen.

Unterstützte Paketdienste:

| Paketdienst | Woher kommen die Daten? | Was Sie brauchen |
|---|---|---|
| **DHL** | Offizielle DHL-Schnittstelle (API), optional zusätzlich DHL-Benachrichtigungsmails | Einen kostenlosen DHL-API-Key (dann kein E-Mail-Eingang nötig) und/oder den E-Mail-Eingang |
| **UPS** | Offizielle UPS-Schnittstelle (API) und UPS-Benachrichtigungsmails | Kostenlose UPS-Zugangsdaten (Client-ID und Secret) und/oder den E-Mail-Eingang |
| **Amazon** | Versand- und Zustellmails von Amazon | E-Mail-Eingang |
| **Hermes** | Benachrichtigungsmails von Hermes, optional Live-Abfrage über die Sendungsverfolgung von myhermes.de | E-Mail-Eingang und/oder *Live-Abfrage* einschalten |
| **DPD** | Benachrichtigungsmails von DPD | E-Mail-Eingang |
| **GLS** | Benachrichtigungsmails von GLS | E-Mail-Eingang |
| FedEx, TNT | Benachrichtigungsmails (vorbereitet, standardmäßig ausgeschaltet) | E-Mail-Eingang |

**Warum nicht überall eine Schnittstelle?** Amazon, Hermes, DPD und GLS bieten Privatkunden keine offizielle Schnittstelle zur Sendungsverfolgung an. Das Plugin nutzt bewusst nur offizielle und rechtlich saubere Wege. Es meldet sich nicht auf Webseiten an und liest keine Webseiten aus. Für diese Paketdienste wertet es stattdessen die Benachrichtigungsmails aus, die Sie ohnehin bekommen. Einzige Ausnahme ist die **optionale Hermes-Live-Abfrage** (standardmäßig aus, siehe [Abschnitt 13](#13-hermes-einrichten)).

**So arbeitet das Plugin:** Alle paar Minuten (Standard: alle 15 Minuten)
1. liest es neue Paketmails aus Ihrem Postfach,
2. übernimmt die Sendungen, die Sie selbst eingetragen haben,
3. fragt DHL- und UPS-Sendungen über deren Schnittstelle ab,
4. schickt das Ergebnis per MQTT an den LoxBerry (und von dort an Loxone) und stellt es über eine Web-Schnittstelle (REST) bereit.

Fällt ein Paketdienst oder das Postfach aus, arbeiten alle anderen Teile normal weiter.

---

## 2. Voraussetzungen

- **LoxBerry ab Version 3.0**
- Für MQTT: der in LoxBerry integrierte **MQTT-Broker und das MQTT Gateway** (bei LoxBerry 3 enthalten)
- Für Amazon, Hermes, DPD und GLS: ein **E-Mail-Postfach mit IMAP-Zugang**, in dem die Versandmails ankommen
- Für DHL-Live-Daten: ein kostenloses Konto auf developer.dhl.com
- Für UPS-Live-Daten: ein kostenloses UPS-Konto und ein Zugang auf developer.ups.com

---

## 3. Installation

1. Laden Sie die Datei `pakettracker-<Version>.zip` herunter (z.B. `pakettracker-1.0.0.zip`). **Entpacken Sie sie nicht.**
2. Öffnen Sie die LoxBerry-Weboberfläche und gehen Sie zu **Plugin-Verwaltung**.
3. Wählen Sie unter *Plugin installieren oder aktualisieren* die ZIP-Datei aus und klicken Sie auf **Installieren**.
4. Warten Sie, bis die Installation abgeschlossen ist. Im Installationsprotokoll sollten am Ende Meldungen mit **OK** stehen, z.B. „Pakettracker 1.0.0 installiert“.
   - Erscheint eine **Warnung** zu `python3-paho-mqtt`, konnte das MQTT-Modul nicht installiert werden. Das Plugin funktioniert trotzdem, nur ohne MQTT. Siehe [Fehlersuche](#22-logs-und-fehlersuche).
5. Das Plugin erscheint jetzt in der Plugin-Liste. Ein Klick darauf öffnet die Plugin-Oberfläche.

> Nach der Installation ist der **Testmodus** eingeschaltet. Es werden noch keine Paketdienste abgefragt. Sie können also gefahrlos alles einrichten.

Das **Update** einer bestehenden Installation ist in [Abschnitt 23](#23-backup-und-update) beschrieben.

---

## 4. Erste Inbetriebnahme

Wir empfehlen diese Reihenfolge:

| Schritt | Was | Wo | Abschnitt |
|---|---|---|---|
| 1 | Prüfen, ob MQTT läuft, und den Testmodus ausprobieren | Status → Jetzt aktualisieren | [6](#6-testmodus), [17](#17-mqtt-einrichten) |
| 2 | Eine Testsendung eintragen und in Loxone anzeigen | Sendungen, Loxone Config | [8](#8-sendungen-manuell-hinzufügen), [19](#19-einbindung-in-loxone) |
| 3 | E-Mail-Eingang einrichten und testen | Einstellungen → E-Mail-Eingang | [10](#10-e-mail-eingang-imap-einrichten) |
| 4 | Optional: DHL- und/oder UPS-Zugangsdaten eintragen | Einstellungen → Anbieter | [11](#11-dhl-einrichten), [16](#16-ups-einrichten) |
| 5 | Testmodus ausschalten | Einstellungen → Allgemein | [6](#6-testmodus) |
| 6 | Kontrollieren | Seite *Anbieter*, Seite *Status* | [22](#22-logs-und-fehlersuche) |

**Schnelltest in fünf Minuten:**
1. Plugin öffnen → **Sendungen** → Sendungsnummer `00340434000000000001` eintragen, Anbieter *Automatisch erkennen*, Beschreibung „Test“ → **Sendung hinzufügen**.
2. **Status** → **Jetzt aktualisieren**.
3. In der Tabelle *Loxone-Slots* steht jetzt in Slot 1 die Sendung „Test“ mit einem simulierten Status (z.B. „Angekündigt“).
4. Im LoxBerry **MQTT Gateway** → *Incoming Overview* erscheinen Einträge, die mit `pakettracker/` beginnen.

Funktioniert das, ist die Grundeinrichtung erledigt.

---

## 5. Die Weboberfläche im Überblick

Oben in der Plugin-Oberfläche finden Sie fünf Seiten:

| Seite | Inhalt |
|---|---|
| **Status** | Zeitpunkt der letzten Aktualisierung, Knopf **Jetzt aktualisieren**, Zusammenfassung (Anzahl Sendungen je Status), Zustand je Paketdienst, die Loxone-Slots und die letzten Zeilen des Logs |
| **Sendungen** | Sendungen von Hand eintragen oder entfernen, Liste aller aktuell bekannten Sendungen mit Link zur Sendungsverfolgung des Paketdienstes |
| **Einstellungen** | Allgemein, MQTT, REST, E-Mail-Eingang (mit Verbindungstest) und alle Paketdienste (aufklappbar, mit Verbindungstest für DHL und UPS) |
| **Anbieter** | Übersicht aller Paketdienste: aktiv, Datenquelle, Zugangsdaten, Zustand, letzter Erfolg, letzter Fehler, Anzahl Sendungen |
| **Hilfe** | Kurzanleitung mit den wichtigsten Schritten und der Knopf **Ausführliche Anleitung öffnen** (diese Anleitung) |

**Zustandsanzeigen auf den Seiten Status und Anbieter:**

| Anzeige | Bedeutung |
|---|---|
| **OK** | Der Paketdienst wurde zuletzt erfolgreich abgefragt bzw. das Postfach erfolgreich gelesen. |
| **Fehler** | Beim letzten Versuch ist ein Fehler aufgetreten. Der Text steht in der Spalte *Letzter Fehler*. |
| **Noch keine Daten** | Es gab noch keinen erfolgreichen Abruf, z.B. weil noch keine Sendung vorhanden ist. |
| **Nur E-Mail (Zugangsdaten fehlen)** | DHL bzw. UPS: Ohne API-Zugangsdaten werden nur Mails ausgewertet. Das ist kein Fehler. |
| **Keine Datenquelle** | Der Paketdienst kann keine Daten liefern, meist weil der E-Mail-Eingang ausgeschaltet ist und keine Zugangsdaten hinterlegt sind. |
| **Deaktiviert** | Der Paketdienst ist in den Einstellungen ausgeschaltet. |

Die Spalte **Datenquelle** zeigt die tatsächlich genutzte Quelle: *API* (z.B. DHL mit API-Key bei ausgeschaltetem E-Mail-Eingang), *E-Mail*, *API + E-Mail* oder *keine*. Darunter zeigt der Abschnitt **Live-Abfrage** je Paketdienst mit Schnittstelle, ob die Live-Abfrage aktiv ist, wann sie zuletzt erfolgreich war, einen eventuellen Fehler und – ohne Zugangsdaten – einen Hinweis, wo sie einzutragen sind. Gespeicherte Zugangsdaten werden nie angezeigt.

---

## 6. Testmodus

**Was ist der Testmodus?** Im Testmodus fragt das Plugin keine Paketdienste ab. Stattdessen erhält jede Sendung, die Sie eintragen, einen erfundenen Status. So können Sie MQTT, die Loxone-Slots und Ihre Visualisierung einrichten, ohne echte Zugangsdaten zu brauchen.

- Eingeschaltet ab Werk.
- Ein- und ausschalten: **Einstellungen → Allgemein → Testmodus (keine echten Anbieter-Abfragen)** → **Speichern**.
- Simulierte Statustexte beginnen immer mit **„[Testmodus]“**. Oben auf der Statusseite erscheint zusätzlich ein gelber Hinweis.
- Dieselbe Sendungsnummer bekommt immer denselben simulierten Status. Wenn Sie mehrere Nummern eintragen, sehen Sie verschiedene Status (angekündigt, unterwegs, in Zustellung, abholbereit, zugestellt).
- Der **E-Mail-Eingang arbeitet auch im Testmodus.** Ist er eingerichtet, werden echte Mails gelesen.
- Beim **Ausschalten** des Testmodus verwirft das Plugin einmalig alle simulierten Status. Die Sendungen selbst bleiben in der Liste und erhalten beim nächsten Lauf echte Daten.

---

## 7. Statuscodes 0–7

Jede Sendung hat einen einheitlichen Status, unabhängig vom Paketdienst. In Loxone kommt er als Zahl an (`status_code`), zusätzlich als deutscher Text (`status_label`).

| Code | Text | Bedeutung | Typische Auslöser |
|---|---|---|---|
| **0** | Unbekannt | Es liegt (noch) kein Status vor. Bei einem **leeren Slot** steht hier ebenfalls 0, dann ist `used` = 0. | Sendung gerade eingetragen; Paketdienst kennt die Nummer noch nicht |
| **1** | Angekündigt | Der Versender hat die Sendung angemeldet, sie ist aber noch nicht beim Paketdienst. | DHL „Sendungsdaten übermittelt“, Bestellbestätigung von Amazon, „Ihr Paket kommt am …“ |
| **2** | Unterwegs | Der Paketdienst hat die Sendung übernommen und transportiert sie. | „Versandt“, „im Paketzentrum bearbeitet“ |
| **3** | In Zustellung | Das Paket ist heute auf dem Zustellfahrzeug. | DHL „in das Zustellfahrzeug geladen“, Hermes „heute in Zustellung“, UPS „Out for Delivery“ |
| **4** | Zugestellt | Das Paket wurde zugestellt. | „Zugestellt“, „Delivered“ |
| **5** | Abholbereit | Das Paket liegt zur Abholung bereit (Filiale, Packstation, PaketShop, UPS Access Point). | GLS „liegt im PaketShop zur Abholung bereit“ |
| **6** | Problem | Es gibt ein Problem, z.B. einen gescheiterten Zustellversuch, eine Verzögerung oder eine falsche Adresse. | „Zustellversuch“, „nicht zugestellt“, UPS Exception |
| **7** | Rücksendung | Die Sendung geht an den Absender zurück. | „zurück an den Absender“, UPS „Returned to Shipper“ |

Hinweise:
- **Reihenfolge der Slots:** In Zustellung (3) → Abholbereit (5) → Problem (6) → Unterwegs (2) → Angekündigt (1) → Unbekannt (0) → heute zugestellt (4). Bei gleichem Status steht die Sendung mit dem früheren Zustelltermin vorne.
- **Abgeschlossene Sendungen:** Zugestellte Sendungen erscheinen nur am Tag der Zustellung in den Slots. Sendungen mit Status 7 erscheinen nicht in den Slots, nur in der Sendungsliste und per REST.
- **Wann eine Sendung verschwindet:** Zugestellte Sendungen werden nach *Zugestellte Sendungen behalten* (Standard: 1 Tag) aus der Liste entfernt. Sendungen ohne Neuigkeiten verschwinden nach *Sendungen ohne Aktualisierung entfernen nach* (Standard: 30 Tage). Von Hand eingetragene Sendungen bleiben in diesem Fall stehen.
- **Abgelaufene Sendungen (seit 1.0.1):** Ist der Zustelltermin verstrichen, kam seitdem keine neue Statusinformation und gibt es kein aktuelles Live-Tracking, gilt die Sendung als *abgelaufen* („stale“). Das betrifft vor allem reine E-Mail-Sendungen (Amazon, DPD, GLS, Hermes ohne Live-Abfrage), für die nie eine Zustellmail kam. Abgelaufene Sendungen erscheinen **nicht mehr** in den Slots, in `summary/active`, den Status-Zählern, `arriving_today`, `next_eta` und `provider/<id>/active`. Sie bleiben gespeichert, stehen unter *Sendungen → Abgelaufene Sendungen* und werden wie oben nach der Höchstdauer entfernt. Kommt eine neue Mail oder ein Live-Status, ist die Sendung wieder aktiv. Abholbereite Sendungen (Code 5) laufen nicht ab. Ihre Anzahl steht in `summary/stale`.
- **Live-Tracking hat Vorrang:** Liefert eine Live-Abfrage (DHL, UPS, Hermes mit Live-Abfrage) einen Status, gilt dieser vor jeder Mailprognose. Hat die Live-Abfrage in den letzten 48 Stunden erfolgreich geantwortet, läuft die Sendung nicht ab, auch wenn der ursprüngliche Termin vorbei ist – `eta_text` zeigt dann z.B. „verspätet – ursprünglicher Termin 01.10.“.
- **„heute“ und „morgen“ in Texten:** Statustexte aus Mails wie „In Zustellung – kommt heute“ werden bei jedem Lauf neu berechnet (Bezug: Tag der Mail, Kalendertage in Europe/Berlin). Am Folgetag steht dort nicht mehr „kommt heute“; aus „kommt morgen“ wird am nächsten Tag „kommt heute“.
- **Feste Codes:** Die Codes 0–7 ändern sich in künftigen Versionen nicht. Sie können sich in Loxone darauf verlassen.

---

## 8. Sendungen manuell hinzufügen

Sendungen aus Mails erscheinen automatisch. Von Hand eintragen müssen Sie eine Sendung nur, wenn Sie keine Mail bekommen oder den E-Mail-Eingang nicht nutzen, z.B. bei einer DHL-Nummer vom Verkäufer.

1. Plugin → **Sendungen** → Bereich *Sendung hinzufügen*.
2. **Anbieter:** *Automatisch erkennen* (siehe [Abschnitt 9](#9-automatische-anbieter-erkennung)) oder den Paketdienst direkt auswählen. Deaktivierte Paketdienste sind mit „(deaktiviert)“ gekennzeichnet; deren Sendungen werden nicht abgefragt.
3. **Sendungsnummer:** wie auf dem Beleg. Leerzeichen und Bindestriche werden entfernt, Kleinbuchstaben in Großbuchstaben umgewandelt. Erlaubt sind 6–40 Zeichen (A–Z, 0–9).
4. **Beschreibung (optional):** z.B. „Ersatzteil Waschmaschine“. Sie wird in Loxone als `description` angezeigt und hat Vorrang vor Beschreibungen aus Mails.
5. **Sendung hinzufügen** klicken.
6. Die Sendung erscheint nach der nächsten Aktualisierung in der Liste. Sofort geht es über **Status → Jetzt aktualisieren**.

**Sendung entfernen:** In der Liste *Manuell erfasste Sendungen* auf das Löschsymbol klicken. Die Sendung verschwindet beim nächsten Lauf, es sei denn, sie ist zusätzlich aus einer Mail bekannt.

**Eine manuelle Anbieterwahl hat immer Vorrang.** Meldet später z.B. eine Mail eines anderen Paketdienstes dieselbe Nummer, bleibt die Sendung bei dem Anbieter, den Sie gewählt haben.

---

## 9. Automatische Anbieter-Erkennung

Bei *Automatisch erkennen* bestimmt das Plugin den Paketdienst anhand des Nummernformats. Berücksichtigt werden nur **aktivierte** Paketdienste.

| Nummer (Beispiel) | Erkannt als | Sicherheit |
|---|---|---|
| `1Z999AA10123456784` (beginnt mit 1Z, 18 Zeichen) | UPS | eindeutig, Prüfziffer wird kontrolliert |
| `H1000…` (H + 19 Ziffern) | Hermes | eindeutig |
| `TBA…` (TBA + 12 Ziffern) | Amazon | eindeutig |
| `00340434…` (20 Ziffern, beginnt mit 0034) | DHL | eindeutig |
| `JJD…`, `JVGL…` | DHL | eindeutig |
| `RR123456785DE` (2 Buchstaben, 9 Ziffern, „DE“) | DHL / Deutsche Post | eindeutig, Prüfziffer wird kontrolliert |
| 11 Ziffern | GLS | wahrscheinlich |
| 8 Zeichen aus Buchstaben und Ziffern | GLS (Track-ID) | wahrscheinlich |
| **12 Ziffern** | **DHL oder GLS** | **mehrdeutig** |
| **14 Ziffern** | **Hermes oder DPD** | **mehrdeutig** |

**Was passiert bei mehrdeutigen Nummern?** Das Plugin wählt den verbreiteteren Paketdienst (bei 12 Ziffern DHL, bei 14 Ziffern Hermes) und zeigt eine Meldung wie *„Erkannt als DHL. Die Nummer ist nicht eindeutig (auch möglich: GLS)…“*. Ist die Wahl falsch:
1. Die Sendung in der Liste entfernen.
2. Neu eintragen und dabei den richtigen Paketdienst **manuell** auswählen.

**Nicht erkennbare Nummern** werden mit der Meldung *„Der Anbieter dieser Nummer ist nicht erkennbar – bitte manuell auswählen“* abgelehnt. Wählen Sie dann den Paketdienst von Hand aus.

Der erkannte Paketdienst wird fest gespeichert. Aktivieren Sie später weitere Paketdienste, ändert sich die Zuordnung bestehender Sendungen nicht.

---

## 10. E-Mail-Eingang (IMAP) einrichten

Der E-Mail-Eingang ist die Datenquelle für Amazon, Hermes, DPD und GLS und ergänzt DHL und UPS.

### 10.1 Vorbereitung

- **Wohin sollen die Paketmails?** Am einfachsten ist das Postfach, in dem die Mails ohnehin ankommen. Wenn Sie nicht möchten, dass das Plugin Ihren gesamten Posteingang sieht:
  - eine Postfachregel anlegen, die Mails der Paketdienste in einen eigenen Ordner (z.B. „Pakete“) verschiebt, und nur diesen Ordner eintragen, oder
  - ein eigenes Postfach verwenden und die Mails dorthin **umleiten**. Achtung, siehe den Hinweis zu Weiterleitungen in [Abschnitt 24](#24-bekannte-einschränkungen).
- **IMAP beim Mailanbieter freischalten.** Bei manchen Anbietern ist IMAP standardmäßig aus (z.B. GMX, WEB.DE: Einstellungen → POP3/IMAP Abruf).
- **App-Passwort erzeugen**, wenn Ihr Konto eine Zwei-Faktor-Anmeldung nutzt (Gmail, iCloud, Yahoo …). Das normale Passwort funktioniert dann nicht.

### 10.2 Typische Servereinstellungen

Bitte prüfen Sie die Werte im Zweifel in der Hilfe Ihres Mailanbieters.

| Anbieter | IMAP-Server | Port | Verschlüsselung | Hinweis |
|---|---|---|---|---|
| GMX | `imap.gmx.net` | 993 | ssl | IMAP in den GMX-Einstellungen aktivieren |
| WEB.DE | `imap.web.de` | 993 | ssl | IMAP in den WEB.DE-Einstellungen aktivieren |
| T-Online | `secureimap.t-online.de` | 993 | ssl | eigenes „E-Mail-Passwort“ im Kundencenter anlegen |
| Gmail | `imap.gmail.com` | 993 | ssl | App-Passwort nötig (Zwei-Faktor-Anmeldung) |
| iCloud | `imap.mail.me.com` | 993 | ssl | App-spezifisches Passwort nötig |
| Yahoo | `imap.mail.yahoo.com` | 993 | ssl | App-Passwort nötig |
| IONOS (1&1) | `imap.ionos.de` | 993 | ssl | |
| Strato | `imap.strato.de` | 993 | ssl | |
| Posteo | `posteo.de` | 993 | ssl | |
| mailbox.org | `imap.mailbox.org` | 993 | ssl | |
| Eigener Server | laut Anbieter | 993 oder 143 | ssl bzw. starttls | |
| Outlook.com / Hotmail | `outlook.office365.com` | 993 | ssl | **funktioniert in der Regel nicht**, siehe [Abschnitt 24](#24-bekannte-einschränkungen) |

**Benutzer** ist fast immer die vollständige E-Mail-Adresse.

### 10.3 Einstellungen im Plugin

Plugin → **Einstellungen** → Abschnitt **E-Mail-Eingang (Paketankündigungen)**:

| Feld | Empfehlung |
|---|---|
| E-Mails auswerten | an |
| Quelle | `imap` |
| IMAP-Server | siehe Tabelle |
| IMAP-Port | `993` (bei STARTTLS `143`) |
| Verschlüsselung | `ssl` (bei STARTTLS `starttls`; `none` nur in Ausnahmefällen im eigenen Netz) |
| IMAP-Benutzer | Ihre E-Mail-Adresse |
| IMAP-Passwort | Passwort bzw. App-Passwort. Nach dem Speichern wird es nie wieder angezeigt; ein leeres Feld behält den gespeicherten Wert. |
| Ordner | `INBOX` (Posteingang) oder mehrere mit Komma, z.B. `INBOX, Pakete`. Unterordner schreibt man je nach Server z.B. `INBOX/Pakete` oder `INBOX.Pakete`. |
| Zeitraum (Tage) | `14`. Beim ersten Abruf werden Mails dieses Zeitraums gelesen, danach nur neue. |
| Verarbeitete Mails markieren | aus (siehe unten) |

Dann **„Speichern & IMAP-Verbindung testen“** klicken. Erwartetes Ergebnis:

> Test IMAP: Anmeldung erfolgreich. Ordner 'INBOX': 230 Mails im Zeitraum, 4 von Paketdiensten

„4 von Paketdiensten“ bedeutet: Vier Mails stammen von Absendern aktivierter Paketdienste. Ist die Zahl 0, obwohl Paketmails vorhanden sind, prüfen Sie Ordner und Zeitraum.

Anschließend **Status → Jetzt aktualisieren**. Die gefundenen Sendungen erscheinen unter *Sendungen* mit der Quelle „email“.

### 10.4 Was das Plugin mit Ihren Mails macht und was nicht

- Es **liest nur.** Ordner werden schreibgeschützt geöffnet. Mails werden nie gelöscht, verschoben oder als gelesen markiert.
- Es lädt zunächst **nur den Absender** jeder Mail. Den Inhalt lädt es nur bei Mails von Paketdiensten, also z.B. von `amazon.de`, `dhl.de`, `deutschepost.de`, `myhermes.de`, `hermesworld.com`, `dpd.de`, `gls-pakete.de`, `gls-group.eu` und `ups.com`.
- Es merkt sich je Ordner, bis zu welcher Mail es gelesen hat, und liest **jede Mail nur einmal**. Liegt dieselbe Mail in zwei Ordnern, wird sie nur einmal ausgewertet.
- Mailinhalte werden **nirgends gespeichert und nie ins Log geschrieben.** Gespeichert werden nur die erkannten Sendungsdaten (Nummer, Status, Termin, Beschreibung, Bestellnummer).
- **Verarbeitete Mails markieren** (optional) setzt in Ihrem Postfach das Schlüsselwort `$Pakettracker`. Das Plugin selbst braucht das nicht. Es ist nur nützlich, wenn Sie in Ihrem Mailprogramm sehen möchten, was ausgewertet wurde. Nicht jeder Server unterstützt eigene Schlüsselwörter. Das Plugin öffnet den Ordner dafür mit Schreibrecht, setzt aber weiterhin nur dieses Schlüsselwort.

### 10.5 Testen ohne Postfach

Für Tests können Sie statt IMAP einen Ordner mit gespeicherten Mails (`.eml`-Dateien) verwenden: *Quelle* = `eml_dir`, *Ordner mit .eml-Dateien* = vollständiger Pfad auf dem LoxBerry.

---

## 11. DHL einrichten

DHL-Sendungen kommen auf zwei Wegen ins Plugin:
- **DHL-Schnittstelle (API):** Das Plugin fragt den aktuellen Status jeder DHL-Sendung direkt bei DHL ab. Das ist genauer und aktueller als die Mails.
- **E-Mail (optional):** DHL-Benachrichtigungen („Ihr Paket kommt am …“) werden automatisch erkannt, wenn der E-Mail-Eingang eingerichtet ist.

**DHL ganz ohne E-Mail:** Zugangsdaten hinterlegen (11.2–11.4) und die Sendungsnummer unter *Sendungen → Sendung hinzufügen* eintragen (Anbieter „Automatisch erkennen“ oder „DHL“). Das Plugin fragt die Sendung dann regelmäßig direkt bei DHL ab; ein E-Mail-Konto ist nicht nötig.

Übernommen werden, soweit DHL sie für Ihren Zugang liefert: Status, Statustext, Sendungsverlauf (Zeit, Text, Ort), voraussichtlicher Zustelltag und -zeitfenster. Fehlende Angaben werden nicht ergänzt oder geschätzt. Zugestellte Sendungen werden nicht weiter abgefragt. Schlägt eine Abfrage fehl (Zugang abgelehnt, Netzwerk, Rate-Limit, Wartung), bleiben die zuletzt bekannten Daten erhalten.

### 11.1 Zwei DHL-Schnittstellen

| | Shipment Tracking – Unified | Parcel DE Tracking (Post & Parcel Germany) |
|---|---|---|
| Für | alle DHL-Sendungen (Paket, Express, international) | DHL Paket Deutschland, Warenpost, Retouren, Importsendungen |
| Zugang | API-Key einer App auf developer.dhl.com (Self-Service, DHL prüft den Antrag) | API-Key **und** API-Secret einer App. **Die produktive Nutzung schaltet DHL frei.** Je nach Abschnitt der DHL-Dokumentation sind zusätzlich eine **Benutzerkennung und ein Passwort** nötig, die DHL (Kundenberater) vergibt |
| Abfrage im Plugin | `GET …/track/shipments` mit Header `DHL-API-Key` | „public“-Abfrage `get-status-for-public-user`: `GET …/parcel/de/tracking/v0/shipments?xml=…` mit Basic-Auth (API-Key/API-Secret) |
| Daten | Status, Text, Verlauf, Termin/Zeitfenster soweit vorhanden | wie die öffentliche Sendungsverfolgung auf dhl.de; mit Empfänger-PLZ zusätzlich Ort und Adresse von Filiale/Packstation; Zustelltag/-zeitfenster nur mit **gesondertem Recht** bei DHL; genauere Einordnung über DHL-Ereigniscodes |
| Kontingent laut DHL | 250 Abfragen/Tag, 1 Abfrage je 5 s (kostenlos) | 1000 Abfragen/Tag, 3 je Sekunde |
| Sandbox | – | Die Sandbox ist für Nicht-Geschäftskunden direkt nutzbar, kann laut DHL die public-Abfrage aber **nicht** ausführen – das Plugin nutzt daher nur die Produktion |

**Welche wird genutzt?** Einstellung *DHL-Schnittstelle*:
- **Automatisch** (Standard): Parcel DE Tracking, sobald ein API-Secret hinterlegt ist, sonst Shipment Tracking – Unified. Lehnt DHL den Parcel-DE-Zugang ab (HTTP 401/403 oder „Anmeldung fehlgeschlagen“), wird Parcel DE für 6 Stunden pausiert und dieselbe Abfrage einmal über Unified gestellt. Temporäre Fehler (Wartung, Netzwerk) oder unbekannte Sendungen lösen keine zweite Abfrage aus.
- **Parcel DE Tracking** bzw. **Shipment Tracking – Unified**: nur diese Schnittstelle, ohne Ausweichen.

**Als Privatkunde:** Ob DHL einem Privatkunden Parcel DE Tracking in der Produktion nur mit API-Key/API-Secret freischaltet, sagt die Dokumentation nicht eindeutig (siehe oben). Der zuverlässige Weg ist Shipment Tracking – Unified. Parcel DE lohnt sich, wenn DHL Ihre App dafür freigegeben hat. Die Business-Abfrage für Geschäftskunden (GKP-Benutzer mit „Verfolgen Paket & Waren“) liefert nur Sendungen aus dem eigenen Nummernkreis – für empfangene Pakete ist sie ungeeignet und wird nicht verwendet.

### 11.2 Zugang für Shipment Tracking – Unified

1. Auf **developer.dhl.com** ein Benutzerkonto anlegen. Tragen Sie im Profil einen **Firmen- oder Projektnamen** ein (z.B. „Smart Home Mustermann“). DHL prüft jeden Antrag von Hand und lehnt Konten ohne diese Angabe eher ab.
2. Anmelden → **My Apps** → **Create App** (oder auf der Seite der API „Shipment Tracking – Unified“ auf *Get Access* klicken).
3. Einen App-Namen vergeben, z.B. „LoxBerry Pakettracker“.
4. Unter **Select APIs** die API **„Shipment Tracking – Unified“** auswählen und speichern.
5. Auf die Freigabe durch DHL warten. Der Status der App wechselt auf *Approved*. Das kann einige Zeit dauern.
6. **My Apps** → App anklicken → bei der API unter den Sternchen auf **Show** klicken → den **Consumer Key** (API-Key) kopieren.

### 11.3 Zugang für Parcel DE Tracking (optional)

1. Auf developer.dhl.com bei der API **„Parcel DE Tracking (Post & Parcel Germany)“** auf *Get Access* klicken oder in **My Apps** die App um diese API erweitern. In der Liste stehen zwei Einträge – Sandbox und Produktion; für das Plugin wird die **Produktion** gebraucht.
2. Die Freischaltung der Produktion abwarten bzw. bei DHL anfragen („Die produktive Verwendung wird durch DHL freigeschaltet“).
3. In **My Apps** **API-Key** und **API-Secret** dieser App kopieren. Key und Secret gelten für alle APIs der App – ist dieselbe App auch für Unified freigegeben, genügt ein API-Key.
4. Hat DHL Ihnen eine **Benutzerkennung** und ein **Passwort** für die Sendungsverfolgung gegeben, diese ebenfalls eintragen. Sonst die Felder leer lassen.

### 11.4 Im Plugin eintragen

Plugin → **Einstellungen** → Bereich *Anbieter* → **DHL** aufklappen:

| Feld | Bedeutung |
|---|---|
| Aktiviert | an |
| API-Key (DHL Developer App) | der Consumer Key (für beide Schnittstellen) |
| DHL-Schnittstelle | *Automatisch* (empfohlen), *Parcel DE Tracking* oder *Shipment Tracking – Unified* |
| API-Secret (nur Parcel DE Tracking) | Secret derselben App; leer = Parcel DE wird nicht genutzt |
| Tracking-Benutzerkennung / Tracking-Passwort | nur, falls von DHL vergeben; immer beide oder keines |
| Sprache der Statustexte | `de` |
| Postleitzahl des Empfängers (optional) | Ihre PLZ (5 Ziffern). Wird nur an DHL übertragen und nur bei Einzelabfragen mitgeschickt. Parcel DE liefert damit z.B. Ort und Adresse von Filiale/Packstation. Passt die PLZ nicht zur Sendung, meldet DHL „Zur angegebenen PLZ sind keine Informationen verfügbar“. |
| Mindestabstand je Sendung (Minuten) | `60` (siehe Kontingent) |
| Max. API-Abfragen pro Tag | `250` (kostenloser Unified-Zugang; gilt für beide Schnittstellen zusammen) |

Alle Zugangsdaten landen in `credentials.json` (Dateirechte 0600), werden nie angezeigt, protokolliert, per MQTT oder REST ausgegeben. Bei Parcel DE schreibt DHL vor, Benutzerkennung und Passwort im XML-Parameter der (verschlüsselten HTTPS-)Adresse zu übertragen; das Plugin protokolliert diese Adresse nicht.

Dann **„Speichern & Verbindung testen“** klicken. Getestet wird jede konfigurierte Schnittstelle (je 1 Abfrage). Ist eine aktive DHL-Sendung in der Liste, wird mit ihr getestet, sonst mit einer nicht existierenden Testnummer. Beispiele:
- *„Parcel DE Tracking: ✓ API erreichbar · ✓ Authentifizierung erfolgreich · ✓ Sendungsdaten empfangen (Unterwegs)“*
- *„Shipment Tracking – Unified: ✓ API erreichbar · ✓ Authentifizierung erfolgreich · Sendung unbekannt“* (Testnummer – erwartet)
- *„Parcel DE Tracking: ✗ DHL Parcel DE Tracking: Zugang abgelehnt (HTTP 401) …“*

Die Seite **Anbieter** zeigt im Abschnitt *Live-Abfrage*, welche Schnittstelle genutzt wird: „Parcel DE Tracking aktiv“ bzw. „Shipment Tracking – Unified aktiv“ erst nach einer erfolgreichen Antwort, vorher „… konfiguriert – noch keine erfolgreiche Abfrage“. Fehlt etwas, steht dort „DHL Live-Tracking nicht vollständig konfiguriert – fehlt: …“. Ist Parcel DE nach einer Ablehnung pausiert, werden Fehler und Pausenende angezeigt.

### 11.5 Kontingent

Das Plugin hält die DHL-Vorgaben automatisch ein (beide Schnittstellen teilen sich Zähler und Drosselung):
- **Mindestabstand:** Jede Sendung wird höchstens im *Mindestabstand* abgefragt (Standard 60 Minuten). Das gilt auch für **Jetzt aktualisieren**. Neu eingetragene Sendungen werden sofort abgefragt.
- **Pro Lauf:** höchstens 10 Abfragen, mit 5 Sekunden Abstand. Weitere Sendungen kommen im nächsten Lauf dran.
- **Tageszähler:** Ein eigener Zähler stoppt bei *Max. API-Abfragen pro Tag* und setzt sich um Mitternacht zurück.
- **Rate-Limit:** Meldet DHL „zu viele Anfragen“ (HTTP 429), legt das Plugin eine Pause ein (`Retry-After` bzw. 30 Minuten).
- **Zugestellte Sendungen** werden nicht mehr abgefragt (bei Parcel DE ausdrücklich von DHL vorgeschrieben).

Faustregel: Bei 60 Minuten Mindestabstand reicht das kostenlose Unified-Kontingent für etwa 10 gleichzeitig aktive DHL-Sendungen.

### 11.6 Fehlermeldungen beim Zugang

| Meldung | Bedeutung / was tun |
|---|---|
| „DHL hat die Authentifizierung mit HTTP 401 abgelehnt …“ (Unified) | Das DHL-Gateway hat den Key für Shipment Tracking – Unified nicht akzeptiert. Aus dem Fehler ist nicht erkennbar, ob der Key falsch ist oder die App nicht freigegeben – beides prüfen: Key vollständig kopiert, Produktions-Key, App in *My Apps* für „Shipment Tracking – Unified“ auf *Approved*. |
| „DHL Parcel DE Tracking: Zugang abgelehnt (HTTP 401/403) …“ | API-Key/API-Secret falsch, nicht dieselbe App, oder die App ist für Parcel DE Tracking (Produktion) noch nicht freigeschaltet. Auch hier ist die Ursache nicht unterscheidbar. |
| „… Anmeldung fehlgeschlagen (Code 5)“ | Das Gateway hat die App akzeptiert, die DHL-Sendungsverfolgung aber nicht die Anmeldung – Benutzerkennung/Passwort fehlen oder sind falsch. Bei DHL erfragen. |
| „… fehlender Berechtigung (Code 62/64)“ | Das Recht für diese Abfrage fehlt – bei DHL klären. |
| „… keine Daten gefunden (Code 100/200)“, „Sendung … nicht gefunden“ | DHL kennt die Sendung (noch) nicht. Bisherige Daten bleiben erhalten. |

### 11.7 Ohne API-Key

Ohne API-Key zeigt die Seite *Anbieter* bei DHL „Nur E-Mail (Zugangsdaten fehlen)“ bzw. – bei ausgeschaltetem E-Mail-Eingang – „Keine Datenquelle“. DHL-Sendungen werden dann nur über Mails aktualisiert.

---

## 12. Amazon einrichten

Amazon bietet für Kunden keine Schnittstelle zur Sendungsverfolgung an. Das Plugin wertet deshalb die Mails von Amazon aus. Es meldet sich **nicht** bei amazon.de an.

1. E-Mail-Eingang einrichten ([Abschnitt 10](#10-e-mail-eingang-imap-einrichten)). Die Amazon-Mails müssen in den angegebenen Ordnern ankommen.
2. Plugin → **Einstellungen** → *Anbieter* → **Amazon**: *Aktiviert* an.
3. **Absender-Domains:** Standard `amazon.de, amazon.com`. Bestellen Sie auch in anderen Ländern, ergänzen Sie z.B. `amazon.at, amazon.fr`.
4. Speichern → **Status → Jetzt aktualisieren**.

**Was erkannt wird:**
- **Bestellnummer** (z.B. `302-1234567-1234567`). Sie verbindet die Mails einer Bestellung.
- **Artikelname** aus dem Betreff (z.B. `Versandt: „USB-C Kabel“`). Er wird zur Beschreibung der Sendung.
- **Liefertermin** (z.B. „Lieferung voraussichtlich: Samstag, 3. Oktober“) und **Status** (bestellt, versandt, heute in Zustellung, zugestellt …).
- **Amazon-Logistics-Nummer** (`TBA…`). Die Sendung erscheint dann unter „Amazon“.
- **Sendungsnummer eines anderen Paketdienstes**, wenn Amazon mit DHL, Hermes, DPD, GLS oder UPS verschickt. Die Sendung erscheint dann beim jeweiligen Paketdienst. Bei DHL und UPS übernimmt danach die Schnittstelle (sofern eingerichtet).

**Bestellungen ohne Sendungsnummer:** Nach der Bestellbestätigung kennt das Plugin nur die Bestellnummer. Es legt einen Platzhalter `ORDER-<Bestellnummer>` an (Status „Angekündigt“, mit Liefertermin). Kommt die Versandmail mit der echten Sendungsnummer, ersetzt diese den Platzhalter automatisch. Ein Duplikat entsteht dabei nicht.

---

## 13. Hermes einrichten

Hermes bietet eine offizielle Schnittstelle nur für Geschäftskunden mit Vertrag an. Das Plugin hat deshalb zwei Quellen, die sich ergänzen:

**A) Live-Abfrage über myhermes.de (empfohlen, ohne Zugangsdaten)**

1. Plugin → **Einstellungen** → *Anbieter* → **Hermes**: *Aktiviert* und **Live-Abfrage über myhermes.de** an.
2. Optional **Speichern & Verbindung testen**.
3. Sendungsnummer unter **Sendungen** eintragen.

Das Plugin fragt dann dieselbe Schnittstelle ab, die auch die Sendungsverfolgung auf myhermes.de nutzt: Status, Originaltext, Verlauf und das **Zustellzeitfenster** (z.B. „05.10.2026 10:00–14:00“). Übertragen wird nur die Sendungsnummer. Standardmäßig höchstens einmal pro Stunde je Sendung, zugestellte Sendungen gar nicht mehr.

> **Hinweis:** Diese Schnittstelle ist öffentlich, aber von Hermes nicht offiziell dokumentiert. Sie kann sich jederzeit ändern oder gesperrt werden. Dann erscheint unter *Anbieter* ein Fehler, und die Daten kommen weiter aus den Mails (B).

**B) Benachrichtigungsmails**

1. E-Mail-Benachrichtigungen bei Hermes aktivieren: Kundenkonto auf **myhermes.de** anlegen und dort die Benachrichtigungen per E-Mail einschalten. Viele Versender melden die Sendung zusätzlich direkt an Hermes. Dann kommen die Mails automatisch.
2. E-Mail-Eingang einrichten ([Abschnitt 10](#10-e-mail-eingang-imap-einrichten)).
3. Plugin → **Einstellungen** → *Anbieter* → **Hermes**: *Aktiviert* an.

**Erkannt werden** Mails von `myhermes.de` und `hermesworld.com`: Paketankündigung, „heute in Zustellung“ (mit Termin heute), Zustellung, Abgabe im PaketShop und Zustellprobleme. Hermes-Nummern haben die Form `H` + 19 Ziffern oder 14/16 Ziffern.

---

## 14. DPD einrichten

Die DPD-Schnittstellen sind Geschäftskunden vorbehalten. Das Plugin nutzt die DPD-Mails.

1. DPD-Benachrichtigungen per E-Mail aktivieren, z.B. über die **DPD-App** oder **myDPD**. Bei vielen Sendungen kommt die „Predict“-Mail mit dem Zustellfenster auch automatisch.
2. E-Mail-Eingang einrichten ([Abschnitt 10](#10-e-mail-eingang-imap-einrichten)).
3. Plugin → **Einstellungen** → *Anbieter* → **DPD**: *Aktiviert* an.

**Erkannt werden** Mails von `dpd.de` und `dpd.com`: Ankündigung mit Zustelltag (z.B. „Ihr DPD Paket kommt am 06.10.2026“), Zustellung, Abgabe im Pickup-Paketshop und Zustellprobleme. DPD-Paketnummern sind 14-stellig, auch mit Leerzeichen geschrieben („0123 4567 8901 23“).

---

## 15. GLS einrichten

Die GLS-Schnittstelle erfordert ein Versenderkonto mit Vertrag. Das Plugin nutzt die GLS-Mails.

1. GLS-Benachrichtigungen per E-Mail aktivieren, z.B. über **gls-pakete.de** oder die GLS-App.
2. E-Mail-Eingang einrichten ([Abschnitt 10](#10-e-mail-eingang-imap-einrichten)).
3. Plugin → **Einstellungen** → *Anbieter* → **GLS**: *Aktiviert* an.

**Erkannt werden** Mails von `gls-pakete.de`, `gls-group.eu`, `gls-group.com` und `gls-germany.com`: Ankündigung, Zustellung, „liegt im PaketShop zur Abholung bereit“ und Zustellprobleme. GLS-Nummern sind 11 oder 12 Ziffern lang oder eine 8-stellige Track-ID aus Buchstaben und Ziffern.

---

## 16. UPS einrichten

UPS-Sendungen kommen wie bei DHL über Mails und über die offizielle UPS-Schnittstelle.

### 16.1 Zugangsdaten besorgen

1. Ein kostenloses UPS-Konto auf ups.com anlegen (falls noch nicht vorhanden).
2. Mit diesem Konto auf **developer.ups.com** anmelden.
3. **Apps** → **Add Apps** (bzw. *Create Application*). Als Zweck die Sendungsverfolgung angeben.
4. Der App das Produkt **Tracking** hinzufügen und speichern.
5. In der App unter *Credentials* die **Client ID** und das **Client Secret** kopieren.

### 16.2 Im Plugin eintragen

Plugin → **Einstellungen** → *Anbieter* → **UPS** aufklappen:

| Feld | Bedeutung |
|---|---|
| Aktiviert | an |
| Client-ID | aus der UPS-App (wird wie ein Passwort behandelt und nie wieder angezeigt) |
| Client-Secret | aus der UPS-App |
| Umgebung | `production`. `test` ist die UPS-Testumgebung, die nur Beispieldaten liefert. |
| Sprache der Statustexte | `de` |
| Mindestabstand je Sendung / Max. API-Abfragen pro Tag | wie bei DHL, Standard 60 Minuten / 250 |

Dann **„Speichern & Verbindung testen“** klicken. Der Test meldet sich nur bei UPS an und verbraucht keine Tracking-Abfrage. Erwartet: *„UPS-Anmeldung erfolgreich (Produktion, Token erhalten …)“*.

UPS-Nummern beginnen mit `1Z` und sind 18 Zeichen lang. UPS-Mails (`ups.com`) werden zusätzlich ausgewertet. Ohne Zugangsdaten arbeitet UPS nur über E-Mail.

---

## 17. MQTT einrichten

MQTT ist der empfohlene Weg zu Loxone. Das Plugin schickt seine Werte an den MQTT-Broker des LoxBerry. Das **MQTT Gateway** des LoxBerry leitet sie an den Miniserver weiter.

1. **LoxBerry → MQTT Gateway** öffnen und prüfen, ob Broker und Gateway laufen. In den Gateway-Einstellungen muss Ihr Miniserver eingetragen sein.
2. **Abonnement:** Das Gateway muss die Topics des Plugins abonnieren.
   - **MQTT Gateway V1** (Standard): übernimmt das Abonnement `pakettracker/#` automatisch aus dem Plugin. Sie müssen nichts tun.
   - **MQTT Gateway V2:** liest diese Plugin-Datei nicht. Legen Sie im Gateway eine Subscription `pakettracker/#` an. Haben Sie das Basis-Topic im Plugin geändert, verwenden Sie dieses.
3. Plugin → **Einstellungen** → **MQTT**:

| Feld | Empfehlung |
|---|---|
| MQTT-Ausgabe aktiv | an |
| Broker von LoxBerry verwenden | an (Zugangsdaten kommen automatisch vom LoxBerry) |
| Broker-Host / Port / Benutzer / Passwort | nur nötig, wenn Sie einen anderen Broker verwenden |
| Basis-Topic | `pakettracker` |
| Retained senden | an. Der Broker behält den letzten Wert, sodass Loxone nach einem Neustart sofort den aktuellen Stand hat (gilt für Werte mit Inhalt, siehe [Abschnitt 18](#18-wichtige-mqtt-topics)). |
| Anzahl Slots für Loxone | `5` (0–20) |

4. **Status → Jetzt aktualisieren** → im MQTT Gateway unter **Incoming Overview** nach `pakettracker` suchen. Dort sehen Sie alle Werte und die Namen, unter denen sie an Loxone gehen.

Ist kein Broker erreichbar, protokolliert das Plugin einen Fehler. Die Oberfläche und die REST-API funktionieren weiter.

---

## 18. Wichtige MQTT-Topics

Alle Topics beginnen mit dem Basis-Topic (Standard `pakettracker`).

> **Leere Werte:** Werte **mit Inhalt** speichert der Broker (retained). Ein **leerer** Wert – z.B. `error` ohne Fehler, `last_success` vor dem ersten Erfolg oder die Texte eines leeren Slots – löscht nach MQTT-Standard den gespeicherten Wert, statt einen leeren zu speichern. Das MQTT Gateway erhält den leeren Wert trotzdem sofort; nur wer sich später neu verbindet, findet für dieses Topic nichts. Für Loxone heißt das: Ein Topic, das fehlt, gilt als leer.

### 18.1 Zusammenfassung

| Topic | Inhalt | Beispiel |
|---|---|---|
| `pakettracker/summary/active` | Anzahl noch nicht zugestellter Sendungen | `3` |
| `pakettracker/summary/announced` | davon angekündigt | `1` |
| `pakettracker/summary/in_transit` | davon unterwegs | `1` |
| `pakettracker/summary/out_for_delivery` | davon heute in Zustellung | `1` |
| `pakettracker/summary/pickup_ready` | davon abholbereit | `0` |
| `pakettracker/summary/exception` | davon mit Problem | `0` |
| `pakettracker/summary/delivered_today` | heute zugestellt | `2` |
| `pakettracker/summary/arriving_today` | aktive Sendungen mit Termin heute | `1` |
| `pakettracker/summary/next_eta` | nächster Zustelltermin ab heute (JJJJ-MM-TT, leer wenn unbekannt) | `2026-10-05` |
| `pakettracker/summary/stale` | abgelaufene Sendungen (Termin verstrichen, keine neue Info – nicht in `active` enthalten) | `1` |

### 18.2 Slots (feste Plätze für Loxone)

Loxone kann keine wechselnden Listen verarbeiten. Deshalb stehen die wichtigsten Sendungen in festen „Slots“ 1 bis N, die wichtigste in Slot 1 (Reihenfolge siehe [Abschnitt 7](#7-statuscodes-07)).

| Topic | Inhalt | Beispiel |
|---|---|---|
| `pakettracker/slot/1/used` | 1 = belegt, 0 = leer | `1` |
| `pakettracker/slot/1/status_code` | Statuscode 0–7 | `3` |
| `pakettracker/slot/1/status_label` | Status als Text | `In Zustellung` |
| `pakettracker/slot/1/status_text` | Text des Paketdienstes; „heute/morgen“ wird bei jedem Lauf neu berechnet | `Die Sendung wurde in das Zustellfahrzeug geladen.` |
| `pakettracker/slot/1/description` | Beschreibung | `USB-C Kabel 2m` |
| `pakettracker/slot/1/eta` | Termin (JJJJ-MM-TT) | `2026-10-02` |
| `pakettracker/slot/1/eta_window` | Zustellzeitfenster (Ortszeit), leer wenn unbekannt – derzeit von Hermes (Live-Abfrage), DHL und UPS | `10:00–14:00` |
| `pakettracker/slot/1/eta_text` | Termin als Text, bei jedem Lauf neu: `kommt heute`, `kommt morgen`, `kommt am Fr 09.10.`, bei verspäteten Live-Sendungen `verspätet – ursprünglicher Termin 01.10.`; leer ohne Termin | `kommt heute` |
| `pakettracker/slot/1/provider` | Paketdienst | `dhl` |
| `pakettracker/slot/1/tracking_number` | Sendungsnummer | `00340434…` |
| `pakettracker/slot/1/status` | Status als Schlüsselwort | `out_for_delivery` |

Dasselbe gilt für `slot/2`, `slot/3` usw. Leere Slots haben `used` = 0, `status_code` = 0 und leere Texte. Wird eine Sendung entfernt oder läuft sie ab, rückt die nächste Sendung nach; ein frei gewordener Slot wird bei jedem Lauf mit `used` = 0 und leeren Texten überschrieben – in Loxone bleibt kein alter Text stehen.

### 18.3 Je Paketdienst

`<id>` ist `dhl`, `ups`, `amazon`, `hermes`, `dpd` oder `gls` (bzw. `fedex`, `tnt`). Gesendet wird nur für aktivierte Paketdienste.

| Topic | Inhalt |
|---|---|
| `pakettracker/provider/<id>/active` | aktive Sendungen dieses Paketdienstes (ohne abgelaufene) |
| `pakettracker/provider/<id>/shipment_count` | alle Sendungen dieses Paketdienstes in der Liste (inkl. heute zugestellt) |
| `pakettracker/provider/<id>/error` | aktueller Fehlertext; **leer = alles in Ordnung** (leer wird nicht gespeichert, siehe oben) |
| `pakettracker/provider/<id>/last_success` | Zeitpunkt des letzten erfolgreichen Abrufs (ISO-Format, UTC) |

### 18.4 Allgemein

| Topic | Inhalt |
|---|---|
| `pakettracker/updated` | Zeitpunkt der letzten Aktualisierung (ISO, UTC) |
| `pakettracker/updated_epoch` | dasselbe als Unix-Zeitstempel (Sekunden) |
| `pakettracker/mock_mode` | 1 = Testmodus aktiv |
| `pakettracker/json` | Zusammenfassung, Anbieter und Slots als JSON, z.B. für andere Systeme |

---

## 19. Einbindung in Loxone

### 19.1 Grundprinzip

Das MQTT Gateway schickt jeden empfangenen Wert an den Miniserver, als **virtuellen Eingang** mit einem Namen, der aus dem Topic gebildet wird. Aus `/` wird dabei `_`. Aus `pakettracker/summary/active` wird so `pakettracker_summary_active`.

> Maßgeblich ist der Name, den das MQTT Gateway in der *Incoming Overview* anzeigt. Übernehmen Sie ihn exakt, inklusive Groß- und Kleinschreibung.
>
> Topics mit leerem Wert (z.B. `…_error` ohne Fehler) erscheinen dort erst, wenn sie einmal einen Inhalt hatten. Legen Sie die virtuellen Eingänge trotzdem an – Loxone erhält leere Werte im laufenden Betrieb.

- **Zahlenwerte** (`status_code`, `active`, `used` …): **virtueller Eingang** (analog)
- **Textwerte** (`status_label`, `description`, `eta`, `error` …): **virtueller Texteingang**

### 19.2 Beispiel: „Heute kommt ein Paket“

In **Loxone Config**:
1. Im Peripheriebaum *Virtuelle Eingänge* einen **virtuellen Eingang** anlegen:
   - Bezeichnung: `pakettracker_summary_out_for_delivery`
   - Als digitaler Eingang verwenden: nein (analog)
   - Min/Max: 0 / 20
2. Den Eingang auf die Programmierseite ziehen und mit einem Vergleich `> 0` verbinden.
3. Den Ausgang z.B. an einen **Status**-Baustein („Heute kommt ein Paket“) oder einen **Push-Benachrichtigungs**-Baustein anschließen.

### 19.3 Beispiel: Anzeige von Slot 1 in der App

| Virtueller Eingang (Loxone) | Typ | Verwendung |
|---|---|---|
| `pakettracker_slot_1_used` | virtueller Eingang (digital) | Slot belegt? |
| `pakettracker_slot_1_status_code` | virtueller Eingang (analog, 0–7) | Status als Zahl, z.B. für Farben/Logik |
| `pakettracker_slot_1_status_label` | virtueller Texteingang | „In Zustellung“ |
| `pakettracker_slot_1_description` | virtueller Texteingang | „USB-C Kabel 2m“ |
| `pakettracker_slot_1_eta` | virtueller Texteingang | „2026-10-02“ |

**Status-Baustein** mit dem Eingang `pakettracker_slot_1_status_code`:

| Bedingung | Anzeige |
|---|---|
| = 0 | „Keine Sendung“ |
| = 1 | „Paket angekündigt“ |
| = 2 | „Paket unterwegs“ |
| = 3 | „Paket kommt heute“ |
| = 4 | „Paket zugestellt“ |
| = 5 | „Paket abholbereit“ |
| = 6 | „Problem bei der Zustellung“ |

### 19.4 Weitere Ideen

- `pakettracker_summary_pickup_ready` > 0 → abends erinnern: „Paket abholen“.
- `pakettracker_summary_delivered_today` steigt → Benachrichtigung „Paket wurde zugestellt“.
- `pakettracker_provider_dhl_error` ist nicht leer → Hinweis an den Admin.
- `pakettracker_mock_mode` = 1 → in der Visualisierung „Testdaten“ anzeigen.

**Tipp:** Richten Sie alles im **Testmodus** ein. Tragen Sie dafür mehrere Testnummern ein, damit alle Slots belegt sind.

### 19.5 Alternative ohne MQTT: virtueller HTTP-Eingang

Siehe [Abschnitt 20.4](#204-beispiel-für-loxone-virtueller-http-eingang).

---

## 20. REST-API und REST-Token

### 20.1 Wofür?

Die REST-API stellt dieselben Daten wie MQTT über eine Web-Adresse bereit. Das ist nützlich, wenn Sie kein MQTT verwenden möchten oder andere Systeme die Daten abfragen sollen. Sie ist ohne LoxBerry-Anmeldung erreichbar und deshalb durch einen **Token** geschützt, eine Art Passwort in der Adresse.

### 20.2 Einrichtung

Plugin → **Einstellungen** → **REST / HTTP**:
- **REST-Schnittstelle aktiv:** an
- **Token erforderlich:** an (dringend empfohlen)
- **Zugriffs-Token:** wird bei der Installation zufällig erzeugt und hier angezeigt. Sie können einen eigenen eintragen. Danach müssen alle Adressen angepasst werden, die den alten Token nutzen.

Unten auf der Einstellungsseite stehen fertige Beispiel-Adressen mit Ihrem Token zum Anklicken.

| Adresse (an `http://<loxberry>/plugins/pakettracker/api.php` anhängen) | Inhalt |
|---|---|
| `?q=summary&token=…` | Zusammenfassung und Daten je Paketdienst |
| `?q=slots&token=…` | alle Slots |
| `?q=slot&n=1&token=…` | ein Slot |
| `?q=shipments&token=…` | alle Sendungen |
| `?q=all&token=…` | alles |

Mit `&format=text` kommt statt JSON eine einfache Liste `schlüssel=wert`, eine Zeile pro Wert, z.B.:

```
summary.active=3
summary.out_for_delivery=1
providers.dhl.active=2
providers.dhl.error=
```

### 20.3 Einzelwerte für Loxone (ab 0.2.3)

Mit `&field=…` liefert die API **genau einen Wert**, ohne Feldnamen, ohne JSON und ohne HTML. So braucht Loxone keine Befehlserkennung mit Schlüssel und keine JSON-Auswertung.

| Adresse (an `http://<loxberry>/plugins/pakettracker/api.php` anhängen) | Antwort (Beispiel) |
|---|---|
| `?q=summary&field=active&format=text&token=…` | `2` |
| `?q=summary&field=out_for_delivery&format=text&token=…` | `1` |
| `?q=summary&field=delivered_today&format=text&token=…` | `0` |
| `?q=slot&n=1&field=used&format=text&token=…` | `1` |
| `?q=slot&n=1&field=status_code&format=text&token=…` | `3` |
| `?q=slot&n=1&field=provider&format=text&token=…` | `dhl` |
| `?q=slot&n=1&field=description&format=text&token=…` | `Bücher & Kaffeetasse` |
| `?q=slot&n=1&field=status_label&format=text&token=…` | `In Zustellung` |
| `?q=slot&n=1&field=eta&format=text&token=…` | `2026-10-03` |

Mögliche Felder:
- **`q=summary`:** `active`, `announced`, `in_transit`, `out_for_delivery`, `pickup_ready`, `exception`, `delivered_today`, `arriving_today`, `next_eta`
- **`q=slot&n=<Nummer>`:** `used`, `provider`, `description`, `status_code`, `status`, `status_label`, `status_text`, `eta` (Format JJJJ-MM-TT), `eta_window` (z.B. `10:00–14:00`), `tracking_number`

Regeln für `format=text`:
- Die Antwort ist UTF-8-Klartext und endet mit genau einem Zeilenumbruch.
- Leerzeichen am Anfang und Ende werden entfernt, Zeilenumbrüche im Text werden zu Leerzeichen.
- HTML-Entities wie `&amp;` oder `&#x20;` werden in normale Zeichen umgewandelt.
- **Leerer Slot:** Zahlenfelder (`used`, `status_code`) liefern `0`, Textfelder eine leere Antwort.
- Ohne `&format=text` kommt JSON, z.B. `{"q":"slot","n":1,"field":"status_code","value":3}`.

Fertige Adressen mit Ihrer LoxBerry-Adresse und, falls nötig, Ihrem Token stehen im Plugin unter **Hilfe → Loxone per HTTP/REST**.

| Antwortcode | Bedeutung |
|---|---|
| 200 | OK |
| 400 | Unbekannte Abfrage, unbekanntes Feld oder ungültiger Slot (bei `field=…`) |
| 403 | REST-Schnittstelle ausgeschaltet, oder Token fehlt bzw. ist falsch |
| 404 | Slot nicht vorhanden (nur bei Abfragen ohne `field=…`) |
| 405 | Andere Methode als GET (die API ist nur lesend) |
| 503 | Noch keine Daten vorhanden (es lief noch keine Aktualisierung) oder kein Token konfiguriert |

Bis Version 0.2.2 hat eine ausgeschaltete REST-Schnittstelle mit 404 geantwortet, ab 0.2.3 mit 403.

### 20.4 Beispiel für Loxone: virtueller HTTP-Eingang

**Ein Wert je Eingang (empfohlen):**

1. Loxone Config → **Peripherie** → **Virtuelle Eingänge** markieren → **Virtueller HTTP Eingang**:
   - Bezeichnung: z.B. `Paket_Anzahl_Aktiv`
   - URL: `http://<loxberry>/plugins/pakettracker/api.php?q=summary&field=active&format=text&token=<IHR-TOKEN>`
   - Abfragezyklus: `300` Sekunden (das Plugin aktualisiert ohnehin nur alle paar Minuten)
2. Den neuen Eingang markieren → **Virtueller HTTP Eingang Befehl**:
   - Bezeichnung: `Paket_Anzahl_Aktiv`
   - Befehlserkennung: `\v`
3. Den Befehl in die Programmierung ziehen, in den Miniserver speichern.

**Alle Zahlen mit einer Abfrage:** URL `…/api.php?q=summary&format=text&token=<IHR-TOKEN>`, darunter je Wert ein Befehl:

| Bezeichnung | Befehlserkennung |
|---|---|
| Pakete aktiv | `summary.active=\v` |
| Pakete heute | `summary.out_for_delivery=\v` |
| Pakete abholbereit | `summary.pickup_ready=\v` |

Empfohlene Eingänge:

| Name in Loxone | Abfrage | Loxone-Baustein |
|---|---|---|
| Paket_Anzahl_Aktiv | `q=summary&field=active` | virtueller HTTP-Eingang (Zahl) |
| Paket_In_Zustellung | `q=summary&field=out_for_delivery` | virtueller HTTP-Eingang (Zahl) |
| Paket_Heute_Zugestellt | `q=summary&field=delivered_today` | virtueller HTTP-Eingang (Zahl) |
| Paket1_Aktiv | `q=slot&n=1&field=used` | virtueller HTTP-Eingang (0/1) |
| Paket1_Status | `q=slot&n=1&field=status_code` | virtueller HTTP-Eingang (0–7) |
| Paket1_Anbieter | `q=slot&n=1&field=provider` | virtueller Texteingang |
| Paket1_Beschreibung | `q=slot&n=1&field=description` | virtueller Texteingang |
| Paket1_Lieferdatum | `q=slot&n=1&field=eta` | virtueller Texteingang |

Für Paket 2 und 3 gilt dasselbe mit `n=2` bzw. `n=3`. An jede Abfrage `&format=text&token=<IHR-TOKEN>` anhängen.

**Einschränkung:** Virtuelle HTTP-Eingänge in Loxone lesen nur **Zahlen**. Einen Text kann der Miniserver nicht selbst per HTTP abholen. Ein virtueller Texteingang wird immer von außen beschrieben, z.B. vom MQTT Gateway. Die Text-Adressen eignen sich zum Prüfen im Browser und für andere Systeme (Node-RED, Skripte).

---

## 21. Sicherheit und Umgang mit Zugangsdaten

- **Speicherort:** Alle Zugangsdaten (DHL-API-Key, UPS-Client-ID und -Secret, IMAP-Passwort, MQTT-Passwort, REST-Token) liegen ausschließlich auf Ihrem LoxBerry in der Datei `/opt/loxberry/config/plugins/pakettracker/credentials.json`. Nur der LoxBerry-Benutzer darf sie lesen (Dateirechte 0600). Im Programmcode und im Installationspaket stehen keine Zugangsdaten.
- **Anzeige in der Oberfläche:** Nach dem Speichern werden Passwörter und Keys **nie wieder angezeigt**, das Feld zeigt nur „gespeichert“. Bleibt das Feld leer, bleibt der gespeicherte Wert erhalten. Zum Löschen das Kästchen **„Gespeicherten Wert löschen“** anhaken und speichern.
- **Ausnahme REST-Token:** Er wird in der (passwortgeschützten) Plugin-Oberfläche angezeigt, weil Sie ihn für Loxone brauchen.
- **Logs:** Zugangsdaten, Tokens und Mailinhalte werden nicht protokolliert. Fehlermeldungen der Paketdienste werden vor dem Protokollieren um Geheimnisse bereinigt.
- **Formulare:** Die Plugin-Oberfläche ist durch die LoxBerry-Anmeldung und zusätzlich gegen untergeschobene Formularaufrufe (CSRF) geschützt.
- **An wen Daten gehen:**
  - an **DHL** bzw. **UPS** die Sendungsnummer (bei DHL optional Ihre PLZ)
  - an niemanden Ihre Mails, sie werden nur auf dem LoxBerry ausgewertet
- **Was gespeichert wird:** Sendungsnummer, Paketdienst, Status, Termin, Beschreibung (z.B. Artikelname aus dem Betreff) und Bestellnummer. Diese Daten gehen per MQTT/REST in Ihr Heimnetz. MQTT ist im Heimnetz in der Regel unverschlüsselt. Wer Artikelnamen als sensibel betrachtet, sollte das berücksichtigen.

**Empfehlungen:**
- **App-Passwort:** Für IMAP ein eigenes App-Passwort verwenden statt des Hauptpassworts. Sie können es jederzeit beim Mailanbieter widerrufen.
- **Postfach eingrenzen:** Möglichst einen eigenen Ordner oder ein eigenes Postfach für Paketmails nutzen.
- **Token schützen:** Den REST-Token nicht öffentlich weitergeben. Bei Verdacht einen neuen Token eintragen.
- **Keine Freigabe nach außen:** Den LoxBerry nicht ungeschützt aus dem Internet erreichbar machen.
- **Backups:** Backups enthalten `credentials.json` und gehören an einen sicheren Ort.

---

## 22. Logs und Fehlersuche

### 22.1 Wo sehe ich, was passiert?

1. **Seite Anbieter:** Zustand, letzter Erfolg und letzter Fehler je Paketdienst, dazu der Zustand des E-Mail-Eingangs.
2. **Seite Status:** „Letzte Aktualisierung“, ggf. die Fehleranzahl des letzten Laufs und „Letzter fehlerfreier Gesamtabruf“. Unten stehen die **letzten 60 Zeilen des Logs**.
3. **Jetzt aktualisieren** zeigt nach dem Lauf die komplette Ausgabe dieses Laufs.
4. **Log-Datei:** `/opt/loxberry/log/plugins/pakettracker/pakettracker.log`. Sie wird bei 512 KB rotiert, zwei ältere Dateien bleiben erhalten. Das LoxBerry-Logverzeichnis liegt im Arbeitsspeicher, **nach einem Neustart des LoxBerry sind die Logs leer.**

**Mehr Details:** Einstellungen → Allgemein → *Loglevel* = `debug`. Danach wieder auf `info` stellen.

### 22.2 Befehle per SSH (für Fortgeschrittene)

Melden Sie sich per SSH als Benutzer **`loxberry`** an, **nicht als root**. Würden die Befehle als root laufen, gehörten neu angelegte Dateien root, und das Plugin könnte sie danach nicht mehr schreiben.

```bash
cd /opt/loxberry/bin/plugins/pakettracker
python3 pakettracker.py run --force -v      # Lauf sofort ausführen, Ausgabe im Terminal
python3 pakettracker.py detect 1Z999AA10123456784   # Anbieter-Erkennung prüfen
python3 pakettracker.py test imap           # IMAP-Verbindung testen
python3 pakettracker.py test ups            # UPS-Anmeldung testen
python3 pakettracker.py test dhl            # DHL-Zugang testen (je konfigurierter Schnittstelle 1 Abfrage)
```

### 22.3 Häufige Probleme

| Problem | Ursache und Lösung |
|---|---|
| „Das Backend (pakettracker.py) antwortet nicht“ | Installation unvollständig. Plugin neu installieren (Einstellungen bleiben erhalten) und das Installationsprotokoll prüfen. |
| Keine Werte im MQTT Gateway | MQTT-Ausgabe aktiv? Broker läuft? Bei Gateway V2 die Subscription `pakettracker/#` anlegen. Im Log nach „MQTT:“ suchen. |
| Log: „python3-paho-mqtt ist nicht installiert“ | Per SSH `sudo apt install python3-paho-mqtt` ausführen oder das Plugin neu installieren. |
| Log: „In LoxBerry ist kein Broker konfiguriert“ | Im MQTT Gateway den Broker einrichten oder im Plugin einen eigenen Broker eintragen (*Broker von LoxBerry verwenden* aus). |
| IMAP-Test: „Anmeldung fehlgeschlagen“ | Benutzer bzw. Passwort falsch. Bei Zwei-Faktor-Anmeldung ein App-Passwort verwenden. IMAP beim Mailanbieter freischalten. |
| IMAP-Test: „nicht erreichbar“ / „Zeitüberschreitung“ | Server, Port und Verschlüsselung prüfen (993 + ssl oder 143 + starttls). Internetverbindung des LoxBerry prüfen. |
| IMAP-Test: „TLS-Fehler“ | Verschlüsselung passt nicht zum Port, oder das Zertifikat des Servers ist ungültig. |
| IMAP-Test: „Ordner nicht gefunden“ | Ordnernamen exakt wie im Postfach schreiben; Unterordner z.B. `INBOX/Pakete` oder `INBOX.Pakete`. |
| Amazon/Hermes/DPD/GLS: „Keine Datenquelle“ | E-Mail-Eingang ist aus oder nicht eingerichtet. |
| DHL: „DHL hat die Authentifizierung mit HTTP 401 abgelehnt“ bzw. „Parcel DE Tracking: Zugang abgelehnt“ | Key/Secret falsch kopiert, App noch nicht freigegeben oder der App die gewählte Schnittstelle nicht zugeordnet – Details in [Abschnitt 11.6](#116-fehlermeldungen-beim-zugang). |
| DHL: „Tageslimit erreicht“ / „Rate-Limit-Pause“ | Kontingent verbraucht. Das Plugin macht automatisch weiter (am nächsten Tag bzw. nach der Pause). *Mindestabstand je Sendung* erhöhen. |
| DHL/UPS: „Sendung … (noch) nicht gefunden“ | Die Sendung ist dem Paketdienst noch nicht bekannt (frisch angekündigt) oder die Nummer gehört zu einem anderen Paketdienst. Die bisherigen Daten bleiben erhalten. |
| UPS: „UPS lehnt die Anmeldung ab“ | Client-ID oder Secret falsch, oder der App fehlt das Produkt „Tracking“. Umgebung `production` gewählt? |
| Eine Sendung aus einer Mail fehlt | War der Absender wirklich der Paketdienst? Weitergeleitete Mails haben einen anderen Absender und werden nicht erkannt (siehe [Abschnitt 24](#24-bekannte-einschränkungen)). Liegt die Mail im eingetragenen Ordner und im Zeitraum? |
| Falscher Paketdienst erkannt | Sendung entfernen und mit manueller Anbieterwahl neu eintragen. |
| Status bleibt im Testmodus „[Testmodus] …“ | Testmodus ausschalten (Einstellungen → Allgemein) und speichern. |
| Sendung verschwindet nicht | Sendungen aus Mails verschwinden erst nach der Zustellung (plus *Zugestellte Sendungen behalten*) bzw. nach dem *maximalen Alter* (Standard 30 Tage). |

---

## 23. Backup und Update

### 23.1 Update auf eine neue Version

**Automatische Updates (ab 0.2.2):** Pakettracker veröffentlicht neue Versionen über GitHub. In der LoxBerry-**Plugin-Verwaltung** können Sie beim Pakettracker einstellen, ob LoxBerry Sie über neue Versionen nur benachrichtigt oder sie automatisch installiert. LoxBerry prüft dafür regelmäßig selbst. Versionen bis einschließlich 0.2.1 kennen diesen Weg noch nicht und müssen einmal von Hand auf 0.2.2 oder neuer aktualisiert werden.

**Manuelles Update:**

1. Neue ZIP-Datei herunterladen (nicht entpacken), z.B. unter https://github.com/Maddog1090/loxberry-pakettracker/releases.
2. LoxBerry → **Plugin-Verwaltung** → ZIP auswählen → **Installieren**. LoxBerry erkennt selbst, dass es ein Update ist.
3. **Erhalten bleiben:**
   - alle Einstellungen und alle Zugangsdaten
   - manuell eingetragene Sendungen
   - der aktuelle Sendungsstand
   - Tageszähler, IMAP-Lesestand und Anbieter-Zustand
4. Nach dem Update kurz prüfen: Seite **Anbieter** und **Status → Jetzt aktualisieren**.

Technischer Hintergrund: Der LoxBerry-Installer löscht bei einem Update die Konfigurations- und Datenordner des Plugins. Das Plugin sichert sie deshalb vorher selbst nach `/tmp` und spielt sie nach der Installation zurück. Neue Einstellungen einer neuen Version erhalten automatisch ihre Standardwerte.

**Update auf 1.0.0:** Hermes kann Sendungen jetzt zusätzlich live über die Sendungsverfolgung von myhermes.de abfragen. Dafür unter *Einstellungen → Hermes* die **Live-Abfrage über myhermes.de** einschalten, sie ist standardmäßig aus (siehe [Abschnitt 13](#13-hermes-einrichten)). Neu ist außerdem das Zustellzeitfenster `eta_window` (MQTT, REST, Oberfläche). Bestehende Topics, Felder und Status-Codes bleiben unverändert. Ab 1.0.0 gelten MQTT-Topics, Status-Codes und REST-Felder als feste Schnittstelle.

**Update von 0.2.2 auf 0.2.3:** Neue Einzelwert-Abfragen der REST-API für Loxone und der Abschnitt *Hilfe → Loxone per HTTP/REST*. Bestehende REST-Adressen funktionieren unverändert. Einzige Änderung: Ist die REST-Schnittstelle ausgeschaltet, antwortet sie jetzt mit 403 statt 404. Es ist nichts weiter zu tun.

**Update von 0.2.1 auf 0.2.2:** Dokumentation (Hinweis zu leeren MQTT-Werten) und Vorbereitung der automatischen Updates. Es ist nichts weiter zu tun; ab jetzt können Updates automatisch kommen.

**Update von 0.2.0 auf 0.2.1:** Es ändert sich nur die Oberfläche (neue Seite *Hilfe* mit dieser Anleitung). Es ist nichts weiter zu tun.

**Besonderheiten beim Update von 0.1.x auf 0.2.0 bzw. 0.2.1:**
- **Neue Paketdienste:** UPS, Hermes, DPD und GLS sind nach dem Update aktiviert. Sie liefern erst Daten, wenn der E-Mail-Eingang bzw. die UPS-Zugangsdaten eingerichtet sind.
- **Verschlüsselung:** Die Einstellung „SSL/TLS“ des E-Mail-Eingangs heißt jetzt **Verschlüsselung** (Standard `ssl`). Bitte einmal prüfen.
- **Alte Sendungen:** Mit „Automatisch erkennen“ eingetragene Sendungen aus 0.1.x funktionieren unverändert weiter.

### 23.2 Backup

Wichtig sind zwei Ordner auf dem LoxBerry:

| Ordner | Inhalt |
|---|---|
| `/opt/loxberry/config/plugins/pakettracker/` | Einstellungen (`settings.json`) und Zugangsdaten (`credentials.json`) |
| `/opt/loxberry/data/plugins/pakettracker/` | Sendungen (`tracked.json`, `state.json`), Anbieter-Zustand (`provider_state.json`) |

Möglichkeiten:
- **Vollständige LoxBerry-Sicherung** (Systemsicherung bzw. Image der SD-Karte). Sie enthält das Plugin samt Konfiguration.
- **Nur das Plugin sichern:** die beiden Ordner per SSH als Benutzer `loxberry` kopieren, z.B.:
  ```bash
  tar czf ~/pakettracker-backup.tar.gz -C /opt/loxberry config/plugins/pakettracker data/plugins/pakettracker
  ```
- **Zurückspielen:** Plugin installieren, dann die Ordner aus dem Backup zurückkopieren (als Benutzer `loxberry`, Rechte von `credentials.json` auf 600 lassen).

> Das Backup enthält Ihre Zugangsdaten. Bewahren Sie es sicher auf.

### 23.3 Deinstallation

LoxBerry → **Plugin-Verwaltung** → Pakettracker → **Deinstallieren**. Dabei werden Ordner, Einstellungen, Zugangsdaten und der Cronjob entfernt. MQTT-Werte, die als *retained* gesendet wurden, bleiben im Broker gespeichert, bis sie überschrieben oder im MQTT Gateway gelöscht werden.

---

## 24. Bekannte Einschränkungen

- **Amazon, Hermes, DPD, GLS:** nur über E-Mail. Ohne Benachrichtigungsmail kennt das Plugin keinen Status. Ändern die Paketdienste ihr Mail-Layout, kann die Erkennung leiden. Melden Sie solche Fälle bitte mit einer anonymisierten Beispielmail.
- **Weitergeleitete Mails** haben Ihren eigenen Absender und werden nicht erkannt. Nutzen Sie stattdessen eine Postfachregel, die Mails **verschiebt** oder **umleitet** (Original-Absender bleibt erhalten), oder tragen Sie das Originalpostfach ein.
- **Outlook.com/Hotmail** und Postfächer, die nur noch eine Anmeldung per OAuth erlauben: Das Plugin kann sich nur mit Benutzer und Passwort anmelden. Solche Postfächer funktionieren in der Regel nicht. Leiten Sie die Paketmails in ein anderes Postfach um.
- **Mehrdeutige Nummern** (12 Ziffern: DHL/GLS, 14 Ziffern: Hermes/DPD) können falsch zugeordnet werden. Dann den Anbieter manuell wählen.
- **Mehrere Pakete einer Amazon-Bestellung** ohne eigene Sendungsnummer erscheinen als eine Sendung.
- **Sendungen aus Mails** lassen sich in der Oberfläche nicht von Hand ausblenden. Sie verschwinden nach der Zustellung bzw. nach dem eingestellten maximalen Alter.
- **DHL-Kontingent:** Der kostenlose Zugang reicht für etwa 10 gleichzeitig aktive Sendungen bei 60 Minuten Abstand. Für mehr muss bei DHL ein höheres Kontingent beantragt werden.
- **UPS:** Die Zuordnung der UPS-Statustypen zu den Codes 0–7 deckt die üblichen Fälle ab. Seltene Sonderstatus erscheinen als „Unbekannt“ oder „Unterwegs“, der Originaltext steht in `status_text`.
- **Aktualisierungstakt:** frühestens alle 5 Minuten (Cronjob). DHL/UPS-Sendungen werden je Sendung höchstens im eingestellten Mindestabstand abgefragt.
- **MQTT Gateway V2** übernimmt das Abonnement nicht automatisch.
- **Leere MQTT-Werte** (z.B. `error` ohne Fehler) werden nach MQTT-Standard nicht im Broker gespeichert. Wer sich nach einem Neustart neu verbindet, findet diese Topics nicht. War der Miniserver gerade offline, als ein Wert leer wurde, kann dort der alte Text stehen bleiben, bis sich der Wert wieder ändert.
- **Logs** liegen im Arbeitsspeicher und sind nach einem Neustart weg.
- **FedEx und TNT** sind nur vorbereitet (E-Mail und Erkennung). Es gibt noch keine Live-Abfrage.
- **Feldnamen in den Einstellungen** sind nur auf Deutsch verfügbar.

---

## 25. Alle Einstellungen auf einen Blick

> Support und Fehlermeldungen: https://github.com/Maddog1090/loxberry-pakettracker/issues (bitte ohne Zugangsdaten, Sendungsnummern oder echte Mailinhalte). Sicherheitslücken bitte vertraulich an existenzz-cod2@gmx.de.


### Allgemein
| Einstellung | Standard | Bedeutung |
|---|---|---|
| Abfrageintervall (Minuten) | 15 | Wie oft das Plugin aktualisiert (mindestens 5) |
| Zugestellte Sendungen behalten (Tage) | 1 | 0 = nur am Tag der Zustellung anzeigen |
| Sendungen ohne Aktualisierung entfernen nach (Tagen) | 30 | gilt nicht für manuell eingetragene Sendungen |
| Testmodus | an | siehe [Abschnitt 6](#6-testmodus) |
| Loglevel | info | debug, info, warning, error |

### MQTT
| Einstellung | Standard |
|---|---|
| MQTT-Ausgabe aktiv | an |
| Broker von LoxBerry verwenden | an |
| Broker-Host / -Port / Benutzer / Passwort | localhost / 1883 / – / – |
| Basis-Topic | pakettracker |
| Retained senden | an |
| Anzahl Slots für Loxone | 5 |

### REST / HTTP
| Einstellung | Standard |
|---|---|
| REST-Schnittstelle aktiv | an |
| Token erforderlich | an |
| Zugriffs-Token | zufällig bei der Installation |

### E-Mail-Eingang
| Einstellung | Standard |
|---|---|
| E-Mails auswerten | aus |
| Quelle | imap |
| IMAP-Port / Verschlüsselung | 993 / ssl |
| Ordner | INBOX |
| Zeitraum (Tage) | 14 |
| Verarbeitete Mails markieren | aus |

### Paketdienste
| Paketdienst | Standard | Eigene Einstellungen |
|---|---|---|
| DHL | an | API-Key, DHL-Schnittstelle (automatisch), API-Secret, Tracking-Benutzerkennung/-Passwort (optional), Sprache, PLZ, Mindestabstand (60), Tageslimit (250) |
| UPS | an | Client-ID, Client-Secret, Umgebung, Sprache, Mindestabstand (60), Tageslimit (250) |
| Amazon | an | Absender-Domains |
| Hermes, DPD, GLS | an | – |
| FedEx, TNT | aus | – |
