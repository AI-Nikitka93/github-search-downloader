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
}

# Explicit runtime asset whitelist to prevent bundling raw/unused design sources
$runtimeAssets = @(
    "icon.ico",
    "icon.png",
    "icon_1024.png",
    "wizard_step1_hero.png",
    "hero_storage_vault.png",
    "hero_ai_providers.png",
    "hero_search_radar.png",
    "empty_state_search.png",
    "chip_ai_24.png",
    "chip_fastapi_24.png",
    "chip_osint_24.png",
    "chip_python_24.png",
    "chip_rust_24.png",
    "chip_stars_24.png"
)
$dataArgs = @()
foreach ($asset in $runtimeAssets) {
    $assetPath = Join-Path "$Root\assets" $asset
    if (Test-Path $assetPath) {
        $dataArgs += "--add-data"
        $dataArgs += "$assetPath;assets"
    }
}

# Standard exclusion matrix for bloated/unused transitive modules
$excludeModules = @(
    "numpy",
    "numpy._core",
    "numpy.linalg",
    "numpy.fft",
    "numpy.random",
    "numpy.testing",
    "numpy.f2py",
    "yaml",
    "psutil",
    "charset_normalizer",
    "PIL._avif",
    "PIL.AvifImagePlugin",
    "unittest",
    "unittest.mock",
    "doctest",
    "test",
    "pydoc",
    "pydoc_data",
    "xmlrpc",
    "defusedxml",
    "multiprocessing",
    "distutils",
    "setuptools",
    "pip",
    "turtle",
    "turtledemo",
    "idlelib",
    "curses",
    "pdb",
    "cProfile",
    "profile",
    "pstats"
)
$excludeArgs = @()
foreach ($mod in $excludeModules) {
    $excludeArgs += "--exclude-module"
    $excludeArgs += $mod
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
    --optimize 1 `
    --paths "$Root\src" `
    --collect-all "sv_ttk" `
    --workpath "$PyInstallerBuildRoot" `
    --specpath "$PyInstallerSpecRoot" `
    @modeArgs `
    @iconArgs `
    @dataArgs `
    @excludeArgs `
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
