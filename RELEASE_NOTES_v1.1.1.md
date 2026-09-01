# 🚀 GitHub Search & Downloader v1.1.1

Welcome to **v1.1.1**! This release brings critical stability improvements, non-blocking clipboard copying, seamless in-place installation upgrades, NTFS file-locking resilience, and memory hardening.

---

### 📥 Downloads

| Asset | Description | Size | Checksum |
| :--- | :--- | :--- | :--- |
| 💿 **[`GithubSearchDownloader-v1.1.1-windows-x64-setup.exe`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/GithubSearchDownloader-v1.1.1-windows-x64-setup.exe)** | **Windows Setup Installer** (Automatically detects & upgrades existing versions) | ~14.2 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/checksums.sha256) |
| 📦 **[`GithubSearchDownloader-1.1.1-windows-x64.zip`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/GithubSearchDownloader-1.1.1-windows-x64.zip)** | **Portable Standalone ZIP** (Extract and run `GithubSearchDownloader.exe`) | ~13.7 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/checksums.sha256) |
| 🛡️ **[`checksums.sha256`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/checksums.sha256)** | SHA-256 integrity checksums for all release binaries | ~200 B | — |

---

### ✨ What's New & Fixed in v1.1.1

#### 1. ⚡ Non-Blocking 64-bit Clipboard Engine
- Replaced synchronous `clip.exe` subprocess execution with a native 64-bit Win32 API clipboard module (`src/github_harvester/clipboard.py`).
- All clipboard copy actions run asynchronously in a dedicated daemon thread, eliminating GUI freezes and window stutters when copying OAuth codes.

#### 2. 🔄 Seamless In-Place Upgrades
- The Inno Setup installer now binds to `AppMutex=GithubSearchDownloaderAppMutex`, automatically detects running instances of the app, closes them cleanly (`CloseApplications=force`), overwrites older binaries (`ignoreversion restartreplace`), and cleans legacy registry keys without creating duplicate directories.
- The PowerShell installer script stops running processes and includes a 5-attempt retry loop to overcome transient antivirus file locks.

#### 3. 🛡️ Windows NTFS Read-Only File Removal
- Added `safe_rmtree_windows` with automated `stat.S_IWRITE` attribute stripping to cleanly remove locked `.git/objects` packfiles on failed or cancelled clones.

#### 4. 🤖 AI Repomix Exporter Memory & Path Hardening
- Normalized XML file path delimiters to POSIX slashes (`/`).
- Added per-file size cap (1 MB) and total repository export cap (25 MB) with truncation notices to prevent out-of-memory crashes on giant repositories.

#### 5. ⏱️ Cancellable OAuth Device Flow
- Added granular `cancel_event` support to `poll_for_token`, instantly terminating background polling when closing or skipping the wizard.

---

### 💻 System Requirements
- **OS**: Windows 10 / Windows 11 (64-bit)
- **Dependencies**: [Git for Windows](https://git-scm.com/download/win) (for repository cloning)

---

<details>
<summary><b>🇷🇺 Описание релиза на русском языке (Russian Translation)</b></summary>

### 🚀 GitHub Search & Downloader v1.1.1 (Русская версия)

Версия **v1.1.1** устраняет зависания при копировании в буфер обмена, настраивает бесшовное обновление поверх существующей версии и повышает общую стабильность системы.

#### 📥 Ссылки на загрузку:
- 💿 **[Установщик Windows (Setup.exe)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/GithubSearchDownloader-v1.1.1-windows-x64-setup.exe)** (~14.2 MB)
- 📦 **[Портативный архив (Portable.zip)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/GithubSearchDownloader-1.1.1-windows-x64.zip)** (~13.7 MB)
- 🛡️ **[Контрольные суммы (checksums.sha256)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.1/checksums.sha256)**

#### ✨ Ключевые исправления:
1. **Устранено зависание при копировании кода**: внедрен прямой 64-битный Win32 API для работы с буфером обмена в фоновом потоке. Окно программы больше не зависает при нажатии «Скопировать код».
2. **Бесшовное обновление поверх установленной версии**: установщик Inno Setup и скрипт установки теперь автоматически обнаруживают запущенную копию программы, корректно закрывают ее и перезаписывают файлы без конфликтов и дублирования папок.
3. **Надежная очистка NTFS**: функция `safe_rmtree_windows` автоматически снимает атрибут «Только для чтения» с файлов `.git`, предотвращая ошибки удаления.
4. **Защита памяти при экспорте для ИИ**: ограничение размера файлов (1 МБ) и общего объема (25 МБ) для предотвращения нехватки памяти (OOM), а также приведение путей к стандарту POSIX (`/`).
5. **Мгновенная отмена авторизации**: закрытие окна мастера теперь сразу останавливает фоновый опрос сервера GitHub.

</details>
