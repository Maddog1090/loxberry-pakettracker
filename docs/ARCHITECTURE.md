# Architektur Pakettracker

## Ziele

- Paketankündigungen und Sendungsstatus mehrerer Paketdienste erfassen: DHL, Amazon, Hermes, DPD, GLS, UPS (vorbereitet: FedEx, TNT)
- Weitere Anbieter mit **einer Datei** ergänzen
- Ausgabe an Loxone per MQTT (primär) und HTTP/REST (optional)
- Konfiguration über die LoxBerry-Weboberfläche, Zugangsdaten nie im Code
- Nur offizielle, dokumentierte Schnittstellen: kein Scraping, keine Login-Automatisierung

## Überblick

```
              ┌──────────────────── LoxBerry ──────────────────────────────────────────────┐
 Weboberfläche│ webfrontend/htmlauth/index.php (PHP, LoxBerry-SDK)                         │
  (Login)     │   │ describe · detect · test  ▲      │ schreibt                            │
              │   ▼                           │      ▼                                     │
              │ bin/pakettracker.py ──────────┘  config/settings.json                      │
 cron.05min ─▶│   run                            config/credentials.json  (0600)           │
              │   ├─ Quellen:   sources/imap.py · sources/mail.py (.eml) · tracked.json    │
              │   ├─ Provider:  dhl · ups (API+Mail) │ amazon · hermes · dpd · gls (Mail)  │
              │   │             fedex · tnt (vorbereitet)          ← Auto-Discovery         │
              │   ├─ store.py (Duplikate) · health.py (Zustand je Anbieter)                 │
              │   └─ Ausgaben: data/state.json ──▶ webfrontend/html/api.php ──▶ Loxone      │
              │                MQTT (retained) ──▶ LoxBerry MQTT Gateway   ──▶ Loxone       │
              └────────────────────────────────────────────────────────────────────────────┘
```

### Module (Backend, `bin/pakettracker/`)

| Modul | Aufgabe |
|---|---|
| `engine.py` | Ablauf eines Zyklus (Mails → manuelle Sendungen → Live-Tracking → Aufräumen → Ausgabe) |
| `store.py` | Sendungssammlung eines Laufs, Duplikate, Platzhalter, Vorrang manueller Anbieterwahl |
| `health.py` | Letzter Erfolg/Fehler je Anbieter und E-Mail-Eingang |
| `registry.py` | Auto-Discovery der Provider, Anbieter-Erkennung (Konfidenz, Mehrdeutigkeit) |
| `providers/base.py` | `Provider`-Basisklasse, Status-Schlüsselwörter, Termin-Erkennung, Testmodus |
| `providers/apibase.py` | `ApiProvider`: HTTP, Timeouts, Drosselung, Tageskontingent, 429-Pause, Schwärzen von Geheimnissen |
| `providers/mailparse.py` | gemeinsame Mail-Auswertung, `MailCarrierProvider` für reine E-Mail-Anbieter |
| `providers/checkdigits.py` | Prüfziffern (UPS 1Z, UPU S10, GS1) |
| `providers/<anbieter>.py` | je Anbieter nur Formate, Domains, Besonderheiten |
| `sources/imap.py` · `sources/mail.py` · `sources/manual.py` | IMAP, .eml-Ordner/Mail-Modell, manuelle Sendungen |
| `outputs/snapshot.py` · `mqtt.py` · `statefile.py` | Loxone-Aufbereitung (Slots), MQTT, state.json |
| `config.py` · `schema.py` | Einstellungen/Geheimnisse, Schema für die Oberfläche |

### Warum Python-Backend und PHP-Oberfläche?

- **PHP:** Das ist der übliche Weg für LoxBerry-Oberflächen (`LBWeb::lbheader`, Sprachdateien, Navbar).
- **Python:** eignet sich besser für Abfragelogik, IMAP, E-Mail-Parsing und MQTT (`python3-paho-mqtt` als Debian-Paket). Alles andere nutzt nur die Standardbibliothek (`urllib`, `imaplib`, `email`).
- **Zusammenspiel:** Die Oberfläche kennt keine Anbieter-Details. Sie rendert Formulare aus dem Schema von `pakettracker.py describe` und nutzt `detect` und `test`.

