from __future__ import annotations

import json
import math
import re
import threading
import time
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Sequence

from github_harvester.ai_exporter import export_repo_for_ai
from github_harvester.ai_planner import (
    AI_PROVIDER_OLLAMA,
    AI_PROVIDER_OPENAI_COMPATIBLE,
    AiProviderConfig,
    normalize_ai_provider_type,
    parse_json_object,
    request_ai,
)
from github_harvester.downloader import CloneOptions, CloneResult, download_repositories, ensure_git_available
from github_harvester.exporters import export_repositories_to_sqlite
from github_harvester.github_api import (
    GitHubApiError,
    GitHubCancelledError,
    GitHubClient,
    collect_repositories,
    enrich_repositories_with_graphql,
    sort_repositories,
)
from github_harvester.models import Repo, SearchOptions
from github_harvester.run_state import (
    collect_repository_ids_from_metadata,
    filter_repositories_for_resume,
    initialize_run_state,
    record_clone_result,
)


class RunCancelledError(RuntimeError):
    """Raised when run is cancelled by user."""


@dataclass(frozen=True)
class RunConfig:
    query: str
    output_root: Path
    token: str = ""
    min_stars: int = 0
    language: str = ""
    include_forks: bool = False
    include_archived: bool = False
    created_after: date = date(2008, 1, 1)
    created_before: date = date.today()
    max_age_years: int = 5
    sort: str = "stars"
    order: str = "desc"
    max_repos: int = 0
    workers: int = 4
    batch_size: int = 100
    clone_timeout: int = 300
    clone_depth: int = 1
    clone_partial: bool = True
    clone_single_branch: bool = True
    clone_no_tags: bool = True
    retry_failed_clones: int = 2
    retry_delay_seconds: int = 5
    request_timeout: int = 30
    max_retries: int = 5
    max_rate_limit_wait: int = 900
    skip_existing: bool = True
    no_sharding: bool = False
    dry_run: bool = False
    ai_filter_enabled: bool = False
    ai_provider_type: str = AI_PROVIDER_OLLAMA
    ai_filter_endpoint: str = ""
    ai_filter_model: str = ""
    ai_api_key: str = ""
    ai_filter_timeout: int = 20
    ai_temperature: float = 0.0
    ai_num_ctx: int = 4096
    ai_num_predict: int = 768
    ai_filter_min_score: float = 0.55
    ai_filter_max_reviews: int = 10
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    incremental: bool = False
    resume_state_file: Path | None = None
    export_sqlite: Path | None = None
    graphql_enrich: bool = False
    graphql_batch_size: int = 25
    deep_relevance_enabled: bool = False
    deep_relevance_max_repos: int = 25
    deep_relevance_min_score: float = 0.0
    ai_custom_prompt: str = ""
    export_csv: bool = False
    export_ai_ready: bool = False


@dataclass(frozen=True)
class RunSummary:
    found_count: int
    cloned_count: int
    skipped_count: int
    failed_count: int
    cancelled_count: int
    output_root: Path
    repos_dir: Path
    metadata_file: Path
    failure_report_file: Path | None
    run_log_file: Path
    run_state_file: Path | None = None
    sqlite_file: Path | None = None


_KEY_VALUE_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|token|github_token|access_token|api_key|password)\b(\s*[:=]\s*)([^\s,;]+)"
)
_AUTH_BEARER_HEADER_PATTERN = re.compile(r"(?i)\bauthorization\b(\s*[:=]\s*)bearer\s+([^\s,;]+)")
_BEARER_SECRET_PATTERN = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._\-]+)")
_URL_CREDENTIALS_PATTERN = re.compile(r"(?i)(https?://)([^/\s:@]+):([^/\s@]+)@")
_URL_TOKEN_USERINFO_PATTERN = re.compile(
    r"(?i)(https?://)((?:gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{20,}))@"
)
_GITHUB_CLASSIC_TOKEN_PATTERN = re.compile(r"\b(gh[pousr]_)[A-Za-z0-9_]{16,}\b")
_GITHUB_FINE_GRAINED_TOKEN_PATTERN = re.compile(r"\b(github_pat_)[A-Za-z0-9_]{20,}\b")
_LINE_BREAK_PATTERN = re.compile(r"[\r\n\x85\u2028\u2029]+")
_LOGICAL_OPERATOR_PATTERN = re.compile(r"\b(?:AND|OR|NOT)\b", flags=re.IGNORECASE)
_QUALIFIER_TOKEN_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:[^\s]+$")
MAX_GITHUB_LOGICAL_OPERATORS = 5
MAX_SAFE_OR_TERMS = MAX_GITHUB_LOGICAL_OPERATORS + 1
METADATA_SCHEMA_VERSION = 4


def redact_sensitive_text(text: str) -> str:
    value = str(text)
    value = _AUTH_BEARER_HEADER_PATTERN.sub(r"Authorization\1Bearer ***", value)
    value = _KEY_VALUE_SECRET_PATTERN.sub(r"\1\2***", value)
    value = _BEARER_SECRET_PATTERN.sub("Bearer ***", value)
    value = _URL_CREDENTIALS_PATTERN.sub(r"\1***:***@", value)
    value = _URL_TOKEN_USERINFO_PATTERN.sub(r"\1***@", value)
    value = _GITHUB_FINE_GRAINED_TOKEN_PATTERN.sub(r"\1***", value)
    value = _GITHUB_CLASSIC_TOKEN_PATTERN.sub(r"\1***", value)
    return value


def normalize_log_text(text: str) -> str:
    value = str(text)
    value = _LINE_BREAK_PATTERN.sub(" | ", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def atomic_write_text(target_path: Path, content: str, encoding: str = "utf-8") -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.tmp_{time.time_ns()}")
    try:
        temp_path.write_text(content, encoding=encoding)
        temp_path.replace(target_path)
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)


def validate_run_config(config: RunConfig) -> None:
    if not config.query.strip():
        raise ValueError("Запрос не может быть пустым.")
    if config.created_after > config.created_before:
        raise ValueError("Дата начала должна быть меньше или равна дате конца.")
    if config.workers < 1:
        raise ValueError("Количество потоков должно быть не меньше 1.")
    if config.max_repos < 0:
        raise ValueError("Параметр max_repos должен быть не меньше 0.")
    if config.min_stars < 0:
        raise ValueError("Параметр min_stars должен быть не меньше 0.")
    if config.batch_size < 1:
        raise ValueError("Размер пакета должен быть не меньше 1.")
    if config.retry_failed_clones < 0:
        raise ValueError("Количество повторов должно быть не меньше 0.")
    if config.retry_delay_seconds < 0:
        raise ValueError("Задержка перед повтором должна быть не меньше 0.")
    if config.max_age_years < 0:
        raise ValueError("Параметр max_age_years должен быть не меньше 0.")
    if config.clone_timeout < 10:
        raise ValueError("Параметр clone_timeout должен быть не меньше 10 секунд.")
    if config.clone_depth < 0:
        raise ValueError("Параметр clone_depth должен быть не меньше 0.")
    if config.request_timeout < 5:
        raise ValueError("Параметр request_timeout должен быть не меньше 5 секунд.")
    if config.max_retries < 0:
        raise ValueError("Параметр max_retries должен быть не меньше 0.")
    if config.max_rate_limit_wait < 1:
        raise ValueError("Параметр max_rate_limit_wait должен быть не меньше 1.")
    if config.sort not in {"stars", "updated"}:
        raise ValueError("Параметр sort должен быть stars или updated.")
    if config.order not in {"desc", "asc"}:
        raise ValueError("Параметр order должен быть desc или asc.")
    if config.ai_filter_timeout < 5:
        raise ValueError("Параметр ai_filter_timeout должен быть не меньше 5.")
    if normalize_ai_provider_type(config.ai_provider_type) not in {
        AI_PROVIDER_OLLAMA,
        AI_PROVIDER_OPENAI_COMPATIBLE,
    }:
        raise ValueError("Параметр ai_provider_type должен быть ollama или openai-compatible.")
    if not (0.0 <= config.ai_temperature <= 2.0):
        raise ValueError("Параметр ai_temperature должен быть в диапазоне 0..2.")
    if config.ai_num_ctx < 512:
        raise ValueError("Параметр ai_num_ctx должен быть не меньше 512.")
    if config.ai_num_predict < 16:
        raise ValueError("Параметр ai_num_predict должен быть не меньше 16.")
    if not (0.0 <= config.ai_filter_min_score <= 1.0):
        raise ValueError("Параметр ai_filter_min_score должен быть в диапазоне 0..1.")
    if config.ai_filter_max_reviews < 1:
        raise ValueError("Параметр ai_filter_max_reviews должен быть не меньше 1.")
    if config.graphql_batch_size < 1 or config.graphql_batch_size > 50:
        raise ValueError("Параметр graphql_batch_size должен быть в диапазоне 1..50.")
    if config.deep_relevance_max_repos < 1:
        raise ValueError("Параметр deep_relevance_max_repos должен быть не меньше 1.")
    if not (0.0 <= config.deep_relevance_min_score <= 1.0):
        raise ValueError("Параметр deep_relevance_min_score должен быть в диапазоне 0..1.")
    if config.resume_state_file is not None and not config.resume_state_file.expanduser().exists():
        raise ValueError(f"Файл состояния для resume не найден: {config.resume_state_file}")


