"""Rundenakkumulator.

Sammelt waehrend der Runde alles Noetige im RAM und gibt bei
Start/Ziel-Ueberfahrt genau EIN Payload zurueck. Das ist der Kern der
Free-Tier-Architektur: 50 Hz rein, ~350 Zeilen pro 24h raus.

Integrale (thermische Bremslast, Reibarbeit) werden hier gebildet, nicht
im Backend - der Client hat die hohe Abtastrate, das Backend nicht.
"""

from __future__ import annotations

from typing import Optional


def _avg(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


class LapAccumulator:
    def __init__(self, brake_t_opt_c: float = 500.0):
        self.brake_t_opt_c = brake_t_opt_c
        self.reset(None)
        self.current_lap: Optional[int] = None
        self.fuel_at_lap_start: Optional[float] = None
        self.prev_sample: Optional[dict] = None
        self.pitted_this_lap = False
        self.prev_in_pits = False
        # Rundenzeit selbst rechnen: mLapStartET kommt aus derselben
        # Telemetriestruktur wie mLapNumber, laeuft also im Gleichtakt.
        self.lap_start_et: Optional[float] = None
        # Nachreichen: Sektoren und die offizielle Rundenzeit stehen im
        # Scoring, das langsamer aktualisiert als die Telemetrie. Das
        # Payload wartet deshalb kurz, bevor es rausgeht.
        self.nachlauf_s = 1.5
        self._pending: Optional[dict] = None
        self._pending_bis: float = 0.0
        self._pending_lap_start_et: Optional[float] = None
        self.lap_time_quelle: Optional[str] = None

    # ----------------------------------------------------------------
    def reset(self, sample: Optional[dict]):
        self.samples = 0
        self.max_speed = 0.0
        self.speed_sum = 0.0
        self.max_brake_temp = None
        self.thermal_load = 0.0
        self.friction_work = 0.0
        self.wear_last = None
        self.tyre_temp_sum = [0.0] * 4
        self.tyre_temp_n = 0
        self.tyre_press_last = None
        self.fcy_seen = False
        self.pitted_this_lap = False

    # ----------------------------------------------------------------
    def update(self, s: dict) -> Optional[dict]:
        """Sample einspeisen. Gibt bei Rundenende das Payload zurueck."""
        payload = None
        lap = s.get("lap_number")

        if self.current_lap is None and lap is not None:
            self.current_lap = lap
            self.fuel_at_lap_start = s.get("fuel_l")
            self.lap_start_et = s.get("lap_start_et")
            self.reset(s)
            self.prev_sample = s
            return None

        # --- Start/Ziel ueberfahren -------------------------------
        if lap is not None and self.current_lap is not None and lap > self.current_lap:
            gebaut = self._build_payload(s)
            # Noch nicht ausliefern: Scoring hinkt der Telemetrie hinterher,
            # mLastLapTime und mLastSector1/2 sind in diesem Tick noch die
            # Werte der Vorrunde bzw. leer.
            self._pending = gebaut
            self._pending_bis = float(s.get("t", 0)) + self.nachlauf_s
            self._pending_lap_start_et = self.lap_start_et
            self.current_lap = lap
            self.fuel_at_lap_start = s.get("fuel_l")
            self.lap_start_et = s.get("lap_start_et")
            self.reset(s)

        # --- Integration ------------------------------------------
        prev = self.prev_sample
        dt = 0.0
        if prev is not None:
            dt = max(0.0, min(1.0, float(s.get("t", 0)) - float(prev.get("t", 0))))

        self.samples += 1
        speed = s.get("speed_kmh") or 0.0
        self.max_speed = max(self.max_speed, speed)
        self.speed_sum += speed

        btemps = [t for t in (s.get("brake_temp") or []) if t is not None]
        if btemps:
            peak = max(btemps)
            self.max_brake_temp = peak if self.max_brake_temp is None else max(self.max_brake_temp, peak)
            # Integral(max(T - T_opt, 0)) dt  -> Grad C * s
            self.thermal_load += max(0.0, peak - self.brake_t_opt_c) * dt

        bpress = [p for p in (s.get("brake_pressure") or []) if p is not None]
        if bpress:
            # Integral(Druck * v) dt -> relativer Index, keine Joule
            self.friction_work += max(bpress) * (speed / 3.6) * dt

        wear = s.get("wear")
        if wear and any(w is not None for w in wear):
            self.wear_last = wear
        press = s.get("tyre_press")
        if press and any(p is not None for p in press):
            self.tyre_press_last = press
        ttemp = s.get("tyre_temp")
        if ttemp and all(t is not None for t in ttemp):
            for i in range(4):
                self.tyre_temp_sum[i] += ttemp[i]
            self.tyre_temp_n += 1

        # Gelbphase: LMU fuehrt das pro Fahrzeug in mUnderYellow. Das ist
        # belastbar - die frueher hier geratenen mGamePhase-Werte waren es nicht.
        if s.get("under_yellow"):
            self.fcy_seen = True
        elif s.get("game_phase") in (4, 6, 7) and s.get("under_yellow") is None:
            self.fcy_seen = True

        in_pits = bool(s.get("in_pits"))
        if in_pits and not self.prev_in_pits:
            self.pitted_this_lap = True
        self.prev_in_pits = in_pits

        self.prev_sample = s

        if self._pending is not None and float(s.get("t", 0)) >= self._pending_bis:
            payload = self._finalisieren(s)
        return payload

    # ----------------------------------------------------------------
    def _finalisieren(self, s: dict) -> dict:
        """Geparktes Payload fertigstellen.

        Jetzt, gut eine Sekunde nach der Start/Ziel-Ueberfahrt, hat das
        Scoring nachgezogen. Reihenfolge fuer die Rundenzeit:

          1. die offizielle aus mLastLapTime, wenn sie plausibel ist,
          2. sonst die selbst gerechnete aus mLapStartET.

        Punkt 2 ist der Grund, warum ueberhaupt Zeiten ankommen: bei
        ungueltigen Runden (Outlap, Streckenbegrenzung) laesst LMU
        mLastLapTime auf -1 stehen, die Runde ist aber trotzdem gefahren
        worden und die Dauer interessiert uns.
        """
        p = self._pending
        self._pending = None

        gerechnet = None
        neu, alt = s.get("lap_start_et"), self._pending_lap_start_et
        if neu and alt and neu > alt:
            gerechnet = round(neu - alt, 3)

        offiziell = s.get("last_lap_time")
        if offiziell and offiziell > 0 and (
                gerechnet is None or abs(offiziell - gerechnet) < 5.0):
            lap_time = round(offiziell, 3)
            self.lap_time_quelle = "spiel"
        elif gerechnet and 10.0 < gerechnet < 1800.0:
            lap_time = gerechnet
            self.lap_time_quelle = "gerechnet"
        else:
            lap_time = None
            self.lap_time_quelle = None

        # Sektoren stehen jetzt ebenfalls im Scoring.
        s1 = s.get("sector1")
        s2_cum = s.get("sector2")
        s2 = round(s2_cum - s1, 3) if (s1 and s2_cum and s2_cum > s1) else None
        s3 = (round(lap_time - s2_cum, 3)
              if (lap_time and s2_cum and lap_time > s2_cum) else None)

        p["lap_time"] = lap_time
        p["s1"] = round(s1, 3) if s1 else None
        p["s2"] = s2
        p["s3"] = s3
        # Gueltig ist eine Runde nur mit offizieller Zeit. Eine selbst
        # gerechnete Dauer ist gut genug fuer Sprit- und Boxenrechnung,
        # aber sie darf nicht als Bestzeit in die Wertung.
        p["is_valid"] = bool(offiziell and offiziell > 0
                             and not p.get("under_fcy")
                             and not p.get("_invalidated"))
        p.pop("_invalidated", None)
        return p

    def flush(self) -> Optional[dict]:
        """Beim Beenden noch geparktes Payload herausgeben."""
        if self._pending is None:
            return None
        return self._finalisieren(self.prev_sample or {})

    # ----------------------------------------------------------------
    def _build_payload(self, s: dict) -> dict:
        fuel_now = s.get("fuel_l")
        fuel_used = None
        if self.fuel_at_lap_start is not None and fuel_now is not None:
            diff = self.fuel_at_lap_start - fuel_now
            fuel_used = round(diff, 3) if diff > 0 else None  # Tanken -> kein Verbrauch

        # lap_time, s1, s2, s3 und is_valid setzt _finalisieren nach, sobald
        # das Scoring nachgezogen hat. Hier stehen sie bewusst leer.

        tyre_temp_avg = (
            [round(v / self.tyre_temp_n, 2) for v in self.tyre_temp_sum]
            if self.tyre_temp_n else [None] * 4
        )
        wear = self.wear_last or [None] * 4
        press = self.tyre_press_last or [None] * 4

        return {
            "lap_num": self.current_lap,
            "lap_time": None,
            "s1": None,
            "s2": None,
            "s3": None,
            "is_valid": False,
            "_invalidated": bool(s.get("lap_invalidated")),
            "is_inlap": self.pitted_this_lap,
            "is_outlap": False,   # wird vom Runner aus dem Vorgaenger gesetzt
            "under_fcy": self.fcy_seen,
            "position": s.get("position"),
            "gap_to_leader": s.get("gap_to_leader"),
            "race_time_s": s.get("et"),
            "telemetry": {
                "fuel_used_l": fuel_used,
                "fuel_remaining_l": round(fuel_now, 3) if fuel_now is not None else None,
                "virtual_energy_pct": s.get("virtual_energy"),
                "wear_fl": wear[0], "wear_fr": wear[1],
                "wear_rl": wear[2], "wear_rr": wear[3],
                "tyre_temp_fl": tyre_temp_avg[0], "tyre_temp_fr": tyre_temp_avg[1],
                "tyre_temp_rl": tyre_temp_avg[2], "tyre_temp_rr": tyre_temp_avg[3],
                "tyre_press_fl": press[0], "tyre_press_fr": press[1],
                "tyre_press_rl": press[2], "tyre_press_rr": press[3],
                "max_brake_temp_c": round(self.max_brake_temp, 2) if self.max_brake_temp else None,
                "brake_thermal_load": round(self.thermal_load, 2),
                "brake_friction_work": round(self.friction_work, 2),
                "max_speed_kmh": round(self.max_speed, 2),
                "avg_speed_kmh": round(self.speed_sum / self.samples, 2) if self.samples else None,
                "track_temp_c": s.get("track_temp"),
                "ambient_temp_c": s.get("ambient_temp"),
                "rain_pct": (s.get("raining") or 0) * 100 if s.get("raining") is not None else None,
                "track_wetness_pct": (s.get("wetness") or 0) * 100 if s.get("wetness") is not None else None,
            },
        }