### Warum Cron statt Daemon?

Paketstatus ändern sich selten. Ein Cronjob (`cron/cron.05min`) ist robuster als ein Dauerprozess: Nach einem Fehler läuft einfach der nächste Takt. Das Intervall prüft das Backend selbst, ein Datei-Lock verhindert parallele Läufe.

## Datenquellen je Anbieter (Stand 02.10.2026)

| Anbieter | Live-Tracking | Ankündigungen/Status per Mail | Begründung |
|---|---|---|---|
| DHL | Shipment Tracking – Unified (`GET api-eu.dhl.com/track/shipments`, Header `DHL-API-Key`) | ja (dhl.de, deutschepost.de) | API für jeden registrierbar |
| UPS | Tracking API (OAuth Client Credentials, `onlinetools.ups.com`) | ja (ups.com) | API für jeden mit UPS-Konto registrierbar |
| Amazon | – | ja (amazon.de/.com, konfigurierbar) | Selling Partner API nur für Verkäufer |
| Hermes | optional, standardmäßig aus: Sendungsverfolgung von myhermes.de (`GET api.my-deliveries.de/tnt/v2/shipments/search/{nr}`, ohne Key, nicht offiziell dokumentiert) | ja (myhermes.de, hermesworld.com) | offizielles HSI/Business-Portal nur für Vertragskunden |
| DPD | – | ja (dpd.de, dpd.com) | Webservices nur für Geschäftskunden mit Vertrag; öffentliche Sendungsverfolgung verlangt PLZ-/Datenschutz-Bestätigung im Browser |
| GLS | – | ja (gls-pakete.de, gls-group.eu/.com) | Track&Trace-API nur mit MyGLS-Versenderkonto; frühere offene Schnittstelle leitet auf die API-Registrierung um |
| FedEx, TNT | vorbereitet (FedEx Track API wäre möglich) | ja | standardmäßig aus |

Der E-Mail-Eingang ist damit für vier der sechs Anbieter die einzige rechtlich saubere Quelle.

## DHL-Live-Tracking (seit 0.1.1)

Am 02.10.2026 mit der offiziellen Doku auf developer.dhl.com abgeglichen:

| Punkt | Wert laut DHL | Umsetzung |
|---|---|---|
| Endpoint | `GET https://api-eu.dhl.com/track/shipments` | unverändert gegenüber der Annahme in 0.1.0 |
| Authentifizierung | Header `DHL-API-Key: <Consumer Key>` | Key aus `credentials.json`, nie im Log |
| Parameter | `trackingNumber` (Pflicht), `language`, `recipientPostalCode`, … | `language` aus den Einstellungen, PLZ optional (nur 5 Ziffern) |
| `status.statusCode` | `pre-transit`, `transit`, `delivered`, `failure`, `unknown` | wie bisher gemappt; „In Zustellung“/„Abholbereit“ gibt es bei DHL (noch) nicht als Code → Ableitung aus dem Text |
| Fehler | RFC 7807 `application/problem+json`; 401, 404, 429 dokumentiert | `title`/`detail` gekürzt ins Log |
| **Limit Free-Tier** | **250 Abfragen/Tag, max. 1 alle 5 s** | **neu:** Abstand 5 s, max. 10 pro Lauf, Mindestabstand je Sendung (Standard 60 min), Tageszähler, Pause nach 429 |

**Abweichungen von der Annahme in 0.1.0 und was daraus folgt:**
- **Rate-Limit:** Es ist deutlich enger als angenommen, daher die neue Drosselung. Ohne sie würde ein 15-Minuten-Takt mit 3 Sendungen bereits 288 Abfragen pro Tag erzeugen.
- **`recipientPostalCode`:** neu als optionale Einstellung.
- **Fehlender Status-Zeitstempel:** Die Antwort setzt dann kein `last_update` mehr (früher: „jetzt“). Ein „unbekannt“ ohne Zeitangabe überschreibt so keine besseren Daten.
- **`parse_ts`:** versteht `…Z`. Python < 3.11 hätte DHL-Zeitstempel sonst verworfen.

