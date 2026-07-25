; JCM Pitwall - Windows-Installer (Inno Setup 6)
; Baut aus den beiden EXE-Dateien ein Setup mit zwei Komponenten:
;   Fahrer      - das Fenster fuer die Strecke (Standard)
;   Einrichter  - das Werkzeug fuer denjenigen, der das Team aufsetzt
;
; Keine Zugangsdaten im Installer. Die kommen ueber den Team-Code.
; Deshalb darf dieses Setup auch oeffentlich liegen.

#define AppName "JCM Pitwall"
#define AppVersion "1.0.0"
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
; haeufigste Stelle, an der jemand abbricht.
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\JCM-Pitwall.exe

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
Source: "..\dist\JCM-Pitwall.exe";            DestDir: "{app}"; Components: client; Flags: ignoreversion
Source: "..\dist\JCM-Pitwall-Einrichter.exe"; DestDir: "{app}"; Components: admin;  Flags: ignoreversion
Source: "..\ANLEITUNG_FAHRER.md";             DestDir: "{app}"; DestName: "Anleitung.txt"; Components: client; Flags: ignoreversion

[Icons]
Name: "{group}\JCM Pitwall";             Filename: "{app}\JCM-Pitwall.exe";            Components: client
Name: "{group}\JCM Pitwall Einrichter";  Filename: "{app}\JCM-Pitwall-Einrichter.exe"; Components: admin
Name: "{group}\Anleitung";               Filename: "{app}\Anleitung.txt";              Components: client
Name: "{autodesktop}\JCM Pitwall";       Filename: "{app}\JCM-Pitwall.exe";            Components: client; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Verknüpfung auf dem Desktop anlegen"; GroupDescription: "Zusätzlich:"

[Run]
Filename: "{app}\JCM-Pitwall.exe"; Description: "JCM Pitwall jetzt starten"; Flags: nowait postinstall skipifsilent; Components: client

[UninstallDelete]
; Die Konfiguration im Benutzerprofil bleibt bewusst stehen, damit der
; Team-Code nach einer Neuinstallation nicht nochmal gebraucht wird.
Type: dirifempty; Name: "{app}"
