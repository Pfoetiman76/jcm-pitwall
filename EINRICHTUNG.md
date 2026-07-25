# Einrichtung: Datenbank und Hosting

Reihenfolge einhalten. Nach jedem Block steht eine Kontrolle — wenn die nicht
grün ist, hat der nächste Schritt keinen Zweck.

---

## Vorweg: brauchst du überhaupt Hosting?

Läuft der Kommandostand nur auf deinem eigenen Rechner, **nein**. Dann öffnest du
`dashboard/index.html` per Doppelklick und bist fertig. Hosting brauchst du erst,
wenn die anderen fünf Fahrer von ihren PCs draufschauen sollen — oder du das
Handy als vierten Schirm nutzen willst.

Die Datenbank brauchst du in jedem Fall, sobald mehr als ein PC beteiligt ist.

---

## Teil 1 — Supabase (rund 10 Minuten)

### 1.1 Projekt anlegen

1. [supabase.com](https://supabase.com) → **Start your project** → mit GitHub anmelden.
2. **New project**:
   - Name: `jcm-pitwall`
   - Database Password: erzeugen lassen und in deinen Passwortmanager. Du brauchst
     es für dieses Setup nicht, aber ohne kommst du später nicht mehr ran.
   - Region: **Central EU (Frankfurt)** — kürzeste Latenz von Deutschland aus.
   - Plan: Free.
3. Zwei bis drei Minuten warten, bis das Projekt steht.

### 1.2 Schema einspielen

Links **SQL Editor** → **New query** → den kompletten Inhalt von
`sql/00_setup_all.sql` einfügen → **Run**.

Die Datei ersetzt 01 bis 04 und ist idempotent — nochmal ausführen schadet nicht.
Unten erscheint eine Tabelle mit den angelegten Policies. Steht da für jede der
neun Tabellen eine Zeile `…_read` mit `{anon,authenticated}`, hat es geklappt.

### 1.3 Die sechs Fahrer anlegen

Zweite Query, Namen und Farben anpassen:

```sql
insert into drivers (driver_name, short_name, color, max_total_min) values
  ('Marcelinjo','MAR','#ff6a13',840),
  ('Fahrer 2','F02','#1fd4c3',840),
  ('Fahrer 3','F03','#ffb020',840),
  ('Fahrer 4','F04','#7c8cff',840),
  ('Fahrer 5','F05','#35d07f',840),
  ('Fahrer 6','F06','#ff5d9e',840)
on conflict (driver_name) do nothing;
```

`max_total_min` ist das Lenkzeitlimit aus eurem Reglement in Minuten.

### 1.4 Die beiden Schlüssel holen

**Project Settings → API**. Dort liegen zwei Dinge, die man nicht verwechseln darf:

| Schlüssel | Wo er hingehört | Was er darf |
|---|---|---|
| **anon public** | ins Dashboard, ins Netz | nur lesen |
| **service_role secret** | nur auf die 6 Fahrer-PCs | alles |

Das ist die Änderung gegenüber der ersten Fassung: gehostet ist das Dashboard eine
statische Seite, ihr Schlüssel steht damit für jeden im Quelltext. Lesbar ist
unkritisch — Rundenzeiten sind kein Geheimnis. Schreibbar wäre eine Einladung,
dir mitten im Rennen Müll in die Datenbank zu kippen. Deshalb schreibt jetzt nur
noch der service_role-Key, und der verlässt den Fahrer-PC nie.

**Der service_role-Key gehört niemals in ein Repo, in einen Screenshot oder in
einen Discord-Chat.** Er hängt an der Datenbank vorbei an allen Rechten vorbei.

### 1.5 Client konfigurieren

```bat
cd client
python config.py
```

In der entstandenen `pitwall_config.json`:

```json
{
  "supabase_url": "https://xxxxxxxx.supabase.co",
  "supabase_key": "<service_role secret>",
  "anon_key": "<anon public>",
  "driver_name": "Marcelinjo"
}
```

`anon_key` braucht der Client nicht — er steht nur da, damit das Prüfskript testen
kann, dass der Dashboard-Schlüssel wirklich nicht schreiben darf.

Die Datei steht in `.gitignore`. Lass das so.

### ✅ Kontrolle

```bat
python tools/check_setup.py
```

Das Skript prüft Verbindung, alle neun Tabellen, alle fünf Views, legt testweise
eine Session mit Runde und Telemetrie an, liest sie über den View zurück, testet
den Feldstand-Upsert, prüft dass der anon-Key nicht schreiben darf, und räumt
hinterher auf. Am Ende steht entweder `Alles bereit.` oder genau, was fehlt.

---

## Teil 2 — Testlauf mit echten Daten

Bevor irgendwas gehostet wird: einmal echte Daten in die Datenbank schreiben.

```bat
cd client
python run_client.py --demo --new-session --minutes 3
```

Das simuliert drei Minuten Rennen im Zeitraffer und lädt Runden, Feldstand und
Wetter wirklich hoch. Danach `dashboard/index.html` öffnen, **Verbindung** →
URL und **anon**-Key eintragen → alle drei Schirme durchklicken. Wenn hier Daten
stehen, funktioniert die ganze Kette.

Aufräumen, wenn du magst:

```sql
delete from sessions where track_name = 'Circuit de la Sarthe' and planned_hours = 24;
```

---

## Teil 2b — Installer bauen und verteilen

**Alles im Fenster statt im Terminal:** `EINRICHTER.bat` doppelklicken. Drei
Reiter — Zugang prüfen, Fahrer verwalten, Team-Code erzeugen und die
`config.js` für den Kommandostand schreiben.

### Installer bauen

```
installer\build.bat
```

Baut beide Programme und daraus **einen** Installer für alle. Voraussetzung
neben Python ist Inno Setup 6 (`winget install JRSoftware.InnoSetup`) — die
Schiene kennst du vom Consistency Coach. Wer will, kann stattdessen einen Tag
setzen (`git tag v1.0.0 && git push origin v1.0.0`), dann baut GitHub den
Installer selbst und hängt ihn ans Release.

Ergebnis: `installer\Output\JCM-Pitwall-Setup-1.0.0.exe`. Beim Installieren
wählt man **„Ich fahre mit"** oder **„Ich richte das Team ein"**.
Administratorrechte sind nicht nötig.

### Der Team-Code

Im Installer stecken **keine** Zugangsdaten. Deshalb darf er offen liegen —
auf GitHub, im Discord, egal.

Die Zugangsdaten gehen stattdessen als Team-Code raus: im Einrichter unter
*3 · Verteilen* auf **CODE ERZEUGEN**, dann **In Zwischenablage**, und den
Text direkt an die fünf schicken. Sie fügen ihn beim ersten Start einmal ein.

Das hat zwei Vorteile gegenüber einem Installer mit eingebauten Daten:
du musst bei jedem Schlüsselwechsel keinen neuen Installer bauen, und der
Installer selbst ist harmlos.

**Der Code enthält den service_role-Schlüssel.** Direkt verschicken, nicht in
einen offenen Kanal. Rutscht er doch mal raus: in Supabase unter
*Project Settings → API* neu erzeugen, im Einrichter neuen Code erzeugen,
einmal verteilen.

### Ohne Installer

`python tools\paket_fuer_fahrer.py` baut weiterhin ein ZIP mit dem Client
zum Entpacken und Anklicken — für den Fall, dass jemand nichts installieren
will oder darf.

---

## Teil 2c — Test mit dem echten Spiel

Bevor sechs Leute etwas installiert bekommen, einmal prüfen was bei dir
tatsächlich ankommt:

```
python tools\kanal_check.py
```

Dreißig Sekunden fahren, danach steht in einer Tabelle, welcher Wert da ist
und welcher leer bleibt — und wofür er gebraucht wird. Es wird nichts
hochgeladen.

**Reicht dafür eine Wiederholung?** Für die Hälfte. Eine Wiederholung spielt
den Scoring-Strom ab: Rundenzeiten, Positionen, Abstände, Streckenposition,
Wetter. Zeitentabelle und Wetterschirm kannst du damit prüfen.

Physik wird in einer Wiederholung **nicht** aufgezeichnet — Sprit,
Reifenverschleiß und Bremstemperaturen bleiben leer. Genau die Werte, auf
denen die Spritkalkulation, die Reifenprojektion und die Bremswarnung
stehen. Der Kanal-Check erkennt die Wiederholung und sagt es dir auch.

Der Client lädt aus einer Wiederholung deshalb **nichts** hoch. Sonst
liefen deren Rundenzeiten in die laufende Rennsession und würden die
Auswertung verfälschen. Wer es trotzdem will: `--wiederholung`.

Für einen vollständigen Test reicht eine kurze Trainingssession: allein auf
die Strecke, drei, vier Runden, davon eine mit Boxenstopp. Zehn Minuten und
du hast jeden Kanal gesehen, den das System braucht — inklusive der
Boxenverlust-Messung.

---

## Teil 3 — Hosting

Drei Wege, aufsteigend nach Aufwand. Das Dashboard ist eine einzelne statische
Datei ohne Build — jeder Hoster für statische Seiten kann das.

### Weg A: Netlify Drop (2 Minuten, kein Repo)

1. [app.netlify.com/drop](https://app.netlify.com/drop) öffnen.
2. Den Ordner `dashboard/` ins Browserfenster ziehen.
3. Fertig. Du bekommst eine Adresse wie `zufallsname-123.netlify.app`.

Mit Konto kannst du den Namen ändern und per erneutem Drop aktualisieren. Für
ein Rennwochenende reicht das völlig.

### Weg B: GitHub Pages — alle sehen sofort Daten (empfohlen)

Damit bekommt jeder Fahrer eine Adresse, die er nur öffnen muss. Keine
Schlüssel eintippen, kein Knopf „Verbindung".

```
deploy_dashboard.bat
```

Vor dem Hochladen läuft automatisch eine Sperre, die jede Datei im Upload
nach Zugangsschlüsseln durchsucht. Findet sie einen, bricht sie ab und lädt
nichts hoch. Das ist Absicht: ein service_role-Schlüssel auf GitHub lässt
sich nicht mehr zurücknehmen — Löschen hilft nicht, die History bleibt.

Was **nicht** ins Repo gehört und deshalb ausgeschlossen ist: deine
`pitwall_config.json`, das fertige `Fahrerpaket/`, dessen ZIP, und jede
`config.js`. Das Fahrerpaket verteilst du direkt an die fünf — nicht über
GitHub.

Das Skript fragt einmal nach Supabase-URL und **anon**-Key und legt beides
als GitHub-Secret ab — nicht im Repo. Beim Veröffentlichen baut der Workflow
daraus die `config.js`. So steht kein Schlüssel im Quelltext des Repos, aber
die fertige Seite bringt ihn mit.

Danach einmalig auf GitHub: **Settings → Pages → Source: GitHub Actions**.
Die Adresse lautet dann `https://pfoetiman76.github.io/jcm-pitwall/` — die
gibst du an alle fünf.

**Was das bedeutet:** wer die Adresse kennt, kann eure Rundenzeiten lesen.
Schreiben kann niemand, dafür braucht es den service_role-Key, und der bleibt
auf den Fahrer-PCs. Für ein Hobby-Team ist das der richtige Schnitt. Wer auch
das Lesen dicht haben will, braucht einen bezahlten Plan mit privater Seite —
dafür ist der Aufwand hier nicht.

### Weg C: Vercel

Wie in deinem Architekturpapier vorgesehen. Repo verbinden, als **Root Directory**
`dashboard` eintragen, Framework Preset **Other**, kein Build-Command. Deploy.

---

## Vor dem 24h-Rennen: drei Dinge

1. **Supabase pausiert kostenlose Projekte nach sieben Tagen ohne Zugriff.**
   Das Aufwecken dauert Minuten. Also am Tag vor dem Rennen einmal
   `python tools/check_setup.py` laufen lassen, nicht erst 20 Minuten vor Start.

2. **Testrennen mit allen sechs Fahrern**, ein bis zwei Stunden. Danach zählen:

   ```sql
   select d.driver_name, count(*) as runden, min(l.lap_time) as beste
   from laps l join drivers d on d.id = l.driver_id
   group by d.driver_name order by runden desc;
   ```

   Fehlt bei jemandem alles, hat sein Client keine Zugangsdaten. Fehlen einzelne
   Runden, schau in `client/pitwall_spool.jsonl` — dann hat das Netz gehustet und
   die Runden warten auf den nächsten Start.

3. **Speicher prüfen.** Supabase → Reports → Database. Ein 24h-Rennen kostet unter
   3 MB; wenn dort nach dem Test schon 50 MB stehen, läuft etwas Falsches.

---

## Wenn etwas nicht geht

| Symptom | Ursache | Lösung |
|---|---|---|
| `HTTP 401` beim Client | anon-Key statt service_role in der Config | Schlüssel tauschen |
| `HTTP 404` auf eine Tabelle | Schema nicht eingespielt | `sql/00_setup_all.sql` ausführen |
| Dashboard bleibt auf Demo | keine Zugangsdaten hinterlegt | **Verbindung** → URL und anon-Key |
| „Keine aktive Session" | keine Session mit `is_active = true` | Client mit `--new-session` starten |
| Zeitentabelle leer | Client läuft nicht oder liest kein Feld | `run_client.py --dry-run`, dort steht die Fahrzeugzahl |
| Verbindung bricht ständig ab | Projekt pausiert | im Supabase-Dashboard aufwecken |
