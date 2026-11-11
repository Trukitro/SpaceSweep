; SpaceSweep installer (Inno Setup 6). Built by:  .\build.ps1 -Installer
;
; Per-user install, no administrator rights: SpaceSweep itself only asks for
; elevation when you press "Restart as admin" for the few cleanups that need it.
; Uninstalling also removes the scheduled tasks the Automatic page may have created.

#define MyAppName "SpaceSweep"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Trukitro"
#define MyAppExeName "SpaceSweep.exe"
#define MyAppURL "https://github.com/Trukitro/SpaceSweep"
; build.ps1 stages the PyInstaller output in a short temp path (deep repo paths exceed MAX_PATH).
#ifndef SourceDir
  #define SourceDir "..\dist\SpaceSweep"
#endif

[Setup]
AppId={{7C3B1E2A-4F5D-4A8E-9B61-2D7E0C5F9A13}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=SpaceSweepSetup
SetupIconFile=..\.build-venv\SpaceSweep.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""SpaceSweep - Daily check"""; Flags: runhidden; RunOnceId: "DelCheck"
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""SpaceSweep - Weekly clean"""; Flags: runhidden; RunOnceId: "DelClean"
