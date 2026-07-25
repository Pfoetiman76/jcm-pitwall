@echo off
cd /d "%~dp0"
title JCM Pitwall - Fahrer-Client
python run_client.py %*
pause
