#define AppName "Vox Groq Early Access"
#define AppVersion "0.1.0"
#define AppExeName "VoxGroq.exe"

[Setup]
AppId={{D7E1B7E1-BB9B-4BF0-A2EC-F999031BB38F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Vox
DefaultDirName={localappdata}\Programs\VoxGroq
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=Vox-Groq-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}

[Files]
Source: "..\dist\VoxGroq\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autoprograms}\{#AppName} - Read me"; Filename: "{app}\README.txt"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
