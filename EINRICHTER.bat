@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JCM Pitwall - Einrichter
where py >nul 2>nul && (set PY=py) || (set PY=python)
if not defined PY (
  echo Python fehlt. Herunterladen von python.org,
  echo beim Installieren "Add python.exe to PATH" anhaken.
  pause & start https://www.python.org/downloads/ & exit /b 1
)
%PY% client\einrichter.py
if errorlevel 1 pause
