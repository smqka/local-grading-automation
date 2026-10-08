#define AppName "AI阅卷助手"
#define AppVersion "1.0.0"
#define AppExe "bin\launcher\launcher.exe"

[Setup]
AppId={{A0579F60-B1E6-4B2C-BB6A-2CE78D2F6D2B}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Local Grading Automation Contributors
AppPublisherURL=https://github.com/Liuhe808/local-grading-automation
DefaultDirName={localappdata}\Programs\LocalGradingAutomation
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\..\dist\installer
OutputBaseFilename=AI阅卷助手_Setup_1.0.0_x64
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Messages]
; Use built-in English defaults for non-overridden messages so builds do not
; require an optional external ChineseSimplified.isl translation package.
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载
ButtonNext=下一步(&N) >
ButtonBack=< 上一步(&B)
ButtonInstall=安装(&I)
ButtonFinish=完成(&F)

[Files]
Source: "..\..\dist\windows-stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："; Flags: checkedonce

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent
