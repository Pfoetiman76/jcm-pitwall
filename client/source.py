"""Telemetriequelle.

Liest Le Mans Ultimate ueber pyLMUSharedMemory (MIT, TinyPedal-Projekt,
liegt im Unterordner bei). Zweite Implementierung mit gleichem Interface:
ein Simulator fuer Tests ohne laufenden Sim.

Die Feldnamen und Zugriffspfade hier sind gegen den echten Quelltext von
pyLMUSharedMemory geprueft, nicht geraten. Drei Fallen stecken darin:

  1. Telemetrie-Index und Scoring-Index sind NICHT dieselben. Zugeordnet
     wird ueber mID, sonst mischt man stillschweigend Fahrzeuge.
  2. mTemperature je Rad ist ein Feld aus DREI Werten (innen/mitte/aussen)
     in Kelvin, kein einzelner Wert.
  3. mLastSector2 ist kumuliert, mSector zaehlt 0=Sektor3, 1=Sektor1,
     2=Sektor2. Nicht fragen, steht so im Header von Studio 397.
"""

from __future__ import annotations

import math
import random
import re
import time
from typing import Any, Optional

KELVIN_OFFSET = 273.15
_NUM_RE = re.compile(r"#\s*(\d{1,3})")


class TelemetrieNichtGefunden(RuntimeError):
    """Der Shared-Memory-Zugang des Sims fehlt oder das Spiel laeuft nicht."""


# --------------------------------------------------------------------
# Hilfen
# --------------------------------------------------------------------
def _decode(value: Any) -> Optional[str]:
    if isinstance(value, (bytes, bytearray)):
        text = value.decode("utf-8", errors="ignore").strip("\x00").strip()
        return text or None
    if value is None:
        return None
    return str(value).strip() or None