**Fehlerbehandlung:** `ProviderError(abort=…, level=…)` bestimmt, ob der Anbieter für den Rest des Laufs pausiert und mit welchem Level geloggt wird.

| Fall | Abbruch für den Lauf | Sendung als „abgefragt“ markiert | Log |
|---|---|---|---|
| 200 + gültige Daten | – | ja | INFO mit Tageszähler |
| ungültiges JSON / keine `shipments` | nein | ja | WARNING |
| 400 | nein | ja | WARNING |
| 404 | nein | ja | INFO, Daten bleiben |
| 401/403 | ja | nein (nach Key-Korrektur sofort wieder abfragbar) | ERROR; Meldung nennt mögliche Ursachen, ohne zu raten |
| 429 | ja + Pause (`Retry-After` oder 30 min) | nein | WARNING |
| 5xx, Timeout (15 s), Netzwerk | ja | nein | WARNING |

**Ohne E-Mail (seit 1.0.1 dokumentiert und getestet):** Die Live-Abfrage hängt nicht am E-Mail-Eingang. Eine manuell eingetragene Nummer (`tracked.json`) wird mit API-Key direkt abgefragt; `health.provider_info` meldet dann `source = "api"`, `live = true`. Am 03.10.2026 erneut mit developer.dhl.com abgeglichen (Endpoint, Header, Free-Tier-Limit unverändert); es wird weiterhin ausschließlich die Unified API genutzt, bestehende API-Keys gelten unverändert. Zusätzlich ordnet `map_api_shipment` Texte zu Zustellversuch (→ 6), Packstation/Filiale zur Abholung (→ 5) und Rücksendung (→ 7) ein.

Der Zustand (Tageszähler, letzte Abfrage je Sendung, Pause) liegt in `data/provider_state.json` und übersteht Upgrades über das bestehende Backup. Der Testmodus nutzt diesen Pfad nicht. Beim Wechsel aus dem Testmodus verwirft die Engine die simulierten Statusdaten einmalig.

## DHL Parcel DE Tracking (seit 1.0.2)

Am 03.10.2026 mit der DHL-Doku „DHL Paket DE Sendungsverfolgung (Post & Paket Deutschland)“, DHLs Postman-Sammlung und der ICE/RIC-Codeliste (05/2026) abgeglichen.

| Punkt | Wert laut DHL | Umsetzung |
|---|---|---|
| Endpoint | Produktion `https://api-eu.dhl.com/parcel/de/tracking/v0/shipments`, Sandbox `https://api-sandbox.dhl.com/…` | nur Produktion – die Sandbox kann die public-Abfrage laut DHL nicht |
| Gateway | API-Key + API-Secret als Basic Auth; Postman zusätzlich Header `dhl-api-key` | beides (`api_key`, `api_secret` aus `credentials.json`) |
| Abfrage | `GET ?xml=<data request="get-status-for-public-user" language-code=… [appname password]><data piece-code=… [zip-code]/></data>` | XML mit ElementTree gebaut (Werte maskiert); `appname`/`password` nur, wenn beide hinterlegt; PLZ nur bei 5 Ziffern |
| Zugang | Doku widersprüchlich: Abschnitt „Authentifizierung“ – Key/Secret reichen für public; „Zugangsvoraussetzungen“/I/O-Referenz – Benutzerkennung + Passwort vom DHL-Kundenberater; „Die produktive Verwendung wird durch DHL freigeschaltet“ | Benutzerkennung/Passwort optional; Oberfläche meldet „aktiv“ erst nach erfolgreicher Antwort |
| Antwort | XML: `<data name="piece-status-public-list" code=…>` → `<data name="piece-status-public" …/>`, Ereignisse mit `event-timestamp` | DTD/Entities werden abgelehnt (XXE), Größe begrenzt; Ereignisse überall im Baum gesucht, neueste zuerst |
| Status | `delivery-event-flag`, `ruecksendung`, `ice`, `standard-event-code`, `status` | Reihenfolge: Zustell-/Rücksende-Flag → eindeutige ICE-Codes → Statustext → Standard-Ereigniscode → „unterwegs“ |
| Termin | `delivery-date`, `delivery-timeframe-from/-to` – „gesondertes Recht erforderlich“ | nur übernommen, wenn geliefert |
| Fehlercodes | 5/6 Anmeldung, 62/64 Berechtigung, 57 PLZ, 100/200 keine Daten, 41/45/59 Nummer, < 0 technisch | 5/6/62/64 wie HTTP 401/403 (Abbruch, ggf. Fallback); 100/200 INFO, Daten bleiben; < 0 Abbruch für den Lauf |
| Limit | 1000/Tag, 3/s, zugestellte nicht erneut abfragen | gemeinsame Drosselung mit Unified (`ApiProvider`, `provider_state.json`) |

