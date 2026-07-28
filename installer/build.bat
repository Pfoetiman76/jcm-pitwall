@echo off
REM Baut beide Programme und daraus den Windows-Installer.
REM Nur Marcel fuehrt das aus, einmal pro Version.
REM
REM Voraussetzungen:
REM   - Python mit PyInstaller  (installiert das Skript selbst)
REM   - Inno Setup 6            (winget install JRSoftware.InnoSetup)
REM
REM WICHTIG: onedir (nicht onefile) - genau wie die CI und setup.iss es
REM erwarten. onefile wuerde dist\JCM-Pitwall.exe erzeugen, setup.iss will
REM aber den Ordner dist\JCM-Pitwall\ mit _internal. Ausserdem: das .ico
REM wird per --icon in die EXE eingebettet UND per --add-data mitgeliefert,
REM damit das laufende Fenster (iconbitmap) es findet.

cd /d "%~dp0\.."
where py >nul 2>nul && (set PY=py) || (set PY=python)

echo [1/4] PyInstaller bereitstellen ...
%PY% -m pip install --quiet --upgrade pyinstaller || goto :fehler

echo [2/4] Fahrer-Fenster bauen ...
%PY% -m PyInstaller --noconfirm --onedir --windowed ^
  --name JCM-Pitwall ^
  --icon client\jcm.ico ^
  --add-data "client\jcm.ico;." ^
  --distpath dist --workpath build --specpath build ^
  --paths client ^
  --collect-submodules pyLMUSharedMemory ^
  --hidden-import tkinter ^
  client\pitwall.py || goto :fehler

echo [3/4] Einrichter bauen ...
%PY% -m PyInstaller --noconfirm --onedir --windowed ^
  --name JCM-Pitwall-Einrichter ^
  --icon client\jcm-einrichter.ico ^
  --add-data "client\jcm-einrichter.ico;." ^
  --distpath dist --workpath build --specpath build ^
  --paths client ^
  --hidden-import tkinter ^
  client\einrichter.py || goto :fehler

echo [4/4] Installer bauen ...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo.
  echo   Inno Setup 6 fehlt. Installieren mit:
  echo      winget install JRSoftware.InnoSetup
  echo.
  echo   Die beiden Programmordner liegen aber schon fertig in dist\ -
  echo   die kannst du auch einzeln verteilen.
  pause & exit /b 1
)
%ISCC% installer\setup.iss || goto :fehler

echo.
echo Fertig. Der Installer liegt in:  installer\Output\
echo Diese eine Datei bekommen alle - Fahrer wie Einrichter.
pause
exit /b 0

:fehler
echo.
echo Build fehlgeschlagen. Die Zeile darueber sagt warum.
pause
exit /b 1
