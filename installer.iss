; Grafel - one-click Windows installer (Inno Setup 6)
; Build: compile dist\Grafel.exe first (build.bat), then open this in Inno Setup
; or run: iscc installer.iss

#define AppName "Grafel"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define AppPublisher "Codewithusman.com"
#define AppPublisherURL "https://codewithusman.com"
#define AppExe "Grafel.exe"

[Setup]
AppId={{7A3F9C41-52B8-4E1D-9F0A-GRAFEL000001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppPublisherURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=assets\grafel.ico
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
OutputDir=installer
OutputBaseFilename=GrafelSetup
; proper real-life install: admin rights, Program Files, machine-wide
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
Name: "addtopath"; Description: "Add Grafel to the system &PATH"; GroupDescription: "System integration:"

[Files]
Source: "dist\{#AppExe}"; DestDir: "{app}"; Flags: ignoreversion
; console companion for scripted/CLI use (grafel-*.cmd shims); {app} is on
; PATH via the addtopath task, so "where GrafelCLI.exe" finds it - no icons,
; no [Run], no App Paths needed.
Source: "dist\GrafelCLI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\grafel.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\grafel.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\grafel.ico"; Tasks: desktopicon

[Registry]
; add install dir to system PATH (checked task)
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; \
    ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: addtopath; Check: NeedsAddPath('{app}')
; register Grafel.exe for helper scripts and Windows shell resolution
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"
Root: HKLM; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; \
    ValueType: string; ValueName: "Path"; ValueData: "{app}"

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKLM,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + ExpandConstant(Param) + ';', ';' + OrigPath + ';') = 0;
end;
