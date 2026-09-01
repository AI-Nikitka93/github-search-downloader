param(
    [string]$Version = "1.1.1",
    [string]$OutputDir = "",
    [switch]$SkipBuild,
    [switch]$Sign,
    [switch]$RequireSignature,
    [string]$CertificateThumbprint = "",
    [string]$SignToolPath = "",
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [string]$UpdateBaseUrl = ""
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
Import-Module Microsoft.PowerShell.Archive -ErrorAction Stop

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Resolve-FullPath {
    param([string]$PathValue)
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Get-Sha256 {
    param([string]$PathValue)
    $stream = [System.IO.File]::OpenRead($PathValue)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $sha256.ComputeHash($stream)
            return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "").ToUpperInvariant()
        }
        finally {
            $sha256.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

function Assert-ChildPath {
    param(
        [string]$Parent,
        [string]$Child
    )
    $parentFull = (Resolve-FullPath $Parent).TrimEnd([char[]]@("\", "/"))
    $childFull = Resolve-FullPath $Child
    $isInside = $childFull.Equals($parentFull, [System.StringComparison]::OrdinalIgnoreCase) -or
        $childFull.StartsWith("$parentFull\", [System.StringComparison]::OrdinalIgnoreCase) -or
        $childFull.StartsWith("$parentFull/", [System.StringComparison]::OrdinalIgnoreCase)
    if (-not $isInside) {
        throw "Refusing to remove path outside release output: $childFull"
    }
}

function Find-SignTool {
    param([string]$ExplicitPath)
    if ($ExplicitPath.Trim()) {
        if (-not (Test-Path -LiteralPath $ExplicitPath)) {
            throw "SignToolPath not found: $ExplicitPath"
        }
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }
    $command = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $kitsRoot = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    if (Test-Path -LiteralPath $kitsRoot) {
        $candidate = Get-ChildItem -Path $kitsRoot -Recurse -Filter "signtool.exe" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "\\x64\\signtool\.exe$" } |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    throw "SignTool was requested but signtool.exe was not found. Install Windows SDK or pass -SignToolPath."
}

function Join-UpdateUrl {
    param(
        [string]$BaseUrl,
        [string]$FileName
    )
    if (-not $BaseUrl.Trim()) {
        return $FileName
    }
    return "$($BaseUrl.TrimEnd('/'))/$([System.Uri]::EscapeDataString($FileName))"
}

function Set-InstallerVersion {
    param(
        [string]$InstallerPath,
        [string]$ReleaseVersion
    )
    $script = Get-Content -LiteralPath $InstallerPath -Raw -Encoding UTF8
    $updated = $script -replace '(?m)^\$ProductVersion\s*=\s*"[^"]*"\r?$', "`$ProductVersion = `"$ReleaseVersion`""
    if ($updated -eq $script -and $script -notmatch '(?m)^\$ProductVersion\s*=') {
        throw "Installer script does not declare ProductVersion: $InstallerPath"
    }
    Set-Content -LiteralPath $InstallerPath -Value $updated -Encoding UTF8
}

function Get-ReleaseSignature {
    param([string]$PathValue)
    try {
        return Get-AuthenticodeSignature -LiteralPath $PathValue
    } catch {
        return [pscustomobject]@{
            Status = "Unavailable"
            SignerCertificate = $null
            Error = $_.Exception.Message
        }
    }
}

if (-not $OutputDir.Trim()) {
    $OutputDir = Join-Path $Root "release"
}
$ReleaseRoot = Resolve-FullPath $OutputDir
$ExePath = Join-Path $Root "dist\GithubSearchDownloader.exe"
$BuildScript = Join-Path $Root "build_windows.ps1"

if (-not $SkipBuild) {
    & $BuildScript
    if ($LASTEXITCODE -ne 0) {
        throw "build_windows.ps1 failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path -LiteralPath $ExePath)) {
    throw "Missing executable: $ExePath"
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
$ReleaseName = "GithubSearchDownloader-$Version-windows-x64"
$StageDir = Join-Path $ReleaseRoot $ReleaseName
$ZipPath = Join-Path $ReleaseRoot "$ReleaseName.zip"
$ManifestPath = Join-Path $ReleaseRoot "release_manifest.json"
$UpdateManifestPath = Join-Path $ReleaseRoot "update_manifest.json"
$ChecksumsPath = Join-Path $ReleaseRoot "SHA256SUMS.txt"
$UpdateChannelFileName = "update_channel.json"

if (Test-Path -LiteralPath $StageDir) {
    Assert-ChildPath -Parent $ReleaseRoot -Child $StageDir
    Remove-Item -LiteralPath $StageDir -Recurse -Force
}
if (Test-Path -LiteralPath $ZipPath) {
    Assert-ChildPath -Parent $ReleaseRoot -Child $ZipPath
    Remove-Item -LiteralPath $ZipPath -Force
}

New-Item -ItemType Directory -Force -Path $StageDir | Out-Null
Copy-Item -LiteralPath $ExePath -Destination (Join-Path $StageDir "GithubSearchDownloader.exe") -Force
Copy-Item -LiteralPath (Join-Path $Root "README.md") -Destination (Join-Path $StageDir "README.md") -Force
Copy-Item -LiteralPath (Join-Path $Root "LICENSE.txt") -Destination (Join-Path $StageDir "LICENSE.txt") -Force
Copy-Item -LiteralPath (Join-Path $Root "docs\ARCHITECTURE.md") -Destination (Join-Path $StageDir "ARCHITECTURE.md") -Force
$AssetsDir = Join-Path $Root "assets"
if (Test-Path -LiteralPath $AssetsDir) {
    Copy-Item -LiteralPath $AssetsDir -Destination (Join-Path $StageDir "assets") -Recurse -Force
}
foreach ($scriptName in @("install_windows.ps1", "uninstall_windows.ps1", "check_updates_windows.ps1")) {
    $scriptPath = Join-Path $Root "packaging\$scriptName"
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        throw "Missing distribution script: $scriptPath"
    }
    $stagedScriptPath = Join-Path $StageDir $scriptName
    Copy-Item -LiteralPath $scriptPath -Destination $stagedScriptPath -Force
    if ($scriptName -eq "install_windows.ps1") {
        Set-InstallerVersion -InstallerPath $stagedScriptPath -ReleaseVersion $Version
    }
}
$VerifierPath = Join-Path $Root "verify_release_windows.ps1"
if (-not (Test-Path -LiteralPath $VerifierPath)) {
    throw "Missing release verifier: $VerifierPath"
}
Copy-Item -LiteralPath $VerifierPath -Destination (Join-Path $StageDir "verify_release_windows.ps1") -Force

$DownloadUrl = Join-UpdateUrl -BaseUrl $UpdateBaseUrl -FileName "$ReleaseName.zip"
$UpdateManifestUrl = Join-UpdateUrl -BaseUrl $UpdateBaseUrl -FileName "update_manifest.json"
if ($UpdateBaseUrl.Trim()) {
    $UpdateChannel = [ordered]@{
        product = "GithubSearchDownloader"
        channel = "stable"
        latest_version = $Version
        update_manifest_url = $UpdateManifestUrl
        generated_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    }
    $UpdateChannel | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $StageDir $UpdateChannelFileName) -Encoding UTF8
}

$StageExePath = Join-Path $StageDir "GithubSearchDownloader.exe"

if ($Sign) {
    $SignTool = Find-SignTool -ExplicitPath $SignToolPath
    if (-not $CertificateThumbprint.Trim()) {
        throw "Signing requested but -CertificateThumbprint was not provided."
    }
    & $SignTool sign /sha1 $CertificateThumbprint /fd SHA256 /tr $TimestampUrl /td SHA256 $StageExePath
    if ($LASTEXITCODE -ne 0) {
        throw "SignTool failed with exit code $LASTEXITCODE"
    }
} else {
    $SignTool = ""
}

$Signature = Get-ReleaseSignature -PathValue $StageExePath
if ($RequireSignature -and $Signature.Status -ne "Valid") {
    throw "Release signature gate failed. Authenticode status: $($Signature.Status)"
}

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal -Force

$ArtifactHashes = @()
foreach ($artifact in @($StageExePath, $ZipPath)) {
    $file = Get-Item -LiteralPath $artifact
    $ArtifactHashes += [ordered]@{
        name = $file.Name
        path = $file.FullName
        size_bytes = $file.Length
        sha256 = Get-Sha256 -PathValue $artifact
    }
}

$checksumLines = $ArtifactHashes | ForEach-Object { "$($_.sha256)  $($_.name)" }
Set-Content -LiteralPath $ChecksumsPath -Value $checksumLines -Encoding UTF8

$ZipArtifact = $ArtifactHashes | Where-Object { $_.name -eq "$ReleaseName.zip" } | Select-Object -First 1
$ExeArtifact = $ArtifactHashes | Where-Object { $_.name -eq "GithubSearchDownloader.exe" } | Select-Object -First 1
$UninstallRegistryKey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader"
$UpdateManifest = [ordered]@{
    product = "GithubSearchDownloader"
    latest_version = $Version
    release_name = $ReleaseName
    channel = "stable"
    published_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    download_url = $DownloadUrl
    package_name = "$ReleaseName.zip"
    package_sha256 = $ZipArtifact.sha256
    package_size_bytes = $ZipArtifact.size_bytes
    executable_sha256 = $ExeArtifact.sha256
    signed = ($Signature.Status -eq "Valid")
    authenticode_status = [string]$Signature.Status
    minimum_windows = "Windows 11"
    install_script = "install_windows.ps1"
    uninstall_script = "uninstall_windows.ps1"
    update_script = "check_updates_windows.ps1"
    update_channel = if ($UpdateBaseUrl.Trim()) { $UpdateChannelFileName } else { "" }
    update_manifest_url = if ($UpdateBaseUrl.Trim()) { $UpdateManifestUrl } else { "" }
    uninstall_registry_key = $UninstallRegistryKey
}
$UpdateManifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $UpdateManifestPath -Encoding UTF8

$Manifest = [ordered]@{
    product = "GithubSearchDownloader"
    version = $Version
    built_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    release_name = $ReleaseName
    signed = ($Signature.Status -eq "Valid")
    authenticode_status = [string]$Signature.Status
    signer = if ($Signature.SignerCertificate) { $Signature.SignerCertificate.Subject } else { "" }
    timestamp_url = if ($Sign) { $TimestampUrl } else { "" }
    signtool = $SignTool
    update_manifest = $UpdateManifestPath
    update_download_url = $DownloadUrl
    update_script = "check_updates_windows.ps1"
    update_channel = if ($UpdateBaseUrl.Trim()) { (Join-Path $StageDir $UpdateChannelFileName) } else { "" }
    uninstall_registry_key = $UninstallRegistryKey
    artifacts = $ArtifactHashes
}
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

Write-Host "Release package: $ZipPath"
Write-Host "Manifest: $ManifestPath"
Write-Host "Update manifest: $UpdateManifestPath"
Write-Host "Checksums: $ChecksumsPath"
Write-Host "Authenticode status: $($Signature.Status)"
