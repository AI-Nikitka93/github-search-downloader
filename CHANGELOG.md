# Changelog

All notable changes to the **GitHub Search & Downloader** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

---

## [1.1.2] — 2026-09-01

### 🚀 Added & Enhanced
- **Universal Multi-Provider AI Engine**:
  - Full support for **OpenRouter**, **Groq**, **NVIDIA NIM**, **Mistral AI**, **LLM7.io**, **DeepSeek**, **Cloudflare Workers AI**, **Ollama Cloud/Local**, and **OpenAI**.
  - **Intelligent Key Auto-Detection**: Automatically identifies provider and Base URL when pasting keys (`sk-or-v1-` -> OpenRouter, `gsk_` -> Groq, `nvapi-` -> NVIDIA NIM, `cfut_` -> Cloudflare, `sk-` -> DeepSeek/OpenAI, 32-char hex -> Mistral AI).
  - **Live Asynchronous Model Discovery**: Dynamically queries `/v1/models` and provider APIs without blocking the GUI.
  - **Free Models Highlighting & Filtering**: Automatically tags and sorts `:free` and 0-cost models (`[FREE] meta-llama/llama-3.3-70b-instruct:free`, `[FREE] deepseek/deepseek-r1:free`, `[FREE] qwen/qwen-2.5-72b-instruct:free`) with a 1-click filter checkbox.
  - **Smart Error Diagnostics**: Informative status badges explaining exact failure causes (e.g. 401 Unauthorized, 403 Forbidden with VPN tips for Groq, 429 Rate Limits, Connection Refused).
  - Integrated into both **First-Run Onboarding Wizard (Step 3)** and **Main AI Settings Tab**.

---

## [1.1.1] — 2026-09-01

### 🛠 Fixed & Hardened
- **Non-Blocking Clipboard Engine**: Implemented 64-bit type-safe Win32 API clipboard bindings (`src/github_harvester/clipboard.py`) with async daemon executor, eliminating UI freezes when clicking "Copy Code".
- **Seamless In-Place Upgrades**:
  - Inno Setup detects running instances (`AppMutex=GithubSearchDownloaderAppMutex`), closes them automatically (`CloseApplications=force`), cleanly overwrites files (`ignoreversion restartreplace`), and cleans legacy registry keys.
  - PowerShell installer stops running processes with polling wait before copying.
- **NTFS Read-Only Deletion Resilience**: Added `safe_rmtree_windows` with `os.chmod(..., stat.S_IWRITE)` retry handlers to cleanly delete locked git packfiles.
- **AI Repomix Exporter Hardening**:
  - Normalized path delimiters to standard POSIX slashes (`/`).
  - Added per-file size cap (1 MB) and total repository export cap (25 MB) with truncation notices to prevent out-of-memory crashes.
- **Cancellable OAuth Device Flow**: Added `cancel_event` support to `poll_for_token` so closing or skipping the wizard immediately terminates background network polling.
- **Auto-Updater Batch Hardening**: Configured `apply_update.bat` with `chcp 65001` UTF-8 codepage, `robocopy` with retry, and fallback `taskkill` process termination.

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