def _celsius(value: Optional[float]) -> Optional[float]:
    """Kelvin oder Celsius? Der Header sagt Celsius, geliefert wird je nach
    Feld Kelvin. Ueber die Groessenordnung erkannt - dieselbe Heuristik,
    die sich im Consistency Coach bewaehrt hat."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v == 0.0:
        return None
    return round(v - KELVIN_OFFSET, 2) if v > 200.0 else round(v, 2)


def _tyre_temp(wheel) -> Optional[float]:
    """Mittel aus innen/mitte/aussen. Der Header sagt hier eindeutig
    Kelvin, also wird immer umgerechnet - keine Heuristik noetig."""
    try:
        vals = [v for v in wheel.mTemperature if v]
    except Exception:
        return None
    if not vals:
        return None
    return round(sum(vals) / len(vals) - KELVIN_OFFSET, 2)


def _speed_kmh(vect) -> float:
    try:
        return 3.6 * math.sqrt(vect.x ** 2 + vect.y ** 2 + vect.z ** 2)
    except Exception:
        return 0.0


def _car_number(*texts) -> Optional[str]:
    for text in texts:
        if text:
            m = _NUM_RE.search(str(text))
            if m:
                return m.group(1)
    return None


def _nz(value):
    """0.0 bedeutet bei vielen LMU-Feldern 'nicht gesetzt'."""
    return value if value else None


# ====================================================================
# Le Mans Ultimate / rFactor 2
# ====================================================================
class SharedMemorySource:
    def __init__(self, sim: str = "LMU", reader: Any = None):
        self.sim = (sim or "LMU").upper()
        self.info = reader if reader is not None else self._connect()
        self._tele_index: dict[int, int] = {}
        self._tele_index_stamp = 0.0
        # Bremstemperaturen: der Header sagt Celsius, rF2/LMU liefern je nach
        # Build Kelvin. Ueber einen Schwellwert je Messwert ist das NICHT zu
        # entscheiden - 612 waere als Celsius voellig normal und als Kelvin
        # ebenso. Also wie im Consistency Coach ueber das Sessionminimum:
        # kalte Bremsen liegen bei Umgebungstemperatur, also klar unter 200.
        self._brake_min = float("inf")

    # ----------------------------------------------------------------
    def _connect(self):
        if self.sim == "RF2":
            try:
                import pyRfactor2SharedMemory.sharedMemoryAPI as api  # type: ignore
                return api.SimInfoAPI()
            except ImportError as exc:
                raise TelemetrieNichtGefunden(
                    "Fuer rFactor 2 fehlt pyRfactor2SharedMemory.\n"
                    "  Das ist kein Fehler von dir - bitte Marcel Bescheid geben."
                ) from exc
        try:
            from pyLMUSharedMemory import lmu_data
        except ImportError as exc:
            raise TelemetrieNichtGefunden(
                "Der Telemetrie-Baustein fuer Le Mans Ultimate fehlt im Ordner.\n"
                "  Das ist kein Fehler von dir - bitte Marcel Bescheid geben."
            ) from exc
        try:
            return lmu_data.SimInfo()
        except Exception as exc:
            raise TelemetrieNichtGefunden(
                "Le Mans Ultimate wurde nicht gefunden.\n"
                "  Bitte das Spiel starten und ins Auto setzen, dann nochmal START.\n"
                f"  (technisch: {exc})"
            ) from exc

    # ----------------------------------------------------------------
    @property
    def data(self):
        return self.info.LMUData

    def available(self) -> bool:
        try:
            return bool(self.data.telemetry.playerHasVehicle)
        except Exception:
            return False

    def _scoring_player_index(self) -> int:
        veh = self.data.scoring.vehScoringInfo
        total = self.data.scoring.scoringInfo.mNumVehicles
        for i in range(min(int(total), len(veh))):
            if veh[i].mIsPlayer:
                return i
        return -1

    def _tele_for(self, vehicle_id: int):
        """Telemetrie zu einer Scoring-mID holen. Der Index unterscheidet
        sich zwischen beiden Feldern, deshalb die Zuordnungstabelle."""
        now = time.time()
        if now - self._tele_index_stamp > 2.0:
            self._tele_index.clear()
            tele = self.data.telemetry
            total = min(int(tele.activeVehicles or 0), len(tele.telemInfo))
            for idx in range(total):
                self._tele_index[tele.telemInfo[idx].mID] = idx
            self._tele_index_stamp = now
        idx = self._tele_index.get(vehicle_id)
        return self.data.telemetry.telemInfo[idx] if idx is not None else None

    # ----------------------------------------------------------------
    def read(self) -> dict:
        """Ein Abtastwert des eigenen Fahrzeugs."""
        d = self.data
        si = d.scoring.scoringInfo
        s_idx = self._scoring_player_index()
        if s_idx < 0:
            return {"t": time.time(), "lap_number": None}
        scor = d.scoring.vehScoringInfo[s_idx]
        tele = self._tele_for(scor.mID)
        if tele is None:
            return {"t": time.time(), "lap_number": None}

        wheels = tele.mWheels
        return {
            "t": time.time(),
            "lap_number": tele.mLapNumber,
            "lap_start_et": _nz(tele.mLapStartET),
            "et": _nz(si.mCurrentET),
            "session_remaining_s": _nz(si.mSessionTimeRemaining),
            "time_of_day": _nz(si.mTimeOfDay),
            "speed_kmh": _speed_kmh(tele.mLocalVel),
            "fuel_l": _nz(tele.mFuel),
            "fuel_capacity_l": _nz(tele.mFuelCapacity),
            "virtual_energy": _nz(tele.mVirtualEnergy),
            "throttle": tele.mUnfilteredThrottle,
            "brake": tele.mUnfilteredBrake,
            "in_pits": bool(scor.mInPits),
            "pit_state": scor.mPitState,
            "position": _nz(scor.mPlace),
            "last_lap_time": _nz(scor.mLastLapTime),
            "sector1": _nz(scor.mLastSector1),
            "sector2": _nz(scor.mLastSector2),          # kumuliert!
            "gap_to_leader": scor.mTimeBehindLeader,
            "under_yellow": bool(scor.mUnderYellow),
            "lap_invalidated": bool(tele.mLapInvalidated),
            "game_phase": si.mGamePhase,
            # Faehrst du wirklich, oder laeuft eine Wiederholung / schaust du zu?
            # mInRealtime ist in der Wiederholung false. Wichtig, weil Wiederholungen
            # KEINE Physikdaten mitschreiben - Sprit, Verschleiss und Bremstemperatur
            # bleiben dann leer, waehrend Rundenzeiten und Positionen weiterlaufen.
            "in_realtime": bool(si.mInRealtime),
            "ignition": tele.mIgnitionStarter,
            "session_type": si.mSession,
            "track_name": _decode(si.mTrackName),
            "track_length_m": _nz(si.mLapDist),
            "track_temp": _celsius(si.mTrackTemp),
            "ambient_temp": _celsius(si.mAmbientTemp),
            "raining": si.mRaining,
            "wetness": si.mAvgPathWetness,
            "car_name": _decode(scor.mVehicleName),
            "car_class": _decode(scor.mVehicleClass),
            "wear": [w.mWear for w in wheels],
            "tyre_temp": [_tyre_temp(w) for w in wheels],
            "tyre_press": [_nz(w.mPressure) for w in wheels],
            "brake_temp": self._brake_temps(wheels),
            "brake_pressure": [w.mBrakePressure for w in wheels],
        }

    def _brake_temps(self, wheels) -> list:
        """Bremstemperaturen in Celsius.

        Zwei Fallstricke, beide hier gefunden statt im Rennen:
        - Solange kein einziger Messwert vorliegt (Wiederholung, Auto steht),
          darf NICHT umgerechnet werden. Sonst wird aus 0 ein -273,15.
        - Die Verschachtelung von zwei Bedingungen in einem Ausdruck hatte
          die falsche Reihenfolge. Deshalb steht hier eine ehrliche Schleife.
        """
        raw = [w.mBrakeTemp for w in wheels]
        for v in raw:
            if v:
                self._brake_min = min(self._brake_min, float(v))
        if self._brake_min == float("inf"):
            return [None] * len(raw)          # noch kein Wert gesehen
        kelvin = self._brake_min > 200.0
        ergebnis = []
        for v in raw:
            if not v:
                ergebnis.append(None)
            elif kelvin:
                ergebnis.append(round(float(v) - KELVIN_OFFSET, 2))
            else:
                ergebnis.append(round(float(v), 2))
        return ergebnis

    # ----------------------------------------------------------------
    def read_field(self) -> dict:
        """Alle Fahrzeuge, Wetter und Streckendaten."""
        d = self.data
        si = d.scoring.scoringInfo
        total = min(int(si.mNumVehicles or 0), len(d.scoring.vehScoringInfo))

        vehicles = []
        for i in range(total):
            v = d.scoring.vehScoringInfo[i]
            tele = self._tele_for(v.mID)
            name = _decode(v.mVehicleName)
            driver = _decode(v.mDriverName)
            vehicles.append({
                "id": v.mID,
                # Weltposition fuer die Streckenkarte (Schirm 4); None-sicher,
                # falls ein Build mPos nicht liefert -> Karte nutzt dann lap_dist.
                "x": getattr(getattr(v, "mPos", None), "x", None),
                "z": getattr(getattr(v, "mPos", None), "z", None),
                "driver": driver,
                "car": name,
                "car_class": _decode(v.mVehicleClass),
                "number": _car_number(name, driver),
                "place": _nz(v.mPlace),
                "laps": v.mTotalLaps,
                "lap_dist": v.mLapDist,
                "behind_next": v.mTimeBehindNext,
                "behind_leader": v.mTimeBehindLeader,
                "laps_behind_next": v.mLapsBehindNext,
                "laps_behind_leader": v.mLapsBehindLeader,
                "best_lap": _nz(v.mBestLapTime),
                "last_lap": _nz(v.mLastLapTime),
                "in_pits": bool(v.mInPits),
                "pit_state": v.mPitState,
                "num_pitstops": v.mNumPitstops,
                "is_player": bool(v.mIsPlayer),
                "sector": v.mSector,
                "finish_status": v.mFinishStatus,
                "under_yellow": bool(v.mUnderYellow),
                "fuel_pct": _nz(v.mFuelFraction),
                # Direkte Abstaende auf der Strecke, vom Spiel gerechnet -
                # besser als alles, was wir aus mLapDist ableiten koennten
                "gap_ahead": _nz(tele.mTimeGapCarAhead) if tele else None,
                "gap_behind": _nz(tele.mTimeGapCarBehind) if tele else None,
            })

        wind = getattr(si, "mWind", None)
        return {
            "race_time_s": _nz(si.mCurrentET),
            "session_remaining_s": _nz(si.mSessionTimeRemaining),
            "time_of_day": _nz(si.mTimeOfDay),
            "track_length_m": _nz(si.mLapDist),
            "leader_laps": max([v["laps"] or 0 for v in vehicles], default=0),
            "yellow_flag": bool(si.mYellowFlagState not in (b"\x00", 0, None)),
            "vehicles": vehicles,
            "weather": {
                "track_temp_c": _celsius(si.mTrackTemp),
                "ambient_temp_c": _celsius(si.mAmbientTemp),
                "rain_pct": (si.mRaining or 0) * 100.0,
                "wetness_avg_pct": (si.mAvgPathWetness or 0) * 100.0,
                "wetness_min_pct": (si.mMinPathWetness or 0) * 100.0,
                "wetness_max_pct": (si.mMaxPathWetness or 0) * 100.0,
                "dark_cloud": (si.mDarkCloud or 0) * 100.0,
                "cloud_pct": (si.mDarkCloud or 0) * 100.0,
                "wind_kmh": _speed_kmh(wind) if wind is not None else None,
                "grip_level": getattr(si, "mTrackGripLevel", None),
            },
        }


# ====================================================================
# Simulator
# ====================================================================
_DEMO_FIELD = [
    ("HYPERCAR", 7,  "Toyota GR010",    "Conway / Kobayashi",     208.0),
    ("HYPERCAR", 8,  "Toyota GR010",    "Buemi / Hartley",        208.4),
    ("HYPERCAR", 50, "Ferrari 499P",    "Fuoco / Molina",         208.2),
    ("HYPERCAR", 6,  "Porsche 963",     "Estre / Vanthoor",       208.9),
    ("HYPERCAR", 2,  "Cadillac V-LMDh", "Bamber / Lynn",          209.3),
    ("LMP2",     22, "Oreca 07",        "Jarvis / Hanson",        215.6),
    ("LMP2",     23, "Oreca 07",        "Aubry / Dillmann",       216.1),
    ("LMP2",     34, "Oreca 07",        "Smiechowski / Yoluc",    217.0),
    ("LMP2",     41, "Oreca 07",        "Andrade / Kubica",       215.9),
    ("LMGT3",    76, "Corvette Z06",    "Marcelinjo",             224.0),
    ("LMGT3",    91, "Porsche 911",     "Lietz / Christensen",    223.6),
    ("LMGT3",    46, "BMW M4",          "Rossi / Martin",         224.3),
    ("LMGT3",    54, "Ferrari 296",     "Flohr / Castellacci",    224.8),
    ("LMGT3",    77, "Aston Martin",    "Sorensen / Thiim",       225.1),
    ("LMGT3",    88, "McLaren 720S",    "Barnicoat / Grunewald",  224.5),
]
TRACK_LENGTH = 13626.0


class SimulatorSource:
    """Erzeugt ein 24h-Rennen im Zeitraffer. Fuer Tests ohne Sim."""

    def __init__(self, lap_time: float = 224.0, speedup: float = 30.0,
                 fuel_capacity: float = 100.0, fuel_per_lap: float = 3.3):
        self.lap_time = lap_time
        self.speedup = speedup
        self.fuel_capacity = fuel_capacity
        self.fuel_per_lap = fuel_per_lap
        self.t0 = time.time()
        self.fuel = fuel_capacity
        self.wear = [1.0, 1.0, 1.0, 1.0]
        self.lap = 1
        self._last_read = self.t0

    def available(self) -> bool:
        return True

    def read(self) -> dict:
        now = time.time()
        dt = (now - self._last_read) * self.speedup
        self._last_read = now
        et = (now - self.t0) * self.speedup
        lap = int(et // self.lap_time) + 1

        if lap != self.lap:
            self.lap = lap
            if lap % 30 == 0:
                self.fuel = self.fuel_capacity
                self.wear = [1.0, 1.0, 1.0, 1.0]

        self.fuel = max(0.5, self.fuel - self.fuel_per_lap * dt / self.lap_time)
        for i in range(4):
            self.wear[i] = max(0.05, self.wear[i] - (0.0022 if i < 2 else 0.0018) * dt / self.lap_time)

        jitter = random.uniform(-0.4, 0.9)
        return {
            "t": now, "lap_number": lap, "lap_start_et": (lap - 1) * self.lap_time,
            "et": et, "session_remaining_s": max(0.0, 86400 - et), "time_of_day": (et % 86400),
            "speed_kmh": 180 + 60 * math.sin(et / 7.0),
            "fuel_l": self.fuel, "fuel_capacity_l": self.fuel_capacity,
            "virtual_energy": 100.0 * self.fuel / self.fuel_capacity,
            "throttle": max(0.0, math.sin(et / 3.0)), "brake": max(0.0, -math.sin(et / 3.0)),
            "in_pits": False, "pit_state": 0, "position": 12,
            "last_lap_time": self.lap_time + jitter,
            "sector1": self.lap_time * 0.29 + jitter / 3,
            "sector2": self.lap_time * 0.69 + 2 * jitter / 3,
            "gap_to_leader": 41.2 + lap * 0.3,
            "under_yellow": False, "lap_invalidated": False,
            "game_phase": 5, "session_type": 10,
            "track_name": "Circuit de la Sarthe", "track_length_m": TRACK_LENGTH,
            "track_temp": 31.5 - 6 * math.sin(et / 43200), "ambient_temp": 22.0 - 5 * math.sin(et / 43200),
            "raining": 0.0, "wetness": 0.0,
            "car_name": "Corvette Z06 LMGT3", "car_class": "LMGT3",
            "wear": list(self.wear),
            "tyre_temp": [88 + random.uniform(-4, 6) for _ in range(4)],
            "tyre_press": [172 + random.uniform(-2, 2) for _ in range(4)],
            "brake_temp": [430 + 180 * max(0.0, -math.sin(et / 3.0)) for _ in range(4)],
            "brake_pressure": [max(0.0, -math.sin(et / 3.0))] * 4,
        }

    def read_field(self) -> dict:
        et = (time.time() - self.t0) * self.speedup
        vehicles = []
        for idx, (cls, num, car, driver, pace) in enumerate(_DEMO_FIELD):
            wobble = math.sin((et / 900.0) + idx) * 22.0
            total_time = max(0.0, et - idx * 4.0 - wobble)
            laps = int(total_time / pace)
            in_pits = ((int(et / pace) + idx) % 34) == 0
            vehicles.append({
                "id": 100 + idx, "driver": driver, "car": f"#{num} {car}",
                "car_class": cls, "number": str(num), "place": 0, "laps": laps,
                "lap_dist": (total_time % pace) / pace * TRACK_LENGTH,
                "behind_next": None, "behind_leader": None,
                "laps_behind_next": 0, "laps_behind_leader": 0,
                "best_lap": pace - 1.6, "last_lap": pace + math.sin(et / 60 + idx) * 0.7,
                "in_pits": in_pits, "pit_state": 3 if in_pits else 0,
                "num_pitstops": laps // 34, "is_player": num == 76,
                "sector": 1, "finish_status": 0, "under_yellow": False,
                "fuel_pct": 70, "gap_ahead": None, "gap_behind": None,
            })
        vehicles.sort(key=lambda v: (-(v["laps"] or 0), -(v["lap_dist"] or 0)))
        leader = vehicles[0] if vehicles else None
        for i, v in enumerate(vehicles):
            v["place"] = i + 1
            if leader:
                v["laps_behind_leader"] = max(0, leader["laps"] - v["laps"])
                v["behind_leader"] = i * 3.4 + abs(math.sin(et / 120 + i)) * 6.0
            v["behind_next"] = 0.0 if i == 0 else v["behind_leader"] - vehicles[i - 1]["behind_leader"]

        night = math.sin(et / 43200.0 * math.pi)
        return {
            "race_time_s": et, "session_remaining_s": max(0.0, 86400 - et),
            "time_of_day": et % 86400, "track_length_m": TRACK_LENGTH,
            "leader_laps": leader["laps"] if leader else 0, "yellow_flag": False,
            "vehicles": vehicles,
            "weather": {
                "track_temp_c": 24.0 + 10.0 * night, "ambient_temp_c": 17.0 + 7.0 * night,
                "rain_pct": max(0.0, math.sin(et / 20000.0 - 1.2)) * 78.0,
                "wetness_avg_pct": max(0.0, math.sin(et / 20000.0 - 1.5)) * 62.0,
                "wetness_min_pct": max(0.0, math.sin(et / 20000.0 - 1.6)) * 40.0,
                "wetness_max_pct": max(0.0, math.sin(et / 20000.0 - 1.4)) * 85.0,
                "dark_cloud": 30.0 + 40.0 * max(0.0, math.sin(et / 18000.0)),
                "cloud_pct": 30.0 + 40.0 * max(0.0, math.sin(et / 18000.0)),
                "wind_kmh": 9.0 + 6.0 * math.sin(et / 5000.0), "grip_level": None,
            },
        }
