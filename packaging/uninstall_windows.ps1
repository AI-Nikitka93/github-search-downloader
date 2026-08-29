param(
    [string]$InstallDir = "",
    [switch]$KeepUserData
)

$ErrorActionPreference = "Stop"
$UninstallRegistrySubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader"
$UninstallRegistryKey = "HKCU:\$UninstallRegistrySubkey"

if (-not $InstallDir.Trim()) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\GithubSearchDownloader"
}

$ResolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$DefaultRoot = ([System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs"))).TrimEnd([char[]]@("\", "/"))
$isDefaultInstallPath = $ResolvedInstallDir.Equals($DefaultRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedInstallDir.StartsWith("$DefaultRoot\", [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedInstallDir.StartsWith("$DefaultRoot/", [System.StringComparison]::OrdinalIgnoreCase)
if (-not $isDefaultInstallPath -and -not $PSBoundParameters.ContainsKey("InstallDir")) {
    throw "Resolved install path is outside LocalAppData Programs: $ResolvedInstallDir"
}
if ($ResolvedInstallDir.Length -lt 10) {
    throw "Refusing to uninstall suspiciously short path: $ResolvedInstallDir"
}

$TargetExe = Join-Path $ResolvedInstallDir "GithubSearchDownloader.exe"

function Assert-ProductInstallDirectory {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue -PathType Container)) {
        return
    }

    $manifestPath = Join-Path $PathValue "install_manifest.json"
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        try {
            $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
            if ([string]$manifest.product -eq "GithubSearchDownloader") {
                return
            }
        } catch {
            $null = $_
        }
    }

    $exePath = Join-Path $PathValue "GithubSearchDownloader.exe"
    $uninstallerPath = Join-Path $PathValue "uninstall_windows.ps1"
    if ((Test-Path -LiteralPath $exePath -PathType Leaf) -and
        (Test-Path -LiteralPath $uninstallerPath -PathType Leaf)) {
        return
    }

    throw "Refusing to remove install directory without GithubSearchDownloader product markers: $PathValue"
}

Assert-ProductInstallDirectory -PathValue $ResolvedInstallDir

$running = Get-CimInstance Win32_Process -Filter "Name='GithubSearchDownloader.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -eq $TargetExe }
if ($running) {
    $processIds = ($running | ForEach-Object { $_.ProcessId }) -join ", "
    throw "Close GithubSearchDownloader.exe before uninstalling. PID(s): $processIds"
}

$StartMenuShortcut = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\GithubSearchDownloader\GitHub Search Downloader.lnk"
$StartMenuDir = Split-Path -Parent $StartMenuShortcut
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath("Desktop")) "GitHub Search Downloader.lnk"

foreach ($shortcut in @($StartMenuShortcut, $DesktopShortcut)) {
    if (Test-Path -LiteralPath $shortcut) {
        Remove-Item -LiteralPath $shortcut -Force
    }
}
if (Test-Path -LiteralPath $StartMenuDir) {
    $remaining = Get-ChildItem -LiteralPath $StartMenuDir -Force -ErrorAction SilentlyContinue
    if (-not $remaining) {
        Remove-Item -LiteralPath $StartMenuDir -Force
    }
}

if (Test-Path -LiteralPath $UninstallRegistryKey) {
    $registryInstallLocation = ""
    try {
        $registryInstallLocation = [string](Get-ItemProperty -Path $UninstallRegistryKey -Name "InstallLocation" -ErrorAction Stop).InstallLocation
    } catch {
        $registryInstallLocation = ""
    }
    if (-not $registryInstallLocation -or
        [System.IO.Path]::GetFullPath($registryInstallLocation) -eq $ResolvedInstallDir) {
        Remove-Item -Path $UninstallRegistryKey -Recurse -Force
        Write-Host "Removed uninstall registry key: $UninstallRegistrySubkey"
    } else {
        Write-Host "Skipped uninstall registry cleanup; key points to another install: $registryInstallLocation"
    }
}

if (Test-Path -LiteralPath $ResolvedInstallDir) {
    Remove-Item -LiteralPath $ResolvedInstallDir -Recurse -Force
}

if (-not $KeepUserData) {
    $AppDataDir = Join-Path $env:APPDATA "GithubSearchDownloader"
    if (Test-Path -LiteralPath $AppDataDir) {
        Remove-Item -LiteralPath $AppDataDir -Recurse -Force
    }
}

Write-Host "Uninstalled GitHub Search Downloader from: $ResolvedInstallDir"
