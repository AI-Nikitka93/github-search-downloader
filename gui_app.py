from __future__ import annotations

import ctypes
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import sv_ttk
from dataclasses import replace
from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path
from tkinter import (
    BOTH,
    END,
    LEFT,
    RIGHT,
    VERTICAL,
    W,
    Y,
    BooleanVar,
    DoubleVar,
    PhotoImage,
    StringVar,
    Text,
    Toplevel,
    Tk,
    filedialog,
    messagebox,
    Canvas,
    Menu,
)
from tkinter import ttk


def enable_high_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from github_harvester.ai_planner import (
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI_COMPATIBLE,
    AiProviderConfig,
    list_ai_models,
    discover_local_models,
    plan_search_task,
)
from github_harvester.secret_store import (
    DEFAULT_SECRET_NAME,
    SecretStoreError,
    delete_secret,
    has_secret,
    load_secret,
    secret_name_for_ai_provider,
    store_secret,
)
from github_harvester.service import (
    RunCancelledError,
    RunConfig,
    atomic_write_text,
    extract_query_terms_for_ai_filter,
    load_repositories_from_metadata,
    normalize_query_for_search,
    parse_iso_date,
    parse_keyword_list,
    redact_sensitive_text,
    repo_composite_relevance_score,
    run_collection,
    run_download_for_repositories,
    validate_run_config,
)
from github_harvester.models import Repo
from github_harvester.github_auth import GitHubOAuthDeviceFlow, get_github_cli_token
from github_harvester.clipboard import copy_to_clipboard_async, safe_copy_to_clipboard
from github_harvester.version import (
    APP_DISPLAY_NAME,
    APP_NAME,
    AUTHOR,
    COPYRIGHT,
    CURRENT_SEMVER,
    GITHUB_REPO_URL,
    __version__,
)
from github_harvester.updater import (
    CheckResult,
    ReleaseInfo,
    SelfUpdater,
    UpdateChecker,
    UpdateDownloader,
)


SETTINGS_FILE = ROOT_DIR / "gui_settings.json"
DEBUG_DIR = ROOT_DIR / "debug_logs"
SORT_OPTIONS = {
    "По звездам": "stars",
    "По обновлению": "updated",
}
ORDER_OPTIONS = {
    "По убыванию": "desc",
    "По возрастанию": "asc",
}
SORT_OPTIONS_REVERSE = {value: key for key, value in SORT_OPTIONS.items()}
ORDER_OPTIONS_REVERSE = {value: key for key, value in ORDER_OPTIONS.items()}
SEARCH_PROFILES: dict[str, dict[str, str]] = {
    "Точность": {
        "min_stars": "25",
        "max_age_years": "2",
        "max_repos": "180",
        "batch_size": "60",
        "workers": "4",
        "sort": "По обновлению",
        "order": "По убыванию",
        "language": "",
        "ai_filter_min_score": "0.68",
        "ai_filter_max_reviews": "20",
        "ai_timeout": "25",
    },
    "Баланс": {
        "min_stars": "8",
        "max_age_years": "2",
        "max_repos": "300",
        "batch_size": "80",
        "workers": "4",
        "sort": "По обновлению",
        "order": "По убыванию",
        "language": "",
        "ai_filter_min_score": "0.55",
        "ai_filter_max_reviews": "30",
        "ai_timeout": "30",
    },
    "Полнота": {
        "min_stars": "2",
        "max_age_years": "4",
        "max_repos": "600",
        "batch_size": "100",
        "workers": "4",
        "sort": "По обновлению",
        "order": "По убыванию",
        "language": "",
        "ai_filter_min_score": "0.42",
        "ai_filter_max_reviews": "50",
        "ai_timeout": "30",
    },
}
AI_PROVIDER_PROFILES: dict[str, dict[str, str]] = {
    "DeepSeek": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "timeout": "60",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://platform.deepseek.com/api_keys",
    },
    "Google Gemini": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-3.5-flash",
        "api_key_env": "GEMINI_API_KEY",
        "timeout": "60",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://aistudio.google.com/app/apikey",
    },
    "xAI (Grok)": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://api.x.ai/v1",
        "model": "grok-4.5",
        "api_key_env": "XAI_API_KEY",
        "timeout": "60",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://console.x.ai/",
    },
    "Groq": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://api.groq.com/openai/v1",
        "model": "llama-4-70b-versatile",
        "api_key_env": "GROQ_API_KEY",
        "timeout": "30",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://console.groq.com/keys",
    },
    "OpenRouter (Платные)": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://openrouter.ai/api/v1",
        "model": "anthropic/claude-3.5-sonnet",
        "api_key_env": "OPENROUTER_API_KEY",
        "timeout": "90",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://openrouter.ai/settings/keys",
    },
    "OpenRouter (Бесплатные)": {
        "provider_type": AI_PROVIDER_OPENAI_COMPATIBLE,
        "endpoint": "https://openrouter.ai/api/v1",
        "model": "google/gemma-4-31b-it:free",
        "api_key_env": "OPENROUTER_API_KEY",
        "timeout": "90",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "https://openrouter.ai/settings/keys",
    },
    "Ollama (Локально)": {
        "provider_type": AI_PROVIDER_OLLAMA,
        "endpoint": "http://127.0.0.1:11434",
        "model": "llama-3.1-8b-instruct",
        "api_key_env": "",
        "timeout": "45",
        "temperature": "0",
        "num_ctx": "8192",
        "num_predict": "1024",
        "get_key_url": "",
    },
}

class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        padding = kwargs.pop("padding", None)
        super().__init__(parent, *args, **kwargs)
        
        self.canvas = Canvas(self, borderwidth=0, highlightthickness=0)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        
        self.scrollbar = ttk.Scrollbar(self, orient=VERTICAL, command=self.canvas.yview)
        self.scrollbar.pack(side=RIGHT, fill=Y)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.inner_frame = ttk.Frame(self.canvas)
        if padding is not None:
            self.inner_frame.configure(padding=padding)
            
        self.inner_frame_id = self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        
        self.inner_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_frame_configure(self, event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfig(self.inner_frame_id, width=event.width)

    def _bind_mousewheel(self, event=None) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event=None) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event) -> None:
        if self.canvas.yview() == (0.0, 1.0):
            return
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class AboutDialog(Toplevel):
    """About application modal dialog."""

    def __init__(self, master):
        super().__init__(master)
        self.title(f"О программе — {APP_DISPLAY_NAME}")
        self.geometry("540x440")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        container = ttk.Frame(self, padding=24)
        container.pack(fill=BOTH, expand=True)

        title = ttk.Label(
            container,
            text=APP_DISPLAY_NAME,
            font=("Segoe UI Variable Display", 16, "bold"),
        )
        title.pack(anchor="center", pady=(0, 4))

        ver = ttk.Label(
            container,
            text=f"Версия {__version__} (Harvest Edition)",
            foreground="#57606a",
        )
        ver.pack(anchor="center", pady=(0, 16))

        desc = (
            f"{APP_DISPLAY_NAME} — инструмент для интеллектуального поиска, "
            "фильтрации нейросетями (Ollama, DeepSeek, OpenAI) и пакетной параллельной "
            "загрузки исходного кода из GitHub.\n\n"
            "• Автоматический обход лимитов через шардирование по датам\n"
            "• Надежная защита токенов через Windows DPAPI\n"
            "• Скоростное клонирование (blobless / shallow clone)\n"
            "• Экспорт в SQLite (WAL mode), CSV и AI-ready формат (Repomix)"
        )
        ttk.Label(container, text=desc, wraplength=480, justify="left").pack(anchor="w", pady=(0, 16))

        links_frame = ttk.Frame(container)
        links_frame.pack(fill="x", pady=(0, 16))

        ttk.Button(
            links_frame,
            text="🌐 Репозиторий GitHub",
            command=lambda: webbrowser.open(GITHUB_REPO_URL),
        ).pack(side=LEFT, padx=4)

        ttk.Button(
            links_frame,
            text="📖 Документация",
            command=lambda: webbrowser.open(f"{GITHUB_REPO_URL}#readme"),
        ).pack(side=LEFT, padx=4)

        btn_row = ttk.Frame(container)
        btn_row.pack(side="bottom", fill="x")

        copy_lbl = ttk.Label(btn_row, text=COPYRIGHT, font=("Segoe UI", 8), foreground="#8b949e")
        copy_lbl.pack(side=LEFT)

        ttk.Button(btn_row, text="Закрыть", command=self.destroy).pack(side=RIGHT)


