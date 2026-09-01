#define MyAppName "GitHub Search Downloader"
#define MyAppExeName "GithubSearchDownloader.exe"
#ifndef MyAppVersion
  #define MyAppVersion "1.1.2"
#endif
#define MyAppPublisher "Nikita Kizevich"
#define MyAppURL "https://github.com/AI-Nikitka93/github-search-downloader"
#define DistExe "..\dist\GithubSearchDownloader.exe"
#define AssetsDir "..\assets"

[Setup]
AppId={{D3F76A0C-82B1-4F48-97F2-8A74902F1C6E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\GithubSearchDownloader
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\release
OutputBaseFilename=GithubSearchDownloader-v{#MyAppVersion}-windows-x64-setup
SetupIconFile={#AssetsDir}\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
AppMutex=GithubSearchDownloaderAppMutex
CloseApplications=force
CloseApplicationsFilter=GithubSearchDownloader.exe
RestartApplications=no
UsePreviousAppDir=yes
DisableDirPage=auto
DirExistsWarning=no
CreateUninstallRegKey=yes
UpdateUninstallLogAppName=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
english.AppRunningWarning=Setup detected that %1 is currently running.%n%nPlease close all instances of %1 before continuing.%n%nClick 'Retry' to try again after closing the program, or 'Cancel' to exit setup.
russian.AppRunningWarning=Установщик обнаружил, что приложение %1 запущено.%n%nПожалуйста, закройте все запущенные копии %1 перед продолжением установки.%n%nНажмите «Повторить» после закрытия программы или «Отмена» для выхода.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
Type: files; Name: "{app}\install_manifest.json"

[Files]
Source: "{#DistExe}"; DestDir: "{app}"; Flags: ignoreversion restartreplace
Source: "{#AssetsDir}\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\packaging\uninstall_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\packaging\check_updates_windows.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
const
  TargetExeName = 'GithubSearchDownloader.exe';
  AppMutexIdentifier = 'GithubSearchDownloaderAppMutex';
  LegacyUninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader';

function IsAppProcessRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := CheckForMutexes(AppMutexIdentifier);
  if not Result then
  begin
    if Exec('cmd.exe', '/c tasklist /FI "IMAGENAME eq ' + TargetExeName + '" 2>nul | find /I "' + TargetExeName + '" >nul', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Result := (ResultCode = 0);
    end;
  end;
end;

function TerminateAppProcess(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('taskkill.exe', '/F /IM ' + TargetExeName + ' /T', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(400);
  Result := not IsAppProcessRunning();
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  while IsAppProcessRunning() do
  begin
    if MsgBox(FmtMessage(CustomMessage('AppRunningWarning'), ['{#MyAppName}']), mbConfirmation, MB_RETRYCANCEL) = idRetry then
    begin
      TerminateAppProcess();
    end
    else
    begin
      Result := False;
      Exit;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NeedsRestart := False;
  Result := '';
  if IsAppProcessRunning() then
  begin
    if not TerminateAppProcess() then
    begin
      Result := FmtMessage(CustomMessage('AppRunningWarning'), ['{#MyAppName}']);
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if RegKeyExists(HKCU, LegacyUninstallKey) then
    begin
      RegDeleteKeyIncludingSubkeys(HKCU, LegacyUninstallKey);
    end;
  end;
end;
