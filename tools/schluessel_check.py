"""Schluessel-Sperre.

Laeuft automatisch vor jedem Hochladen zu GitHub und bricht ab, wenn eine
Datei dabei waere, die einen Zugangsschluessel enthaelt.

Geprueft wird zweifach:
  1. Auf den exakten service_role-Schluessel aus deiner eigenen Konfiguration.
  2. Generisch auf jedes Supabase-Token mit der Rolle service_role - falls
     jemand einen fremden Schluessel in einer Datei liegen hat.

    python tools/schluessel_check.py
    -> Rueckgabewert 0 wenn sauber, 1 wenn etwas gefunden wurde
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "client" / "pitwall_config.json"

JWT_RE = re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}")
BINAER = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".exe", ".pdf", ".7z"}


def rolle(token: bytes) -> str | None:
    """Rolle aus dem Mittelteil eines Supabase-Tokens lesen."""
    try:
        payload = token.split(b".")[1]
        payload += b"=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload)).get("role")
    except Exception:
        return None


def dateien() -> list[Path]:
    """Alles, was Git hochladen wuerde - inklusive noch nicht verfolgter."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        namen = [n for n in out.stdout.splitlines() if n.strip()]
    except Exception:
        namen = []
    if not namen:   # noch kein Repo: alles ausser dem, was ohnehin ignoriert wird
        namen = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*")
                 if p.is_file() and ".git" not in p.parts]
    return [ROOT / n for n in namen]


def main() -> int:
    eigener = ""
    if CONFIG.exists():
        try:
            eigener = (json.loads(CONFIG.read_text(encoding="utf-8"))
                       .get("supabase_key") or "").strip()
        except Exception:
            pass

    treffer: list[tuple[str, str]] = []
    for pfad in dateien():
        if not pfad.is_file() or pfad.suffix.lower() in BINAER:
            if pfad.suffix.lower() == ".zip" and pfad.exists():
                treffer.append((str(pfad.relative_to(ROOT)),
                                "ZIP-Archiv - Inhalt nicht pruefbar"))
            continue
        try:
            roh = pfad.read_bytes()
        except Exception:
            continue
        if eigener and len(eigener) > 20 and eigener.encode() in roh:
            treffer.append((str(pfad.relative_to(ROOT)), "dein service_role-Schluessel"))
            continue
        for token in JWT_RE.findall(roh):
            if rolle(token) == "service_role":
                treffer.append((str(pfad.relative_to(ROOT)), "ein service_role-Token"))
                break

    if not treffer:
        print("[Schluessel-Sperre] sauber - kein Zugangsschluessel im Upload")
        return 0

    print("\n" + "=" * 62)
    print("  ABBRUCH - hier steckt ein Zugangsschluessel drin")
    print("=" * 62)
    for datei, grund in treffer:
        print(f"  {datei}\n      -> {grund}")
    print("""
  Es wurde NICHTS hochgeladen.

  Der service_role-Schluessel darf alles in deiner Datenbank. Auf GitHub
  waere er oeffentlich - Loeschen hilft dann nicht mehr, die History
  bleibt.

  So raeumst du auf:
    - Fahrerpaket/ und JCM-Pitwall-Fahrerpaket.zip aus dem Projektordner
      herausschieben, zum Beispiel auf den Desktop.
    - Danach deploy_dashboard.bat nochmal starten.

  Das Fahrerpaket verteilst du direkt an die fuenf, nicht ueber GitHub.
""")
    return 1


if __name__ == "__main__":
    sys.exit(main())
