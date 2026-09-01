# Changelog

All notable changes to the **GitHub Search & Downloader** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).

---

## [0.0.1] — 2026-09-02

### 🎉 Initial Public Beta Release
- **Modern 2026 UI Design System**:
  - Windows 11 DWM Chrome integration with immersive titlebars, rounded corners, and native multi-resolution icons.
  - Soft GitHub Dark palette with elevated CardFrame containers and live PillBadge indicators.
  - Modern typography scale, SegmentedPillToggle, and 60fps braille spinner animation.
  - 3D hero illustrations and micro-chip icons for fast visual recognition.
- **Universal Multi-Provider AI Engine**:
  - Full support for **OpenRouter**, **Groq**, **NVIDIA NIM**, **Mistral AI**, **LLM7.io**, **DeepSeek**, **Cloudflare Workers AI**, **Ollama Cloud/Local**, and **OpenAI**.
  - **Intelligent Key Auto-Detection**: Automatically identifies provider and Base URL when pasting keys (`sk-or-v1-` -> OpenRouter, `gsk_` -> Groq, `nvapi-` -> NVIDIA NIM, `cfut_` -> Cloudflare, `sk-` -> DeepSeek/OpenAI, 32-char hex -> Mistral AI).
  - **Live Asynchronous Model Discovery**: Dynamically queries `/v1/models` and provider APIs without blocking the GUI.
  - **Free Models Highlighting & Filtering**: Automatically tags and sorts `:free` and 0-cost models with a 1-click filter checkbox.
  - **Smart Error Diagnostics**: Informative status badges explaining exact failure causes.
- **Date-Sharded Search Engine & Resilient API Client**:
  - Automatically shards wide date intervals into recursive bisections (`created:YYYY-MM-DD..YYYY-MM-DD`) to completely bypass GitHub's 1,000-search-results ceiling.
  - **Proactive GraphQL Rate-Limiting**: Intercepts `rateLimit { cost remaining resetAt }` to proactively manage quotas before exhaustion.
  - **Resource Bucket Tracking**: Segregated `X-RateLimit-Resource` pool management across `search`, `graphql`, and `core`.
  - **Random Jitter Backoff**: Anti-thundering-herd jitter (+1..3s) on secondary rate-limit recovery.
- **1-Click Authentication & DPAPI Security**:
  - GitHub OAuth Device Flow (`github.com/login/device`) with automatic clipboard code copying.
  - Military-grade token and API key encryption via native Windows DPAPI (`CryptProtectData`) tied to current user credentials. Zero plaintext credentials in logs or storage.
- **Parallel Downloader & Multi-Format Exporters**:
  - Multi-threaded Git clone engine with shallow (`--depth 1`) and partial (`--filter=blob:none`) cloning with process tree timeout management.
  - Real-time serialization to SQLite, CSV, and AI Repomix XML formats.
- **Full Windows Lifecycle Management**:
  - Inno Setup 6 installer (`packaging/installer.iss`) with clean in-place upgrade, taskbar mutex protection, and uninstaller.
  - In-app self-updater with GitHub Releases API integration and atomic batch replacement.
