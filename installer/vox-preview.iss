#define AppName "Vox Early Preview"
#define AppVersion "0.1.0"
#define AppExeName "VoxPreview.exe"

[Setup]
AppId={{E15C2A46-C0E8-4E3A-A922-84012C8F9981}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Vox preview
DefaultDirName={localappdata}\Programs\VoxPreview
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=Vox-Preview-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\VoxPreview\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\{#AppName} - Read me"; Filename: "{app}\README.txt"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
