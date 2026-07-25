# JCM Pitwall — Telemetrie & Strategie für 24h

Umsetzung von Phase 1 aus der Systemarchitektur: rundenbasierte Aggregation,
Supabase Free Tier, Kommandostand im Browser. Läuft komplett ohne laufende Kosten.

```
Fahrer-PC (LMU / rF2)
  └─ client/run_client.py      liest Shared Memory mit 20 Hz,
     └─ LapAccumulator          bildet Integrale und feuert 1 Payload je Runde
        └─ Supabase REST         laps + stint_telemetry
           └─ dashboard/index.html  Kommandostand, aktualisiert alle 5 s
```

Datenvolumen pro 24h-Rennen:

| Tabelle | Zeilen | Grund |
|---|---|---|
| `laps` + `stint_telemetry` | ~350 | eigenes Auto, eine Zeile je Runde |
| `opponent_laps` | ~10.000 | jede Runde jedes Fahrzeugs im Feld |
| `field_state` | **1** | Live-Stand, wird alle 5 s überschrieben |
| `weather_log` | ~1.440 | eine Zeile pro Minute |

Zusammen unter 3 MB. Das Free-Tier-Limit von 500 MB reicht für über 150 Rennen.
Der Live-Feldstand ist bewusst eine einzige Zeile — Abstände brauchen keine
Historie, nur den aktuellen Stand.

---

## 1. Datenbank aufsetzen (einmalig, ~10 Minuten)

**Schritt für Schritt steht in [EINRICHTUNG.md](EINRICHTUNG.md)** — inklusive
Hosting, Prüfskript und Fehlertabelle. Kurzfassung:

1. Auf supabase.com ein kostenloses Projekt anlegen, Region **Frankfurt**.
2. Im SQL-Editor `sql/00_setup_all.sql` ausführen. Diese eine Datei ersetzt 01–04.
3. Unter *Project Settings → API* beide Schlüssel holen: **service_role** für die
   Fahrer-PCs, **anon public** fürs Dashboard.
4. `python tools/check_setup.py` — prüft die ganze Kette in zehn Sekunden.

Schreiben darf nur der service_role-Key. Der anon-Key im gehosteten Dashboard ist
öffentlich sichtbar und deshalb nur lesend berechtigt.

Die sechs Fahrer einmal anlegen, Farben tauchen so im Stint-Ring auf:

```sql
insert into drivers (driver_name, short_name, color, max_total_min) values
  ('Marcelinjo','MAR','#ff6a13',840),
  ('Fahrer 2','F02','#1fd4c3',840),
  ('Fahrer 3','F03','#ffb020',840),
  ('Fahrer 4','F04','#7c8cff',840),
  ('Fahrer 5','F05','#35d07f',840),
  ('Fahrer 6','F06','#ff5d9e',840);
```

## 2. Client auf jedem Fahrer-PC

**Für die anderen fünf Fahrer:** `python tools/paket_fuer_fahrer.py` baut ein
fertiges ZIP mit Zugangsdaten und Fahrerliste. Die entpacken es, klicken
`START_HIER.bat`, wählen ihren Namen und drücken START — mehr nicht. Siehe
[ANLEITUNG_FAHRER.md](ANLEITUNG_FAHRER.md).

Für dich selbst mit Terminal:

```bat
cd client
python config.py                    :: legt pitwall_config.json an
:: supabase_url, supabase_key und driver_name eintragen
python run_client.py --demo         :: erst mal ohne Sim testen
python run_client.py                :: scharf, LMU muss laufen
```

Der erste Client legt die Session an und schreibt die ID nach `current_session.txt`.
Die anderen fünf starten mit `--session <uuid>` oder bekommen die Datei kopiert.

Nützliche Schalter:

| Schalter | Wirkung |
|---|---|
| `--demo` | simuliertes 24h-Rennen im Zeitraffer, kein Sim nötig |
| `--dry-run` | rechnet und zeigt alles an, lädt nichts hoch |
| `--sim rf2` | rFactor 2 statt LMU |
| `--new-session` | erzwingt eine neue Session |
| `--close-session` | schließt die Session beim Beenden |