**Auswahl und Fallback** (`DhlProvider._plan`): Modus `auto` (Standard) → `[parcel_de, unified]`, wenn ein API-Secret hinterlegt und Parcel DE nicht pausiert ist, sonst `[unified]`. Nur ein `_AuthError` (Gateway 401/403, Codes 5/6/62/64) bei Parcel DE führt zur zweiten Abfrage über Unified und pausiert Parcel DE für 6 h (`parcel_de_paused_until`, `parcel_de_error` in `provider_state.json`). Modi `parcel_de`/`unified` nutzen genau eine Schnittstelle. Bestehende Installationen (nur API-Key) bleiben damit unverändert bei Unified.

**Anzeige** (`DhlProvider.live_details` → `health.provider_info`): `live_api`, `live_api_label`, `live_api_confirmed` (erfolgreiche Antwort dieser Schnittstelle in `last_api_success`), `live_missing`, `parcel_de_configured`, `parcel_de_error`, `parcel_de_paused_until`. Keine neuen MQTT-Topics.

**Verbindungstest:** testet jede konfigurierte Schnittstelle; `pakettracker.py test dhl` übergibt eine aktive eigene DHL-Sendung aus `state.json`, sonst eine nicht existierende Testnummer (Unified 404 bzw. Parcel DE Code 100 = Zugang in Ordnung).

**Nicht genutzt:** die Business-Abfragen `d-get-piece-detail`/`d-get-signature` (nur Sendungen aus dem Nummernkreis eines Geschäftskunden, GKP-Benutzer mit „Verfolgen Paket & Waren“) sowie jede Form von Scraping oder nicht dokumentierten Endpunkten.

## UPS-Live-Tracking (seit 0.2.0)

Grundlage ist die offizielle OpenAPI-Spezifikation (github.com/UPS-API/api-documentation, `OAuthClientCredentials.yaml`, `Tracking.yaml`, Stand 17.09.2026):

| Schritt | Request |
|---|---|
| Token | `POST <base>/security/v1/oauth/token`, Basic-Auth `Client-ID:Secret`, Body `grant_type=client_credentials` → `access_token`, `expires_in` |
| Status | `GET <base>/api/track/v1/details/{inquiryNumber}?locale=de_DE&returnSignature=false…`, Header `Authorization: Bearer …`, `transId` (eindeutig), `transactionSrc` |
| base | `https://onlinetools.ups.com` (Produktion), `https://wwwcie.ups.com` (Testumgebung) |

- **Token:** wird nur im Arbeitsspeicher gehalten (pro Lauf), nie gespeichert.
- **Status:** kommt aus `package.currentStatus.type` (M, P, I, O, D, X, RS, …). Ist der Typ unbekannt oder steht er auf „unterwegs“, wird zusätzlich der Text ausgewertet, z.B. „Access Point“ → abholbereit.
- **Termin:** aus `deliveryDate` (RDD vor SDD, bei Zustellung DEL).
- **Zeitstempel:** aus `activity[0].gmtDate/gmtTime`.
- **Fehler:** wie bei DHL.
  - 401/403 → Abbruch (ERROR), der Token wird verworfen
  - 404 → INFO, die Sendung gilt als abgefragt
  - 429 → Pause
  - 5xx/Timeout → Abbruch für den Lauf

