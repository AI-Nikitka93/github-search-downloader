from __future__ import annotations

import sys
import contextlib
import io
import unittest
from dataclasses import replace
from datetime import date
import json
import re
import sqlite3
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import github_harvester.service as service
from app import (
    load_config_file_defaults,
    main as cli_main,
    parse_args as parse_cli_args,
    resolve_ai_api_key,
    resolve_github_token,
)
from github_harvester.ai_planner import AiProviderConfig
from github_harvester.downloader import CloneResult
from github_harvester.exporters import export_repositories_to_sqlite
from github_harvester.github_api import GitHubApiError
from github_harvester.models import Repo
from github_harvester.run_state import (
    collect_repository_ids_from_metadata,
    filter_repositories_for_resume,
    initialize_run_state,
    record_clone_result,
)
from github_harvester.service import (
    apply_deep_relevance_scoring,
    apply_max_age_filter,
    build_softened_search_options,
    build_query_recovery_candidate,
    build_relaxed_query_from_strict,
    build_review_pool,
    extract_query_terms_for_ai_filter,
    filter_repositories_by_keywords,
    load_repositories_from_metadata,
    normalize_query_for_search,
    normalize_ai_filter_decision,
    normalize_log_text,
    parse_iso_date,
    parse_keyword_list,
    pick_evenly_by_index,
    query_has_search_terms,
    redact_sensitive_text,
    repo_text_relevance_score,
    run_download_for_repositories,
    score_code_path_relevance,
    score_deep_relevance_snapshot,
    score_readme_relevance,
    should_retry_with_relaxed_query,
    should_expand_query_for_low_results,
    split_into_batches,
    validate_run_config,
    RunConfig,
)


