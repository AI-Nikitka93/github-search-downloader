from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Sequence

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from github_harvester.service import (
    RunConfig,
    RunCancelledError,
    load_repositories_from_metadata,
    parse_iso_date,
    parse_keyword_list,
    run_collection,
    run_download_for_repositories,
)
from github_harvester.github_api import GitHubApiError
from github_harvester.version import __version__
from github_harvester.secret_store import (
    DEFAULT_SECRET_NAME,
    SecretStoreError,
    delete_secret,
    has_secret,
    load_secret,
    secret_name_for_ai_provider,
    store_secret,
)


def parse_bool_value(value: object, default: bool | None = None) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on", "да"}:
            return True
        if lowered in {"false", "0", "no", "off", "нет"}:
            return False
    return default


def parse_int_value(value: object, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def parse_float_value(value: object, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return default


def load_config_file_defaults(config_file: Path) -> dict[str, Any]:
    path = config_file.expanduser()
    if not path.exists():
        raise ValueError(f"Файл конфигурации не найден: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать JSON-конфигурацию: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("JSON-конфигурация должна быть объектом.")

    defaults: dict[str, Any] = {}

    def pick(*keys: str) -> object | None:
        for key in keys:
            if key in payload:
                return payload.get(key)
        return None

    query = str(pick("query") or "").strip()
    if query:
        defaults["query"] = query

    output = str(pick("output") or "").strip()
    if output:
        defaults["output"] = output

    language = str(pick("language") or "").strip()
    if language:
        defaults["language"] = language

    created_after = str(pick("created_after") or "").strip()
    if created_after:
        defaults["created_after"] = created_after

    created_before = str(pick("created_before") or "").strip()
    if created_before:
        defaults["created_before"] = created_before

    sort = str(pick("sort") or "").strip().lower()
    if sort in {"stars", "updated"}:
        defaults["sort"] = sort

    order = str(pick("order") or "").strip().lower()
    if order in {"desc", "asc"}:
        defaults["order"] = order

    ai_filter_endpoint = str(pick("ai_filter_endpoint", "ai_endpoint") or "").strip()
    if ai_filter_endpoint:
        defaults["ai_filter_endpoint"] = ai_filter_endpoint

    ai_filter_model = str(pick("ai_filter_model", "ai_model") or "").strip()
    if ai_filter_model:
        defaults["ai_filter_model"] = ai_filter_model

    ai_provider = str(pick("ai_provider", "ai_provider_type") or "").strip()
    if ai_provider:
        defaults["ai_provider"] = ai_provider

    ai_api_key_env = str(pick("ai_api_key_env") or "").strip()
    if ai_api_key_env:
        defaults["ai_api_key_env"] = ai_api_key_env

    metadata_file = str(pick("metadata_file") or "").strip()
    if metadata_file:
        defaults["metadata_file"] = metadata_file

    resume_state_file = str(pick("resume_state_file") or "").strip()
    if resume_state_file:
        defaults["resume_state_file"] = resume_state_file

    export_sqlite = str(pick("export_sqlite") or "").strip()
    if export_sqlite:
        defaults["export_sqlite"] = export_sqlite

    ai_custom_prompt = str(pick("ai_custom_prompt") or "").strip()
    if ai_custom_prompt:
        defaults["ai_custom_prompt"] = ai_custom_prompt

    include_keywords = str(pick("include_keywords") or "").strip()
    if include_keywords:
        defaults["include_keywords"] = include_keywords

    exclude_keywords = str(pick("exclude_keywords") or "").strip()
    if exclude_keywords:
        defaults["exclude_keywords"] = exclude_keywords

    defaults["min_stars"] = parse_int_value(pick("min_stars"), 0)
    defaults["max_age_years"] = parse_int_value(pick("max_age_years"), 5)
    defaults["max_repos"] = parse_int_value(pick("max_repos"), 0)
    defaults["workers"] = parse_int_value(pick("workers"), 4)
    defaults["batch_size"] = parse_int_value(pick("batch_size"), 100)
    defaults["request_timeout"] = parse_int_value(pick("request_timeout"), 30)
    defaults["clone_timeout"] = parse_int_value(pick("clone_timeout"), 300)
    defaults["clone_depth"] = parse_int_value(pick("clone_depth"), 1)
    defaults["retry_failed_clones"] = parse_int_value(pick("retry_failed_clones"), 2)
    defaults["retry_delay"] = parse_int_value(pick("retry_delay_seconds"), 5)
    defaults["max_retries"] = parse_int_value(pick("max_retries"), 5)
    defaults["max_rate_limit_wait"] = parse_int_value(pick("max_rate_limit_wait"), 900)
    defaults["ai_filter_timeout"] = parse_int_value(pick("ai_filter_timeout", "ai_timeout"), 20)
    defaults["ai_temperature"] = parse_float_value(pick("ai_temperature", "ai_temp"), 0.0)
    defaults["ai_num_ctx"] = parse_int_value(pick("ai_num_ctx"), 4096)
    defaults["ai_num_predict"] = parse_int_value(pick("ai_num_predict"), 768)
    defaults["ai_filter_min_score"] = parse_float_value(pick("ai_filter_min_score"), 0.55)
    defaults["ai_filter_max_reviews"] = parse_int_value(pick("ai_filter_max_reviews"), 10)
    defaults["graphql_batch_size"] = parse_int_value(pick("graphql_batch_size"), 25)
    defaults["deep_relevance_max_repos"] = parse_int_value(pick("deep_relevance_max_repos"), 25)
    defaults["deep_relevance_min_score"] = parse_float_value(pick("deep_relevance_min_score"), 0.0)

    for source_key, target_key in (
        ("include_forks", "include_forks"),
        ("include_archived", "include_archived"),
        ("skip_existing", "skip_existing"),
        ("no_sharding", "no_sharding"),
        ("dry_run", "dry_run"),
        ("ai_filter_enabled", "ai_filter"),
        ("incremental", "incremental"),
        ("clone_partial", "clone_partial"),
        ("clone_single_branch", "clone_single_branch"),
        ("clone_no_tags", "clone_no_tags"),
        ("graphql_enrich", "graphql_enrich"),
        ("deep_relevance_enabled", "deep_relevance"),
        ("deep_relevance", "deep_relevance"),
        ("export_csv", "export_csv"),
        ("export_ai_ready", "export_ai_ready"),
    ):
        parsed = parse_bool_value(pick(source_key))
        if parsed is not None:
            defaults[target_key] = parsed

    return defaults


def resolve_github_token(
    explicit_token: str = "",
    env_token: str = "",
    saved_token_loader=load_secret,
) -> tuple[str, str]:
    explicit = explicit_token.strip()
    if explicit:
        return explicit, "cli"
    env_value = env_token.strip()
    if env_value:
        return env_value, "env"
    try:
        saved = str(saved_token_loader() or "").strip()
    except SecretStoreError:
        saved = ""
    if saved:
        return saved, "saved"
    return "", "none"


def resolve_ai_api_key(
    provider_type: str,
    endpoint: str,
    explicit_key: str = "",
    key_env_name: str = "",
    environ: dict[str, str] | None = None,
    saved_key_loader=load_secret,
) -> tuple[str, str]:
    provider_value = str(provider_type or "").strip().lower().replace("_", "-")
    if provider_value in {"", "ollama", "ollama-local"}:
        return "", "not-required"
    explicit = explicit_key.strip()
    if explicit:
        return explicit, "explicit"
    env = environ if environ is not None else os.environ
    env_name = str(key_env_name or "").strip()
    if env_name:
        env_value = str(env.get(env_name, "") or "").strip()
        if env_value:
            return env_value, f"env:{env_name}"
    try:
        saved = str(saved_key_loader(secret_name_for_ai_provider(provider_type, endpoint)) or "").strip()
    except SecretStoreError:
        saved = ""
    if saved:
        return saved, "saved"
    return "", "none"


def build_parser(defaults: dict[str, Any] | None = None, secret_mode: bool = False) -> argparse.ArgumentParser:
    defaults = defaults or {}
    metadata_mode = bool(str(defaults.get("metadata_file") or "").strip())
    query_required = not secret_mode and not metadata_mode and not bool(str(defaults.get("query") or "").strip())

    parser = argparse.ArgumentParser(
        description="Search GitHub repositories by topic/query and download them locally."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit.",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check for application updates on GitHub Releases and exit.",
    )
    parser.add_argument(
        "--config-file",
        default="",
        help="Path to JSON config file (for example gui_settings.json). CLI flags override file values.",
    )
    parser.add_argument("--query", required=query_required, default="", help="GitHub search query text.")
    parser.add_argument(
        "--metadata-file",
        default="",
        help="Download repositories from an existing metadata/search_*.json file instead of searching.",
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="Root output folder. Repositories go to <output>/repos.",
    )
    parser.add_argument(
        "--token",
        default="",
        help="GitHub token for this run only. Prefer saved local token or GITHUB_TOKEN for regular use.",
    )
    parser.add_argument(
        "--save-github-token",
        action="store_true",
        help="Prompt for a GitHub token and save it in local Windows protected storage, then exit.",
    )
    parser.add_argument(
        "--delete-saved-github-token",
        action="store_true",
        help="Delete the locally saved GitHub token, then exit.",
    )
    parser.add_argument(
        "--show-token-status",
        action="store_true",
        help="Show whether a local protected GitHub token is saved, then exit.",
    )
    parser.add_argument(
        "--min-stars",
        type=int,
        default=0,
        help="Minimum stars for repositories.",
    )
    parser.add_argument(
        "--language",
        default="",
        help="Optional language filter, for example Python.",
    )
    parser.add_argument(
        "--include-forks",
        action="store_true",
        help="Include forked repositories.",
    )
    parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived repositories.",
    )
    parser.add_argument(
        "--created-after",
        default="2008-01-01",
        help="Start date (YYYY-MM-DD) for repo creation date.",
    )
    parser.add_argument(
        "--created-before",
        default=date.today().isoformat(),
        help="End date (YYYY-MM-DD) for repo creation date.",
    )
    parser.add_argument(
        "--max-age-years",
        type=int,
        default=5,
        help="Ignore repositories older than N years (0 disables this filter).",
    )
    parser.add_argument(
        "--sort",
        choices=["stars", "updated"],
        default="stars",
        help="Sort key for GitHub search API.",
    )
    parser.add_argument(
        "--order",
        choices=["desc", "asc"],
        default="desc",
        help="Sort order for GitHub search API.",
    )
    parser.add_argument(
        "--max-repos",
        type=int,
        default=0,
        help="Stop after this many unique repositories (0 means no explicit limit).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel git clone workers.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Download repositories in batches of this size.",
    )
    parser.add_argument(
        "--request-timeout",
        type=int,
        default=30,
        help="Timeout in seconds for each GitHub API request.",
    )
    parser.add_argument(
        "--clone-timeout",
        type=int,
        default=300,
        help="Timeout in seconds for each git clone.",
    )
    parser.add_argument(
        "--clone-depth",
        type=int,
        default=1,
        help="git clone depth. Use 0 for full history.",
    )
    parser.add_argument(
        "--no-partial-clone",
        action="store_false",
        dest="clone_partial",
        help="Disable git partial clone blob filter.",
    )
    parser.add_argument(
        "--all-branches",
        action="store_false",
        dest="clone_single_branch",
        help="Clone all branches instead of only the default branch.",
    )
    parser.add_argument(
        "--fetch-tags",
        action="store_false",
        dest="clone_no_tags",
        help="Fetch tags during clone.",
    )
    parser.add_argument(
        "--retry-failed-clones",
        type=int,
        default=2,
        help="Retry failed clones this many times.",
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=5,
        help="Delay in seconds before each retry attempt.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Max retries for GitHub API errors.",
    )
    parser.add_argument(
        "--max-rate-limit-wait",
        type=int,
        default=900,
        help="Max seconds to wait when GitHub rate limit is hit.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        default=True,
        help="Skip repositories already downloaded.",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_false",
        dest="skip_existing",
        help="Do not skip existing folders.",
    )
    parser.add_argument(
        "--no-sharding",
        action="store_true",
        help="Disable date-range sharding (subject to 1000 result API cap).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search only, do not clone repositories.",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Skip repository IDs already present in previous metadata files under the output folder.",
    )
    parser.add_argument(
        "--resume-state-file",
        default="",
        help="Resume from a metadata/run_state_*.json file, skipping cloned/skipped repositories.",
    )
    parser.add_argument(
        "--include-keywords",
        default="",
        help="Comma/semicolon separated metadata keywords; keep repos matching at least one.",
    )
    parser.add_argument(
        "--exclude-keywords",
        default="",
        help="Comma/semicolon separated metadata keywords; drop repos matching any.",
    )
    parser.add_argument(
        "--export-sqlite",
        default="",
        help="Optional SQLite database path for repository metadata export.",
    )
    parser.add_argument(
        "--export-csv",
        action="store_true",
        help="Optional CSV file metadata export.",
    )
    parser.add_argument(
        "--export-ai-ready",
        action="store_true",
        help="Clean downloaded repositories from binaries and package as AI-ready Repomix XML.",
    )
    parser.add_argument(
        "--graphql-enrich",
        action="store_true",
        help="Use GitHub GraphQL to enrich final repository metadata. Requires a GitHub token.",
    )
    parser.add_argument(
        "--graphql-batch-size",
        type=int,
        default=25,
        help="Repositories per GraphQL enrichment request (1..50).",
    )
    parser.add_argument(
        "--deep-relevance",
        action="store_true",
        help="Fetch README and Git tree paths for the final shortlist and sort by deep relevance.",
    )
    parser.add_argument(
        "--no-deep-relevance",
        action="store_false",
        dest="deep_relevance",
        help="Disable deep relevance scoring (overrides config file).",
    )
    parser.add_argument(
        "--deep-relevance-max-repos",
        type=int,
        default=25,
        help="Max final repositories to inspect with README/tree deep relevance scoring.",
    )
    parser.add_argument(
        "--deep-relevance-min-score",
        type=float,
        default=0.0,
        help="Optional deep relevance threshold (0..1) for checked repositories.",
    )
    parser.add_argument(
        "--ai-filter",
        action="store_true",
        help="Enable superficial AI relevance filter before download.",
    )
    parser.add_argument(
        "--no-ai-filter",
        action="store_false",
        dest="ai_filter",
        help="Disable AI filter (overrides config file).",
    )
    parser.add_argument(
        "--ai-provider",
        choices=["ollama", "openai-compatible"],
        default="ollama",
        help="AI provider for planner/filter calls.",
    )
    parser.add_argument(
        "--ai-filter-endpoint",
        default=os.getenv("OLLAMA_ENDPOINT", "http://127.0.0.1:11434"),
        help="Ollama endpoint or OpenAI-compatible Base URL for AI filtering.",
    )
    parser.add_argument(
        "--ai-filter-model",
        default="",
        help="AI model name for planner/filter calls.",
    )
    parser.add_argument(
        "--ai-api-key",
        default="",
        help="AI provider API key for this run only. Prefer saved local key or --ai-api-key-env.",
    )
    parser.add_argument(
        "--ai-api-key-env",
        default="",
        help="Environment variable name that contains the AI provider API key.",
    )
    parser.add_argument(
        "--save-ai-api-key",
        action="store_true",
        help="Prompt for an AI provider API key and save it in local Windows protected storage, then exit.",
    )
    parser.add_argument(
        "--delete-saved-ai-api-key",
        action="store_true",
        help="Delete the locally saved AI provider API key for --ai-provider/--ai-filter-endpoint, then exit.",
    )
    parser.add_argument(
        "--show-ai-api-key-status",
        action="store_true",
        help="Show whether a local protected AI provider API key is saved, then exit.",
    )
    parser.add_argument(
        "--ai-filter-timeout",
        type=int,
        default=20,
        help="Timeout in seconds for one AI filter call.",
    )
    parser.add_argument(
        "--ai-temperature",
        type=float,
        default=0.0,
        help="Ollama generation temperature for planner/filter calls.",
    )
    parser.add_argument(
        "--ai-num-ctx",
        type=int,
        default=4096,
        help="Ollama num_ctx option for planner/filter calls.",
    )
    parser.add_argument(
        "--ai-num-predict",
        type=int,
        default=768,
        help="Ollama num_predict option for planner/filter calls.",
    )
    parser.add_argument(
        "--ai-filter-min-score",
        type=float,
        default=0.55,
        help="Min relevance score (0..1) for AI filter keep decision.",
    )
    parser.add_argument(
        "--ai-filter-max-reviews",
        type=int,
        default=10,
        help="Max repositories to review with AI filter.",
    )
    parser.add_argument(
        "--ai-custom-prompt",
        default="",
        help="Custom prompt for AI evaluation.",
    )
    parser.set_defaults(
        skip_existing=True,
        ai_filter=False,
        deep_relevance=False,
        clone_partial=True,
        clone_single_branch=True,
        clone_no_tags=True,
        export_csv=False,
        export_ai_ready=False,
    )
    if defaults:
        parser.set_defaults(**defaults)
    return parser


build_arg_parser = build_parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    argv_list = list(argv) if argv is not None else None
    probe_parser = argparse.ArgumentParser(add_help=False)
    probe_parser.add_argument("--config-file", default="")
    probe_parser.add_argument("--metadata-file", default="")
    probe_parser.add_argument("--check-updates", action="store_true")
    probe_parser.add_argument("--save-github-token", action="store_true")
    probe_parser.add_argument("--delete-saved-github-token", action="store_true")
    probe_parser.add_argument("--show-token-status", action="store_true")
    probe_parser.add_argument("--save-ai-api-key", action="store_true")
    probe_parser.add_argument("--delete-saved-ai-api-key", action="store_true")
    probe_parser.add_argument("--show-ai-api-key-status", action="store_true")
    probe_args, _ = probe_parser.parse_known_args(argv_list)

    defaults: dict[str, Any] = {}
    config_file_raw = str(probe_args.config_file or "").strip()
    if config_file_raw:
        try:
            defaults = load_config_file_defaults(Path(config_file_raw))
        except ValueError as exc:
            build_parser().error(str(exc))
    metadata_file_raw = str(probe_args.metadata_file or "").strip()
    if metadata_file_raw:
        defaults["metadata_file"] = metadata_file_raw

    secret_mode = bool(
        probe_args.check_updates
        or probe_args.save_github_token
        or probe_args.delete_saved_github_token
        or probe_args.show_token_status
        or probe_args.save_ai_api_key
        or probe_args.delete_saved_ai_api_key
        or probe_args.show_ai_api_key_status
    )
    parser = build_parser(defaults=defaults, secret_mode=secret_mode)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if getattr(args, "check_updates", False):
            from github_harvester.updater import UpdateChecker
            checker = UpdateChecker()
            res = checker.check_for_updates(force=True)
            if res.update_available and res.latest_release:
                print(f"Доступна новая версия: v{res.latest_release.version_str} (текущая: v{res.current_version})")
                print(f"Ссылка: {res.latest_release.html_url}")
            else:
                print(f"У вас установлена актуальная версия: v{res.current_version}")
            return 0
        if args.save_github_token:
            token = getpass.getpass("GitHub token: ").strip()
            store_secret(DEFAULT_SECRET_NAME, token)
            print("GitHub token сохранен в локальном Windows protected storage.")
            return 0
        if args.delete_saved_github_token:
            deleted = delete_secret(DEFAULT_SECRET_NAME)
            print("GitHub token удален." if deleted else "Сохраненный GitHub token не найден.")
            return 0
        if args.show_token_status:
            print("GitHub token: сохранен локально." if has_secret(DEFAULT_SECRET_NAME) else "GitHub token: не сохранен.")
            return 0
        if args.save_ai_api_key:
            if args.ai_provider == "ollama":
                print("AI provider API key: не требуется для Ollama.")
                return 0
            token = getpass.getpass("AI provider API key: ").strip()
            store_secret(secret_name_for_ai_provider(args.ai_provider, args.ai_filter_endpoint), token)
            print("AI provider API key сохранен в локальном Windows protected storage.")
            return 0
        if args.delete_saved_ai_api_key:
            secret_name = secret_name_for_ai_provider(args.ai_provider, args.ai_filter_endpoint)
            deleted = delete_secret(secret_name)
            print("AI provider API key удален." if deleted else "Сохраненный AI provider API key не найден.")
            return 0
        if args.show_ai_api_key_status:
            if args.ai_provider == "ollama":
                print("AI provider API key: не требуется для Ollama.")
                return 0
            secret_name = secret_name_for_ai_provider(args.ai_provider, args.ai_filter_endpoint)
            print("AI provider API key: сохранен локально." if has_secret(secret_name) else "AI provider API key: не сохранен.")
            return 0

        created_after = parse_iso_date(args.created_after, "--created-after")
        created_before = parse_iso_date(args.created_before, "--created-before")
        metadata_file = Path(args.metadata_file).expanduser() if str(args.metadata_file or "").strip() else None
        metadata_query = ""
        metadata_repositories = None
        if metadata_file is not None:
            metadata_query, metadata_repositories = load_repositories_from_metadata(metadata_file)
        query = str(args.query or "").strip() or metadata_query
        if not query:
            print("Ошибка: укажите --query или metadata-файл с query/search_query.", file=sys.stderr)
            return 1

        resolved_token, _token_source = resolve_github_token(
            explicit_token=args.token,
            env_token=os.environ.get("GITHUB_TOKEN", ""),
        )
        resolved_ai_api_key, _ai_key_source = resolve_ai_api_key(
            provider_type=args.ai_provider,
            endpoint=args.ai_filter_endpoint,
            explicit_key=args.ai_api_key,
            key_env_name=args.ai_api_key_env,
        )
        config = RunConfig(
            query=query,
            output_root=Path(args.output or "./output"),
            token=resolved_token,
            min_stars=args.min_stars,
            language=args.language.strip(),
            include_forks=args.include_forks,
            include_archived=args.include_archived,
            created_after=created_after,
            created_before=created_before,
            max_age_years=args.max_age_years,
            sort=args.sort,
            order=args.order,
            max_repos=args.max_repos,
            workers=args.workers,
            batch_size=args.batch_size,
            request_timeout=args.request_timeout,
            clone_timeout=args.clone_timeout,
            clone_depth=args.clone_depth,
            clone_partial=args.clone_partial,
            clone_single_branch=args.clone_single_branch,
            clone_no_tags=args.clone_no_tags,
            retry_failed_clones=args.retry_failed_clones,
            retry_delay_seconds=args.retry_delay,
            max_retries=args.max_retries,
            max_rate_limit_wait=args.max_rate_limit_wait,
            skip_existing=args.skip_existing,
            no_sharding=args.no_sharding,
            dry_run=args.dry_run,
            ai_filter_enabled=args.ai_filter,
            ai_provider_type=args.ai_provider,
            ai_filter_endpoint=args.ai_filter_endpoint.strip(),
            ai_filter_model=args.ai_filter_model.strip(),
            ai_api_key=resolved_ai_api_key,
            ai_filter_timeout=args.ai_filter_timeout,
            ai_temperature=args.ai_temperature,
            ai_num_ctx=args.ai_num_ctx,
            ai_num_predict=args.ai_num_predict,
            ai_filter_min_score=args.ai_filter_min_score,
            ai_filter_max_reviews=args.ai_filter_max_reviews,
            include_keywords=parse_keyword_list(args.include_keywords),
            exclude_keywords=parse_keyword_list(args.exclude_keywords),
            incremental=args.incremental,
            resume_state_file=Path(args.resume_state_file) if str(args.resume_state_file or "").strip() else None,
            export_sqlite=Path(args.export_sqlite) if str(args.export_sqlite or "").strip() else None,
            export_csv=args.export_csv,
            export_ai_ready=args.export_ai_ready,
            graphql_enrich=args.graphql_enrich,
            graphql_batch_size=args.graphql_batch_size,
            deep_relevance_enabled=args.deep_relevance,
            deep_relevance_max_repos=args.deep_relevance_max_repos,
            deep_relevance_min_score=args.deep_relevance_min_score,
            ai_custom_prompt=args.ai_custom_prompt.strip(),
        )

        if metadata_repositories is not None:
            run_download_for_repositories(
                config=config,
                repositories=metadata_repositories,
                metadata_file=metadata_file,
                log=print,
            )
        else:
            run_collection(config=config, log=print)
        return 0
    except KeyboardInterrupt:
        print("Ошибка: операция прервана пользователем.", file=sys.stderr)
        return 130
    except (ValueError, GitHubApiError, RunCancelledError, RuntimeError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
