from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    is_free: bool = False
    is_recommended: bool = False
    context_length: Optional[int] = None
    description: str = ""

    def display_label(self) -> str:
        prefix = "🎁 [FREE] " if self.is_free else ("⭐ " if self.is_recommended else "")
        ctx = f" ({self.context_length // 1024}k)" if self.context_length and self.context_length >= 1024 else ""
        return f"{prefix}{self.id}{ctx}"


@dataclass(frozen=True)
class ProviderSpec:
    id: str
    display_name: str
    default_base_url: str
    key_prefix: str = ""
    help_url: str = ""
    requires_account_id: bool = False
    extra_headers: dict[str, str] = field(default_factory=dict)
    default_models: list[str] = field(default_factory=list)


PROVIDERS: dict[str, ProviderSpec] = {
    "openrouter": ProviderSpec(
        id="openrouter",
        display_name="OpenRouter (400+ моделей, есть бесплатные)",
        default_base_url="https://openrouter.ai/api/v1",
        key_prefix="sk-or-v1-",
        help_url="https://openrouter.ai/keys",
        extra_headers={
            "HTTP-Referer": "https://github.com/AI-Nikitka93/github-search-downloader",
            "X-Title": "GitHub Search Downloader",
        },
        default_models=[
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-r1:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "nvidia/nemotron-3.5-lightning:free",
            "mistralai/mistral-7b-instruct:free",
            "google/gemini-2.0-flash-exp:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o",
            "deepseek/deepseek-chat",
        ],
    ),
    "groq": ProviderSpec(
        id="groq",
        display_name="Groq (Сверхбыстрый инференс)",
        default_base_url="https://api.groq.com/openai/v1",
        key_prefix="gsk_",
        help_url="https://console.groq.com/keys",
        default_models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "qwen-2.5-32b",
            "deepseek-r1-distill-llama-70b",
        ],
    ),
    "nvidia": ProviderSpec(
        id="nvidia",
        display_name="NVIDIA NIM (Build NVIDIA)",
        default_base_url="https://integrate.api.nvidia.com/v1",
        key_prefix="nvapi-",
        help_url="https://build.nvidia.com/",
        default_models=[
            "meta/llama-3.3-70b-instruct",
            "nvidia/nemotron-4-340b-instruct",
            "deepseek-ai/deepseek-r1",
            "mistralai/mistral-large-2407",
            "qwen/qwen2.5-72b-instruct",
        ],
    ),
    "deepseek": ProviderSpec(
        id="deepseek",
        display_name="DeepSeek (Официальный API)",
        default_base_url="https://api.deepseek.com/v1",
        key_prefix="sk-",
        help_url="https://platform.deepseek.com/api_keys",
        default_models=[
            "deepseek-chat",
            "deepseek-reasoner",
        ],
    ),
    "mistral": ProviderSpec(
        id="mistral",
        display_name="Mistral AI (La Plateforme)",
        default_base_url="https://api.mistral.ai/v1",
        help_url="https://console.mistral.ai/api-keys",
        default_models=[
            "codestral-latest",
            "mistral-large-latest",
            "mistral-small-latest",
            "open-mistral-nemo",
            "pixtral-12b-2409",
        ],
    ),
    "llm7": ProviderSpec(
        id="llm7",
        display_name="LLM7.io (Фронтирные модели 2026)",
        default_base_url="https://api.llm7.io/v1",
        help_url="https://token.llm7.io/#/api-keys",
        default_models=[
            "deepseek-v4-flash",
            "kimi-k3",
            "minimax-m3",
            "glm-5.3",
            "gpt-5.4-mini",
            "gemini-3.7-flash",
            "codestral-latest",
        ],
    ),
    "cloudflare": ProviderSpec(
        id="cloudflare",
        display_name="Cloudflare Workers AI",
        default_base_url="https://api.cloudflare.com/client/v4",
        key_prefix="cfut_",
        help_url="https://dash.cloudflare.com/",
        requires_account_id=True,
        default_models=[
            "@cf/meta/llama-3.3-70b-instruct",
            "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b",
            "@cf/qwen/qwen2.5-72b-instruct",
            "@cf/mistral/mistral-7b-instruct-v0.2",
        ],
    ),
    "ollama_cloud": ProviderSpec(
        id="ollama_cloud",
        display_name="Ollama Cloud / Remote",
        default_base_url="https://ollama.com/api",
        help_url="https://ollama.com/settings/keys",
        default_models=[
            "llama3.3",
            "qwen2.5-coder",
            "mistral",
            "deepseek-r1",
        ],
    ),
    "openai": ProviderSpec(
        id="openai",
        display_name="OpenAI (Official)",
        default_base_url="https://api.openai.com/v1",
        key_prefix="sk-proj-",
        help_url="https://platform.openai.com/api-keys",
        default_models=[
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
            "gpt-4-turbo",
        ],
    ),
    "custom": ProviderSpec(
        id="custom",
        display_name="Пользовательский (OpenAI-compatible)",
        default_base_url="http://127.0.0.1:1234/v1",
        default_models=[],
    ),
}