def maybe_enrich_repositories_with_graphql(
    config: RunConfig,
    client: GitHubClient,
    repositories: Sequence[Repo],
    log: Callable[[str], None],
    should_cancel: Callable[[], bool],
) -> list[Repo]:
    if not config.graphql_enrich or not repositories:
        return list(repositories)
    if not config.token.strip():
        log("GraphQL enrichment включен, но GITHUB_TOKEN не задан. Enrichment пропущен.")
        return list(repositories)
    try:
        enriched = enrich_repositories_with_graphql(
            client=client,
            repositories=list(repositories),
            batch_size=config.graphql_batch_size,
            log=log,
            should_cancel=should_cancel,
        )
    except GitHubCancelledError as exc:
        raise RunCancelledError(str(exc)) from exc
    except Exception as exc:
        log(f"GraphQL enrichment не выполнен, используем REST metadata: {exc}")
        return list(repositories)
    enriched_count = sum(1 for repo in enriched if repo.graphql_enriched)
    log(f"GraphQL enrichment завершен: enriched={enriched_count}/{len(enriched)}.")
    return enriched


def parse_iso_date(raw_date: str, field_name: str) -> date:
    try:
        return datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Неверный формат поля '{field_name}': {raw_date}. Используйте YYYY-MM-DD.") from exc


def normalize_query_for_search(raw_query: str) -> tuple[str, str | None]:
    query = raw_query.strip()
    if not query:
        return query, None

    # Preserve explicit GitHub syntax when user controls query manually.
    if re.search(r'\b(?:OR|AND|NOT)\b|[()"]|\b[a-zA-Z_]+:', query, flags=re.IGNORECASE):
        operator_count = len(_LOGICAL_OPERATOR_PATTERN.findall(query))
        if operator_count > MAX_GITHUB_LOGICAL_OPERATORS:
            relaxed_query = build_relaxed_query_from_strict(query)
            if relaxed_query:
                message = (
                    "Запрос упрощен для совместимости с GitHub Search API: "
                    f"найдено {operator_count} логических операторов (лимит GitHub: {MAX_GITHUB_LOGICAL_OPERATORS}). "
                    f"Используем безопасный вариант: '{query}' -> '{relaxed_query}'."
                )
                return relaxed_query, message
        if not query_has_search_terms(query):
            relaxed_query = build_relaxed_query_from_strict(query)
            if relaxed_query:
                message = (
                    "Запрос содержит только операторы/фильтры GitHub без явных поисковых терминов. "
                    f"Используем безопасный вариант: '{query}' -> '{relaxed_query}'."
                )
                return relaxed_query, message
        return query, None

    terms: list[str] = []
    seen_terms: set[str] = set()
    for token in re.split(r"[\s,;|]+", query):
        term = token.strip()
        if not term or len(term) < 2:
            continue
        lowered = term.lower()
        if lowered in seen_terms:
            continue
        terms.append(term)
        seen_terms.add(lowered)

    if len(terms) <= 1:
        return query, None

    normalized_terms = terms[:MAX_SAFE_OR_TERMS]
    normalized = "(" + " OR ".join(normalized_terms) + ")"
    message = (
        "Нормализован текст запроса для GitHub-поиска: "
        f"'{query}' -> '{normalized}'. "
        "Для строгого режима используйте явный AND/NOT/qualifiers."
    )
    return normalized, message


def build_relaxed_query_from_strict(raw_query: str) -> str | None:
    query = raw_query.strip()
    if not query:
        return None

    stop_words = {
        "or",
        "and",
        "not",
        "stars",
        "language",
        "created",
        "updated",
        "fork",
        "archived",
        "topic",
        "in",
        "sort",
        "desc",
        "asc",
    }
    terms: list[str] = []
    seen: set[str] = set()
    skip_next_for_not = False
    for raw_token in re.split(r"\s+", query):
        token = raw_token.strip().strip("()[]{}\"'")
        if not token:
            continue
        upper_token = token.upper()
        if upper_token in {"AND", "OR"}:
            skip_next_for_not = False
            continue
        if upper_token == "NOT":
            skip_next_for_not = True
            continue
        if skip_next_for_not:
            skip_next_for_not = False
            continue
        value = token.split(":", maxsplit=1)[1] if ":" in token else token
        value = re.sub(r"^[><=]+", "", value)
        value = value.replace("..", " ")
        for piece in re.split(r"[^\w]+", value, flags=re.UNICODE):
            term = piece.strip().lower()
            if not term:
                continue
            if term in stop_words:
                continue
            if term.isdigit():
                continue
            if re.fullmatch(r"\d{4}", term):
                continue
            if len(term) < 2:
                continue
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)

    if len(terms) <= 1:
        return None
    relaxed = "(" + " OR ".join(terms[:MAX_SAFE_OR_TERMS]) + ")"
    if relaxed.lower() == query.lower():
        return None
    return relaxed


def query_has_search_terms(query: str) -> bool:
    for raw_token in re.findall(r'"[^"]+"|\S+', query):
        token = raw_token.strip()
        if not token:
            continue
        token = token.strip("()")
        if not token:
            continue
        upper_token = token.upper()
        if upper_token in {"AND", "OR", "NOT"}:
            continue
        if _QUALIFIER_TOKEN_PATTERN.fullmatch(token):
            continue
        if token.startswith('"') and token.endswith('"'):
            inner = token[1:-1].strip()
            if inner:
                return True
            continue
        if any(char.isalnum() for char in token):
            return True
    return False


def should_retry_with_relaxed_query(error_message: str) -> bool:
    lowered = str(error_message or "").lower()
    return "422" in lowered or "validation failed" in lowered


def build_query_recovery_candidate(query: str) -> str | None:
    relaxed = build_relaxed_query_from_strict(query)
    if relaxed:
        return relaxed
    terms = extract_query_terms_for_ai_filter(query)
    if len(terms) >= 2:
        return "(" + " OR ".join(terms[:MAX_SAFE_OR_TERMS]) + ")"
    return None


