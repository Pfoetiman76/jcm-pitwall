"""Fahrerpaket bauen.

Erzeugt einen fertigen Ordner samt ZIP, den die anderen fuenf Fahrer nur
noch entpacken und anklicken muessen. Zugangsdaten und Fahrerliste sind
schon drin - niemand ausser dir bearbeitet je eine Konfigurationsdatei.

    python tools/paket_fuer_fahrer.py

Voraussetzung: client/pitwall_config.json ist bei dir ausgefuellt und
'python tools/check_setup.py' laeuft gruen durch.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "client"
CONFIG = CLIENT / "pitwall_config.json"
OUT = ROOT / "Fahrerpaket"
ZIP = ROOT / "JCM-Pitwall-Fahrerpaket.zip"

# Was ins Paket gehoert. Alles andere bleibt bei dir.
DATEIEN = [
    "pitwall.py", "gui.py", "run_client.py", "source.py",
    "accumulator.py", "field.py", "uploader.py", "config.py",
    "teamcode.py",
    "START_HIER.bat",
]
# Ordner, die komplett mitmuessen
ORDNER = ["pyLMUSharedMemory"]


def fahrer_aus_db(cfg: dict) -> list[str]:
    url, key = cfg.get("supabase_url", ""), cfg.get("supabase_key", "")
    if not (url and key):
        return []
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/drivers?select=driver_name&order=driver_name")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return [r["driver_name"] for r in json.loads(resp.read().decode())]
    except Exception as exc:
        print(f"  Fahrerliste konnte nicht geladen werden ({exc}) - nutze die aus der Config")
        return []


def main() -> int:
    print("=" * 62)
    print("  Fahrerpaket bauen")
    print("=" * 62)

    if not CONFIG.exists():
        print(f"\n  {CONFIG} fehlt. Erst dein eigenes Setup fertig machen.")
        return 1
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not cfg.get("supabase_url") or not cfg.get("supabase_key"):
        print("\n  In pitwall_config.json fehlen URL oder Schluessel.")
        return 1

    namen = fahrer_aus_db(cfg) or cfg.get("driver_list") or []
    if not namen:
        print("\n  Keine Fahrer gefunden. Lege sie erst in der Datenbank an (Abschnitt 1.3).")
        return 1
    print(f"\n  Fahrer im Paket: {', '.join(namen)}")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    fehlend = [d for d in DATEIEN if not (CLIENT / d).exists()]
    if fehlend:
        print(f"\n  Diese Dateien fehlen im Ordner client: {', '.join(fehlend)}")
        return 1
    for d in DATEIEN:
        shutil.copy2(CLIENT / d, OUT / d)
    for ordner in ORDNER:
        quelle = CLIENT / ordner
        if not quelle.exists():
            print(f"\n  Der Ordner client/{ordner} fehlt - ohne ihn findet der")
            print("  Client die Telemetrie nicht.")
            return 1
        shutil.copytree(quelle, OUT / ordner,
                        ignore=shutil.ignore_patterns("__pycache__", "tests"))

    # Konfiguration fuers Paket: Fahrername leer, damit jeder selbst waehlt
    paket_cfg = dict(cfg)
    paket_cfg["driver_name"] = ""
    paket_cfg["driver_list"] = namen
    paket_cfg.pop("anon_key", None)          # brauchen die Fahrer nicht
    (OUT / "pitwall_config.json").write_text(
        json.dumps(paket_cfg, indent=2, ensure_ascii=False), encoding="utf-8")

    anleitung = ROOT / "ANLEITUNG_FAHRER.md"
    if anleitung.exists():
        shutil.copy2(anleitung, OUT / "ANLEITUNG.txt")

    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for pfad in sorted(OUT.rglob("*")):
            if pfad.is_file():
                z.write(pfad, pfad.relative_to(OUT.parent))

    print(f"\n  Ordner: {OUT}")
    print(f"  ZIP:    {ZIP}  ({ZIP.stat().st_size // 1024} KB)")
    print("\n  " + "-" * 58)
    print("  ACHTUNG: in diesem Paket steckt der service_role-Schluessel.")
    print("  Der darf alles in deiner Datenbank. Verteile das ZIP direkt an")
    print("  die fuenf Fahrer - nicht in einen oeffentlichen Kanal, nicht auf")
    print("  GitHub. Falls er doch mal rausrutscht: in Supabase unter")
    print("  Project Settings -> API den Schluessel neu erzeugen und das")
    print("  Paket einmal neu bauen.")
    print("  " + "-" * 58)
    return 0


if __name__ == "__main__":
    sys.exit(main())
