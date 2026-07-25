"""Supabase-REST-Uploader.

Nur stdlib (urllib), kein SDK - gleiche Linie wie beim Gemini-Zugriff im
Consistency Coach.

Wichtig fuer 24h: faellt das WLAN aus, wandert das Payload in eine
Spool-Datei und wird beim naechsten erfolgreichen Call nachgeschoben.
Ein Verbindungsabriss darf keine Runde kosten.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


class SupabaseClient:
    def __init__(self, rest_url: str, api_key: str, spool_path: Path, timeout: float = 8.0):
        self.rest_url = rest_url.rstrip("/")
        self.api_key = api_key
        self.spool_path = Path(spool_path)
        self.timeout = timeout
        self.online = True

    # -- Low level ---------------------------------------------------
    def _request(self, method: str, path: str, body: Any = None, prefer: str = "return=representation"):
        url = f"{self.rest_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("apikey", self.api_key)
        req.add_header("Authorization", f"Bearer {self.api_key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", prefer)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8") or "[]"
        return json.loads(raw) if raw.strip() else []

    def get(self, path: str):
        return self._request("GET", path, prefer="count=none")

    def insert(self, table: str, row: dict):
        return self._request("POST", table, row)

    def patch(self, table: str, filt: str, row: dict):
        return self._request("PATCH", f"{table}?{filt}", row)

    def upsert(self, table: str, row: dict, on_conflict: str):
        return self._request(
            "POST", f"{table}?on_conflict={on_conflict}", row,
            prefer="resolution=merge-duplicates,return=representation",
        )

    # -- Spool -------------------------------------------------------
    def _spool(self, kind: str, payload: dict):
        with self.spool_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, "payload": payload, "t": time.time()}) + "\n")

    def flush_spool(self, handler) -> int:
        if not self.spool_path.exists():
            return 0
        lines = self.spool_path.read_text(encoding="utf-8").splitlines()
        remaining, sent = [], 0
        for line in lines:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                handler(item["kind"], item["payload"], spooled=True)
                sent += 1
            except Exception:
                remaining.append(line)
        if remaining:
            self.spool_path.write_text("\n".join(remaining) + "\n", encoding="utf-8")
        else:
            self.spool_path.unlink(missing_ok=True)
        return sent

    def spool_count(self) -> int:
        if not self.spool_path.exists():
            return 0
        return sum(1 for line in self.spool_path.read_text(encoding="utf-8").splitlines() if line.strip())

    # -- High level --------------------------------------------------
    def safe_insert(self, table: str, row: dict, spool_kind: Optional[str] = None):
        """Insert mit Netz. Gibt die angelegte Zeile zurueck oder None."""
        try:
            out = self.insert(table, row)
            self.online = True
            return out[0] if isinstance(out, list) and out else out
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            self.online = False
            if spool_kind:
                self._spool(spool_kind, row)
            print(f"[upload] {table} fehlgeschlagen ({exc}) -> gespoolt")
            return None

    def safe_upsert(self, table: str, rows, on_conflict: str, spool_kind: Optional[str] = None):
        """Upsert mit merge-duplicates. Wichtig: ein HTTP-Fehler (doppelte Zeile,
        fehlende Spalte/Constraint) kippt den Online-Status NICHT - der Server ist
        ja erreichbar. Sonst meldete ein einzelner opponent_laps-Fehler dem
        Fahrer-Fenster faelschlich 'Kein Netz'. Nur echte Netzfehler = offline.
        Bei HTTP-Fehlern wird Code + Antworttext geloggt (400 = Constraint fehlt,
        dann sql/09 einspielen; 409 sollte mit merge-duplicates nicht mehr kommen).
        """
        try:
            out = self.upsert(table, rows, on_conflict)
            self.online = True
            return out[0] if isinstance(out, list) and out else out
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8")[:200]
            except Exception:
                pass
            print(f"[upload] {table} abgelehnt (HTTP {exc.code}) {detail}")
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.online = False
            if spool_kind:
                self._spool(spool_kind, rows)
            print(f"[upload] {table} kein Netz ({exc}) -> gespoolt")
            return None