Fällt die Verbindung aus, landen die Runden in `pitwall_spool.jsonl` und werden beim
nächsten erfolgreichen Call nachgeschoben. Kein Netz heißt nicht: Runde weg.

## 3. Kommandostand

`dashboard/index.html` im Browser öffnen. Ohne Zugangsdaten läuft die Demo-Ansicht,
damit der Schirm nie leer ist.

### Drei Schirme

| Schirm | Adresse | Taste | Inhalt |
|---|---|---|---|
| Übersicht | `#uebersicht` | `1` | Stint-Ring, Sprit, Reifen, Bremsen, Lenkzeiten |
| Zeiten | `#zeiten` | `2` | Feld nach Klassen, Ø der letzten 5 Runden, Abstände, Boxenstopp-Projektion |
| Wetter | `#wetter` | `3` | aktuelle Werte, 24h-Verlauf, Reifenempfehlung |

**Mehrere Monitore:** jeder Schirm hat eine eigene Adresse. Für den Pit-Wall-Aufbau
drei Browserfenster öffnen und jeweils an eine Adresse hängen —
`…/index.html#uebersicht`, `…/index.html#zeiten`, `…/index.html#wetter` — dann
`F` für Vollbild. Der Knopf **Zweiter Schirm** öffnet den gerade sichtbaren Schirm
direkt in einem neuen Fenster.

- Für den festen Pit-PC: `config.example.js` zu `config.js` umbenennen und ausfüllen.
  Nie in ein öffentliches Repo committen — sie steht in `.gitignore`.
- Sonst: Knopf **Verbindung**, URL und Key eintragen. Die bleiben nur im Tab.
- Ins Netz stellen: den Ordner `dashboard/` hochladen, fertig — es gibt keinen
  Build-Schritt. Drei Wege stehen in [EINRICHTUNG.md](EINRICHTUNG.md), ein fertiger
  GitHub-Pages-Workflow liegt bei (`deploy_dashboard.bat`).

---

## Woher die Telemetrie kommt

