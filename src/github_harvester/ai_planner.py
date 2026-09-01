from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Callable


INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]+')
NON_WORD = re.compile(r"[^A-Za-z0-9._-]+")
PLANNER_QUERY_QUALIFIER = re.compile(
    r"\b(?:stars|language|created|updated|pushed|fork|archived|sort|order):[^\s()]+",
    flags=re.IGNORECASE,
)


class AiPlannerError(RuntimeError):
    """Raised when AI planning request fails."""


AI_PROVIDER_OLLAMA = "ollama"
AI_PROVIDER_OPENAI_COMPATIBLE = "openai-compatible"


@dataclass(frozen=True)
class AiProviderConfig:
    endpoint: str
    model: str
    provider_type: str = AI_PROVIDER_OLLAMA
    api_key: str = ""
    api_key_env: str = ""
    timeout: int = 90
    temperature: float = 0.0
    num_ctx: int = 4096
    num_predict: int = 768


@dataclass(frozen=True)
class AiPlanResult:
    query: str
    folder_name: str
    min_stars: int
    language: str
    max_age_years: int
    max_repos: int
    batch_size: int
    workers: int
    clone_timeout: int
    retry_failed_clones: int
    retry_delay_seconds: int
    include_forks: bool
    include_archived: bool
    sort: str
    order: str


