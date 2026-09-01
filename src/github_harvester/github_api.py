from __future__ import annotations

import base64
import json
import math
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Sequence

from github_harvester.models import DateRange, Repo, SearchOptions


SEARCH_URL = "https://api.github.com/search/repositories"
REPOSITORY_URL = "https://api.github.com/repos/{owner}/{repo}"
GRAPHQL_URL = "https://api.github.com/graphql"
GITHUB_API_VERSION = "2026-03-10"


class GitHubApiError(RuntimeError):
    """Raised when GitHub API request fails after retries."""


class GitHubCancelledError(RuntimeError):
    """Raised when search is cancelled by user."""


class GitHubClient:
    def __init__(
        self,
        token: str = "",
        timeout: int = 30,
        max_retries: int = 5,
        max_rate_limit_wait: int = 900,
        log: Callable[[str], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> None:
        self.token = token.strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_rate_limit_wait = max_rate_limit_wait
        self.log = log or (lambda _: None)
        self.should_cancel = should_cancel or (lambda: False)
        self._rate_limits: dict[str, dict[str, float]] = {}

    def _get_resource_for_url(self, url: str) -> str:
        if url.startswith(SEARCH_URL):
            return "search"
        if url.startswith(GRAPHQL_URL):
            return "graphql"
        return "core"

    def _check_proactive_rate_limit(self, resource: str, cost: int = 1) -> None:
        limit_info = self._rate_limits.get(resource)
        if not limit_info:
            return
        if limit_info["remaining"] < cost:
            now = time.time()
            reset_at = limit_info["reset"]
            if reset_at > now:
                wait_seconds = reset_at - now + random.uniform(1, 3)
                if wait_seconds > self.max_rate_limit_wait:
                    raise GitHubApiError(f"Proactive rate limit wait ({wait_seconds:.1f}s) exceeds max.")
                self.log(f"Proactive rate limit wait for {resource}: {wait_seconds:.1f} сек...")
                waited = 0.0
                while waited < wait_seconds:
                    if self.should_cancel():
                        raise GitHubCancelledError("Поиск отменен пользователем.")
                    time.sleep(1)
                    waited += 1

    def _update_rate_limit(self, headers: dict[str, str], resource: str) -> None:
        returned_resource = headers.get("X-RateLimit-Resource", resource)
        remaining = _parse_positive_int(headers.get("X-RateLimit-Remaining"))
        reset = _parse_positive_int(headers.get("X-RateLimit-Reset"))
        if remaining is not None and reset is not None:
            self._rate_limits[returned_resource] = {"remaining": float(remaining), "reset": float(reset)}

    def search_page(self, query: str, sort: str, order: str, page: int, per_page: int) -> dict:
        params = {
            "q": query,
            "sort": sort,
            "order": order,
            "per_page": per_page,
            "page": page,
        }
        return self._request_json(SEARCH_URL, params)

    def get_repository_readme_text(self, repo: Repo, max_chars: int = 200_000) -> str:
        owner, name = _split_repository_full_name(repo.full_name)
        url = f"{_repository_api_url(owner, name)}/readme"
        payload = self._request_json(url, {})
        encoding = str(payload.get("encoding") or "").strip().lower()
        content = payload.get("content")
        if encoding != "base64" or not isinstance(content, str):
            return ""
        normalized = "".join(content.split())
        try:
            decoded = base64.b64decode(normalized, validate=False)
        except Exception as exc:
            raise GitHubApiError(f"README {repo.full_name} не удалось декодировать base64.") from exc
        text = decoded.decode("utf-8", errors="replace")
        if max_chars > 0 and len(text) > max_chars:
            return text[:max_chars]
        return text

    def get_repository_tree_paths(self, repo: Repo, max_paths: int = 5_000) -> tuple[list[str], bool]:
        owner, name = _split_repository_full_name(repo.full_name)
        ref = repo.default_branch.strip() or "HEAD"
        quoted_ref = urllib.parse.quote(ref, safe="")
        url = f"{_repository_api_url(owner, name)}/git/trees/{quoted_ref}"
        payload = self._request_json(url, {"recursive": 1})
        tree = payload.get("tree")
        if not isinstance(tree, list):
            return [], bool(payload.get("truncated", False))
        paths: list[str] = []
        for item in tree:
            if not isinstance(item, dict):
                continue
            if str(item.get("type") or "") != "blob":
                continue
            path = str(item.get("path") or "").strip()
            if not path:
                continue
            paths.append(path)
            if max_paths > 0 and len(paths) >= max_paths:
                break
        truncated = bool(payload.get("truncated", False)) or (
            max_paths > 0 and len(paths) >= max_paths and len(tree) > max_paths
        )
        return paths, truncated

    def graphql(self, query: str, variables: dict[str, object]) -> dict:
        if not self.token:
            raise GitHubApiError("GitHub GraphQL API требует GITHUB_TOKEN.")
        payload = {
            "query": query,
            "variables": variables,
        }
        return self._request_graphql_json(payload)

    def _request_json(self, url: str, params: dict[str, str | int] | None = None) -> dict:
        params = params or {}
        encoded = urllib.parse.urlencode(params)
        full_url = f"{url}?{encoded}" if encoded else url
        resource = self._get_resource_for_url(url)
        self._check_proactive_rate_limit(resource)
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "github-harvester/1.0",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for attempt in range(1, self.max_retries + 2):
            request = urllib.request.Request(full_url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self._update_rate_limit(response.headers, resource)
                    payload = response.read().decode("utf-8")
                    return json.loads(payload)
            except urllib.error.HTTPError as exc:
                self._update_rate_limit(exc.headers, resource)
                error_body = exc.read().decode("utf-8", errors="replace")
                error_message = _extract_api_message(error_body)
                if _is_rate_limit_error(exc.code, error_message):
                    if attempt <= self.max_retries:
                        self._wait_for_rate_limit(exc.headers, fallback_attempt=attempt)
                        continue
                    raise GitHubApiError(
                        "Достигнут лимит запросов GitHub после всех повторных попыток: "
                        f"{error_message or error_body}"
                    ) from exc
                if exc.code >= 500 and attempt <= self.max_retries:
                    time.sleep(2 * attempt)
                    continue
                raise GitHubApiError(
                    f"Ошибка GitHub API {exc.code}: {error_message or error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt <= self.max_retries:
                    time.sleep(2 * attempt)
                    continue
                raise GitHubApiError(f"Сетевая ошибка: {exc}") from exc

        raise GitHubApiError("GitHub API не ответил после повторных попыток")

    def _request_graphql_json(self, payload: dict[str, object]) -> dict:
        resource = "graphql"
        self._check_proactive_rate_limit(resource)
        headers = {
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "github-harvester/1.0",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "Authorization": f"Bearer {self.token}",
        }
        body = json.dumps(payload).encode("utf-8")
        for attempt in range(1, self.max_retries + 2):
            request = urllib.request.Request(GRAPHQL_URL, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self._update_rate_limit(response.headers, resource)
                    response_payload = response.read().decode("utf-8")
                    result = json.loads(response_payload)
                    if isinstance(result, dict) and "data" in result:
                        rate_limit = result["data"].get("rateLimit")
                        if isinstance(rate_limit, dict):
                            remaining = _parse_positive_int(rate_limit.get("remaining"))
                            cost = _parse_positive_int(rate_limit.get("cost"))
                            reset_at = _parse_iso_timestamp(rate_limit.get("resetAt"))
                            if remaining is not None and reset_at is not None:
                                self._rate_limits[resource] = {"remaining": float(remaining), "reset": reset_at}

                    if isinstance(result, dict) and result.get("errors") and not result.get("data"):
                        error_message = _extract_graphql_error_message(result)
                        if _is_rate_limit_error(403, error_message) and attempt <= self.max_retries:
                            self._wait_for_rate_limit(response.headers, fallback_attempt=attempt)
                            continue
                        raise GitHubApiError(f"Ошибка GitHub GraphQL API: {error_message}")
                    return result
            except urllib.error.HTTPError as exc:
                self._update_rate_limit(exc.headers, resource)
                error_body = exc.read().decode("utf-8", errors="replace")
                error_message = _extract_api_message(error_body) or _extract_graphql_error_message_from_text(error_body)
                if _is_rate_limit_error(exc.code, error_message):
                    if attempt <= self.max_retries:
                        self._wait_for_rate_limit(exc.headers, fallback_attempt=attempt)
                        continue
                    raise GitHubApiError(
                        "Достигнут лимит запросов GitHub GraphQL после всех повторных попыток: "
                        f"{error_message or error_body}"
                    ) from exc
                if exc.code >= 500 and attempt <= self.max_retries:
                    time.sleep(2 * attempt)
                    continue
                raise GitHubApiError(
                    f"Ошибка GitHub GraphQL API {exc.code}: {error_message or error_body}"
                ) from exc
            except urllib.error.URLError as exc:
                if attempt <= self.max_retries:
                    time.sleep(2 * attempt)
                    continue
                raise GitHubApiError(f"Сетевая ошибка GitHub GraphQL: {exc}") from exc

        raise GitHubApiError("GitHub GraphQL API не ответил после повторных попыток")

    def _wait_for_rate_limit(self, headers: dict[str, str], fallback_attempt: int = 1) -> None:
        wait_seconds = _rate_limit_wait_seconds(headers, fallback_attempt=fallback_attempt)
        if wait_seconds > self.max_rate_limit_wait:
            raise GitHubApiError(
                "Достигнут лимит запросов GitHub, время ожидания превышает допустимое "
                f"({wait_seconds}s > {self.max_rate_limit_wait}s)."
            )
        self.log(f"Достигнут лимит GitHub API. Ожидание {wait_seconds} сек...")
        waited = 0
        while waited < wait_seconds:
            if self.should_cancel():
                raise GitHubCancelledError("Поиск отменен пользователем.")
            time.sleep(1)
            waited += 1


def _split_repository_full_name(full_name: str) -> tuple[str, str]:
    parts = str(full_name or "").strip().split("/", maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        raise GitHubApiError(f"Некорректное имя репозитория: {full_name}")
    return parts[0].strip(), parts[1].strip()


def _repository_api_url(owner: str, repo: str) -> str:
    quoted_owner = urllib.parse.quote(owner, safe="")
    quoted_repo = urllib.parse.quote(repo, safe="")
    return REPOSITORY_URL.format(owner=quoted_owner, repo=quoted_repo)


def _rate_limit_wait_seconds(
    headers: dict[str, str],
    now: int | None = None,
    fallback_attempt: int = 1,
) -> float:
    current_time = int(time.time()) if now is None else int(now)
    retry_after = _parse_positive_int(headers.get("Retry-After"))
    if retry_after is not None:
        return float(retry_after) + random.uniform(1, 3)

    reset_unix = _parse_positive_int(headers.get("X-RateLimit-Reset"))
    remaining = str(headers.get("X-RateLimit-Remaining") or "").strip()
    if reset_unix is not None and remaining == "0":
        return max(1.0, float(reset_unix - current_time)) + random.uniform(1, 3)

    attempt = max(1, int(fallback_attempt or 1))
    return float(60 * (2 ** (attempt - 1))) + random.uniform(1, 3)


def _parse_positive_int(raw_value: object) -> int | None:
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def build_search_query(options: SearchOptions, start: date | None = None, end: date | None = None) -> str:
    parts = [options.query.strip()]
    if options.min_stars > 0:
        parts.append(f"stars:>={options.min_stars}")
    if options.language:
        parts.append(f"language:{options.language}")
    parts.append("fork:true" if options.include_forks else "fork:false")
    parts.append("archived:true" if options.include_archived else "archived:false")
    if start and end:
        parts.append(f"created:{start.isoformat()}..{end.isoformat()}")
    elif start:
        parts.append(f"created:>={start.isoformat()}")
    elif end:
        parts.append(f"created:<={end.isoformat()}")
    return " ".join(part for part in parts if part)


def collect_repositories(
    client: GitHubClient,
    options: SearchOptions,
    max_repositories: int | None = None,
    use_date_sharding: bool = True,
    log: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Repo]:
    logger = log or (lambda _: None)
    is_cancelled = should_cancel or (lambda: False)
    if is_cancelled():
        raise GitHubCancelledError("Поиск отменен пользователем.")
    if use_date_sharding:
        ranges = plan_date_ranges(
            options.created_after,
            options.created_before,
            lambda start, end: count_repositories(client, options, start, end),
            should_cancel=is_cancelled,
        )
    else:
        total = count_repositories(client, options, options.created_after, options.created_before)
        ranges = [DateRange(options.created_after, options.created_before, total)]

    if not ranges:
        return []

    ordered_ranges = list(ranges)
    if use_date_sharding and options.order == "desc":
        ordered_ranges.reverse()

    unique_repos: dict[int, Repo] = {}
    for index, date_range in enumerate(ordered_ranges, start=1):
        if is_cancelled():
            raise GitHubCancelledError("Поиск отменен пользователем.")
        if date_range.total_count <= 0:
            continue
        logger(
            "Сбор диапазона "
            f"{index}/{len(ordered_ranges)}: {date_range.start.isoformat()}..{date_range.end.isoformat()} "
            f"(количество={date_range.total_count})"
        )
        if max_repositories and max_repositories > 0:
            target_for_shard = min(date_range.total_count, max_repositories)
        else:
            target_for_shard = min(date_range.total_count, 1000)
            
        page_count = min(math.ceil(target_for_shard / 100), 10)
        query = build_search_query(options, date_range.start, date_range.end)
        for page in range(1, page_count + 1):
            if is_cancelled():
                raise GitHubCancelledError("Поиск отменен пользователем.")
            data = client.search_page(query, options.sort, options.order, page=page, per_page=100)
            items = data.get("items", [])
            for item in items:
                repo = Repo.from_api_item(item)
                unique_repos[repo.id] = repo
                
            if len(items) < 100:
                break
                
            # Early exit if we collected enough across ALL shards (since we sort later anyway, but if we don't care about absolute global ordering beyond max_repos, it's fine. Wait, if we use date sharding, breaking early gives us the most recent repos if ordered desc)
            if max_repositories and max_repositories > 0 and len(unique_repos) >= max_repositories:
                break
                
        if max_repositories and max_repositories > 0 and len(unique_repos) >= max_repositories:
            break

    ordered_repositories = sort_repositories(unique_repos.values(), options.sort, options.order)
    if max_repositories and max_repositories > 0:
        return ordered_repositories[:max_repositories]
    return ordered_repositories


def enrich_repositories_with_graphql(
    client: GitHubClient,
    repositories: Sequence[Repo],
    batch_size: int = 25,
    log: Callable[[str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> list[Repo]:
    logger = log or (lambda _: None)
    is_cancelled = should_cancel or (lambda: False)
    if not repositories:
        return []

    bounded_batch_size = max(1, min(int(batch_size), 50))
    result_by_id = {repo.id: repo for repo in repositories}
    candidates = [repo for repo in repositories if repo.node_id.strip()]
    if not candidates:
        logger("GraphQL enrichment: пропущено, в REST metadata нет node_id.")
        return list(repositories)

    logger(
        "GraphQL enrichment: "
        f"обогащаем {len(candidates)}/{len(repositories)} репозиториев "
        f"(batch_size={bounded_batch_size})."
    )
    for batch_start in range(0, len(candidates), bounded_batch_size):
        if is_cancelled:
            if is_cancelled():
                raise GitHubCancelledError("GraphQL enrichment отменен пользователем.")
        batch = candidates[batch_start : batch_start + bounded_batch_size]
        query = _build_graphql_repository_enrichment_query(len(batch))
        variables = {f"id{index}": repo.node_id for index, repo in enumerate(batch)}
        payload = client.graphql(query, variables)
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        for index, original_repo in enumerate(batch):
            raw_repo = data.get(f"repo{index}")
            if not isinstance(raw_repo, dict) or raw_repo.get("__typename") != "Repository":
                continue
            result_by_id[original_repo.id] = _apply_graphql_repository_enrichment(original_repo, raw_repo)

    return [result_by_id.get(repo.id, repo) for repo in repositories]


def count_repositories(
    client: GitHubClient,
    options: SearchOptions,
    start: date,
    end: date,
) -> int:
    query = build_search_query(options, start, end)
    data = client.search_page(query, options.sort, options.order, page=1, per_page=1)
    return int(data.get("total_count") or 0)


def _build_graphql_repository_enrichment_query(count: int) -> str:
    variables = ", ".join(f"$id{index}: ID!" for index in range(count))
    aliases = "\n".join(
        f"  repo{index}: node(id: $id{index}) {{\n"
        "    ...RepositoryEnrichmentFields\n"
        "  }"
        for index in range(count)
    )
    return (
        f"query RepositoryEnrichment({variables}) {{\n"
        f"  rateLimit {{\n"
        f"    cost\n"
        f"    remaining\n"
        f"    resetAt\n"
        f"  }}\n"
        f"{aliases}\n"
        "}\n"
        "fragment RepositoryEnrichmentFields on Repository {\n"
        "  __typename\n"
        "  id\n"
        "  nameWithOwner\n"
        "  homepageUrl\n"
        "  diskUsage\n"
        "  isArchived\n"
        "  isEmpty\n"
        "  isFork\n"
        "  isMirror\n"
        "  updatedAt\n"
        "  pushedAt\n"
        "  primaryLanguage { name }\n"
        "  licenseInfo { spdxId }\n"
        "  defaultBranchRef {\n"
        "    name\n"
        "    target {\n"
        "      __typename\n"
        "      ... on Commit {\n"
        "        oid\n"
        "        messageHeadline\n"
        "        committedDate\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  latestRelease {\n"
        "    tagName\n"
        "    publishedAt\n"
        "  }\n"
        "  repositoryTopics(first: 20) {\n"
        "    nodes { topic { name } }\n"
        "  }\n"
        "}\n"
    )


def _apply_graphql_repository_enrichment(repo: Repo, raw_repo: dict) -> Repo:
    primary_language = raw_repo.get("primaryLanguage")
    language = repo.language
    if isinstance(primary_language, dict):
        language = str(primary_language.get("name") or repo.language)

    license_info = raw_repo.get("licenseInfo")
    license_spdx_id = repo.license_spdx_id
    if isinstance(license_info, dict):
        license_spdx_id = str(license_info.get("spdxId") or repo.license_spdx_id)

    default_branch_ref = raw_repo.get("defaultBranchRef")
    default_branch = repo.default_branch
    default_branch_oid = repo.default_branch_oid
    default_branch_committed_at = repo.default_branch_committed_at
    latest_commit_message = repo.latest_commit_message
    if isinstance(default_branch_ref, dict):
        default_branch = str(default_branch_ref.get("name") or repo.default_branch)
        target = default_branch_ref.get("target")
        if isinstance(target, dict):
            default_branch_oid = str(target.get("oid") or repo.default_branch_oid)
            default_branch_committed_at = str(
                target.get("committedDate") or repo.default_branch_committed_at
            )
            latest_commit_message = str(target.get("messageHeadline") or repo.latest_commit_message)

    latest_release = raw_repo.get("latestRelease")
    latest_release_tag = repo.latest_release_tag
    latest_release_published_at = repo.latest_release_published_at
    if isinstance(latest_release, dict):
        latest_release_tag = str(latest_release.get("tagName") or repo.latest_release_tag)
        latest_release_published_at = str(
            latest_release.get("publishedAt") or repo.latest_release_published_at
        )

    topics = _extract_graphql_topics(raw_repo.get("repositoryTopics")) or repo.topics
    return replace(
        repo,
        node_id=str(raw_repo.get("id") or repo.node_id),
        full_name=str(raw_repo.get("nameWithOwner") or repo.full_name),
        homepage_url=str(raw_repo.get("homepageUrl") or repo.homepage_url),
        size_kb=_coerce_int(raw_repo.get("diskUsage"), repo.size_kb),
        is_archived=_coerce_bool(raw_repo.get("isArchived"), repo.is_archived),
        is_empty=_coerce_bool(raw_repo.get("isEmpty"), repo.is_empty),
        is_fork=_coerce_bool(raw_repo.get("isFork"), repo.is_fork),
        is_mirror=_coerce_bool(raw_repo.get("isMirror"), repo.is_mirror),
        updated_at=str(raw_repo.get("updatedAt") or repo.updated_at),
        pushed_at=str(raw_repo.get("pushedAt") or repo.pushed_at),
        language=language,
        license_spdx_id=license_spdx_id,
        default_branch=default_branch,
        default_branch_oid=default_branch_oid,
        default_branch_committed_at=default_branch_committed_at,
        latest_commit_message=latest_commit_message,
        latest_release_tag=latest_release_tag,
        latest_release_published_at=latest_release_published_at,
        topics=topics,
        graphql_enriched=True,
    )


def _extract_graphql_topics(raw_topics: object) -> list[str]:
    if not isinstance(raw_topics, dict):
        return []
    nodes = raw_topics.get("nodes")
    if not isinstance(nodes, list):
        return []
    topics: list[str] = []
    seen: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            continue
        topic = node.get("topic")
        if not isinstance(topic, dict):
            continue
        name = str(topic.get("name") or "").strip()
        lowered = name.lower()
        if not name or lowered in seen:
            continue
        seen.add(lowered)
        topics.append(name)
    return topics


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def plan_date_ranges(
    start: date,
    end: date,
    count_func: Callable[[date, date], int],
    max_per_range: int = 1000,
    should_cancel: Callable[[], bool] | None = None,
) -> list[DateRange]:
    is_cancelled = should_cancel or (lambda: False)
    if start > end:
        raise ValueError("Дата начала не может быть больше даты конца")
    stack: list[tuple[date, date]] = [(start, end)]
    ranges: list[DateRange] = []

    while stack:
        if is_cancelled():
            raise GitHubCancelledError("Поиск отменен пользователем.")
        current_start, current_end = stack.pop()
        total_count = count_func(current_start, current_end)
        if total_count <= 0:
            continue
        if total_count <= max_per_range or current_start == current_end:
            ranges.append(DateRange(current_start, current_end, total_count))
            continue
        delta_days = (current_end - current_start).days
        midpoint = current_start + timedelta(days=delta_days // 2)
        left_start = current_start
        left_end = midpoint
        right_start = midpoint + timedelta(days=1)
        right_end = current_end
        stack.append((right_start, right_end))
        stack.append((left_start, left_end))

    ranges.sort(key=lambda item: item.start)
    return ranges


def _extract_api_message(raw_body: str) -> str:
    if not raw_body:
        return ""
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return ""
    message = str(payload.get("message") or "").strip()
    errors = payload.get("errors")
    details: list[str] = []
    if isinstance(errors, list):
        for item in errors[:3]:
            if isinstance(item, dict):
                detail = str(item.get("message") or item.get("code") or "").strip()
            else:
                detail = str(item).strip()
            if detail:
                details.append(detail)
    if details:
        suffix = "; ".join(details)
        return f"{message}: {suffix}" if message else suffix
    return message


def _extract_graphql_error_message_from_text(raw_body: str) -> str:
    if not raw_body:
        return ""
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        return _extract_graphql_error_message(payload)
    return ""


def _extract_graphql_error_message(payload: dict) -> str:
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return ""
    messages: list[str] = []
    for item in errors[:5]:
        if isinstance(item, dict):
            message = str(item.get("message") or item.get("type") or "").strip()
        else:
            message = str(item).strip()
        if message:
            messages.append(message)
    return "; ".join(messages)


def _is_rate_limit_error(status_code: int, message: str) -> bool:
    if status_code not in (403, 429):
        return False
    lowered = message.lower()
    return "rate limit" in lowered or "secondary rate limit" in lowered or "rate_limited" in lowered


def deduplicate_repositories(repositories: Iterable[Repo]) -> list[Repo]:
    unique: dict[int, Repo] = {}
    for repository in repositories:
        unique[repository.id] = repository
    return list(unique.values())


def sort_repositories(repositories: Iterable[Repo], sort: str, order: str) -> list[Repo]:
    reverse = order == "desc"

    if sort == "updated":
        return sorted(
            repositories,
            key=lambda repo: (_repo_update_timestamp(repo), repo.stargazers_count, repo.id),
            reverse=reverse,
        )
    return sorted(
        repositories,
        key=lambda repo: (repo.stargazers_count, _repo_update_timestamp(repo), repo.id),
        reverse=reverse,
    )


def _repo_update_timestamp(repo: Repo) -> float:
    for raw_value in (repo.updated_at, repo.pushed_at, repo.created_at):
        parsed = _parse_iso_timestamp(raw_value)
        if parsed is not None:
            return parsed
    return 0.0


def _parse_iso_timestamp(raw_value: str) -> float | None:
    text = str(raw_value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed.timestamp()
