from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Repo:
    id: int
    full_name: str
    clone_url: str
    html_url: str
    description: str
    stargazers_count: int
    language: str
    topics: list[str]
    default_branch: str
    created_at: str
    updated_at: str
    pushed_at: str
    node_id: str = ""
    forks_count: int = 0
    open_issues_count: int = 0
    watchers_count: int = 0
    size_kb: int = 0
    license_spdx_id: str = ""
    is_fork: bool = False
    is_archived: bool = False
    visibility: str = ""
    homepage_url: str = ""
    default_branch_oid: str = ""
    default_branch_committed_at: str = ""
    latest_commit_message: str = ""
    latest_release_tag: str = ""
    latest_release_published_at: str = ""
    is_mirror: bool = False
    is_empty: bool = False
    graphql_enriched: bool = False
    readme_relevance_score: float = 0.0
    code_relevance_score: float = 0.0
    deep_relevance_score: float = 0.0
    deep_relevance_checked: bool = False
    deep_relevance_error: str = ""

    @classmethod
    def from_api_item(cls, item: dict) -> "Repo":
        raw_license = item.get("license")
        if isinstance(raw_license, dict):
            license_spdx_id = str(raw_license.get("spdx_id") or "").strip()
        else:
            license_spdx_id = str(item.get("license_spdx_id") or "").strip()
        return cls(
            id=int(item["id"]),
            node_id=str(item.get("node_id") or item.get("nodeId") or "").strip(),
            full_name=str(item["full_name"]),
            clone_url=str(item["clone_url"]),
            html_url=str(item["html_url"]),
            description=str(item.get("description") or ""),
            stargazers_count=int(item.get("stargazers_count") or 0),
            language=str(item.get("language") or ""),
            topics=[str(topic) for topic in item.get("topics") or []],
            default_branch=str(item.get("default_branch") or "main"),
            created_at=str(item.get("created_at") or ""),
            updated_at=str(item.get("updated_at") or ""),
            pushed_at=str(item.get("pushed_at") or ""),
            forks_count=int(item.get("forks_count") or item.get("forks") or 0),
            open_issues_count=int(item.get("open_issues_count") or item.get("open_issues") or 0),
            watchers_count=int(item.get("watchers_count") or item.get("watchers") or 0),
            size_kb=int(item.get("size") or item.get("size_kb") or 0),
            license_spdx_id=license_spdx_id,
            is_fork=bool(item.get("fork") if "fork" in item else item.get("is_fork", False)),
            is_archived=bool(item.get("archived") if "archived" in item else item.get("is_archived", False)),
            visibility=str(item.get("visibility") or ""),
            homepage_url=str(item.get("homepage_url") or item.get("homepageUrl") or "").strip(),
            default_branch_oid=str(item.get("default_branch_oid") or "").strip(),
            default_branch_committed_at=str(item.get("default_branch_committed_at") or "").strip(),
            latest_commit_message=str(item.get("latest_commit_message") or "").strip(),
            latest_release_tag=str(item.get("latest_release_tag") or "").strip(),
            latest_release_published_at=str(item.get("latest_release_published_at") or "").strip(),
            is_mirror=bool(item.get("is_mirror", False)),
            is_empty=bool(item.get("is_empty", False)),
            graphql_enriched=bool(item.get("graphql_enriched", False)),
            readme_relevance_score=float(item.get("readme_relevance_score") or 0.0),
            code_relevance_score=float(item.get("code_relevance_score") or 0.0),
            deep_relevance_score=float(item.get("deep_relevance_score") or 0.0),
            deep_relevance_checked=bool(item.get("deep_relevance_checked", False)),
            deep_relevance_error=str(item.get("deep_relevance_error") or "").strip(),
        )


@dataclass(frozen=True)
class SearchOptions:
    query: str
    min_stars: int
    language: str
    include_forks: bool
    include_archived: bool
    created_after: date
    created_before: date
    sort: str
    order: str


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    total_count: int
