# 🚀 GitHub Search & Downloader v1.1.2

Welcome to **v1.1.2**! This release introduces a **Universal Multi-Provider AI Engine** with instant key auto-detection, live model discovery, and free models highlighting across all major AI providers.

---

### 📥 Downloads

| Asset | Description | Size | Checksum |
| :--- | :--- | :--- | :--- |
| 💿 **[`GithubSearchDownloader-v1.1.2-windows-x64-setup.exe`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/GithubSearchDownloader-v1.1.2-windows-x64-setup.exe)** | **Windows Setup Installer** (Auto-replaces older versions) | ~14.2 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/checksums.sha256) |
| 📦 **[`GithubSearchDownloader-1.1.2-windows-x64.zip`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/GithubSearchDownloader-1.1.2-windows-x64.zip)** | **Portable Standalone ZIP** (Extract and run `GithubSearchDownloader.exe`) | ~13.7 MB | [Verify](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/checksums.sha256) |
| 🛡️ **[`checksums.sha256`](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/checksums.sha256)** | SHA-256 integrity checksums for all release binaries | ~200 B | — |

---

### ✨ What's New in v1.1.2

#### 1. 🧠 Universal Multi-Provider AI Engine
- Native support for:
  - **OpenRouter** (`https://openrouter.ai/api/v1` - 400+ models, with `:free` models highlighted)
  - **Groq** (`https://api.groq.com/openai/v1` - Ultra-fast Llama 3.3, Mixtral)
  - **NVIDIA NIM** (`https://integrate.api.nvidia.com/v1` - Nemotron, Llama 3.3, DeepSeek R1)
  - **DeepSeek** (`https://api.deepseek.com/v1` - DeepSeek Chat & Reasoner)
  - **Mistral AI** (`https://api.mistral.ai/v1` - Codestral, Mistral Large, Mistral Small)
  - **LLM7.io** (`https://api.llm7.io/v1` - Frontier 2026 models like DeepSeek V4 Flash, Kimi K3, GLM 5.3)
  - **Cloudflare Workers AI** (`https://api.cloudflare.com/client/v4`)
  - **Ollama (Local & Cloud)** (`http://127.0.0.1:11434` / `https://ollama.com/api`)
  - **OpenAI (Official)** & **Custom OpenAI-Compatible** servers.

#### 2. ⚡ Intelligent API Key Auto-Detection
- Pasting an API key instantly identifies the provider and switches the endpoint:
  - `sk-or-v1-...` ➔ **OpenRouter**
  - `gsk_...` ➔ **Groq**
  - `nvapi-...` ➔ **NVIDIA NIM**
  - `cfut_...` ➔ **Cloudflare Workers AI**
  - `sk-...` ➔ **DeepSeek / OpenAI**
  - 32-character hex ➔ **Mistral AI**

#### 3. 🎁 Live Model Discovery & Free Model Filtering
- Clicking **"⚡ Проверить и загрузить модели"** queries the provider's `/v1/models` endpoint in a non-blocking background thread.
- Free models are labeled `🎁 [FREE]` and pinned to the top of the dropdown list.
- Dedicated checkbox: `[x] 🎁 Только бесплатные (:free)`.

#### 4. 🔍 Clear Error Diagnostics
- Displays human-readable diagnostics for 401 Unauthorized, 403 Forbidden (with VPN tips for Groq), 429 Rate Limits, and network timeouts.

---

<details>
<summary><b>🇷🇺 Описание релиза на русском языке (Russian Translation)</b></summary>

### 🚀 GitHub Search & Downloader v1.1.2 (Русская версия)

Версия **v1.1.2** добавляет универсальную поддержку всех современных провайдеров ИИ, мгновенное автоопределение ключей и загрузку актуальных бесплатных и платных моделей.

#### 📥 Ссылки на загрузку:
- 💿 **[Установщик Windows (Setup.exe)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/GithubSearchDownloader-v1.1.2-windows-x64-setup.exe)** (~14.2 MB)
- 📦 **[Портативный архив (Portable.zip)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/GithubSearchDownloader-1.1.2-windows-x64.zip)** (~13.7 MB)
- 🛡️ **[Контрольные суммы (checksums.sha256)](https://github.com/AI-Nikitka93/github-search-downloader/releases/download/v1.1.2/checksums.sha256)**

#### ✨ Ключевые нововведения:
1. **Поддержка всех ведущих провайдеров ИИ**: OpenRouter, Groq, NVIDIA NIM, Mistral AI, LLM7.io, DeepSeek, Cloudflare Workers AI, Ollama (локально и в облаке), OpenAI и кастомные серверы.
2. **Автоопределение ключа на лету**: при вставке ключа программа сама определяет провайдера (`sk-or-v1-` -> OpenRouter, `gsk_` -> Groq, `nvapi-` -> NVIDIA, `cfut_` -> Cloudflare, `sk-` -> DeepSeek) и подставляет нужный Base URL.
3. **Живая загрузка моделей с выделением бесплатных**: опрос эндпоинта `/models` в фоновом потоке, маркировка `🎁 [FREE]` для бесплатных моделей и удобный фильтр `Только бесплатные (:free)`.
4. **Понятная диагностика ошибок**: детальные подсказки при ошибках 401, 403 (например, необходимость VPN для Groq), 429 и таймаутах.

</details>
