# Changelog

All notable changes to the **GitHub Search & Downloader** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

---

## [1.1.0] — 2026-09-01

### 🚀 Added
- **First-Run Onboarding Wizard**: 4-step interactive onboarding modal:
  - 1-click authentication via GitHub OAuth Device Code Flow (with auto-clipboard copy of user code via `clip.exe`).
  - Storage & workspace directory selection with real-time free disk space probe.
  - Automatic detection of local Ollama server (`http://localhost:11434`) and installed models (`llama3.2`, `mistral`), or secure cloud API key entry (DeepSeek / OpenAI).
  - Quick-start search presets in 1 click.
- **Header Status Widget**: Live status pill bar showing GitHub user handle, remaining API request quota (e.g. `4998/5000`), AI provider status, and free disk space.
- **In-App Self-Updater Engine**:
  - GitHub Releases API integration with 24-hour ETag rate-limit caching (`304 Not Modified`).
  - Interactive changelog viewer and 1-click self-update execution (`UpdateCheckerDialog`).
  - Non-blocking detached Windows batch helper (`apply_update.bat`) for atomic binary replacement.
  - CLI commands `--version` and `--check-updates`.
- **AI Repomix XML Exporter**: Formats entire repository source code and trees into a structured XML format for LLM context ingestion.
- **Application Menu Bar**: Added native menus (`Help -> About`, `Help -> Check for Updates...`, `Help -> First-Run Wizard...`).

### 🔒 Security Hardening
- **CWE-59 (Symlink Traversal)**: Cycle prevention and canonical path boundary checks in repository tree mapping.
- **CWE-88 (Command Argument Injection)**: Added `--` argument separator before remote URLs in `git clone`.
- **CWE-1236 (CSV Formula / DDE Injection)**: Automatic sanitization of dangerous leading spreadsheet characters (`=`, `+`, `-`, `@`, `\t`, `\r`).
- **Zip-Slip & Windows DOS Device Protection**: Validates update archives against relative traversals (`..`), absolute drive paths (`C:`), and DOS reserved device names (`CON`, `NUL`, `COM1..9`, `LPT1..9`).
- **Encrypted Secret Storage**: Hardened Windows DPAPI storage for personal access tokens and cloud AI keys.

### 📦 Packaging & CI/CD
- Inno Setup 6 script (`packaging/installer.iss`) for generating Windows Setup installers.
- GitHub Actions workflow (`.github/workflows/release.yml`) for automated builds on tag push `v*.*.*`.
- Automated generation of SHA-256 integrity manifests (`checksums.sha256` and `SHA256SUMS.txt`).

---

## [1.0.1] — 2026-08-15

### 🛠 Fixed
- Graceful recovery and backoff for GitHub Search API secondary rate limits (`403 Secondary Rate Limit`).
- Automatic recursive date-range bisection when shard results exceed 1,000 repositories.

---

## [1.0.0] — 2026-08-01

### 🎉 Initial Release
- Desktop GUI built with Tkinter and `sv_ttk` (light/dark themes).
- Date-sharded search algorithm overcoming GitHub's 1,000-result search limit.
- Multi-threaded parallel downloader with shallow (`--depth 1`) and partial (`--filter=blob:none`) cloning.
- AI-assisted relevance evaluation via Ollama and OpenAI-compatible endpoints.
- Multi-format metadata export to JSON, CSV, and SQLite.
