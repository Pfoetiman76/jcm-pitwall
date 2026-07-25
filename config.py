"""Konfiguration des Pitwall-Clients.

Der Key liegt NIE im Code. Er wird aus pitwall_config.json neben dem
Skript gelesen (steht in .gitignore) oder aus Umgebungsvariablen.
Gleiche Konvention wie im LMU Consistency Coach.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, "frozen", False)
BASE = Path(sys.executable).resolve().parent if IS_FROZEN else HERE


def _user_dir() -> Path:
    """Schreibbarer Ordner im Benutzerprofil."""
    appdata = (os.environ.get("APPDATA")
               or os.environ.get("XDG_CONFIG_HOME")
               or str(Path.home()))
    ordner = Path(appdata) / "JCM Pitwall"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def _resolve_config_path() -> Path:
    """Dieselbe Reihenfolge wie in gui.py -- sonst schreibt das Fenster die
    Zugangsdaten woanders hin, als der Client sie sucht.

    Als EXE ist __file__ das Auspackverzeichnis (_MEIPASS). Eine dort
    abgelegte Konfiguration liest kein zweiter Prozess und ueberlebt bei
    --onefile nicht einmal das Programmende.
    """
    daneben = BASE / "pitwall_config.json"          # portabel, vom Stick
    if daneben.exists():
        return daneben
    lokal = HERE / "pitwall_config.json"            # Entwicklung im Repo
    if lokal.exists() and not IS_FROZEN:
        return lokal
    return _user_dir() / "pitwall_config.json"


def data_dir() -> Path:
    """Wohin Spool, Logdatei und Session-Merker gehoeren.

    Neben die Konfiguration. Der Spool ist der Puffer fuer fehlgeschlagene
    Uploads -- landet er im Auspackverzeichnis, ist er nach dem naechsten
    Neustart des Clients weg, und genau dann braucht man ihn.
    """
    return _resolve_config_path().parent


CONFIG_PATH = _resolve_config_path()

DEFAULTS = {
    "supabase_url": "",          # z.B. https://xxxx.supabase.co
    "supabase_key": "",          # service_role secret - schreibt, bleibt lokal
    "anon_key": "",              # anon public - nur fuers Pruefskript
    "driver_name": "Marcelinjo",
    "sim": "LMU",                # LMU | RF2
    "poll_hz": 20,               # Abtastrate der Shared Memory (lokal, nicht Upload)
    "brake_t_opt_c": 500.0,      # Schwelle fuer thermische Last, wie im Bremsmodell
    "spool_file": "pitwall_spool.jsonl",
    "log_file": "pitwall_client.log",
}


@dataclass
class Config:
    supabase_url: str = ""
    supabase_key: str = ""
    anon_key: str = ""
    driver_name: str = "Driver"
    sim: str = "LMU"
    poll_hz: int = 20
    brake_t_opt_c: float = 500.0
    spool_file: str = "pitwall_spool.jsonl"
    log_file: str = "pitwall_client.log"

    @property
    def rest_url(self) -> str:
        return self.supabase_url.rstrip("/") + "/rest/v1"

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)


def load() -> Config:
    data = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception as exc:  # kaputte Datei soll den Renneinsatz nicht killen
            print(f"[config] {CONFIG_PATH.name} nicht lesbar ({exc}) - nutze Defaults")
    # Umgebungsvariablen gewinnen (praktisch fuer die anderen 5 Fahrer)
    for key in ("supabase_url", "supabase_key", "driver_name"):
        env = os.environ.get("PITWALL_" + key.upper())
        if env:
            data[key] = env
    known = {f: data[f] for f in Config.__dataclass_fields__ if f in data}
    return Config(**known)


def write_template() -> Path:
    CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2), encoding="utf-8")
    return CONFIG_PATH


if __name__ == "__main__":
    print("Vorlage geschrieben:", write_template())
