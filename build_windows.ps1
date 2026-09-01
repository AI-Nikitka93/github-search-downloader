param(
    [switch]$Console
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$DistExe = Join-Path $Root "dist\GithubSearchDownloader.exe"
$PyInstallerBuildRoot = Join-Path $Root "_build\pyinstaller"
$PyInstallerSpecRoot = Join-Path $Root "_build\spec"

$checkScript = @'
import importlib.util
raise SystemExit(0 if importlib.util.find_spec("PyInstaller") else 1)
'@
$checkScript | python -
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Run: python -m pip install .[build]"
}

$modeArgs = @()
if (-not $Console) {
    $modeArgs += "--windowed"
}

$iconArgs = @()
if (Test-Path "$Root\assets\icon.ico") {
    $iconArgs += "--icon"
    $iconArgs += "$Root\assets\icon.ico"
    $iconArgs += "--add-data"
    $iconArgs += "$Root\assets;assets"
}

# Generate Windows PE version resource dynamically
python "$Root\packaging\generate_version_info.py"
$versionInfoFile = "$Root\_build\version_info.txt"
$versionArgs = @()
if (Test-Path $versionInfoFile) {
    $versionArgs += "--version-file"
    $versionArgs += $versionInfoFile
}

$runningApp = Get-CimInstance Win32_Process -Filter "Name='GithubSearchDownloader.exe'" |
    Where-Object { $_.ExecutablePath -eq $DistExe }
if ($runningApp) {
    $processIds = ($runningApp | ForEach-Object { $_.ProcessId }) -join ", "
    Write-Error "Close running GithubSearchDownloader.exe process(es) before building. PID(s): $processIds"
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --paths "$Root\src" `
    --collect-all "sv_ttk" `
    --workpath "$PyInstallerBuildRoot" `
    --specpath "$PyInstallerSpecRoot" `
    @modeArgs `
    @iconArgs `
    @versionArgs `
    --name "GithubSearchDownloader" `
    "gui_app.py"

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path $DistExe)) {
    Write-Error "PyInstaller finished but did not create $DistExe"
}

Write-Host "Build complete: $DistExe"
