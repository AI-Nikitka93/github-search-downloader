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
    --workpath "$PyInstallerBuildRoot" `
    --specpath "$PyInstallerSpecRoot" `
    @modeArgs `
    @iconArgs `
    --name "GithubSearchDownloader" `
    "gui_app.py"

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path $DistExe)) {
    Write-Error "PyInstaller finished but did not create $DistExe"
}

Write-Host "Build complete: $DistExe"
