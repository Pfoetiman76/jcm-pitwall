@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JCM Pitwall

REM ---- Python suchen -------------------------------------------------
set PY=
where py >nul 2>nul && set PY=py
if not defined PY (where python >nul 2>nul && set PY=python)

if not defined PY (
  echo.
  echo   ============================================================
  echo     Python fehlt auf diesem Rechner.
  echo   ============================================================
  echo.
  echo   So geht es weiter:
  echo.
  echo     1. Es oeffnet sich gleich die Download-Seite.
  echo     2. Grossen gelben Knopf "Download Python" anklicken.
  echo     3. Datei ausfuehren.
  echo     4. WICHTIG: unten das Haekchen bei
  echo        "Add python.exe to PATH" setzen!
  echo     5. "Install Now" klicken, warten, fertig.
  echo     6. Danach diese Datei hier nochmal doppelklicken.
  echo.
  pause
  start https://www.python.org/downloads/
  exit /b 1
)

REM ---- Zugangsdaten pruefen -----------------------------------------
if not exist "pitwall_config.json" (
  echo.
  echo   Die Datei pitwall_config.json fehlt.
  echo   Du brauchst das fertige Paket von Marcel - da ist sie drin.
  echo.
  pause
  exit /b 1
)

REM ---- Fenster starten -----------------------------------------------
%PY% pitwall.py
if errorlevel 1 (
  echo.
  echo   Da ist etwas schiefgegangen. Schick Marcel einen Screenshot
  echo   von diesem Fenster.
  echo.
  pause
)
