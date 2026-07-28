@echo off
setlocal EnableExtensions
cd /d "%~dp0"

REM ==== JCM Pitwall Deploy =========================================
REM Nutzung:  deploy.bat 1.1.1      (oder ohne Argument -> fragt nach)
REM Committet main, pusht, setzt Tag vX.Y.Z -> GitHub Actions baut
REM den Installer (Fahrer + Einrichter) und haengt ihn ans Release.
REM Bewusst KEIN Force-Push: das ist dein echter, gewachsener Klon.
REM =================================================================

set "VERSION=%~1"
if "%VERSION%"=="" set /p "VERSION=Version (z.B. 1.1.1, ohne v): "
if "%VERSION%"=="" ( echo Keine Version angegeben. & pause & exit /b 1 )

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 ( echo Kein Git-Repo hier. & pause & exit /b 1 )

REM --- Git-Identitaet-Fallback (nur falls nicht gesetzt) -----------
git config user.name  >nul 2>&1 || git config user.name  "Pfoetiman76"
git config user.email >nul 2>&1 || git config user.email "pfoetiman76@users.noreply.github.com"

echo.
echo === 1/3  Commit ===
git add -A
git commit -m "Release v%VERSION%" || echo (nichts Neues zu committen - weiter)

echo.
echo === 2/3  Push main ===
git push origin main
if errorlevel 1 ( echo Push nach main fehlgeschlagen. & pause & exit /b 1 )

echo.
echo === 3/3  Tag v%VERSION% ===
REM gleichnamigen Tag lokal+remote entfernen (erlaubt Re-Release derselben Version)
git tag -d v%VERSION% >nul 2>&1
git push origin :refs/tags/v%VERSION% >nul 2>&1
git tag v%VERSION%
git push origin v%VERSION%
if errorlevel 1 ( echo Tag-Push fehlgeschlagen. & pause & exit /b 1 )

echo.
echo ================================================================
echo  Fertig. Actions baut jetzt den Installer und haengt ihn an
echo  das Release v%VERSION%.
echo  Fortschritt: https://github.com/Pfoetiman76/jcm-pitwall/actions
echo ================================================================
pause
