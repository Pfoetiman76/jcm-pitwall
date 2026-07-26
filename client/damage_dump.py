"""Schadens-Dump auf FAHRZEUG-Ebene (nicht Rad-Ebene).

Sucht die Stelle, an der LMU Front- vs Heckschaden unterscheidet:
  - Shared Memory: mDentSeverity[8] (8 Zonen ums Auto) + Aufprall-Felder
  - REST: wearables.body komplett inkl. detachableParts (mit Index)

So starten (im client-Ordner, LMU laeuft, im Auto):

    python damage_dump.py

Am aussagekraeftigsten: einmal MIT Frontschaden und einmal MIT Heckschaden
fahren/abrufen - dann sieht man, welche Zone bzw. welcher detachableParts-Index
reagiert. Ausgabe an Marcel schicken.
"""

from __future__ import annotations

import ctypes
import time

from source import SharedMemorySource, TelemetrieNichtGefunden

try:
    from lmu_rest import WEARABLES, _hole
except Exception:
    WEARABLES, _hole = None, None

# mDentSeverity: 8 Zonen im Uhrzeigersinn ab vorne. Mapping ist die uebliche
# rF2-Konvention - beim Testen mit gezieltem Front-/Heckschaden verifizieren.
DENT_ZONEN = ["VORNE", "VORNE-LINKS", "LINKS", "HINTEN-LINKS",
              "HINTEN", "HINTEN-RECHTS", "RECHTS", "VORNE-RECHTS"]


def fmt(val):
    if isinstance(val, bytes):
        return val.split(b"\x00", 1)[0].decode("latin-1", "replace")
    if isinstance(val, ctypes.Array):
        return [fmt(v) for v in val]
    if isinstance(val, ctypes.Structure):
        return {n: fmt(getattr(val, n)) for n, *_ in getattr(type(val), "_fields_", [])}
    if isinstance(val, float):
        return round(val, 4)
    return val


def dump_tele(tele):
    print("\n=== FAHRZEUG-TELEMETRIE: alle Felder ===")
    fields = getattr(type(tele), "_fields_", [])
    namen = []
    for feld in fields:
        name = feld[0]
        namen.append(name)
        if name == "mWheels":                       # Raeder haben wir schon
            print(f"  {name:<30} = <4 Raeder, siehe wheel_dump.py>")
            continue
        try:
            print(f"  {name:<30} = {fmt(getattr(tele, name))}")
        except Exception as exc:
            print(f"  {name:<30} = <Fehler: {exc}>")
    return namen


def deute_dents(tele, namen):
    if "mDentSeverity" not in namen:
        print("\n  Kein mDentSeverity in der Struktur - LMU/pyLMUSharedMemory gibt die")
        print("  Zonen-Schadensinfo hier nicht her.")
        return
    sev = list(getattr(tele, "mDentSeverity"))
    print("\n=== mDentSeverity je Zone (0=keiner .. 2=schwer) ===")
    for z, v in zip(DENT_ZONEN, sev):
        print(f"  {z:<14} {v}")
    front = max(sev[7], sev[0], sev[1])
    heck = max(sev[3], sev[4], sev[5])
    print(f"\n  -> FRONT (Zonen VL/V/VR): {front}    HECK (Zonen HL/H/HR): {heck}")
    print("  Das trennt Front- von Heckschaden - als Stufe, nicht als %.")


def dump_rest_body():
    if _hole is None or WEARABLES is None:
        return
    daten = _hole(WEARABLES)
    body = ((daten or {}).get("wearables") or {}).get("body")
    if not isinstance(body, dict):
        print("\n=== REST wearables.body ===\n  (nicht erreichbar)")
        return
    print("\n=== REST wearables.body (roh) ===")
    for k, v in body.items():
        if k == "detachableParts" and isinstance(v, list):
            print("  detachableParts (Index: Wert):")
            for i, x in enumerate(v):
                print(f"    [{i:>2}] {x}")
        else:
            print(f"  {k} = {v}")
    print("  -> body.aero ist EIN Aero-Skalar. Falls ein detachableParts-Index bei")
    print("     Front- vs Heckschaden unterschiedlich kippt, waere das die Trennung.")


def main():
    print("[dump] verbinde mit Le Mans Ultimate ...")
    try:
        src = SharedMemorySource(sim="LMU")
    except TelemetrieNichtGefunden as exc:
        print("[dump]", exc)
        return 2

    print("[dump] warte auf dein Auto in der Telemetrie ...")
    tele = None
    for _ in range(120):
        try:
            d = src.data
            s_idx = src._scoring_player_index()
            if s_idx >= 0:
                scor = d.scoring.vehScoringInfo[s_idx]
                tele = src._tele_for(scor.mID)
                if tele is not None:
                    break
        except Exception as exc:
            print("[dump] noch nicht bereit:", exc)
        time.sleep(0.5)

    if tele is None:
        print("[dump] Kein eigenes Auto in der Telemetrie gefunden.")
        return 1

    namen = dump_tele(tele)
    deute_dents(tele, namen)
    dump_rest_body()
    print("\n[dump] fertig - Ausgabe bitte an Marcel schicken.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