class UpdateCheckerDialog(Toplevel):
    """Update checker and downloader dialog."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Проверка обновлений")
        self.geometry("520x360")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.checker = UpdateChecker()
        self.downloader = UpdateDownloader()
        self.latest_release: Optional[ReleaseInfo] = None

        self.status_var = StringVar(value="🔍 Проверка наличия новых версий на GitHub...")
        self.notes_var = StringVar(value="")
        self.progress_var = DoubleVar(value=0.0)
        self.progress_text_var = StringVar(value="")

        self._build_ui()
        self._check_updates_async()

    def _build_ui(self):
        container = ttk.Frame(self, padding=20)
        container.pack(fill=BOTH, expand=True)

        ttk.Label(container, textvariable=self.status_var, font=("Segoe UI Variable Display", 11, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        sub = ttk.Label(
            container,
            text=f"Текущая версия: v{__version__}",
            foreground="#57606a",
        )
        sub.pack(anchor="w", pady=(0, 10))

        self.notes_box = Text(container, height=8, wrap="word", font=("Segoe UI Variable Text", 9))
        self.notes_box.pack(fill=BOTH, expand=True, pady=(0, 10))

        self.progress_bar = ttk.Progressbar(container, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 4))

        ttk.Label(container, textvariable=self.progress_text_var, font=("Segoe UI", 9), foreground="#57606a").pack(
            anchor="w", pady=(0, 10)
        )

        self.btn_row = ttk.Frame(container)
        self.btn_row.pack(fill="x")

        self.btn_action = ttk.Button(self.btn_row, text="Закрыть", command=self.destroy)
        self.btn_action.pack(side=RIGHT)

    def _check_updates_async(self):
        def _worker():
            res = self.checker.check_for_updates(force=True)
            if res.update_available and res.latest_release:
                self.latest_release = res.latest_release
                def _found():
                    self.status_var.set(f"🎉 Доступна новая версия: v{res.latest_release.version_str}!")
                    self.notes_box.delete("1.0", END)
                    self.notes_box.insert("1.0", res.latest_release.body_markdown or "Нет описания изменений.")
                    self.btn_action.configure(
                        text="⬇ Обновить и перезапустить",
                        command=self._start_download,
                    )
                self.after(0, _found)
            else:
                def _uptodate():
                    self.status_var.set(f"✅ У вас установлена актуальная версия (v{__version__})")
                    self.notes_box.delete("1.0", END)
                    self.notes_box.insert("1.0", "Все компоненты обновлены до последней версии.")
                self.after(0, _uptodate)
        threading.Thread(target=_worker, daemon=True).start()

    def _start_download(self):
        if not self.latest_release:
            return
        self.btn_action.configure(state="disabled")
        self.status_var.set("Загрузка пакета обновления...")

        def _worker():
            def _on_progress(downloaded: int, total: int, speed: float):
                pct = (downloaded / total * 100) if total > 0 else 0
                mb_down = downloaded / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                speed_mb = speed / (1024 * 1024)
                self.after(0, lambda: self._update_progress_ui(pct, mb_down, mb_tot, speed_mb))

            try:
                zip_path = self.downloader.download_and_verify(self.latest_release, progress_callback=_on_progress)
                self.after(0, lambda: self._apply_and_restart(zip_path))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror("Ошибка обновления", str(exc), parent=self))
                self.after(0, lambda: self.btn_action.configure(state="normal"))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_progress_ui(self, pct: float, mb_down: float, mb_tot: float, speed_mb: float):
        self.progress_var.set(pct)
        self.progress_text_var.set(f"{mb_down:.1f} MB / {mb_tot:.1f} MB ({speed_mb:.1f} MB/s)")

    def _apply_and_restart(self, zip_path: Path):
        self.status_var.set("Установка обновления...")
        current_exe = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).resolve()
        SelfUpdater.launch_updater_and_restart(zip_path, current_exe, self.latest_release.version_str)


class HeaderStatusWidget(ttk.Frame):
    """Real-time live status pill widget displayed in the top header."""

    def __init__(self, parent, on_github_click=None, on_ai_click=None, on_disk_click=None):
        super().__init__(parent, padding=(0, 4))
        self.on_github_click = on_github_click
        self.on_ai_click = on_ai_click
        self.on_disk_click = on_disk_click

        self.github_text_var = StringVar(value="🐙 GitHub: Проверка...")
        self.ai_text_var = StringVar(value="🧠 ИИ: Проверка...")
        self.disk_text_var = StringVar(value="💾 Диск: ...")

        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        self.btn_gh = ttk.Button(
            self,
            textvariable=self.github_text_var,
            command=self.on_github_click,
        )
        self.btn_gh.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_ai = ttk.Button(
            self,
            textvariable=self.ai_text_var,
            command=self.on_ai_click,
        )
        self.btn_ai.grid(row=0, column=1, sticky="ew", padx=2)

        self.btn_disk = ttk.Button(
            self,
            textvariable=self.disk_text_var,
            command=self.on_disk_click,
        )
        self.btn_disk.grid(row=0, column=2, sticky="ew", padx=(4, 0))

    def update_github(self, username: str | None, remaining: int, limit: int):
        if username:
            self.github_text_var.set(f"🐙 GitHub: @{username} ({remaining:,}/{limit:,})")
        else:
            self.github_text_var.set(f"🐙 GitHub: Анонимный ({remaining:,}/{limit:,})")

    def update_ai(self, provider_name: str, model_name: str, ready: bool):
        icon = "🟢" if ready else "⚪"
        self.ai_text_var.set(f"🧠 ИИ: {icon} {provider_name} ({model_name})")

    def update_disk(self, workspace_path: Path):
        try:
            workspace_path.mkdir(parents=True, exist_ok=True)
            total, used, free = shutil.disk_usage(workspace_path)
            free_gb = free / (1024**3)
            self.disk_text_var.set(f"💾 {workspace_path.anchor} ({free_gb:.1f} GB свободно)")
        except Exception:
            self.disk_text_var.set("💾 Диск: Готов")


class FirstRunWizard(Toplevel):
    """Zero-friction 4-step first-run onboarding wizard."""

    def __init__(self, master, on_finish_callback=None):
        super().__init__(master)
        self.title(f"Первоначальная настройка — {APP_DISPLAY_NAME}")
        self.geometry("780x560")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self.on_finish_callback = on_finish_callback
        self.current_step = 1

        self.github_user_var = StringVar(value="Не подключен")
        self.github_rate_limit_var = StringVar(value="Лимит: 60 запросов/час")
        self.github_status_msg_var = StringVar(value="")
        self.oauth_code_var = StringVar(value="")
        self.verification_uri_var = StringVar(value="https://github.com/login/device")
        self.oauth_in_progress = False
        self.oauth_cancel_event = threading.Event()
        self.cached_ollama_models: list[str] = []

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        default_workspace = Path.home() / "Downloads" / "GitHubRepositories"
        self.workspace_var = StringVar(value=str(default_workspace))
        self.disk_info_var = StringVar(value="")

        self.ai_mode_var = StringVar(value="local")
        self.ollama_model_var = StringVar(value="")
        self.ollama_status_var = StringVar(value="Поиск Ollama...")
        self.cloud_provider_var = StringVar(value="DeepSeek")
        self.cloud_key_var = StringVar(value="")

        self.selected_preset: dict | None = None

        self._build_ui()
        self._show_step(1)
        self._update_disk_info()
        self._probe_ai_background()

    def _on_close(self):
        self.oauth_cancel_event.set()
        self.destroy()

    def _build_ui(self):
        self.container = ttk.Frame(self, padding=20)
        self.container.pack(fill=BOTH, expand=True)

        self.header_frame = ttk.Frame(self.container)
        self.header_frame.pack(fill="x", pady=(0, 15))

        self.step_label = ttk.Label(
            self.header_frame,
            text="Шаг 1 из 4: Авторизация GitHub",
            font=("Segoe UI Variable Display", 13, "bold"),
        )
        self.step_label.pack(side=LEFT)

        self.progress_bar = ttk.Progressbar(self.header_frame, length=200, mode="determinate", value=25)
        self.progress_bar.pack(side=RIGHT)

        self.content_frame = ttk.Frame(self.container)
        self.content_frame.pack(fill=BOTH, expand=True)

        self.nav_frame = ttk.Frame(self.container)
        self.nav_frame.pack(fill="x", pady=(15, 0))

        self.btn_back = ttk.Button(self.nav_frame, text="⬅ Назад", command=self._prev_step)
        self.btn_back.pack(side=LEFT)

        self.btn_skip = ttk.Button(self.nav_frame, text="Пропустить шаг", command=self._next_step)
        self.btn_skip.pack(side=LEFT, padx=10)

        self.btn_next = ttk.Button(self.nav_frame, text="Далее ➔", command=self._next_step)
        self.btn_next.pack(side=RIGHT)

    def _show_step(self, step: int):
        self.current_step = step
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.progress_bar["value"] = step * 25
        self.btn_back.configure(state="normal" if step > 1 else "disabled")
        self.btn_skip.pack_forget()

        if step == 1:
            self.step_label.configure(text="Шаг 1 из 4: Авторизация GitHub (1-Click)")
            self.btn_skip.pack(side=LEFT, padx=10)
            self._render_step1(self.content_frame)
        elif step == 2:
            self.step_label.configure(text="Шаг 2 из 4: Папка для репозиториев")
            self._render_step2(self.content_frame)
        elif step == 3:
            self.step_label.configure(text="Шаг 3 из 4: Подключение ИИ-помощника")
            self.btn_skip.pack(side=LEFT, padx=10)
            self._render_step3(self.content_frame)
        elif step == 4:
            self.step_label.configure(text="Шаг 4 из 4: Готово! Быстрый старт")
            self.btn_next.configure(text="🚀 Запустить Harvester", command=self._finish)
            self._render_step4(self.content_frame)

    def _render_step1(self, parent):
        box = ttk.LabelFrame(parent, text=" 🐙 Подключение учетной записи GitHub ", padding=15)
        box.pack(fill=BOTH, expand=True)

        ttk.Label(
            box,
            text="Авторизация увеличивает лимит запросов к API GitHub с 60 до 5 000 в час,\n"
            "что позволяет мгновенно находить и анализировать тысячи проектов.",
            font=("Segoe UI Variable Text", 10),
        ).pack(anchor="w", pady=(0, 12))

        btn_row = ttk.Frame(box)
        btn_row.pack(fill="x", pady=5)

        ttk.Button(
            btn_row,
            text="🔑 Войти через GitHub (OAuth 1-Click)",
            command=self._start_oauth_flow,
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Button(
            btn_row,
            text="💻 Импорт из GitHub CLI",
            command=self._import_gh_cli,
        ).pack(side=LEFT, padx=(0, 8))

        ttk.Button(
            btn_row,
            text="✍️ Ввести токен вручную",
            command=self._manual_token_entry,
        ).pack(side=LEFT)

        # Prominent Code Display Frame
        self.code_box_frame = ttk.LabelFrame(box, text=" 🔑 Ваш одноразовый код для входа ", padding=12)

        ttk.Label(
            self.code_box_frame,
            text="1. Скопируйте этот код и вставьте его на открывшейся странице GitHub:",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 6))

        code_row = ttk.Frame(self.code_box_frame)
        code_row.pack(fill="x", pady=(0, 8))

        code_lbl = ttk.Label(
            code_row,
            textvariable=self.oauth_code_var,
            font=("Consolas", 20, "bold"),
            foreground="#0969da",
        )
        code_lbl.pack(side=LEFT, padx=(0, 15))

        ttk.Button(
            code_row,
            text="📋 Скопировать код",
            command=self._copy_user_code,
        ).pack(side=LEFT, padx=4)

        ttk.Button(
            code_row,
            text="🌐 Открыть страницу GitHub",
            command=lambda: webbrowser.open(self.verification_uri_var.get()),
        ).pack(side=LEFT, padx=4)

        ttk.Label(
            self.code_box_frame,
            text="2. Нажмите зеленую кнопку 'Continue' на сайте GitHub. Авторизация в программе завершится автоматически.",
            font=("Segoe UI", 9),
            foreground="#57606a",
        ).pack(anchor="w")

        if self.oauth_code_var.get():
            self.code_box_frame.pack(fill="x", pady=(10, 10))

        self.status_card = ttk.Frame(box, relief="groove", padding=10)
        self.status_card.pack(fill="x", pady=10)

        ttk.Label(self.status_card, textvariable=self.github_user_var, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(self.status_card, textvariable=self.github_rate_limit_var, foreground="#57606a").pack(anchor="w")
        ttk.Label(self.status_card, textvariable=self.github_status_msg_var, foreground="#0969da").pack(
            anchor="w", pady=(4, 0)
        )

    def _render_step2(self, parent):
        box = ttk.LabelFrame(parent, text=" 💾 Рабочая папка ", padding=15)
        box.pack(fill=BOTH, expand=True)

        ttk.Label(box, text="Куда сохранять скачиваемые репозитории:").pack(anchor="w")

        path_row = ttk.Frame(box)
        path_row.pack(fill="x", pady=8)

        entry = ttk.Entry(path_row, textvariable=self.workspace_var)
        entry.pack(side=LEFT, fill="x", expand=True, padx=(0, 8))

        def browse():
            chosen = filedialog.askdirectory(initialdir=self.workspace_var.get())
            if chosen:
                self.workspace_var.set(chosen)
                self._update_disk_info()

        ttk.Button(path_row, text="Обзор...", command=browse).pack(side=RIGHT)
        ttk.Label(box, textvariable=self.disk_info_var, font=("Segoe UI", 10)).pack(anchor="w", pady=10)

    def _render_step3(self, parent):
        box = ttk.LabelFrame(parent, text=" 🧠 Настройка ИИ ", padding=15)
        box.pack(fill=BOTH, expand=True)

        r1 = ttk.Radiobutton(
            box,
            text="Локальный ИИ (Ollama) — Рекомендуется (Бесплатно и приватно)",
            variable=self.ai_mode_var,
            value="local",
        )
        r1.pack(anchor="w", pady=(0, 4))

        ollama_frame = ttk.Frame(box, padding=(20, 0, 0, 10))
        ollama_frame.pack(fill="x")
        ttk.Label(ollama_frame, textvariable=self.ollama_status_var).pack(anchor="w")
        self.combo_ollama = ttk.Combobox(ollama_frame, textvariable=self.ollama_model_var, state="readonly", width=30)
        self.combo_ollama.pack(side=LEFT, pady=4)
        ttk.Button(ollama_frame, text="🔄 Обновить", command=self._probe_ai_background).pack(side=LEFT, padx=8)

        r2 = ttk.Radiobutton(
            box,
            text="Облачные ИИ (DeepSeek, OpenAI, OpenRouter)",
            variable=self.ai_mode_var,
            value="cloud",
        )
        r2.pack(anchor="w", pady=(10, 4))

        cloud_frame = ttk.Frame(box, padding=(20, 0, 0, 10))
        cloud_frame.pack(fill="x")
        ttk.Label(cloud_frame, text="API Key:").pack(side=LEFT)
        ttk.Entry(cloud_frame, textvariable=self.cloud_key_var, show="*", width=30).pack(side=LEFT, padx=8)
        ttk.Button(cloud_frame, text="⚡ Проверить", command=self._test_cloud_key).pack(side=LEFT)

        r3 = ttk.Radiobutton(
            box,
            text="Без ИИ (Только прямой поиск по фильтрам)",
            variable=self.ai_mode_var,
            value="none",
        )
        r3.pack(anchor="w", pady=(10, 0))

    def _render_step4(self, parent):
        box = ttk.LabelFrame(parent, text=" ✨ Готовые быстрые шаблоны ", padding=15)
        box.pack(fill=BOTH, expand=True)

        ttk.Label(box, text="Выберите шаблон для первого поиска или начните с чистого листа:", font=("Segoe UI", 10)).pack(
            anchor="w", pady=(0, 10)
        )

        presets = [
            ("🤖 AI & LLM Библиотеки", "topic:machine-learning stars:>500", "Найти передовые библиотеки для работы с LLM"),
            ("🕷 Парсеры и Краулеры", "web-scraper crawler python stars:>100", "Найти быстрые и надежные парсеры"),
            ("✈️ Telegram-Боты", "telegram bot aiogram python stars:>50", "Найти лучшие готовые шаблоны Telegram-ботов"),
            ("🛡 OSINT & Кибербезопасность", "osint tools reconnaissance security", "Собрать современные утилиты разведки"),
        ]

        grid_frame = ttk.Frame(box)
        grid_frame.pack(fill=BOTH, expand=True)
        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, weight=1)

        for i, (title, query, task) in enumerate(presets):
            btn = ttk.Button(
                grid_frame,
                text=f"{title}\n({query[:28]}...)",
                command=lambda q=query, t=task: self._select_preset(q, t),
            )
            btn.grid(row=i // 2, column=i % 2, padx=6, pady=6, sticky="nsew")

    def _start_oauth_flow(self):
        if self.oauth_in_progress:
            return
        self.oauth_in_progress = True
        self.oauth_cancel_event.clear()
        self.github_status_msg_var.set("Запрос одноразового кода в GitHub...")

        def _worker():
            try:
                auth = GitHubOAuthDeviceFlow()
                info = auth.request_device_code()
                user_code = info["user_code"]
                uri = info.get("verification_uri", "https://github.com/login/device")

                self.after(0, lambda: self._on_code_received(user_code, uri))
                webbrowser.open(uri)

                token = auth.poll_for_token(
                    info["device_code"],
                    info.get("interval", 5),
                    lambda msg: self.after(0, lambda: self.github_status_msg_var.set(msg)),
                    cancel_event=self.oauth_cancel_event,
                )

                store_secret(DEFAULT_SECRET_NAME, token)
                self._fetch_github_user_badge(token)
            except Exception as exc:
                self.after(0, lambda: self.github_status_msg_var.set(f"Ошибка: {exc}"))
            finally:
                self.oauth_in_progress = False

        threading.Thread(target=_worker, daemon=True).start()

    def _on_code_received(self, user_code: str, uri: str):
        self.oauth_code_var.set(user_code)
        self.verification_uri_var.set(uri)
        copy_to_clipboard_async(user_code, tk_widget=self)
        if hasattr(self, "code_box_frame"):
            self.code_box_frame.pack(fill="x", pady=10, before=self.status_card)
        self.github_status_msg_var.set(f"⏳ Ожидание подтверждения кода {user_code} на сайте GitHub...")

    def _copy_user_code(self):
        code = self.oauth_code_var.get().strip()
        if code:
            def _on_copied(ok: bool):
                if ok:
                    self.github_status_msg_var.set(f"📋 Код {code} скопирован в буфер обмена!")
                else:
                    self.github_status_msg_var.set(f"Код {code} (не удалось скопировать в буфер)")

            copy_to_clipboard_async(code, tk_widget=self, on_complete=_on_copied)

    def _manual_token_entry(self):
        from tkinter import simpledialog
        token = simpledialog.askstring("GitHub Token", "Введите ваш Personal Access Token (classic или fine-grained):", parent=self)
        if token and token.strip():
            token = token.strip()
            store_secret(DEFAULT_SECRET_NAME, token)
            self._fetch_github_user_badge(token)

    def _fetch_github_user_badge(self, token: str):
        def _fetch():
            try:
                req = urllib.request.Request(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "GitHub-Harvester-App"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    login = data.get("login", "User")

                req_rate = urllib.request.Request(
                    "https://api.github.com/rate_limit",
                    headers={"Authorization": f"Bearer {token}", "User-Agent": "GitHub-Harvester-App"},
                )
                with urllib.request.urlopen(req_rate, timeout=10) as resp:
                    rate_data = json.loads(resp.read().decode("utf-8"))
                    remaining = rate_data.get("resources", {}).get("core", {}).get("remaining", 5000)
                    limit = rate_data.get("resources", {}).get("core", {}).get("limit", 5000)

                self.after(0, lambda: self._set_user_success(login, remaining, limit))
            except Exception:
                self.after(
                    0,
                    lambda: self.github_status_msg_var.set("Токен сохранен, но профиль не удалось загрузить."),
                )

        threading.Thread(target=_fetch, daemon=True).start()

    def _set_user_success(self, login: str, remaining: int, limit: int):
        if hasattr(self, "code_box_frame"):
            self.code_box_frame.pack_forget()
        self.github_user_var.set(f"✅ Авторизован: @{login}")
        self.github_rate_limit_var.set(f"Лимит API: {remaining} / {limit} запросов/час")
        self.github_status_msg_var.set("Авторизация успешно завершена!")

    def _import_gh_cli(self):
        token = get_github_cli_token()
        if token:
            store_secret(DEFAULT_SECRET_NAME, token)
            self._fetch_github_user_badge(token)
        else:
            messagebox.showwarning("GitHub CLI", "Токен в GitHub CLI (`gh`) не найден.")

    def _update_disk_info(self):
        try:
            path = Path(self.workspace_var.get())
            path.mkdir(parents=True, exist_ok=True)
            total, used, free = shutil.disk_usage(path)
            free_gb = free / (1024**3)
            self.disk_info_var.set(f"Диск {path.anchor}: Свободно {free_gb:.1f} ГБ (Доступно для загрузки)")
        except Exception:
            self.disk_info_var.set("Не удалось определить свободное место на диске.")

    def _probe_ai_background(self):
        def _worker():
            res = discover_local_models(timeout=3)
            if res:
                provider, models = res
                self.cached_ollama_models = list(models)

                def _update():
                    self.ollama_status_var.set(f"🟢 Найден {provider.provider_type.upper()} ({len(models)} моделей)")
                    if hasattr(self, "combo_ollama"):
                        self.combo_ollama["values"] = self.cached_ollama_models
                        if self.cached_ollama_models and not self.ollama_model_var.get():
                            self.ollama_model_var.set(self.cached_ollama_models[0])

                self.after(0, _update)
            else:
                self.after(0, lambda: self.ollama_status_var.set("⚪ Локальный сервер Ollama не запущен"))

        threading.Thread(target=_worker, daemon=True).start()

    def _test_cloud_key(self):
        key = self.cloud_key_var.get().strip()
        provider = self.cloud_provider_var.get().strip()
        if not key:
            messagebox.showwarning("API Key", "Введите API-ключ для сохранения.", parent=self)
            return
        endpoint = "https://api.deepseek.com/v1" if provider == "DeepSeek" else "https://api.openai.com/v1"
        secret_name = secret_name_for_ai_provider(AI_PROVIDER_OPENAI_COMPATIBLE, endpoint)
        try:
            store_secret(secret_name, key)
            messagebox.showinfo("Проверка ключа", f"Ключ для {provider} успешно сохранен в защищенное хранилище Windows DPAPI!", parent=self)
        except Exception as exc:
            messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить ключ в DPAPI: {exc}", parent=self)

    def _select_preset(self, query: str, task: str):
        self.selected_preset = {"query": query, "ai_task": task}
        self._finish()

    def _prev_step(self):
        if self.current_step > 1:
            self._show_step(self.current_step - 1)

    def _next_step(self):
        if self.current_step < 4:
            self._show_step(self.current_step + 1)
        else:
            self._finish()

    def _finish(self):
        if self.on_finish_callback:
            self.on_finish_callback(
                {
                    "workspace": self.workspace_var.get(),
                    "ai_mode": self.ai_mode_var.get(),
                    "ollama_model": self.ollama_model_var.get(),
                    "cloud_provider": self.cloud_provider_var.get(),
                    "cloud_key": self.cloud_key_var.get().strip(),
                    "preset": self.selected_preset,
                }
            )
        self.destroy()


class GitHubSearchGUI:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(f"{APP_DISPLAY_NAME} v{__version__}")
        self.root.geometry("1180x940")
        self.root.minsize(1080, 820)

        self._icon_image: PhotoImage | None = None
        icon_ico = ROOT_DIR / "assets" / "icon.ico"
        icon_png = ROOT_DIR / "assets" / "icon.png"
        if icon_ico.exists():
            try:
                self.root.iconbitmap(str(icon_ico))
            except Exception:
                pass
        elif icon_png.exists():
            try:
                self._icon_image = PhotoImage(file=str(icon_png))
                self.root.iconphoto(True, self._icon_image)
            except Exception:
                pass

        self.events: queue.Queue[tuple] = queue.Queue()
        self.worker_thread: threading.Thread | None = None
        self.ai_thread: threading.Thread | None = None
        self.models_thread: threading.Thread | None = None
        self.cancel_event: threading.Event | None = None
        self.is_running = False
        self.ai_busy = False
        self.models_loading = False
        self.run_id_counter = 0
        self.active_run_id: int | None = None
        self.autopilot_pending = False
        self.autopilot_preview_pending = False
        self._last_query_normalization_message: str | None = None
        self._last_token_source: str = "none"
        self._last_ai_key_source: str = "none"
        self._last_debug_progress: tuple[int, int] = (-1, -1)
        self._last_poll_state: str = ""
        self._debug_lock = threading.Lock()
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        self.debug_log_file = DEBUG_DIR / f"gui_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self.debug_log_file.write_text("", encoding="utf-8")

        self.query_var = StringVar(value="osint ai")
        self.output_var = StringVar(value=r"M:\Projects\GItHubProjektAI")
        self.token_var = StringVar(value="")
        self.saved_token_status_var = StringVar(value="Сохраненный token: проверяется")
        self.min_stars_var = StringVar(value="0")
        self.language_var = StringVar(value="")
        self.created_after_var = StringVar(value="2008-01-01")
        self.created_before_var = StringVar(value=date.today().isoformat())
        self.max_age_years_var = StringVar(value="5")
        self.max_repos_var = StringVar(value="100")
        self.batch_size_var = StringVar(value="100")
        self.workers_var = StringVar(value="6")
        self.clone_timeout_var = StringVar(value="300")
        self.clone_depth_var = StringVar(value="1")
        self.clone_partial_var = BooleanVar(value=True)
        self.clone_single_branch_var = BooleanVar(value=True)
        self.clone_no_tags_var = BooleanVar(value=True)
        self.retry_failed_var = StringVar(value="2")
        self.retry_delay_var = StringVar(value="5")
        self.include_keywords_var = StringVar(value="")
        self.exclude_keywords_var = StringVar(value="")
        self.export_sqlite_var = StringVar(value="")
        self.export_csv_var = BooleanVar(value=False)
        self.export_ai_ready_var = BooleanVar(value=False)
        self.graphql_enrich_var = BooleanVar(value=False)
        self.graphql_batch_size_var = StringVar(value="25")
        self.deep_relevance_var = BooleanVar(value=False)
        self.deep_relevance_max_repos_var = StringVar(value="25")
        self.deep_relevance_min_score_var = StringVar(value="0")
        self.sort_var = StringVar(value="По звездам")
        self.order_var = StringVar(value="По убыванию")
        self.include_forks_var = BooleanVar(value=False)
        self.include_archived_var = BooleanVar(value=False)
        self.skip_existing_var = BooleanVar(value=True)
        self.no_sharding_var = BooleanVar(value=False)
        self.dry_run_var = BooleanVar(value=False)
        self.incremental_var = BooleanVar(value=False)
        self.status_var = StringVar(value="Готово")
        self.progress_var = DoubleVar(value=0.0)
        self.progress_text_var = StringVar(value="0 / 0")
        self.autopilot_enabled_var = BooleanVar(value=False)

        self.ai_model_var = StringVar(value="qwen-14b-general")
        self.ai_provider_type_var = StringVar(value=AI_PROVIDER_OLLAMA)
        self.ai_endpoint_var = StringVar(value="http://127.0.0.1:11434")
        self.ai_api_key_var = StringVar(value="")
        self.ai_api_key_env_var = StringVar(value="")
        self.saved_ai_key_status_var = StringVar(value="AI API key: проверяется")
        self.ai_timeout_var = StringVar(value="30")
        self.ai_temperature_var = StringVar(value="0")
        self.ai_num_ctx_var = StringVar(value="4096")
        self.ai_num_predict_var = StringVar(value="768")
        self.ai_provider_profile_var = StringVar(value="Вручную")
        self.ai_auto_folder_var = BooleanVar(value=True)
        self.ai_filter_enabled_var = BooleanVar(value=True)
        self.ai_filter_min_score_var = StringVar(value="0.55")
        self.ai_filter_max_reviews_var = StringVar(value="10")
        self.ai_custom_prompt_var = StringVar(value="")
        self.search_profile_var = StringVar(value="Баланс")

        self.header_subtitle: ttk.Label | None = None
        self.preview_subtitle: ttk.Label | None = None
        self.ai_task_text: Text | None = None
        self.log_text: Text | None = None
        self.start_button: ttk.Button | None = None
        self.stop_button: ttk.Button | None = None
        self.preview_button: ttk.Button | None = None
        self.ai_apply_button: ttk.Button | None = None
        self.ai_autopilot_button: ttk.Button | None = None
        self.ai_autopilot_preview_button: ttk.Button | None = None
        self.ai_models_button: ttk.Button | None = None
        self.ai_model_combo: ttk.Combobox | None = None
        self.profile_apply_button: ttk.Button | None = None
        self.ai_provider_apply_button: ttk.Button | None = None
        self.preview_window: Toplevel | None = None
        self.preview_tree: ttk.Treeview | None = None
        self.preview_items: dict[str, Repo] = {}
        self.preview_selected_items: set[str] = set()
        self.preview_recommended_items: set[str] = set()
        self.preview_selection_var = StringVar(value="Выбрано: 0")
        self.preview_metadata_file: Path | None = None
        self.preview_query: str = ""

        self._build_ui()
        self.apply_selected_profile(notify=False)
        self._debug("GUI инициализирована")
        self._debug(f"Python={sys.version.split()[0]}; cwd={Path.cwd()}")
        self._debug(f"Файл debug-лога: {self.debug_log_file}")
        self._load_settings()
        self._append_log(f"Debug-лог: {self.debug_log_file}")
        self.refresh_ollama_models()
        
        try:
            if not has_secret(DEFAULT_SECRET_NAME):
                gh_token = get_github_cli_token()
                if gh_token:
                    store_secret(DEFAULT_SECRET_NAME, gh_token)
                    self._refresh_saved_token_status()
                    self._append_log("Токен GitHub автоматически импортирован из GitHub CLI!")
        except Exception as e:
            self._debug(f"Ошибка авто-импорта токена: {e}")

        self._build_menu()
        self._refresh_header_status()
        self.root.after(400, self._check_and_show_onboarding)
        self.root.after(1200, self._start_background_update_check)

    def _build_menu(self) -> None:
        menubar = Menu(self.root)

        help_menu = Menu(menubar, tearoff=0)
        help_menu.add_command(label="Мастер первого запуска...", command=self._open_onboarding_wizard)
        help_menu.add_command(label="Проверить обновления...", command=self._open_update_dialog)
        help_menu.add_separator()
        help_menu.add_command(label="Открыть репозиторий GitHub", command=lambda: webbrowser.open(GITHUB_REPO_URL))
        help_menu.add_command(label="Документация", command=lambda: webbrowser.open(f"{GITHUB_REPO_URL}#readme"))
        help_menu.add_separator()
        help_menu.add_command(label="О программе", command=self._open_about_dialog)

        menubar.add_cascade(label="Справка", menu=help_menu)
        self.root.config(menu=menubar)

    def _open_about_dialog(self) -> None:
        AboutDialog(self.root)

    def _open_update_dialog(self) -> None:
        UpdateCheckerDialog(self.root)

    def _open_onboarding_wizard(self) -> None:
        def on_wizard_finish(data: dict):
            if data.get("workspace"):
                self.output_var.set(data["workspace"])
            ai_mode = data.get("ai_mode", "local")
            if ai_mode == "local":
                self.ai_provider_type_var.set(AI_PROVIDER_OLLAMA)
                self.ai_endpoint_var.set("http://localhost:11434")
                if data.get("ollama_model"):
                    self.ai_model_var.set(data["ollama_model"])
            elif ai_mode == "cloud":
                self.ai_provider_type_var.set(AI_PROVIDER_OPENAI_COMPATIBLE)
                provider = data.get("cloud_provider", "DeepSeek")
                if provider == "DeepSeek":
                    self.ai_endpoint_var.set("https://api.deepseek.com/v1")
                    self.ai_model_var.set("deepseek-chat")
                else:
                    self.ai_endpoint_var.set("https://api.openai.com/v1")
                    self.ai_model_var.set("gpt-4o-mini")
                cloud_key = data.get("cloud_key", "")
                if cloud_key:
                    secret_name = secret_name_for_ai_provider(AI_PROVIDER_OPENAI_COMPATIBLE, self.ai_endpoint_var.get())
                    try:
                        store_secret(secret_name, cloud_key)
                    except Exception as e:
                        self._debug(f"Could not store wizard cloud key: {e}")
            elif ai_mode == "none":
                self.ai_filter_enabled_var.set(False)

            if data.get("preset"):
                self.query_var.set(data["preset"]["query"])
                if self.ai_task_text:
                    self.ai_task_text.delete("1.0", END)
                    self.ai_task_text.insert("1.0", data["preset"]["ai_task"])
            self._save_settings(first_run_completed=True)
            self._refresh_header_status()
            self._refresh_saved_ai_key_status()

        FirstRunWizard(self.root, on_finish_callback=on_wizard_finish)

    def _check_and_show_onboarding(self) -> None:
        settings_exist = SETTINGS_FILE.exists()
        has_token = False
        try:
            has_token = has_secret(DEFAULT_SECRET_NAME)
        except Exception:
            pass

        first_run = False
        if not settings_exist:
            first_run = True
        else:
            try:
                payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if not payload.get("first_run_completed", False) and not has_token:
                    first_run = True
            except Exception:
                first_run = True

        if first_run:
            self._open_onboarding_wizard()

    def _start_background_update_check(self) -> None:
        def _worker():
            checker = UpdateChecker()
            result = checker.check_for_updates(force=False)
            if result.update_available and result.latest_release:
                self.root.after(0, lambda: self._prompt_update_available(result.latest_release))
        threading.Thread(target=_worker, daemon=True, name="UpdateCheckThread").start()

    def _prompt_update_available(self, release: ReleaseInfo) -> None:
        if hasattr(self, "_update_prompted") and self._update_prompted:
            return
        self._update_prompted = True
        dlg = UpdateCheckerDialog(self.root)
        dlg.latest_release = release
        dlg.status_var.set(f"🎉 Доступна новая версия: v{release.version_str}!")
        dlg.notes_box.delete("1.0", END)
        dlg.notes_box.insert("1.0", release.body_markdown or "Нет описания изменений.")
        dlg.btn_action.configure(
            text="⬇ Обновить и перезапустить",
            command=dlg._start_download,
        )

    def _refresh_header_status(self) -> None:
        if not hasattr(self, "status_pill_widget") or not self.status_pill_widget.winfo_exists():
            return

        try:
            has_tok = has_secret(DEFAULT_SECRET_NAME)
        except Exception:
            has_tok = False

        if has_tok:
            self.status_pill_widget.github_text_var.set("🐙 GitHub: Подключен (5000/5000)")
        else:
            self.status_pill_widget.github_text_var.set("🐙 GitHub: Анонимный (60/60)")

        ai_prov = self.ai_provider_type_var.get().strip()
        ai_model = self.ai_model_var.get().strip() or "none"
        self.status_pill_widget.update_ai(ai_prov.capitalize(), ai_model, ready=True)

        out_path = Path(self.output_var.get().strip() or str(Path.home() / "Downloads"))
        self.status_pill_widget.update_disk(out_path)

    def _toggle_theme(self) -> None:
        try:
            sv_ttk.toggle_theme()
            dark = sv_ttk.get_theme() == "dark"
        except Exception:
            dark = False
        self._apply_theme_colors(dark)

    def _apply_theme_colors(self, dark: bool | None = None) -> None:
        if dark is None:
            try:
                dark = sv_ttk.get_theme() == "dark"
            except Exception:
                dark = False
        sub_fg = "#8b949e" if dark else "#57606a"
        if getattr(self, "header_subtitle", None) and self.header_subtitle.winfo_exists():
            self.header_subtitle.configure(foreground=sub_fg)
        if getattr(self, "preview_subtitle", None) and self.preview_subtitle.winfo_exists():
            self.preview_subtitle.configure(foreground=sub_fg)
        if getattr(self, "preview_tree", None) and self.preview_tree.winfo_exists():
            self.preview_tree.tag_configure(
                "highly_recommended",
                background="#1e2d24" if dark else "#d4edda",
                foreground="#e6edf3" if dark else "#155724",
            )
            self.preview_tree.tag_configure(
                "low_priority",
                foreground="#8b949e" if dark else "#6c757d",
            )

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=24)
        container.pack(fill=BOTH, expand=True)

        header_frame = ttk.Frame(container)
        header_frame.pack(fill="x", pady=(0, 12))

        header_top = ttk.Frame(header_frame)
        header_top.pack(fill="x")
        
        title = ttk.Label(header_top, text=f"{APP_DISPLAY_NAME} v{__version__}", font=("Segoe UI Variable Display", 18, "bold"))
        title.pack(side=LEFT)
        
        theme_btn = ttk.Button(header_top, text="🌓 Тема", command=self._toggle_theme)
        theme_btn.pack(side=RIGHT, padx=(4, 0))

        update_btn = ttk.Button(header_top, text="🔄 Обновления", command=self._open_update_dialog)
        update_btn.pack(side=RIGHT, padx=(4, 0))

        about_btn = ttk.Button(header_top, text="ℹ О программе", command=self._open_about_dialog)
        about_btn.pack(side=RIGHT, padx=(4, 0))

        self.header_subtitle = ttk.Label(
            header_frame,
            text="Шаг 1: опишите задачу ИИ. Шаг 2: при необходимости поправьте параметры. Шаг 3: запуск.",
            font=("Segoe UI Variable Text", 11),
            foreground="#8b949e"
        )
        self.header_subtitle.pack(anchor=W, pady=(0, 4))

        self.status_pill_widget = HeaderStatusWidget(
            header_frame,
            on_github_click=lambda: self.notebook.select(self.tab_tokens),
            on_ai_click=lambda: self.notebook.select(self.tab_ai),
            on_disk_click=lambda: self.notebook.select(self.tab_main),
        )
        self.status_pill_widget.pack(fill="x", pady=(2, 6))

        bottom_container = ttk.Frame(container)
        bottom_container.pack(side="bottom", fill=BOTH)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(side="top", fill=BOTH, expand=True, pady=(0, 16))

        self.tab_main = ScrollableFrame(self.notebook, padding=16)
        self.tab_ai = ScrollableFrame(self.notebook, padding=16)
        self.tab_filters = ScrollableFrame(self.notebook, padding=16)
        self.tab_tokens = ScrollableFrame(self.notebook, padding=16)
        self.tab_advanced = ScrollableFrame(self.notebook, padding=16)

        self.notebook.add(self.tab_main, text="Главная")
        self.notebook.add(self.tab_filters, text="Фильтры поиска")
        self.notebook.add(self.tab_ai, text="ИИ: Провайдеры и Фильтры")
        self.notebook.add(self.tab_tokens, text="Авторизация GitHub")
        self.notebook.add(self.tab_advanced, text="Движок и Git")

        self._build_tab_main(self.tab_main.inner_frame)
        self._build_tab_ai(self.tab_ai.inner_frame)
        self._build_tab_filters(self.tab_filters.inner_frame)
        self._build_tab_tokens(self.tab_tokens.inner_frame)
        self._build_tab_advanced(self.tab_advanced.inner_frame)

        self._build_actions(bottom_container)
        self._build_status(bottom_container)
        self._build_log(bottom_container)
        self._apply_theme_colors()

    def _build_tab_main(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1)

        # Блок "Поиск"
        search_frame = ttk.LabelFrame(parent, text="Поиск")
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8), padx=4)
        search_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Что нужно найти? (описание для ИИ)", font=("Segoe UI Variable Display", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))
        self.ai_task_text = Text(search_frame, height=3, wrap="word", font=("Segoe UI Variable Text", 10))
        self.ai_task_text.grid(row=1, column=0, columnspan=2, sticky="we", padx=8, pady=(0, 8))
        self.ai_task_text.insert("1.0", "Найди свежие репозитории по OSINT и AI-анализу, без старых и заброшенных проектов.")
        
        btn_frame = ttk.Frame(search_frame)
        btn_frame.grid(row=2, column=0, columnspan=2, sticky="e", padx=8, pady=(0, 8))
        ttk.Checkbutton(btn_frame, text="Использовать AI-Автопилот (AI-планировщик)", variable=self.autopilot_enabled_var).pack(side="left", padx=(0, 16))
        self.ai_apply_button = ttk.Button(btn_frame, text="Сгенерировать настройки поиска", command=self.apply_ai_command)
        self.ai_apply_button.pack(side="right")

        self._add_labeled_entry(search_frame, "Поисковый запрос (для GitHub)", self.query_var, row=3)

        # Блок "Сохранение и Экспорт"
        export_frame = ttk.LabelFrame(parent, text="Сохранение и экспорт")
        export_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8), padx=4)
        export_frame.grid_columnconfigure(1, weight=1)

        self._add_output_row(export_frame, row=0)
        
        export_flags = ttk.Frame(export_frame)
        export_flags.grid(row=1, column=0, columnspan=3, sticky="w", padx=8, pady=(4, 12))
        ttk.Checkbutton(export_flags, text="Экспорт в CSV", variable=self.export_csv_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(export_flags, text="Упаковать код в один файл (для ИИ)", variable=self.export_ai_ready_var).pack(side="left", padx=(0, 16))

        # Блок "Лимиты и качество"
        limits_frame = ttk.LabelFrame(parent, text="Лимиты и качество")
        limits_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8), padx=4)
        limits_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(limits_frame, text="Профиль качества").grid(row=0, column=0, sticky="w", padx=8, pady=(8, 8))
        profile_frame = ttk.Frame(limits_frame)
        profile_frame.grid(row=0, column=1, sticky="w", pady=(8, 8))
        profile_combo = ttk.Combobox(profile_frame, textvariable=self.search_profile_var, values=tuple(SEARCH_PROFILES.keys()), state="readonly", width=20)
        profile_combo.pack(side="left")
        self.profile_apply_button = ttk.Button(profile_frame, text="Применить", command=self.apply_selected_profile)
        self.profile_apply_button.pack(side="left", padx=(8, 0))

        self._add_labeled_entry(limits_frame, "Сколько проектов искать (максимум)", self.max_repos_var, row=1)
        self._add_labeled_entry(limits_frame, "Игнорировать проекты старше (лет)", self.max_age_years_var, row=2)
        self._add_labeled_entry(limits_frame, "Минимум звезд", self.min_stars_var, row=3)

    def _build_tab_ai(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(0, weight=1, uniform="pane")
        parent.grid_columnconfigure(1, weight=1, uniform="pane")
        
        left_pane = ttk.Frame(parent)
        left_pane.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        
        right_pane = ttk.Frame(parent)
        right_pane.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        
        left_pane.grid_columnconfigure(1, weight=1)
        right_pane.grid_columnconfigure(0, weight=1)
        
        # Профиль
        ttk.Label(left_pane, text="Профиль ИИ").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(4, 12))
        ai_prof_frame = ttk.Frame(left_pane)
        ai_prof_frame.grid(row=0, column=1, columnspan=3, sticky="w", pady=(4, 12))
        
        provider_profile_combo = ttk.Combobox(ai_prof_frame, textvariable=self.ai_provider_profile_var, values=("Кастомный", *AI_PROVIDER_PROFILES.keys()), state="readonly", width=22)
        provider_profile_combo.pack(side="left")
        provider_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_ai_provider_profile(notify=False))

        # Модель
        ttk.Label(left_pane, text="Модель ИИ").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(4, 12))
        model_frame = ttk.Frame(left_pane)
        model_frame.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(4, 12))
        self.ai_model_combo = ttk.Combobox(model_frame, textvariable=self.ai_model_var)
        self.ai_model_combo.pack(side="left", fill="x", expand=True)
        self.ai_models_button = ttk.Button(model_frame, text="Проверить ключ и загрузить модели", command=self.refresh_ollama_models)
        self.ai_models_button.pack(side="left", padx=(8, 0))

        # Тип провайдера (Скрываемый)
        self.lbl_provider_type = ttk.Label(left_pane, text="Провайдер ИИ")
        self.lbl_provider_type.grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(4, 12))
        self.combo_provider_type = ttk.Combobox(left_pane, textvariable=self.ai_provider_type_var, values=(AI_PROVIDER_OLLAMA, AI_PROVIDER_OPENAI_COMPATIBLE), state="readonly")
        self.combo_provider_type.grid(row=2, column=1, sticky="ew", pady=(4, 12))

        # Endpoint (Скрываемый)
        self.lbl_endpoint = ttk.Label(left_pane, text="AI Endpoint URL")
        self.lbl_endpoint.grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
        self.entry_endpoint = ttk.Entry(left_pane, textvariable=self.ai_endpoint_var)
        self.entry_endpoint.grid(row=3, column=1, sticky="ew", pady=4)

        # Ключ
        ttk.Label(left_pane, text="Ключ API ИИ").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=(4, 12))
        key_frame = ttk.Frame(left_pane)
        key_frame.grid(row=4, column=1, columnspan=3, sticky="ew", pady=(4, 12))
        self.entry_ai_key = ttk.Entry(key_frame, textvariable=self.ai_api_key_var, show="*")
        self.entry_ai_key.pack(side="left", fill="x", expand=True)
        
        def toggle_ai_key_visibility():
            if self.entry_ai_key.cget("show") == "":
                self.entry_ai_key.config(show="*")
            else:
                self.entry_ai_key.config(show="")
                
        ttk.Button(key_frame, text="👁 Показать", command=toggle_ai_key_visibility).pack(side="left", padx=(4, 0))
        ttk.Button(key_frame, text="Сохранить", command=self._save_ai_api_key_to_store).pack(side="left", padx=(8, 0))
        ttk.Button(key_frame, text="Загрузить", command=self._load_ai_api_key_from_store).pack(side="left", padx=(6, 0))
        
        self.lbl_get_key = ttk.Label(key_frame, text="Где взять ключ?", foreground="#0078D7", cursor="hand2")
        self.lbl_get_key.pack(side="left", padx=(12, 0))
        self.lbl_get_key.bind("<Button-1>", self._open_provider_key_url)

        ttk.Label(left_pane, textvariable=self.saved_ai_key_status_var).grid(row=5, column=1, columnspan=3, sticky="w", pady=(0, 12))
        self._add_labeled_entry(left_pane, "Переменная окружения для ключа", self.ai_api_key_env_var, row=6)

        # AI-фильтр релевантности
        filter_frame = ttk.LabelFrame(right_pane, text="AI-фильтр релевантности")
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, 8), padx=4)
        filter_frame.grid_columnconfigure(1, weight=1)
        
        ttk.Checkbutton(filter_frame, text="Оценивать каждый найденный проект через ИИ", variable=self.ai_filter_enabled_var).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 12))
        self.ai_filter_min_score_entry = self._add_labeled_entry(filter_frame, "Минимальная оценка ИИ (от 0.0 до 1.0)", self.ai_filter_min_score_var, row=1)
        self.ai_filter_max_reviews_entry = self._add_labeled_entry(filter_frame, "Макс. AI-проверок", self.ai_filter_max_reviews_var, row=2)
        self._add_labeled_entry(filter_frame, "Кастомные ИИ-правила", self.ai_custom_prompt_var, row=3)

        def update_ai_filter_state(*args):
            state = "normal" if self.ai_filter_enabled_var.get() else "disabled"
            if hasattr(self, "ai_filter_min_score_entry"):
                try:
                    # In _add_labeled_entry, we return the entry widget.
                    self.ai_filter_min_score_entry.configure(state=state)
                    self.ai_filter_max_reviews_entry.configure(state=state)
                except Exception as e:
                    self._debug(f"State update failed: {e}")
            
        self.ai_filter_enabled_var.trace_add("write", update_ai_filter_state)
        self.root.after(100, update_ai_filter_state)

        # Тонкая настройка
        adv_frame = ttk.LabelFrame(right_pane, text="Тонкая настройка (Advanced)")
        adv_frame.grid(row=1, column=0, sticky="ew", pady=(12, 8), padx=4)
        adv_frame.grid_columnconfigure(1, weight=1)
        
        self._add_labeled_entry(adv_frame, "Размер контекста (num_ctx)", self.ai_num_ctx_var, row=0)
        self._add_labeled_entry(adv_frame, "Лимит токенов вывода (num_predict)", self.ai_num_predict_var, row=1)
        self._add_labeled_entry(adv_frame, "Температура (temperature)", self.ai_temperature_var, row=2)
        self._add_labeled_entry(adv_frame, "Таймаут ожидания ИИ (сек)", self.ai_timeout_var, row=3)

    def _build_tab_filters(self, parent: ttk.Frame) -> None:
        parent.grid_columnconfigure(1, weight=1)
        self._add_labeled_entry(parent, "Дата начала (YYYY-MM-DD)", self.created_after_var, row=0)
        self._add_labeled_entry(parent, "Дата конца (YYYY-MM-DD)", self.created_before_var, row=1)
        self._add_labeled_entry(parent, "Язык (необязательно)", self.language_var, row=2)
        self._add_labeled_entry(parent, "Обязательные слова (через запятую)", self.include_keywords_var, row=3)
        self._add_labeled_entry(parent, "Исключить слова (через запятую)", self.exclude_keywords_var, row=4)
        
        toggles = ttk.Frame(parent)
        toggles.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 4))
        ttk.Checkbutton(toggles, text="Искать среди форков (копий)", variable=self.include_forks_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(toggles, text="Искать заброшенные (Archived)", variable=self.include_archived_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(toggles, text="Не скачивать уже загруженные", variable=self.skip_existing_var).pack(side="left", padx=(0, 16))

    def _build_tab_tokens(self, parent: ttk.Frame) -> None:
        self._add_token_row(parent, row=0)
        for col in range(2):
            parent.grid_columnconfigure(col, weight=1 if col == 1 else 0)

    def _build_tab_advanced(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Сортировка", font=("Segoe UI Variable Display", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        sort_combo = ttk.Combobox(parent, textvariable=self.sort_var, values=tuple(SORT_OPTIONS.keys()), state="readonly", width=20)
        sort_combo.grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 12))
        order_combo = ttk.Combobox(parent, textvariable=self.order_var, values=tuple(ORDER_OPTIONS.keys()), state="readonly", width=20)
        order_combo.grid(row=1, column=1, sticky="w", pady=(0, 12))

        ttk.Label(parent, text="Настройки движка (Engine)", font=("Segoe UI Variable Display", 11, "bold")).grid(row=2, column=0, columnspan=4, sticky="w", pady=(12, 8))
        self._add_labeled_entry(parent, "Размер пакета", self.batch_size_var, row=3)
        self._add_labeled_entry(parent, "Параллельных потоков", self.workers_var, row=4)
        self._add_labeled_entry(parent, "Повторы при ошибке", self.retry_failed_var, row=5)
        self._add_labeled_entry(parent, "Пауза перед повтором (сек)", self.retry_delay_var, row=6)
        
        ttk.Label(parent, text="Настройки Git Clone", font=("Segoe UI Variable Display", 11, "bold")).grid(row=7, column=0, columnspan=4, sticky="w", pady=(12, 8))
        self._add_labeled_entry(parent, "Таймаут клонирования (сек)", self.clone_timeout_var, row=8)
        self._add_labeled_entry(parent, "Глубина истории Git (1 = только последняя версия)", self.clone_depth_var, row=9)
        
        clone_toggles = ttk.Frame(parent)
        clone_toggles.grid(row=10, column=0, columnspan=4, sticky="w", pady=(8, 12))
        ttk.Checkbutton(clone_toggles, text="Partial clone", variable=self.clone_partial_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(clone_toggles, text="Одна ветка", variable=self.clone_single_branch_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(clone_toggles, text="Без тегов", variable=self.clone_no_tags_var).pack(side="left", padx=(0, 16))

        ttk.Label(parent, text="Дополнительные флаги поиска", font=("Segoe UI Variable Display", 11, "bold")).grid(row=11, column=0, columnspan=4, sticky="w", pady=(12, 8))
        self._add_labeled_entry(parent, "SQLite export (опц.)", self.export_sqlite_var, row=12)
        self._add_labeled_entry(parent, "GraphQL batch", self.graphql_batch_size_var, row=13)
        self._add_labeled_entry(parent, "Deep max repos", self.deep_relevance_max_repos_var, row=14)
        self._add_labeled_entry(parent, "Deep min score (0..1)", self.deep_relevance_min_score_var, row=15)
        
        flags = ttk.Frame(parent)
        flags.grid(row=16, column=0, columnspan=4, sticky="w", pady=(8, 12))
        ttk.Checkbutton(flags, text="Инкрементально (Продолжить с места остановки)", variable=self.incremental_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(flags, text="Быстрый поиск (до 1000 проектов, без шардирования)", variable=self.no_sharding_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(flags, text="GraphQL enrichment", variable=self.graphql_enrich_var).pack(side="left", padx=(0, 16))
        ttk.Checkbutton(flags, text="Глубокий анализ релевантности (по README)", variable=self.deep_relevance_var).pack(side="left", padx=(0, 16))

        for col in range(2):
            parent.grid_columnconfigure(col, weight=1 if col == 1 else 0)

    def _build_actions(self, parent: ttk.Frame) -> None:
        mode_frame = ttk.Frame(parent)
        mode_frame.pack(fill="x", pady=(8, 0))
        ttk.Label(mode_frame, text="Режим работы:", font=("Segoe UI Variable Display", 10, "bold")).pack(side="left", padx=(0, 16))
        
        def update_start_btn():
            if self.dry_run_var.get():
                self.start_button.config(text="🔍 Найти и Собрать список")
            else:
                self.start_button.config(text="🚀 Найти и Скачать код")

        r1 = ttk.Radiobutton(mode_frame, text="🚀 Полный цикл (Поиск + Скачивание кода)", variable=self.dry_run_var, value=False, command=update_start_btn)
        r1.pack(side="left", padx=(0, 16))
        
        r2 = ttk.Radiobutton(mode_frame, text="📋 Только поиск (Собрать список, без скачивания)", variable=self.dry_run_var, value=True, command=update_start_btn)
        r2.pack(side="left", padx=(0, 16))

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(16, 16))
        
        self.start_button = ttk.Button(actions, text="🚀 Найти и Скачать код", command=self.start_collection, style="Accent.TButton")
        self.start_button.pack(side="left", padx=(0, 8))
        
        self.stop_button = ttk.Button(actions, text="Стоп", command=self.stop_collection, state="disabled")
        self.stop_button.pack(side="left", padx=(0, 8))

        # Вспомогательные кликабельные метки вместо кнопок
        links_frame = ttk.Frame(actions)
        links_frame.pack(side="right", padx=(0, 8))
        
        lbl_folder = ttk.Label(links_frame, text="📁 Открыть папку", foreground="#0078D7", cursor="hand2")
        lbl_folder.pack(side="left", padx=(0, 16))
        lbl_folder.bind("<Button-1>", lambda e: self.open_output_folder())
        
        lbl_log = ttk.Label(links_frame, text="📄 Открыть лог", foreground="#0078D7", cursor="hand2")
        lbl_log.pack(side="left")
        lbl_log.bind("<Button-1>", lambda e: self.open_debug_log())

    def _build_status(self, parent: ttk.Frame) -> None:
        status_bar = ttk.Frame(parent)
        status_bar.pack(fill="x", pady=(0, 8))
        self.status_label = ttk.Label(status_bar, textvariable=self.status_var, font=("Segoe UI Variable Text", 10, "bold"))
        self.status_label.pack(side="left")
        ttk.Label(status_bar, textvariable=self.progress_text_var, font=("Segoe UI Variable Text", 10)).pack(side="right")

        self.progress_widget = ttk.Progressbar(parent, orient="horizontal", mode="determinate", variable=self.progress_var, maximum=100)
        self.progress_widget.pack(fill="x", pady=(0, 16))
        
        self._animation_active = False
        self._animation_step = 0
        self._base_status_text = ""

    def _set_progress_mode(self, mode: str) -> None:
        """Sets progress bar mode ('determinate' or 'indeterminate')."""
        if hasattr(self, 'progress_widget'):
            self.progress_widget.configure(mode=mode)
            if mode == 'indeterminate':
                self.progress_widget.start(15)
            else:
                self.progress_widget.stop()

    def _start_status_animation(self, base_text: str) -> None:
        self._base_status_text = base_text
        if not self._animation_active:
            self._animation_active = True
            self._animate_status()

    def _stop_status_animation(self) -> None:
        self._animation_active = False

    def _set_status(self, new_status: str) -> None:
        if self._animation_active:
            self._base_status_text = new_status
        else:
            self.status_var.set(new_status)

    def _animate_status(self) -> None:
        if not self._animation_active:
            return
        dots = "." * (self._animation_step % 4)
        self.status_var.set(f"{self._base_status_text}{dots}")
        self._animation_step += 1
        self.root.after(400, self._animate_status)

    def _build_log(self, parent: ttk.Frame) -> None:
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=BOTH, expand=True)
        self.log_text = Text(log_frame, wrap="word", height=10, relief="flat", borderwidth=0, font=("Consolas", 10))
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, orient=VERTICAL, command=self.log_text.yview)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.configure(state="disabled")

    def apply_selected_profile(self, notify: bool = True) -> None:
        profile_name = self.search_profile_var.get()
        if profile_name in SEARCH_PROFILES:
            prof = SEARCH_PROFILES[profile_name]
            for var_name, key in [
                ("min_stars_var", "min_stars"),
                ("max_age_years_var", "max_age_years"),
                ("max_repos_var", "max_repos"),
                ("batch_size_var", "batch_size"),
                ("workers_var", "workers"),
                ("sort_var", "sort"),
                ("order_var", "order"),
                ("language_var", "language"),
                ("ai_filter_min_score_var", "ai_filter_min_score"),
                ("ai_filter_max_reviews_var", "ai_filter_max_reviews"),
                ("ai_timeout_var", "ai_timeout"),
            ]:
                if hasattr(self, var_name) and key in prof:
                    getattr(self, var_name).set(prof[key])
            if notify:
                messagebox.showinfo("Профиль применен", f"Применен профиль параметров поиска: {profile_name}")

    def apply_ai_provider_profile(self, notify: bool = True) -> None:
        profile_name = self.ai_provider_profile_var.get()
        if profile_name in AI_PROVIDER_PROFILES:
            prof = AI_PROVIDER_PROFILES[profile_name]
            if "provider_type" in prof:
                self.ai_provider_type_var.set(prof["provider_type"])
            if "endpoint" in prof:
                self.ai_endpoint_var.set(prof["endpoint"])
            if "model" in prof:
                self.ai_model_var.set(prof["model"])
            if "timeout" in prof:
                self.ai_timeout_var.set(str(prof["timeout"]))
            if "num_ctx" in prof:
                self.ai_num_ctx_var.set(str(prof["num_ctx"]))
            if "num_predict" in prof:
                self.ai_num_predict_var.set(str(prof["num_predict"]))
            if "temperature" in prof:
                self.ai_temperature_var.set(str(prof["temperature"]))
            if "api_key_env" in prof:
                self.ai_api_key_env_var.set(prof["api_key_env"])
            if notify:
                messagebox.showinfo("Профиль применен", f"Применен ИИ-профиль: {profile_name}")
        self._update_ai_visibility()

    def _open_provider_key_url(self, event=None) -> None:
        profile_name = self.ai_provider_profile_var.get()
        if profile_name in AI_PROVIDER_PROFILES:
            url = AI_PROVIDER_PROFILES[profile_name].get("get_key_url")
            if url:
                import webbrowser
                webbrowser.open(url)

    def _update_ai_visibility(self) -> None:
        profile_name = self.ai_provider_profile_var.get()
        if profile_name in AI_PROVIDER_PROFILES:
            # Hide custom fields
            if hasattr(self, 'lbl_provider_type') and self.lbl_provider_type.winfo_exists():
                self.lbl_provider_type.grid_remove()
                self.combo_provider_type.grid_remove()
                self.lbl_endpoint.grid_remove()
                self.entry_endpoint.grid_remove()
            
            url = AI_PROVIDER_PROFILES[profile_name].get("get_key_url")
            if url and hasattr(self, 'lbl_get_key') and self.lbl_get_key.winfo_exists():
                self.lbl_get_key.pack(side=LEFT, padx=(12, 0))
            elif hasattr(self, 'lbl_get_key') and self.lbl_get_key.winfo_exists():
                self.lbl_get_key.pack_forget()
        else:
            # Show custom fields
            if hasattr(self, 'lbl_provider_type') and self.lbl_provider_type.winfo_exists():
                self.lbl_provider_type.grid()
                self.combo_provider_type.grid()
                self.lbl_endpoint.grid()
                self.entry_endpoint.grid()
            if hasattr(self, 'lbl_get_key') and self.lbl_get_key.winfo_exists():
                self.lbl_get_key.pack_forget()

    def _add_labeled_entry(
        self,
        parent: object,
        label_text: str,
        text_var: StringVar,
        row: int,
        show: str | None = None,
    ) -> None:
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=W, padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=text_var, width=60, show=show)
        entry.grid(row=row, column=1, sticky=W, pady=4)

    def _add_token_row(self, parent: object, row: int) -> None:
        label = ttk.Label(parent, text="GitHub Token (необязательно)")
        label.grid(row=row, column=0, sticky=W, padx=(0, 8), pady=4)
        token_frame = ttk.Frame(parent)
        token_frame.grid(row=row, column=1, sticky=W, pady=4)
        self.entry_github_token = ttk.Entry(token_frame, textvariable=self.token_var, width=34, show="*")
        self.entry_github_token.pack(side=LEFT)
        
        def toggle_github_token_visibility():
            if self.entry_github_token.cget("show") == "":
                self.entry_github_token.config(show="*")
            else:
                self.entry_github_token.config(show="")
                
        ttk.Button(token_frame, text="👁 Показать", command=toggle_github_token_visibility).pack(side=LEFT, padx=(4, 0))
        
        # OAUTH frame
        oauth_frame = ttk.Frame(parent)
        oauth_frame.grid(row=row+1, column=1, sticky=W, pady=(8, 12))
        
        btn_oauth = ttk.Button(oauth_frame, text="Если нет ключа: Авторизоваться через браузер", command=self._start_github_oauth)
        btn_oauth.pack(side=LEFT, padx=(0, 8))
        
        btn_cli = ttk.Button(oauth_frame, text="Импорт из GitHub CLI", command=self._import_gh_cli_token)
        btn_cli.pack(side=LEFT)
        
        actions_frame = ttk.Frame(parent)
        actions_frame.grid(row=row+2, column=1, sticky=W, pady=4)
        
        ttk.Button(actions_frame, text="Сохранить на ПК", command=self._save_github_token_to_store).pack(
            side=LEFT, padx=(0, 6)
        )
        ttk.Button(actions_frame, text="Загрузить", command=self._load_github_token_from_store).pack(
            side=LEFT, padx=(6, 0)
        )
        ttk.Button(actions_frame, text="Удалить", command=self._delete_github_token_from_store).pack(
            side=LEFT, padx=(6, 0)
        )
        
        ttk.Label(parent, textvariable=self.saved_token_status_var).grid(row=row+2, column=2, sticky=W, padx=(8, 0))

    def _start_github_oauth(self) -> None:
        if self.ai_busy: return
        
        # Если ключ уже есть (в текстовом поле или в DPAPI), предупреждаем пользователя
        current_token = self.token_var.get().strip()
        if current_token:
            import tkinter.messagebox as mb
            if not mb.askyesno("GitHub OAuth", "У вас уже сохранен ключ (Token)!\n\nАвторизация через браузер нужна ТОЛЬКО если у вас еще нет ключа. Вы уверены, что хотите авторизоваться заново?"):
                return
                
        self.ai_busy = True
        self.status_var.set("Запуск GitHub OAuth...")
        
        def _worker():
            try:
                auth = GitHubOAuthDeviceFlow()
                device_info = auth.request_device_code()
                user_code = device_info["user_code"]
                verification_uri = device_info["verification_uri"]
                
                # Показываем код юзеру
                def _show_code():
                    import tkinter.messagebox as mb
                    
                    copy_to_clipboard_async(user_code, tk_widget=self.root)
                    webbrowser.open(verification_uri)
                    mb.showinfo(
                        "Авторизация GitHub",
                        f"Сейчас откроется браузер.\n\nВаш код подтверждения: {user_code}\n(Код гарантированно скопирован в буфер обмена!)\n\nНа странице GitHub просто кликните на первое поле и нажмите Ctrl+V, чтобы код вставился автоматически."
                    )
                self.root.after(0, _show_code)
                
                def status_cb(msg):
                    self.root.after(0, lambda: self.status_var.set(msg))
                    
                token = auth.poll_for_token(device_info["device_code"], device_info.get("interval", 5), status_cb)
                
                def _success():
                    self.token_var.set(token)
                    self._save_github_token_to_store()
                    self.status_var.set("Успешно авторизовано!")
                    self.ai_busy = False
                    
                self.root.after(0, _success)
            except Exception as e:
                def _fail():
                    import tkinter.messagebox as mb
                    mb.showerror("Ошибка OAuth", str(e))
                    self.status_var.set("Ошибка авторизации")
                    self.ai_busy = False
                self.root.after(0, _fail)
                
        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _import_gh_cli_token(self) -> None:
        token = get_github_cli_token()
        if token:
            self.token_var.set(token)
            self._save_github_token_to_store()
            import tkinter.messagebox as mb
            mb.showinfo("GitHub CLI", "Токен успешно импортирован из gh cli!")
        else:
            import tkinter.messagebox as mb
            mb.showwarning("GitHub CLI", "Не удалось найти токен. Убедитесь, что gh установлен и авторизован (gh auth login).")

    def _add_output_row(self, parent: object, row: int) -> None:
        label = ttk.Label(parent, text="Папка сохранения")
        label.grid(row=row, column=0, sticky=W, padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=self.output_var, width=60)
        entry.grid(row=row, column=1, sticky=W, pady=4)
        ttk.Button(parent, text="Обзор", command=self.browse_output_folder).grid(row=row, column=2, padx=(8, 0))

    def browse_output_folder(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_var.get() or str(ROOT_DIR))
        if selected:
            self.output_var.set(selected)

    def _refresh_saved_token_status(self) -> None:
        try:
            if has_secret(DEFAULT_SECRET_NAME):
                status = "есть, Windows DPAPI"
                if not self.token_var.get().strip():
                    self.token_var.set("***")
            else:
                status = "не сохранен"
                if self.token_var.get().strip() == "***":
                    self.token_var.set("")
        except SecretStoreError as exc:
            status = f"ошибка: {exc}"
        self.saved_token_status_var.set(f"Сохраненный token: {status}")

    def _save_github_token_to_store(self) -> None:
        token = self.token_var.get().strip()
        if not token:
            messagebox.showinfo("GitHub Token", "Введите token в поле, затем нажмите сохранение.")
            return
        try:
            store_secret(DEFAULT_SECRET_NAME, token)
        except SecretStoreError as exc:
            messagebox.showerror("GitHub Token", f"Не удалось сохранить token локально:\n{exc}")
            self._refresh_saved_token_status()
            return
        self.token_var.set("")
        self._refresh_saved_token_status()
        self._append_log("GitHub token сохранен локально через Windows DPAPI; поле очищено.")

    def _load_github_token_from_store(self) -> None:
        try:
            token = load_secret(DEFAULT_SECRET_NAME)
        except SecretStoreError as exc:
            messagebox.showerror("GitHub Token", f"Не удалось загрузить token:\n{exc}")
            self._refresh_saved_token_status()
            return
        if not token:
            messagebox.showinfo("GitHub Token", "Сохраненный GitHub token не найден.")
            self._refresh_saved_token_status()
            return
        self.token_var.set(token)
        self._refresh_saved_token_status()
        self._append_log("GitHub token загружен из локального protected storage.")

    def _delete_github_token_from_store(self) -> None:
        try:
            deleted = delete_secret(DEFAULT_SECRET_NAME)
        except SecretStoreError as exc:
            messagebox.showerror("GitHub Token", f"Не удалось удалить token:\n{exc}")
            self._refresh_saved_token_status()
            return
        self._refresh_saved_token_status()
        if deleted:
            self._append_log("GitHub token удален из локального хранилища.")
        else:
            self._append_log("Сохраненный GitHub token не найден.")

    def _ai_secret_name(self) -> str:
        return secret_name_for_ai_provider(self.ai_provider_type_var.get(), self.ai_endpoint_var.get())

    def _refresh_saved_ai_key_status(self) -> None:
        provider_type = self.ai_provider_type_var.get().strip()
        if provider_type == AI_PROVIDER_OLLAMA:
            self.saved_ai_key_status_var.set("AI API key: не требуется")
            if self.ai_api_key_var.get().strip() == "***":
                self.ai_api_key_var.set("")
            return
        try:
            if has_secret(self._ai_secret_name()):
                status = "есть, Windows DPAPI"
                if not self.ai_api_key_var.get().strip():
                    self.ai_api_key_var.set("***")
            else:
                status = "не сохранен"
                if self.ai_api_key_var.get().strip() == "***":
                    self.ai_api_key_var.set("")
        except SecretStoreError as exc:
            status = f"ошибка: {exc}"
        self.saved_ai_key_status_var.set(f"AI API key: {status}")

    def _save_ai_api_key_to_store(self) -> None:
        if self.ai_provider_type_var.get().strip() == AI_PROVIDER_OLLAMA:
            messagebox.showinfo("AI API key", "Для Ollama API key не требуется.")
            self._refresh_saved_ai_key_status()
            return
        token = self.ai_api_key_var.get().strip()
        if not token:
            messagebox.showinfo("AI API key", "Введите API key в поле, затем нажмите сохранение.")
            return
        try:
            store_secret(self._ai_secret_name(), token)
        except SecretStoreError as exc:
            messagebox.showerror("AI API key", f"Не удалось сохранить API key локально:\n{exc}")
            self._refresh_saved_ai_key_status()
            return
        self.ai_api_key_var.set("")
        self._refresh_saved_ai_key_status()
        self._append_log("AI API key сохранен локально через Windows DPAPI; поле очищено.")

    def _load_ai_api_key_from_store(self) -> None:
        if self.ai_provider_type_var.get().strip() == AI_PROVIDER_OLLAMA:
            messagebox.showinfo("AI API key", "Для Ollama API key не требуется.")
            self._refresh_saved_ai_key_status()
            return
        try:
            token = load_secret(self._ai_secret_name())
        except SecretStoreError as exc:
            messagebox.showerror("AI API key", f"Не удалось загрузить API key:\n{exc}")
            self._refresh_saved_ai_key_status()
            return
        if not token:
            messagebox.showinfo("AI API key", "Сохраненный AI API key не найден.")
            self._refresh_saved_ai_key_status()
            return
        self.ai_api_key_var.set(token)
        self._refresh_saved_ai_key_status()
        self._append_log("AI API key загружен из локального protected storage.")

    def _delete_ai_api_key_from_store(self) -> None:
        try:
            deleted = delete_secret(self._ai_secret_name())
        except SecretStoreError as exc:
            messagebox.showerror("AI API key", f"Не удалось удалить API key:\n{exc}")
            self._refresh_saved_ai_key_status()
            return
        self._refresh_saved_ai_key_status()
        if deleted:
            self._append_log("AI API key удален из локального хранилища.")
        else:
            self._append_log("Сохраненный AI API key не найден.")

    def open_output_folder(self) -> None:
        output = Path(self.output_var.get().strip())
        if not output.exists():
            messagebox.showinfo("Папка", "Папка сохранения пока не существует.")
            return
        try:
            import os

            os.startfile(str(output))
        except Exception as exc:
            messagebox.showerror("Папка", f"Не удалось открыть папку:\n{exc}")

    def open_debug_log(self) -> None:
        if not self.debug_log_file.exists():
            messagebox.showinfo("Debug-лог", "Файл debug-лога пока не создан.")
            return
        try:
            import os

            os.startfile(str(self.debug_log_file))
        except Exception as exc:
            messagebox.showerror("Debug-лог", f"Не удалось открыть debug-лог:\n{exc}")

    def _append_log(self, message: str) -> None:
        if not self.log_text:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert(END, f"{message}\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _append_log_batch(self, messages: list[str]) -> None:
        if not self.log_text or not messages:
            return
        self.log_text.configure(state="normal")
        self.log_text.insert(END, "\n".join(messages) + "\n")
        self.log_text.see(END)
        self.log_text.configure(state="disabled")

    def _update_runtime_status_from_log(self, message: str) -> None:
        if not self.is_running:
            return
        line = re.sub(r"^\[[^\]]+\]\s*", "", message).strip()
        if not line:
            return

        if "Достигнут лимит GitHub API. Ожидание" in line:
            self.status_var.set("Ожидание лимита GitHub API...")
        elif line.startswith("Авто-режим поиска:"):
            self.status_var.set("Настройка режима поиска...")
        elif line.startswith("Режим поиска:"):
            self.status_var.set("Подготовка поиска...")
        elif line.startswith("Сбор диапазона"):
            self.status_var.set("Идет поиск репозиториев...")
        elif line.startswith("Найдено репозиториев:"):
            self.status_var.set(line)
        elif line.startswith("Начинаем скачивание репозиториев:"):
            self.status_var.set("Начинаем скачивание репозиториев...")
        elif line.startswith("Пакет "):
            self.status_var.set(line)
        elif line.startswith("Старт клонирования:"):
            self.status_var.set("Клонирование репозиториев...")
        elif line.startswith("Клонирование идет:"):
            self.status_var.set("Клонирование (в процессе)...")
        elif line.startswith("AI-фильтр:"):
            self.status_var.set("AI-проверка релевантности...")
        elif line.startswith("Повтор "):
            self.status_var.set(line)
        elif line.startswith("Ожидание перед повтором"):
            self.status_var.set(line)

    def _debug(self, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] {redact_sensitive_text(message)}\n"
        with self._debug_lock:
            with self.debug_log_file.open("a", encoding="utf-8") as handle:
                handle.write(line)

    def _config_for_debug(self, config: RunConfig) -> dict[str, object]:
        token_value = config.token.strip()
        token_masked = "***" if token_value else ""
        return {
            "query": config.query,
            "output_root": str(config.output_root),
            "token": token_masked,
            "min_stars": config.min_stars,
            "language": config.language,
            "include_forks": config.include_forks,
            "include_archived": config.include_archived,
            "created_after": config.created_after.isoformat(),
            "created_before": config.created_before.isoformat(),
            "max_age_years": config.max_age_years,
            "sort": config.sort,
            "order": config.order,
            "max_repos": config.max_repos,
            "batch_size": config.batch_size,
            "workers": config.workers,
            "clone_timeout": config.clone_timeout,
            "clone_depth": config.clone_depth,
            "clone_partial": config.clone_partial,
            "clone_single_branch": config.clone_single_branch,
            "clone_no_tags": config.clone_no_tags,
            "retry_failed_clones": config.retry_failed_clones,
            "retry_delay_seconds": config.retry_delay_seconds,
            "skip_existing": config.skip_existing,
            "no_sharding": config.no_sharding,
            "dry_run": config.dry_run,
            "ai_filter_enabled": config.ai_filter_enabled,
            "ai_provider_type": config.ai_provider_type,
            "ai_filter_endpoint": config.ai_filter_endpoint,
            "ai_filter_model": config.ai_filter_model,
            "ai_api_key": "***" if config.ai_api_key.strip() else "",
            "ai_filter_timeout": config.ai_filter_timeout,
            "ai_temperature": config.ai_temperature,
            "ai_num_ctx": config.ai_num_ctx,
            "ai_num_predict": config.ai_num_predict,
            "ai_filter_min_score": config.ai_filter_min_score,
            "ai_filter_max_reviews": config.ai_filter_max_reviews,
            "include_keywords": list(config.include_keywords),
            "exclude_keywords": list(config.exclude_keywords),
            "incremental": config.incremental,
            "export_sqlite": str(config.export_sqlite) if config.export_sqlite else "",
            "export_csv": config.export_csv,
            "export_ai_ready": config.export_ai_ready,
            "graphql_enrich": config.graphql_enrich,
            "graphql_batch_size": config.graphql_batch_size,
            "deep_relevance_enabled": config.deep_relevance_enabled,
            "deep_relevance_max_repos": config.deep_relevance_max_repos,
            "deep_relevance_min_score": config.deep_relevance_min_score,
            "search_profile": self.search_profile_var.get().strip(),
            "ai_custom_prompt": config.ai_custom_prompt,
        }

    def _set_running(self, running: bool) -> None:
        self.is_running = running
        if not running:
            self._stop_status_animation()
            self._set_progress_mode("determinate")
        if self.start_button:
            self.start_button.configure(state="disabled" if running else "normal")
        if self.preview_button:
            self.preview_button.configure(state="disabled" if running else "normal")
        if self.stop_button:
            self.stop_button.configure(state="normal" if running else "disabled")
        if self.profile_apply_button:
            self.profile_apply_button.configure(state="disabled" if running else "normal")
        if self.ai_provider_apply_button:
            self.ai_provider_apply_button.configure(state="disabled" if running else "normal")
        if self.ai_autopilot_button:
            self.ai_autopilot_button.configure(state="disabled" if running or self.ai_busy else "normal")
        if self.ai_autopilot_preview_button:
            self.ai_autopilot_preview_button.configure(state="disabled" if running or self.ai_busy else "normal")

    def _set_ai_busy(self, busy: bool) -> None:
        self.ai_busy = busy
        if not busy:
            self._stop_status_animation()
            self._set_progress_mode("determinate")
        if self.ai_apply_button:
            self.ai_apply_button.configure(state="disabled" if busy else "normal")
        if self.ai_autopilot_button:
            self.ai_autopilot_button.configure(state="disabled" if busy or self.is_running else "normal")
        if self.ai_autopilot_preview_button:
            self.ai_autopilot_preview_button.configure(state="disabled" if busy or self.is_running else "normal")
        if self.preview_button:
            self.preview_button.configure(state="disabled" if busy or self.is_running else "normal")
        if self.ai_provider_apply_button:
            self.ai_provider_apply_button.configure(state="disabled" if busy or self.is_running else "normal")

    def _set_models_loading(self, loading: bool) -> None:
        self.models_loading = loading
        if self.ai_models_button:
            self.ai_models_button.configure(state="disabled" if loading else "normal")

    def _next_run_id(self) -> int:
        self.run_id_counter += 1
        return self.run_id_counter

    def _drain_stale_run_events(self) -> None:
        preserved: list[tuple] = []
        dropped_count = 0
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            if not event:
                continue
            kind = str(event[0])
            if kind in {"log", "progress", "done", "preview_done", "cancelled", "error"}:
                dropped_count += 1
                continue
            preserved.append(event)
        for event in preserved:
            self.events.put(event)
        if dropped_count > 0:
            self._debug(f"Удалены устаревшие run-события из очереди: {dropped_count}")

    def _load_settings(self) -> None:
        if not SETTINGS_FILE.exists():
            self._debug("Настройки не найдены, используем значения по умолчанию.")
            self.created_before_var.set(date.today().isoformat())
            self._refresh_saved_token_status()
            self._refresh_saved_ai_key_status()
            return
        try:
            payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        except Exception:
            self._debug("Ошибка чтения gui_settings.json, используем значения по умолчанию.")
            self._refresh_saved_token_status()
            self._refresh_saved_ai_key_status()
            return

        self.query_var.set(str(payload.get("query", self.query_var.get())))
        self.output_var.set(str(payload.get("output", self.output_var.get())))
        legacy_token = str(payload.get("token", "")).strip()
        self.token_var.set("")
        if legacy_token:
            self._debug("Найден сохраненный token в настройках, токен очищен (безопасный режим).")
        self.min_stars_var.set(str(payload.get("min_stars", self.min_stars_var.get())))
        self.language_var.set(str(payload.get("language", self.language_var.get())))
        self.created_after_var.set(str(payload.get("created_after", self.created_after_var.get())))
        self.created_before_var.set(str(payload.get("created_before", self.created_before_var.get())))
        today_iso = date.today().isoformat()
        if self.created_before_var.get().strip() != today_iso:
            self.created_before_var.set(today_iso)
            self._debug(f"Дата конца автоматически обновлена до текущей даты: {today_iso}")
        self.max_age_years_var.set(str(payload.get("max_age_years", self.max_age_years_var.get())))
        self.max_repos_var.set(str(payload.get("max_repos", self.max_repos_var.get())))
        self.batch_size_var.set(str(payload.get("batch_size", self.batch_size_var.get())))
        self.workers_var.set(str(payload.get("workers", self.workers_var.get())))
        self.clone_timeout_var.set(str(payload.get("clone_timeout", self.clone_timeout_var.get())))
        self.clone_depth_var.set(str(payload.get("clone_depth", self.clone_depth_var.get())))
        self.clone_partial_var.set(bool(payload.get("clone_partial", self.clone_partial_var.get())))
        self.clone_single_branch_var.set(bool(payload.get("clone_single_branch", self.clone_single_branch_var.get())))
        self.clone_no_tags_var.set(bool(payload.get("clone_no_tags", self.clone_no_tags_var.get())))
        self.retry_failed_var.set(str(payload.get("retry_failed_clones", self.retry_failed_var.get())))
        self.retry_delay_var.set(str(payload.get("retry_delay_seconds", self.retry_delay_var.get())))
        self.include_keywords_var.set(str(payload.get("include_keywords", self.include_keywords_var.get())))
        self.exclude_keywords_var.set(str(payload.get("exclude_keywords", self.exclude_keywords_var.get())))
        self.export_sqlite_var.set(str(payload.get("export_sqlite", self.export_sqlite_var.get())))
        self.export_csv_var.set(bool(payload.get("export_csv", self.export_csv_var.get())))
        self.export_ai_ready_var.set(bool(payload.get("export_ai_ready", self.export_ai_ready_var.get())))
        self.graphql_enrich_var.set(bool(payload.get("graphql_enrich", self.graphql_enrich_var.get())))
        self.graphql_batch_size_var.set(str(payload.get("graphql_batch_size", self.graphql_batch_size_var.get())))
        self.deep_relevance_var.set(
            bool(payload.get("deep_relevance_enabled", payload.get("deep_relevance", self.deep_relevance_var.get())))
        )
        self.deep_relevance_max_repos_var.set(
            str(payload.get("deep_relevance_max_repos", self.deep_relevance_max_repos_var.get()))
        )
        self.deep_relevance_min_score_var.set(
            str(payload.get("deep_relevance_min_score", self.deep_relevance_min_score_var.get()))
        )
        loaded_sort = str(payload.get("sort", SORT_OPTIONS[self.sort_var.get()]))
        loaded_order = str(payload.get("order", ORDER_OPTIONS[self.order_var.get()]))
        self.sort_var.set(SORT_OPTIONS_REVERSE.get(loaded_sort, loaded_sort))
        self.order_var.set(ORDER_OPTIONS_REVERSE.get(loaded_order, loaded_order))
        self.include_forks_var.set(bool(payload.get("include_forks", self.include_forks_var.get())))
        self.include_archived_var.set(bool(payload.get("include_archived", self.include_archived_var.get())))
        self.skip_existing_var.set(bool(payload.get("skip_existing", self.skip_existing_var.get())))
        self.no_sharding_var.set(bool(payload.get("no_sharding", self.no_sharding_var.get())))
        self.dry_run_var.set(bool(payload.get("dry_run", self.dry_run_var.get())))
        self.incremental_var.set(bool(payload.get("incremental", self.incremental_var.get())))

        self.ai_provider_type_var.set(str(payload.get("ai_provider_type", payload.get("ai_provider", self.ai_provider_type_var.get()))))
        self.ai_model_var.set(str(payload.get("ai_model", self.ai_model_var.get())))
        self.ai_endpoint_var.set(str(payload.get("ai_endpoint", self.ai_endpoint_var.get())))
        self.ai_api_key_var.set("")
        self.ai_api_key_env_var.set(str(payload.get("ai_api_key_env", self.ai_api_key_env_var.get())))
        self.ai_timeout_var.set(str(payload.get("ai_timeout", self.ai_timeout_var.get())))
        self.ai_temperature_var.set(str(payload.get("ai_temperature", self.ai_temperature_var.get())))
        self.ai_num_ctx_var.set(str(payload.get("ai_num_ctx", self.ai_num_ctx_var.get())))
        self.ai_num_predict_var.set(str(payload.get("ai_num_predict", self.ai_num_predict_var.get())))
        loaded_ai_profile = str(payload.get("ai_provider_profile", self.ai_provider_profile_var.get())).strip()
        if loaded_ai_profile == "Вручную" or loaded_ai_profile in AI_PROVIDER_PROFILES:
            self.ai_provider_profile_var.set(loaded_ai_profile)
        self.ai_auto_folder_var.set(bool(payload.get("ai_auto_folder", self.ai_auto_folder_var.get())))
        loaded_profile = str(payload.get("search_profile", self.search_profile_var.get())).strip()
        if loaded_profile in SEARCH_PROFILES:
            self.search_profile_var.set(loaded_profile)
        self.ai_filter_enabled_var.set(bool(payload.get("ai_filter_enabled", self.ai_filter_enabled_var.get())))
        self.ai_filter_min_score_var.set(str(payload.get("ai_filter_min_score", self.ai_filter_min_score_var.get())))
        self.ai_filter_max_reviews_var.set(
            str(payload.get("ai_filter_max_reviews", self.ai_filter_max_reviews_var.get()))
        )
        self.ai_custom_prompt_var.set(str(payload.get("ai_custom_prompt", self.ai_custom_prompt_var.get())))
        ai_task = str(payload.get("ai_task", "")).strip()
        if ai_task and self.ai_task_text:
            self.ai_task_text.delete("1.0", END)
            self.ai_task_text.insert("1.0", ai_task)
        self._refresh_saved_token_status()
        self._refresh_saved_ai_key_status()
        self._debug("Настройки успешно загружены из gui_settings.json.")

    def _save_settings(self, first_run_completed: bool | None = None) -> None:
        sort_value = SORT_OPTIONS.get(self.sort_var.get(), self.sort_var.get())
        order_value = ORDER_OPTIONS.get(self.order_var.get(), self.order_var.get())
        ai_task = self.ai_task_text.get("1.0", END).strip() if self.ai_task_text else ""
        existing_first_run = False
        if SETTINGS_FILE.exists():
            try:
                existing_payload = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                existing_first_run = bool(existing_payload.get("first_run_completed", False))
            except Exception:
                pass
        final_first_run = bool(first_run_completed) if first_run_completed is not None else existing_first_run

        payload = {
            "query": self.query_var.get().strip(),
            "output": self.output_var.get().strip(),
            "token": "",
            "min_stars": self.min_stars_var.get().strip(),
            "language": self.language_var.get().strip(),
            "created_after": self.created_after_var.get().strip(),
            "created_before": self.created_before_var.get().strip(),
            "max_age_years": self.max_age_years_var.get().strip(),
            "max_repos": self.max_repos_var.get().strip(),
            "batch_size": self.batch_size_var.get().strip(),
            "workers": self.workers_var.get().strip(),
            "clone_timeout": self.clone_timeout_var.get().strip(),
            "clone_depth": self.clone_depth_var.get().strip(),
            "clone_partial": self.clone_partial_var.get(),
            "clone_single_branch": self.clone_single_branch_var.get(),
            "clone_no_tags": self.clone_no_tags_var.get(),
            "retry_failed_clones": self.retry_failed_var.get().strip(),
            "retry_delay_seconds": self.retry_delay_var.get().strip(),
            "include_keywords": self.include_keywords_var.get().strip(),
            "exclude_keywords": self.exclude_keywords_var.get().strip(),
            "export_sqlite": self.export_sqlite_var.get().strip(),
            "graphql_enrich": self.graphql_enrich_var.get(),
            "graphql_batch_size": self.graphql_batch_size_var.get().strip(),
            "deep_relevance_enabled": self.deep_relevance_var.get(),
            "deep_relevance_max_repos": self.deep_relevance_max_repos_var.get().strip(),
            "deep_relevance_min_score": self.deep_relevance_min_score_var.get().strip(),
            "sort": sort_value,
            "order": order_value,
            "include_forks": self.include_forks_var.get(),
            "include_archived": self.include_archived_var.get(),
            "skip_existing": self.skip_existing_var.get(),
            "no_sharding": self.no_sharding_var.get(),
            "dry_run": self.dry_run_var.get(),
            "incremental": self.incremental_var.get(),
            "ai_model": self.ai_model_var.get().strip(),
            "ai_provider_type": self.ai_provider_type_var.get().strip(),
            "ai_endpoint": self.ai_endpoint_var.get().strip(),
            "ai_api_key": "",
            "ai_api_key_env": self.ai_api_key_env_var.get().strip(),
            "ai_timeout": self.ai_timeout_var.get().strip(),
            "ai_temperature": self.ai_temperature_var.get().strip(),
            "ai_num_ctx": self.ai_num_ctx_var.get().strip(),
            "ai_num_predict": self.ai_num_predict_var.get().strip(),
            "ai_provider_profile": self.ai_provider_profile_var.get().strip(),
            "ai_auto_folder": self.ai_auto_folder_var.get(),
            "search_profile": self.search_profile_var.get().strip(),
            "ai_filter_enabled": self.ai_filter_enabled_var.get(),
            "ai_filter_min_score": self.ai_filter_min_score_var.get().strip(),
            "ai_filter_max_reviews": self.ai_filter_max_reviews_var.get().strip(),
            "ai_custom_prompt": self.ai_custom_prompt_var.get().strip(),
            "export_csv": self.export_csv_var.get(),
            "export_ai_ready": self.export_ai_ready_var.get(),
            "ai_task": ai_task,
            "first_run_completed": final_first_run,
        }
        atomic_write_text(SETTINGS_FILE, json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self._debug("Настройки сохранены в gui_settings.json.")

    def _normalize_user_query(self, raw_query: str) -> tuple[str, str | None]:
        return normalize_query_for_search(raw_query)

    def _build_config(self) -> RunConfig:
        raw_query = self.query_var.get().strip()
        self._debug(
            f"_build_config: raw_query='{raw_query}', output='{self.output_var.get().strip()}', "
            f"dry_run={self.dry_run_var.get()}, skip_existing={self.skip_existing_var.get()}"
        )
        if not raw_query:
            raise ValueError("Поле запроса обязательно.")
        query, normalized_message = self._normalize_user_query(raw_query)
        self._last_query_normalization_message = normalized_message
        if normalized_message:
            self._debug(f"_build_config: нормализация запроса применена. query='{query}'")
        output = self.output_var.get().strip()
        if not output:
            raise ValueError("Укажите папку сохранения.")

        manual_token = self.token_var.get().strip()
        if manual_token == "***":
            manual_token = ""
            
        env_token = os.environ.get("GITHUB_TOKEN", "").strip()
        saved_token = ""
        if not manual_token and not env_token:
            try:
                saved_token = load_secret(DEFAULT_SECRET_NAME)
            except SecretStoreError as exc:
                self._debug(f"GitHub token protected storage недоступен: {exc}")
        token_value = manual_token or env_token or saved_token
        if manual_token:
            self._last_token_source = "manual"
        elif env_token:
            self._last_token_source = "env"
        elif saved_token:
            self._last_token_source = "saved"
        else:
            self._last_token_source = "none"

        created_after = parse_iso_date(self.created_after_var.get().strip(), "дата начала")
        today_iso = date.today().isoformat()
        if self.created_before_var.get().strip() != today_iso:
            self.created_before_var.set(today_iso)
            self._append_log(f"Дата конца автоматически обновлена до сегодня: {today_iso}")
            self._debug(f"_build_config: created_before принудительно обновлена до {today_iso}")
        created_before = parse_iso_date(today_iso, "дата конца")

        min_stars = int(self.min_stars_var.get().strip())
        max_age_years = int(self.max_age_years_var.get().strip() or "0")
        max_repos = int(self.max_repos_var.get().strip() or "0")
        batch_size = int(self.batch_size_var.get().strip())
        workers = int(self.workers_var.get().strip())
        clone_timeout = int(self.clone_timeout_var.get().strip())
        clone_depth = int(self.clone_depth_var.get().strip() or "0")
        retry_failed = int(self.retry_failed_var.get().strip())
        retry_delay = int(self.retry_delay_var.get().strip())
        ai_filter_timeout = int(self.ai_timeout_var.get().strip())
        ai_temperature = float(self.ai_temperature_var.get().strip())
        ai_num_ctx = int(self.ai_num_ctx_var.get().strip())
        ai_num_predict = int(self.ai_num_predict_var.get().strip())
        ai_filter_min_score = float(self.ai_filter_min_score_var.get().strip())
        ai_filter_max_reviews = int(self.ai_filter_max_reviews_var.get().strip())
        ai_filter_enabled = self.ai_filter_enabled_var.get()
        include_keywords = parse_keyword_list(self.include_keywords_var.get())
        exclude_keywords = parse_keyword_list(self.exclude_keywords_var.get())
        export_sqlite_raw = self.export_sqlite_var.get().strip()
        export_sqlite = Path(export_sqlite_raw) if export_sqlite_raw else None
        graphql_batch_size = int(self.graphql_batch_size_var.get().strip())
        deep_relevance_max_repos = int(self.deep_relevance_max_repos_var.get().strip())
        deep_relevance_min_score = float(self.deep_relevance_min_score_var.get().strip())

        if min_stars < 0:
            raise ValueError("Минимум звезд должен быть не меньше 0.")
        if max_age_years < 0:
            raise ValueError("Возраст репозиториев должен быть не меньше 0.")
        if max_repos < 0:
            raise ValueError("Максимум репозиториев должен быть не меньше 0.")
        if batch_size < 1:
            raise ValueError("Размер пакета должен быть не меньше 1.")
        if workers < 1:
            raise ValueError("Количество потоков должно быть не меньше 1.")
        if clone_timeout < 10:
            raise ValueError("Таймаут клонирования должен быть не меньше 10 секунд.")
        if clone_depth < 0:
            raise ValueError("Глубина clone должна быть не меньше 0.")
        if retry_failed < 0:
            raise ValueError("Количество повторов должно быть не меньше 0.")
        if retry_delay < 0:
            raise ValueError("Пауза перед повтором должна быть не меньше 0.")
        if ai_filter_timeout < 5:
            raise ValueError("Таймаут AI должен быть не меньше 5 секунд.")
        if ai_temperature < 0.0 or ai_temperature > 2.0:
            raise ValueError("temperature должна быть в диапазоне 0..2.")
        if ai_num_ctx < 512:
            raise ValueError("num_ctx должен быть не меньше 512.")
        if ai_num_predict < 16:
            raise ValueError("num_predict должен быть не меньше 16.")
        if ai_filter_min_score < 0.0 or ai_filter_min_score > 1.0:
            raise ValueError("Порог релевантности AI должен быть в диапазоне 0..1.")
        if ai_filter_max_reviews < 1:
            raise ValueError("Макс. AI-проверок должен быть не меньше 1.")
        if graphql_batch_size < 1 or graphql_batch_size > 50:
            raise ValueError("GraphQL batch должен быть в диапазоне 1..50.")
        if deep_relevance_max_repos < 1:
            raise ValueError("Deep max repos должен быть не меньше 1.")
        if deep_relevance_min_score < 0.0 or deep_relevance_min_score > 1.0:
            raise ValueError("Deep min score должен быть в диапазоне 0..1.")
        if ai_filter_enabled and not self.ai_endpoint_var.get().strip():
            raise ValueError("Для AI-фильтра укажите AI endpoint/Base URL.")
        if ai_filter_enabled and not self.ai_model_var.get().strip():
            raise ValueError("Для AI-фильтра выберите модель AI provider.")

        sort_value = SORT_OPTIONS.get(self.sort_var.get())
        order_value = ORDER_OPTIONS.get(self.order_var.get())
        if sort_value is None:
            raise ValueError("Некорректная сортировка.")
        if order_value is None:
            raise ValueError("Некорректный порядок.")

        ai_provider_type = self.ai_provider_type_var.get().strip() or AI_PROVIDER_OLLAMA
        ai_api_key_value = ""
        if ai_provider_type != AI_PROVIDER_OLLAMA:
            manual_ai_key = self.ai_api_key_var.get().strip()
            if manual_ai_key == "***":
                manual_ai_key = ""
                
            env_name = self.ai_api_key_env_var.get().strip()
            env_ai_key = os.environ.get(env_name, "").strip() if env_name else ""
            saved_ai_key = ""
            if not manual_ai_key and not env_ai_key:
                try:
                    saved_ai_key = load_secret(self._ai_secret_name())
                except SecretStoreError as exc:
                    self._debug(f"AI API key protected storage недоступен: {exc}")
            ai_api_key_value = manual_ai_key or env_ai_key or saved_ai_key
            if manual_ai_key:
                self._last_ai_key_source = "manual"
            elif env_ai_key:
                self._last_ai_key_source = f"env:{env_name}"
            elif saved_ai_key:
                self._last_ai_key_source = "saved"
            else:
                self._last_ai_key_source = "none"
        else:
            self._last_ai_key_source = "not-required"

        config = RunConfig(
            query=query,
            output_root=Path(output),
            token=token_value,
            min_stars=min_stars,
            language=self.language_var.get().strip(),
            include_forks=self.include_forks_var.get(),
            include_archived=self.include_archived_var.get(),
            created_after=created_after,
            created_before=created_before,
            max_age_years=max_age_years,
            sort=sort_value,
            order=order_value,
            max_repos=max_repos,
            batch_size=batch_size,
            workers=workers,
            clone_timeout=clone_timeout,
            clone_depth=clone_depth,
            clone_partial=self.clone_partial_var.get(),
            clone_single_branch=self.clone_single_branch_var.get(),
            clone_no_tags=self.clone_no_tags_var.get(),
            retry_failed_clones=retry_failed,
            retry_delay_seconds=retry_delay,
            skip_existing=self.skip_existing_var.get(),
            no_sharding=self.no_sharding_var.get(),
            dry_run=self.dry_run_var.get(),
            ai_filter_enabled=ai_filter_enabled,
            ai_provider_type=ai_provider_type,
            ai_filter_endpoint=self.ai_endpoint_var.get().strip(),
            ai_filter_model=self.ai_model_var.get().strip(),
            ai_api_key=ai_api_key_value,
            ai_filter_timeout=ai_filter_timeout,
            ai_temperature=ai_temperature,
            ai_num_ctx=ai_num_ctx,
            ai_num_predict=ai_num_predict,
            ai_filter_min_score=ai_filter_min_score,
            ai_filter_max_reviews=ai_filter_max_reviews,
            include_keywords=include_keywords,
            exclude_keywords=exclude_keywords,
            incremental=self.incremental_var.get(),
            export_sqlite=export_sqlite,
            export_csv=self.export_csv_var.get(),
            export_ai_ready=self.export_ai_ready_var.get(),
            graphql_enrich=self.graphql_enrich_var.get(),
            graphql_batch_size=graphql_batch_size,
            deep_relevance_enabled=self.deep_relevance_var.get(),
            deep_relevance_max_repos=deep_relevance_max_repos,
            deep_relevance_min_score=deep_relevance_min_score,
            ai_custom_prompt=self.ai_custom_prompt_var.get().strip(),
        )
        validate_run_config(config)
        return config

    def refresh_ollama_models(self) -> None:
        if self.models_loading:
            self._debug("refresh_ollama_models: уже выполняется, пропуск.")
            return
        endpoint = self.ai_endpoint_var.get().strip()
        if not endpoint:
            self._debug("refresh_ollama_models: endpoint пустой.")
            messagebox.showerror("AI provider", "Укажите AI endpoint/Base URL.")
            return

        provider_cfg = AiProviderConfig(
            provider_type=self.ai_provider_type_var.get().strip() or AI_PROVIDER_OLLAMA,
            endpoint=endpoint,
            model=self.ai_model_var.get().strip(),
            api_key=self.ai_api_key_var.get().strip(),
            api_key_env=self.ai_api_key_env_var.get().strip(),
            timeout=30,
            temperature=0.0,
            num_ctx=4096,
            num_predict=128,
        )
        if provider_cfg.provider_type != AI_PROVIDER_OLLAMA and not provider_cfg.api_key and provider_cfg.api_key_env:
            provider_cfg = replace(
                provider_cfg,
                api_key=os.environ.get(provider_cfg.api_key_env, "").strip(),
            )
        if provider_cfg.provider_type != AI_PROVIDER_OLLAMA and not provider_cfg.api_key:
            try:
                provider_cfg = replace(provider_cfg, api_key=load_secret(self._ai_secret_name()))
            except SecretStoreError as exc:
                self._debug(f"AI API key protected storage недоступен для list models: {exc}")

        self._debug(
            f"Запрошено обновление моделей AI. provider={provider_cfg.provider_type}, endpoint={endpoint}"
        )
        self._set_models_loading(True)
        self.status_var.set("Загружаем список моделей AI...")
        self._append_log("AI provider: запрашиваем список моделей...")
        self.models_thread = threading.Thread(
            target=self._worker_fetch_models,
            args=(provider_cfg,),
            daemon=True,
        )
        self.models_thread.start()
        self.root.after(120, self._poll_events)

    def _worker_fetch_models(self, provider_cfg: AiProviderConfig) -> None:
        try:
            models = list_ai_models(provider_cfg, timeout=10)
            self._debug(f"Получено моделей AI provider: {len(models)}")
            self.events.put(("models_done", models))
        except Exception as exc:
            self._debug(f"Ошибка получения моделей AI provider: {exc}")
            is_local = "127.0.0.1" in provider_cfg.endpoint or "localhost" in provider_cfg.endpoint
            if is_local or provider_cfg.provider_type == AI_PROVIDER_OLLAMA:
                discovered = discover_local_models(timeout=5)
                if discovered:
                    new_provider, new_models = discovered
                    self.events.put(("models_auto_discovered", (new_provider, new_models)))
                    return
                else:
                    self.events.put(("models_not_found", "Модели ИИ не найдены. Убедитесь, что вы ввели корректный API ключ.\n\nВы можете использовать облачные сервисы (OpenRouter, Groq, Gemini и др.).\nВыберите подходящий профиль в выпадающем списке 'Профиль AI' и введите API ключ."))
                    return
            self.events.put(("models_error", str(exc)))

    def apply_ai_command(self) -> None:
        self._start_ai_plan(auto_start=False, auto_preview=False)

    def start_autopilot(self) -> None:
        self._start_ai_plan(auto_start=True, auto_preview=False)

    def start_autopilot_preview(self) -> None:
        self._start_ai_plan(auto_start=False, auto_preview=True)

    def _start_ai_plan(self, auto_start: bool, auto_preview: bool) -> None:
        if self.is_running:
            self._debug("_start_ai_plan: отклонено, активен запуск.")
            messagebox.showinfo("ИИ", "Нельзя менять параметры во время активного запуска.")
            return
        if self.ai_busy:
            self._debug("_start_ai_plan: уже выполняется.")
            return
        if not self.ai_task_text:
            self._debug("_start_ai_plan: поле ai_task_text недоступно.")
            return

        task_text = self.ai_task_text.get("1.0", END).strip()
        if not task_text:
            messagebox.showerror("ИИ", "Введите текст задачи для ИИ.")
            return
        if not self.ai_model_var.get().strip():
            messagebox.showerror("ИИ", "Выберите модель AI provider.")
            return
        if not self.ai_endpoint_var.get().strip():
            messagebox.showerror("ИИ", "Укажите AI endpoint/Base URL.")
            return

        try:
            timeout = int(self.ai_timeout_var.get().strip())
        except ValueError:
            messagebox.showerror("ИИ", "Таймаут AI должен быть целым числом.")
            return
        if timeout < 5:
            messagebox.showerror("ИИ", "Таймаут AI должен быть не меньше 5 секунд.")
            return
        try:
            ai_temperature = float(self.ai_temperature_var.get().strip())
            ai_num_ctx = int(self.ai_num_ctx_var.get().strip())
            ai_num_predict = int(self.ai_num_predict_var.get().strip())
        except ValueError:
            messagebox.showerror("ИИ", "temperature, num_ctx и num_predict должны быть числовыми.")
            return
        if ai_temperature < 0.0 or ai_temperature > 2.0:
            messagebox.showerror("ИИ", "temperature должна быть в диапазоне 0..2.")
            return
        if ai_num_ctx < 512:
            messagebox.showerror("ИИ", "num_ctx должен быть не меньше 512.")
            return
        if ai_num_predict < 16:
            messagebox.showerror("ИИ", "num_predict должен быть не меньше 16.")
            return

        ai_provider_type = self.ai_provider_type_var.get().strip() or AI_PROVIDER_OLLAMA
        ai_api_key_value = ""
        if ai_provider_type != AI_PROVIDER_OLLAMA:
            manual_ai_key = self.ai_api_key_var.get().strip()
            if manual_ai_key == "***":
                manual_ai_key = ""
            env_name = self.ai_api_key_env_var.get().strip()
            env_ai_key = os.environ.get(env_name, "").strip() if env_name else ""
            saved_ai_key = ""
            if not manual_ai_key and not env_ai_key:
                try:
                    saved_ai_key = load_secret(self._ai_secret_name())
                except SecretStoreError as exc:
                    self._debug(f"AI API key protected storage недоступен для planner: {exc}")
            ai_api_key_value = manual_ai_key or env_ai_key or saved_ai_key

        provider_cfg = AiProviderConfig(
            provider_type=ai_provider_type,
            endpoint=self.ai_endpoint_var.get().strip(),
            model=self.ai_model_var.get().strip(),
            api_key=ai_api_key_value,
            api_key_env=self.ai_api_key_env_var.get().strip(),
            timeout=timeout,
            temperature=ai_temperature,
            num_ctx=ai_num_ctx,
            num_predict=ai_num_predict,
        )

        self.autopilot_pending = auto_start
        self.autopilot_preview_pending = auto_preview
        self._set_ai_busy(True)
        if auto_start:
            self._start_status_animation("Автопилот: ИИ анализирует ТЗ")
            self._append_log("Автопилот: запускаем ИИ-анализ ТЗ...")
        elif auto_preview:
            self._start_status_animation("Автопилот: ИИ анализирует ТЗ для предпросмотра")
            self._append_log("Автопилот: готовим параметры и предпросмотр...")
        else:
            self._start_status_animation("ИИ анализирует задачу")
            self._append_log("ИИ: запускаем анализ задачи...")
        self._set_progress_mode("indeterminate")
        self._debug(
            "Запуск AI-команды. "
            f"autopilot={auto_start}; autopreview={auto_preview}; endpoint={provider_cfg.endpoint}; "
            f"model={provider_cfg.model}; timeout={provider_cfg.timeout}"
        )
        self.ai_thread = threading.Thread(
            target=self._worker_ai_plan,
            args=(task_text, provider_cfg),
            daemon=True,
        )
        self.ai_thread.start()
        self.root.after(120, self._poll_events)

    def _worker_ai_plan(self, task_text: str, provider_cfg: AiProviderConfig) -> None:
        try:
            plan = plan_search_task(task_text, provider_cfg)
            self._debug("AI-план успешно построен.")
            self.events.put(("ai_done", plan))
        except Exception as exc:
            self._debug(f"AI-план ошибка: {exc}\n{traceback.format_exc()}")
            self.events.put(("ai_error", str(exc)))

    @staticmethod
    def _to_int_or_default(raw_value: object, default: int = 0) -> int:
        try:
            return int(str(raw_value).strip())
        except Exception:
            return default

    def _apply_ai_plan_to_form(self, plan: object, autopilot_mode: bool = False) -> None:
        previous_max_repos = self._to_int_or_default(self.max_repos_var.get(), default=0)
        self.query_var.set(plan.query)
        self.min_stars_var.set(str(plan.min_stars))
        self.language_var.set(plan.language)
        self.max_age_years_var.set(str(plan.max_age_years))
        ai_max_repos = int(plan.max_repos)
        if ai_max_repos != 0 and ai_max_repos < 20:
            self._append_log(
                f"ИИ предложил слишком низкий лимит max_repos={ai_max_repos}; автоматически увеличено до 20."
            )
            self._debug(f"AI max_repos скорректирован: {ai_max_repos} -> 20")
            ai_max_repos = 20
        if autopilot_mode and ai_max_repos > 0:
            profile = SEARCH_PROFILES.get(self.search_profile_var.get().strip(), {})
            profile_floor = self._to_int_or_default(profile.get("max_repos"), default=0)
            learned_floor = max(previous_max_repos, profile_floor)
            if learned_floor > 0 and ai_max_repos < learned_floor:
                self._append_log(
                    "Автопилот: ИИ предложил слишком низкий лимит "
                    f"max_repos={ai_max_repos}; применен запомненный уровень {learned_floor}."
                )
                self._debug(
                    "autopilot max_repos floor applied: "
                    f"ai={ai_max_repos}, previous={previous_max_repos}, profile={profile_floor}, final={learned_floor}"
                )
                ai_max_repos = learned_floor
        self.max_repos_var.set(str(ai_max_repos))
        if autopilot_mode and ai_max_repos > 0:
            current_reviews = self._to_int_or_default(self.ai_filter_max_reviews_var.get(), default=0)
            target_reviews = min(160, max(30, ai_max_repos // 2))
            if current_reviews < target_reviews:
                self.ai_filter_max_reviews_var.set(str(target_reviews))
                self._append_log(
                    "Автопилот: увеличено Макс. AI-проверок "
                    f"{current_reviews} -> {target_reviews} под max_repos={ai_max_repos}."
                )
        self.batch_size_var.set(str(plan.batch_size))
        self.workers_var.set(str(plan.workers))
        self.clone_timeout_var.set(str(plan.clone_timeout))
        self.retry_failed_var.set(str(plan.retry_failed_clones))
        self.retry_delay_var.set(str(plan.retry_delay_seconds))
        self.include_forks_var.set(bool(plan.include_forks))
        self.include_archived_var.set(bool(plan.include_archived))
        self.sort_var.set(SORT_OPTIONS_REVERSE.get(plan.sort, "По звездам"))
        self.order_var.set(ORDER_OPTIONS_REVERSE.get(plan.order, "По убыванию"))

        if self.ai_auto_folder_var.get():
            current_output = Path(self.output_var.get().strip() or r"M:\Projects\GItHubProjektAI")
            base_path = current_output
            if (current_output / "repos").exists() or (current_output / "metadata").exists():
                base_path = current_output.parent
            elif getattr(self, "_last_ai_folder_name", None) and current_output.name == getattr(self, "_last_ai_folder_name", None):
                base_path = current_output.parent
                
            target = base_path / plan.folder_name
            self.output_var.set(str(target))
            self._last_ai_folder_name = plan.folder_name
            self._append_log(f"ИИ: выбрана папка проекта {target}")

    def start_preview_collection(self) -> None:
        if self.autopilot_enabled_var.get():
            self._start_ai_plan(auto_start=False, auto_preview=True)
            return

        if self.is_running:
            self._debug("Нажат Предпросмотр, но процесс уже выполняется. Игнорировано.")
            return
        self._debug("Нажат Предпросмотр. Начинаем сбор конфигурации.")
        try:
            base_config = self._build_config()
        except Exception as exc:
            self._debug(f"Ошибка валидации параметров preview: {exc}")
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        config = replace(base_config, dry_run=True)
        try:
            self._save_settings()
        except Exception as exc:
            self._debug(f"Ошибка сохранения настроек для preview: {exc}")
            self._append_log(f"Не удалось сохранить настройки: {exc}")

        self._debug(f"Конфигурация preview: {json.dumps(self._config_for_debug(config), ensure_ascii=False)}")
        run_id = self._next_run_id()
        self.active_run_id = run_id
        self._drain_stale_run_events()
        self._last_debug_progress = (-1, -1)
        self.cancel_event = threading.Event()
        self.progress_var.set(0.0)
        self.progress_text_var.set("0 / 0")
        self._append_log("-" * 80)
        self._append_log("Режим предпросмотра: выполняем только поиск и готовим список для ручного выбора.")
        if self._last_query_normalization_message:
            self._append_log(self._last_query_normalization_message)
        self._append_log(f"Запуск preview-запроса: {config.query}")
        self._append_log(f"Профиль качества: {self.search_profile_var.get().strip()}")
        self._append_log(
            "Параметры preview: "
            f"max_repos={config.max_repos}, ai_filter={config.ai_filter_enabled}, "
            f"ai_filter_min_score={config.ai_filter_min_score}, ai_filter_max_reviews={config.ai_filter_max_reviews}, "
            f"output={config.output_root}"
        )
        self._append_log(f"Debug-лог: {self.debug_log_file}")
        self._start_status_animation("Предпросмотр: поиск и оценка")
        self._set_progress_mode("indeterminate")
        self._set_running(True)

        self.worker_thread = threading.Thread(
            target=self._worker_preview,
            args=(config, self.cancel_event, run_id),
            daemon=True,
        )
        self.worker_thread.start()
        self._debug(f"Поток preview запущен: name={self.worker_thread.name}, alive={self.worker_thread.is_alive()}")
        self.root.after(120, self._poll_events)

    def _worker_preview(self, config: RunConfig, cancel_event: threading.Event, run_id: int) -> None:
        def send_log(message: str) -> None:
            self.events.put(("log", run_id, message))

        def send_progress(done: int, total: int) -> None:
            self.events.put(("progress", run_id, done, total))

        try:
            self._debug(f"_worker_preview стартовал run_id={run_id}")
            summary = run_collection(config, log=send_log, progress=send_progress, cancel_event=cancel_event)
            self._debug(
                "preview завершен успешно "
                f"run_id={run_id}; found={summary.found_count}; metadata={summary.metadata_file}"
            )
            self.events.put(("preview_done", run_id, summary))
        except RunCancelledError as exc:
            self._debug(f"preview отменен run_id={run_id}: {exc}")
            self.events.put(("cancelled", run_id, str(exc)))
        except Exception as exc:
            self._debug(f"preview исключение run_id={run_id}: {exc}\n{traceback.format_exc()}")
            self.events.put(("error", run_id, str(exc)))

    def _worker_download_selected(
        self,
        config: RunConfig,
        selected_repositories: list[Repo],
        metadata_file: Path | None,
        cancel_event: threading.Event,
        run_id: int,
    ) -> None:
        def send_log(message: str) -> None:
            self.events.put(("log", run_id, message))

        def send_progress(done: int, total: int) -> None:
            self.events.put(("progress", run_id, done, total))

        try:
            self._debug(
                f"_worker_download_selected стартовал run_id={run_id}; selected={len(selected_repositories)}"
            )
            summary = run_download_for_repositories(
                config=config,
                repositories=selected_repositories,
                metadata_file=metadata_file,
                log=send_log,
                progress=send_progress,
                cancel_event=cancel_event,
            )
            self._debug(
                "run_download_for_repositories завершен успешно "
                f"run_id={run_id}; found={summary.found_count}; cloned={summary.cloned_count}; "
                f"skipped={summary.skipped_count}; failed={summary.failed_count}; cancelled={summary.cancelled_count}"
            )
            self.events.put(("done", run_id, summary))
        except RunCancelledError as exc:
            self._debug(f"download_selected отменен run_id={run_id}: {exc}")
            self.events.put(("cancelled", run_id, str(exc)))
        except Exception as exc:
            self._debug(f"download_selected исключение run_id={run_id}: {exc}\n{traceback.format_exc()}")
            self.events.put(("error", run_id, str(exc)))

    @staticmethod
    def _truncate_text(value: str, limit: int = 140) -> str:
        text = " ".join((value or "").split())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    def _build_preview_summary_ru(self, repository: Repo) -> str:
        parts: list[str] = []
        if repository.language.strip():
            parts.append(f"Язык: {repository.language.strip()}")
        parts.append(f"Звезды: {repository.stargazers_count}")
        if repository.forks_count:
            parts.append(f"Forks: {repository.forks_count}")
        if repository.open_issues_count:
            parts.append(f"Issues: {repository.open_issues_count}")
        if repository.license_spdx_id.strip():
            parts.append(f"Лицензия: {repository.license_spdx_id.strip()}")
        if repository.is_archived:
            parts.append("Архивный")

        topics = [topic.strip() for topic in repository.topics if str(topic).strip()]
        if topics:
            parts.append("Темы: " + ", ".join(topics[:6]))

        description = " ".join(repository.description.split())
        if description and re.search(r"[А-Яа-яЁё]", description):
            parts.append("Описание: " + self._truncate_text(description, limit=90))

        if not parts:
            parts.append("Краткая карточка недоступна")
        return ". ".join(parts)

    @staticmethod
    def _format_repo_updated_date(raw_value: str) -> str:
        text = str(raw_value or "").strip()
        if not text:
            return "-"
        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
            return parsed.date().isoformat()
        except Exception:
            # Fallback to date prefix if API format is unexpected.
            return text[:10] if len(text) >= 10 else text

    def _open_preview_selector(self, metadata_file: Path) -> None:
        query, repositories = load_repositories_from_metadata(metadata_file)
        if not repositories:
            messagebox.showinfo("Предпросмотр", "Список пуст. Нечего выбирать для скачивания.")
            return

        query_terms = extract_query_terms_for_ai_filter(query or self.query_var.get().strip())
        now = datetime.now(timezone.utc)
        threshold = 0.55
        try:
            threshold = float(self.ai_filter_min_score_var.get().strip())
        except Exception as e:
            self._debug(f"Could not parse threshold: {e}")

        rows: list[tuple[float, Repo, str, str, str, str]] = []
        for repository in repositories:
            if repository.deep_relevance_checked:
                score = repository.deep_relevance_score
            else:
                score = repo_composite_relevance_score(repository, query_terms, now=now)
            if score >= max(0.68, threshold):
                recommendation = "Рекомендую"
            elif score >= max(0.45, threshold - 0.12):
                recommendation = "Можно взять"
            else:
                recommendation = "Низкий приоритет"

            summary = self._build_preview_summary_ru(repository)
            updated_label = self._format_repo_updated_date(repository.updated_at)
            pushed_label = self._format_repo_updated_date(repository.pushed_at)
            rows.append((score, repository, recommendation, summary, updated_label, pushed_label))

        rows.sort(key=lambda item: (item[0], item[1].stargazers_count, item[1].updated_at), reverse=True)

        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.destroy()

        window = Toplevel(self.root)
        window.title("Предпросмотр: выбор репозиториев для скачивания")
        window.geometry("1260x680")
        window.minsize(1080, 520)
        icon_ico = ROOT_DIR / "assets" / "icon.ico"
        if icon_ico.exists():
            try:
                window.iconbitmap(str(icon_ico))
            except Exception:
                pass
        elif getattr(self, "_icon_image", None):
            try:
                window.iconphoto(True, self._icon_image)
            except Exception:
                pass

        self.preview_window = window
        self.preview_metadata_file = metadata_file
        self.preview_query = query
        self.preview_items = {}
        self.preview_selected_items = set()
        self.preview_recommended_items = set()

        top = ttk.Frame(window, padding=(12, 12, 12, 4))
        top.pack(fill="x")
        ttk.Label(
            top,
            text=f"AI-Анализ завершен (Найдено: {len(rows)})",
            font=("Segoe UI", 12, "bold")
        ).pack(anchor=W)
        is_dark = False
        try:
            is_dark = sv_ttk.get_theme() == "dark"
        except Exception:
            pass
        self.preview_subtitle = ttk.Label(
            top,
            text=(
                "Отметьте нужные репозитории. Двойной клик по названию откроет репозиторий на GitHub.\n"
                "Колонка «Код (push)» показывает дату последнего реального обновления кода."
            ),
            foreground="#8b949e" if is_dark else "#57606a"
        )
        self.preview_subtitle.pack(anchor=W, pady=(4, 0))

        table_frame = ttk.Frame(window, padding=(8, 0, 8, 0))
        table_frame.pack(fill=BOTH, expand=True)

        columns = ("mark", "repo", "stars", "pushed", "lang", "score", "advice", "commit", "about")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=20)
        tree.heading("mark", text="Pick")
        tree.heading("repo", text="Репозиторий")
        tree.heading("stars", text="Stars")
        tree.heading("pushed", text="Последний коммит")
        tree.heading("lang", text="Язык")
        tree.heading("score", text="Score")
        tree.heading("advice", text="Совет")
        tree.heading("commit", text="Суть коммита")
        tree.heading("about", text="О чем")
        tree.column("mark", width=48, anchor="center", stretch=False)
        tree.column("repo", width=240, anchor="w")
        tree.column("stars", width=80, anchor="e", stretch=False)
        tree.column("pushed", width=120, anchor="center", stretch=False)
        tree.column("lang", width=82, anchor="center", stretch=False)
        tree.column("score", width=75, anchor="center", stretch=False)
        tree.column("advice", width=120, anchor="center", stretch=False)
        tree.column("commit", width=200, anchor="w")
        tree.column("about", width=360, anchor="w")

        y_scroll = ttk.Scrollbar(table_frame, orient=VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=y_scroll.set)
        tree.pack(side=LEFT, fill=BOTH, expand=True)
        y_scroll.pack(side=RIGHT, fill=Y)

        default_selected = 0
        for score, repository, recommendation, summary, updated_label, pushed_label in rows:
            is_recommended = recommendation in {"Рекомендую", "Можно взять"}
            if is_recommended:
                default_selected += 1
            mark = "☑" if is_recommended else "☐"

            adv_text = recommendation
            row_tags = ()
            if recommendation == "Рекомендую":
                adv_text = "⭐ Рекомендую"
                row_tags = ("highly_recommended",)
            elif recommendation == "Можно взять":
                adv_text = "✅ Можно взять"
            elif recommendation == "Низкий приоритет":
                adv_text = "⚠️ Низк. приоритет"
                row_tags = ("low_priority",)
            elif recommendation == "Мусор":
                adv_text = "🗑 Мусор"
                row_tags = ("low_priority",)

            score_text = f"{int(score * 100)}%"

            row_id = tree.insert(
                "",
                END,
                values=(
                    mark,
                    repository.full_name,
                    repository.stargazers_count,
                    pushed_label,
                    repository.language or "-",
                    score_text,
                    adv_text,
                    repository.latest_commit_message,
                    summary,
                ),
                tags=row_tags
            )
            self.preview_items[row_id] = repository
            if is_recommended:
                self.preview_selected_items.add(row_id)
                self.preview_recommended_items.add(row_id)

        if default_selected == 0:
            for row_id in list(self.preview_items.keys())[: min(20, len(self.preview_items))]:
                self.preview_selected_items.add(row_id)
                values = list(tree.item(row_id, "values"))
                values[0] = "☑"
                tree.item(row_id, values=values)

        self.preview_tree = tree
        self._apply_theme_colors()
        tree.bind("<Button-1>", self._on_preview_tree_click)
        tree.bind("<Double-1>", self._on_preview_tree_double_click)
        tree.bind("<Return>", self._on_preview_tree_open_selected)
        self._refresh_preview_selection_label()

        controls = ttk.Frame(window, padding=8)
        controls.pack(fill="x")
        ttk.Button(
            controls,
            text="Выбрать рекомендованные",
            command=lambda: self._set_preview_selection_mode("recommended"),
        ).pack(side=LEFT)
        ttk.Button(controls, text="Выбрать все", command=lambda: self._set_preview_selection_mode("all")).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Button(controls, text="Снять все", command=lambda: self._set_preview_selection_mode("none")).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Button(controls, text="Инвертировать", command=lambda: self._set_preview_selection_mode("invert")).pack(
            side=LEFT, padx=(8, 0)
        )
        ttk.Label(controls, textvariable=self.preview_selection_var).pack(side=LEFT, padx=(14, 0))
        ttk.Button(
            controls,
            text="Открыть репозиторий",
            command=self._open_selected_preview_repo,
        ).pack(side=RIGHT, padx=(8, 0))
        ttk.Button(
            controls,
            text="Скачать выбранные",
            command=self._start_download_selected_from_preview,
            style="Accent.TButton",
        ).pack(side=RIGHT)

    def _on_preview_tree_click(self, event: object) -> str | None:
        if not self.preview_tree:
            return None
        tree = self.preview_tree
        region = tree.identify_region(event.x, event.y)  # type: ignore[attr-defined]
        if region != "cell":
            return None
        column = tree.identify_column(event.x)  # type: ignore[attr-defined]
        if column != "#1":
            return None
        row_id = tree.identify_row(event.y)  # type: ignore[attr-defined]
        if not row_id or row_id not in self.preview_items:
            return None
        self._toggle_preview_row(row_id)
        return "break"

    def _on_preview_tree_double_click(self, event: object) -> str | None:
        if not self.preview_tree:
            return None
        tree = self.preview_tree
        region = tree.identify_region(event.x, event.y)  # type: ignore[attr-defined]
        if region != "cell":
            return None
        column = tree.identify_column(event.x)  # type: ignore[attr-defined]
        row_id = tree.identify_row(event.y)  # type: ignore[attr-defined]
        if not row_id or row_id not in self.preview_items:
            return None
        # Repo name column is clickable to open GitHub page.
        if column == "#2":
            self._open_preview_repo_by_row(row_id)
            return "break"
        return None

    def _on_preview_tree_open_selected(self, _event: object) -> str | None:
        self._open_selected_preview_repo()
        return "break"

    def _open_preview_repo_by_row(self, row_id: str) -> None:
        repository = self.preview_items.get(row_id)
        if not repository:
            return
        url = repository.html_url.strip()
        if not url:
            messagebox.showerror("GitHub", "У репозитория нет ссылки.")
            return
        try:
            webbrowser.open(url, new=2)
            self._append_log(f"Открыт репозиторий: {repository.full_name} -> {url}")
        except Exception as exc:
            messagebox.showerror("GitHub", f"Не удалось открыть ссылку:\n{exc}")

    def _open_selected_preview_repo(self) -> None:
        if not self.preview_tree:
            return
        selected = self.preview_tree.selection()
        row_id = selected[0] if selected else self.preview_tree.focus()
        if not row_id or row_id not in self.preview_items:
            messagebox.showinfo("GitHub", "Выберите репозиторий в таблице.")
            return
        self._open_preview_repo_by_row(row_id)

    def _toggle_preview_row(self, row_id: str) -> None:
        if not self.preview_tree:
            return
        is_selected = row_id in self.preview_selected_items
        values = list(self.preview_tree.item(row_id, "values"))
        if is_selected:
            self.preview_selected_items.discard(row_id)
            values[0] = "☐"
        else:
            self.preview_selected_items.add(row_id)
            values[0] = "☑"
        self.preview_tree.item(row_id, values=values)
        self._refresh_preview_selection_label()

    def _set_preview_selection_mode(self, mode: str) -> None:
        if not self.preview_tree:
            return
        row_ids = list(self.preview_items.keys())
        if mode == "all":
            self.preview_selected_items = set(row_ids)
        elif mode == "none":
            self.preview_selected_items = set()
        elif mode == "recommended":
            self.preview_selected_items = set(self.preview_recommended_items)
        elif mode == "invert":
            self.preview_selected_items = {row_id for row_id in row_ids if row_id not in self.preview_selected_items}
        else:
            return

        for row_id in row_ids:
            values = list(self.preview_tree.item(row_id, "values"))
            values[0] = "☑" if row_id in self.preview_selected_items else "☐"
            self.preview_tree.item(row_id, values=values)
        self._refresh_preview_selection_label()

    def _refresh_preview_selection_label(self) -> None:
        total = len(self.preview_items)
        selected = len(self.preview_selected_items)
        self.preview_selection_var.set(f"Выбрано: {selected}/{total}")

    def _start_download_selected_from_preview(self) -> None:
        if self.is_running:
            messagebox.showinfo("Скачивание", "Сейчас уже выполняется другой запуск.")
            return
        if not self.preview_selected_items:
            messagebox.showerror("Скачивание", "Не выбрано ни одного репозитория.")
            return

        selected_repositories = [
            self.preview_items[row_id]
            for row_id in self.preview_items
            if row_id in self.preview_selected_items
        ]
        try:
            base_config = self._build_config()
        except Exception as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
            return
        config = replace(base_config, dry_run=False)

        try:
            self._save_settings()
        except Exception as exc:
            self._debug(f"Ошибка сохранения настроек перед download_selected: {exc}")
            self._append_log(f"Не удалось сохранить настройки: {exc}")

        run_id = self._next_run_id()
        self.active_run_id = run_id
        self._drain_stale_run_events()
        self._last_debug_progress = (-1, -1)
        self.cancel_event = threading.Event()
        self.progress_var.set(0.0)
        self.progress_text_var.set("0 / 0")
        self._append_log("-" * 80)
        self._append_log(
            f"Ручной выбор: запускаем скачивание выбранных репозиториев ({len(selected_repositories)} шт.)."
        )
        self._append_log(f"Папка проекта: {config.output_root}")
        self._set_status("Скачивание выбранных репозиториев...")
        self._set_progress_mode("determinate")
        self._set_running(True)

        self.worker_thread = threading.Thread(
            target=self._worker_download_selected,
            args=(config, selected_repositories, self.preview_metadata_file, self.cancel_event, run_id),
            daemon=True,
        )
        self.worker_thread.start()
        self._debug(
            f"Поток download_selected запущен: run_id={run_id}, "
            f"selected={len(selected_repositories)}, alive={self.worker_thread.is_alive()}"
        )
        self.root.after(120, self._poll_events)

    def start_collection(self) -> None:
        if self.autopilot_enabled_var.get():
            self._start_ai_plan(auto_start=True, auto_preview=False)
            return

        if self.is_running:
            self._debug("Нажат Запуск, но процесс уже выполняется. Игнорировано.")
            return
        self._debug("Нажат Запуск. Начинаем сбор конфигурации.")
        try:
            config = self._build_config()
        except Exception as exc:
            self._debug(f"Ошибка валидации параметров: {exc}")
            messagebox.showerror("Ошибка параметров", str(exc))
            return

        try:
            self._save_settings()
        except Exception as exc:
            self._debug(f"Ошибка сохранения настроек: {exc}")
            self._append_log(f"Не удалось сохранить настройки: {exc}")

        self._debug(f"Конфигурация запуска: {json.dumps(self._config_for_debug(config), ensure_ascii=False)}")
        run_id = self._next_run_id()
        self.active_run_id = run_id
        self._drain_stale_run_events()
        self._last_debug_progress = (-1, -1)
        self.cancel_event = threading.Event()
        self.progress_var.set(0.0)
        self.progress_text_var.set("0 / 0")
        self._append_log("-" * 80)
        if self._last_query_normalization_message:
            self._append_log(self._last_query_normalization_message)
        self._append_log(f"Запуск запроса: {config.query}")
        self._append_log(f"Профиль качества: {self.search_profile_var.get().strip()}")
        self._append_log(
            "Параметры запуска: "
            f"max_repos={config.max_repos}, batch_size={config.batch_size}, workers={config.workers}, "
            f"skip_existing={config.skip_existing}, dry_run={config.dry_run}, output={config.output_root}, "
            f"ai_provider={config.ai_provider_type}, ai_model={config.ai_filter_model}, "
            f"ai_filter={config.ai_filter_enabled}, ai_filter_min_score={config.ai_filter_min_score}, "
            f"ai_filter_max_reviews={config.ai_filter_max_reviews}, incremental={config.incremental}, "
            f"include_keywords={list(config.include_keywords)}, exclude_keywords={list(config.exclude_keywords)}, "
            f"clone_depth={config.clone_depth}, clone_partial={config.clone_partial}, "
            f"clone_single_branch={config.clone_single_branch}, clone_no_tags={config.clone_no_tags}, "
            f"graphql_enrich={config.graphql_enrich}, graphql_batch_size={config.graphql_batch_size}, "
            f"deep_relevance={config.deep_relevance_enabled}, "
            f"deep_relevance_max_repos={config.deep_relevance_max_repos}, "
            f"deep_relevance_min_score={config.deep_relevance_min_score}, "
            f"export_sqlite={config.export_sqlite or ''}"
        )
        if self._last_token_source == "manual":
            self._append_log("GitHub token: использован из поля GUI (не сохраняется в настройках).")
        elif self._last_token_source == "env":
            self._append_log("GitHub token: использован из переменной окружения GITHUB_TOKEN.")
        elif self._last_token_source == "saved":
            self._append_log("GitHub token: использован из локального Windows protected storage.")
        else:
            self._append_log("GitHub token: не задан. Возможны паузы из-за лимитов GitHub API.")
        if self._last_ai_key_source == "manual":
            self._append_log("AI API key: использован из поля GUI (не сохраняется в настройках).")
        elif self._last_ai_key_source.startswith("env:"):
            self._append_log(f"AI API key: использован из переменной окружения {self._last_ai_key_source[4:]}.")
        elif self._last_ai_key_source == "saved":
            self._append_log("AI API key: использован из локального Windows protected storage.")
        elif self._last_ai_key_source == "not-required":
            self._append_log("AI API key: не требуется для выбранного AI provider.")
        else:
            self._append_log("AI API key: не задан. Провайдер должен поддерживать no-key/local режим или вернет ошибку.")
        if config.max_repos == 1:
            self._append_log(
                "ВНИМАНИЕ: max_repos=1, поэтому будет обработан максимум 1 репозиторий."
            )
        self._append_log(f"Debug-лог: {self.debug_log_file}")
        self._debug(f"Запуск run_id={run_id}. Потоки workers={config.workers}, batch_size={config.batch_size}")
        self._start_status_animation("Поиск репозиториев")
        self._set_progress_mode("indeterminate")
        self._set_running(True)

        self.worker_thread = threading.Thread(
            target=self._worker_run,
            args=(config, self.cancel_event, run_id),
            daemon=True,
        )
        self.worker_thread.start()
        self._debug(f"Поток worker запущен: name={self.worker_thread.name}, alive={self.worker_thread.is_alive()}")
        self.root.after(120, self._poll_events)

    def stop_collection(self) -> None:
        if not self.is_running or not self.cancel_event:
            self._debug("Нажат Стоп, но активного запуска нет.")
            return
        self.cancel_event.set()
        self.status_var.set("Останавливаем...")
        self._append_log("Запрошена остановка. Завершаем текущие операции...")
        self._debug(f"Запрошена остановка run_id={self.active_run_id}")

    def _worker_run(self, config: RunConfig, cancel_event: threading.Event, run_id: int) -> None:
        def send_log(message: str) -> None:
            self.events.put(("log", run_id, message))

        def send_progress(done: int, total: int) -> None:
            self.events.put(("progress", run_id, done, total))

        try:
            self._debug(f"_worker_run стартовал run_id={run_id}")
            summary = run_collection(config, log=send_log, progress=send_progress, cancel_event=cancel_event)
            self._debug(
                "run_collection завершен успешно "
                f"run_id={run_id}; found={summary.found_count}; cloned={summary.cloned_count}; "
                f"skipped={summary.skipped_count}; failed={summary.failed_count}; cancelled={summary.cancelled_count}"
            )
            if config.dry_run:
                self.events.put(("preview_done", run_id, summary))
            else:
                self.events.put(("done", run_id, summary))
        except RunCancelledError as exc:
            self._debug(f"run_collection отменен run_id={run_id}: {exc}")
            self.events.put(("cancelled", run_id, str(exc)))
        except Exception as exc:
            self._debug(
                f"run_collection исключение run_id={run_id}: {exc}\n{traceback.format_exc()}"
            )
            self.events.put(("error", run_id, str(exc)))

    def _poll_events(self) -> None:
        log_batch = []
        processed = 0
        while processed < 100:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break
            processed += 1

            kind = event[0]
            if kind == "log":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события log от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                log_message = str(event[2])
                log_batch.append(log_message)
                self._update_runtime_status_from_log(log_message)
            elif kind == "progress":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события progress от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                done = int(event[2])
                total = int(event[3])
                
                # Switch to determinate progress on first real progress event
                if self._animation_active:
                    self._stop_status_animation()
                    self._set_progress_mode("determinate")
                    
                percent = (done / total * 100.0) if total > 0 else 0.0
                self.progress_var.set(percent)
                self.progress_text_var.set(f"{done} / {total}")
                current_progress = (done, total)
                if current_progress != self._last_debug_progress:
                    self._debug(f"Прогресс run_id={event_run_id}: {done}/{total} ({percent:.2f}%)")
                    self._last_debug_progress = current_progress
            elif kind == "preview_done":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события preview_done от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                summary = event[2]
                self._debug(
                    "Получено событие preview_done "
                    f"run_id={event_run_id}; found={summary.found_count}; metadata={summary.metadata_file}"
                )
                self.status_var.set(f"Предпросмотр готов. Найдено={summary.found_count}")
                self._append_log(self.status_var.get())
                self._append_log(f"Метаданные: {summary.metadata_file}")
                self._append_log(f"Лог запуска: {summary.run_log_file}")
                self._set_running(False)
                self.active_run_id = None
                self.cancel_event = None
                self.worker_thread = None
                try:
                    self._open_preview_selector(Path(summary.metadata_file))
                except Exception as exc:
                    self._debug(f"Ошибка открытия окна выбора preview: {exc}\n{traceback.format_exc()}")
                    self._append_log(f"ОШИБКА предпросмотра: {exc}")
                    messagebox.showerror("Предпросмотр", str(exc))
            elif kind == "done":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события done от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                summary = event[2]
                self._debug(
                    "Получено событие done "
                    f"run_id={event_run_id}; found={summary.found_count}; cloned={summary.cloned_count}; "
                    f"skipped={summary.skipped_count}; failed={summary.failed_count}; cancelled={summary.cancelled_count}"
                )
                self.status_var.set(
                    f"Готово. Найдено={summary.found_count}, Скачано={summary.cloned_count}, "
                    f"Пропущено={summary.skipped_count}, Остановлено={summary.cancelled_count}, "
                    f"Ошибок={summary.failed_count}"
                )
                self._append_log(self.status_var.get())
                self._append_log(f"Метаданные: {summary.metadata_file}")
                self._append_log(f"Лог запуска: {summary.run_log_file}")
                if summary.failure_report_file:
                    self._append_log(f"Отчет об ошибках: {summary.failure_report_file}")
                if summary.cloned_count == 0 and summary.skipped_count > 0 and summary.failed_count == 0:
                    self._append_log(
                        "Новых репозиториев нет: все найденные уже были скачаны ранее. "
                        "Укажите новую папку проекта или удалите старые папки репозиториев для перекачки."
                    )
                self._set_running(False)
                self.active_run_id = None
                self.cancel_event = None
                self.worker_thread = None
            elif kind == "cancelled":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события cancelled от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                self._debug(f"Получено событие cancelled run_id={event_run_id}: {event[2]}")
                self.status_var.set("Остановлено пользователем")
                self._append_log(str(event[2]))
                self._set_running(False)
                self.active_run_id = None
                self.cancel_event = None
                self.worker_thread = None
            elif kind == "error":
                event_run_id = int(event[1])
                if event_run_id != self.active_run_id:
                    self._debug(
                        f"Пропуск события error от run_id={event_run_id}, активный={self.active_run_id}"
                    )
                    continue
                message = str(event[2])
                self._debug(f"Получено событие error run_id={event_run_id}: {message}")
                self.status_var.set("Ошибка")
                self._append_log(f"ОШИБКА: {message}")
                messagebox.showerror("Ошибка выполнения", message)
                self._set_running(False)
                self.active_run_id = None
                self.cancel_event = None
                self.worker_thread = None
            elif kind == "models_done":
                models = event[1]
                self._debug(f"Событие models_done: {len(models)} моделей")
                if self.ai_model_combo is not None:
                    self.ai_model_combo["values"] = tuple(models)
                if models and self.ai_model_var.get().strip() not in models:
                    self.ai_model_var.set(models[0])
                self._append_log(f"AI provider: получено моделей {len(models)}")
                self._set_models_loading(False)
            elif kind == "models_auto_discovered":
                new_provider, models = event[1]
                self._debug(f"Событие models_auto_discovered: {new_provider.provider_type}, {len(models)} моделей")
                self.ai_provider_type_var.set(new_provider.provider_type)
                self.ai_endpoint_var.set(new_provider.endpoint)
                if self.ai_model_combo is not None:
                    self.ai_model_combo["values"] = tuple(models)
                if models and self.ai_model_var.get().strip() not in models:
                    self.ai_model_var.set(models[0])
                self._append_log(f"Автопоиск: найден локальный сервис {new_provider.endpoint}, получено моделей {len(models)}")
                self._set_models_loading(False)
            elif kind == "models_not_found":
                message = str(event[1])
                self._debug(f"Событие models_not_found: {message}")
                self._append_log("Автопоиск: локальные модели не найдены.")
                messagebox.showinfo("Модели не найдены", message)
                self._set_models_loading(False)
            elif kind == "models_error":
                message = str(event[1])
                self._debug(f"Событие models_error: {message}")
                self._append_log(f"AI provider модели: ошибка: {message}")
                messagebox.showerror("Ошибка AI provider", message)
                self._set_models_loading(False)
            elif kind == "ai_done":
                plan = event[1]
                auto_start = self.autopilot_pending
                auto_preview = self.autopilot_preview_pending
                self.autopilot_pending = False
                self.autopilot_preview_pending = False
                self._debug(
                    "Событие ai_done: "
                    f"query={plan.query}; folder={plan.folder_name}; max_repos={plan.max_repos}; "
                    f"autopilot={auto_start}; autopreview={auto_preview}"
                )
                self._apply_ai_plan_to_form(plan, autopilot_mode=(auto_start or auto_preview))
                self.status_var.set("ИИ-команда применена")
                self._append_log(
                    f"ИИ: сформирован запрос '{plan.query}', папка '{plan.folder_name}', "
                    f"возраст<= {plan.max_age_years} лет."
                )
                self._set_ai_busy(False)
                if auto_start and not self.is_running:
                    self._append_log("Автопилот: запускаем поиск по примененным параметрам...")
                    self.start_collection()
                elif auto_preview and not self.is_running:
                    self._append_log("Автопилот: открываем предпросмотр перед скачиванием...")
                    self.start_preview_collection()
            elif kind == "ai_error":
                message = str(event[1])
                auto_start = self.autopilot_pending
                auto_preview = self.autopilot_preview_pending
                self.autopilot_pending = False
                self.autopilot_preview_pending = False
                self._debug(f"Событие ai_error: {message}")
                self.status_var.set("Ошибка ИИ")
                self._append_log(f"ИИ ОШИБКА: {message}")
                if auto_start or auto_preview:
                    self._append_log("Автопилот остановлен: ИИ не смог подготовить параметры.")
                messagebox.showerror("Ошибка ИИ", message)
                self._set_ai_busy(False)
        if log_batch:
            self._append_log_batch(log_batch)

        worker_alive = self.worker_thread is not None and self.worker_thread.is_alive()
        ai_alive = self.ai_thread is not None and self.ai_thread.is_alive()
        models_alive = self.models_thread is not None and self.models_thread.is_alive()
        poll_state = (
            f"is_running={self.is_running}; ai_busy={self.ai_busy}; models_loading={self.models_loading}; "
            f"worker_alive={worker_alive}; ai_alive={ai_alive}; models_alive={models_alive}; "
            f"events_empty={self.events.empty()}"
        )
        if poll_state != self._last_poll_state:
            self._debug(f"Состояние поллинга: {poll_state}")
            self._last_poll_state = poll_state
        if self.is_running or self.ai_busy or self.models_loading or worker_alive or ai_alive or models_alive or not self.events.empty():
            self.root.after(120, self._poll_events)


APP_MUTEX_NAME = "GithubSearchDownloaderAppMutex"
_APP_MUTEX_HANDLE: int | None = None


def acquire_app_mutex(mutex_name: str = APP_MUTEX_NAME) -> bool:
    """Acquires a named Windows mutex to enforce single-instance and allow Inno Setup detection.

    Returns True if this is the first/primary instance, or False if another instance is already running.
    """
    global _APP_MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        ERROR_ALREADY_EXISTS = 183
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            return True
        last_error = kernel32.GetLastError()
        _APP_MUTEX_HANDLE = handle
        if last_error == ERROR_ALREADY_EXISTS:
            return False
        return True
    except Exception:
        return True


def release_app_mutex() -> None:
    """Releases the Windows named mutex upon application exit."""
    global _APP_MUTEX_HANDLE
    if os.name == "nt" and _APP_MUTEX_HANDLE:
        try:
            ctypes.windll.kernel32.CloseHandle(_APP_MUTEX_HANDLE)
        except Exception:
            pass
        _APP_MUTEX_HANDLE = None


def activate_existing_instance() -> None:
    """Attempts to bring an existing running instance of the application window to foreground."""
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        hwnd = user32.FindWindowW(None, APP_DISPLAY_NAME)
        if not hwnd:
            hwnd = user32.FindWindowW(None, "GitHub Search Downloader")
        if hwnd:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def main() -> None:
    enable_high_dpi_awareness()
    if not acquire_app_mutex():
        activate_existing_instance()
        sys.exit(0)
    try:
        import sv_ttk
        root = Tk()
        sv_ttk.set_theme("dark")
        GitHubSearchGUI(root)
        root.mainloop()
    finally:
        release_app_mutex()


if __name__ == "__main__":
    main()

