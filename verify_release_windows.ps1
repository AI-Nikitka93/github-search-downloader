param(
    [string]$ReleaseDir = "",
    [string]$Version = "0.0.1",
    [switch]$RequireSignature,
    [switch]$RequireHostedUpdateUrl
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $ReleaseDir.Trim()) {
    $ReleaseDir = Join-Path $Root "release"
}

$ReleaseRoot = [System.IO.Path]::GetFullPath($ReleaseDir)
$ManifestPath = Join-Path $ReleaseRoot "release_manifest.json"
$UpdateManifestPath = Join-Path $ReleaseRoot "update_manifest.json"
$ChecksumsPath = Join-Path $ReleaseRoot "SHA256SUMS.txt"
$UpdateChannelFileName = "update_channel.json"

function Assert-FileExists {
    param([string]$PathValue)
    if (-not (Test-Path -LiteralPath $PathValue -PathType Leaf)) {
        throw "Missing required file: $PathValue"
    }
}

function Read-JsonFile {
    param([string]$PathValue)
    Assert-FileExists -PathValue $PathValue
    return Get-Content -LiteralPath $PathValue -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Assert-Equal {
    param(
        [object]$Actual,
        [object]$Expected,
        [string]$Message
    )
    if ([string]$Actual -ne [string]$Expected) {
        throw "$Message Expected='$Expected' Actual='$Actual'"
    }
}

function Get-Sha256 {
    param([string]$PathValue)
    Assert-FileExists -PathValue $PathValue
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

function Get-ChecksumMap {
    param([string]$PathValue)
    Assert-FileExists -PathValue $PathValue
    $map = @{}
    foreach ($line in Get-Content -LiteralPath $PathValue -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed) {
            continue
        }
        if ($trimmed -notmatch "^(?<hash>[0-9A-Fa-f]{64})\s+(?<name>.+)$") {
            throw "Invalid checksum line: $line"
        }
        $map[$Matches["name"].Trim()] = $Matches["hash"].ToUpperInvariant()
    }
    return $map
}

function Test-HostedUrl {
    param([string]$Value)
    $parsed = $null
    if (-not [System.Uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$parsed)) {
        return $false
    }
    return $parsed.Scheme -in @("https", "http")
}

Assert-FileExists -PathValue $ManifestPath
Assert-FileExists -PathValue $UpdateManifestPath
Assert-FileExists -PathValue $ChecksumsPath

$Manifest = Read-JsonFile -PathValue $ManifestPath
$UpdateManifest = Read-JsonFile -PathValue $UpdateManifestPath
$Checksums = Get-ChecksumMap -PathValue $ChecksumsPath

Assert-Equal -Actual $Manifest.product -Expected "GithubSearchDownloader" -Message "Unexpected manifest product."
Assert-Equal -Actual $Manifest.version -Expected $Version -Message "Unexpected manifest version."
Assert-Equal -Actual $UpdateManifest.product -Expected "GithubSearchDownloader" -Message "Unexpected update manifest product."
Assert-Equal -Actual $UpdateManifest.latest_version -Expected $Version -Message "Unexpected update manifest version."
Assert-Equal -Actual $UpdateManifest.release_name -Expected $Manifest.release_name -Message "Release names differ."

$ReleaseName = [string]$Manifest.release_name
$StageDir = Join-Path $ReleaseRoot $ReleaseName
$ZipPath = Join-Path $ReleaseRoot "$ReleaseName.zip"
$StageExePath = Join-Path $StageDir "GithubSearchDownloader.exe"

Assert-FileExists -PathValue $ZipPath
Assert-FileExists -PathValue $StageExePath

$ActualZipHash = Get-Sha256 -PathValue $ZipPath
$ActualExeHash = Get-Sha256 -PathValue $StageExePath

Assert-Equal -Actual $UpdateManifest.package_name -Expected "$ReleaseName.zip" -Message "Update package name mismatch."
Assert-Equal -Actual $UpdateManifest.package_sha256 -Expected $ActualZipHash -Message "Update package SHA256 mismatch."
Assert-Equal -Actual $UpdateManifest.executable_sha256 -Expected $ActualExeHash -Message "Update executable SHA256 mismatch."
Assert-Equal -Actual $UpdateManifest.install_script -Expected "install_windows.ps1" -Message "Update install script mismatch."
Assert-Equal -Actual $UpdateManifest.uninstall_script -Expected "uninstall_windows.ps1" -Message "Update uninstall script mismatch."
Assert-Equal -Actual $UpdateManifest.update_script -Expected "check_updates_windows.ps1" -Message "Update checker script mismatch."

if (-not $Checksums.ContainsKey("GithubSearchDownloader.exe")) {
    throw "SHA256SUMS.txt does not list GithubSearchDownloader.exe."
}
if (-not $Checksums.ContainsKey("$ReleaseName.zip")) {
    throw "SHA256SUMS.txt does not list $ReleaseName.zip."
}
Assert-Equal -Actual $Checksums["GithubSearchDownloader.exe"] -Expected $ActualExeHash -Message "Checksum file exe hash mismatch."
Assert-Equal -Actual $Checksums["$ReleaseName.zip"] -Expected $ActualZipHash -Message "Checksum file zip hash mismatch."

$ManifestArtifacts = @{}
foreach ($artifact in @($Manifest.artifacts)) {
    $ManifestArtifacts[[string]$artifact.name] = $artifact
    Assert-FileExists -PathValue ([string]$artifact.path)
    $actualHash = Get-Sha256 -PathValue ([string]$artifact.path)
    Assert-Equal -Actual $artifact.sha256 -Expected $actualHash -Message "Manifest artifact hash mismatch for $($artifact.name)."
}
foreach ($requiredArtifact in @("GithubSearchDownloader.exe", "$ReleaseName.zip")) {
    if (-not $ManifestArtifacts.ContainsKey($requiredArtifact)) {
        throw "release_manifest.json does not list $requiredArtifact."
    }
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $entries = @{}
    foreach ($entry in $zip.Entries) {
        $entries[$entry.FullName.Replace("\", "/")] = $true
    }
    $requiredEntries = @(
        "GithubSearchDownloader.exe",
        "README.md",
        "LICENSE.txt",
        "ARCHITECTURE.md",
        "install_windows.ps1",
        "uninstall_windows.ps1",
        "check_updates_windows.ps1",
        "verify_release_windows.ps1"
    )
    if (Test-HostedUrl -Value ([string]$UpdateManifest.download_url)) {
        $requiredEntries += $UpdateChannelFileName
    }
    foreach ($requiredEntry in $requiredEntries) {
        if (-not $entries.ContainsKey($requiredEntry)) {
            throw "Release zip missing entry: $requiredEntry"
        }
    }
}
finally {
    $zip.Dispose()
}

$Signature = Get-ReleaseSignature -PathValue $StageExePath
$ManifestSignatureStatus = [string]$Manifest.authenticode_status
$UpdateSignatureStatus = [string]$UpdateManifest.authenticode_status
if ([string]$Signature.Status -eq "Unavailable" -and -not [bool]$Manifest.signed) {
    $ExpectedSignatureStatus = $ManifestSignatureStatus
} else {
    $ExpectedSignatureStatus = [string]$Signature.Status
}
Assert-Equal -Actual $ManifestSignatureStatus -Expected $ExpectedSignatureStatus -Message "Manifest Authenticode status mismatch."
Assert-Equal -Actual $UpdateSignatureStatus -Expected $ExpectedSignatureStatus -Message "Update Authenticode status mismatch."

if ($RequireSignature -and $Signature.Status -ne "Valid") {
    throw "Signature gate failed. Authenticode status: $($Signature.Status)"
}
if ($RequireHostedUpdateUrl -and -not (Test-HostedUrl -Value ([string]$UpdateManifest.download_url))) {
    throw "Hosted update URL gate failed. download_url is not an absolute http(s) URL: $($UpdateManifest.download_url)"
}
if ($RequireHostedUpdateUrl) {
    $UpdateChannelPath = Join-Path $StageDir $UpdateChannelFileName
    Assert-FileExists -PathValue $UpdateChannelPath
    $UpdateChannel = Read-JsonFile -PathValue $UpdateChannelPath
    Assert-Equal -Actual $UpdateChannel.product -Expected "GithubSearchDownloader" -Message "Unexpected update channel product."
    Assert-Equal -Actual $UpdateChannel.latest_version -Expected $Version -Message "Unexpected update channel version."
    if (-not (Test-HostedUrl -Value ([string]$UpdateChannel.update_manifest_url))) {
        throw "Hosted update channel gate failed. update_manifest_url is not an absolute http(s) URL: $($UpdateChannel.update_manifest_url)"
    }
}

Write-Host "Release verification OK"
Write-Host "Release: $ReleaseName"
Write-Host "Zip SHA256: $ActualZipHash"
Write-Host "Exe SHA256: $ActualExeHash"
Write-Host "Authenticode status: $($Signature.Status)"
Write-Host "Update URL: $($UpdateManifest.download_url)"
