"""Trackmap-Sonde — prueft, ob LMU eine fertige Streckenkarte liefert, die wir
statt der aus x/z zusammengesetzten Form aufs Dashboard legen koennen.

So starten (im client-Ordner, LMU laeuft, im Auto/in der Session):

    python trackmap_probe.py

Fragt die Trackmap-Endpunkte ab, sichert die ROHDATEN als Datei (egal ob SVG,
JSON oder PNG) und meldet Content-Type + Groesse + eine Vorschau. Die
erzeugten trackmap_*-Dateien UND die Konsolenausgabe an Marcel schicken.

Wichtig ist v.a.: Format (SVG/Pfad/JSON/PNG) und ob Koordinaten zu den
Fahrzeug-x/z passen (Welt-Koordinaten) oder normalisiert sind.

Nur GET, nur Standardbibliothek.
"""

from __future__ import annotations

import json
import urllib.request

BASIS = "http://localhost:6397"


def roh(pfad: str):
    """Gibt (status, content_type, bytes) zurueck oder (None, fehler, b'')."""
    url = BASIS + pfad
    try:
        req = urllib.request.Request(url, headers={"Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            ct = resp.headers.get("Content-Type", "?")
            data = resp.read()
        return resp.status if hasattr(resp, "status") else 200, ct, data
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}", b""


def endung(ct: str, data: bytes) -> str:
    if "svg" in ct or data[:5] == b"<?xml" or data[:4] == b"<svg":
        return "svg"
    if "json" in ct or data[:1] in (b"{", b"["):
        return "json"
    if data[:8].startswith(b"\x89PNG"):
        return "png"
    if "html" in ct:
        return "html"
    return "bin"


def zeige(name: str, pfad: str):
    status, ct, data = roh(pfad)
    print("=" * 72)
    print(pfad)
    print("=" * 72)
    if status is None:
        print("  Fehler:", ct)
        print()
        return None, None
    ext = endung(ct, data)
    datei = f"trackmap_{name}.{ext}"
    with open(datei, "wb") as fh:
        fh.write(data)
    print(f"  Status {status} · Content-Type: {ct} · {len(data)} Bytes -> {datei}")
    # Vorschau nur bei Text
    if ext in ("svg", "json", "html"):
        txt = data.decode("utf-8", "replace")
        print("  --- Vorschau (erste 1200 Zeichen) ---")
        print(txt[:1200])
    else:
        print("  (Binaerdatei - komplett in", datei, "gesichert)")
    print()
    return ext, data


def track_ids(data: bytes):
    """Aus /rest/race/track moegliche Track-ids ziehen."""
    ids = []
    try:
        j = json.loads(data.decode("utf-8", "replace"))
    except Exception:
        return ids
    kandidaten = j if isinstance(j, list) else [j]
    if isinstance(j, dict):
        for v in j.values():
            if isinstance(v, list):
                kandidaten = v
                break
    for e in kandidaten:
        if isinstance(e, dict):
            for k in ("id", "trackId", "ID", "track_id"):
                if e.get(k) is not None:
                    ids.append(e[k])
                    break
    return ids


def main():
    print("[trackmap] frage Endpunkte ab ...\n")

    # 1) Der beste Kandidat: aktuelle Session, ohne id.
    zeige("watch", "/rest/watch/trackmap")

    # 2) Tracks auflisten, um an eine id fuer den race-Endpunkt zu kommen.
    _, tdata = zeige("racetrack", "/rest/race/track")
    ids = track_ids(tdata) if tdata else []
    if ids:
        print(f"[trackmap] gefundene Track-ids: {ids[:5]}")
        zeige("byid", f"/rest/race/track/{ids[0]}/trackmap")
    else:
        print("[trackmap] keine Track-id gefunden - /rest/race/track/{id}/trackmap "
              "muesste mit der aktuellen Streckennummer aufgerufen werden.")

    print("\n[trackmap] fertig - die trackmap_*-Dateien UND diese Ausgabe an Marcel.")
    print("[trackmap] Entscheidend: Format (SVG/JSON/PNG) und ob die Koordinaten")
    print("[trackmap] zu den Fahrzeug-x/z passen (Welt) oder normalisiert sind.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
