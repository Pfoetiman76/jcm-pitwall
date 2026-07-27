; JCM Pitwall - Windows-Installer (Inno Setup 6)
; Installiert zwei onedir-Apps in eigene Unterordner:
;   {app}\Fahrer\JCM-Pitwall.exe             (+ _internal)
;   {app}\Einrichter\JCM-Pitwall-Einrichter.exe (+ _internal)
;
; onedir statt onefile: die EXE entpackt sich NICHT zur Laufzeit -> kein _MEI-
; Ordner, kein "Failed to load python312.dll". Jede App traegt ihre DLLs im
; eigenen _internal, deshalb getrennte Unterordner (kein Kollidieren).
;
; Keine Zugangsdaten im Installer. Die kommen ueber den Team-Code.

#define AppName "JCM Pitwall"
#ifndef AppVersion
  #define AppVersion "1.0.7"
#endif
#define Publisher "JCM Motorsport"

[Setup]
AppId={{8F3C2A41-7D5E-4B19-9C3A-JCMPITWALL01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#Publisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputBaseFilename=JCM-Pitwall-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Ohne Administratorrechte - erspart den UAC-Dialog und damit die
; haeufigste Stelle, an der jemand abbricht. {autopf} landet dann in
; %LocalAppData%\Programs (benutzerschreibbar -> Auto-Update ohne Admin).
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Fahrer\JCM-Pitwall.exe
; Laufende App vor dem Ersetzen sauber schliessen (Auto-Update-Fall).
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Types]
Name: "fahrer";     Description: "Ich fahre mit"
Name: "einrichter"; Description: "Ich richte das Team ein"
Name: "voll";       Description: "Alles installieren"

[Components]
Name: "client"; Description: "Fahrer-Fenster"; Types: fahrer einrichter voll; Flags: fixed
Name: "admin";  Description: "Einrichter (Datenbank, Fahrer, Team-Code)"; Types: einrichter voll

[Files]
; Ganze onedir-Ordner rekursiv einpacken (EXE + _internal).
Source: "..\dist\JCM-Pitwall\*";            DestDir: "{app}\Fahrer"; \
    Components: client; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\JCM-Pitwall-Einrichter\*"; DestDir: "{app}\Einrichter"; \
    Components: admin;  Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\ANLEITUNG_FAHRER.md"; DestDir: "{app}"; DestName: "Anleitung.txt"; \
    Components: client; Flags: ignoreversion

[Icons]
Name: "{group}\JCM Pitwall";            Filename: "{app}\Fahrer\JCM-Pitwall.exe";                 Components: client
Name: "{group}\JCM Pitwall Einrichter"; Filename: "{app}\Einrichter\JCM-Pitwall-Einrichter.exe";  Components: admin
Name: "{group}\Anleitung";              Filename: "{app}\Anleitung.txt";                          Components: client
Name: "{autodesktop}\JCM Pitwall";      Filename: "{app}\Fahrer\JCM-Pitwall.exe";                 Components: client; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop anlegen"; GroupDescription: "Zusätzlich:"

[Run]
Filename: "{app}\Fahrer\JCM-Pitwall.exe"; Description: "JCM Pitwall jetzt starten"; \
    Flags: nowait postinstall skipifsilent; Components: client

[UninstallDelete]
; Konfiguration im Benutzerprofil bleibt bewusst stehen (Team-Code).
Type: filesandordirs; Name: "{app}\Fahrer"
Type: filesandordirs; Name: "{app}\Einrichter"
Type: dirifempty;     Name: "{app}"