@dataclass
class ValidationResult:
    success: bool
    provider_id: str
    provider_name: str
    endpoint: str
    models: list[ModelInfo] = field(default_factory=list)
    free_models: list[ModelInfo] = field(default_factory=list)
    recommended_models: list[ModelInfo] = field(default_factory=list)
    error_message: str = ""
    http_status: int = 0
    quota_info: str = ""


def detect_provider_from_key(api_key: str) -> Optional[str]:
    """Автоматически определяет ID провайдера по сигнатуре ключа."""
    k = api_key.strip()
    if not k:
        return None
    if k.startswith("sk-or-v1-"):
        return "openrouter"
    if k.startswith("gsk_"):
        return "groq"
    if k.startswith("nvapi-"):
        return "nvidia"
    if k.startswith("cfut_"):
        return "cloudflare"
    if k.startswith("sk-proj-"):
        return "openai"
    if k.startswith("sk-") and len(k) > 20:
        return "deepseek"
    if len(k) == 32 and re.match(r"^[a-zA-Z0-9]+$", k):
        # Типичный формат Mistral API key (32 символа)
        return "mistral"
    return None


def parse_models_response(provider_id: str, payload: dict[str, Any]) -> list[ModelInfo]:
    """Парсит ответ /models или аналогичного эндпоинта в список ModelInfo."""
    models: list[ModelInfo] = []
    seen: set[str] = set()

    # Формат OpenAI/OpenRouter/NVIDIA/Groq/Mistral/LLM7: {"data": [...]}
    raw_list = payload.get("data") or payload.get("models") or payload.get("result") or []
    if isinstance(payload, list):
        raw_list = payload

    for item in raw_list:
        if isinstance(item, str):
            model_id = item.strip()
            item_data: dict[str, Any] = {}
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
            item_data = item
        else:
            continue

        if not model_id or model_id.lower() in seen:
            continue
        seen.add(model_id.lower())

        # Определение бесплатности
        is_free = False
        if ":free" in model_id.lower():
            is_free = True
        elif provider_id == "openrouter":
            pricing = item_data.get("pricing", {})
            if isinstance(pricing, dict):
                prompt_price = str(pricing.get("prompt", "")).strip()
                if prompt_price in ("0", "0.0", "0.000000"):
                    is_free = True

        # Определение рекомендаций (флагманы 2025-2026)
        is_recommended = False
        rec_keywords = [
            "llama-3.3", "deepseek-r1", "deepseek-v4", "codestral",
            "qwen-2.5", "qwen-3.5", "kimi-k3", "glm-5", "nemotron",
            "gpt-4o", "gpt-4o-mini", "claude-3.5-sonnet"
        ]
        lowered_id = model_id.lower()
        if any(kw in lowered_id for kw in rec_keywords):
            is_recommended = True

        # Контекст
        ctx_len = item_data.get("context_length") or item_data.get("max_tokens") or item_data.get("context_window")
        try:
            ctx_len = int(ctx_len) if ctx_len else None
        except (ValueError, TypeError):
            ctx_len = None

        desc = str(item_data.get("description") or "")

        models.append(
            ModelInfo(
                id=model_id,
                name=str(item_data.get("name") or model_id),
                is_free=is_free,
                is_recommended=is_recommended,
                context_length=ctx_len,
                description=desc,
            )
        )

    # Сортировка: сначала бесплатные (:free), затем рекомендуемые, затем по алфавиту
    def _sort_key(m: ModelInfo) -> tuple[int, int, str]:
        free_score = 0 if m.is_free else 1
        rec_score = 0 if m.is_recommended else 1
        return (free_score, rec_score, m.id.lower())

    models.sort(key=_sort_key)
    return models