UPS veröffentlicht kein festes Tageskontingent; das Plugin nutzt dieselbe Drosselung wie DHL (einstellbar).

## Anbieter-Erkennung

Jeder Provider gibt für eine Nummer eine Treffersicherheit zurück:
- **3 – eindeutig:** Präfix bzw. gültige Prüfziffer
- **1 – nur Format**
- **0 – passt nicht**

Die Registry sortiert die Treffer nach Sicherheit und bei Gleichstand nach `detection_priority` (DHL, Hermes, DPD, GLS, UPS, Amazon, FedEx, TNT). Mehrdeutig sind vor allem 12 Ziffern (DHL/GLS) und 14 Ziffern (Hermes/DPD). Die Oberfläche speichert den erkannten Anbieter fest und weist auf die Alternativen hin. Eine manuelle Wahl gewinnt immer, auch gegenüber Mails anderer Anbieter mit derselben Nummer. Prüfziffern werden nur für sicher bekannte Verfahren genutzt (UPS 1Z, UPU S10, GS1). Eine ungültige Prüfziffer senkt die Sicherheit nur, sie schließt nie aus.

## Duplikate (`store.py`)

- Gleiche ID `anbieter:nummer` → zusammenführen. Neuere Information gewinnt, ein vorhandener Termin bleibt erhalten, wenn die neuere Information keinen hat.
- Gleiche Nummer bei anderem Anbieter → dieselbe Sendung. Eine manuelle Anbieterwahl verschiebt sie zum gewählten Anbieter.
- Amazon-Mail ohne Sendungsnummer → Platzhalter `ORDER-<Bestellnummer>`. Er wird durch die erste echte Sendung mit gleicher `reference` ersetzt (oder geht in sie auf).
- Meldet eine Mail eine Sendung für einen deaktivierten Anbieter (z.B. Amazon nennt eine DHL-Nummer, DHL ist aus), wird sie dem meldenden Anbieter zugeordnet.
- Dieselbe Mail aus mehreren Ordnern bzw. Läufen: IMAP-UID-Merker je Ordner plus Message-ID-Abgleich im Lauf.
- Sendung mit aktuellem Live-Tracking (`live_checked` ≤ 48 h, `Shipment.live_fresh`) → eine Mail ergänzt nur Herkunft, Beschreibung und Referenz (`merge(status=False)`); Status, Text und Termin bleiben aus der API.

## IMAP (`sources/imap.py`)

- **Verbindung:** `IMAP4_SSL` (993), `IMAP4` + `STARTTLS` (143) oder unverschlüsselt (nur auf ausdrücklichen Wunsch), Timeout 30 s.
- **Ablauf je Ordner:**
  1. `SELECT` read-only
  2. `UID SEARCH SINCE <Zeitraum>`
  3. nur UIDs größer der gemerkten (bei geänderter UIDVALIDITY neu einlesen)
  4. `UID FETCH (RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM)])` als Vorfilter auf Absender aktiver Anbieter
  5. nur relevante Mails mit `BODY.PEEK[]` laden (≤ 1,5 MB)
- **Nie** `\Seen`, `EXPUNGE`, `MOVE` oder `COPY`. Optional `STORE +FLAGS.SILENT ($Pakettracker)`.
- **Fehler:** Anmelde-, TLS- und Netzwerkfehler werden zu verständlichen Meldungen ohne Zugangsdaten. Der Lauf geht weiter, der Fehler steht im Gesundheitsstatus.

## Gesundheitsstatus (`health.py`)

`data/provider_state.json["_health"]` speichert je Anbieter und für `email` den letzten Erfolg und den letzten Fehler. Daraus entsteht in `state.json` je Anbieter:
- `health`: `ok`, `error`, `email_only` (API-Zugang fehlt), `no_source` (weder API noch E-Mail) oder `idle`
- `source` – tatsächlich genutzte Quelle: `api`, `email`, `api+email` oder `none` (seit 1.0.1; vorher die statische Fähigkeit)
- `live`, `live_last_success`, `live_error` – Live-Abfrage möglich (API-Anbieter mit Zugangsdaten bzw. eingeschaltete Hermes-Abfrage), letzter Erfolg und aktueller Fehler nur der API
- `credentials`, `last_success`, `error`, `active`, `shipment_count`

