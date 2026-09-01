# Security Policy

## Supported Versions

| Version | Supported          | Security Maintenance Status |
| ------- | ------------------ | --------------------------- |
| 0.0.x   | :white_check_mark: | Active (Current Beta)       |

## Reporting a Vulnerability

We take the security of GitHub Search Downloader seriously. If you discover a potential vulnerability, **do not open a public issue or discussion**.

### Reporting Process
1. Email your findings directly to **security@github-search-downloader.local** (or submit via GitHub Private Vulnerability Reporting on the repository if enabled).
2. Include:
   - Type of vulnerability (e.g., secret leakage, process injection, path traversal).
   - Step-by-step reproduction instructions or proof-of-concept.
   - Impact assessment and potential attack vectors.
   - Affected versions and environment (Windows version, Python runtime).
3. We will acknowledge receipt within 48 business hours and provide an estimated remediation timeline.

---

## Security Architecture & Threat Model

### 1. Secret Protection & Windows DPAPI (Zero Plaintext)
- **Zero Plaintext Storage:** GitHub personal access tokens and cloud AI API keys are never stored in plaintext within configuration files (`gui_settings.json`), CLI arguments history, or application logs.
- **Cryptographic Isolation:** Secrets are encrypted using the Windows Data Protection API (DPAPI) via `CryptProtectData` and stored under `%LOCALAPPDATA%\GithubSearchDownloader\secrets`. Decryption (`CryptUnprotectData`) is strictly bound to the local Windows user session.
- **Log Masking:** Application and debug logs automatically redact authorization headers, token prefixes (`ghp_`, `gho_`, `ghu_`, `ghs_`, `github_pat_`), and URL credentials.

### 2. Modern GitHub Token Architecture (2026 Standards)
- **Variable-Length Buffer Compliance:** Storage and memory buffers for authentication tokens support variable-length strings up to **520+ characters** to accommodate modern GitHub App and installation token formats (`ghs_APPID_JWT`).
- **No Hardcoded Regex Assumptions:** Token validation does not enforce obsolete 36-character fixed-length patterns.
- **Least-Privilege Recommendation:** Tokens should only be granted `public_repo` (read-only) scope for standard harvesting operations.

### 3. Process Execution & Subprocess Isolation
- **Path Traversal & Device Name Protection:** Target repository paths and folder segments are sanitized against Windows reserved device names (`CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9`) and invalid filename characters.
- **Hard Process Tree Termination:** Git clone operations are monitored with strict timeouts and terminated using Windows process-tree signals (`taskkill /T /F`) to prevent rogue subprocess hangs.

### 4. Supply Chain & Release Verification
- **SHA-256 Manifest Verification:** Official releases provide `SHA256SUMS.txt`, `release_manifest.json`, and `update_manifest.json`.
- **Integrity Validation:** The included `verify_release_windows.ps1` script validates zip archive contents, file hashes, and Authenticode signatures prior to installation or update execution.