def list_ollama_models(endpoint: str, timeout: int = 30) -> list[str]:
    base_url = endpoint.strip().rstrip("/")
    if not base_url:
        raise AiPlannerError("Не указан endpoint Ollama.")
    url = f"{base_url}/api/tags"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AiPlannerError(f"Ollama HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AiPlannerError(_format_ollama_unavailable_message(base_url, exc)) from exc
    except json.JSONDecodeError as exc:
        raise AiPlannerError(f"Некорректный JSON от Ollama /api/tags: {exc}") from exc

    return parse_ollama_tags_payload(payload)


def list_ai_models(provider: AiProviderConfig, timeout: int = 30) -> list[str]:
    provider_type = normalize_ai_provider_type(provider.provider_type)
    if provider_type == AI_PROVIDER_OLLAMA:
        return list_ollama_models(provider.endpoint, timeout=timeout)
    if provider_type == AI_PROVIDER_OPENAI_COMPATIBLE:
        return list_openai_compatible_models(provider, timeout=timeout)
    raise AiPlannerError(f"Неподдерживаемый AI provider: {provider.provider_type}")


import subprocess
import os
import time

def _try_start_ollama() -> bool:
    try:
        localappdata = os.environ.get("LOCALAPPDATA", "")
        ollama_path = os.path.join(localappdata, "Programs", "Ollama", "ollama.exe")
        if os.path.exists(ollama_path):
            subprocess.Popen([ollama_path, "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            return True
        else:
            subprocess.Popen(["ollama", "serve"], creationflags=subprocess.CREATE_NO_WINDOW)
            time.sleep(2)
            return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug(f"Ollama start failed: {e}")
    return False

def discover_local_models(timeout: int = 5) -> tuple[AiProviderConfig, list[str]] | None:
    """Опрашивает известные локальные порты ИИ (Ollama, LM Studio) и возвращает первый успешный результат. При необходимости пытается запустить Ollama."""
    provider_ollama = AiProviderConfig(
        provider_type=AI_PROVIDER_OLLAMA,
        endpoint="http://127.0.0.1:11434",
        model="",
        api_key="",
        api_key_env="",
    )
    
    # Попытка 1: Просто опрашиваем Ollama
    try:
        models = list_ollama_models(provider_ollama.endpoint, timeout=timeout)
        if models is not None:
            return provider_ollama, models
    except AiPlannerError:
        # Попытка 2: Пробуем запустить Ollama сервер, если он установлен
        if _try_start_ollama():
            try:
                models = list_ollama_models(provider_ollama.endpoint, timeout=timeout)
                if models is not None:
                    return provider_ollama, models
            except AiPlannerError as e:
                import logging
                logging.getLogger(__name__).debug(f"Ollama list failed after start: {e}")

    # Попытка 3: Проверяем LM Studio
    provider_lmstudio = AiProviderConfig(
        provider_type=AI_PROVIDER_OPENAI_COMPATIBLE,
        endpoint="http://127.0.0.1:1234/v1",
        model="",
        api_key="",
        api_key_env="",
    )
    try:
        models = list_openai_compatible_models(provider_lmstudio, timeout=timeout)
        if models is not None:
            return provider_lmstudio, models
    except AiPlannerError as e:
        import logging
        logging.getLogger(__name__).debug(f"LM Studio list failed: {e}")

    return None


def list_openai_compatible_models(provider: AiProviderConfig, timeout: int = 30) -> list[str]:
    base_url = provider.endpoint.strip().rstrip("/")
    if not base_url:
        raise AiPlannerError("Не указан OpenAI-compatible Base URL.")
    url = f"{base_url}/models"
    request = urllib.request.Request(url, method="GET")
    if provider.api_key.strip():
        request.add_header("Authorization", f"Bearer {provider.api_key.strip()}")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            payload = json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise AiPlannerError(f"AI provider HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise AiPlannerError(_format_ai_provider_unavailable_message(base_url, exc)) from exc
    except json.JSONDecodeError as exc:
        raise AiPlannerError(f"Некорректный JSON от AI provider /models: {exc}") from exc
    return parse_openai_models_payload(payload)


def parse_ollama_tags_payload(payload: dict) -> list[str]:
    models = payload.get("models")
    if not isinstance(models, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(name)
    result.sort(key=lambda value: value.lower())
    return result


def parse_openai_models_payload(payload: dict | list) -> list[str]:
    raw_models = []
    if isinstance(payload, list):
        raw_models = payload
    elif isinstance(payload, dict):
        raw_models = payload.get("data") or payload.get("models") or payload.get("result") or []

    if not isinstance(raw_models, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in raw_models:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            model_id = str(item.get("id") or item.get("name") or "").strip()
        else:
            continue
        if not model_id:
            continue
        lowered = model_id.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(model_id)

    # Free models (:free) at the top, then alphabetically
    result.sort(key=lambda value: (0 if ":free" in value.lower() else 1, value.lower()))
    return result


def plan_search_task(
    task_text: str,
    provider: AiProviderConfig,
    today: date | None = None,
    log: Callable[[str], None] | None = None,
) -> AiPlanResult:
    logger = log or (lambda _: None)
    text = task_text.strip()
    if not text:
        raise ValueError("Текст задачи пустой.")
    if not provider.endpoint.strip():
        raise ValueError("Не указан endpoint Ollama.")
    if not provider.model.strip():
        raise ValueError("Не указана модель Ollama.")

    current_day = today or date.today()
    # The planner itself doesn't receive the custom prompt in plan_search_task 
    # directly via API (it's mainly for the filter), but we pass an empty string here
    # just to keep the signature intact if someone wants to pass it later.
    prompt = build_planner_prompt(text, current_day)
    logger(f"AI planner: provider={provider.provider_type}, model={provider.model}")
    raw_response = request_ai(provider, prompt, retries=2)
    payload = parse_json_object(raw_response)
    return normalize_plan(payload, task_text=text)


def build_planner_prompt(task_text: str, current_day: date, custom_ai_prompt: str = "") -> str:
    base_prompt = (
        "Ты помощник для настройки GitHub-поиска.\n"
        "Верни СТРОГО JSON-объект без пояснений.\n"
        "Поля JSON:\n"
        "{\n"
        '  "query": "строка для GitHub поиска",\n'
        '  "folder_name": "короткое имя папки проекта латиницей и _",\n'
        '  "min_stars": 0,\n'
        '  "language": "",\n'
        '  "max_age_years": 5,\n'
        '  "max_repos": 100,\n'
        '  "batch_size": 100,\n'
        '  "workers": 6,\n'
        '  "clone_timeout": 300,\n'
        '  "retry_failed_clones": 2,\n'
        '  "retry_delay_seconds": 5,\n'
        '  "include_forks": false,\n'
        '  "include_archived": false,\n'
        '  "sort": "stars",\n'
        '  "order": "desc"\n'
        "}\n"
        "Требования:\n"
        "- query: только смысловые термины/фразы темы; не добавляй stars:/language:/created:/updated:/fork:/archived:.\n"
        "- folder_name: только латиница, цифры, _ и -, длина до 80.\n"
        "- sort только stars или updated.\n"
        "- order только desc или asc.\n"
        "- max_age_years 0..15.\n"
        "- min_stars >= 0.\n"
        f"Сегодня: {current_day.isoformat()}.\n"
        f"Задача пользователя: {task_text}\n"
    )
    if custom_ai_prompt:
        base_prompt += f"\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:\n{custom_ai_prompt.strip()}\nОбязательно учти их при формировании параметров поиска.\n"
    
    return base_prompt


def request_ai(provider: AiProviderConfig, prompt: str, retries: int = 0) -> str:
    provider_type = normalize_ai_provider_type(provider.provider_type)
    if provider_type == AI_PROVIDER_OLLAMA:
        return request_ollama(provider, prompt, retries=retries)
    if provider_type == AI_PROVIDER_OPENAI_COMPATIBLE:
        return request_openai_compatible(provider, prompt, retries=retries)
    raise AiPlannerError(f"Неподдерживаемый AI provider: {provider.provider_type}")


def request_ollama(provider: AiProviderConfig, prompt: str, retries: int = 0) -> str:
    url = provider.endpoint.rstrip("/") + "/api/generate"
    payload = {
        "model": provider.model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": provider.temperature,
            "num_ctx": provider.num_ctx,
            "num_predict": provider.num_predict,
        },
    }
    max_attempts = max(1, retries + 1)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        timeout_step = max(20, provider.timeout)
        timeout_seconds = min(240, max(5, provider.timeout + (attempt - 1) * timeout_step))
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
                payload_data = json.loads(body)
                text = str(payload_data.get("response") or "").strip()
                if not text:
                    raise AiPlannerError("Ollama вернул пустой ответ.")
                return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 404:
                raise AiPlannerError(
                    f"Ollama не нашел модель '{provider.model}'. Проверьте имя модели в GUI."
                ) from exc
            raise AiPlannerError(f"Ollama HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_attempts and _is_timeout_error(exc):
                time.sleep(min(3.0, 0.8 * attempt))
                continue
            if _is_timeout_error(exc):
                raise AiPlannerError(
                    f"Ollama не ответил за {timeout_seconds}с (модель '{provider.model}'). "
                    "Увеличьте 'Таймаут AI' или выберите более быструю модель."
                ) from exc
            raise AiPlannerError(
                _format_ollama_unavailable_message(provider.endpoint.rstrip("/"), exc)
            ) from exc
        except (TimeoutError, socket.timeout) as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(3.0, 0.8 * attempt))
                continue
            raise AiPlannerError(
                f"Ollama не ответил за {timeout_seconds}с (модель '{provider.model}'). "
                "Увеличьте 'Таймаут AI' или выберите более быструю модель."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AiPlannerError(f"Некорректный JSON от Ollama: {exc}") from exc

    if last_error is not None:
        raise AiPlannerError(f"Ollama ошибка: {last_error}") from last_error
    raise AiPlannerError("Ollama ошибка: неизвестная причина.")


def request_openai_compatible(provider: AiProviderConfig, prompt: str, retries: int = 0) -> str:
    if not provider.endpoint.strip():
        raise AiPlannerError("Не указан OpenAI-compatible Base URL.")
    if not provider.model.strip():
        raise AiPlannerError("Не указана модель AI provider.")
    url = _chat_completions_url(provider.endpoint)
    max_attempts = max(1, retries + 1)
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        timeout_step = max(20, provider.timeout)
        timeout_seconds = min(240, max(5, provider.timeout + (attempt - 1) * timeout_step))
        payload = {
            "model": provider.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": provider.temperature,
        }
        if "o1" in provider.model.lower() or "o3" in provider.model.lower() or "deepseek-reasoner" in provider.model.lower():
            payload["max_completion_tokens"] = provider.num_predict
        else:
            payload["max_tokens"] = provider.num_predict

        if "openrouter.ai" not in provider.endpoint.lower() and "groq" not in provider.endpoint.lower():
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/mrgigabyte/GithubSearch",
            "X-Title": "GithubSearchAI"
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        if provider.api_key.strip():
            request.add_header("Authorization", f"Bearer {provider.api_key.strip()}")
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
                payload_data = json.loads(body)
                text = _extract_openai_chat_text(payload_data)
                if not text:
                    raise AiPlannerError("AI provider вернул пустой ответ.")
                return text
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in {401, 403}:
                raise AiPlannerError(
                    "AI provider отклонил API key или доступ к модели. "
                    "Проверьте сохраненный ключ, права аккаунта и model id."
                ) from exc
            if exc.code == 404:
                raise AiPlannerError(
                    f"AI provider не нашел endpoint или модель '{provider.model}'. "
                    "Проверьте Base URL и model id."
                ) from exc
            if exc.code == 429:
                raise AiPlannerError(
                    "AI provider вернул rate limit 429. Подождите или выберите другой key/model/provider."
                ) from exc
            raise AiPlannerError(f"AI provider HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < max_attempts and _is_timeout_error(exc):
                time.sleep(min(3.0, 0.8 * attempt))
                continue
            if _is_timeout_error(exc):
                raise AiPlannerError(
                    f"AI provider не ответил за {timeout_seconds}с (модель '{provider.model}'). "
                    "Увеличьте 'Таймаут AI' или выберите более быструю модель."
                ) from exc
            raise AiPlannerError(_format_ai_provider_unavailable_message(provider.endpoint, exc)) from exc
        except (TimeoutError, socket.timeout) as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(min(3.0, 0.8 * attempt))
                continue
            raise AiPlannerError(
                f"AI provider не ответил за {timeout_seconds}с (модель '{provider.model}'). "
                "Увеличьте 'Таймаут AI' или выберите более быструю модель."
            ) from exc
        except json.JSONDecodeError as exc:
            raise AiPlannerError(f"Некорректный JSON от AI provider: {exc}") from exc

    if last_error is not None:
        raise AiPlannerError(f"AI provider ошибка: {last_error}") from last_error
    raise AiPlannerError("AI provider ошибка: неизвестная причина.")


def normalize_ai_provider_type(provider_type: str) -> str:
    value = str(provider_type or "").strip().lower().replace("_", "-")
    if value in {"", "ollama", "ollama-local"}:
        return AI_PROVIDER_OLLAMA
    if value in {"openai", "openai-compatible", "openai-compatible-api", "custom"}:
        return AI_PROVIDER_OPENAI_COMPATIBLE
    return value


def _chat_completions_url(endpoint: str) -> str:
    base_url = endpoint.strip().rstrip("/")
    if base_url.lower().endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def _extract_openai_chat_text(payload: dict) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    elif part.get("type") == "text" and isinstance(part.get("content"), str):
                        parts.append(str(part.get("content")))
            return "\n".join(parts).strip()
    text = first.get("text")
    return str(text or "").strip()


def _is_timeout_error(exc: urllib.error.URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(exc).lower()


def _format_ai_provider_unavailable_message(endpoint: str, exc: urllib.error.URLError) -> str:
    base_url = endpoint.strip().rstrip("/") or "не указан"
    reason = getattr(exc, "reason", exc)
    reason_text = str(reason)
    errno_value = getattr(reason, "errno", None)
    winerror_value = getattr(reason, "winerror", None)
    is_refused = isinstance(reason, ConnectionRefusedError) or errno_value in {10061, 111} or winerror_value == 10061

    if is_refused:
        return (
            f"AI provider не запущен или не слушает endpoint {base_url}. "
            "Запустите локальный сервер или исправьте Base URL."
        )

    return (
        f"AI provider недоступен по endpoint {base_url}. "
        f"Проверьте адрес, порт, firewall/VPN и что сервис запущен. Детали: {reason_text}"
    )


def _format_ollama_unavailable_message(endpoint: str, exc: urllib.error.URLError) -> str:
    base_url = endpoint.strip().rstrip("/") or "не указан"
    reason = getattr(exc, "reason", exc)
    reason_text = str(reason)
    errno_value = getattr(reason, "errno", None)
    winerror_value = getattr(reason, "winerror", None)
    is_refused = isinstance(reason, ConnectionRefusedError) or errno_value in {10061, 111} or winerror_value == 10061

    if is_refused:
        return (
            f"Ollama не запущен или не слушает endpoint {base_url}. "
            "Запустите Ollama (`ollama serve` или приложение Ollama), затем нажмите "
            "`Обновить модели`. Если Ollama работает на другом компьютере или порту, "
            "исправьте поле `Ollama endpoint`."
        )

    return (
        f"Ollama недоступен по endpoint {base_url}. "
        f"Проверьте адрес, порт, firewall/VPN и что сервер Ollama запущен. Детали: {reason_text}"
    )


def parse_json_object(raw_text: str) -> dict:
    raw = raw_text.strip()
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        payload = None

    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        raise AiPlannerError("AI вернул невалидный JSON.")
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AiPlannerError("AI вернул JSON с ошибкой синтаксиса.") from exc
    if not isinstance(payload, dict):
        raise AiPlannerError("AI должен вернуть JSON-объект.")
    return payload


def normalize_plan(payload: dict, task_text: str) -> AiPlanResult:
    raw_query = normalize_text(payload.get("query")) or task_text.strip()
    query = sanitize_planner_query(raw_query) or task_text.strip()
    folder_name = sanitize_folder_name(normalize_text(payload.get("folder_name")) or query)
    sort = normalize_sort(payload.get("sort"))
    order = normalize_order(payload.get("order"))

    return AiPlanResult(
        query=query,
        folder_name=folder_name,
        min_stars=clamp_int(payload.get("min_stars"), default=0, min_value=0, max_value=100_000),
        language=normalize_text(payload.get("language")),
        max_age_years=clamp_int(payload.get("max_age_years"), default=5, min_value=0, max_value=15),
        max_repos=clamp_int(payload.get("max_repos"), default=100, min_value=0, max_value=50_000),
        batch_size=clamp_int(payload.get("batch_size"), default=100, min_value=1, max_value=500),
        workers=clamp_int(payload.get("workers"), default=6, min_value=1, max_value=32),
        clone_timeout=clamp_int(payload.get("clone_timeout"), default=300, min_value=30, max_value=7200),
        retry_failed_clones=clamp_int(payload.get("retry_failed_clones"), default=2, min_value=0, max_value=10),
        retry_delay_seconds=clamp_int(payload.get("retry_delay_seconds"), default=5, min_value=0, max_value=120),
        include_forks=to_bool(payload.get("include_forks"), False),
        include_archived=to_bool(payload.get("include_archived"), False),
        sort=sort,
        order=order,
    )


def sanitize_folder_name(name: str) -> str:
    cleaned = INVALID_FOLDER_CHARS.sub("_", name.strip())
    cleaned = NON_WORD.sub("_", cleaned).strip("._- ")
    cleaned = re.sub(r"_+", "_", cleaned)
    if not cleaned:
        cleaned = "project"
    return cleaned[:80].strip("._- ") or "project"


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def sanitize_planner_query(raw_query: str) -> str:
    query = normalize_text(raw_query)
    if not query:
        return ""

    # Keep topic values as plain terms and remove structured qualifiers handled by separate fields.
    query = re.sub(r"\btopic:([^\s()]+)", r"\1", query, flags=re.IGNORECASE)
    query = PLANNER_QUERY_QUALIFIER.sub(" ", query)
    query = re.sub(r"\s+", " ", query).strip()

    tokens = re.findall(r'"[^"]+"|\S+', query)
    cleaned: list[str] = []
    previous_is_operator = True
    for token in tokens:
        upper = token.upper()
        is_operator = upper in {"AND", "OR", "NOT"}
        if is_operator:
            if previous_is_operator:
                continue
            cleaned.append(upper)
            previous_is_operator = True
            continue
        cleaned.append(token)
        previous_is_operator = False

    while cleaned and cleaned[-1] in {"AND", "OR", "NOT"}:
        cleaned.pop()
    if not cleaned:
        return ""
    return " ".join(cleaned).strip()


def clamp_int(value: object, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def normalize_sort(value: object) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in ("stars", "updated") else "stars"


def normalize_order(value: object) -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in ("desc", "asc") else "desc"


def to_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on", "да"):
            return True
        if lowered in ("false", "0", "no", "off", "нет"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default