Zusätzlich gibt es `email`, `errors` (Anzahl Fehler im Lauf) und `last_full_success`. Fehlende Zugangsdaten oder ein erreichtes Kontingent gelten nicht als Fehler.

## Ablauf eines Zyklus (`engine.py`)

1. Bisherigen Stand aus `state.json` laden (dient zugleich als Gedächtnis)
2. E-Mails nach Datum sortiert an alle aktiven Provider geben
3. Manuelle Einträge aus `tracked.json` übernehmen; in der UI gelöschte verwerfen
4. Nicht abgeschlossene Sendungen live abfragen (im Testmodus: simulierte Daten)
5. Aufräumen: zugestellte nach `keep_delivered_days`, veraltete nach `max_age_days`
6. `state.json` schreiben, MQTT publizieren

Beim Zusammenführen gilt: Neuere Informationen (`last_update`) gewinnen. Eine ältere Mail überschreibt also keinen neueren API-Status. Ergebnisse einer Live-Abfrage sind zusätzlich **maßgeblich** (`merge(authoritative=True)`): Sie gelten auch dann, wenn ihr Ereigniszeitpunkt älter ist als eine zwischenzeitlich eingegangene Mailprognose. Jede erfolgreiche Abfrage mit Status setzt `live_checked`.

## Termine, relative Texte und abgelaufene Sendungen (seit 1.0.1)

Alle Tagesvergleiche laufen über `models.local_today()/local_date()` in **Europe/Berlin** (`zoneinfo`, Rückfall auf die Systemzeitzone), nie über UTC-Daten. `snapshot.build(today, now)` berechnet bei **jedem Lauf** neu:

- **Relative Wörter** (`heute`, `morgen`, `übermorgen`, `today`, `tomorrow`) im gespeicherten Originaltext werden auf den Kalendertag der Statusinformation (`last_update`) bezogen und relativ zu heute neu formuliert (`render_relative`). Liegt der gemeinte Tag in der Vergangenheit oder ist der Bezugstag unbekannt, entfällt die Angabe samt „kommt“. `state.json` enthält je Sendung den aufbereiteten `status_text` und das Original `status_text_raw`; geladen wird das Original (Dateien aus 1.0.0 ohne `status_text_raw` liefern ebenfalls das Original).
- **`eta_text`** aus `eta`: `kommt heute`, `kommt morgen`, `kommt am <Wochentag> TT.MM.`, verstrichen und aktiv: `verspätet – ursprünglicher Termin TT.MM.`, verstrichen und stale: `Termin TT.MM. überschritten`.
- **Stale** (`Shipment.is_stale`): nicht abgeschlossen, nicht abholbereit, gültige `eta` < heute, kein `live_checked` innerhalb von 48 h und `last_update` nicht nach dem ETA-Tag. Stale-Sendungen zählen nicht zu `active`, den Status-Zählern, `arriving_today`, `next_eta` (nur Termine ≥ heute) und `provider/<id>/active` und belegen keinen Slot. Sie bleiben in `shipments` (`stale: true`) und werden wie bisher nach `max_age_days` entfernt. `summary/stale` zählt sie.

Die Slot-Liste hat immer genau `slots` Einträge. Rückt eine Sendung auf oder fällt sie heraus, werden alle Felder des Slots neu gesendet; leere Texte löschen den retained Wert (siehe unten), `used` = 0 und `status_code` = 0 bleiben gespeichert.

## Normalisierter Status (Loxone-Werte)

| Code | Key | Bedeutung |
|---|---|---|
| 0 | unknown | Unbekannt |
| 1 | announced | Angekündigt / Sendungsdaten übermittelt |
| 2 | in_transit | Unterwegs |
| 3 | out_for_delivery | In Zustellung |
| 4 | delivered | Zugestellt |
| 5 | pickup_ready | Abholbereit (Filiale, Packstation) |
| 6 | exception | Problem / Zustellversuch fehlgeschlagen |
| 7 | returned | Rücksendung |

