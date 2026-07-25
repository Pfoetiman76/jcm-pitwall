"""Setup-Pruefung.

Sagt dir in 10 Sekunden, ob die Datenbank richtig steht - bevor du es
mitten im Rennen merkst.

    python tools/check_setup.py

Liest die Zugangsdaten aus client/pitwall_config.json. Fragt zusaetzlich
nach dem anon-Key, um zu pruefen, dass der wirklich nur lesen darf.

Nur Standardbibliothek.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "client" / "pitwall_config.json"

TABLES = ["drivers", "sessions", "laps", "stint_telemetry", "stints",
          "events", "field_state", "opponent_laps", "weather_log"]
VIEWS = ["v_laps_full", "v_fuel_strategy", "v_driver_summary",
         "v_field_pace", "v_weather_trend"]

OK, FAIL, WARN = "  OK  ", " FEHL ", " WARN "
_results: list[tuple[str, str, str]] = []


def report(state: str, name: str, detail: str = ""):
    _results.append((state, name, detail))
    print(f"[{state}] {name}" + (f"  -> {detail}" if detail else ""))


def call(url: str, key: str, path: str, method: str = "GET", body=None, prefer=None):
    req = urllib.request.Request(url.rstrip("/") + "/rest/v1/" + path.lstrip("/"),
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)
    with urllib.request.urlopen(req, timeout=12) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, (json.loads(raw) if raw.strip() else [])


def main() -> int:
    print("=" * 62)
    print("  JCM Pitwall - Setup-Pruefung")
    print("=" * 62)

    if not CONFIG.exists():
        report(FAIL, "Konfiguration", f"{CONFIG} fehlt. Erst 'python config.py' im Ordner client ausfuehren.")
        return 1
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    url, key = cfg.get("supabase_url", "").strip(), cfg.get("supabase_key", "").strip()

    if not url.startswith("https://") or ".supabase.co" not in url:
        report(FAIL, "Supabase-URL", f"sieht nicht nach einer Projekt-URL aus: {url!r}")
        return 1
    report(OK, "Supabase-URL", url)

    if not key:
        report(FAIL, "Schluessel", "supabase_key ist leer")
        return 1

    # --- 1. Erreichbarkeit ------------------------------------------
    try:
        call(url, key, "sessions?select=id&limit=1")
        report(OK, "Verbindung zur Datenbank")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")[:180]
        report(FAIL, "Verbindung", f"HTTP {exc.code} - {body}")
        if exc.code == 401:
            print("\n  -> Der Schluessel passt nicht zum Projekt. Project Settings -> API,")
            print("     'service_role secret' kopieren (NICHT den anon-Key).")
        return 1
    except Exception as exc:
        report(FAIL, "Verbindung", str(exc))
        print("\n  -> Kein Netz, falsche URL oder Projekt pausiert (Supabase pausiert")
        print("     kostenlose Projekte nach 7 Tagen ohne Zugriff).")
        return 1

    # --- 2. Schema ---------------------------------------------------
    missing = []
    for t in TABLES + VIEWS:
        try:
            call(url, key, f"{t}?select=*&limit=1")
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 400):
                missing.append(t)
            else:
                missing.append(f"{t} (HTTP {exc.code})")
    if missing:
        report(FAIL, "Schema", "fehlt: " + ", ".join(missing))
        print("\n  -> sql/00_setup_all.sql im SQL-Editor ausfuehren.")
        return 1
    report(OK, "Schema", f"{len(TABLES)} Tabellen, {len(VIEWS)} Views vorhanden")

    # --- 3. Fahrer ---------------------------------------------------
    try:
        _, drivers = call(url, key, "drivers?select=driver_name,color&order=driver_name")
        if len(drivers) < 2:
            report(WARN, "Fahrer", f"nur {len(drivers)} angelegt - fuer das Team sollten es 6 sein")
        else:
            report(OK, "Fahrer", ", ".join(d["driver_name"] for d in drivers))
    except Exception as exc:
        report(WARN, "Fahrer", str(exc))

    # --- 4. Schreibtest ----------------------------------------------
    test_id = None
    try:
        _, rows = call(url, key, "sessions", "POST", {
            "sim": "LMU", "track_name": "SETUP-TEST", "session_type": "PRACTICE",
            "planned_hours": 0, "is_active": False,
        }, prefer="return=representation")
        test_id = rows[0]["id"] if rows else None
        report(OK, "Schreibrecht", "Testsession angelegt")
    except urllib.error.HTTPError as exc:
        report(FAIL, "Schreibrecht", f"HTTP {exc.code}")
        print("\n  -> In client/pitwall_config.json steht vermutlich der anon-Key.")
        print("     Der darf seit dem neuen Setup nur lesen. Trag den service_role-Key ein.")
        return 1

    # --- 5. Kette laps -> stint_telemetry ----------------------------
    if test_id:
        try:
            _, lap = call(url, key, "laps", "POST", {
                "session_id": test_id, "lap_num": 1, "lap_time": 95.123, "is_valid": True,
            }, prefer="return=representation")
            lap_id = lap[0]["id"]
            call(url, key, "stint_telemetry", "POST", {
                "lap_id": lap_id, "session_id": test_id,
                "fuel_used_l": 3.2, "fuel_remaining_l": 80.0, "wear_fl": 0.98,
            }, prefer="return=representation")
            _, joined = call(url, key, f"v_laps_full?session_id=eq.{test_id}&select=lap_num,fuel_used_l")
            if joined and joined[0].get("fuel_used_l") is not None:
                report(OK, "Datenkette", "laps -> stint_telemetry -> View v_laps_full")
            else:
                report(FAIL, "Datenkette", "View liefert keine Telemetrie")
        except Exception as exc:
            report(FAIL, "Datenkette", str(exc))

        try:
            call(url, key, "field_state?on_conflict=session_id", "POST",
                 {"session_id": test_id, "vehicles": [{"id": 1, "driver": "Test"}], "weather": {}},
                 prefer="resolution=merge-duplicates,return=representation")
            call(url, key, "field_state?on_conflict=session_id", "POST",
                 {"session_id": test_id, "vehicles": [{"id": 1, "driver": "Test2"}], "weather": {}},
                 prefer="resolution=merge-duplicates,return=representation")
            report(OK, "Feldstand", "Upsert ueberschreibt statt anzuhaengen")
        except Exception as exc:
            report(FAIL, "Feldstand", str(exc))

    # --- 6. anon-Key: darf lesen, darf nicht schreiben ---------------
    anon = (cfg.get("anon_key") or "").strip()
    if not anon:
        try:
            anon = input("\nAnon-Key fuers Dashboard (Enter zum Ueberspringen): ").strip()
        except EOFError:
            anon = ""
    if anon:
        try:
            call(url, anon, "sessions?select=id&limit=1")
            report(OK, "Dashboard-Key liest")
        except Exception as exc:
            report(FAIL, "Dashboard-Key liest", str(exc))
        try:
            call(url, anon, "sessions", "POST",
                 {"track_name": "SOLLTE-NICHT-GEHEN", "is_active": False},
                 prefer="return=representation")
            report(FAIL, "Dashboard-Key schreibt", "der anon-Key darf schreiben - 00_setup_all.sql nochmal ausfuehren")
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403, 404):
                report(OK, "Dashboard-Key schreibt nicht", f"abgelehnt mit HTTP {exc.code}")
            else:
                report(WARN, "Dashboard-Key schreibt", f"unerwartet HTTP {exc.code}")
    else:
        report(WARN, "Dashboard-Key", "nicht geprueft")

    # --- 7. Aufraeumen -----------------------------------------------
    if test_id:
        try:
            call(url, key, f"sessions?id=eq.{test_id}", "DELETE")
            report(OK, "Aufraeumen", "Testsession geloescht")
        except Exception:
            report(WARN, "Aufraeumen", f"Testsession {test_id} bitte von Hand loeschen")

    fails = sum(1 for s, _, _ in _results if s == FAIL)
    warns = sum(1 for s, _, _ in _results if s == WARN)
    print("\n" + "=" * 62)
    if fails:
        print(f"  {fails} Punkt(e) fehlgeschlagen - siehe oben.")
        return 1
    print(f"  Alles bereit." + (f"  ({warns} Hinweis(e))" if warns else ""))
    print("  Naechster Schritt:  cd client  &&  python run_client.py --demo")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    sys.exit(main())
