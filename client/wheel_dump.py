"""Shared-Memory Wheel-Dump — zeigt ALLE Felder eines Rades der eigenen
Telemetrie. Damit sehen wir, ob LMU einen Flatspot-/Lockup-Wert liefert oder
nur das binaere mFlat (Reifen platt).

So starten (im client-Ordner, LMU laeuft und du sitzt im Auto):

    python wheel_dump.py

Es wartet, bis dein Auto in der Telemetrie steht, gibt dann einmal ALLE
Radfelder von VORNE LINKS aus (Feldname + Wert) plus eine kompakte Tabelle
der interessanten Felder je Rad und beendet sich. Nur Standardbibliothek +
deine vorhandene source.py / pyLMUSharedMemory.
"""

from __future__ import annotations

import ctypes
import time

from source import SharedMemorySource, TelemetrieNichtGefunden

# Felder, die fuer Reifenschaden/Flatspot interessant sind. Gibt es keinen
# abgestuften Flatspot, bleibt nur mFlat (0/1) und mWear (Restprofil).
INTERESSANT = ["mWear", "mFlat", "mDetached", "mPressure", "mBrakeTemp",
               "mGripFract", "mTemperature", "mFlatSpot", "mFlatspot",
               "mTireLoad", "mTireWear"]

RAEDER = ["VORNE LINKS", "VORNE RECHTS", "HINTEN LINKS", "HINTEN RECHTS"]


def fmt(val):
    """ctypes-Wert lesbar machen (Arrays -> Liste, bytes -> str)."""
    if isinstance(val, bytes):
        return val.split(b"\x00", 1)[0].decode("latin-1", "replace")
    if isinstance(val, ctypes.Array):
        return [fmt(v) for v in val]
    if isinstance(val, ctypes.Structure):
        return "<struct>"
    if isinstance(val, float):
        return round(val, 4)
    return val


def dump_all_fields(wheel):
    print("\n=== ALLE FELDER: VORNE LINKS (mWheels[0]) ===")
    fields = getattr(type(wheel), "_fields_", [])
    if not fields:
        print("  (kein _fields_ - unerwartete Struktur:", type(wheel), ")")
        return [n for n, *_ in fields]
    namen = []
    for feld in fields:
        name = feld[0]
        namen.append(name)
        try:
            print(f"  {name:<32} = {fmt(getattr(wheel, name))}")
        except Exception as exc:
            print(f"  {name:<32} = <Fehler: {exc}>")
    return namen


def dump_interessant(wheels, vorhandene):
    da = [f for f in INTERESSANT if f in vorhandene]
    if not da:
        return
    print("\n=== JE RAD (interessante Felder) ===")
    kopf = "  " + "RAD".ljust(16) + "".join(f.ljust(18) for f in da)
    print(kopf)
    for i, w in enumerate(list(wheels)[:4]):
        zeile = "  " + RAEDER[i].ljust(16)
        for f in da:
            zeile += str(fmt(getattr(w, f, "-"))).ljust(18)
        print(zeile)


def main():
    print("[dump] verbinde mit Le Mans Ultimate ...")
    try:
        src = SharedMemorySource(sim="LMU")
    except TelemetrieNichtGefunden as exc:
        print("[dump]", exc)
        return 2

    print("[dump] warte auf dein Auto in der Telemetrie (ins Auto setzen) ...")
    wheels = None
    for _ in range(120):                       # bis ~60 s warten
        try:
            d = src.data
            s_idx = src._scoring_player_index()
            if s_idx >= 0:
                scor = d.scoring.vehScoringInfo[s_idx]
                tele = src._tele_for(scor.mID)
                if tele is not None:
                    wheels = tele.mWheels
                    break
        except Exception as exc:
            print("[dump] noch nicht bereit:", exc)
        time.sleep(0.5)

    if wheels is None:
        print("[dump] Kein eigenes Auto in der Telemetrie gefunden. LMU offen? Im Auto?")
        return 1

    vorhandene = dump_all_fields(wheels[0])
    dump_interessant(wheels, vorhandene)

    # Klartext-Auswertung fuer die Flatspot-Frage
    print("\n=== AUSWERTUNG ===")
    hat_flat = any("flat" in n.lower() for n in vorhandene)
    grad = [n for n in vorhandene if "flat" in n.lower() and n.lower() not in ("mflat",)]
    if grad:
        print("  Moeglicher abgestufter Flatspot-Wert gefunden:", grad,
              "-> koennen wir als %-Anzeige verdrahten.")
    elif "mFlat" in vorhandene:
        print("  Nur binaeres 'mFlat' (0=ok, 1=platt) vorhanden - KEIN abgestufter")
        print("  Flatspot. Anzeige waere nur 'platt / nicht platt'.")
    elif not hat_flat:
        print("  Kein Flatspot-Feld in der Radstruktur. LMU liefert es nicht.")
    print("\n[dump] fertig - diese Ausgabe bitte an Marcel schicken.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
