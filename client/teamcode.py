"""Team-Code.

Ein Team-Code ist die komplette Konfiguration in einer Zeile zum Kopieren.
Marcel erzeugt ihn einmal im Einrichter, die anderen fuegen ihn beim ersten
Start ein. Danach nie wieder.

Warum nicht die Zugangsdaten in den Installer bauen: dann muesste bei jedem
Schluesselwechsel ein neuer Installer gebaut und verteilt werden, und die
Datei duerfte nie oeffentlich liegen. So bleibt der Installer fuer alle
gleich und darf sogar auf GitHub liegen.

Der Code ist NICHT verschluesselt, nur kodiert - er ist so vertraulich wie
der Schluessel darin. Direkt verschicken, nicht in offene Kanaele.
"""

from __future__ import annotations

import base64
import json
import zlib

PREFIX = "JCM1-"


def encode(supabase_url: str, supabase_key: str, drivers: list[str] | None = None) -> str:
    payload = {"u": supabase_url.strip().rstrip("/"), "k": supabase_key.strip()}
    if drivers:
        payload["d"] = list(drivers)
    roh = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return PREFIX + base64.urlsafe_b64encode(zlib.compress(roh, 9)).decode("ascii")


def decode(code: str) -> dict:
    """Gibt ein Konfigurations-Dict zurueck oder wirft ValueError."""
    code = "".join((code or "").split())          # Zeilenumbrueche aus dem Chat raus
    if not code:
        raise ValueError("Der Team-Code ist leer.")
    if not code.startswith(PREFIX):
        raise ValueError("Das sieht nicht nach einem Team-Code aus - "
                         f"er muss mit {PREFIX} anfangen.")
    body = code[len(PREFIX):]
    try:
        payload = json.loads(zlib.decompress(base64.urlsafe_b64decode(body)).decode("utf-8"))
    except Exception as exc:
        raise ValueError("Der Team-Code ist unvollstaendig oder beschaedigt. "
                         "Bitte nochmal komplett kopieren.") from exc
    if not payload.get("u") or not payload.get("k"):
        raise ValueError("Im Team-Code fehlen Adresse oder Schluessel.")
    cfg = {
        "supabase_url": payload["u"],
        "supabase_key": payload["k"],
        "driver_name": "",
        "sim": "LMU",
        "poll_hz": 20,
        "brake_t_opt_c": 500.0,
        "spool_file": "pitwall_spool.jsonl",
        "log_file": "pitwall_client.log",
    }
    if payload.get("d"):
        cfg["driver_list"] = payload["d"]
    return cfg


if __name__ == "__main__":
    probe = encode("https://beispiel.supabase.co", "eyJtest." + "x" * 40,
                   ["Hoefels", "MiCa", "Walter"])
    print("Beispiel-Code:", probe)
    print("Laenge:", len(probe), "Zeichen")
    print("Zurueckgelesen:", decode(probe))
