# 🚀 GitHub Search & Downloader v0.0.1 (Beta 1)

Welcome to the first official public beta release of **GitHub Search & Downloader** (0.0.1)!  
A state-of-the-art Windows desktop application and CLI designed for high-speed GitHub discovery, multi-provider AI relevance filtering, and massive parallel repository downloads.

---

### 📥 Download Assets

| File | Description | Size | SHA-256 |
| :--- | :--- | :--- | :--- |
| 💿 **[GithubSearchDownloader-v0.0.1-windows-x64-setup.exe](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/GithubSearchDownloader-v0.0.1-windows-x64-setup.exe)** | **Windows Setup Installer** (Start Menu & Desktop shortcuts, in-place upgrade, Add/Remove Programs) | ~14.3 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/checksums.sha256) |
| 📦 **[GithubSearchDownloader-0.0.1-windows-x64.zip](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/GithubSearchDownloader-0.0.1-windows-x64.zip)** | **Portable Standalone Package** (Extract anywhere & run GithubSearchDownloader.exe) | ~17.0 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/checksums.sha256) |
| 🛡️ **[checksums.sha256](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/checksums.sha256)** | SHA-256 cryptographic verification file | ~200 B | — |

---

### ✨ Key Features in v0.0.1 Beta

#### 1. 🎨 Modern 2026 UI Design System
* **Windows 11 DWM Chrome**: Native immersive dark titlebars and rounded window corners via Win32 API.
* **Exclusive 3D Octocat Cyber Mascot**: Custom 3D Octocat with antenna, radar, and glowing AI core.
* **Component Suite**: Elevated CardFrame containers (#161B22), live PillBadge indicators, and modern zebra-striped tables.

#### 2. 🧠 Universal Multi-Provider AI Engine
* **Instant Key Auto-Detection**: Automatically detects key formats for:
  * 🌐 **OpenRouter** (sk-or-v1-...) — 400+ models with :free highlighting
  * ⚡ **Groq** (gsk_...) — ultra-fast Llama 3.3 70B & DeepSeek R1
  * 🟢 **NVIDIA NIM** (
vapi-...) — NVIDIA Build Llama 3.1 / Nemotron
  * 🌪️ **Mistral AI** (hexadecimal API key) — Codestral & Mistral Large
  * 🏠 **Ollama** (Local private AI) — auto-discovery on http://127.0.0.1:11434
  * 🐋 **DeepSeek** (sk-...) & OpenAI-compatible endpoints
* **Live Model Discovery**: 1-click test button queries provider endpoints and populates real model catalogs.

#### 3. 🔑 1-Click GitHub Authentication (OAuth Device Flow)
* Instant authentication via github.com/login/device with automatic clipboard code copying.
* Raises API limits from 60 to **5,000 requests/hour**.
* Fallback import from GitHub CLI (gh auth token) and manual Personal Access Token (PAT).

#### 4. 🛡️ Windows DPAPI Military-Grade Security
* Tokens and API keys encrypted using Windows Data Protection API (CryptProtectData) tied to user credentials.
* Zero plaintext key leaks in logs or files.

#### 5. 🔍 Date-Sharding GitHub Search Engine
* Automatically partitions wide date intervals into smaller shards.
* Completely bypasses GitHub's 1,000-search-results ceiling.

#### 6. 🔄 Complete Installation & Lifecycle Management
* **Setup Installer**: Per-user %LOCALAPPDATA%\Programs\GithubSearchDownloader install without UAC requirements.
* **In-Place Upgrades**: Gracefully shuts down running instances (GithubSearchDownloaderAppMutex) and overwrites binaries.
* **Clean Uninstaller**: Dedicated Start Menu uninstaller and Windows Control Panel integration.
* **In-App Self-Updater**: 1-Click update checking and automated replacement from GitHub Releases.

---

### 🇷🇺 Описание релиза (на русском)

Первый официальный публичный релиз **GitHub Search & Downloader (v0.0.1 Beta 1)**.

- 💿 **[Установщик Windows (Setup.exe)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/GithubSearchDownloader-v0.0.1-windows-x64-setup.exe)** (~14.3 MB)
- 📦 **[Портативный архив (Portable.zip)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/GithubSearchDownloader-0.0.1-windows-x64.zip)** (~13.8 MB)
- 🛡️ **[Контрольные суммы SHA-256](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v0.0.1/checksums.sha256)**

---

**Developed by Nikita Kizevich (@AI-Nikitka93)**  
*September 2026*
