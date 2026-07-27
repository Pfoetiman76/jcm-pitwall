"""JCM Pitwall — Selbst-Updater über GitHub Releases.

Gleiches Muster wie der LMU Consistency Coach (updater.py): fragt die
GitHub-Releases-API, vergleicht den Tag mit der installierten VERSION und laedt
bei Bedarf das Asset. Ergaenzt um den Anwenden-Schritt: ein Installer (setup.exe)
wird gestartet, eine blanke onefile-EXE tauscht sich selbst per Retry-Move-Batch.
Kein Token noetig (oeffentliches Repo). Nur Standardbibliothek.

EINMALIG SETZEN: GITHUB_REPO auf "benutzer/repo" und VERSION je Release.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# >>> EINMALIG anpassen <<<
# VERSION kommt bei einem CI-Build aus client/_version.py (dort schreibt der
# Workflow die Release-Version rein) - so ist sie IMMER == Release-Tag und der
# aktualisierte Client verlangt nicht endlos dasselbe Update. Der Fallback gilt
# nur fuer lokale Laeufe ohne _version.py.
# vorher: try/except from _version ... VERSION = "1.0.7"
from version import VERSION              # eine Quelle (version.py resolvt _version)
GITHUB_REPO = "Pfoetiman76/jcm-pitwall"      # bestaetigt
PREFER_EXACT = "JCM-Pitwall.exe"             # Fallback-EXE (Fahrer-Client); Einrichter setzt eigene

_API = "https://api.github.com/repos/{repo}/releases/latest"
IS_FROZEN = getattr(sys, "frozen", False)
NEU_NAME = "JCM-Pitwall.new.exe"


def _ver(s: str) -> tuple:
    """'v1.0.3 Beta' -> (1,0,3). Robust gegen Suffixe/Praefixe (wie beim Coach)."""
    nums = re.findall(r"\d+", s or "")
    return tuple(int(n) for n in nums[:4]) if nums else (0,)


def _pick_asset(assets: list, prefer_exact: str | None):
    """Ein Release hat mehrere EXEs (Einrichter, Setup, Client). Reihenfolge:
    1) Setup-Installer (ein Installer fuer alle), 2) exakt die gewuenschte App-EXE,
    3) irgendeine .exe. Verhindert, dass der Client versehentlich den Einrichter zieht."""
    for a in assets:
        if "setup" in (a.get("name") or "").lower():
            return a
    if prefer_exact:
        for a in assets:
            if (a.get("name") or "").lower() == prefer_exact.lower():
                return a
    for a in assets:
        if (a.get("name") or "").lower().endswith(".exe"):
            return a
    return None


def check_for_update(current_version: str = VERSION, repo: str | None = None,
                     timeout: int = 8, prefer_exact: str | None = PREFER_EXACT) -> dict | None:
    """Info-Dict, wenn ein neueres Release existiert, sonst None. Wirft bei
    Netz-/Konfigurationsfehlern (vom Aufrufer zu fangen)."""
    repo = repo or GITHUB_REPO
    if "DEIN-" in repo or "/" not in repo:
        raise ValueError("GITHUB_REPO in updater.py ist noch nicht gesetzt (benutzer/repo).")
    req = urllib.request.Request(
        _API.format(repo=repo),
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "JCM-Pitwall-Updater"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = data.get("tag_name", "") or ""
    if _ver(tag) <= _ver(current_version):
        return None
    a = _pick_asset(data.get("assets", []) or [], prefer_exact)
    asset_name = (a.get("name") or "") if a else ""
    asset_url = (a.get("browser_download_url") or "") if a else ""
    return {
        "version": tag.lstrip("vV"),
        "url": data.get("html_url", "") or f"https://github.com/{repo}/releases/latest",
        "asset_url": asset_url,
        "asset_name": asset_name,
        "is_installer": "setup" in asset_name.lower(),
        "notes": (data.get("body", "") or "").strip(),
    }


def check(current_version: str = VERSION, timeout: int = 8) -> dict | None:
    """Wie check_for_update, schluckt aber alle Fehler -> None. Fuer den stillen
    Autostart-Check, der den Programmstart nie aufhalten darf."""
    try:
        return check_for_update(current_version, timeout=timeout)
    except Exception:
        return None


def download_asset(url: str, dest_path: str, progress_cb=None, timeout: int = 120) -> str:
    """Laedt das Release-Asset nach dest_path. progress_cb(done,total) optional.
    Reine stdlib. Gibt den Zielpfad zurueck; wirft bei Fehlern (wie beim Coach)."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "JCM-Pitwall-Updater",
                      "Accept": "application/octet-stream"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        with open(dest_path, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if progress_cb is not None:
                    try:
                        progress_cb(done, total)
                    except Exception:
                        pass
    return dest_path


def staged_path(is_installer: bool) -> Path:
    """Zielpfad fuer den Download. Blanke EXE muss NEBEN die alte (gleiches
    Laufwerk, sonst schlaegt move fehl); ein Installer darf in %TEMP%."""
    if is_installer:
        return Path(tempfile.gettempdir()) / "JCM-Pitwall-setup.exe"
    return Path(sys.executable).parent / NEU_NAME


def _batch(neu: Path, alt: Path) -> str:
    # Retry-Move: greift erst, wenn die alte EXE nicht mehr gesperrt ist -> deckt
    # den onefile-Doppelprozess (Bootloader + App) sauber ab.
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "set TRIES=0\r\n"
        ":trymove\r\n"
        f'move /y "{neu}" "{alt}" >nul 2>&1\r\n'
        "if errorlevel 1 (\r\n"
        "  set /a TRIES+=1\r\n"
        "  if %TRIES% GEQ 30 goto giveup\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto trymove\r\n"
        ")\r\n"
        ":giveup\r\n"
        f'start "" "{alt}"\r\n'
        'del "%~f0"\r\n'
    )


def apply_update(dest_path, is_installer: bool) -> bool:
    """Installer: starten (der uebernimmt), App soll sich danach beenden.
    Blanke EXE: Retry-Move-Batch + Neustart (nur in der gebauten EXE moeglich)."""
    dest_path = Path(dest_path)
    if is_installer:
        subprocess.Popen([str(dest_path)], close_fds=True)
        return True
    if not IS_FROZEN:
        print("[update] Selbst-Tausch nur in der EXE-Version moeglich (kein frozen).")
        return False
    alt = Path(sys.executable)
    bat = Path(tempfile.gettempdir()) / "jcm_pitwall_update.bat"
    bat.write_text(_batch(dest_path, alt), encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(bat)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0),
        close_fds=True)
    return True


if __name__ == "__main__":
    cur = sys.argv[1] if len(sys.argv) > 1 else VERSION
    try:
        info = check_for_update(cur)
        print("Update:", info if info else "keins (aktuell)")
    except Exception as e:
        print("Fehler:", e)