Diese Codes sind eine Schnittstellenzusage und dürfen sich nicht ändern.

## Loxone-Anbindung

Loxone kann keine dynamischen Listen verarbeiten. Deshalb gibt es neben Zählern **feste Slots** (`slot/1 … slot/N`), sortiert nach Relevanz (in Zustellung → abholbereit → Problem → unterwegs → angekündigt → heute zugestellt).

**MQTT** (retained, Basis-Topic `pakettracker`). Leere Werte werden ebenfalls mit retain gesendet und löschen damit nach MQTT-Standard den gespeicherten Wert (bewusst so belassen: keine veralteten Fehlertexte im Broker, Loxone erhält leere Werte live):

```
pakettracker/summary/{active,announced,in_transit,out_for_delivery,pickup_ready,exception,delivered_today,arriving_today,next_eta,stale}
pakettracker/provider/<id>/active
pakettracker/slot/<n>/{used,status_code,status,status_label,status_text,provider,tracking_number,description,eta,eta_window,eta_text}
pakettracker/updated, pakettracker/updated_epoch, pakettracker/mock_mode, pakettracker/json
```

Das LoxBerry MQTT Gateway V1 (Standard) liest `config/mqtt_subscriptions.cfg` jedes Plugins und abonniert damit `pakettracker/#` automatisch. Das optionale Gateway V2 tut das nicht, dort muss die Subscription manuell angelegt werden. Das Gateway leitet die Werte an virtuelle Eingänge in Loxone weiter.

MQTT ist bewusst optional: Ohne paho-mqtt, ohne Broker in `general.json` oder bei einem nicht erreichbaren Broker (Verbindungs-Timeout 10 s) wird nur ein Fehler protokolliert. `state.json`, Oberfläche und REST arbeiten weiter.

**REST** (`/plugins/pakettracker/api.php`, öffentlich erreichbar, daher Token-Pflicht): `q=summary|slots|slot&n=…|shipments|all`, `format=json|text`. `format=text` liefert `schluessel=wert`-Zeilen für die Befehlserkennung in virtuellen HTTP-Eingängen (`summary.active=\v`). Mit `field=…` (bei `q=summary` und `q=slot&n=…`) kommt genau ein Wert als bereinigter UTF-8-Klartext (Entities aufgelöst, Leerzeichen getrimmt); unbekanntes Feld/ungültiger Slot → 400, REST aus/Token falsch → 403, nur GET. `api.php` puffert alle Ausgaben und zeigt keine PHP-Fehler an, damit Loxone nie HTML-Fehlerseiten erhält.

## LoxBerry-Konventionen (geprüft gegen `sbin/plugininstall.pl`, Stand 09/2026)

- `plugin.cfg` im ZIP-Root, Interface 2.0. `AUTHOR.NAME/EMAIL` und `PLUGIN.NAME/FOLDER` nie mehr ändern (Plugin-Identität).
- Der Installer ersetzt `REPLACELBPBINDIR` usw. in allen Textdateien. Der Cronjob nutzt das. Das Python-Backend leitet seine Pfade aus dem eigenen Installationsort ab. Es gibt keine fest codierten `/opt/loxberry`-Pfade, auf die der Installer warnt.
- Bei Kollisionen hängt LoxBerry ein Suffix an den Plugin-Ordner an. Backend (Pfadableitung), PHP (`LBP*DIR`-Konstanten) und Skripte (Argument `$3`) kommen damit zurecht.
- Bei Upgrades löscht der Installer `config/` und `data/` des Plugins. Deshalb gibt es das Backup in `preupgrade.sh`/`postupgrade.sh`.
- Skripte erhalten `<TEMPFILE> <NAME> <FOLDER> <VERSION> <LBHOMEDIR> <TEMPFOLDER>`. Exit 1 = Warnung, 2 = Abbruch.
- Auto-Update (`sbin/pluginsupdate.pl`): `plugin.cfg` → `[AUTOUPDATE] AUTOMATIC_UPDATES/RELEASECFG/PRERELEASECFG`; die dort verlinkte `release.cfg` enthält `[AUTOUPDATE] VERSION/ARCHIVEURL/INFOURL`, Vergleich nach SemVer. `tools/build_release.py` erzeugt `release.cfg`/`prerelease.cfg` aus `GITHUB_REPO` und der Version (Ablauf: [RELEASE_LOXBERRY.md](RELEASE_LOXBERRY.md)).
- App Store (LoxBerry 4, `system/appstore.cgi`): Katalog aus dem LoxBerry-Wiki (`plugins.json`), Felder u.a. title, author, description, status, version, min_lb_version, zip, repo.
- Apache kann eine ältere PHP-Version nutzen als die Kommandozeile (auf LoxBerry 4.0.0.15: Apache PHP 7.4, CLI PHP 8.5) – die Weboberfläche muss PHP-7.4-kompatibel bleiben.

