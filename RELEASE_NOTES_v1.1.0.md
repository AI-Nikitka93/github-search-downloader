# 🚀 GitHub Search & Downloader v1.1.0

Welcome to **v1.1.0**! This major release transforms the application into an out-of-the-box Windows software package featuring a 1-click Onboarding Wizard, In-App Self-Updater, Live Status Monitoring, and enhanced security hardening.

---

### 📥 Downloads

| Asset | Description | Size | Checksum |
| :--- | :--- | :--- | :--- |
| 💿 **[`GithubSearchDownloader-v1.1.0-windows-x64-setup.exe`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/GithubSearchDownloader-v1.1.0-windows-x64-setup.exe)** | **Windows Setup Installer** (Creates Start Menu & Desktop shortcuts) | ~14.2 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/checksums.sha256) |
| 📦 **[`GithubSearchDownloader-1.1.0-windows-x64.zip`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/GithubSearchDownloader-1.1.0-windows-x64.zip)** | **Portable Standalone ZIP** (Extract and run `GithubSearchDownloader.exe`) | ~13.7 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/checksums.sha256) |
| 🛡️ **[`checksums.sha256`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/checksums.sha256)** | SHA-256 integrity checksums for all binary release assets | ~200 B | — |

---

### ✨ What's New in v1.1.0

#### 1. 🧙‍♂️ 4-Step First-Run Onboarding Wizard
- **1-Click GitHub Authentication**: OAuth Device Code Flow (automatically copies user verification code to clipboard via `clip.exe` and polls in background).
- **Workspace & Storage Selection**: Smart workspace picker with real-time disk space probe.
- **AI Intelligence Setup**: Auto-detects local **Ollama** instances (`http://localhost:11434`) and lists installed models (`llama3.2`, `mistral`, etc.), or provides cloud API key inputs (**DeepSeek / OpenAI**) with DPAPI storage.
- **Quick-Search Presets**: 1-click popular search templates ("AI Libraries", "Web Crawlers", "Telegram Bots").

#### 2. 🔄 Built-in In-App Auto-Updater
- Real-time GitHub Releases update checker with rate-limit-safe 24-hour ETag caching (`304 Not Modified`).
- Interactive changelog viewer and 1-click atomic self-update script (`apply_update.bat`).
- Full CLI support via `python app.py --version` and `python app.py --check-updates`.

#### 3. 📊 Live Status Bar & App Menu
- Top header pill bar displaying:
  - 🟢 GitHub user handle and remaining API quota (e.g. `4998/5000`);
  - 🤖 AI provider state (`Ollama: llama3.2` / `OpenAI: Connected`);
  - 💾 Real-time disk free space monitoring.
- Native application menu: `Help -> About`, `Help -> Check for Updates...`, `Help -> First-Run Wizard...`.

#### 4. 🤖 AI Repomix XML Exporter
- Packages entire repository file trees into structured XML documents for instant ingestion into LLM context windows.

#### 5. 🛡️ Security Hardening
- **CWE-59**: Recursive symlink loop prevention and boundary verification.
- **CWE-88**: Added `--` argument separator before remote URLs in `git clone` invocations.
- **CWE-1236**: CSV/Excel Formula & DDE injection sanitization (`=`, `+`, `-`, `@`, `\t`, `\r`).
- **Encrypted Storage**: DPAPI protection (`CryptProtectData`) for all personal access tokens and API keys.

---

### 💻 System Requirements
- **OS**: Windows 10 / Windows 11 (64-bit)
- **Dependencies**: [Git for Windows](https://git-scm.com/download/win) (for repository cloning)

---

<details>
<summary><b>🇷🇺 Описание релиза на русском языке (Russian Translation)</b></summary>

### 🚀 GitHub Search & Downloader v1.1.0 (Русская версия)

Добро пожаловать в версию **v1.1.0**! Этот релиз превращает приложение в полноценный автономный программный продукт с удобным мастером быстрой настройки, встроенным автообновлением и расширенной безопасностью.

#### 📥 Ссылки на загрузку:
- 💿 **[Установщик Windows (Setup.exe)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/GithubSearchDownloader-v1.1.0-windows-x64-setup.exe)** (~14.2 MB)
- 📦 **[Портативный архив (Portable.zip)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/GithubSearchDownloader-1.1.0-windows-x64.zip)** (~13.7 MB)
- 🛡️ **[Контрольные суммы (checksums.sha256)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.0/checksums.sha256)**

#### ✨ Ключевые изменения:
1. **Мастер первого запуска**: 4-шаговый интерактивный мастер настройки при первом запуске (вход через GitHub в 1 клик, автопоиск Ollama / ввод ключей DeepSeek/OpenAI, выбор папки с контролем места на диске).
2. **Система автообновлений**: Встроенная проверка новых релизов через GitHub API с обновлением в 1 клик.
3. **Статус-бар в шапке окна**: Отображение лимитов API, статуса AI и свободного места на диске.
4. **Экспорт для AI (XML)**: Упаковка репозитория в формат Repomix для передачи в контекст нейросетей.
5. **Безопасность**: Защита от symlink-петель (CWE-59), инъекций аргументов (CWE-88), формул Excel (CWE-1236) и шифрование через Windows DPAPI.

</details>
