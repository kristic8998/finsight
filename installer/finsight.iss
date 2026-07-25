; ============================================================================
; FinSight — Inno Setup installer script
; ----------------------------------------------------------------------------
; Builds a standard Windows installer (Setup.exe) from the PyInstaller
; one-folder output in dist\FinSight. It installs to Program Files, creates
; Start-menu and optional desktop shortcuts, registers an uninstaller in
; "Apps & features", and can launch the app on finish.
;
; PREREQUISITES (run on a Windows machine):
;   1. Build the app first:   scripts\build_windows.bat
;      → produces dist\FinSight\FinSight.exe (one-folder build)
;   2. Install Inno Setup 6+ :  https://jrsoftware.org/isdl.php
;   3. Open this file in the Inno Setup Compiler and press Build (F9),
;      or from a terminal:      ISCC.exe installer\finsight.iss
;   → produces installer\Output\FinSight-Setup-<version>.exe
; ============================================================================

#define AppName "FinSight"
#define AppVersion "1.5.0"
#define AppPublisher "Kristi Chakraborty"
#define AppExeName "FinSight.exe"
#define AppURL "https://github.com/kristic8998/finsight"

[Setup]
AppId={{7F3C2A54-9B1E-4D2A-9C7E-FIN51GHT2026}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Per-user install by default → no admin prompt, works on locked-down laptops.
PrivilegesRequiredOverridesAllowed=dialog commandline
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=FinSight-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
; Uninstaller is generated automatically and registered in Apps & features.
UninstallDisplayName={#AppName} {#AppVersion}
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Ship the entire PyInstaller one-folder output.
Source: "..\dist\FinSight\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\FinSight\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\USER_GUIDE.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\TROUBLESHOOTING.md"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} User Guide"; Filename: "{app}\docs\USER_GUIDE.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName} now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; The app writes user data to %LOCALAPPDATA%\FinSight. Leave it in place on
; uninstall (backups/reports are the user's), but remove any logs we created
; under the install dir. User data removal is documented in TROUBLESHOOTING.md.
Type: filesandordirs; Name: "{app}\_internal\__pycache__"
