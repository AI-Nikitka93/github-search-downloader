---
status: accepted
date: 2026-03-22
deciders: Nikita Kizevich
consulted: Packaging & Security Architecture
informed: Core Engineering
---

# ADR-0020: Verifiable Windows Release Package Workflow

## Context and Problem Statement

Distributing standalone Windows desktop executables (`.exe`) without provenance manifests, cryptographic checksums, or automated verification scripts makes it impossible for users, enterprise security auditors, and update engines to verify artifact integrity. Furthermore, installers that require administrator rights create deployment friction, and unverified in-place auto-updaters pose supply-chain risks. How should Windows releases be built, packaged, and verified?

## Decision Drivers

- Cryptographically verifiable release packages with SHA-256 manifests.
- Pre-publish verification gate script (`verify_release_windows.ps1`) for QA and CI.
- Per-user installation without requiring local administrator privileges.
- Atomic updater with size, checksum, and signature checks.

## Considered Options

1. **Manifest-Driven PowerShell Packaging & Verification Pipeline**: Implement `release_windows.ps1` to stage artifacts, compute SHA-256 via .NET, generate `SHA256SUMS.txt`, `release_manifest.json`, and `update_manifest.json`; provide `install_windows.ps1` (per-user with product markers) and `verify_release_windows.ps1` as strict integrity gates.
2. **Ad-Hoc Zip Packaging**: Manually zip PyInstaller output without manifests or hash files.
3. **Heavyweight MSI / InstallShield Setup**: Package as an administrative MSI installer.

## Decision Outcome

Chosen option: **Manifest-Driven PowerShell Packaging & Verification Pipeline**.

### Positive Consequences
- Guarantees 100% reproducible and auditable Windows release artifacts.
- Clear distinction between unsigned builds, installer-ready packages, and signed Authenticode public releases.
- Updater strictly validates `.partial` downloads against manifest hashes and sizes before replacing binaries.
- Safe per-user uninstaller requiring GithubSearchDownloader product markers before directory removal.

### Negative Consequences
- Requires maintaining PowerShell release and verification scripts alongside Python codebase.
