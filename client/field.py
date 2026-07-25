"""Feld-Tracker.

Erkennt fuer JEDES Fahrzeug im Feld die abgeschlossenen Runden, rechnet
Klassenpositionen und Klassenabstaende und misst nebenbei den echten
Boxenverlust der Strecke.

Warum das im Client passiert und nicht im Backend: der Scoring-Buffer ist
nur lokal verfuegbar, und die Rundenerkennung braucht die hohe Abtastrate.
Hochgeladen wird verdichtet - ein Upsert fuer den Live-Stand, ein Insert
pro tatsaechlich gefahrener Gegnerrunde.
"""

from __future__ import annotations

from typing import Optional


class FieldTracker:
    def __init__(self):
        self.last_laps: dict[int, int] = {}
        self.last_lap_start: dict[int, float] = {}
        self.pit_entry_lap: dict[int, int] = {}
        self.pit_loss_samples: list[float] = []
        self.class_order: list[str] = []

    # ----------------------------------------------------------------
    def annotate(self, field: dict) -> dict:
        """Klassenpositionen und Klassenabstaende ergaenzen."""
        vehicles = field.get("vehicles") or []
        by_class: dict[str, list] = {}
        for v in vehicles:
            by_class.setdefault(v.get("car_class") or "?", []).append(v)

        for cls, group in by_class.items():
            group.sort(key=lambda v: (v.get("place") or 999))
            leader = group[0] if group else None
            for i, v in enumerate(group):
                v["class_position"] = i + 1
                v["class_size"] = len(group)
                if leader is not None and v.get("behind_leader") is not None \
                        and leader.get("behind_leader") is not None:
                    v["class_behind_leader"] = round(
                        float(v["behind_leader"]) - float(leader["behind_leader"]), 3)
                else:
                    v["class_behind_leader"] = None
                if i == 0:
                    v["class_behind_next"] = 0.0
                else:
                    prev = group[i-1]
                    if v.get("behind_leader") is not None and prev.get("behind_leader") is not None:
                        v["class_behind_next"] = round(
                            float(v["behind_leader"]) - float(prev["behind_leader"]), 3)
                    else:
                        v["class_behind_next"] = None
                v["class_laps_behind_leader"] = max(
                    0, (leader.get("laps") or 0) - (v.get("laps") or 0)) if leader else 0

        self.class_order = sorted(by_class.keys())
        field["classes"] = self.class_order
        field["pit_loss_s"] = self.pit_loss()
        return field

    # ----------------------------------------------------------------
    def new_laps(self, field: dict) -> list[dict]:
        """Fahrzeuge, die seit dem letzten Aufruf Start/Ziel ueberfahren haben."""
        out = []
        et = field.get("race_time_s") or 0.0
        for v in field.get("vehicles") or []:
            vid = v.get("id")
            laps = v.get("laps") or 0
            prev = self.last_laps.get(vid)
            self.last_laps[vid] = laps

            if v.get("in_pits"):
                self.pit_entry_lap.setdefault(vid, laps)
            elif vid in self.pit_entry_lap and laps > self.pit_entry_lap[vid] + 1:
                self.pit_entry_lap.pop(vid, None)

            if prev is None or laps <= prev:
                self.last_lap_start[vid] = et
                continue

            lap_time = v.get("last_lap")
            if lap_time is not None and lap_time <= 0:
                lap_time = None
            out.append({
                "vehicle_id": vid,
                "driver_name": v.get("driver"),
                "car_number": v.get("number"),
                "car_class": v.get("car_class"),
                "lap_num": laps,
                "lap_time": round(float(lap_time), 3) if lap_time else None,
                "position": v.get("place"),
                "class_position": v.get("class_position"),
                "gap_to_leader": v.get("class_behind_leader"),
                "in_pits": bool(v.get("in_pits")),
                "race_time_s": round(float(et), 3),
            })
            self.last_lap_start[vid] = et
        return out

    # ----------------------------------------------------------------
    def observe_pit_loss(self, lap_time: float, reference: float, kind: str):
        """Boxenverlust aus einer In- oder Out-Lap schaetzen.

        In-Lap und Out-Lap sind zusammen um den Boxenverlust laenger als zwei
        normale Runden. Beide Haelften einzeln zu messen ist ungenau, aber
        ueber mehrere Stopps mittelt sich das raus - und es ist immer noch
        besser als ein geratener Festwert.
        """
        if not lap_time or not reference or lap_time <= reference:
            return
        delta = lap_time - reference
        if 3.0 < delta < 120.0:
            self.pit_loss_samples.append(delta)
            if len(self.pit_loss_samples) > 12:
                self.pit_loss_samples.pop(0)

    def pit_loss(self) -> Optional[float]:
        if not self.pit_loss_samples:
            return None
        # Median, damit ein Dreher in der Boxengasse die Zahl nicht kippt
        s = sorted(self.pit_loss_samples)
        mid = len(s) // 2
        val = s[mid] if len(s) % 2 else (s[mid-1] + s[mid]) / 2
        return round(val, 2)
