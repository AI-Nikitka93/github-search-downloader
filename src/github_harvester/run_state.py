from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from github_harvester.downloader import CloneResult
from github_harvester.models import Repo


RUN_STATE_SCHEMA_VERSION = 1
TERMINAL_SUCCESS_STATUSES = {"cloned", "skipped"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def initialize_run_state(
    state_file: Path,
    query: str,
    metadata_file: Path,
    repositories: Sequence[Repo],
    mode: str,
) -> Path:
    payload = {
        "schema_version": RUN_STATE_SCHEMA_VERSION,
        "producer": "github-harvester",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "mode": mode,
        "query": query,
        "metadata_file": str(metadata_file),
        "total": len(repositories),
        "results": {
            repo.full_name: {
                "repo_id": repo.id,
                "status": "pending",
                "target_path": "",
                "message": "",
                "updated_at": "",
            }
            for repo in repositories
        },
    }
    _atomic_write_json(state_file, payload)
    return state_file


def record_clone_result(state_file: Path, result: CloneResult) -> None:
    payload = load_run_state(state_file)
    results = payload.setdefault("results", {})
    if not isinstance(results, dict):
        results = {}
        payload["results"] = results
    previous = results.get(result.repo_full_name)
    repo_id = previous.get("repo_id") if isinstance(previous, dict) else None
    results[result.repo_full_name] = {
        "repo_id": repo_id,
        "status": result.status,
        "target_path": str(result.target_path),
        "message": result.message,
        "updated_at": utc_now_iso(),
    }
    payload["updated_at"] = utc_now_iso()
    _atomic_write_json(state_file, payload)


def load_run_state(state_file: Path) -> dict:
    try:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Не удалось прочитать run-state JSON: {state_file}") from exc
    if not isinstance(payload, dict):
        raise ValueError("run-state JSON должен быть объектом.")
    schema_version = int(payload.get("schema_version", 0) or 0)
    if schema_version != RUN_STATE_SCHEMA_VERSION:
        raise ValueError(
            "run-state JSON имеет неподдерживаемую схему "
            f"(schema_version={schema_version}, поддерживается {RUN_STATE_SCHEMA_VERSION})."
        )
    return payload


def filter_repositories_for_resume(
    repositories: Sequence[Repo],
    state_file: Path,
    skip_statuses: Iterable[str] = TERMINAL_SUCCESS_STATUSES,
) -> tuple[list[Repo], int]:
    payload = load_run_state(state_file)
    raw_results = payload.get("results")
    if not isinstance(raw_results, dict):
        return list(repositories), 0
    skip_set = set(skip_statuses)
    remaining: list[Repo] = []
    skipped_count = 0
    for repo in repositories:
        item = raw_results.get(repo.full_name)
        status = item.get("status") if isinstance(item, dict) else ""
        if status in skip_set:
            skipped_count += 1
            continue
        remaining.append(repo)
    return remaining, skipped_count


def collect_repository_ids_from_metadata(metadata_dir: Path) -> set[int]:
    seen: set[int] = set()
    if not metadata_dir.exists():
        return seen
    for metadata_file in sorted(metadata_dir.glob("search_*.json")):
        try:
            payload = json.loads(metadata_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        raw_repositories = payload.get("repositories")
        if raw_repositories is None:
            raw_repositories = payload.get("items")
        if not isinstance(raw_repositories, list):
            continue
        for raw_item in raw_repositories:
            if not isinstance(raw_item, dict):
                continue
            try:
                seen.add(int(raw_item.get("id")))
            except (TypeError, ValueError):
                continue
    return seen


def _atomic_write_json(target_path: Path, payload: dict) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_name(f".{target_path.name}.tmp_{datetime.now().timestamp()}")
    try:
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(target_path)
    finally:
        temp_path.unlink(missing_ok=True)