class TestService(unittest.TestCase):
    def test_parse_iso_date_valid(self) -> None:
        parsed = parse_iso_date("2026-02-11", "field")
        self.assertEqual(parsed.isoformat(), "2026-02-11")

    def test_parse_iso_date_invalid(self) -> None:
        with self.assertRaises(ValueError):
            parse_iso_date("11-02-2026", "field")

    def test_normalize_query_for_search_plain_text(self) -> None:
        query, note = normalize_query_for_search("OSINT AI analysis")
        self.assertEqual(query, "(OSINT OR AI OR analysis)")
        self.assertTrue(note)

    def test_normalize_query_for_search_keeps_advanced(self) -> None:
        raw = '(osint OR ai) language:python stars:>=10'
        query, note = normalize_query_for_search(raw)
        self.assertEqual(query, raw)
        self.assertIsNone(note)

    def test_normalize_query_for_search_relaxes_overloaded_boolean_query(self) -> None:
        raw = (
            "AI agent automation OR task automation OR workflow automation "
            "NOT tutorial NOT example NOT list NOT collection "
            "language:python language:typescript"
        )
        query, note = normalize_query_for_search(raw)
        self.assertNotEqual(query, raw)
        self.assertTrue(note)
        self.assertLessEqual(len(re.findall(r"\b(?:AND|OR|NOT)\b", query, flags=re.IGNORECASE)), 5)
        self.assertNotIn("tutorial", query.lower())
        self.assertNotIn("example", query.lower())

    def test_normalize_query_for_search_relaxes_operator_only_qualifier_query(self) -> None:
        raw = "topic:AI-agent OR topic:automation language:python created:>=2024-01-01 stars:>=100"
        normalized, note = normalize_query_for_search(raw)
        self.assertNotEqual(normalized, raw)
        self.assertTrue(note)
        self.assertIn("ai", normalized.lower())
        self.assertIn("automation", normalized.lower())
        self.assertTrue(query_has_search_terms(normalized))

    def test_build_relaxed_query_from_strict(self) -> None:
        raw = "topic:osint topic:ai-analysis created:>=2023-01-01"
        relaxed = build_relaxed_query_from_strict(raw)
        self.assertIsNotNone(relaxed)
        assert relaxed is not None
        self.assertIn("osint", relaxed)
        self.assertIn("ai", relaxed)
        self.assertIn("analysis", relaxed)

    def test_build_relaxed_query_from_strict_returns_none_for_simple_query(self) -> None:
        self.assertIsNone(build_relaxed_query_from_strict("osint"))

    def test_build_query_recovery_candidate(self) -> None:
        query = "topic:AI-agent OR topic:automation language:python stars:>=100"
        candidate = build_query_recovery_candidate(query)
        self.assertIsNotNone(candidate)
        assert candidate is not None
        self.assertIn("ai", candidate.lower())
        self.assertIn("automation", candidate.lower())

    def test_should_retry_with_relaxed_query(self) -> None:
        self.assertTrue(should_retry_with_relaxed_query("Ошибка GitHub API 422: Validation Failed"))
        self.assertFalse(should_retry_with_relaxed_query("Ошибка GitHub API 500"))

    def test_load_repositories_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = Path(tmp_dir) / "search_test.json"
            metadata_path.write_text(
                """
{
  "query": "ai agents",
  "repositories": [
    {
      "id": 1,
      "full_name": "team/agent-tool",
      "clone_url": "https://github.com/team/agent-tool.git",
      "html_url": "https://github.com/team/agent-tool",
      "description": "Agent toolkit",
      "stargazers_count": 42,
      "language": "Python",
      "topics": ["ai", "agent"],
      "default_branch": "main",
      "created_at": "2025-01-01T00:00:00Z",
      "updated_at": "2026-01-01T00:00:00Z",
      "pushed_at": "2026-01-02T00:00:00Z"
    }
  ]
}
                """.strip(),
                encoding="utf-8",
            )
            query, repositories = load_repositories_from_metadata(metadata_path)
            self.assertEqual(query, "ai agents")
            self.assertEqual(len(repositories), 1)
            self.assertEqual(repositories[0].full_name, "team/agent-tool")

    def test_run_download_for_repositories_empty_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            config = RunConfig(query="ai agents", output_root=output_root, max_repos=10)
            summary = run_download_for_repositories(config=config, repositories=[])
            self.assertEqual(summary.found_count, 0)
            self.assertEqual(summary.cloned_count, 0)
            self.assertEqual(summary.failed_count, 0)
            self.assertTrue(summary.metadata_file.exists())
            self.assertTrue(summary.run_log_file.exists())

    def test_run_download_for_repositories_dry_run_does_not_clone(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            repo = Repo(
                id=1,
                full_name="team/dry-run",
                clone_url="https://example.com/team/dry-run.git",
                html_url="https://example.com/team/dry-run",
                description="",
                stargazers_count=1,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            )
            config = RunConfig(query="ai agents", output_root=output_root, dry_run=True)
            summary = run_download_for_repositories(config=config, repositories=[repo])
            self.assertEqual(summary.found_count, 1)
            self.assertEqual(summary.cloned_count, 0)
            self.assertFalse(summary.run_state_file)
            self.assertFalse((output_root / "repos").exists())

    def test_run_download_retry_updates_run_state_to_final_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            repo = Repo(
                id=1,
                full_name="team/retry-ok",
                clone_url="https://example.com/team/retry-ok.git",
                html_url="https://example.com/team/retry-ok",
                description="",
                stargazers_count=1,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            )
            config = RunConfig(
                query="ai agents",
                output_root=output_root,
                clone_depth=0,
                clone_partial=False,
                clone_single_branch=False,
                clone_no_tags=False,
                retry_failed_clones=1,
                retry_delay_seconds=0,
            )
            original_download = service.download_repositories
            original_ensure_git = service.ensure_git_available
            call_count = 0

            def fake_download(
                repositories,
                output_root,
                workers,
                clone_timeout,
                skip_existing,
                progress_callback=None,
                log_callback=None,
                cancel_event=None,
                clone_options=None,
            ):
                nonlocal call_count
                del workers, clone_timeout, skip_existing, log_callback, cancel_event
                self.assertIsNotNone(clone_options)
                assert clone_options is not None
                self.assertEqual(clone_options.depth, 0)
                self.assertFalse(clone_options.partial_clone)
                self.assertFalse(clone_options.single_branch)
                self.assertFalse(clone_options.no_tags)
                call_count += 1
                status = "failed" if call_count == 1 else "cloned"
                result = CloneResult(
                    repo_full_name=repositories[0].full_name,
                    target_path=output_root / "team" / "retry-ok",
                    status=status,
                    message="temporary network error" if status == "failed" else "OK",
                )
                if progress_callback:
                    progress_callback(1, len(repositories), result)
                return [result]

            service.download_repositories = fake_download
            service.ensure_git_available = lambda: None
            try:
                summary = run_download_for_repositories(config=config, repositories=[repo])
            finally:
                service.download_repositories = original_download
                service.ensure_git_available = original_ensure_git

            self.assertEqual(summary.cloned_count, 1)
            self.assertIsNotNone(summary.run_state_file)
            assert summary.run_state_file is not None
            state = json.loads(summary.run_state_file.read_text(encoding="utf-8"))
            self.assertEqual(state["results"]["team/retry-ok"]["status"], "cloned")

    def test_run_collection_recovers_after_github_422(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            config = RunConfig(
                query="ai",
                output_root=output_root,
                dry_run=True,
                max_repos=0,
            )
            calls: list[str] = []
            original_collect = service.collect_repositories
            original_recovery_builder = service.build_query_recovery_candidate

            def fake_collect(*, client, options, max_repositories, use_date_sharding, log, should_cancel):
                del client, max_repositories, use_date_sharding, log, should_cancel
                calls.append(options.query)
                if len(calls) == 1:
                    raise GitHubApiError(
                        "Ошибка GitHub API 422: Validation Failed: The search contains only logical operators."
                    )
                return [
                    Repo(
                        id=1,
                        full_name="team/ai-agent-demo",
                        clone_url="https://example.com/team/ai-agent-demo",
                        html_url="https://example.com/team/ai-agent-demo",
                        description="AI agent automation toolkit",
                        stargazers_count=120,
                        language="Python",
                        topics=["ai", "automation"],
                        default_branch="main",
                        created_at="2025-01-01T00:00:00Z",
                        updated_at="2026-01-01T00:00:00Z",
                        pushed_at="2026-01-01T00:00:00Z",
                    )
                ]

            service.collect_repositories = fake_collect
            service.build_query_recovery_candidate = lambda _query: "(ai OR automation OR toolkit)"
            try:
                summary = service.run_collection(config=config, log=lambda _msg: None)
            finally:
                service.collect_repositories = original_collect
                service.build_query_recovery_candidate = original_recovery_builder

            self.assertEqual(summary.found_count, 1)
            self.assertEqual(len(calls), 2)
            self.assertNotEqual(calls[0], calls[1])

    def test_should_expand_query_for_low_results(self) -> None:
        self.assertTrue(
            should_expand_query_for_low_results(
                query="ai automation OR workflow language:python",
                found_count=2,
                requested_max_repos=400,
            )
        )
        self.assertFalse(
            should_expand_query_for_low_results(
                query="ai automation",
                found_count=2,
                requested_max_repos=400,
            )
        )
        self.assertFalse(
            should_expand_query_for_low_results(
                query="ai automation OR workflow language:python",
                found_count=80,
                requested_max_repos=400,
            )
        )

    def test_validate_run_config_rejects_invalid_sort(self) -> None:
        config = RunConfig(query="osint", output_root=Path("M:/Projects/GithubSearch/tmp"), sort="invalid")
        with self.assertRaises(ValueError):
            validate_run_config(config)

    def test_redact_sensitive_text(self) -> None:
        raw = "token=ghp_secret_value Authorization: Bearer abc123 https://user:pass@example.com"
        redacted = redact_sensitive_text(raw)
        self.assertNotIn("ghp_secret_value", redacted)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("user:pass", redacted)

    def test_redact_sensitive_text_masks_bare_github_tokens(self) -> None:
        classic = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"
        fine_grained = "github_pat_11AABBCC0_abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        raw = (
            f"clone failed for {classic}; "
            f"fine token {fine_grained}; "
            f"retry url=https://{fine_grained}@github.com/example/private.git"
        )
        redacted = redact_sensitive_text(raw)
        self.assertNotIn(classic, redacted)
        self.assertNotIn(fine_grained, redacted)
        self.assertIn("ghp_***", redacted)
        self.assertIn("github_pat_***", redacted)
        self.assertIn("https://***@github.com/example/private.git", redacted)

    def test_normalize_log_text_collapses_multiline(self) -> None:
        raw = "line1\nline2\rline3\u2028line4"
        normalized = normalize_log_text(raw)
        self.assertEqual(normalized, "line1 | line2 | line3 | line4")

    def test_apply_max_age_filter(self) -> None:
        result = apply_max_age_filter(date(2008, 1, 1), max_age_years=3, today=date(2026, 2, 11))
        self.assertEqual(result, date(2023, 2, 12))

    def test_split_into_batches(self) -> None:
        repos = [
            Repo(
                id=index,
                full_name=f"owner/repo{index}",
                clone_url="https://example.com/owner/repo",
                html_url="https://example.com/owner/repo",
                description="",
                stargazers_count=0,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            )
            for index in range(1, 8)
        ]
        batches = split_into_batches(repos, batch_size=3)
        self.assertEqual(len(batches), 3)
        self.assertEqual(len(batches[0]), 3)
        self.assertEqual(len(batches[1]), 3)
        self.assertEqual(len(batches[2]), 1)

    def test_parse_keyword_list(self) -> None:
        parsed = parse_keyword_list("osint, AI;security\nosint")
        self.assertEqual(parsed, ("osint", "ai", "security"))

    def test_filter_repositories_by_keywords(self) -> None:
        repos = [
            Repo(
                id=1,
                full_name="team/osint-ai-toolkit",
                clone_url="https://example.com/team/osint-ai-toolkit.git",
                html_url="https://example.com/team/osint-ai-toolkit",
                description="Security automation",
                stargazers_count=1,
                language="Python",
                topics=["osint"],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
            Repo(
                id=2,
                full_name="team/weather-demo",
                clone_url="https://example.com/team/weather-demo.git",
                html_url="https://example.com/team/weather-demo",
                description="Tutorial example",
                stargazers_count=1,
                language="Python",
                topics=["weather"],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
        ]
        filtered, include_dropped, exclude_dropped = filter_repositories_by_keywords(
            repos,
            include_keywords=("osint", "security"),
            exclude_keywords=("tutorial",),
        )
        self.assertEqual([repo.id for repo in filtered], [1])
        self.assertEqual(include_dropped, 1)
        self.assertEqual(exclude_dropped, 0)

    def test_extract_query_terms_for_ai_filter(self) -> None:
        terms = extract_query_terms_for_ai_filter("(osint OR ai OR analysis) language:python stars:>=5")
        self.assertIn("osint", terms)
        self.assertIn("ai", terms)
        self.assertIn("analysis", terms)
        self.assertNotIn("or", terms)
        self.assertNotIn("language", terms)

    def test_extract_query_terms_for_ai_filter_cyrillic(self) -> None:
        terms = extract_query_terms_for_ai_filter("osint анализ люди поиск")
        self.assertIn("анализ", terms)
        self.assertIn("поиск", terms)

    def test_pick_evenly_by_index(self) -> None:
        repos = [
            (
                float(index),
                Repo(
                    id=index,
                    full_name=f"owner/repo{index}",
                    clone_url="https://example.com/owner/repo",
                    html_url="https://example.com/owner/repo",
                    description="",
                    stargazers_count=0,
                    language="Python",
                    topics=[],
                    default_branch="main",
                    created_at="",
                    updated_at="",
                    pushed_at="",
                ),
            )
            for index in range(1, 21)
        ]
        sampled = pick_evenly_by_index(repos, 5)
        self.assertEqual(len(sampled), 5)
        sampled_ids = [repo.id for _score, repo in sampled]
        self.assertIn(1, sampled_ids)
        self.assertIn(20, sampled_ids)

    def test_build_review_pool_has_exploration(self) -> None:
        scored = [
            (
                1.0 - (index / 1000.0),
                Repo(
                    id=index,
                    full_name=f"owner/repo{index}",
                    clone_url="https://example.com/owner/repo",
                    html_url="https://example.com/owner/repo",
                    description="",
                    stargazers_count=1000 - index,
                    language="Python",
                    topics=[],
                    default_branch="main",
                    created_at="",
                    updated_at="",
                    pushed_at="",
                ),
            )
            for index in range(1, 121)
        ]
        pool = build_review_pool(scored, review_count=60, exploration_ratio=0.25)
        self.assertEqual(len(pool), 60)
        ids = [repo.id for _score, repo in pool]
        self.assertTrue(any(repo_id > 45 for repo_id in ids))

    def test_repo_text_relevance_score(self) -> None:
        repo = Repo(
            id=1,
            full_name="team/osint-ai-toolkit",
            clone_url="https://example.com/team/osint-ai-toolkit",
            html_url="https://example.com/team/osint-ai-toolkit",
            description="AI toolkit for OSINT analysis",
            stargazers_count=42,
            language="Python",
            topics=["osint", "ai", "investigation"],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        score = repo_text_relevance_score(repo, ["osint", "analysis", "ai"])
        self.assertGreater(score, 0.5)

    def test_deep_relevance_scores_readme_and_code_paths(self) -> None:
        query_terms = ["osint", "ai", "automation"]
        readme_score = score_readme_relevance(
            "# OSINT AI Automation\n\n"
            "Production toolkit for OSINT automation, AI triage, and investigation workflows.",
            query_terms,
        )
        code_score = score_code_path_relevance(
            [
                "src/osint_ai/automation_agent.py",
                "src/osint_ai/github_client.py",
                "tests/test_automation_agent.py",
                "docs/usage.md",
            ],
            query_terms,
            tree_truncated=False,
        )
        weak_score = score_deep_relevance_snapshot(
            "Weather dashboard with chart widgets.",
            ["src/weather/app.py", "README.md"],
            query_terms,
            tree_truncated=False,
        )

        self.assertGreater(readme_score, 0.7)
        self.assertGreater(code_score, 0.5)
        self.assertGreater(score_deep_relevance_snapshot(
            "OSINT AI automation toolkit.",
            ["src/osint_ai/automation_agent.py"],
            query_terms,
            tree_truncated=False,
        ), weak_score)

    def test_apply_deep_relevance_scoring_sorts_marks_and_preserves_errors(self) -> None:
        good = Repo(
            id=1,
            full_name="team/osint-ai-toolkit",
            clone_url="https://github.com/team/osint-ai-toolkit.git",
            html_url="https://github.com/team/osint-ai-toolkit",
            description="",
            stargazers_count=10,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        failing = Repo(
            id=2,
            full_name="team/api-error",
            clone_url="https://github.com/team/api-error.git",
            html_url="https://github.com/team/api-error",
            description="",
            stargazers_count=100,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )

        class FakeClient:
            def get_repository_readme_text(self, repo: Repo) -> str:
                if repo.id == 2:
                    raise GitHubApiError("README unavailable")
                return "OSINT AI automation platform with production collectors."

            def get_repository_tree_paths(self, repo: Repo) -> tuple[list[str], bool]:
                if repo.id == 2:
                    raise GitHubApiError("tree unavailable")
                return ["src/osint_ai/automation_agent.py", "tests/test_osint_ai.py"], False

        config = RunConfig(
            query="osint ai automation",
            output_root=Path("M:/Projects/GithubSearch/tmp"),
            deep_relevance_enabled=True,
            deep_relevance_max_repos=10,
        )
        scored = apply_deep_relevance_scoring(
            config=config,
            client=FakeClient(),
            repositories=[failing, good],
            query="osint ai automation",
            log=lambda _msg: None,
            should_cancel=lambda: False,
        )

        self.assertEqual([repo.full_name for repo in scored], ["team/osint-ai-toolkit", "team/api-error"])
        self.assertTrue(scored[0].deep_relevance_checked)
        self.assertGreater(scored[0].deep_relevance_score, 0.6)
        self.assertTrue(scored[1].deep_relevance_checked)
        self.assertIn("README unavailable", scored[1].deep_relevance_error)
        self.assertIn("tree unavailable", scored[1].deep_relevance_error)

    def test_normalize_ai_filter_decision(self) -> None:
        keep, score, _reason = normalize_ai_filter_decision(
            {"relevant": True, "score": 0.78, "reason": "match"}, min_score=0.55
        )
        self.assertTrue(keep)
        self.assertAlmostEqual(score, 0.78)

        keep2, score2, _reason2 = normalize_ai_filter_decision(
            {"score": 0.4, "reason": "weak"}, min_score=0.55
        )
        self.assertFalse(keep2)
        self.assertAlmostEqual(score2, 0.4)

    def test_filter_repositories_with_ai(self) -> None:
        repos = [
            Repo(
                id=1,
                full_name="team/osint-ai-toolkit",
                clone_url="https://example.com/team/osint-ai-toolkit",
                html_url="https://example.com/team/osint-ai-toolkit",
                description="AI toolkit for OSINT analysis",
                stargazers_count=42,
                language="Python",
                topics=["osint", "ai"],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
            Repo(
                id=2,
                full_name="team/random-weather-app",
                clone_url="https://example.com/team/random-weather-app",
                html_url="https://example.com/team/random-weather-app",
                description="simple weather widget",
                stargazers_count=5,
                language="Python",
                topics=["weather"],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
        ]
        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=10)
        original_request = service.request_ai

        def fake_request(_provider: AiProviderConfig, prompt: str) -> str:
            if "osint-ai-toolkit" in prompt:
                return '{"relevant": true, "score": 0.9, "reason": "match"}'
            return '{"relevant": false, "score": 0.1, "reason": "off-topic"}'

        service.request_ai = fake_request
        try:
            filtered = service.filter_repositories_with_ai(
                repositories=repos,
                query="osint ai analysis",
                provider=provider,
                min_score=0.55,
                max_reviews=10,
                log=lambda _msg: None,
                should_cancel=lambda: False,
            )
        finally:
            service.request_ai = original_request

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].full_name, "team/osint-ai-toolkit")

    def test_filter_repositories_with_ai_limits_model_calls(self) -> None:
        repos = []
        for idx in range(1, 51):
            repos.append(
                Repo(
                    id=idx,
                    full_name=f"team/osint-tool-{idx}",
                    clone_url=f"https://example.com/team/osint-tool-{idx}",
                    html_url=f"https://example.com/team/osint-tool-{idx}",
                    description="OSINT AI utilities",
                    stargazers_count=50 - idx,
                    language="Python",
                    topics=["osint", "ai"],
                    default_branch="main",
                    created_at="",
                    updated_at="",
                    pushed_at="",
                )
            )

        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=1)
        original_request = service.request_ai
        calls: list[str] = []

        def fake_request(_provider: AiProviderConfig, prompt: str) -> str:
            calls.append(prompt)
            return '{"relevant": true, "score": 0.7, "reason": "ok"}'

        service.request_ai = fake_request
        try:
            filtered = service.filter_repositories_with_ai(
                repositories=repos,
                query="osint ai toolkit",
                provider=provider,
                min_score=0.55,
                max_reviews=50,
                log=lambda _msg: None,
                should_cancel=lambda: False,
            )
        finally:
            service.request_ai = original_request

        self.assertTrue(filtered)
        self.assertLessEqual(len(calls), 50)

    def test_filter_repositories_with_ai_not_capped_to_40_when_desired_keep_is_higher(self) -> None:
        repos = []
        for idx in range(1, 301):
            repos.append(
                Repo(
                    id=idx,
                    full_name=f"team/osint-ai-tool-{idx}",
                    clone_url=f"https://example.com/team/osint-ai-tool-{idx}",
                    html_url=f"https://example.com/team/osint-ai-tool-{idx}",
                    description="OSINT AI analysis toolkit for intelligence workflows",
                    stargazers_count=1000 - idx,
                    language="Python",
                    topics=["osint", "ai", "analysis"],
                    default_branch="main",
                    created_at="2025-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                    pushed_at="2026-01-01T00:00:00Z",
                )
            )

        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=1)
        original_request = service.request_ai

        def fake_request(_provider: AiProviderConfig, _prompt: str) -> str:
            return '{"relevant": true, "score": 0.7, "reason": "ok"}'

        service.request_ai = fake_request
        try:
            filtered = service.filter_repositories_with_ai(
                repositories=repos,
                query="osint ai analysis",
                provider=provider,
                min_score=0.55,
                max_reviews=30,
                log=lambda _msg: None,
                should_cancel=lambda: False,
                desired_keep_count=100,
            )
        finally:
            service.request_ai = original_request

        self.assertGreaterEqual(len(filtered), 100)

    def test_filter_repositories_with_ai_empty_terms_fallback(self) -> None:
        repos = [
            Repo(
                id=1,
                full_name="team/repo-low",
                clone_url="https://example.com/team/repo-low",
                html_url="https://example.com/team/repo-low",
                description="",
                stargazers_count=5,
                language="",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
            Repo(
                id=2,
                full_name="team/repo-high",
                clone_url="https://example.com/team/repo-high",
                html_url="https://example.com/team/repo-high",
                description="",
                stargazers_count=50,
                language="",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
            ),
        ]
        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=1)
        filtered = service.filter_repositories_with_ai(
            repositories=repos,
            query="***",
            provider=provider,
            min_score=0.55,
            max_reviews=10,
            log=lambda _msg: None,
            should_cancel=lambda: False,
        )
        self.assertEqual(filtered[0].id, 2)

    def test_run_state_resume_filters_completed_repositories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "run_state.json"
            metadata_path = Path(tmp_dir) / "search.json"
            repos = [
                Repo(
                    id=1,
                    full_name="team/done",
                    clone_url="https://example.com/team/done.git",
                    html_url="https://example.com/team/done",
                    description="",
                    stargazers_count=1,
                    language="Python",
                    topics=[],
                    default_branch="main",
                    created_at="",
                    updated_at="",
                    pushed_at="",
                ),
                Repo(
                    id=2,
                    full_name="team/pending",
                    clone_url="https://example.com/team/pending.git",
                    html_url="https://example.com/team/pending",
                    description="",
                    stargazers_count=1,
                    language="Python",
                    topics=[],
                    default_branch="main",
                    created_at="",
                    updated_at="",
                    pushed_at="",
                ),
            ]
            initialize_run_state(state_path, "ai", metadata_path, repos, mode="test")
            record_clone_result(
                state_path,
                CloneResult(
                    repo_full_name="team/done",
                    target_path=Path(tmp_dir) / "repos" / "team" / "done",
                    status="cloned",
                    message="OK",
                ),
            )
            remaining, skipped = filter_repositories_for_resume(repos, state_path)
            self.assertEqual(skipped, 1)
            self.assertEqual([repo.full_name for repo in remaining], ["team/pending"])

    def test_collect_repository_ids_from_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_dir = Path(tmp_dir)
            (metadata_dir / "search_one.json").write_text(
                json.dumps({"repositories": [{"id": 10}, {"id": 20}]}),
                encoding="utf-8",
            )
            seen = collect_repository_ids_from_metadata(metadata_dir)
            self.assertEqual(seen, {10, 20})

    def test_export_repositories_to_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sqlite_path = Path(tmp_dir) / "repos.sqlite"
            metadata_path = Path(tmp_dir) / "metadata" / "search_20260602_010203.json"
            repo = Repo(
                id=42,
                full_name="team/osint-ai-toolkit",
                clone_url="https://example.com/team/osint-ai-toolkit.git",
                html_url="https://example.com/team/osint-ai-toolkit",
                description="Security automation",
                stargazers_count=12,
                language="Python",
                topics=["osint", "ai"],
                default_branch="main",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                pushed_at="2026-01-02T00:00:00Z",
                forks_count=4,
                open_issues_count=2,
                watchers_count=15,
                size_kb=512,
                license_spdx_id="Apache-2.0",
                is_fork=False,
                is_archived=False,
                visibility="public",
                node_id="R_kgDOExample",
                homepage_url="https://example.com",
                default_branch_oid="abc123",
                default_branch_committed_at="2026-01-02T00:00:00Z",
                latest_release_tag="v1.2.3",
                latest_release_published_at="2026-01-03T00:00:00Z",
                is_mirror=True,
                is_empty=False,
                graphql_enriched=True,
                readme_relevance_score=0.72,
                code_relevance_score=0.64,
                deep_relevance_score=0.70,
                deep_relevance_checked=True,
                deep_relevance_error="",
            )
            export_repositories_to_sqlite(sqlite_path, "osint ai", [repo], metadata_path)
            connection = sqlite3.connect(sqlite_path)
            try:
                row = connection.execute(
                    """
                    SELECT full_name, language, stargazers_count, forks_count, open_issues_count,
                           watchers_count, size_kb, license_spdx_id, is_fork, is_archived, visibility,
                           node_id, homepage_url, default_branch_oid, default_branch_committed_at,
                           latest_release_tag, latest_release_published_at, is_mirror, is_empty,
                           graphql_enriched, readme_relevance_score, code_relevance_score,
                           deep_relevance_score, deep_relevance_checked, deep_relevance_error
                    FROM repositories WHERE id = 42
                    """
                ).fetchone()
                run_row = connection.execute("SELECT repo_count FROM runs").fetchone()
            finally:
                connection.close()
            self.assertEqual(
                row,
                (
                    "team/osint-ai-toolkit",
                    "Python",
                    12,
                    4,
                    2,
                    15,
                    512,
                    "Apache-2.0",
                    0,
                    0,
                    "public",
                    "R_kgDOExample",
                    "https://example.com",
                    "abc123",
                    "2026-01-02T00:00:00Z",
                    "v1.2.3",
                    "2026-01-03T00:00:00Z",
                    1,
                    0,
                    1,
                    0.72,
                    0.64,
                    0.70,
                    1,
                    "",
                ),
            )
            self.assertEqual(run_row, (1,))

    def test_export_repositories_to_sqlite_migrates_existing_repository_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            sqlite_path = Path(tmp_dir) / "repos.sqlite"
            metadata_path = Path(tmp_dir) / "metadata" / "search_20260602_010203.json"
            connection = sqlite3.connect(sqlite_path)
            try:
                connection.executescript(
                    """
                    CREATE TABLE repositories (
                        id INTEGER PRIMARY KEY,
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
                        last_seen_run TEXT NOT NULL
                    );
                    """
                )
                connection.commit()
            finally:
                connection.close()

            repo = Repo(
                id=43,
                full_name="team/migrated",
                clone_url="https://example.com/team/migrated.git",
                html_url="https://example.com/team/migrated",
                description="Migrated schema",
                stargazers_count=3,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="",
                updated_at="",
                pushed_at="",
                forks_count=9,
                license_spdx_id="MIT",
            )
            export_repositories_to_sqlite(sqlite_path, "migrate", [repo], metadata_path)
            connection = sqlite3.connect(sqlite_path)
            try:
                row = connection.execute(
                    """
                    SELECT forks_count, license_spdx_id, graphql_enriched,
                           readme_relevance_score, code_relevance_score,
                           deep_relevance_score, deep_relevance_checked, deep_relevance_error
                    FROM repositories WHERE id = 43
                    """
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(row, (9, "MIT", 0, 0.0, 0.0, 0.0, 0, ""))

    def test_filter_repositories_with_ai_model_failure_fallback(self) -> None:
        repos = [
            Repo(
                id=1,
                full_name="team/osint-ai-toolkit",
                clone_url="https://example.com/team/osint-ai-toolkit",
                html_url="https://example.com/team/osint-ai-toolkit",
                description="OSINT AI toolkit for investigations",
                stargazers_count=250,
                language="Python",
                topics=["osint", "ai"],
                default_branch="main",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2026-01-10T00:00:00Z",
                pushed_at="2026-01-10T00:00:00Z",
            ),
            Repo(
                id=2,
                full_name="team/random-weather",
                clone_url="https://example.com/team/random-weather",
                html_url="https://example.com/team/random-weather",
                description="Weather dashboard",
                stargazers_count=10,
                language="Python",
                topics=["weather"],
                default_branch="main",
                created_at="2021-01-01T00:00:00Z",
                updated_at="2021-01-02T00:00:00Z",
                pushed_at="2021-01-02T00:00:00Z",
            ),
        ]
        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=1)
        original_request = service.request_ai

        def failing_request(_provider: AiProviderConfig, _prompt: str) -> str:
            raise RuntimeError("model unavailable")

        service.request_ai = failing_request
        try:
            filtered = service.filter_repositories_with_ai(
                repositories=repos,
                query="osint ai",
                provider=provider,
                min_score=0.55,
                max_reviews=10,
                log=lambda _msg: None,
                should_cancel=lambda: False,
            )
        finally:
            service.request_ai = original_request

        self.assertTrue(filtered)
        self.assertEqual(filtered[0].id, 1)

    def test_build_softened_search_options(self) -> None:
        options = service.SearchOptions(
            query="ai agents",
            min_stars=120,
            language="Python",
            include_forks=False,
            include_archived=False,
            created_after=date(2024, 1, 1),
            created_before=date(2026, 2, 12),
            sort="stars",
            order="desc",
        )
        softened, note = build_softened_search_options(options)
        self.assertIsNotNone(softened)
        self.assertTrue(note)
        assert softened is not None
        self.assertLess(softened.min_stars, options.min_stars)
        self.assertEqual(softened.language, "")

    def test_run_collection_expands_low_result_pool_before_ai_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            config = RunConfig(
                query="ai agents automation",
                output_root=output_root,
                min_stars=120,
                language="Python",
                max_repos=300,
                dry_run=True,
                ai_filter_enabled=True,
                ai_filter_endpoint="http://127.0.0.1:11434",
                ai_filter_model="dummy",
                ai_filter_max_reviews=50,
            )
            calls: list[tuple[int, str]] = []
            original_collect = service.collect_repositories
            original_filter = service.filter_repositories_with_ai

            def fake_collect(*, client, options, max_repositories, use_date_sharding, log, should_cancel):
                del client, max_repositories, use_date_sharding, log, should_cancel
                calls.append((options.min_stars, options.language))
                base_repo = Repo(
                    id=1,
                    full_name="team/ai-agent-one",
                    clone_url="https://example.com/team/ai-agent-one.git",
                    html_url="https://example.com/team/ai-agent-one",
                    description="AI agent automation toolkit",
                    stargazers_count=250,
                    language="Python",
                    topics=["ai", "agent"],
                    default_branch="main",
                    created_at="2025-01-01T00:00:00Z",
                    updated_at="2026-01-01T00:00:00Z",
                    pushed_at="2026-01-01T00:00:00Z",
                )
                if len(calls) == 1:
                    return [base_repo]
                return [
                    base_repo,
                    Repo(
                        id=2,
                        full_name="team/automation-two",
                        clone_url="https://example.com/team/automation-two.git",
                        html_url="https://example.com/team/automation-two",
                        description="Automation framework",
                        stargazers_count=180,
                        language="TypeScript",
                        topics=["automation"],
                        default_branch="main",
                        created_at="2025-01-01T00:00:00Z",
                        updated_at="2026-01-01T00:00:00Z",
                        pushed_at="2026-01-01T00:00:00Z",
                    ),
                    Repo(
                        id=3,
                        full_name="team/ai-three",
                        clone_url="https://example.com/team/ai-three.git",
                        html_url="https://example.com/team/ai-three",
                        description="AI tool",
                        stargazers_count=170,
                        language="Go",
                        topics=["ai"],
                        default_branch="main",
                        created_at="2025-01-01T00:00:00Z",
                        updated_at="2026-01-01T00:00:00Z",
                        pushed_at="2026-01-01T00:00:00Z",
                    ),
                ]

            def fake_filter(**kwargs):
                return list(kwargs["repositories"])

            service.collect_repositories = fake_collect
            service.filter_repositories_with_ai = fake_filter
            try:
                summary = service.run_collection(config=config, log=lambda _msg: None)
            finally:
                service.collect_repositories = original_collect
                service.filter_repositories_with_ai = original_filter

            self.assertGreaterEqual(len(calls), 2)
            self.assertEqual(calls[0][1], "Python")
            self.assertEqual(calls[1][1], "")
            self.assertLess(calls[1][0], calls[0][0])
            self.assertEqual(summary.found_count, 3)

    def test_run_collection_incremental_skips_previous_metadata_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            metadata_dir = output_root / "metadata"
            metadata_dir.mkdir(parents=True)
            (metadata_dir / "search_previous.json").write_text(
                json.dumps({"repositories": [{"id": 1}]}),
                encoding="utf-8",
            )
            config = RunConfig(
                query="ai agents",
                output_root=output_root,
                dry_run=True,
                incremental=True,
            )
            original_collect = service.collect_repositories

            def fake_collect(*, client, options, max_repositories, use_date_sharding, log, should_cancel):
                del client, options, max_repositories, use_date_sharding, log, should_cancel
                return [
                    Repo(
                        id=1,
                        full_name="team/seen",
                        clone_url="https://example.com/team/seen.git",
                        html_url="https://example.com/team/seen",
                        description="Already seen",
                        stargazers_count=1,
                        language="Python",
                        topics=[],
                        default_branch="main",
                        created_at="",
                        updated_at="",
                        pushed_at="",
                    ),
                    Repo(
                        id=2,
                        full_name="team/new",
                        clone_url="https://example.com/team/new.git",
                        html_url="https://example.com/team/new",
                        description="New repo",
                        stargazers_count=1,
                        language="Python",
                        topics=[],
                        default_branch="main",
                        created_at="",
                        updated_at="",
                        pushed_at="",
                    ),
                ]

            service.collect_repositories = fake_collect
            try:
                summary = service.run_collection(config=config, log=lambda _msg: None)
            finally:
                service.collect_repositories = original_collect

            self.assertEqual(summary.found_count, 1)
            _query, repos = load_repositories_from_metadata(summary.metadata_file)
            self.assertEqual([repo.full_name for repo in repos], ["team/new"])

    def test_run_collection_graphql_enriches_final_repositories_before_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            base_repo = Repo(
                id=1,
                node_id="R_kgDOExample",
                full_name="team/enrich-me",
                clone_url="https://github.com/team/enrich-me.git",
                html_url="https://github.com/team/enrich-me",
                description="Needs enrichment",
                stargazers_count=1,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                pushed_at="2026-01-02T00:00:00Z",
            )
            enriched_repo = Repo(
                id=1,
                node_id="R_kgDOExample",
                full_name="team/enrich-me",
                clone_url="https://github.com/team/enrich-me.git",
                html_url="https://github.com/team/enrich-me",
                description="Needs enrichment",
                stargazers_count=1,
                language="Python",
                topics=["ai"],
                default_branch="main",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                pushed_at="2026-01-02T00:00:00Z",
                homepage_url="https://example.com",
                graphql_enriched=True,
            )
            config = RunConfig(
                query="ai agents",
                output_root=output_root,
                token="ghp_token",
                dry_run=True,
                graphql_enrich=True,
                graphql_batch_size=25,
            )
            original_collect = service.collect_repositories
            original_enrich = service.enrich_repositories_with_graphql
            captured_batch_sizes: list[int] = []

            def fake_collect(*, client, options, max_repositories, use_date_sharding, log, should_cancel):
                del client, options, max_repositories, use_date_sharding, log, should_cancel
                return [base_repo]

            def fake_enrich(client, repositories, batch_size, log=None, should_cancel=None):
                del client, log, should_cancel
                captured_batch_sizes.append(batch_size)
                self.assertEqual(list(repositories), [base_repo])
                return [enriched_repo]

            service.collect_repositories = fake_collect
            service.enrich_repositories_with_graphql = fake_enrich
            try:
                summary = service.run_collection(config=config, log=lambda _msg: None)
            finally:
                service.collect_repositories = original_collect
                service.enrich_repositories_with_graphql = original_enrich

            self.assertEqual(captured_batch_sizes, [25])
            _query, repositories = load_repositories_from_metadata(summary.metadata_file)
            self.assertEqual(repositories[0].homepage_url, "https://example.com")
            self.assertTrue(repositories[0].graphql_enriched)

    def test_run_collection_deep_relevance_scores_before_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_root = Path(tmp_dir) / "result"
            base_repo = Repo(
                id=1,
                full_name="team/deep-score",
                clone_url="https://github.com/team/deep-score.git",
                html_url="https://github.com/team/deep-score",
                description="Needs deep scoring",
                stargazers_count=1,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2026-01-01T00:00:00Z",
                pushed_at="2026-01-02T00:00:00Z",
            )
            config = RunConfig(
                query="osint ai automation",
                output_root=output_root,
                dry_run=True,
                deep_relevance_enabled=True,
                deep_relevance_max_repos=5,
                deep_relevance_min_score=0.25,
            )
            original_collect = service.collect_repositories
            original_deep = service.apply_deep_relevance_scoring
            captured_queries: list[str] = []

            def fake_collect(*, client, options, max_repositories, use_date_sharding, log, should_cancel):
                del client, options, max_repositories, use_date_sharding, log, should_cancel
                return [base_repo]

            def fake_deep(config, client, repositories, query, log, should_cancel):
                del client, log, should_cancel
                self.assertTrue(config.deep_relevance_enabled)
                self.assertEqual(config.deep_relevance_max_repos, 5)
                self.assertAlmostEqual(config.deep_relevance_min_score, 0.25)
                self.assertEqual(list(repositories), [base_repo])
                captured_queries.append(query)
                return [
                    replace(
                        base_repo,
                        readme_relevance_score=0.7,
                        code_relevance_score=0.6,
                        deep_relevance_score=0.67,
                        deep_relevance_checked=True,
                    )
                ]

            service.collect_repositories = fake_collect
            service.apply_deep_relevance_scoring = fake_deep
            try:
                summary = service.run_collection(config=config, log=lambda _msg: None)
            finally:
                service.collect_repositories = original_collect
                service.apply_deep_relevance_scoring = original_deep

            self.assertEqual(captured_queries, ["(osint OR ai OR automation)"])
            _query, repositories = load_repositories_from_metadata(summary.metadata_file)
            self.assertTrue(repositories[0].deep_relevance_checked)
            self.assertAlmostEqual(repositories[0].deep_relevance_score, 0.67)

    def test_load_repositories_from_metadata_rejects_unsupported_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = Path(tmp_dir) / "search_new_schema.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "schema_version": 999,
                        "query": "ai",
                        "repositories": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_repositories_from_metadata(metadata_path)

    def test_load_repositories_from_metadata_rejects_unparseable_nonempty_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = Path(tmp_dir) / "search_broken_items.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "query": "ai",
                        "repositories": [{"id": 1}, "not-an-object"],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "ни одну"):
                load_repositories_from_metadata(metadata_path)

    def test_load_repositories_from_metadata_supports_legacy_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            metadata_path = Path(tmp_dir) / "search_legacy.json"
            metadata_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "search_query": "ai agents",
                        "items": [
                            {
                                "id": 7,
                                "full_name": "team/legacy-agent",
                                "clone_url": "https://github.com/team/legacy-agent.git",
                                "html_url": "https://github.com/team/legacy-agent",
                                "description": "Legacy metadata format",
                                "stargazers_count": 11,
                                "language": "Python",
                                "topics": ["ai"],
                                "default_branch": "main",
                                "created_at": "2024-01-01T00:00:00Z",
                                "updated_at": "2026-01-01T00:00:00Z",
                                "pushed_at": "2026-01-02T00:00:00Z",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            query, repositories = load_repositories_from_metadata(metadata_path)
            self.assertEqual(query, "ai agents")
            self.assertEqual(len(repositories), 1)
            self.assertEqual(repositories[0].full_name, "team/legacy-agent")

    def test_load_config_file_defaults_maps_gui_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "gui_settings.json"
            config_path.write_text(
                json.dumps(
                    {
                        "query": "ai agents",
                        "output": "M:/Projects/GithubSearch/output",
                        "token": "ghp_plaintext_should_not_load",
                        "min_stars": "120",
                        "language": "Python",
                        "max_repos": "300",
                        "clone_depth": "0",
                        "clone_partial": False,
                        "clone_single_branch": False,
                        "clone_no_tags": False,
                        "graphql_enrich": True,
                        "graphql_batch_size": "15",
                        "retry_delay_seconds": "9",
                        "ai_filter_enabled": True,
                        "incremental": True,
                        "include_keywords": "osint,security",
                        "exclude_keywords": "tutorial",
                        "export_sqlite": "metadata/repos.sqlite",
                        "ai_provider_type": "openai-compatible",
                        "ai_endpoint": "http://127.0.0.1:11434",
                        "ai_model": "qwen2.5:14b",
                        "ai_api_key": "sk_plaintext_should_not_load",
                        "ai_api_key_env": "EXAMPLE_API_KEY",
                        "ai_timeout": "45",
                        "ai_temperature": "0.1",
                        "ai_num_ctx": "8192",
                        "ai_num_predict": "512",
                        "deep_relevance_enabled": True,
                        "deep_relevance_max_repos": "35",
                        "deep_relevance_min_score": "0.42",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            defaults = load_config_file_defaults(config_path)
            self.assertEqual(defaults["query"], "ai agents")
            self.assertEqual(defaults["output"], "M:/Projects/GithubSearch/output")
            self.assertNotIn("token", defaults)
            self.assertEqual(defaults["min_stars"], 120)
            self.assertEqual(defaults["language"], "Python")
            self.assertEqual(defaults["max_repos"], 300)
            self.assertEqual(defaults["clone_depth"], 0)
            self.assertFalse(defaults["clone_partial"])
            self.assertFalse(defaults["clone_single_branch"])
            self.assertFalse(defaults["clone_no_tags"])
            self.assertTrue(defaults["graphql_enrich"])
            self.assertEqual(defaults["graphql_batch_size"], 15)
            self.assertEqual(defaults["retry_delay"], 9)
            self.assertTrue(defaults["ai_filter"])
            self.assertTrue(defaults["incremental"])
            self.assertEqual(defaults["include_keywords"], "osint,security")
            self.assertEqual(defaults["exclude_keywords"], "tutorial")
            self.assertEqual(defaults["export_sqlite"], "metadata/repos.sqlite")
            self.assertEqual(defaults["ai_provider"], "openai-compatible")
            self.assertEqual(defaults["ai_filter_endpoint"], "http://127.0.0.1:11434")
            self.assertEqual(defaults["ai_filter_model"], "qwen2.5:14b")
            self.assertNotIn("ai_api_key", defaults)
            self.assertEqual(defaults["ai_api_key_env"], "EXAMPLE_API_KEY")
            self.assertEqual(defaults["ai_filter_timeout"], 45)
            self.assertEqual(defaults["ai_temperature"], 0.1)
            self.assertEqual(defaults["ai_num_ctx"], 8192)
            self.assertEqual(defaults["ai_num_predict"], 512)
            self.assertTrue(defaults["deep_relevance"])
            self.assertEqual(defaults["deep_relevance_max_repos"], 35)
            self.assertAlmostEqual(defaults["deep_relevance_min_score"], 0.42)

    def test_parse_cli_args_reads_config_and_applies_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "cli_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "query": "ai agents",
                        "output": "M:/Projects/GithubSearch/output",
                        "max_repos": 120,
                        "ai_filter_enabled": True,
                        "include_keywords": "agent",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = parse_cli_args(
                [
                    "--config-file",
                    str(config_path),
                    "--max-repos",
                    "500",
                    "--clone-depth",
                    "0",
                    "--no-partial-clone",
                    "--all-branches",
                    "--fetch-tags",
                    "--graphql-enrich",
                    "--graphql-batch-size",
                    "15",
                    "--deep-relevance",
                    "--deep-relevance-max-repos",
                    "30",
                    "--deep-relevance-min-score",
                    "0.4",
                    "--no-ai-filter",
                    "--ai-num-ctx",
                    "8192",
                    "--ai-num-predict",
                    "512",
                    "--ai-temperature",
                    "0.1",
                ]
            )
            self.assertEqual(args.query, "ai agents")
            self.assertEqual(args.output, "M:/Projects/GithubSearch/output")
            self.assertEqual(args.max_repos, 500)
            self.assertEqual(args.clone_depth, 0)
            self.assertFalse(args.clone_partial)
            self.assertFalse(args.clone_single_branch)
            self.assertFalse(args.clone_no_tags)
            self.assertTrue(args.graphql_enrich)
            self.assertEqual(args.graphql_batch_size, 15)
            self.assertTrue(args.deep_relevance)
            self.assertEqual(args.deep_relevance_max_repos, 30)
            self.assertAlmostEqual(args.deep_relevance_min_score, 0.4)
            self.assertEqual(args.include_keywords, "agent")
            self.assertFalse(args.ai_filter)
            self.assertEqual(args.ai_num_ctx, 8192)
            self.assertEqual(args.ai_num_predict, 512)
            self.assertEqual(args.ai_temperature, 0.1)

    def test_cli_secret_management_commands_do_not_require_query_or_output(self) -> None:
        args = parse_cli_args(["--show-token-status"])
        self.assertTrue(args.show_token_status)
        self.assertEqual(str(args.query or ""), "")
        self.assertEqual(str(args.output or ""), "")

    def test_resolve_github_token_prefers_explicit_then_env_then_local_store(self) -> None:
        token, source = resolve_github_token(
            explicit_token="cli-token",
            env_token="env-token",
            saved_token_loader=lambda: "saved-token",
        )
        self.assertEqual(token, "cli-token")
        self.assertEqual(source, "cli")

        token, source = resolve_github_token(
            explicit_token="",
            env_token="env-token",
            saved_token_loader=lambda: "saved-token",
        )
        self.assertEqual(token, "env-token")
        self.assertEqual(source, "env")

        token, source = resolve_github_token(
            explicit_token="",
            env_token="",
            saved_token_loader=lambda: "saved-token",
        )
        self.assertEqual(token, "saved-token")
        self.assertEqual(source, "saved")

    def test_cli_ai_secret_management_commands_do_not_require_query_or_output(self) -> None:
        args = parse_cli_args(
            [
                "--ai-provider",
                "openai-compatible",
                "--ai-filter-endpoint",
                "https://api.example.com/v1",
                "--show-ai-api-key-status",
            ]
        )

        self.assertTrue(args.show_ai_api_key_status)
        self.assertEqual(args.ai_provider, "openai-compatible")
        self.assertEqual(args.ai_filter_endpoint, "https://api.example.com/v1")

    def test_resolve_ai_api_key_prefers_explicit_then_env_then_local_store(self) -> None:
        token, source = resolve_ai_api_key(
            provider_type="openai-compatible",
            endpoint="https://api.example.com/v1",
            explicit_key="explicit-key",
            key_env_name="EXAMPLE_API_KEY",
            environ={"EXAMPLE_API_KEY": "env-key"},
            saved_key_loader=lambda _name: "saved-key",
        )
        self.assertEqual(token, "explicit-key")
        self.assertEqual(source, "explicit")

        token, source = resolve_ai_api_key(
            provider_type="openai-compatible",
            endpoint="https://api.example.com/v1",
            explicit_key="",
            key_env_name="EXAMPLE_API_KEY",
            environ={"EXAMPLE_API_KEY": "env-key"},
            saved_key_loader=lambda _name: "saved-key",
        )
        self.assertEqual(token, "env-key")
        self.assertEqual(source, "env:EXAMPLE_API_KEY")

        token, source = resolve_ai_api_key(
            provider_type="openai-compatible",
            endpoint="https://api.example.com/v1",
            explicit_key="",
            key_env_name="",
            environ={},
            saved_key_loader=lambda _name: "saved-key",
        )
        self.assertEqual(token, "saved-key")
        self.assertEqual(source, "saved")

        token, source = resolve_ai_api_key(
            provider_type="ollama",
            endpoint="http://127.0.0.1:11434",
            explicit_key="ignored",
            key_env_name="OLLAMA_KEY",
            environ={"OLLAMA_KEY": "ignored"},
            saved_key_loader=lambda _name: "ignored",
        )
        self.assertEqual(token, "")
        self.assertEqual(source, "not-required")

    def test_parse_cli_args_metadata_file_makes_query_optional(self) -> None:
        args = parse_cli_args(
            [
                "--metadata-file",
                "M:/Projects/GithubSearch/output/metadata/search_test.json",
                "--output",
                "M:/Projects/GithubSearch/output",
            ]
        )
        self.assertEqual(args.query, "")
        self.assertTrue(str(args.metadata_file).endswith("search_test.json"))

    def test_parse_cli_args_output_is_optional_defaulting_to_none_in_parser(self) -> None:
        args = parse_cli_args(["--query", "test", "--dry-run"])
        self.assertEqual(args.query, "test")
        self.assertTrue(args.dry_run)
        self.assertIsNone(args.output)

    def test_cli_main_reports_expected_errors_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = cli_main(
                    [
                        "--query",
                        "ai agents",
                        "--output",
                        tmp_dir,
                        "--created-after",
                        "not-a-date",
                    ]
                )

            self.assertEqual(exit_code, 1)
            error_text = stderr.getvalue()
            self.assertIn("Ошибка:", error_text)
            self.assertIn("--created-after", error_text)
            self.assertNotIn("Traceback", error_text)


if __name__ == "__main__":
    unittest.main()

