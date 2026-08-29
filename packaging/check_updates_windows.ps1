param(
    [string]$UpdateManifest = "",
    [string]$CurrentVersion = "",
    [string]$DownloadDir = "",
    [switch]$DownloadOnly,
    [switch]$Install,
    [string]$InstallDir = "",
    [switch]$DesktopShortcut,
    [switch]$RequireSignature,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Import-Module Microsoft.PowerShell.Utility -ErrorAction Stop
Import-Module Microsoft.PowerShell.Archive -ErrorAction Stop
Add-Type -AssemblyName System.IO.Compression.FileSystem

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProductName = "GithubSearchDownloader"
$UninstallRegistrySubkey = "Software\Microsoft\Windows\CurrentVersion\Uninstall\GithubSearchDownloader"
$UninstallRegistryKey = "HKCU:\$UninstallRegistrySubkey"

function Resolve-FullPath {
    param([string]$PathValue)
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Test-HttpUrl {
    param([string]$Value)
    $parsed = $null
    if (-not [System.Uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$parsed)) {
        return $false
    }
    return $parsed.Scheme -in @("https", "http")
}

function Test-FileUrl {
    param([string]$Value)
    $parsed = $null
    if (-not [System.Uri]::TryCreate($Value, [System.UriKind]::Absolute, [ref]$parsed)) {
        return $false
    }
    return $parsed.Scheme -eq "file"
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
        throw "Refusing to touch path outside updater download directory: $childFull"
    }
}

function Get-ManifestSource {
    if ($UpdateManifest.Trim()) {
        return $UpdateManifest.Trim()
    }
    $updateChannel = Join-Path $ScriptDir "update_channel.json"
    if (Test-Path -LiteralPath $updateChannel -PathType Leaf) {
        $channel = Get-Content -LiteralPath $updateChannel -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($channel.product -and [string]$channel.product -ne $ProductName) {
            throw "Unexpected update channel product: $($channel.product)"
        }
        $channelManifest = [string]$channel.update_manifest_url
        if (-not $channelManifest.Trim()) {
            throw "Update channel is missing required field: update_manifest_url"
        }
        $channelManifest = $channelManifest.Trim()
        $parsed = $null
        if ([System.Uri]::TryCreate($channelManifest, [System.UriKind]::Absolute, [ref]$parsed)) {
            if ($parsed.Scheme -eq "file") {
                return $parsed.LocalPath
            }
            return $channelManifest
        }
        return Resolve-FullPath (Join-Path $ScriptDir $channelManifest)
    }
    $localManifest = Join-Path $ScriptDir "update_manifest.json"
    if (Test-Path -LiteralPath $localManifest -PathType Leaf) {
        return $localManifest
    }
    throw "No update manifest was provided. Pass -UpdateManifest with an http(s) URL or local path."
}

function Read-UpdateManifest {
    param([string]$Source)

    if (Test-HttpUrl -Value $Source) {
        $tempManifest = Join-Path ([System.IO.Path]::GetTempPath()) "GithubSearchDownloader-update_manifest-$PID.json"
        Invoke-WebRequest -Uri $Source -OutFile $tempManifest -UseBasicParsing
        try {
            return Get-Content -LiteralPath $tempManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        }
        finally {
            if (Test-Path -LiteralPath $tempManifest) {
                Remove-Item -LiteralPath $tempManifest -Force
            }
        }
    }

    if (Test-FileUrl -Value $Source) {
        $sourceUri = [System.Uri]$Source
        $manifestPath = $sourceUri.LocalPath
    } else {
        $manifestPath = Resolve-FullPath $Source
    }

    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "Update manifest not found: $manifestPath"
    }
    return Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
}

function Assert-ManifestField {
    param(
        [object]$Manifest,
        [string]$Name
    )
    $value = $Manifest.$Name
    if ($null -eq $value -or -not ([string]$value).Trim()) {
        throw "Update manifest is missing required field: $Name"
    }
}

function ConvertTo-VersionParts {
    param([string]$VersionValue)
    $normalized = (($VersionValue.Trim() -replace "^v", "") -split "[-+]")[0]
    if (-not $normalized) {
        $normalized = "0"
    }
    $parts = @()
    foreach ($part in $normalized.Split(".")) {
        if ($part -notmatch "^\d+$") {
            throw "Version segment is not numeric: $VersionValue"
        }
        $parts += [int]$part
    }
    while ($parts.Count -lt 3) {
        $parts += 0
    }
    return $parts
}

