"""LMU REST-Sonde — dumpt die noch ungenutzten Endpunkte, um bessere Daten
zu finden (v.a. Front-/Heckfluegel als %, Flatspot, Live-Boxenstopp).

So starten (im client-Ordner, LMU laeuft, im Auto - am besten MIT etwas
Front- ODER Heckschaden, damit man sieht wie die Zustandsfelder reagieren):

    python rest_probe.py

Dumpt jeden Endpunkt als JSON (grosse Antworten gekuerzt) in die Konsole und
zusaetzlich in rest_probe_out.json. Ausgabe an Marcel schicken.

Nur GET (read-only, aendert nichts im Spiel). Nur Standardbibliothek.
"""

from __future__ import annotations

import json
import urllib.request

BASIS = "http://localhost:6397"

# Vielversprechende, ungenutzte GET-Endpunkte aus dem Swagger.
ENDPUNKTE = [
    "/rest/garage/getVehicleCondition",     # <- Hauptverdaechtiger: Zustand je Bauteil?
    "/rest/garage/tireinfo",                # Reifen: Flatspot / Detailverschleiss?
    "/rest/garage/brakeinfo",               # Bremsen: Detail?
    "/rest/garage/summary",                 # Garagen-Uebersicht
    "/rest/garage/UIScreen/TireManagement", # Reifenverwaltung
    "/rest/strategy/overall",               # Gesamtstrategie
    "/rest/strategy/pitstop-estimate",      # Live-Boxenstoppdauer
    "/rest/garage/UIScreen/RepairAndRefuel",# bereits genutzt - zum Vergleich
]

MAX_ZEICHEN = 6000      # sehr grosse Antworten kuerzen (z.B. standings)


def hole(pfad: str):
    url = BASIS + pfad
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            roh = resp.read().decode("utf-8", "replace")
        try:
            return json.loads(roh)
        except ValueError:
            return {"_nicht_json": roh[:MAX_ZEICHEN]}
    except Exception as exc:
        return {"_fehler": f"{type(exc).__name__}: {exc}"}


def kuerzen(text: str) -> str:
    if len(text) > MAX_ZEICHEN:
        return text[:MAX_ZEICHEN] + f"\n... [gekuerzt, {len(text)} Zeichen gesamt]"
    return text


def main():
    print("[probe] frage LMU-Endpunkte ab ...\n")
    alles = {}
    for pfad in ENDPUNKTE:
        daten = hole(pfad)
        alles[pfad] = daten
        js = json.dumps(daten, indent=2, ensure_ascii=False)
        print("=" * 70)
        print(pfad)
        print("=" * 70)
        print(kuerzen(js))
        print()

    with open("rest_probe_out.json", "w", encoding="utf-8") as fh:
        json.dump(alles, fh, indent=2, ensure_ascii=False)
    print("[probe] fertig - Konsole + rest_probe_out.json an Marcel schicken.")
    print("[probe] Tipp: einmal MIT Frontschaden und einmal MIT Heckschaden laufen")
    print("[probe] lassen, dann sieht man welches Feld front/heck unterscheidet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
