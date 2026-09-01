param(
    [string]$InstallDir = "",
    [switch]$DesktopShortcut,
    [switch]$Launch
)

$ErrorActionPreference = "Stop"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceExe = Join-Path $SourceDir "GithubSearchDownloader.exe"
$ProductName = "GithubSearchDownloader"
$DisplayName = "GitHub Search Downloader"
$ProductVersion = "1.1.0"
$UninstallRegistrySubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader"
$UninstallRegistryKey = "HKCU:\$UninstallRegistrySubkey"

if (-not (Test-Path -LiteralPath $SourceExe)) {
    throw "GithubSearchDownloader.exe was not found next to install_windows.ps1."
}

if (-not $InstallDir.Trim()) {
    $InstallDir = Join-Path $env:LOCALAPPDATA "Programs\GithubSearchDownloader"
}

$ResolvedInstallDir = [System.IO.Path]::GetFullPath($InstallDir)
$InstallRoot = ([System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs"))).TrimEnd([char[]]@("\", "/"))
$isDefaultInstallPath = $ResolvedInstallDir.Equals($InstallRoot, [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedInstallDir.StartsWith("$InstallRoot\", [System.StringComparison]::OrdinalIgnoreCase) -or
    $ResolvedInstallDir.StartsWith("$InstallRoot/", [System.StringComparison]::OrdinalIgnoreCase)
if (-not $isDefaultInstallPath -and -not $PSBoundParameters.ContainsKey("InstallDir")) {
    throw "Resolved install path is outside LocalAppData Programs: $ResolvedInstallDir"
}

New-Item -ItemType Directory -Force -Path $ResolvedInstallDir | Out-Null
$TargetExe = Join-Path $ResolvedInstallDir "GithubSearchDownloader.exe"
Copy-Item -LiteralPath $SourceExe -Destination $TargetExe -Force

foreach ($fileName in @("README.md", "LICENSE.txt", "ARCHITECTURE.md", "uninstall_windows.ps1", "check_updates_windows.ps1", "update_channel.json")) {
    $sourcePath = Join-Path $SourceDir $fileName
    if (Test-Path -LiteralPath $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $ResolvedInstallDir $fileName) -Force
    }
}

$sourceAssets = Join-Path $SourceDir "assets"
if (Test-Path -LiteralPath $sourceAssets) {
    Copy-Item -LiteralPath $sourceAssets -Destination (Join-Path $ResolvedInstallDir "assets") -Recurse -Force
}

$StartMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\GithubSearchDownloader"
New-Item -ItemType Directory -Force -Path $StartMenuDir | Out-Null

function New-AppShortcut {
    param(
        [string]$ShortcutPath,
        [string]$TargetPath,
        [string]$WorkingDirectory
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($ShortcutPath)
    $shortcut.TargetPath = $TargetPath
    $shortcut.WorkingDirectory = $WorkingDirectory
    $installedIcon = Join-Path $WorkingDirectory "assets\icon.ico"
    if (Test-Path -LiteralPath $installedIcon) {
        $shortcut.IconLocation = "$installedIcon,0"
    } else {
        $shortcut.IconLocation = "$TargetPath,0"
    }
    $shortcut.Description = "GitHub Search Downloader"
    $shortcut.Save()
}

New-AppShortcut `
    -ShortcutPath (Join-Path $StartMenuDir "GitHub Search Downloader.lnk") `
    -TargetPath $TargetExe `
    -WorkingDirectory $ResolvedInstallDir

if ($DesktopShortcut) {
    New-AppShortcut `
        -ShortcutPath (Join-Path ([Environment]::GetFolderPath("Desktop")) "GitHub Search Downloader.lnk") `
        -TargetPath $TargetExe `
        -WorkingDirectory $ResolvedInstallDir
}

$InstalledSizeBytes = (Get-ChildItem -LiteralPath $ResolvedInstallDir -Recurse -File -ErrorAction SilentlyContinue |
    Measure-Object -Property Length -Sum).Sum
$EstimatedSizeKb = [int][Math]::Ceiling(($InstalledSizeBytes -as [double]) / 1KB)
$InstalledUninstaller = Join-Path $ResolvedInstallDir "uninstall_windows.ps1"
$UninstallString = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$InstalledUninstaller`" -InstallDir `"$ResolvedInstallDir`""
$QuietUninstallString = "$UninstallString -KeepUserData"

$installedIconPath = Join-Path $ResolvedInstallDir "assets\icon.ico"
$displayIcon = if (Test-Path -LiteralPath $installedIconPath) { "$installedIconPath,0" } else { "$TargetExe,0" }

New-Item -Path $UninstallRegistryKey -Force | Out-Null
Set-ItemProperty -Path $UninstallRegistryKey -Name "DisplayName" -Value $DisplayName
Set-ItemProperty -Path $UninstallRegistryKey -Name "DisplayVersion" -Value $ProductVersion
Set-ItemProperty -Path $UninstallRegistryKey -Name "Publisher" -Value "Nikita Kizevich"
Set-ItemProperty -Path $UninstallRegistryKey -Name "InstallLocation" -Value $ResolvedInstallDir
Set-ItemProperty -Path $UninstallRegistryKey -Name "DisplayIcon" -Value $displayIcon
Set-ItemProperty -Path $UninstallRegistryKey -Name "UninstallString" -Value $UninstallString
Set-ItemProperty -Path $UninstallRegistryKey -Name "QuietUninstallString" -Value $QuietUninstallString
Set-ItemProperty -Path $UninstallRegistryKey -Name "NoModify" -Type DWord -Value 1
Set-ItemProperty -Path $UninstallRegistryKey -Name "NoRepair" -Type DWord -Value 1
Set-ItemProperty -Path $UninstallRegistryKey -Name "EstimatedSize" -Type DWord -Value $EstimatedSizeKb

$InstallManifest = [ordered]@{
    product = $ProductName
    version = $ProductVersion
    installed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    install_dir = $ResolvedInstallDir
    executable = $TargetExe
    start_menu_shortcut = (Join-Path $StartMenuDir "GitHub Search Downloader.lnk")
    desktop_shortcut = if ($DesktopShortcut) { (Join-Path ([Environment]::GetFolderPath("Desktop")) "GitHub Search Downloader.lnk") } else { "" }
    uninstall_registry_key = $UninstallRegistrySubkey
}
$InstallManifest | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $ResolvedInstallDir "install_manifest.json") -Encoding UTF8

Write-Host "Installed GitHub Search Downloader to: $ResolvedInstallDir"
Write-Host "Start Menu shortcut: $(Join-Path $StartMenuDir 'GitHub Search Downloader.lnk')"
Write-Host "Uninstall registry key: $UninstallRegistrySubkey"

if ($Launch) {
    Start-Process -FilePath $TargetExe -WorkingDirectory $ResolvedInstallDir
}