## Konfiguration und Geheimnisse

| Datei | Ort (LoxBerry) | Inhalt | Rechte |
|---|---|---|---|
| `settings.json` | `config/plugins/pakettracker/` | alle nicht geheimen Einstellungen | 0644 |
| `credentials.json` | `config/plugins/pakettracker/` | API-Keys, Passwörter, REST-Token | **0600** |
| `tracked.json` | `data/plugins/pakettracker/` | manuell erfasste Sendungsnummern | 0644 |
| `state.json` | `data/plugins/pakettracker/` | aktueller Stand (Ausgabe) | 0644 |
| `provider_state.json` | `data/plugins/pakettracker/` | Anbieter-Zustand (z.B. DHL-Kontingent) | 0644 |

- Schemafelder mit `secret=True` landen automatisch in `credentials.json`.
- `describe` gibt für Geheimnisse nur „gesetzt ja/nein“ zurück. Leere Passwortfelder im Formular bedeuten „unverändert“.
- Ausnahme `reveal=True`: Der REST-Token wird in der (passwortgeschützten) Oberfläche angezeigt, weil er in die Loxone-URL muss.
- Formulare sind CSRF-geschützt. `preupgrade.sh`/`postupgrade.sh` sichern `config/` und `data/` über Upgrades hinweg.

## Neuen Anbieter ergänzen

Reiner E-Mail-Anbieter, z.B. `providers/postnl.py`:

```python
@register
class PostNlProvider(MailCarrierProvider):
    id = "postnl"
    name = "PostNL"
    enabled_by_default = False
    detection_priority = 90
    email_domains = ("postnl.nl", "postnl.de")
    strong_patterns = (re.compile(r"3S[A-Z0-9]{11,13}"),)
    tracking_url_template = "https://jouw.postnl.nl/track-and-trace/{number}"
```

Mit offizieller API: von `ApiProvider` ableiten, `required_secrets`, `settings_schema` (geheime Felder mit `secret=True`, dazu `throttle_fields(...)`), `_fetch()`, `_http_error()` und optional `_test()` implementieren (siehe `ups.py`).

Mehr ist nicht nötig. Der Rest wird automatisch übernommen: Oberfläche (Einstellungen, Übersicht, Verbindungstest), Konfiguration, Erkennung, IMAP-Vorfilter, Gesundheitsstatus, MQTT (`provider/<id>/…`) und REST. Tests mit anonymisierten Beispielmails unter `tests/fixtures/` ergänzen. Echte APIs werden in Tests nie angesprochen (`tests/conftest.py` sperrt die URLs).

## Offene Punkte / nächste Schritte

1. FedEx Track API (OAuth) produktiv anbinden
2. Mail-Parser mit mehr echten (anonymisierten) Mails verschiedener Layouts schärfen
3. Mehrere Pakete pro Amazon-Bestellung ohne Sendungsnummer unterscheiden
4. Logging in den LoxBerry-Logmanager integrieren
5. Sendungen in der Oberfläche ausblenden/umbenennen
6. Englische Labels für Schemafelder (aktuell nur Deutsch)

