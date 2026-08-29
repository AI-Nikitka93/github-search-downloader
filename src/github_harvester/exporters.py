from __future__ import annotations

import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from github_harvester.models import Repo


def export_repositories_to_sqlite(
    sqlite_file: Path,
    query: str,
    repositories: Sequence[Repo],
    metadata_file: Path,
) -> Path:
    sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    run_id = metadata_file.stem
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    connection = sqlite3.connect(sqlite_file)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT OR REPLACE INTO runs(run_id, generated_at, query, metadata_file, repo_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, generated_at, query, str(metadata_file), len(repositories)),
        )
        repo_tuples = []
        run_repo_tuples = []
        for repo in repositories:
            repo_tuples.append((
                repo.id,
                repo.node_id,
                repo.full_name,
                repo.clone_url,
                repo.html_url,
                repo.description,
                repo.stargazers_count,
                repo.language,
                json.dumps(repo.topics, ensure_ascii=False),
                repo.default_branch,
                repo.created_at,
                repo.updated_at,
                repo.pushed_at,
                repo.forks_count,
                repo.open_issues_count,
                repo.watchers_count,
                repo.size_kb,
                repo.license_spdx_id,
                int(repo.is_fork),
                int(repo.is_archived),
                repo.visibility,
                repo.homepage_url,
                repo.default_branch_oid,
                repo.default_branch_committed_at,
                repo.latest_release_tag,
                repo.latest_release_published_at,
                int(repo.is_mirror),
                int(repo.is_empty),
                int(repo.graphql_enriched),
                repo.readme_relevance_score,
                repo.code_relevance_score,
                repo.deep_relevance_score,
                int(repo.deep_relevance_checked),
                repo.deep_relevance_error,
                run_id,
            ))
            run_repo_tuples.append((run_id, repo.id))

        if repo_tuples:
            connection.executemany(
                """
                INSERT OR REPLACE INTO repositories(
                    id, node_id, full_name, clone_url, html_url, description, stargazers_count,
                    language, topics_json, default_branch, created_at, updated_at,
                    pushed_at, forks_count, open_issues_count, watchers_count, size_kb,
                    license_spdx_id, is_fork, is_archived, visibility, homepage_url,
                    default_branch_oid, default_branch_committed_at, latest_release_tag,
                    latest_release_published_at, is_mirror, is_empty, graphql_enriched,
                    readme_relevance_score, code_relevance_score, deep_relevance_score,
                    deep_relevance_checked, deep_relevance_error,
                    last_seen_run
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                repo_tuples
            )
            connection.executemany(
                """
                INSERT OR REPLACE INTO run_repositories(run_id, repo_id)
                VALUES (?, ?)
                """,
                run_repo_tuples
            )
        connection.commit()
    finally:
        connection.close()
    return sqlite_file


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            generated_at TEXT NOT NULL,
            query TEXT NOT NULL,
            metadata_file TEXT NOT NULL,
            repo_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS repositories (
            id INTEGER PRIMARY KEY,
            node_id TEXT NOT NULL DEFAULT '',
            full_name TEXT NOT NULL UNIQUE,
            clone_url TEXT NOT NULL,
            html_url TEXT NOT NULL,
            description TEXT NOT NULL,
            stargazers_count INTEGER NOT NULL,
            language TEXT NOT NULL,
            topics_json TEXT NOT NULL,
            default_branch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            pushed_at TEXT NOT NULL,
            forks_count INTEGER NOT NULL DEFAULT 0,
            open_issues_count INTEGER NOT NULL DEFAULT 0,
            watchers_count INTEGER NOT NULL DEFAULT 0,
            size_kb INTEGER NOT NULL DEFAULT 0,
            license_spdx_id TEXT NOT NULL DEFAULT '',
            is_fork INTEGER NOT NULL DEFAULT 0,
            is_archived INTEGER NOT NULL DEFAULT 0,
            visibility TEXT NOT NULL DEFAULT '',
            homepage_url TEXT NOT NULL DEFAULT '',
            default_branch_oid TEXT NOT NULL DEFAULT '',
            default_branch_committed_at TEXT NOT NULL DEFAULT '',
            latest_release_tag TEXT NOT NULL DEFAULT '',
            latest_release_published_at TEXT NOT NULL DEFAULT '',
            is_mirror INTEGER NOT NULL DEFAULT 0,
            is_empty INTEGER NOT NULL DEFAULT 0,
            graphql_enriched INTEGER NOT NULL DEFAULT 0,
            readme_relevance_score REAL NOT NULL DEFAULT 0,
            code_relevance_score REAL NOT NULL DEFAULT 0,
            deep_relevance_score REAL NOT NULL DEFAULT 0,
            deep_relevance_checked INTEGER NOT NULL DEFAULT 0,
            deep_relevance_error TEXT NOT NULL DEFAULT '',
            last_seen_run TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS run_repositories (
            run_id TEXT NOT NULL,
            repo_id INTEGER NOT NULL,
            PRIMARY KEY (run_id, repo_id),
            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
            FOREIGN KEY (repo_id) REFERENCES repositories(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_repositories_full_name ON repositories(full_name);
        CREATE INDEX IF NOT EXISTS idx_repositories_language ON repositories(language);
        CREATE INDEX IF NOT EXISTS idx_repositories_stars ON repositories(stargazers_count);
        CREATE INDEX IF NOT EXISTS idx_repositories_pushed_at ON repositories(pushed_at);
        """
    )
    _ensure_column(connection, "repositories", "forks_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "node_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "open_issues_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "watchers_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "size_kb", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "license_spdx_id", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "is_fork", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "is_archived", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "visibility", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "homepage_url", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "default_branch_oid", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "default_branch_committed_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "latest_release_tag", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "latest_release_published_at", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(connection, "repositories", "is_mirror", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "is_empty", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "graphql_enriched", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "readme_relevance_score", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "code_relevance_score", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "deep_relevance_score", "REAL NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "deep_relevance_checked", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "repositories", "deep_relevance_error", "TEXT NOT NULL DEFAULT ''")


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        str(row[1])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in existing_columns:
        return
    connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def export_to_csv(csv_file: Path, repositories: Sequence[Repo]) -> Path:
    csv_file.parent.mkdir(parents=True, exist_ok=True)
    
    headers = [
        "id", "full_name", "clone_url", "html_url", "description", 
        "stargazers_count", "language", "topics", "default_branch", 
        "created_at", "updated_at", "pushed_at", "forks_count", 
        "open_issues_count", "watchers_count", "size_kb", "license_spdx_id",
        "is_fork", "is_archived", "visibility", "readme_relevance_score", 
        "deep_relevance_score", "deep_relevance_error"
    ]
    
    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for repo in repositories:
            writer.writerow([
                repo.id,
                repo.full_name,
                repo.clone_url,
                repo.html_url,
                repo.description,
                repo.stargazers_count,
                repo.language,
                json.dumps(repo.topics, ensure_ascii=False) if repo.topics else "",
                repo.default_branch,
                repo.created_at,
                repo.updated_at,
                repo.pushed_at,
                repo.forks_count,
                repo.open_issues_count,
                repo.watchers_count,
                repo.size_kb,
                repo.license_spdx_id,
                repo.is_fork,
                repo.is_archived,
                repo.visibility,
                repo.readme_relevance_score,
                repo.deep_relevance_score,
                repo.deep_relevance_error
            ])
            
    return csv_file
