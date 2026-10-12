#ifndef AppVersion
  #define AppVersion "0.4.1"
#endif
[Setup]
AppId={{39F1E96A-B88B-4E5E-9BCB-EF4D3C4C9EC2}
AppName=FRM
AppVersion={#AppVersion}
AppPublisher=Luca Auletta
AppCopyright=Copyright (C) 2026 Luca Auletta - https://github.com/lucaauletta/frm
VersionInfoCompany=Luca Auletta
VersionInfoDescription=FRM Setup - https://github.com/lucaauletta/frm
VersionInfoCopyright=Copyright (C) 2026 Luca Auletta
AppPublisherURL=https://github.com/lucaauletta/frm
DefaultDirName={localappdata}\Programs\FRM
DefaultGroupName=FRM
PrivilegesRequired=lowest
UsePreviousAppDir=yes
UninstallDisplayIcon={app}\FRM.exe
OutputDir=..\artifacts
OutputBaseFilename=FRM-v{#AppVersion}-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\frm\assets\app-icon.ico
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE
[Files]
Source: "..\dist\FRM-Portable.exe"; DestDir: "{app}"; DestName: "FRM.exe"; Flags: ignoreversion
[Icons]
Name: "{group}\FRM"; Filename: "{app}\FRM.exe"
Name: "{autodesktop}\FRM"; Filename: "{app}\FRM.exe"; Tasks: desktopicon
[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked
[Run]
Filename: "{app}\FRM.exe"; Description: "Launch FRM"; Flags: nowait postinstall skipifsilent
