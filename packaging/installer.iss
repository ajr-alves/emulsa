; Inno Setup script: builds EmulsaSetup-<version>.exe from the PyInstaller output in dist\Emulsa
; Run from the repo root:  iscc packaging\installer.iss

#define AppName "Emulsa"
#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{6E3C9C2A-6F0B-4C3B-9F3E-5A1E8D7C2B41}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Emulsa contributors
AppPublisherURL=https://github.com/ajr-alves/emulsa
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=EmulsaSetup-{#AppVersion}
SetupIconFile=..\emulsa\assets\emulsa.ico
UninstallDisplayIcon={app}\Emulsa.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Emulsa\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Emulsa.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Emulsa.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Emulsa.exe"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
