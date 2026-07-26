"""LMU REST-Schnittstelle.

Le Mans Ultimate stellt neben der Shared Memory noch eine lokale
HTTP-Schnittstelle auf Port 6397 bereit. Dort stehen drei Dinge, die in der
Shared Memory NICHT vorkommen:

  /rest/garage/UIScreen/RepairAndRefuel  ->  echter Bremsbelagverschleiss
                                             je Rad, dazu Aero- und
                                             Fahrwerksschaden
  /rest/sessions/weather                 ->  Wettervorhersage in fuenf
                                             Stuetzpunkten ueber die Session
  /rest/strategy/usage                   ->  Verlauf der virtuellen Energie

Das ersetzt unser Bremsmodell durch einen echten Wert. Das Modell bleibt als
Rueckfall, falls die Schnittstelle nicht antwortet.

Die Formate sind gegen zwei unabhaengige Projekte geprueft: LMU Pitwall
(Swizzjack) und TinyPedal. Beide lesen dieselben Schluessel.

Nur Standardbibliothek.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Optional

BASIS = "http://localhost:6397/rest"
WEARABLES = f"{BASIS}/garage/UIScreen/RepairAndRefuel"
WETTER = f"{BASIS}/sessions/weather"
ENERGIE = f"{BASIS}/strategy/usage"
PITSTOP = f"{BASIS}/strategy/pitstop-estimate"
TRACKMAP = f"{BASIS}/watch/trackmap"

# WNV_SKY, 0 bis 10. Benennung aus LMU Pitwall uebernommen.
HIMMEL = {
    0: "klar", 1: "leicht bewölkt", 2: "teils bewölkt", 3: "stark bewölkt",
    4: "bedeckt", 5: "Nieselregen", 6: "leichter Regen", 7: "bedeckt mit Regen",
    8: "Regen", 9: "starker Regen", 10: "Sturm",
}
KNOTEN = ("START", "NODE_25", "NODE_50", "NODE_75", "FINISH")


def _hole(url: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            roh = resp.read().decode("utf-8", errors="replace")
        return json.loads(roh) if roh.strip() else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
            OSError, ValueError):
        return None


def _downsample(pts: list, n: int) -> list:
    """Punktzahl gleichmaessig auf hoechstens n reduzieren (Endpunkte bleiben)."""
    if n <= 2 or len(pts) <= n:
        return pts
    schritt = (len(pts) - 1) / (n - 1)
    return [pts[round(i * schritt)] for i in range(n)]


def _rad_feld(wert) -> list[Optional[float]]:
    """Vier Radwerte aus einer Liste holen. -1 heisst 'nicht geliefert'."""
    if not isinstance(wert, list) or len(wert) < 4:
        return [None] * 4
    aus = []
    for v in wert[:4]:
        try:
            f = float(v)
        except (TypeError, ValueError):
            aus.append(None)
            continue
        aus.append(None if f < 0 else f)
    return aus


class LmuRest:
    """Fragt die Schnittstelle in ruhigem Takt ab und merkt sich die Antworten.

    Wichtig fuer 24h: die Endpunkte werden NICHT bei jedem Abtastwert
    aufgerufen. Verschleiss aendert sich langsam, die Vorhersage steht fuer
    die ganze Session. Antwortet die Schnittstelle nicht, wird der Takt
    gestreckt, damit ein abgeschaltetes LMU den Client nicht ausbremst.
    """

    def __init__(self, wear_interval: float = 20.0, forecast_interval: float = 600.0):
        self.wear_interval = wear_interval
        self.forecast_interval = forecast_interval
        self.wearables: dict = {}
        self.pit_estimate: dict = {}
        self.forecast: list[dict] = []
        self.verfuegbar: Optional[bool] = None      # None = noch nicht versucht
        self._next_wear = 0.0
        self._next_forecast = 0.0
        self._fehler = 0

    # ----------------------------------------------------------------
    def _strafe(self) -> float:
        """Nach Fehlschlaegen seltener fragen, hoechstens alle zwei Minuten."""
        return min(120.0, self.wear_interval * (2 ** min(self._fehler, 3)))

    def tick(self, session_typ: Optional[int] = None) -> dict:
        """Regelmaessig aufrufen. Gibt den aktuellen Stand zurueck."""
        jetzt = time.time()

        if jetzt >= self._next_wear:
            daten = _hole(WEARABLES)
            if daten is None:
                self._fehler += 1
                self.verfuegbar = False if self.verfuegbar is None else self.verfuegbar
                self._next_wear = jetzt + self._strafe()
            else:
                self._fehler = 0
                self.verfuegbar = True
                self.wearables = self._lies_wearables(daten)
                self._next_wear = jetzt + self.wear_interval
                # Live-Boxenstoppdauer im selben Takt (aendert sich nur mit dem
                # Pit-Menue). Fehlt der Endpunkt, bleibt der letzte Stand stehen.
                pit = _hole(PITSTOP)
                if pit is not None:
                    self.pit_estimate = self._lies_pit_estimate(pit)

        if jetzt >= self._next_forecast:
            daten = _hole(WETTER)
            if daten is not None:
                self.forecast = self._lies_forecast(daten, session_typ)
                self.verfuegbar = True
            self._next_forecast = jetzt + self.forecast_interval

        return {"wearables": self.wearables, "forecast": self.forecast,
                "verfuegbar": bool(self.verfuegbar)}

    # ----------------------------------------------------------------
    @staticmethod
    def _lies_wearables(daten: dict) -> dict:
        w = (daten or {}).get("wearables") or {}
        aero = None
        koerper = w.get("body")
        if isinstance(koerper, dict):
            try:
                aero = float(koerper.get("aero"))
                aero = None if aero < 0 else aero
            except (TypeError, ValueError):
                aero = None
        bremsen = _rad_feld(w.get("brakes"))
        fahrwerk = _rad_feld(w.get("suspension"))
        return {
            # 0.0 = neu, 1.0 = hinueber. Wir drehen auf Restprofil in Prozent,
            # damit es zur Reifenanzeige passt (100 % = neu).
            "brake_wear": bremsen,
            "brake_left_pct": [None if b is None else round((1.0 - b) * 100, 2) for b in bremsen],
            "suspension": fahrwerk,
            "aero_damage": aero,
            "hat_werte": any(b is not None for b in bremsen),
        }

    @staticmethod
    def _lies_pit_estimate(daten: dict) -> dict:
        """Live geplante Boxenstoppdauer je Bestandteil (Sekunden). total ist die
        Summe aus dem aktuell im Pit-Menue Angewaehlten."""
        if not isinstance(daten, dict):
            return {}

        def z(feld):
            try:
                return round(float(daten.get(feld)), 2)
            except (TypeError, ValueError):
                return None

        return {
            "total": z("total"),
            "fuel": z("fuel"),
            "tires": z("tires"),
            "damage": z("damage"),
            "driver": z("driverSwap"),
        }

    @staticmethod
    def _lies_forecast(daten: dict, session_typ: Optional[int]) -> list[dict]:
        if not isinstance(daten, dict):
            return []
        if session_typ is None:
            schluessel = "RACE"
        elif session_typ <= 4:
            schluessel = "PRACTICE"
        elif session_typ <= 8:
            schluessel = "QUALIFY"
        else:
            schluessel = "RACE"
        block = daten.get(schluessel)
        if not isinstance(block, dict):
            # Manche Builds liefern nur einen Abschnitt - dann den ersten nehmen
            for wert in daten.values():
                if isinstance(wert, dict) and any(k in wert for k in KNOTEN):
                    block = wert
                    break
        if not isinstance(block, dict):
            return []

        aus = []
        for i, name in enumerate(KNOTEN):
            knoten = block.get(name)
            if not isinstance(knoten, dict):
                continue

            def zahl(feld):
                try:
                    return float(knoten[feld]["currentValue"])
                except (KeyError, TypeError, ValueError):
                    return None

            himmel = zahl("WNV_SKY")
            regen = zahl("WNV_RAIN_CHANCE")
            aus.append({
                "anteil": round(i * 0.25, 2),          # 0, 25, 50, 75, 100 % der Session
                "sky_type": None if himmel is None else int(himmel),
                "sky_text": HIMMEL.get(int(himmel), "unbekannt") if himmel is not None else None,
                "temperatur_c": zahl("WNV_TEMPERATURE"),
                # LMU liefert die Regenwahrscheinlichkeit in Prozent
                "regen_pct": None if regen is None else round(min(max(regen, 0.0), 100.0), 1),
                "luftfeuchte": zahl("WNV_HUMIDITY"),
                "wind_kmh": zahl("WNV_WINDSPEED"),
                "wind_richtung": zahl("WNV_WINDDIRECTION"),
            })
        return aus

    def trackmap(self, max_line: int = 220, max_pit: int = 90) -> Optional[dict]:
        """Streckenkontur aus /rest/watch/trackmap (aktuelle Session, Welt-x/z).
        type 0 = Ideallinie (geschlossene Schleife), type 1 = Boxengasse. Marker
        (type >=2) werden verworfen. Einmal pro Session aufrufen - die Kontur ist
        statisch. Gibt {'line': [[x,z],..], 'pit': [[x,z],..]} oder None zurueck."""
        daten = _hole(TRACKMAP, timeout=5.0)
        if not isinstance(daten, list) or not daten:
            return None
        line, pit = [], []
        for p in daten:
            if not isinstance(p, dict):
                continue
            try:
                x = round(float(p["x"]), 1)
                z = round(float(p["z"]), 1)
            except (KeyError, TypeError, ValueError):
                continue
            t = p.get("type")
            if t == 0:
                line.append([x, z])
            elif t == 1:
                pit.append([x, z])
        if len(line) < 10:
            return None
        return {"line": _downsample(line, max_line), "pit": _downsample(pit, max_pit)}

    # ----------------------------------------------------------------
    def energie_verlauf(self, fahrername: str) -> Optional[list[float]]:
        """Verlauf der virtuellen Energie je Runde, falls vorhanden."""
        daten = _hole(ENERGIE)
        if not isinstance(daten, (dict, list)):
            return None
        eintraege = daten if isinstance(daten, list) else daten.get("drivers") or []
        for e in eintraege:
            if not isinstance(e, dict):
                continue
            if str(e.get("driverName") or e.get("name") or "").strip() == fahrername.strip():
                verlauf = e.get("virtualEnergy") or e.get("history") or []
                werte = []
                for v in verlauf:
                    try:
                        werte.append(float(v))
                    except (TypeError, ValueError):
                        pass
                return werte or None
        return None