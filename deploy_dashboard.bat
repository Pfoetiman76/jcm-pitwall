@echo off
REM JCM Pitwall - Kommandostand ins Netz stellen.
REM Beim ersten Lauf: Repo anlegen, Zugangsdaten als Secrets hinterlegen, pushen.
REM Danach: nur noch pushen.
cd /d "%~dp0"
setlocal enabledelayedexpansion

set REPO=jcm-pitwall
set USER=Pfoetiman76

where gh >nul 2>nul || (
  echo GitHub CLI fehlt. Installieren mit:  winget install GitHub.cli
  pause & exit /b 1
)

if not exist ".git" ( git init & git branch -M main )
git config user.email >nul 2>nul || git config user.email "%USER%@users.noreply.github.com"
git config user.name  >nul 2>nul || git config user.name  "%USER%"

REM --- Sperre: nichts mit Zugangsdaten hochladen ---------------------
where py >nul 2>nul && (set PY=py) || (set PY=python)
%PY% tools\schluessel_check.py
if errorlevel 1 (
  echo.
  echo Hochladen abgebrochen. Siehe Meldung oben.
  pause & exit /b 1
)

git add -A
git commit -m "Pitwall Kommandostand" || echo Nichts zu committen.

gh repo view %USER%/%REPO% >nul 2>nul || gh repo create %USER%/%REPO% --public --source=. --remote=origin
git remote get-url origin >nul 2>nul || git remote add origin https://github.com/%USER%/%REPO%.git

echo.
echo === Zugangsdaten fuer den Kommandostand ===
echo Die werden als GitHub-Secret hinterlegt, nicht ins Repo geschrieben.
echo Beides steht in Supabase unter Project Settings - API.
echo.
set /p SB_URL="Supabase-URL (https://xxxx.supabase.co): "
set /p SB_KEY="anon public Key (NICHT service_role): "

echo !SB_URL!| gh secret set PITWALL_SUPABASE_URL --repo %USER%/%REPO%
echo !SB_KEY!| gh secret set PITWALL_ANON_KEY     --repo %USER%/%REPO%

git push -u origin main --force

echo.
echo Fertig. Einmalig auf GitHub: Settings - Pages - Source: GitHub Actions
echo Danach laeuft der Kommandostand unter:
echo    https://%USER%.github.io/%REPO%/
echo.
echo Diese Adresse an alle Fahrer geben. Sie sehen sofort Daten,
echo ohne irgendetwas einzutippen.
pause
