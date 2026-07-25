"""Kanal-Check.

Sagt dir in 30 Sekunden, welche Werte Le Mans Ultimate bei DIR gerade
wirklich liefert - und welche leer bleiben.

    python tools/kanal_check.py            # 30 Sekunden messen
    python tools/kanal_check.py --sekunden 60

Das beantwortet die Frage, die man sonst nur durch Ausprobieren im Rennen
klaert: reicht eine Wiederholung? Kommen Reifenwerte bei meiner Klasse?
Ist mLapDist bei Gegnern befuellt?

Nichts wird hochgeladen.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

from source import SharedMemorySource, TelemetrieNichtGefunden  # noqa: E402

# (Anzeigename, Schluessel, Liste?, wofuer es gebraucht wird)
KANAELE = [
    ("Rundennummer",        "lap_number",     False, "Rundenerkennung - ohne das geht gar nichts"),
    ("Letzte Rundenzeit",   "last_lap_time",  False, "Rundenprotokoll, Zeitentabelle"),
    ("Sektor 1",            "sector1",        False, "Sektorzeiten"),
    ("Sektor 2 (kumuliert)", "sector2",       False, "Sektorzeiten"),
    ("Position",            "position",       False, "Kacheln, Zeitentabelle"),
    ("Abstand Fuehrender",  "gap_to_leader",  False, "Zeitentabelle"),
    ("Streckenlaenge",      "track_length_m", False, "Boxenstopp-Verkehrsrechnung"),
    ("Restzeit Session",    "session_remaining_s", False, "Stint-Ring"),
    ("Sprit",               "fuel_l",         False, "SPRIT-KALKULATION"),
    ("Tankgroesse",         "fuel_capacity_l", False, "Sprit in Prozent"),
    ("Virtuelle Energie",   "virtual_energy", False, "Hypercar / LMDh"),
    ("Reifenverschleiss",   "wear",           True,  "REIFEN-PROJEKTION"),
    ("Reifentemperatur",    "tyre_temp",      True,  "Reifenkacheln"),
    ("Reifendruck",         "tyre_press",     True,  "Reifenkacheln"),
    ("Bremstemperatur",     "brake_temp",     True,  "BREMSEN, Fading-Warnung"),
    ("Bremsdruck",          "brake_pressure", True,  "Reibarbeit"),
    ("Streckentemperatur",  "track_temp",     False, "Wetterschirm"),
    ("Lufttemperatur",      "ambient_temp",   False, "Wetterschirm"),
    ("Naesse",              "wetness",        False, "Reifenempfehlung"),
    ("Geschwindigkeit",     "speed_kmh",      False, "Reibarbeit, Spitzenwerte"),
]


def hat_wert(v) -> bool:
    if v is None:
        return False
    if isinstance(v, (list, tuple)):
        return any(x not in (None, 0, 0.0) for x in v)
    return v not in (0, 0.0, "", False)


def beispiel(v) -> str:
    if isinstance(v, (list, tuple)):
        teile = []
        for x in v[:4]:
            teile.append("--" if x is None else (f"{x:.2f}" if isinstance(x, float) else str(x)))
        return "[" + ", ".join(teile) + "]"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="Welche Telemetriewerte liefert LMU?")
    ap.add_argument("--sekunden", type=float, default=30.0)
    ap.add_argument("--sim", choices=["lmu", "rf2"], default="lmu")
    args = ap.parse_args()

    print("=" * 68)
    print("  Kanal-Check - was liefert das Spiel gerade?")
    print("=" * 68)
    try:
        quelle = SharedMemorySource(sim=args.sim.upper())
    except TelemetrieNichtGefunden as exc:
        print("\n" + str(exc))
        return 2

    gesehen: dict[str, object] = {}
    fahrzeuge = 0
    lap_dist_gegner = False
    realtime = None
    runden = set()

    ende = time.time() + args.sekunden
    print(f"\nMesse {args.sekunden:.0f} Sekunden. Fahr in der Zeit bitte normal weiter ...\n")
    while time.time() < ende:
        try:
            s = quelle.read()
        except Exception as exc:
            print(f"  Lesefehler: {exc}")
            time.sleep(0.5)
            continue
        for _, key, _, _ in KANAELE:
            v = s.get(key)
            if hat_wert(v) and key not in gesehen:
                gesehen[key] = v
        if s.get("lap_number"):
            runden.add(s["lap_number"])
        if realtime is None and s.get("in_realtime") is not None:
            realtime = s.get("in_realtime")
        try:
            f = quelle.read_field()
            fahrzeuge = max(fahrzeuge, len(f.get("vehicles") or []))
            if any(v.get("lap_dist") for v in (f.get("vehicles") or []) if not v.get("is_player")):
                lap_dist_gegner = True
        except Exception:
            pass
        time.sleep(0.1)

    fehlt_wichtig = []
    print(f"{'Kanal':<24}{'Status':<12}{'Beispielwert':<26}Wofuer")
    print("-" * 92)
    for name, key, _, zweck in KANAELE:
        da = key in gesehen
        if not da and zweck.isupper():
            fehlt_wichtig.append(name)
        print(f"{name:<24}{'da' if da else 'LEER':<12}"
              f"{(beispiel(gesehen[key]) if da else '-'):<26}{zweck}")

    print("\n" + "=" * 68)
    print(f"  Fahrzeuge im Feld gesehen: {fahrzeuge}")
    print(f"  Streckenposition der Gegner (fuer die Boxenrechnung): "
          f"{'da' if lap_dist_gegner else 'LEER'}")
    print(f"  Runden im Messzeitraum: {len(runden)}")
    if realtime is False:
        print("\n  ACHTUNG: Das Spiel meldet 'nicht im Auto' - also Wiederholung,")
        print("  Zuschauermodus oder Box. Wiederholungen enthalten KEINE Physikdaten:")
        print("  Sprit, Verschleiss und Bremstemperaturen bleiben deshalb leer.")
        print("  Fuer einen vollstaendigen Test bitte selbst ein paar Runden fahren.")
    elif fehlt_wichtig:
        print("\n  Diese wichtigen Kanaele blieben leer: " + ", ".join(fehlt_wichtig))
        print("  Bitte diese Ausgabe an Marcel schicken.")
    else:
        print("\n  Alle wichtigen Kanaele liefern Werte. Der Client kann loslegen.")
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