def validate_and_fetch_models(
    provider_id: str,
    api_key: str,
    base_url: str = "",
    account_id: str = "",
    timeout: int = 10,
) -> ValidationResult:
    """Отправляет тестовый запрос к API провайдера для валидации ключа и получения списка моделей."""
    spec = PROVIDERS.get(provider_id)
    provider_name = spec.display_name if spec else provider_id
    key = api_key.strip()

    if not base_url:
        base_url = spec.default_base_url if spec else "https://api.openai.com/v1"

    base_url = base_url.rstrip("/")

    # Формируем URL запроса моделей
    if provider_id == "cloudflare":
        acc = account_id.strip()
        if not acc:
            return ValidationResult(
                success=False,
                provider_id=provider_id,
                provider_name=provider_name,
                endpoint=base_url,
                error_message="Для Cloudflare Workers AI требуется указать Account ID.",
            )
        req_url = f"{base_url}/accounts/{acc}/ai/models/search"
    elif provider_id in ("ollama_cloud", "ollama"):
        req_url = f"{base_url}/tags" if base_url.endswith("/api") else f"{base_url}/api/tags"
    else:
        req_url = f"{base_url}/models"

    headers: dict[str, str] = {
        "User-Agent": "GitHubSearchDownloader/1.1.1 (Windows x64)",
    }
    if key:
        headers["Authorization"] = f"Bearer {key}"

    if spec and spec.extra_headers:
        headers.update(spec.extra_headers)

    request = urllib.request.Request(req_url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.status
            body = response.read().decode("utf-8", errors="replace")
            payload = json.loads(body)

            models = parse_models_response(provider_id, payload)
            if not models and spec and spec.default_models:
                models = [
                    ModelInfo(id=m, name=m, is_free=":free" in m.lower())
                    for m in spec.default_models
                ]

            free_models = [m for m in models if m.is_free]
            recommended = [m for m in models if m.is_recommended]

            return ValidationResult(
                success=True,
                provider_id=provider_id,
                provider_name=provider_name,
                endpoint=base_url,
                models=models,
                free_models=free_models,
                recommended_models=recommended,
                http_status=status_code,
            )

    except urllib.error.HTTPError as exc:
        code = exc.code
        err_body = exc.read().decode("utf-8", errors="replace")
        msg = f"HTTP {code}"

        if code == 401:
            msg = "Ошибка 401: Неверный API-ключ (Unauthorized). Проверьте правильность введенного ключа."
        elif code == 403:
            if provider_id == "groq":
                msg = "Ошибка 403 Forbidden: Доступ запрещен. Для Groq может требоваться VPN или активная подписка."
            else:
                msg = f"Ошибка 403 Forbidden: Доступ ограничен или превышен лимит ({err_body[:100]})."
        elif code == 404:
            msg = f"Ошибка 404 Not Found: Эндпоинт {req_url} не найден. Проверьте Base URL."
        elif code == 429:
            msg = "Ошибка 429 Too Many Requests: Превышен лимит запросов или закончился баланс."
        else:
            msg = f"Ошибка сервера HTTP {code}: {err_body[:120]}"

        # Если есть дефолтные модели, все равно вернем их для выбора
        fallback_models = (
            [ModelInfo(id=m, name=m, is_free=":free" in m.lower()) for m in spec.default_models]
            if spec
            else []
        )
        return ValidationResult(
            success=False,
            provider_id=provider_id,
            provider_name=provider_name,
            endpoint=base_url,
            models=fallback_models,
            error_message=msg,
            http_status=code,
        )

    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "timed out" in reason.lower() or isinstance(exc.reason, socket.timeout):
            msg = f"Таймаут соединения ({timeout}с). Сервер {base_url} не отвечает."
        elif "connection refused" in reason.lower():
            msg = f"Соединение отклонено. Убедитесь, что сервер {base_url} запущен."
        else:
            msg = f"Ошибка подключения к {base_url}: {reason}"

        fallback_models = (
            [ModelInfo(id=m, name=m, is_free=":free" in m.lower()) for m in spec.default_models]
            if spec
            else []
        )
        return ValidationResult(
            success=False,
            provider_id=provider_id,
            provider_name=provider_name,
            endpoint=base_url,
            models=fallback_models,
            error_message=msg,
        )

    except Exception as exc:
        fallback_models = (
            [ModelInfo(id=m, name=m, is_free=":free" in m.lower()) for m in spec.default_models]
            if spec
            else []
        )
        return ValidationResult(
            success=False,
            provider_id=provider_id,
            provider_name=provider_name,
            endpoint=base_url,
            models=fallback_models,
            error_message=f"Ошибка валидации: {exc}",
        )