Im Ordner `client/pyLMUSharedMemory/` liegt die Bibliothek
[pyLMUSharedMemory](https://github.com/TinyPedal/pyLMUSharedMemory) des
TinyPedal-Projekts (MIT-Lizenz, Tony Whitley und Xiang). Sie bildet das
Shared-Memory-Interface ab, das Studio 397 mit dem Spiel ausliefert. Sie ist
mitgeliefert, damit auf den Fahrer-PCs nichts nachinstalliert werden muss —
Lizenztext liegt daneben. Eine einzige Zeile ist geändert (in `lmu_data.py`,
`SimInfo.close`): schlug der Zugriff fehl, warf der Destruktor einen zweiten,
irreführenden Fehler hinterher. Die Änderung ist im Quelltext markiert.

Der Leser in `client/source.py` ist gegen deren Quelltext gebaut, nicht gegen
Vermutungen. Drei Fallen stecken darin, die auch in eigenen Projekten gerne
zuschlagen:

- **Telemetrie- und Scoring-Index sind verschieden.** Zugeordnet wird über
  `mID`. Wer stur denselben Index nimmt, mischt stillschweigend Fahrzeuge.
- **`mTemperature` je Rad sind drei Werte** (innen/mitte/außen) in Kelvin,
  kein einzelner.
- **`mBrakeTemp` lässt sich nicht am Einzelwert erkennen** — 612 wäre als
  Celsius wie als Kelvin plausibel. Entschieden wird über das Sessionminimum:
  kalte Bremsen liegen bei Umgebungstemperatur.

Direkt vom Spiel übernommen statt selbst geschätzt werden außerdem:
Streckenlänge (`mLapDist` der Session), Restzeit (`mSessionTimeRemaining`),
Gelbphase (`mUnderYellow` je Fahrzeug) und ungültige Runden
(`mLapInvalidated`).

## Was gerechnet wird

**Sprit.** Gleitender Schnitt der letzten fünf gültigen Rennrunden; In-Laps, Out-Laps,
Gelbphasen und ungültige Runden fliegen raus. Neben dem Schnitt steht immer die
Rechnung mit der schlechtesten dieser fünf Runden — auf die planst du den Stopp.

**Reifen.** Linearer Abbau über die bisherigen Stintrunden, hochgerechnet auf das
Stintende. Fällt die Kurve am Ende ab, unterschätzt die Gerade den Abbau; die letzten
Runden gehören dem Fahrerfunk.

**Bremsen.** LMU liefert keinen Belagverschleiß. Was hier steht, ist das
Hitzeintegral ∫max(T−500 °C, 0)dt je Runde plus die Reibarbeit ∫(Druck·v)dt als
relativer Index — dasselbe Modell wie im Consistency Coach. Modell, kein Sim-Wert.

**Feld & Zeitentabelle.** Der Client liest `vehScoringInfo` aller Fahrzeuge mit,
erkennt für jedes Auto die abgeschlossenen Runden und rechnet Klassenpositionen und
Klassenabstände. „Ø 5 Rd" ist der Schnitt der letzten fünf Runden ohne Boxenrunden —
die Zahl sagt, was ein Auto gerade fährt, nicht was es einmal konnte. „Δ Pace"
stellt das gegen das eigene Auto.

**Boxenstopp-Projektion.** Zwei getrennte Antworten, weil es zwei verschiedene
Fragen sind:

- *Position nach dem Stopp* rechnet gegen die Klassifikation und zählt nur
  Fahrzeuge auf derselben Runde.
- *Verkehr beim Rauskommen* rechnet gegen die echte Streckenposition (`mLapDist`).
  Bei einem 24h-Rennen mit Rundenrückständen liegt genau da der Unterschied: das
  Auto, das dir beim Rausfahren vor die Nase kommt, steht oft gar nicht in deiner
  Nähe der Ergebnisliste.

Der Boxenverlust lässt sich von Hand setzen oder aus gemessenen In-/Out-Laps
übernehmen — der Client sammelt die über das Rennen und bildet den Median, damit
ein Dreher in der Boxengasse die Zahl nicht kippt.

**Wetter.** Eine Zeile pro Minute, im Diagramm auf Fünf-Minuten-Punkte verdichtet.
Das blau hinterlegte Band markiert die Phase, in der die Lufttemperatur unter dem
Rennschnitt liegt — das ist die Nacht, und dort ändert sich der Grip, lange bevor
jemand Regen meldet. Die Reifenempfehlung nutzt das Streckenmittel der Nässe
(unter 10 % Slick, 10–40 % Intermediate, darüber Regen).

**Lenkzeiten.** Summe der Rundenzeiten je Fahrer gegen `max_total_min`. Wer voll ist,
darf nicht mehr — das rechnet um vier Uhr morgens niemand mehr im Kopf.

## Bekannte Grenzen

- Sektor 2 kommt aus dem Sim kumuliert, der Client rechnet ihn zurück.
- Die Streckenlänge für die Verkehrsrechnung wird aus dem größten beobachteten
  `mLapDist` im Feld geschätzt. In der ersten Rennminute kann sie daneben liegen.
- Startnummern stehen in LMU/rF2 nicht in einem eigenen Feld; der Client zieht sie
  per `#nn` aus dem Fahrzeug- oder Teamnamen. Fahrzeuge ohne Nummer im Namen
  zeigen einen Strich.
- FCY wird über `mGamePhase` erkannt. Wenn deine Liga anders flaggt, im
  `LapAccumulator` die Phasenliste anpassen.
- Der anon-Key darf schreiben. Für sechs bekannte Leute ist das der richtige
  Kompromiss; wer härter absichern will, siehe Kommentar in `03_rls.sql`.

## Phase 2 und 3

Phase 2 ist der Testlauf: 1–2 Stunden mit allen sechs Fahrern, danach in den Daten
prüfen, ob jede Runde angekommen ist (`select count(*) from laps ...`).

Phase 3 wäre der Hetzner-VPS mit Grafana für Sekundendaten. Dafür muss am Client
nichts umgebaut werden — er bekommt einen zweiten Sink neben `SupabaseClient`,
der ungefiltert mit 1–5 Hz streamt. Vor dem 24h-Rennen buchen, danach abrechnen.