def should_expand_query_for_low_results(query: str, found_count: int, requested_max_repos: int) -> bool:
    if found_count <= 0:
        return True
    if requested_max_repos <= 0:
        return False
    complex_query = bool(re.search(r'\b(?:OR|AND|NOT)\b|[()"]|\b[a-zA-Z_]+:', query, flags=re.IGNORECASE))
    if not complex_query:
        return False
    expected_min = min(40, max(8, requested_max_repos // 10))
    return found_count < expected_min


def apply_max_age_filter(created_after: date, max_age_years: int, today: date | None = None) -> date:
    if max_age_years <= 0:
        return created_after
    current_day = today or date.today()
    age_border = current_day - timedelta(days=365 * max_age_years)
    return max(created_after, age_border)


def split_into_batches(repositories: Sequence[Repo], batch_size: int) -> list[list[Repo]]:
    if not repositories:
        return []
    if batch_size <= 0 or batch_size >= len(repositories):
        return [list(repositories)]
    return [list(repositories[index : index + batch_size]) for index in range(0, len(repositories), batch_size)]


def parse_keyword_list(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, (list, tuple, set)):
        source = [str(item) for item in raw_value]
    else:
        source = re.split(r"[,;\n|]+", str(raw_value))
    result: list[str] = []
    seen: set[str] = set()
    for item in source:
        term = str(item).strip().lower()
        if not term or term in seen:
            continue
        seen.add(term)
        result.append(term)
    return tuple(result)


def filter_repositories_by_keywords(
    repositories: Sequence[Repo],
    include_keywords: Sequence[str],
    exclude_keywords: Sequence[str],
) -> tuple[list[Repo], int, int]:
    include_terms = [term.lower() for term in include_keywords if term]
    exclude_terms = [term.lower() for term in exclude_keywords if term]
    if not include_terms and not exclude_terms:
        return list(repositories), 0, 0

    kept: list[Repo] = []
    include_dropped = 0
    exclude_dropped = 0
    for repo in repositories:
        text = _repo_keyword_text(repo)
        if include_terms and not any(term in text for term in include_terms):
            include_dropped += 1
            continue
        if exclude_terms and any(term in text for term in exclude_terms):
            exclude_dropped += 1
            continue
        kept.append(repo)
    return kept, include_dropped, exclude_dropped


def _repo_keyword_text(repo: Repo) -> str:
    return " ".join(
        [
            repo.full_name,
            repo.description,
            repo.language,
            " ".join(repo.topics),
        ]
    ).lower()


def resolve_output_relative_path(output_root: Path, path_value: Path | None) -> Path | None:
    if path_value is None:
        return None
    path = path_value.expanduser()
    if path.is_absolute():
        return path
    return output_root / path


def build_softened_search_options(options: SearchOptions) -> tuple[SearchOptions | None, str | None]:
    next_min_stars = options.min_stars
    next_language = options.language.strip()
    changes: list[str] = []

    if next_min_stars >= 80:
        relaxed_min_stars = max(30, int(next_min_stars * 0.6))
        if relaxed_min_stars < next_min_stars:
            changes.append(f"min_stars: {next_min_stars} -> {relaxed_min_stars}")
            next_min_stars = relaxed_min_stars
    elif next_min_stars >= 40:
        relaxed_min_stars = max(20, next_min_stars // 2)
        if relaxed_min_stars < next_min_stars:
            changes.append(f"min_stars: {next_min_stars} -> {relaxed_min_stars}")
            next_min_stars = relaxed_min_stars

    if next_language:
        changes.append(f"language: '{next_language}' -> ''")
        next_language = ""

    if not changes:
        return None, None

    softened = SearchOptions(
        query=options.query,
        min_stars=next_min_stars,
        language=next_language,
        include_forks=options.include_forks,
        include_archived=options.include_archived,
        created_after=options.created_after,
        created_before=options.created_before,
        sort=options.sort,
        order=options.order,
    )
    return softened, ", ".join(changes)


def merge_repository_sets(base: Sequence[Repo], extra: Sequence[Repo], sort: str, order: str) -> list[Repo]:
    by_id: dict[int, Repo] = {}
    for repository in base:
        by_id[repository.id] = repository
    for repository in extra:
        by_id[repository.id] = repository
    return sort_repositories(by_id.values(), sort=sort, order=order)


def run_collection(
    config: RunConfig,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> RunSummary:
    incoming_logger = log or (lambda _: None)

    def is_cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def check_cancelled() -> None:
        if is_cancelled():
            raise RunCancelledError("Операция остановлена пользователем.")

    validate_run_config(config)
    query = config.query.strip()
    query, normalization_message = normalize_query_for_search(query)

    output_root = config.output_root.expanduser().resolve()
    repos_dir = output_root / "repos"
    metadata_dir = output_root / "metadata"
    output_root.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_file = metadata_dir / f"run_{run_stamp}.log"
    atomic_write_text(run_log_file, "", encoding="utf-8-sig")
    sqlite_file = resolve_output_relative_path(output_root, config.export_sqlite)
    resume_state_file = config.resume_state_file.expanduser() if config.resume_state_file else None
    incremental_seen_ids = (
        collect_repository_ids_from_metadata(metadata_dir) if config.incremental else set()
    )

    def logger(message: str) -> None:
        safe_message = normalize_log_text(redact_sensitive_text(message))
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {safe_message}"
        incoming_logger(line)
        with run_log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    logger(
        "Параметры запуска: "
        f"query='{query}', min_stars={config.min_stars}, language='{config.language.strip()}', "
        f"created_after={config.created_after.isoformat()}, created_before={config.created_before.isoformat()}, "
        f"max_age_years={config.max_age_years}, sort={config.sort}, order={config.order}, "
        f"max_repos={config.max_repos}, batch_size={config.batch_size}, workers={config.workers}, "
        f"clone_timeout={config.clone_timeout}, retry_failed_clones={config.retry_failed_clones}, "
        f"retry_delay_seconds={config.retry_delay_seconds}, skip_existing={config.skip_existing}, "
        f"clone_depth={config.clone_depth}, clone_partial={config.clone_partial}, "
        f"clone_single_branch={config.clone_single_branch}, clone_no_tags={config.clone_no_tags}, "
        f"no_sharding={config.no_sharding}, dry_run={config.dry_run}, "
        f"ai_filter_enabled={config.ai_filter_enabled}, ai_filter_timeout={config.ai_filter_timeout}, "
        f"ai_filter_min_score={config.ai_filter_min_score}, ai_filter_max_reviews={config.ai_filter_max_reviews}, "
        f"include_keywords={list(config.include_keywords)}, exclude_keywords={list(config.exclude_keywords)}, "
        f"incremental={config.incremental}, resume_state_file={resume_state_file}, "
        f"export_sqlite={sqlite_file}, graphql_enrich={config.graphql_enrich}, "
        f"graphql_batch_size={config.graphql_batch_size}, "
        f"deep_relevance_enabled={config.deep_relevance_enabled}, "
        f"deep_relevance_max_repos={config.deep_relevance_max_repos}, "
        f"deep_relevance_min_score={config.deep_relevance_min_score}"
    )
    if normalization_message:
        logger(normalization_message)
    logger(f"Папка проекта: {output_root}")
    logger(f"Папка репозиториев: {repos_dir}")
    logger(f"Папка метаданных: {metadata_dir}")
    if config.incremental:
        logger(
            "Инкрементальный режим: найдено ранее записанных repo_id="
            f"{len(incremental_seen_ids)}."
        )

    check_cancelled()
    if not config.dry_run:
        ensure_git_available()

    effective_created_after = apply_max_age_filter(config.created_after, config.max_age_years)
    if effective_created_after != config.created_after:
        logger(
            "Применен фильтр возраста: "
            f"репозитории не старше {config.max_age_years} лет "
            f"(с {effective_created_after.isoformat()})."
        )

    options = SearchOptions(
        query=query,
        min_stars=config.min_stars,
        language=config.language.strip(),
        include_forks=config.include_forks,
        include_archived=config.include_archived,
        created_after=effective_created_after,
        created_before=config.created_before,
        sort=config.sort,
        order=config.order,
    )

    client = GitHubClient(
        token=config.token.strip(),
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        max_rate_limit_wait=config.max_rate_limit_wait,
        log=logger,
        should_cancel=is_cancelled,
    )

    use_date_sharding = not config.no_sharding
    if use_date_sharding and config.max_repos > 0 and config.max_repos <= 1000:
        use_date_sharding = False
        logger(
            "Авто-режим поиска: шардирование отключено (max_repos <= 1000), "
            "чтобы ускорить поиск и снизить риск лимитов GitHub API."
        )
    elif use_date_sharding:
        logger("Режим поиска: шардирование по датам включено.")
    else:
        logger("Режим поиска: шардирование отключено вручную.")

    search_limit = config.max_repos if config.max_repos > 0 else None
    if config.ai_filter_enabled and search_limit:
        expanded_limit = min(
            1000,
            max(
                search_limit,
                search_limit * 6,
                search_limit + 500,
                config.ai_filter_max_reviews * 12,
            ),
        )
        if expanded_limit > search_limit:
            logger(
                "AI-фильтр включен: расширяем выборку перед проверкой "
                f"{search_limit} -> {expanded_limit}"
            )
            search_limit = expanded_limit

    def collect_for(active_options: SearchOptions) -> list[Repo]:
        try:
            return collect_repositories(
                client=client,
                options=active_options,
                max_repositories=search_limit,
                use_date_sharding=use_date_sharding,
                log=logger,
                should_cancel=is_cancelled,
            )
        except GitHubCancelledError as exc:
            raise RunCancelledError(str(exc)) from exc

    try:
        repositories = collect_for(options)
    except GitHubApiError as exc:
        recovery_query = None
        if should_retry_with_relaxed_query(str(exc)):
            recovery_query = build_query_recovery_candidate(query)
        if not recovery_query or recovery_query == query:
            raise
        logger(
            "GitHub отклонил исходный запрос. "
            f"Пробуем безопасный fallback: '{query}' -> '{recovery_query}'. "
            f"Причина: {exc}"
        )
        recovery_options = SearchOptions(
            query=recovery_query,
            min_stars=options.min_stars,
            language=options.language,
            include_forks=options.include_forks,
            include_archived=options.include_archived,
            created_after=options.created_after,
            created_before=options.created_before,
            sort=options.sort,
            order=options.order,
        )
        repositories = collect_for(recovery_options)
        options = recovery_options
        query = recovery_query
    should_try_relaxed = should_expand_query_for_low_results(query, len(repositories), config.max_repos)
    if should_try_relaxed:
        relaxed_query = build_relaxed_query_from_strict(query)
        if relaxed_query:
            if repositories:
                expected_min = min(40, max(8, config.max_repos // 10)) if config.max_repos > 0 else 8
                logger(
                    "Поиск вернул слишком мало результатов "
                    f"({len(repositories)} < {expected_min}). "
                    f"Пробуем безопасное расширение запроса: '{query}' -> '{relaxed_query}'."
                )
            else:
                logger(
                    "Поиск вернул 0 результатов. "
                    f"Пробуем безопасное расширение запроса: '{query}' -> '{relaxed_query}'."
                )
            relaxed_options = SearchOptions(
                query=relaxed_query,
                min_stars=options.min_stars,
                language=options.language,
                include_forks=options.include_forks,
                include_archived=options.include_archived,
                created_after=options.created_after,
                created_before=options.created_before,
                sort=options.sort,
                order=options.order,
            )
            try:
                relaxed_repositories = collect_repositories(
                    client=client,
                    options=relaxed_options,
                    max_repositories=search_limit,
                    use_date_sharding=use_date_sharding,
                    log=logger,
                    should_cancel=is_cancelled,
                )
            except GitHubCancelledError as exc:
                raise RunCancelledError(str(exc)) from exc
            if len(relaxed_repositories) > len(repositories):
                options = relaxed_options
                query = relaxed_query
                repositories = relaxed_repositories
                logger(f"После расширения запроса найдено репозиториев: {len(repositories)}")
            elif repositories:
                logger(
                    "Расширение запроса не улучшило результат, оставляем исходный набор: "
                    f"{len(repositories)}."
                )

    if config.ai_filter_enabled and config.max_repos > 0:
        expected_min_pool = min(80, max(16, config.max_repos // 5))
        if len(repositories) < expected_min_pool:
            softened_options, softened_note = build_softened_search_options(options)
            if softened_options and softened_note:
                logger(
                    "Результатов пока мало для устойчивого AI-отбора "
                    f"({len(repositories)} < {expected_min_pool}). "
                    f"Пробуем расширенный проход: {softened_note}."
                )
                try:
                    widened_repositories = collect_for(softened_options)
                except GitHubApiError as exc:
                    logger(f"Расширенный проход пропущен из-за ошибки GitHub API: {exc}")
                else:
                    merged_repositories = merge_repository_sets(
                        repositories,
                        widened_repositories,
                        sort=options.sort,
                        order=options.order,
                    )
                    added_count = len(merged_repositories) - len(repositories)
                    if added_count > 0:
                        repositories = merged_repositories
                        logger(
                            "Расширенный проход добавил "
                            f"{added_count} репозиториев (итого: {len(repositories)})."
                        )
                    else:
                        logger("Расширенный проход не добавил новых репозиториев.")

    repositories, include_dropped, exclude_dropped = filter_repositories_by_keywords(
        repositories,
        include_keywords=config.include_keywords,
        exclude_keywords=config.exclude_keywords,
    )
    if include_dropped or exclude_dropped:
        logger(
            "Фильтр ключевых слов: "
            f"оставлено={len(repositories)}, "
            f"убрано_по_include={include_dropped}, убрано_по_exclude={exclude_dropped}."
        )

    if incremental_seen_ids:
        before_incremental = len(repositories)
        repositories = [repo for repo in repositories if repo.id not in incremental_seen_ids]
        skipped_incremental = before_incremental - len(repositories)
        if skipped_incremental:
            logger(
                "Инкрементальный режим: пропущено уже записанных репозиториев="
                f"{skipped_incremental}, осталось новых={len(repositories)}."
            )

    if config.ai_filter_enabled:
        if not config.ai_filter_endpoint.strip() or not config.ai_filter_model.strip():
            logger("AI-фильтр включен, но endpoint/model не заданы. Проверка пропущена.")
        elif repositories:
            effective_ai_timeout = max(5, min(config.ai_filter_timeout, 120))
            if effective_ai_timeout != config.ai_filter_timeout:
                logger(
                    "AI-filter timeout скорректирован до "
                    f"{effective_ai_timeout}с (допустимый диапазон: 5..120)."
                )
            provider = AiProviderConfig(
                provider_type=config.ai_provider_type,
                endpoint=config.ai_filter_endpoint.strip(),
                model=config.ai_filter_model.strip(),
                api_key=config.ai_api_key.strip(),
                timeout=effective_ai_timeout,
                temperature=config.ai_temperature,
                num_ctx=config.ai_num_ctx,
                num_predict=config.ai_num_predict,
            )
            repositories = filter_repositories_with_ai(
                repositories=repositories,
                query=query,
                provider=provider,
                min_score=config.ai_filter_min_score,
                max_reviews=config.ai_filter_max_reviews,
                desired_keep_count=config.max_repos,
                should_cancel=is_cancelled,
                custom_ai_prompt=config.ai_custom_prompt,
                log=logger,
            )

    if config.max_repos > 0 and len(repositories) > config.max_repos:
        repositories = repositories[: config.max_repos]

    if resume_state_file is not None:
        repositories, resume_skipped = filter_repositories_for_resume(repositories, resume_state_file)
        logger(
            "Resume mode: "
            f"пропущено уже завершенных по state={resume_skipped}, осталось={len(repositories)}."
        )

    check_cancelled()
    repositories = maybe_enrich_repositories_with_graphql(
        config=config,
        client=client,
        repositories=repositories,
        log=logger,
        should_cancel=is_cancelled,
    )
    repositories = apply_deep_relevance_scoring(
        config=config,
        client=client,
        repositories=repositories,
        query=query,
        log=logger,
        should_cancel=is_cancelled,
    )
    check_cancelled()
    metadata_file = save_metadata(metadata_dir, query, options, repositories)
    if sqlite_file is not None:
        export_repositories_to_sqlite(sqlite_file, query, repositories, metadata_file)
        logger(f"SQLite export обновлен: {sqlite_file}")
    if config.export_csv:
        csv_file = sqlite_file.with_suffix(".csv") if sqlite_file else output_root / f"export_{run_stamp}.csv"
        from github_harvester.exporters import export_to_csv
        export_to_csv(csv_file, repositories)
        logger(f"CSV export обновлен: {csv_file}")
    if config.max_repos > 0:
        logger(
            f"Лимит max_repos={config.max_repos} активен: это верхняя граница для финального списка."
        )
    logger(f"Найдено репозиториев: {len(repositories)}")
    if repositories:
        preview = ", ".join(repo.full_name for repo in repositories[:10])
        logger(f"Превью найденных репозиториев (до 10): {preview}")
    logger(f"Метаданные сохранены: {metadata_file}")

    if config.dry_run:
        logger("Режим 'Только поиск' включен, клонирование пропущено.")
        return RunSummary(
            found_count=len(repositories),
            cloned_count=0,
            skipped_count=0,
            failed_count=0,
            cancelled_count=0,
            output_root=output_root,
            repos_dir=repos_dir,
            metadata_file=metadata_file,
            failure_report_file=None,
            run_log_file=run_log_file,
            run_state_file=None,
            sqlite_file=sqlite_file,
        )

    total_count = len(repositories)
    logger(f"Начинаем скачивание репозиториев: {total_count}")
    clone_options = CloneOptions(
        depth=config.clone_depth,
        partial_clone=config.clone_partial,
        single_branch=config.clone_single_branch,
        no_tags=config.clone_no_tags,
    )
    logger(
        "Стратегия клонирования: "
        f"depth={'full' if clone_options.depth == 0 else clone_options.depth}, "
        f"partial_blob_filter={clone_options.partial_clone}, "
        f"single_branch={clone_options.single_branch}, no_tags={clone_options.no_tags}."
    )
    if progress:
        progress(0, total_count)
    run_state_file = metadata_dir / f"run_state_{run_stamp}.json"
    initialize_run_state(
        run_state_file,
        query=query,
        metadata_file=metadata_file,
        repositories=repositories,
        mode="search-download",
    )
    logger(f"Run-state сохранен: {run_state_file}")

    status_labels = {
        "cloned": "скачан",
        "skipped": "пропущен",
        "failed": "ошибка",
        "cancelled": "остановлен",
    }

    def on_progress(done: int, total: int, result: CloneResult) -> None:
        try:
            record_clone_result(run_state_file, result)
        except Exception as exc:
            logger(f"Предупреждение: не удалось обновить run-state: {exc}")
        status_text = status_labels.get(result.status, result.status)
        logger(
            f"[{done}/{total}] {status_text}: {result.repo_full_name} | "
            f"path={result.target_path} | message={result.message}"
        )
        if progress:
            progress(done, total)

    def on_retry_progress(attempt: int, result: CloneResult) -> None:
        try:
            record_clone_result(run_state_file, result)
        except Exception as exc:
            logger(f"Предупреждение: не удалось обновить run-state после повтора: {exc}")
        status_text = status_labels.get(result.status, result.status)
        logger(
            f"[retry {attempt}] {status_text}: {result.repo_full_name} | "
            f"path={result.target_path} | message={result.message}"
        )

    repositories_map = {repo.full_name: repo for repo in repositories}
    all_results: dict[str, CloneResult] = {}
    batches = split_into_batches(repositories, config.batch_size)
    completed_primary = 0

    for batch_index, batch in enumerate(batches, start=1):
        check_cancelled()
        logger(f"Пакет {batch_index}/{len(batches)}: {len(batch)} репозиториев")
        batch_offset = completed_primary

        def on_batch_progress(done: int, _total: int, result: CloneResult) -> None:
            on_progress(batch_offset + done, total_count, result)

        batch_results = download_repositories(
            repositories=batch,
            output_root=repos_dir,
            workers=config.workers,
            clone_timeout=config.clone_timeout,
            skip_existing=config.skip_existing,
            progress_callback=on_batch_progress,
            log_callback=logger,
            cancel_event=cancel_event,
            clone_options=clone_options,
        )
        completed_primary += len(batch)
        batch_cloned = sum(1 for item in batch_results if item.status == "cloned")
        batch_skipped = sum(1 for item in batch_results if item.status == "skipped")
        batch_failed = sum(1 for item in batch_results if item.status == "failed")
        batch_cancelled = sum(1 for item in batch_results if item.status == "cancelled")
        logger(
            f"Итог пакета {batch_index}: cloned={batch_cloned}, skipped={batch_skipped}, "
            f"failed={batch_failed}, cancelled={batch_cancelled}"
        )
        for item in batch_results:
            all_results[item.repo_full_name] = item

        failed_names = [item.repo_full_name for item in batch_results if item.status == "failed"]
        if failed_names and config.retry_failed_clones > 0:
            logger(f"Неуспешных в пакете: {len(failed_names)}. Запускаем повторы.")

        for attempt in range(1, config.retry_failed_clones + 1):
            if not failed_names:
                break
            check_cancelled()
            logger(f"Повтор {attempt}/{config.retry_failed_clones} для {len(failed_names)} репозиториев")
            if config.retry_delay_seconds > 0:
                logger(f"Ожидание перед повтором: {config.retry_delay_seconds} сек")
                for _ in range(config.retry_delay_seconds):
                    check_cancelled()
                    time.sleep(1)

            retry_repositories = [
                repositories_map[full_name] for full_name in failed_names if full_name in repositories_map
            ]

            def on_retry_batch_progress(_done: int, _total: int, result: CloneResult) -> None:
                on_retry_progress(attempt, result)

            retry_results = download_repositories(
                repositories=retry_repositories,
                output_root=repos_dir,
                workers=config.workers,
                clone_timeout=config.clone_timeout,
                skip_existing=config.skip_existing,
                progress_callback=on_retry_batch_progress,
                log_callback=logger,
                cancel_event=cancel_event,
                clone_options=clone_options,
            )
            failed_names = []
            for item in retry_results:
                all_results[item.repo_full_name] = item
                if item.status == "failed":
                    failed_names.append(item.repo_full_name)
            logger(f"После повтора осталось ошибок: {len(failed_names)}")

    check_cancelled()
    results = list(all_results.values())
    success_count = sum(1 for item in results if item.status == "cloned")
    skipped_count = sum(1 for item in results if item.status == "skipped")
    cancelled_count = sum(1 for item in results if item.status == "cancelled")
    failed = [item for item in results if item.status == "failed"]

    logger(f"Скачано: {success_count}")
    logger(f"Пропущено: {skipped_count}")
    logger(f"Остановлено: {cancelled_count}")
    logger(f"Ошибок: {len(failed)}")
    if success_count == 0 and skipped_count > 0 and cancelled_count == 0 and not failed:
        logger("Новых репозиториев для скачивания нет: все найденные уже существуют в целевой папке.")

    if config.export_ai_ready:
        logger("Начат экспорт репозиториев для ИИ (AI-Ready Repomix)...")
        ai_exports_count = 0
        for item in results:
            if item.status in ("cloned", "skipped") and item.target_path and item.target_path.exists():
                try:
                    export_repo_for_ai(item.repo_full_name, item.target_path, output_root)
                    ai_exports_count += 1
                except Exception as exc:
                    logger(f"Ошибка AI-экспорта для {item.repo_full_name}: {exc}")
        logger(f"Успешно экспортировано для ИИ: {ai_exports_count}")

    failed_file: Path | None = None
    if failed:
        failed_file = metadata_dir / f"failed_clones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        atomic_write_text(
            failed_file,
            json.dumps(
                [
                    {
                        "full_name": item.repo_full_name,
                        "path": str(item.target_path),
                        "error": item.message,
                    }
                    for item in failed
                ],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger(f"Отчет об ошибках: {failed_file}")

    return RunSummary(
        found_count=len(repositories),
        cloned_count=success_count,
        skipped_count=skipped_count,
        failed_count=len(failed),
        cancelled_count=cancelled_count,
        output_root=output_root,
        repos_dir=repos_dir,
        metadata_file=metadata_file,
        failure_report_file=failed_file,
        run_log_file=run_log_file,
        run_state_file=run_state_file,
        sqlite_file=sqlite_file,
    )


def run_download_for_repositories(
    config: RunConfig,
    repositories: Sequence[Repo],
    metadata_file: Path | None = None,
    log: Callable[[str], None] | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> RunSummary:
    incoming_logger = log or (lambda _: None)

    def is_cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def check_cancelled() -> None:
        if is_cancelled():
            raise RunCancelledError("Операция остановлена пользователем.")

    validate_run_config(config)
    output_root = config.output_root.expanduser().resolve()
    repos_dir = output_root / "repos"
    metadata_dir = output_root / "metadata"
    output_root.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_log_file = metadata_dir / f"run_{run_stamp}.log"
    atomic_write_text(run_log_file, "", encoding="utf-8-sig")
    sqlite_file = resolve_output_relative_path(output_root, config.export_sqlite)
    resume_state_file = config.resume_state_file.expanduser() if config.resume_state_file else None

    def logger(message: str) -> None:
        safe_message = normalize_log_text(redact_sensitive_text(message))
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {safe_message}"
        incoming_logger(line)
        with run_log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    unique_by_name: dict[str, Repo] = {}
    for repository in repositories:
        unique_by_name[repository.full_name] = repository
    selected_repositories = list(unique_by_name.values())
    selected_repositories, include_dropped, exclude_dropped = filter_repositories_by_keywords(
        selected_repositories,
        include_keywords=config.include_keywords,
        exclude_keywords=config.exclude_keywords,
    )
    if include_dropped or exclude_dropped:
        logger(
            "Фильтр ключевых слов для ручного выбора: "
            f"оставлено={len(selected_repositories)}, "
            f"убрано_по_include={include_dropped}, убрано_по_exclude={exclude_dropped}."
        )
    if resume_state_file is not None:
        selected_repositories, resume_skipped = filter_repositories_for_resume(
            selected_repositories,
            resume_state_file,
        )
        logger(
            "Resume mode: "
            f"пропущено уже завершенных по state={resume_skipped}, осталось={len(selected_repositories)}."
        )

    if selected_repositories and config.graphql_enrich:
        graphql_client = GitHubClient(
            token=config.token.strip(),
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            max_rate_limit_wait=config.max_rate_limit_wait,
            log=logger,
            should_cancel=is_cancelled,
        )
        selected_repositories = maybe_enrich_repositories_with_graphql(
            config=config,
            client=graphql_client,
            repositories=selected_repositories,
            log=logger,
            should_cancel=is_cancelled,
        )

    if selected_repositories and config.deep_relevance_enabled:
        deep_client = GitHubClient(
            token=config.token.strip(),
            timeout=config.request_timeout,
            max_retries=config.max_retries,
            max_rate_limit_wait=config.max_rate_limit_wait,
            log=logger,
            should_cancel=is_cancelled,
        )
        selected_repositories = apply_deep_relevance_scoring(
            config=config,
            client=deep_client,
            repositories=selected_repositories,
            query=config.query.strip(),
            log=logger,
            should_cancel=is_cancelled,
        )

    logger(
        "Режим ручного выбора: "
        f"подготовлено к скачиванию {len(selected_repositories)} репозиториев."
    )
    logger(
        "Параметры скачивания: "
        f"workers={config.workers}, batch_size={config.batch_size}, clone_timeout={config.clone_timeout}, "
        f"retry_failed_clones={config.retry_failed_clones}, retry_delay_seconds={config.retry_delay_seconds}, "
        f"skip_existing={config.skip_existing}, clone_depth={config.clone_depth}, "
        f"clone_partial={config.clone_partial}, clone_single_branch={config.clone_single_branch}, "
        f"clone_no_tags={config.clone_no_tags}, graphql_enrich={config.graphql_enrich}, "
        f"graphql_batch_size={config.graphql_batch_size}, "
        f"deep_relevance_enabled={config.deep_relevance_enabled}, "
        f"deep_relevance_max_repos={config.deep_relevance_max_repos}, "
        f"deep_relevance_min_score={config.deep_relevance_min_score}"
    )
    logger(f"Папка проекта: {output_root}")
    logger(f"Папка репозиториев: {repos_dir}")
    logger(f"Папка метаданных: {metadata_dir}")

    check_cancelled()
    if selected_repositories and not config.dry_run:
        ensure_git_available()

    effective_metadata_file = metadata_file
    should_write_selection_metadata = effective_metadata_file is None or any(
        repo.graphql_enriched or repo.deep_relevance_checked for repo in selected_repositories
    )
    if should_write_selection_metadata:
        normalized_query, _ = normalize_query_for_search(config.query)
        options = SearchOptions(
            query=normalized_query,
            min_stars=config.min_stars,
            language=config.language.strip(),
            include_forks=config.include_forks,
            include_archived=config.include_archived,
            created_after=config.created_after,
            created_before=config.created_before,
            sort=config.sort,
            order=config.order,
        )
        effective_metadata_file = save_metadata(
            metadata_dir=metadata_dir,
            query=normalized_query,
            options=options,
            repositories=selected_repositories,
        )
        logger(f"Метаданные выбора сохранены: {effective_metadata_file}")
    else:
        logger(f"Метаданные выбора: {effective_metadata_file}")
    if sqlite_file is not None:
        export_repositories_to_sqlite(
            sqlite_file,
            query=config.query.strip(),
            repositories=selected_repositories,
            metadata_file=effective_metadata_file,
        )
        logger(f"SQLite export обновлен: {sqlite_file}")
    if config.export_csv:
        csv_file = sqlite_file.with_suffix(".csv") if sqlite_file else output_root / f"export_manual_{run_stamp}.csv"
        from github_harvester.exporters import export_to_csv
        export_to_csv(csv_file, selected_repositories)
        logger(f"CSV export обновлен: {csv_file}")

    if config.dry_run:
        logger("Режим 'Только поиск' включен для metadata/selection, клонирование пропущено.")
        return RunSummary(
            found_count=len(selected_repositories),
            cloned_count=0,
            skipped_count=0,
            failed_count=0,
            cancelled_count=0,
            output_root=output_root,
            repos_dir=repos_dir,
            metadata_file=effective_metadata_file,
            failure_report_file=None,
            run_log_file=run_log_file,
            run_state_file=None,
            sqlite_file=sqlite_file,
        )

    total_count = len(selected_repositories)
    logger(f"Начинаем скачивание репозиториев: {total_count}")
    clone_options = CloneOptions(
        depth=config.clone_depth,
        partial_clone=config.clone_partial,
        single_branch=config.clone_single_branch,
        no_tags=config.clone_no_tags,
    )
    logger(
        "Стратегия клонирования: "
        f"depth={'full' if clone_options.depth == 0 else clone_options.depth}, "
        f"partial_blob_filter={clone_options.partial_clone}, "
        f"single_branch={clone_options.single_branch}, no_tags={clone_options.no_tags}."
    )
    if progress:
        progress(0, total_count)
    run_state_file = metadata_dir / f"run_state_{run_stamp}.json"
    initialize_run_state(
        run_state_file,
        query=config.query.strip(),
        metadata_file=effective_metadata_file,
        repositories=selected_repositories,
        mode="manual-selection-download",
    )
    logger(f"Run-state сохранен: {run_state_file}")

    status_labels = {
        "cloned": "скачан",
        "skipped": "пропущен",
        "failed": "ошибка",
        "cancelled": "остановлен",
    }

    def on_progress(done: int, total: int, result: CloneResult) -> None:
        try:
            record_clone_result(run_state_file, result)
        except Exception as exc:
            logger(f"Предупреждение: не удалось обновить run-state: {exc}")
        status_text = status_labels.get(result.status, result.status)
        logger(
            f"[{done}/{total}] {status_text}: {result.repo_full_name} | "
            f"path={result.target_path} | message={result.message}"
        )
        if progress:
            progress(done, total)

    def on_retry_progress(attempt: int, result: CloneResult) -> None:
        try:
            record_clone_result(run_state_file, result)
        except Exception as exc:
            logger(f"Предупреждение: не удалось обновить run-state после повтора: {exc}")
        status_text = status_labels.get(result.status, result.status)
        logger(
            f"[retry {attempt}] {status_text}: {result.repo_full_name} | "
            f"path={result.target_path} | message={result.message}"
        )

    repositories_map = {repo.full_name: repo for repo in selected_repositories}
    all_results: dict[str, CloneResult] = {}
    batches = split_into_batches(selected_repositories, config.batch_size)
    completed_primary = 0

    for batch_index, batch in enumerate(batches, start=1):
        check_cancelled()
        logger(f"Пакет {batch_index}/{len(batches)}: {len(batch)} репозиториев")
        batch_offset = completed_primary

        def on_batch_progress(done: int, _total: int, result: CloneResult) -> None:
            on_progress(batch_offset + done, total_count, result)

        batch_results = download_repositories(
            repositories=batch,
            output_root=repos_dir,
            workers=config.workers,
            clone_timeout=config.clone_timeout,
            skip_existing=config.skip_existing,
            progress_callback=on_batch_progress,
            log_callback=logger,
            cancel_event=cancel_event,
            clone_options=clone_options,
        )
        completed_primary += len(batch)
        batch_cloned = sum(1 for item in batch_results if item.status == "cloned")
        batch_skipped = sum(1 for item in batch_results if item.status == "skipped")
        batch_failed = sum(1 for item in batch_results if item.status == "failed")
        batch_cancelled = sum(1 for item in batch_results if item.status == "cancelled")
        logger(
            f"Итог пакета {batch_index}: cloned={batch_cloned}, skipped={batch_skipped}, "
            f"failed={batch_failed}, cancelled={batch_cancelled}"
        )
        for item in batch_results:
            all_results[item.repo_full_name] = item

        failed_names = [item.repo_full_name for item in batch_results if item.status == "failed"]
        if failed_names and config.retry_failed_clones > 0:
            logger(f"Неуспешных в пакете: {len(failed_names)}. Запускаем повторы.")

        for attempt in range(1, config.retry_failed_clones + 1):
            if not failed_names:
                break
            check_cancelled()
            logger(f"Повтор {attempt}/{config.retry_failed_clones} для {len(failed_names)} репозиториев")
            if config.retry_delay_seconds > 0:
                logger(f"Ожидание перед повтором: {config.retry_delay_seconds} сек")
                for _ in range(config.retry_delay_seconds):
                    check_cancelled()
                    time.sleep(1)

            retry_repositories = [
                repositories_map[full_name] for full_name in failed_names if full_name in repositories_map
            ]

            def on_retry_batch_progress(_done: int, _total: int, result: CloneResult) -> None:
                on_retry_progress(attempt, result)

            retry_results = download_repositories(
                repositories=retry_repositories,
                output_root=repos_dir,
                workers=config.workers,
                clone_timeout=config.clone_timeout,
                skip_existing=config.skip_existing,
                progress_callback=on_retry_batch_progress,
                log_callback=logger,
                cancel_event=cancel_event,
                clone_options=clone_options,
            )
            failed_names = []
            for item in retry_results:
                all_results[item.repo_full_name] = item
                if item.status == "failed":
                    failed_names.append(item.repo_full_name)
            logger(f"После повтора осталось ошибок: {len(failed_names)}")

    check_cancelled()
    results = list(all_results.values())
    success_count = sum(1 for item in results if item.status == "cloned")
    skipped_count = sum(1 for item in results if item.status == "skipped")
    cancelled_count = sum(1 for item in results if item.status == "cancelled")
    failed = [item for item in results if item.status == "failed"]

    logger(f"Скачано: {success_count}")
    logger(f"Пропущено: {skipped_count}")
    logger(f"Остановлено: {cancelled_count}")
    logger(f"Ошибок: {len(failed)}")
    if success_count == 0 and skipped_count > 0 and cancelled_count == 0 and not failed:
        logger("Новых репозиториев для скачивания нет: все выбранные уже существуют в целевой папке.")

    if config.export_ai_ready:
        logger("Начат экспорт репозиториев для ИИ (AI-Ready Repomix)...")
        ai_exports_count = 0
        for item in results:
            if item.status in ("cloned", "skipped") and item.target_path and item.target_path.exists():
                try:
                    export_repo_for_ai(item.repo_full_name, item.target_path, output_root)
                    ai_exports_count += 1
                except Exception as exc:
                    logger(f"Ошибка AI-экспорта для {item.repo_full_name}: {exc}")
        logger(f"Успешно экспортировано для ИИ: {ai_exports_count}")

    failed_file: Path | None = None
    if failed:
        failed_file = metadata_dir / f"failed_clones_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        atomic_write_text(
            failed_file,
            json.dumps(
                [
                    {
                        "full_name": item.repo_full_name,
                        "path": str(item.target_path),
                        "error": item.message,
                    }
                    for item in failed
                ],
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        logger(f"Отчет об ошибках: {failed_file}")

    return RunSummary(
        found_count=len(selected_repositories),
        cloned_count=success_count,
        skipped_count=skipped_count,
        failed_count=len(failed),
        cancelled_count=cancelled_count,
        output_root=output_root,
        repos_dir=repos_dir,
        metadata_file=effective_metadata_file,
        failure_report_file=failed_file,
        run_log_file=run_log_file,
        run_state_file=run_state_file,
        sqlite_file=sqlite_file,
    )


def load_repositories_from_metadata(metadata_file: Path) -> tuple[str, list[Repo]]:
    try:
        payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать metadata JSON: {metadata_file}") from exc
    if not isinstance(payload, dict):
        raise ValueError("metadata JSON должен быть объектом.")

    raw_schema_version = payload.get("schema_version", 1)
    try:
        schema_version = int(raw_schema_version)
    except (TypeError, ValueError):
        raise ValueError("metadata JSON содержит невалидный schema_version.")
    if schema_version < 1:
        raise ValueError("metadata JSON содержит невалидный schema_version.")
    if schema_version > METADATA_SCHEMA_VERSION:
        raise ValueError(
            "metadata JSON использует более новую схему "
            f"(schema_version={schema_version}, поддерживается до {METADATA_SCHEMA_VERSION})."
        )

    raw_repositories = payload.get("repositories")
    if raw_repositories is None and schema_version <= 1:
        raw_repositories = payload.get("items")
    if not isinstance(raw_repositories, list):
        raise ValueError("metadata JSON не содержит массива repositories/items.")

    repositories: list[Repo] = []
    skipped_items = 0
    for raw_item in raw_repositories:
        if not isinstance(raw_item, dict):
            skipped_items += 1
            continue
        try:
            repositories.append(Repo.from_api_item(raw_item))
        except Exception:
            skipped_items += 1
            continue
    if raw_repositories and not repositories:
        raise ValueError(
            "metadata JSON содержит записи repositories/items, но ни одну из них не удалось распознать "
            f"как репозиторий (пропущено={skipped_items})."
        )
    query = str(payload.get("query") or payload.get("search_query") or "").strip()
    return query, repositories


def extract_query_terms_for_ai_filter(query: str) -> list[str]:
    raw_terms = re.findall(r"\w[\w.+-]*", query.lower(), flags=re.UNICODE)
    terms: list[str] = []
    seen: set[str] = set()
    short_allowed = {"ai", "ml", "llm", "cv", "nlp", "osint"}
    stop_words = {
        "or",
        "and",
        "not",
        "fork",
        "archived",
        "stars",
        "language",
        "created",
        "и",
        "или",
        "не",
        "для",
        "что",
        "как",
        "это",
        "все",
        "всё",
    }
    for term in raw_terms:
        if term in stop_words:
            continue
        if ":" in term:
            continue
        if len(term) < 3 and term not in short_allowed:
            continue
        if term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def repo_text_relevance_score(repo: Repo, query_terms: Sequence[str]) -> float:
    if not query_terms:
        return 0.0
    full_name = repo.full_name.lower()
    description = repo.description.lower()
    topics = " ".join(repo.topics).lower()
    language = repo.language.lower()

    points = 0.0
    max_points = float(len(query_terms) * 2.75)
    for term in query_terms:
        if term in full_name:
            points += 1.25
        if term in topics:
            points += 1.0
        if term in description:
            points += 0.5
        if language and term == language:
            points += 0.25
    return max(0.0, min(1.0, points / max_points))


def score_readme_relevance(readme_text: str, query_terms: Sequence[str]) -> float:
    terms = _normalize_relevance_terms(query_terms)
    text = str(readme_text or "")[:200_000].lower()
    if not terms or not text:
        return 0.0

    total_hits = 0
    matched_terms = 0
    for term in terms:
        hits = _count_text_term_occurrences(text, term)
        if hits > 0:
            matched_terms += 1
            total_hits += hits

    if matched_terms <= 0:
        return 0.0
    token_count = max(1, len(re.findall(r"\w+", text, flags=re.UNICODE)))
    coverage = matched_terms / len(terms)
    density = min(1.0, total_hits / max(1.0, token_count / 160.0))
    return _bounded_score((0.82 * coverage) + (0.18 * density))


def score_code_path_relevance(
    code_paths: Sequence[str],
    query_terms: Sequence[str],
    tree_truncated: bool = False,
) -> float:
    terms = _normalize_relevance_terms(query_terms)
    paths = [str(path or "").replace("\\", "/").strip().lower() for path in code_paths if str(path or "").strip()]
    if not terms or not paths:
        return 0.0

    token_sets = [_path_tokens(path) for path in paths]
    all_tokens: set[str] = set()
    for tokens in token_sets:
        all_tokens.update(tokens)

    matched_terms = 0
    for term in terms:
        if term in all_tokens or (len(term) >= 3 and any(term in path for path in paths)):
            matched_terms += 1
    coverage = matched_terms / len(terms)

    hit_paths = 0
    for path, tokens in zip(paths, token_sets):
        if any(term in tokens or (len(term) >= 3 and term in path) for term in terms):
            hit_paths += 1
    path_hit_ratio = hit_paths / len(paths)

    code_exts = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java", ".kt", ".swift",
        ".cs", ".cpp", ".c", ".h", ".hpp", ".rb", ".php", ".scala", ".lua", ".r",
        ".sql", ".sh", ".ps1", ".mdx",
    }
    code_files = sum(1 for path in paths if Path(path).suffix.lower() in code_exts)
    code_ratio = code_files / len(paths)
    has_source_dir = any(path.startswith(("src/", "app/", "lib/", "packages/", "cmd/")) for path in paths)
    structure_signal = min(1.0, (0.7 * code_ratio) + (0.3 if has_source_dir else 0.0))

    score = (0.75 * coverage) + (0.15 * path_hit_ratio) + (0.10 * structure_signal)
    if tree_truncated:
        score *= 0.97
    return _bounded_score(score)


def score_deep_relevance_snapshot(
    readme_text: str,
    code_paths: Sequence[str],
    query_terms: Sequence[str],
    tree_truncated: bool = False,
) -> float:
    readme_score = score_readme_relevance(readme_text, query_terms)
    code_score = score_code_path_relevance(code_paths, query_terms, tree_truncated=tree_truncated)
    return _bounded_score((0.70 * readme_score) + (0.30 * code_score))


def apply_deep_relevance_scoring(
    config: RunConfig,
    client: object,
    repositories: Sequence[Repo],
    query: str,
    log: Callable[[str], None],
    should_cancel: Callable[[], bool],
) -> list[Repo]:
    if not config.deep_relevance_enabled or not repositories:
        return list(repositories)

    query_terms = extract_query_terms_for_ai_filter(query)
    if not query_terms:
        log("Deep relevance: пропущено, из запроса не удалось извлечь поисковые термы.")
        return list(repositories)

    candidates = list(repositories[: config.deep_relevance_max_repos])
    tail = list(repositories[config.deep_relevance_max_repos :])
    log(
        "Deep relevance: "
        f"проверяем README/tree для {len(candidates)}/{len(repositories)} репозиториев "
        f"(threshold={config.deep_relevance_min_score:.2f})."
    )

    scored: list[Repo] = []
    for index, repo in enumerate(candidates, start=1):
        if should_cancel():
            raise RunCancelledError("Deep relevance отменен пользователем.")

        readme_text = ""
        code_paths: list[str] = []
        tree_truncated = False
        errors: list[str] = []

        try:
            readme_text = client.get_repository_readme_text(repo)  # type: ignore[attr-defined]
        except GitHubCancelledError as exc:
            raise RunCancelledError(str(exc)) from exc
        except Exception as exc:
            errors.append(f"README: {exc}")

        try:
            code_paths, tree_truncated = client.get_repository_tree_paths(repo)  # type: ignore[attr-defined]
        except GitHubCancelledError as exc:
            raise RunCancelledError(str(exc)) from exc
        except Exception as exc:
            errors.append(f"tree: {exc}")

        readme_score = score_readme_relevance(readme_text, query_terms)
        code_score = score_code_path_relevance(code_paths, query_terms, tree_truncated=tree_truncated)
        deep_score = _bounded_score((0.70 * readme_score) + (0.30 * code_score))
        if tree_truncated:
            errors.append("tree: truncated")

        scored.append(
            replace(
                repo,
                readme_relevance_score=round(readme_score, 4),
                code_relevance_score=round(code_score, 4),
                deep_relevance_score=round(deep_score, 4),
                deep_relevance_checked=True,
                deep_relevance_error="; ".join(errors),
            )
        )
        if index % 5 == 0 or index == len(candidates):
            log(f"Deep relevance: проверено {index}/{len(candidates)}.")

    threshold = config.deep_relevance_min_score
    dropped = 0
    if threshold > 0.0:
        before = len(scored)
        scored = [
            repo
            for repo in scored
            if repo.deep_relevance_score >= threshold or bool(repo.deep_relevance_error)
        ]
        dropped = before - len(scored)

    scored.sort(
        key=lambda repo: (
            repo.deep_relevance_score,
            repo.readme_relevance_score,
            repo.code_relevance_score,
            repo.stargazers_count,
            repo.updated_at,
            repo.full_name.lower(),
        ),
        reverse=True,
    )
    if dropped:
        log(f"Deep relevance: отфильтровано ниже threshold={threshold:.2f}: {dropped}.")
    if tail:
        log(f"Deep relevance: без глубокой проверки оставлено хвостом {len(tail)} репозиториев.")
    return scored + tail


def _normalize_relevance_terms(query_terms: Sequence[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in query_terms:
        normalized = str(term or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
    return terms


def _count_text_term_occurrences(text: str, term: str) -> int:
    if len(term) <= 2:
        pattern = rf"(?<![\w.+-]){re.escape(term)}(?![\w.+-])"
        return len(re.findall(pattern, text, flags=re.UNICODE))
    return text.count(term)


def _path_tokens(path: str) -> set[str]:
    tokens = {
        token
        for token in re.split(r"[^0-9A-Za-zА-Яа-я]+", path.lower())
        if token
    }
    return tokens


def _bounded_score(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def parse_repo_datetime(raw_value: str) -> datetime | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc)
    return parsed.replace(tzinfo=timezone.utc)


def repo_recency_score(repo: Repo, now: datetime | None = None) -> float:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    for candidate in (repo.pushed_at, repo.updated_at, repo.created_at):
        parsed = parse_repo_datetime(candidate)
        if parsed is None:
            continue
        delta_days = max(0, (current - parsed).days)
        if delta_days <= 14:
            return 1.0
        if delta_days >= 3650:
            return 0.0
        return max(0.0, 1.0 - (delta_days / 3650.0))
    return 0.25


def repo_popularity_score(repo: Repo) -> float:
    stars = max(0, int(repo.stargazers_count))
    # ~10k stars maps close to 1.0 while preserving gradient for smaller projects.
    return max(0.0, min(1.0, math.log10(stars + 1) / 4.0))


def repo_composite_relevance_score(repo: Repo, query_terms: Sequence[str], now: datetime | None = None) -> float:
    text = repo_text_relevance_score(repo, query_terms)
    recency = repo_recency_score(repo, now=now)
    popularity = repo_popularity_score(repo)
    score = (0.65 * text) + (0.2 * recency) + (0.15 * popularity)
    return max(0.0, min(1.0, score))


def parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on", "да"}:
            return True
        if lowered in {"false", "0", "no", "off", "нет"}:
            return False
    return None


def normalize_ai_filter_decision(payload: dict, min_score: float) -> tuple[bool, float, str]:
    score_raw = payload.get("score")
    try:
        score = float(score_raw)
    except (TypeError, ValueError):
        score = 0.0
    score = max(0.0, min(1.0, score))
    relevant_raw = parse_bool(payload.get("relevant"))
    reason = str(payload.get("reason") or "").strip()

    if relevant_raw is None:
        keep = score >= min_score
    else:
        keep = relevant_raw and score >= min_score
    return keep, score, reason


def build_ai_filter_prompt(query: str, repo: Repo, heuristic_score: float, custom_ai_prompt: str = "") -> str:
    topics = ", ".join(repo.topics[:12])
    base_prompt = (
        "Оцени поверхностную релевантность GitHub-репозитория запросу.\n"
        "Верни СТРОГО JSON в одну строку без пояснений:\n"
        "{\n"
        '  "relevant": true,\n'
        '  "score": 0.0,\n'
        '  "reason": "краткая причина"\n'
        "}\n"
        f"Запрос: {query}\n"
        f"full_name: {repo.full_name}\n"
        f"description: {repo.description}\n"
        f"topics: {topics}\n"
        f"language: {repo.language}\n"
        f"heuristic_score: {heuristic_score:.2f}\n"
    )
    if custom_ai_prompt:
        base_prompt += f"\nДОПОЛНИТЕЛЬНЫЕ ИНСТРУКЦИИ ПОЛЬЗОВАТЕЛЯ:\n{custom_ai_prompt.strip()}\nОбязательно учитывай их при оценке релевантности (relevant/score).\n"
    return base_prompt


def pick_evenly_by_index(items: Sequence[tuple[float, Repo]], count: int) -> list[tuple[float, Repo]]:
    if count <= 0 or not items:
        return []
    if count >= len(items):
        return list(items)
    if count == 1:
        return [items[len(items) // 2]]

    last_index = len(items) - 1
    indices = [round(index * last_index / (count - 1)) for index in range(count)]
    result: list[tuple[float, Repo]] = []
    seen: set[int] = set()
    for raw_index in indices:
        bounded = max(0, min(last_index, int(raw_index)))
        if bounded in seen:
            continue
        seen.add(bounded)
        result.append(items[bounded])
    if len(result) >= count:
        return result[:count]

    for index in range(len(items)):
        if len(result) >= count:
            break
        if index in seen:
            continue
        seen.add(index)
        result.append(items[index])
    return result


def build_review_pool(
    scored: Sequence[tuple[float, Repo]],
    review_count: int,
    exploration_ratio: float = 0.25,
) -> list[tuple[float, Repo]]:
    if review_count <= 0 or not scored:
        return []
    cap = min(len(scored), review_count)
    if cap == len(scored):
        return list(scored)

    exploration_count = int(cap * exploration_ratio)
    if cap >= 40:
        exploration_count = max(6, exploration_count)
    exploration_count = min(exploration_count, max(0, cap // 2))
    head_count = max(1, cap - exploration_count)

    head = list(scored[:head_count])
    if exploration_count <= 0:
        return head

    tail_window_end = min(len(scored), head_count + cap * 4)
    tail_source = scored[head_count:tail_window_end]
    exploration = pick_evenly_by_index(tail_source, exploration_count)

    merged = head + exploration
    unique: list[tuple[float, Repo]] = []
    seen_repo_ids: set[int] = set()
    for score, repo in merged:
        if repo.id in seen_repo_ids:
            continue
        seen_repo_ids.add(repo.id)
        unique.append((score, repo))
    return unique


def filter_repositories_with_ai(
    repositories: Sequence[Repo],
    query: str,
    provider: AiProviderConfig,
    min_score: float,
    max_reviews: int,
    desired_keep_count: int = 0,
    should_cancel: Callable[[], bool] = lambda: False,
    custom_ai_prompt: str = "",
    log: Callable[[str], None] = lambda _: None,
) -> list[Repo]:
    if not repositories:
        return []

    query_terms = extract_query_terms_for_ai_filter(query)
    now = datetime.now(timezone.utc)
    if not query_terms:
        fallback_target = desired_keep_count if desired_keep_count else max(40, max_reviews * 2)
        fallback_count = min(len(repositories), fallback_target)
        ordered = sorted(
            repositories,
            key=lambda item: (
                repo_composite_relevance_score(item, query_terms, now=now),
                item.stargazers_count,
            ),
            reverse=True,
        )
        log(
            "AI-filter: query terms empty, use heuristic fallback "
            f"top {fallback_count} by popularity+recency."
        )
        return ordered[:fallback_count]

    scored = [
        (repo_composite_relevance_score(repo, query_terms, now=now), repo)
        for repo in repositories
    ]
    scored.sort(
        key=lambda item: (
            item[0],
            item[1].stargazers_count,
            item[1].updated_at,
            item[1].full_name.lower(),
        ),
        reverse=True,
    )
    review_cap = min(len(scored), max(60, max_reviews * 8))
    review_pool = build_review_pool(scored, review_cap, exploration_ratio=0.25)
    review_count = len(review_pool)

    keep_threshold = min(0.82, min_score + 0.1)
    drop_threshold = max(0.02, min_score - 0.4)
    ai_budget = min(max_reviews, max(12, min(120, review_count)))

    auto_keep: list[tuple[Repo, float]] = []
    ai_candidates: list[tuple[float, Repo]] = []
    auto_drop_count = 0

    for heuristic_score, repo in review_pool:
        if heuristic_score >= keep_threshold:
            auto_keep.append((repo, heuristic_score))
        elif heuristic_score < drop_threshold:
            auto_drop_count += 1
        else:
            ai_candidates.append((heuristic_score, repo))

    ai_candidates = ai_candidates[:ai_budget]
    log(
        "AI-фильтр: быстрый режим "
        f"{review_count}/{len(scored)} (auto_keep={len(auto_keep)}, "
        f"auto_drop={auto_drop_count}, ai_checks={len(ai_candidates)}, "
        f"model={provider.model}, threshold={min_score:.2f}, timeout={provider.timeout}s)"
    )

    kept: list[tuple[Repo, float]] = list(auto_keep)
    ai_started = time.monotonic()
    ai_time_budget = max(12, min(120, provider.timeout * 5))
    requested_keep = desired_keep_count if desired_keep_count else max(40, max_reviews * 2)
    target_keep = min(review_count, max(10, requested_keep))
    if review_count <= 10:
        target_keep = min(review_count, max(1, min(5, review_count // 2)))
    ai_error_count = 0
    max_ai_errors = max(3, len(ai_candidates) // 2)
    for index, (heuristic_score, repo) in enumerate(ai_candidates, start=1):
        if should_cancel():
            raise RunCancelledError("Операция остановлена пользователем.")

        if (time.monotonic() - ai_started) >= ai_time_budget:
            log("AI-filter: time budget reached, stop deep checks.")
            break
        prompt = build_ai_filter_prompt(query, repo, heuristic_score, custom_ai_prompt=custom_ai_prompt)
        keep = False
        final_score = heuristic_score
        try:
            raw = request_ai(provider, prompt)
            from github_harvester.ai_planner import parse_json_object
            payload = parse_json_object(raw)
            keep = payload.get("relevant", False)
            ai_score = float(payload.get("score", heuristic_score))
            final_score = max(heuristic_score, ai_score)
        except Exception as exc:
            ai_error_count += 1
            keep = heuristic_score >= max(0.35, min_score * 0.7)
            log(
                f"AI-фильтр: ошибка проверки {repo.full_name}: {exc}. "
                f"Fallback по эвристике={'keep' if keep else 'drop'}."
            )
            if ai_error_count >= max_ai_errors:
                log("AI-filter: too many AI errors, switching to heuristic completion mode.")
                if keep:
                    kept.append((repo, final_score))
                break

        if keep:
            kept.append((repo, final_score))
            if len(kept) >= target_keep:
                log("AI-filter: enough candidates selected, stop checks early.")
                break

        if index % 4 == 0 or index == len(ai_candidates):
            log(f"AI-фильтр: проверено AI {index}/{len(ai_candidates)}, оставлено {len(kept)}")

    if not kept:
        ranked_review_pool = sorted(
            review_pool,
            key=lambda item: (item[0], item[1].stargazers_count, item[1].updated_at),
            reverse=True,
        )
        fallback_size = min(len(ranked_review_pool), max(5, min(target_keep, max_reviews * 4)))
        fallback = [repo for _score, repo in ranked_review_pool[:fallback_size]]
        if fallback:
            log(
                "AI-фильтр: модель недоступна/слишком строгая, используем безопасный fallback "
                f"по эвристике ({len(fallback)} репозиториев)."
            )
            return fallback
        log("AI-фильтр: после проверки не осталось подходящих репозиториев.")
        return []

    min_kept = target_keep
    if len(kept) < min_kept:
        existing_ids = {repo.id for repo, _score in kept}
        supplemental: list[tuple[Repo, float]] = []
        ranked_review_pool = sorted(review_pool, key=lambda item: (item[0], item[1].stargazers_count), reverse=True)
        for heuristic_score, repo in ranked_review_pool:
            if repo.id in existing_ids:
                continue
            supplemental.append((repo, heuristic_score))
            existing_ids.add(repo.id)
            if len(kept) + len(supplemental) >= min_kept:
                break
        if supplemental:
            kept.extend(supplemental)
            log(
                "AI-filter: heuristic fallback added "
                f"{len(supplemental)} repos for broader fast coverage."
            )

    best_by_id: dict[int, tuple[Repo, float]] = {}
    for repo, score in kept:
        existing = best_by_id.get(repo.id)
        if existing is None or score > existing[1]:
            best_by_id[repo.id] = (repo, score)
    ordered = sorted(best_by_id.values(), key=lambda item: (item[1], item[0].stargazers_count), reverse=True)
    result = [repo for repo, _score in ordered]
    log(f"AI-фильтр завершен: оставлено {len(result)} из {len(repositories)}")
    return result


def save_metadata(
    metadata_dir: Path,
    query: str,
    options: SearchOptions,
    repositories: Sequence[Repo],
) -> Path:
    metadata_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_file = metadata_dir / f"search_{timestamp}.json"
    payload = {
        "schema_version": METADATA_SCHEMA_VERSION,
        "producer": "github-harvester",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query": query,
        "options": {
            "min_stars": options.min_stars,
            "language": options.language,
            "include_forks": options.include_forks,
            "include_archived": options.include_archived,
            "created_after": options.created_after.isoformat(),
            "created_before": options.created_before.isoformat(),
            "sort": options.sort,
            "order": options.order,
        },
        "count": len(repositories),
        "repositories": [asdict(repo) for repo in repositories],
    }
    atomic_write_text(target_file, json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return target_file