function Compare-Version {
    param(
        [string]$Left,
        [string]$Right
    )
    $leftParts = ConvertTo-VersionParts -VersionValue $Left
    $rightParts = ConvertTo-VersionParts -VersionValue $Right
    $maxParts = [Math]::Max($leftParts.Count, $rightParts.Count)
    for ($index = 0; $index -lt $maxParts; $index++) {
        $leftPart = if ($index -lt $leftParts.Count) { $leftParts[$index] } else { 0 }
        $rightPart = if ($index -lt $rightParts.Count) { $rightParts[$index] } else { 0 }
        if ($leftPart -lt $rightPart) {
            return -1
        }
        if ($leftPart -gt $rightPart) {
            return 1
        }
    }
    return 0
}

function Get-InstalledDirectory {
    if ($InstallDir.Trim()) {
        return Resolve-FullPath $InstallDir
    }
    if (Test-Path -LiteralPath $UninstallRegistryKey) {
        try {
            $registeredPath = [string](Get-ItemProperty -Path $UninstallRegistryKey -Name "InstallLocation" -ErrorAction Stop).InstallLocation
            if ($registeredPath.Trim()) {
                return Resolve-FullPath $registeredPath
            }
        } catch {
            return ""
        }
    }
    return Join-Path $env:LOCALAPPDATA "Programs\GithubSearchDownloader"
}

function Get-InstalledVersion {
    if ($CurrentVersion.Trim()) {
        return $CurrentVersion.Trim()
    }
    if (Test-Path -LiteralPath $UninstallRegistryKey) {
        try {
            $registryVersion = [string](Get-ItemProperty -Path $UninstallRegistryKey -Name "DisplayVersion" -ErrorAction Stop).DisplayVersion
            if ($registryVersion.Trim()) {
                return $registryVersion.Trim()
            }
        } catch {
            $null = $_
        }
    }

    $installedDir = Get-InstalledDirectory
    if ($installedDir.Trim()) {
        $installManifest = Join-Path $installedDir "install_manifest.json"
        if (Test-Path -LiteralPath $installManifest -PathType Leaf) {
            try {
                $manifest = Get-Content -LiteralPath $installManifest -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($manifest.version -and ([string]$manifest.version).Trim()) {
                    return ([string]$manifest.version).Trim()
                }
            } catch {
                $null = $_
            }
        }
    }
    return "0.0.0"
}

function Resolve-DownloadLocation {
    param(
        [string]$ManifestSource,
        [string]$DownloadValue
    )

    $downloadUri = $null
    if ([System.Uri]::TryCreate($DownloadValue, [System.UriKind]::Absolute, [ref]$downloadUri)) {
        if ($downloadUri.Scheme -eq "file") {
            return $downloadUri.LocalPath
        }
        return $downloadUri.AbsoluteUri
    }

    if (Test-HttpUrl -Value $ManifestSource) {
        $manifestUri = [System.Uri]$ManifestSource
        return ([System.Uri]::new($manifestUri, $DownloadValue)).AbsoluteUri
    }

    if (Test-FileUrl -Value $ManifestSource) {
        $manifestUri = [System.Uri]$ManifestSource
        $manifestPath = $manifestUri.LocalPath
    } else {
        $manifestPath = Resolve-FullPath $ManifestSource
    }
    return Resolve-FullPath (Join-Path (Split-Path -Parent $manifestPath) $DownloadValue)
}

function Get-PackageFileName {
    param(
        [object]$Manifest,
        [string]$DownloadLocation
    )
    if ($Manifest.package_name -and ([string]$Manifest.package_name).Trim()) {
        return [System.IO.Path]::GetFileName([string]$Manifest.package_name)
    }
    $locationUri = $null
    if ([System.Uri]::TryCreate($DownloadLocation, [System.UriKind]::Absolute, [ref]$locationUri) -and $locationUri.Scheme -in @("https", "http")) {
        return [System.IO.Path]::GetFileName($locationUri.AbsolutePath)
    }
    return [System.IO.Path]::GetFileName($DownloadLocation)
}

