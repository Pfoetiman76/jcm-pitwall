"""JCM Pitwall - Fahrer-Client.

Laeuft auf dem PC des jeweils aktiven Fahrers, liest die Shared Memory,
aggregiert pro Runde und schiebt ein Payload an Supabase.

    python run_client.py                 # LMU, echte Shared Memory
    python run_client.py --sim rf2       # rFactor 2
    python run_client.py --demo          # ohne Sim, Zeitraffer-Rennen
    python run_client.py --session <uuid>  # an laufende Session andocken
    python run_client.py --dry-run       # nichts hochladen, nur anzeigen

Der erste Client, der startet, legt die Session an und schreibt die
Session-ID nach current_session.txt. Die anderen 5 Fahrer starten mit
--session <uuid> oder legen die Datei einfach in den Ordner.
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config as cfg_mod
from accumulator import LapAccumulator
from field import FieldTracker
from lmu_rest import LmuRest
from source import SharedMemorySource, SimulatorSource, TelemetrieNichtGefunden
from uploader import SupabaseClient

HERE = Path(__file__).resolve().parent
# Schreibpfade kommen aus config -- als EXE ist HERE das Auspack-
# verzeichnis und damit weder geteilt noch dauerhaft.
DATA = cfg_mod.data_dir()
SESSION_FILE = DATA / "current_session.txt"

_running = True


def _stop(*_):
    global _running
    _running = False
    print("\n[client] beende sauber ...")


class PitwallClient:
    # Eine Session gilt als "laeuft noch", wenn ihr letzter field_state juenger
    # als das hier ist. Waehrend eines echten Rennens kommt alle ~2 s ein
    # field_state, also ist eine laufende Session immer sekundenfrisch - auch
    # ueber Mitternacht hinweg im 24h-Lauf. Die 20 min sind reine Toleranz fuer
    # die Luecke bei einem Fahrerwechsel (Client 1 aus, Client 2 an). Eine
    # Geister-Session vom Vortag ist dagegen Stunden alt und faellt raus.
    SESSION_FRESH_MIN = 20.0

    def __init__(self, cfg, args):
        self.cfg = cfg
        self.args = args
        self.dry = args.dry_run or not cfg.configured
        self.db = SupabaseClient(cfg.rest_url, cfg.supabase_key, DATA / cfg.spool_file)
        self.acc = LapAccumulator(brake_t_opt_c=cfg.brake_t_opt_c)
        self.session_id = None
        self.driver_id = None
        self.prev_was_inlap = False
        self._box_zuletzt = False
        self._box_puffer = []
        self.laps_sent = 0
        self.field = FieldTracker()
        self.field_every = 2.0        # Sekunden zwischen Feld-Upserts (frischer aufs Dashboard)
        self.weather_every = 60.0     # Sekunden zwischen Wetter-Zeilen
        self._next_field = 0.0
        self._next_weather = 0.0
        self._ref_lap = None          # saubere Referenzrunde fuer den Boxenverlust
        self._replay_gemeldet = False
        self._dmg = {}          # letzter Karosserieschaden-Stand (aus source.read)
        self._trackmap_done = False   # Streckenkarte nur einmal pro Lauf hochladen
        # LMUs lokale REST-Schnittstelle: echter Bremsbelagverschleiss und
        # Wettervorhersage. Beides gibt es in der Shared Memory nicht.
        self.rest = LmuRest() if not args.demo else None
        self._rest_gemeldet = False

        if args.demo:
            self.source = SimulatorSource(speedup=args.speedup)
            print("[client] Demo-Modus: simuliertes 24h-Rennen im Zeitraffer")
        else:
            self.source = SharedMemorySource(sim=cfg.sim)
            print(f"[client] Shared Memory: {cfg.sim}")

        if self.dry:
            print("[client] DRY RUN - es wird nichts hochgeladen")

    # ----------------------------------------------------------------
    def ensure_driver(self):
        if self.dry:
            return
        name = self.cfg.driver_name
        try:
            rows = self.db.get(f"drivers?driver_name=eq.{name}&select=id")
            if rows:
                self.driver_id = rows[0]["id"]
                return
        except Exception as exc:
            print(f"[client] Fahrer-Lookup fehlgeschlagen: {exc}")
        row = self.db.safe_insert("drivers", {
            "driver_name": name,
            "short_name": name[:3].upper(),
        })
        if row:
            self.driver_id = row["id"]
        print(f"[client] Fahrer: {name} ({self.driver_id})")

    @staticmethod
    def _within_minutes(iso_ts, minutes: float) -> bool:
        """True, wenn der Zeitstempel (Postgres-ISO) hoechstens `minutes` alt ist.
        Bei Parse-Problemen bewusst False -> die Session gilt als nicht frisch und
        es wird lieber eine neue angelegt, statt in eine tote hineinzuschreiben."""
        if not iso_ts:
            return False
        try:
            s = str(iso_ts).strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            return age <= minutes * 60          # negatives Alter (Uhr-Drift) zaehlt als frisch
        except Exception:
            return False

    def _session_is_live(self, sid: str) -> bool:
        """Laeuft die Session noch? is_active gesetzt UND kuerzlich Aktivitaet
        (letzter field_state, ersatzweise started_at). Verhindert, dass ein alter
        SESSION_FILE-Eintrag oder eine is_active-Geister-Session vom Vortag
        wiederbelebt bzw. angedockt wird."""
        try:
            rows = self.db.get(f"sessions?id=eq.{sid}&select=is_active,started_at&limit=1")
            if not rows or rows[0].get("is_active") is False:
                return False
            last = None
            fs = self.db.get(
                f"field_state?session_id=eq.{sid}&select=updated_at&order=updated_at.desc&limit=1")
            if fs:
                last = fs[0].get("updated_at")
            if last is None:
                last = rows[0].get("started_at")     # noch kein field_state -> Startzeit
            return self._within_minutes(last, self.SESSION_FRESH_MIN)
        except Exception as exc:
            print(f"[client] Frische-Pruefung fehlgeschlagen ({exc}) - behandle Session als nicht aktiv")
            return False

    def ensure_session(self, sample: dict):
        # 1) Ausdruecklich per --session vorgegeben: immer respektieren.
        if self.args.session:
            self.session_id = self.args.session
            print(f"[client] Session: {self.session_id}")
            return
        if self.dry:
            return

        # 2) Auf diesem PC gecachte Session wiederaufnehmen - aber nur, wenn sie
        #    noch laeuft. Sonst wuerde ein Eintrag vom Vortag eine tote Session
        #    wiederbeleben: Uploads liefen ins Leere, das Dashboard zeigt Altes.
        #    (Genau diese Falle war heute der Ausloeser.) Bei einem Crash-Neustart
        #    mitten im Stint ist die Session sekundenfrisch und wird korrekt wieder
        #    aufgenommen.
        if SESSION_FILE.exists() and not self.args.new_session:
            cached = SESSION_FILE.read_text(encoding="utf-8").strip() or None
            if cached and self._session_is_live(cached):
                self.session_id = cached
                print(f"[client] Session: {self.session_id} (wiederaufgenommen)")
                return
            if cached:
                print("[client] Gespeicherte Session ist nicht mehr aktiv - ignoriere sie.")

        # 3) Laeuft auf einem anderen PC schon eine Session (Fahrerwechsel)? Andocken
        #    statt eine zweite anlegen - aber nur, wenn sie frisch ist. Eine
        #    Geister-Session vom Vortag wird NICHT adoptiert, sondern geschlossen.
        if not self.args.new_session:
            try:
                rows = self.db.get(
                    "sessions?is_active=eq.true&order=started_at.desc&limit=1&select=id,track_name")
                if rows and self._session_is_live(rows[0]["id"]):
                    self.session_id = rows[0]["id"]
                    SESSION_FILE.write_text(self.session_id, encoding="utf-8")
                    print(f"[client] An laufende Session angedockt: {rows[0].get('track_name')}")
                    return
                if rows:
                    stale = rows[0]["id"]
                    try:
                        self.db.patch("sessions", f"id=eq.{stale}",
                                      {"is_active": False, "ended_at": "now()"})
                        print("[client] Alte, inaktive Session gefunden und geschlossen.")
                    except Exception:
                        pass
            except Exception as exc:
                print(f"[client] Suche nach laufender Session fehlgeschlagen: {exc}")

        # 4) Nichts Frisches da -> neue Session anlegen (explizit aktiv).
        row = self.db.safe_insert("sessions", {
            "sim": self.cfg.sim,
            "track_name": sample.get("track_name") or "Unbekannt",
            "car_name": sample.get("car_name"),
            "car_class": sample.get("car_class"),
            "session_type": "RACE",
            "planned_hours": self.args.hours,
            "fuel_capacity_l": sample.get("fuel_capacity_l"),
            "track_temp_c": sample.get("track_temp"),
            "ambient_temp_c": sample.get("ambient_temp"),
            "is_active": True,
        })
        if row:
            self.session_id = row["id"]
            SESSION_FILE.write_text(self.session_id, encoding="utf-8")
            print(f"[client] Neue Session angelegt: {self.session_id}")
            print(f"[client] Diese ID bekommen die anderen Fahrer: {self.session_id}")

    # ----------------------------------------------------------------
    def _ist_wiederholung(self, sample: dict) -> bool:
        """Wiederholung oder Zuschauermodus erkennen.

        Wird sonst gefaehrlich: die Rundenzeiten einer Wiederholung wuerden
        in die laufende Rennsession geschrieben und die Auswertung verfaelschen.
        """
        rt = sample.get("in_realtime")
        if rt is None:
            return False
        return not rt and not (sample.get("ignition") or 0)

    def send_lap(self, payload: dict, spooled: bool = False):
        payload = dict(payload)
        telemetry = payload.pop("telemetry", {})
        payload["is_outlap"] = self.prev_was_inlap
        self.prev_was_inlap = payload.get("is_inlap", False)

        if self.rest is not None and self.rest.wearables.get("hat_werte"):
            w = self.rest.wearables
            rest_pct = w["brake_left_pct"]
            susp = w.get("suspension") or []
            # Suspension je Ecke (Roh 0=neu..1=hin -> Schaden in %) fuer die
            # Schadenskarte; suspension_max_pct bleibt fuer Abwaertskompatibilitaet.
            sp = [None if (i >= len(susp) or susp[i] is None) else round(susp[i] * 100, 2)
                  for i in range(4)]
            telemetry.update({
                "brake_pad_fl": rest_pct[0], "brake_pad_fr": rest_pct[1],
                "brake_pad_rl": rest_pct[2], "brake_pad_rr": rest_pct[3],
                "aero_damage_pct": None if w.get("aero_damage") is None
                                   else round(w["aero_damage"] * 100, 2),
                "suspension_fl": sp[0], "suspension_fr": sp[1],
                "suspension_rl": sp[2], "suspension_rr": sp[3],
                "suspension_max_pct": (round(max(x for x in susp if x is not None) * 100, 2)
                                       if any(x is not None for x in susp) else None),
            })

        # Karosserieschaden aus der Shared Memory (unabhaengig von der REST-Schnittstelle).
        dmg = getattr(self, "_dmg", None) or {}
        flat = dmg.get("flat") or [None, None, None, None]
        telemetry.update({
            "dent_front": dmg.get("dent_front"),
            "dent_rear": dmg.get("dent_rear"),
            "detached": dmg.get("detached"),
            "flat_fl": bool(flat[0]) if flat[0] is not None else None,
            "flat_fr": bool(flat[1]) if flat[1] is not None else None,
            "flat_rl": bool(flat[2]) if flat[2] is not None else None,
            "flat_rr": bool(flat[3]) if flat[3] is not None else None,
        })

        # Live geplante Boxenstoppdauer aus der REST-Schnittstelle (Pit-Menue).
        pe = self.rest.pit_estimate if self.rest is not None else None
        if pe:
            telemetry.update({
                "pit_estimate_s": pe.get("total"),
                "pit_est_fuel": pe.get("fuel"),
                "pit_est_tires": pe.get("tires"),
                "pit_est_damage": pe.get("damage"),
                "pit_est_driver": pe.get("driver"),
            })

        lt = payload.get("lap_time")
        # Referenz ist die schnellste SAUBERE Runde - unabhaengig davon, ob
        # das Spiel sie als gueltig fuehrt. Sonst gibt es bei einer Session
        # voller ungueltiger Runden nie einen Bezugswert, und damit auch
        # nie einen Boxenverlust.
        sauber = bool(lt and not payload.get("is_inlap")
                      and not payload.get("is_outlap")
                      and not payload.get("under_fcy"))
        if sauber:
            self._ref_lap = lt if self._ref_lap is None else min(self._ref_lap, lt)
            # Nachtrag: In-/Outlaps, die vor der ersten sauberen Runde lagen.
            # Betrifft jeden Rennstart aus der Box heraus - ohne das faellt
            # der erste Boxenverlust dauerhaft unter den Tisch.
            if self._box_puffer:
                for zeit, art in self._box_puffer:
                    self.field.observe_pit_loss(zeit, self._ref_lap, art)
                print(f"[box] {len(self._box_puffer)} frueherer Boxenrunde(n) "
                      f"nachtraeglich ausgewertet")
                self._box_puffer.clear()
        elif lt and (payload.get("is_inlap") or payload.get("is_outlap")):
            art = "in" if payload.get("is_inlap") else "out"
            if self._ref_lap:
                self.field.observe_pit_loss(lt, self._ref_lap, art)
            elif len(self._box_puffer) < 6:
                # Noch keine Referenz - Zeit aufheben statt wegwerfen.
                self._box_puffer.append((lt, art))

        self._log_lap(payload, telemetry)
        if self.dry or not self.session_id:
            return

        payload["session_id"] = self.session_id
        payload["driver_id"] = self.driver_id
        # Upsert statt Insert: bei Client-Neustart / Andocken an dieselbe Session
        # kommt dieselbe Runde erneut -> unique(session_id,lap_num) warf sonst 409,
        # die Runde ging verloren und stint_telemetry wurde uebersprungen.
        lap_row = self.db.safe_upsert("laps", payload,
                                      on_conflict="session_id,lap_num", spool_kind="lap")
        if not lap_row:
            return
        telemetry["lap_id"] = lap_row["id"]
        telemetry["session_id"] = self.session_id
        self.db.safe_upsert("stint_telemetry", telemetry,
                            on_conflict="lap_id", spool_kind="telemetry")
        self.laps_sent += 1

    # ----------------------------------------------------------------
    def push_field(self, now: float):
        """Feldstand, Gegnerrunden und Wetter hochladen.

        Der Feldstand ist EIN Upsert pro Intervall - keine Historie, kein
        Zeilenwachstum. Gegnerrunden gehen als Batch raus, sobald welche
        anfallen."""
        if not hasattr(self.source, "read_field"):
            return
        try:
            field = self.source.read_field()
        except Exception as exc:
            print(f"[feld] Auslesen fehlgeschlagen: {exc}")
            return
        if not field.get("vehicles"):
            return

        self.field.annotate(field)
        new_laps = self.field.new_laps(field)

        if self.dry or not self.session_id:
            if now >= self._next_field:
                self._next_field = now + self.field_every
                player = next((v for v in field["vehicles"] if v.get("is_player")), None)
                pos = f"P{player['place']} (Kl. P{player.get('class_position')})" if player else "-"
                print(f"[feld] {len(field['vehicles'])} Fahrzeuge, {len(field.get('classes') or [])} Klassen, "
                      f"eigenes Auto {pos}, Boxenverlust {self.field.pit_loss()} s")
            return

        if new_laps:
            for row in new_laps:
                row["session_id"] = self.session_id
            self.db.safe_upsert("opponent_laps", new_laps,
                                on_conflict="session_id,vehicle_id,lap_num")

        if now >= self._next_field:
            self._next_field = now + self.field_every
            self.db.upsert("field_state", {
                "session_id": self.session_id,
                "updated_at": "now()",
                "race_time_s": field.get("race_time_s"),
                "leader_laps": field.get("leader_laps"),
                "pit_loss_s": field.get("pit_loss_s"),
                "track_length_m": field.get("track_length_m"),
                "session_remaining_s": field.get("session_remaining_s"),
                "weather_forecast": (self.rest.forecast if self.rest else None) or None,
                "vehicles": field.get("vehicles"),
                "weather": field.get("weather"),
            }, on_conflict="session_id")

        if now >= self._next_weather:
            self._next_weather = now + self.weather_every
            w = field.get("weather") or {}
            self.db.safe_insert("weather_log", {
                "session_id": self.session_id,
                "race_time_s": field.get("race_time_s"),
                "track_temp_c": w.get("track_temp_c"),
                "ambient_temp_c": w.get("ambient_temp_c"),
                "rain_pct": w.get("rain_pct"),
                "wetness_avg_pct": w.get("wetness_avg_pct"),
                "wetness_min_pct": w.get("wetness_min_pct"),
                "wetness_max_pct": w.get("wetness_max_pct"),
                "cloud_pct": w.get("cloud_pct"),
                "wind_kmh": w.get("wind_kmh"),
                "dark_cloud": w.get("dark_cloud"),
            }, spool_kind=None)

    def _log_lap(self, p: dict, t: dict):
        lt = p.get("lap_time")
        lt_str = f"{int(lt // 60)}:{lt % 60:06.3f}" if lt else "--:--.---"
        # ~ heisst: Dauer selbst aus mLapStartET gerechnet, weil das Spiel
        # keine offizielle Rundenzeit geliefert hat.
        if getattr(self.acc, "lap_time_quelle", None) == "gerechnet":
            lt_str += "~"
        flags = "".join([
            "I" if p.get("is_inlap") else "",
            "O" if p.get("is_outlap") else "",
            "Y" if p.get("under_fcy") else "",
            "!" if not p.get("is_valid") else "",
        ]) or "-"
        wear = t.get("wear_fl")
        print(
            f"[Runde {p.get('lap_num'):>3}] {lt_str}  "
            f"Sprit {t.get('fuel_used_l')} l/Rd, Rest {t.get('fuel_remaining_l')} l  "
            f"Reifen VL {round(wear * 100, 1) if wear else '--'} %  "
            f"Bremse max {t.get('max_brake_temp_c')} C  "
            + (f"Belag {t.get('brake_pad_fl')} %  " if t.get("brake_pad_fl") is not None else "")
            + f"[{flags}]"
        )

    # ----------------------------------------------------------------
    def _upload_trackmap(self):
        """Holt die Streckenkontur einmalig aus der REST-Schnittstelle und legt sie
        in session_trackmap ab. Beim Fahrerwechsel teilen sich alle dieselbe
        Session -> upsert auf session_id, spaetere Clients ueberschreiben nur
        identisch. Faellt still aus, wenn die Karte nicht kommt (Dashboard nutzt
        dann die Ersatzform aus den Fahrzeugpositionen)."""
        try:
            tm = self.rest.trackmap()
        except Exception as exc:
            print(f"[client] Streckenkarte nicht abrufbar: {exc}")
            return
        if not tm or len(tm.get("line") or []) < 10:
            return
        self.db.safe_upsert(
            "session_trackmap",
            {"session_id": self.session_id, "line": tm["line"], "pit": tm["pit"]},
            on_conflict="session_id",
        )
        print(f"[client] Streckenkarte hochgeladen ({len(tm['line'])} Linien-, "
              f"{len(tm.get('pit') or [])} Boxenpunkte).")

    def run(self):
        interval = 1.0 / max(1, self.cfg.poll_hz)
        first = None
        print("[client] warte auf Telemetrie ...")
        while _running and first is None:
            s = self.source.read()
            if s.get("lap_number") is not None:
                first = s
            else:
                time.sleep(0.5)
        if first is None:
            return

        self.ensure_driver()
        self.ensure_session(first)
        if not self.dry and self.db.spool_count():
            n = self.db.flush_spool(lambda kind, payload, spooled=True: self._replay(kind, payload))
            print(f"[client] {n} nachgereichte Datensaetze aus dem Spool gesendet")

        last_status = 0.0
        deadline = time.time() + self.args.minutes * 60 if self.args.minutes else None
        while _running:
            if deadline and time.time() > deadline:
                print(f"[client] {self.args.minutes:.0f} Minuten erreicht - Ende")
                break
            try:
                sample = self.source.read()

                if sample.get("dent_front") is not None or sample.get("dent_rear") is not None \
                        or sample.get("flat") is not None:
                    self._dmg = {
                        "dent_front": sample.get("dent_front"),
                        "dent_rear": sample.get("dent_rear"),
                        "detached": bool(sample.get("detached")),
                        "flat": sample.get("flat") or [False, False, False, False],
                    }

                if self._ist_wiederholung(sample) and not self.args.wiederholung:
                    if not self._replay_gemeldet:
                        self._replay_gemeldet = True
                        print("[client] Wiederholung oder Zuschauermodus erkannt - es wird")
                        print("[client] nichts hochgeladen. Wiederholungen enthalten keine")
                        print("[client] Physikdaten (Sprit, Reifen, Bremsen), und die Zeiten")
                        print("[client] wuerden die laufende Session verfaelschen.")
                        print("[client] Mit --wiederholung trotzdem senden.")
                    time.sleep(1.0)
                    continue
                if self._replay_gemeldet and not self._ist_wiederholung(sample):
                    self._replay_gemeldet = False
                    print("[client] Wieder im Auto - Aufzeichnung laeuft.")

                if self.rest is not None:
                    stand = self.rest.tick(sample.get("session_type"))
                    if stand["verfuegbar"] and not self._rest_gemeldet:
                        self._rest_gemeldet = True
                        w = stand["wearables"].get("brake_left_pct") or []
                        print("[rest] LMU-Schnittstelle erreichbar - echter Bremsbelag "
                              f"{w if w else 'noch ohne Werte'}")
                    # Streckenkarte einmal pro Lauf hochladen, sobald REST bestaetigt.
                    if stand["verfuegbar"] and not self._trackmap_done \
                            and self.session_id and not self.dry:
                        self._trackmap_done = True
                        self._upload_trackmap()

                # Boxen-Diagnose: zeigt sofort, ob mInPits ueberhaupt kippt.
                jetzt_box = bool(sample.get("in_pits"))
                if jetzt_box != self._box_zuletzt:
                    self._box_zuletzt = jetzt_box
                    print("[box] Boxengasse betreten" if jetzt_box
                          else "[box] Boxengasse verlassen")

                payload = self.acc.update(sample)
                if payload:
                    self.send_lap(payload)
                now = time.time()
                self.push_field(now)
                if now - last_status > 60:
                    last_status = now
                    state = "online" if self.db.online else "OFFLINE (spoolt)"
                    print(f"[client] laeuft - {self.laps_sent} Runden gesendet, {state}")
            except Exception as exc:
                print(f"[client] Fehler im Loop: {exc}")
                time.sleep(1.0)
            time.sleep(interval)

        # Die letzte Runde haengt eventuell noch im Nachlauf.
        rest_payload = self.acc.flush()
        if rest_payload:
            self.send_lap(rest_payload)

        if self.session_id and not self.dry and self.args.close_session:
            self.db.patch("sessions", f"id=eq.{self.session_id}",
                          {"is_active": False, "ended_at": "now()"})
            print("[client] Session geschlossen")

    def _replay(self, kind: str, payload: dict, spooled: bool = True):
        table = "laps" if kind == "lap" else "stint_telemetry"
        conflict = "session_id,lap_num" if kind == "lap" else "lap_id"
        return self.db.upsert(table, payload, conflict)


def main():
    # stdout/stderr zeilenweise flushen. Sonst puffert vor allem die onefile-EXE
    # im Block: der Client laeuft und laedt hoch, aber die [Runde]-/Session-Zeilen
    # erreichen das Fahrer-Fenster nie -> es bleibt faelschlich auf "warte auf
    # Telemetrie" tuerkis stehen. None-sicher fuer den windowed-Fall (stdout=None).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(line_buffering=True)
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="JCM Pitwall Fahrer-Client")
    ap.add_argument("--demo", action="store_true", help="ohne Sim, simuliertes Rennen")
    ap.add_argument("--speedup", type=float, default=30.0, help="Zeitraffer im Demo-Modus")
    ap.add_argument("--sim", choices=["lmu", "rf2"], help="ueberschreibt die Config")
    ap.add_argument("--session", help="UUID einer laufenden Session")
    ap.add_argument("--new-session", action="store_true", help="neue Session erzwingen")
    ap.add_argument("--close-session", action="store_true", help="Session beim Beenden schliessen")
    ap.add_argument("--driver", help="ueberschreibt den Fahrernamen")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--minutes", type=float, help="nach N Minuten automatisch beenden (fuer Testlaeufe)")
    ap.add_argument("--wiederholung", action="store_true",
                    help="auch aus einer Wiederholung hochladen (Sprit/Reifen fehlen dann)")
    args = ap.parse_args()

    cfg = cfg_mod.load()
    if args.sim:
        cfg.sim = args.sim.upper()
    if args.driver:
        cfg.driver_name = args.driver

    if not cfg.configured and not args.dry_run and not args.demo:
        print("Keine Supabase-Zugangsdaten gefunden.")
        print(f"Keine Zugangsdaten in {cfg_mod.CONFIG_PATH}")
        print("Im Fahrer-Fenster den Team-Code einfuegen "
              "(oder: python config.py fuer eine Vorlage).")
        print("und trage supabase_url + supabase_key ein. Bis dahin: --dry-run oder --demo")
        return 1

    signal.signal(signal.SIGINT, _stop)
    # Die GUI schickt beim STOPP ein CTRL_BREAK an die Prozessgruppe. Windows
    # liefert das als SIGBREAK (nicht SIGINT) -> auch darauf sauber beenden, damit
    # der Nachlauf (letzte Runde flushen) noch durchlaeuft.
    _sigbreak = getattr(signal, "SIGBREAK", None)
    if _sigbreak is not None:
        try:
            signal.signal(_sigbreak, _stop)
        except (ValueError, OSError):
            pass
    try:
        PitwallClient(cfg, args).run()
    except TelemetrieNichtGefunden as exc:
        print("\n[client] " + str(exc))
        return 2
    except Exception as exc:
        print(f"\n[client] Unerwarteter Fehler: {exc}")
        print("[client] Bitte Marcel einen Screenshot vom Fenster schicken.")
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())