function Copy-Or-DownloadPackage {
    param(
        [string]$DownloadLocation,
        [string]$DestinationPath
    )

    $partialPath = "$DestinationPath.partial"
    if (Test-Path -LiteralPath $partialPath) {
        Remove-Item -LiteralPath $partialPath -Force
    }
    if (Test-HttpUrl -Value $DownloadLocation) {
        Invoke-WebRequest -Uri $DownloadLocation -OutFile $partialPath -UseBasicParsing
        Move-Item -LiteralPath $partialPath -Destination $DestinationPath -Force
        return
    }

    $sourcePath = Resolve-FullPath $DownloadLocation
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Update package not found: $sourcePath"
    }
    if ((Resolve-FullPath $DestinationPath) -ne $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination $partialPath -Force
        Move-Item -LiteralPath $partialPath -Destination $DestinationPath -Force
    }
}

function Assert-FileSize {
    param(
        [string]$PathValue,
        [object]$ExpectedSize,
        [string]$Label
    )
    if ($null -eq $ExpectedSize -or -not ([string]$ExpectedSize).Trim()) {
        return
    }
    $expected = [int64]$ExpectedSize
    $actual = (Get-Item -LiteralPath $PathValue).Length
    if ($actual -ne $expected) {
        throw "$Label size mismatch. Expected='$expected' Actual='$actual'"
    }
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

function Assert-Hash {
    param(
        [string]$PathValue,
        [string]$ExpectedSha256,
        [string]$Label
    )
    $actual = Get-Sha256 -PathValue $PathValue
    $expected = $ExpectedSha256.Trim().ToUpperInvariant()
    if ($actual -ne $expected) {
        throw "$Label SHA256 mismatch. Expected='$expected' Actual='$actual'"
    }
    return $actual
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

function Assert-SafeZipEntries {
    param(
        [string]$ZipPath,
        [string[]]$RequiredEntries
    )

    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entries = @{}
        foreach ($entry in $zip.Entries) {
            $normalizedName = $entry.FullName.Replace("\", "/")
            if (-not $normalizedName.Trim()) {
                continue
            }
            if ($normalizedName.StartsWith("/", [System.StringComparison]::Ordinal) -or
                $normalizedName.StartsWith("\", [System.StringComparison]::Ordinal) -or
                [System.IO.Path]::IsPathRooted($entry.FullName)) {
                throw "Unsafe update package entry path: $($entry.FullName)"
            }
            foreach ($segment in $normalizedName.Split("/")) {
                if ($segment -eq "..") {
                    throw "Unsafe update package entry path: $($entry.FullName)"
                }
            }
            $entries[$normalizedName] = $true
        }
        foreach ($requiredEntry in $RequiredEntries) {
            if (-not $entries.ContainsKey($requiredEntry)) {
                throw "Update package is missing required entry: $requiredEntry"
            }
        }
    }
    finally {
        $zip.Dispose()
    }
}

function Invoke-VerifiedInstall {
    param(
        [string]$InstallerPath
    )
    $installArgs = @{}
    if ($InstallDir.Trim()) {
        $installArgs["InstallDir"] = $InstallDir
    }
    if ($DesktopShortcut) {
        $installArgs["DesktopShortcut"] = $true
    }
    & $InstallerPath @installArgs
}

$ManifestSource = Get-ManifestSource
$Manifest = Read-UpdateManifest -Source $ManifestSource

foreach ($fieldName in @("product", "latest_version", "download_url", "package_sha256")) {
    Assert-ManifestField -Manifest $Manifest -Name $fieldName
}
if ([string]$Manifest.product -ne $ProductName) {
    throw "Unexpected update manifest product: $($Manifest.product)"
}

$installedVersion = Get-InstalledVersion
$latestVersion = [string]$Manifest.latest_version
$comparison = Compare-Version -Left $installedVersion -Right $latestVersion
$updateAvailable = ($comparison -lt 0) -or $Force

$result = [ordered]@{
    product = $ProductName
    current_version = $installedVersion
    latest_version = $latestVersion
    update_available = $updateAvailable
    forced = [bool]$Force
    manifest_source = $ManifestSource
    download_url = [string]$Manifest.download_url
    package_sha256 = [string]$Manifest.package_sha256
    uninstall_registry_key = $UninstallRegistrySubkey
    downloaded = $false
    installed = $false
    signature_status = ""
    package_path = ""
    extract_dir = ""
}

if (-not $updateAvailable) {
    $result["message"] = "Already current."
    $result | ConvertTo-Json -Depth 5
    return
}

if (-not $DownloadOnly -and -not $Install) {
    $result["message"] = "Update is available. Re-run with -DownloadOnly to verify the package or -Install to install it."
    $result | ConvertTo-Json -Depth 5
    return
}

if (-not $DownloadDir.Trim()) {
    $DownloadDir = Join-Path $env:LOCALAPPDATA "GithubSearchDownloader\Updates"
}
$resolvedDownloadDir = Resolve-FullPath $DownloadDir
New-Item -ItemType Directory -Force -Path $resolvedDownloadDir | Out-Null

$downloadLocation = Resolve-DownloadLocation -ManifestSource $ManifestSource -DownloadValue ([string]$Manifest.download_url)
$packageName = Get-PackageFileName -Manifest $Manifest -DownloadLocation $downloadLocation
if (-not $packageName.Trim()) {
    throw "Could not determine update package file name."
}
$packagePath = Join-Path $resolvedDownloadDir $packageName
Assert-ChildPath -Parent $resolvedDownloadDir -Child $packagePath
Assert-ChildPath -Parent $resolvedDownloadDir -Child "$packagePath.partial"

Copy-Or-DownloadPackage -DownloadLocation $downloadLocation -DestinationPath $packagePath
Assert-FileSize -PathValue $packagePath -ExpectedSize $Manifest.package_size_bytes -Label "Package"
$packageHash = Assert-Hash -PathValue $packagePath -ExpectedSha256 ([string]$Manifest.package_sha256) -Label "Package"

$releaseName = if ($Manifest.release_name -and ([string]$Manifest.release_name).Trim()) { [string]$Manifest.release_name } else { [System.IO.Path]::GetFileNameWithoutExtension($packageName) }
$installScript = if ($Manifest.install_script -and ([string]$Manifest.install_script).Trim()) { [string]$Manifest.install_script } else { "install_windows.ps1" }
$updateScript = if ($Manifest.update_script -and ([string]$Manifest.update_script).Trim()) { [string]$Manifest.update_script } else { "check_updates_windows.ps1" }
$requiredZipEntries = @(
    "GithubSearchDownloader.exe",
    [System.IO.Path]::GetFileName($installScript),
    [System.IO.Path]::GetFileName($updateScript)
)
Assert-SafeZipEntries -ZipPath $packagePath -RequiredEntries $requiredZipEntries

$extractDir = Join-Path $resolvedDownloadDir "$releaseName-extracted"
Assert-ChildPath -Parent $resolvedDownloadDir -Child $extractDir
if (Test-Path -LiteralPath $extractDir) {
    Remove-Item -LiteralPath $extractDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
Expand-Archive -LiteralPath $packagePath -DestinationPath $extractDir -Force

$extractedExe = Join-Path $extractDir "GithubSearchDownloader.exe"
if (-not (Test-Path -LiteralPath $extractedExe -PathType Leaf)) {
    throw "Update package is missing GithubSearchDownloader.exe."
}
if ($Manifest.executable_sha256 -and ([string]$Manifest.executable_sha256).Trim()) {
    $null = Assert-Hash -PathValue $extractedExe -ExpectedSha256 ([string]$Manifest.executable_sha256) -Label "Executable"
}

$installerPath = Join-Path $extractDir ([System.IO.Path]::GetFileName($installScript))
$updaterPath = Join-Path $extractDir ([System.IO.Path]::GetFileName($updateScript))
foreach ($requiredPath in @($installerPath, $updaterPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
        throw "Update package is missing required script: $([System.IO.Path]::GetFileName($requiredPath))"
    }
}

$signature = Get-ReleaseSignature -PathValue $extractedExe
$result["signature_status"] = [string]$signature.Status
if (($RequireSignature -or [bool]$Manifest.signed) -and $signature.Status -ne "Valid") {
    throw "Update package signature gate failed. Authenticode status: $($signature.Status)"
}

$result["downloaded"] = $true
$result["package_path"] = $packagePath
$result["package_sha256"] = $packageHash
$result["extract_dir"] = $extractDir

if ($Install) {
    Invoke-VerifiedInstall -InstallerPath $installerPath
    $result["installed"] = $true
}

$result["message"] = if ($Install) { "Update installed." } else { "Update package downloaded and verified." }
$result | ConvertTo-Json -Depth 5
