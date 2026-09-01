from __future__ import annotations

import sys
import json
import unittest
import unittest.mock
import base64
from io import BytesIO
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from github_harvester.github_api import (
    GITHUB_API_VERSION,
    GitHubApiError,
    GitHubClient,
    _extract_api_message,
    _rate_limit_wait_seconds,
    build_search_query,
    collect_repositories,
    deduplicate_repositories,
    enrich_repositories_with_graphql,
    plan_date_ranges,
    sort_repositories,
)
from github_harvester.models import Repo, SearchOptions


class TestGitHubApiHelpers(unittest.TestCase):
    def setUp(self) -> None:
        self.options = SearchOptions(
            query="osint ai",
            min_stars=10,
            language="Python",
            include_forks=False,
            include_archived=False,
            created_after=date(2020, 1, 1),
            created_before=date(2020, 1, 10),
            sort="stars",
            order="desc",
        )

    def test_build_search_query(self) -> None:
        query = build_search_query(self.options, date(2020, 1, 1), date(2020, 1, 10))
        self.assertIn("osint ai", query)
        self.assertIn("stars:>=10", query)
        self.assertIn("language:Python", query)
        self.assertIn("fork:false", query)
        self.assertIn("archived:false", query)
        self.assertIn("created:2020-01-01..2020-01-10", query)

    def test_plan_date_ranges_splits_when_needed(self) -> None:
        counts = {
            (date(2020, 1, 1), date(2020, 1, 4)): 1500,
            (date(2020, 1, 1), date(2020, 1, 2)): 700,
            (date(2020, 1, 3), date(2020, 1, 4)): 800,
        }

        def fake_count(start: date, end: date) -> int:
            return counts.get((start, end), 0)

        planned = plan_date_ranges(date(2020, 1, 1), date(2020, 1, 4), fake_count, max_per_range=1000)
        self.assertEqual(len(planned), 2)
        self.assertEqual(planned[0].start, date(2020, 1, 1))
        self.assertEqual(planned[0].end, date(2020, 1, 2))
        self.assertEqual(planned[1].start, date(2020, 1, 3))
        self.assertEqual(planned[1].end, date(2020, 1, 4))

    def test_deduplicate_repositories(self) -> None:
        first = Repo(
            id=1,
            full_name="a/b",
            clone_url="https://example.com/a/b",
            html_url="https://example.com/a/b",
            description="",
            stargazers_count=1,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        second = Repo(
            id=1,
            full_name="a/b",
            clone_url="https://example.com/a/b",
            html_url="https://example.com/a/b",
            description="updated",
            stargazers_count=2,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        unique = deduplicate_repositories([first, second])
        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0].description, "updated")

    def test_repo_from_api_item_preserves_rich_metadata(self) -> None:
        repo = Repo.from_api_item(
            {
                "id": 10,
                "full_name": "team/tool",
                "clone_url": "https://github.com/team/tool.git",
                "html_url": "https://github.com/team/tool",
                "description": "Tool",
                "stargazers_count": 50,
                "language": "Python",
                "topics": ["ai"],
                "default_branch": "main",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-01-02T00:00:00Z",
                "forks_count": 7,
                "open_issues_count": 3,
                "watchers_count": 11,
                "size": 2048,
                "license": {"spdx_id": "MIT"},
                "fork": True,
                "archived": False,
                "visibility": "public",
                "node_id": "R_kgDOExample",
            }
        )
        self.assertEqual(repo.node_id, "R_kgDOExample")
        self.assertEqual(repo.forks_count, 7)
        self.assertEqual(repo.open_issues_count, 3)
        self.assertEqual(repo.watchers_count, 11)
        self.assertEqual(repo.size_kb, 2048)
        self.assertEqual(repo.license_spdx_id, "MIT")
        self.assertTrue(repo.is_fork)
        self.assertFalse(repo.is_archived)
        self.assertEqual(repo.visibility, "public")

    def test_repo_from_api_item_preserves_graphql_enrichment_fields(self) -> None:
        repo = Repo.from_api_item(
            {
                "id": 10,
                "node_id": "R_kgDOExample",
                "full_name": "team/tool",
                "clone_url": "https://github.com/team/tool.git",
                "html_url": "https://github.com/team/tool",
                "description": "Tool",
                "stargazers_count": 50,
                "language": "Python",
                "topics": ["ai"],
                "default_branch": "main",
                "created_at": "2025-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-01-02T00:00:00Z",
                "homepage_url": "https://example.com",
                "default_branch_oid": "abc123",
                "default_branch_committed_at": "2026-01-02T00:00:00Z",
                "latest_release_tag": "v1.2.3",
                "latest_release_published_at": "2026-01-03T00:00:00Z",
                "is_mirror": True,
                "is_empty": False,
                "graphql_enriched": True,
            }
        )
        self.assertEqual(repo.homepage_url, "https://example.com")
        self.assertEqual(repo.default_branch_oid, "abc123")
        self.assertEqual(repo.default_branch_committed_at, "2026-01-02T00:00:00Z")
        self.assertEqual(repo.latest_release_tag, "v1.2.3")
        self.assertEqual(repo.latest_release_published_at, "2026-01-03T00:00:00Z")
        self.assertTrue(repo.is_mirror)
        self.assertFalse(repo.is_empty)
        self.assertTrue(repo.graphql_enriched)

    def test_enrich_repositories_with_graphql_updates_repository_metadata(self) -> None:
        repo = Repo(
            id=10,
            node_id="R_kgDOExample",
            full_name="team/tool",
            clone_url="https://github.com/team/tool.git",
            html_url="https://github.com/team/tool",
            description="Tool",
            stargazers_count=50,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            pushed_at="2026-01-02T00:00:00Z",
        )

        class FakeClient:
            def __init__(self) -> None:
                self.calls = []

            def graphql(self, query: str, variables: dict[str, str]) -> dict:
                self.calls.append((query, variables))
                return {
                    "data": {
                        "repo0": {
                            "__typename": "Repository",
                            "id": "R_kgDOExample",
                            "nameWithOwner": "team/tool",
                            "homepageUrl": "https://example.com",
                            "diskUsage": 12345,
                            "isArchived": False,
                            "isEmpty": False,
                            "isFork": False,
                            "isMirror": True,
                            "updatedAt": "2026-01-04T00:00:00Z",
                            "pushedAt": "2026-01-05T00:00:00Z",
                            "primaryLanguage": {"name": "Go"},
                            "licenseInfo": {"spdxId": "Apache-2.0"},
                            "defaultBranchRef": {
                                "name": "main",
                                "target": {
                                    "__typename": "Commit",
                                    "oid": "abc123",
                                    "committedDate": "2026-01-05T00:00:00Z",
                                },
                            },
                            "latestRelease": {
                                "tagName": "v1.2.3",
                                "publishedAt": "2026-01-06T00:00:00Z",
                            },
                            "repositoryTopics": {
                                "nodes": [
                                    {"topic": {"name": "ai"}},
                                    {"topic": {"name": "automation"}},
                                ]
                            },
                        }
                    }
                }

        client = FakeClient()
        enriched = enrich_repositories_with_graphql(client, [repo], batch_size=10)
        self.assertEqual(len(enriched), 1)
        self.assertEqual(client.calls[0][1], {"id0": "R_kgDOExample"})
        self.assertIn("repositoryTopics(first: 20)", client.calls[0][0])
        updated = enriched[0]
        self.assertEqual(updated.homepage_url, "https://example.com")
        self.assertEqual(updated.size_kb, 12345)
        self.assertEqual(updated.language, "Go")
        self.assertEqual(updated.license_spdx_id, "Apache-2.0")
        self.assertEqual(updated.default_branch_oid, "abc123")
        self.assertEqual(updated.default_branch_committed_at, "2026-01-05T00:00:00Z")
        self.assertEqual(updated.latest_release_tag, "v1.2.3")
        self.assertEqual(updated.latest_release_published_at, "2026-01-06T00:00:00Z")
        self.assertEqual(updated.topics, ["ai", "automation"])
        self.assertTrue(updated.is_mirror)
        self.assertTrue(updated.graphql_enriched)

    def test_sort_repositories_stars_desc(self) -> None:
        repos = [
            Repo(
                id=1,
                full_name="a/low",
                clone_url="https://example.com/a/low",
                html_url="https://example.com/a/low",
                description="",
                stargazers_count=5,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
                pushed_at="2025-01-01T00:00:00Z",
            ),
            Repo(
                id=2,
                full_name="a/high",
                clone_url="https://example.com/a/high",
                html_url="https://example.com/a/high",
                description="",
                stargazers_count=50,
                language="Python",
                topics=[],
                default_branch="main",
                created_at="2024-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
                pushed_at="2025-01-01T00:00:00Z",
            ),
        ]
        ordered = sort_repositories(repos, sort="stars", order="desc")
        self.assertEqual([repo.id for repo in ordered], [2, 1])

    def test_collect_repositories_trims_after_global_sort(self) -> None:
        class FakeClient:
            def search_page(self, query: str, sort: str, order: str, page: int, per_page: int) -> dict:
                if per_page == 1:
                    return {"total_count": 2}
                return {
                    "items": [
                        {
                            "id": 11,
                            "full_name": "team/low",
                            "clone_url": "https://example.com/team/low",
                            "html_url": "https://example.com/team/low",
                            "description": "",
                            "stargazers_count": 1,
                            "language": "Python",
                            "topics": [],
                            "default_branch": "main",
                            "created_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-01T00:00:00Z",
                            "pushed_at": "2024-01-01T00:00:00Z",
                        },
                        {
                            "id": 22,
                            "full_name": "team/high",
                            "clone_url": "https://example.com/team/high",
                            "html_url": "https://example.com/team/high",
                            "description": "",
                            "stargazers_count": 300,
                            "language": "Python",
                            "topics": [],
                            "default_branch": "main",
                            "created_at": "2024-01-01T00:00:00Z",
                            "updated_at": "2024-01-01T00:00:00Z",
                            "pushed_at": "2024-01-01T00:00:00Z",
                        },
                    ]
                }

        results = collect_repositories(
            client=FakeClient(),
            options=self.options,
            max_repositories=1,
            use_date_sharding=False,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].id, 22)

    def test_extract_api_message_includes_validation_details(self) -> None:
        raw = (
            '{"message":"Validation Failed","errors":[{"message":"The search contains only logical operators.",'
            '"resource":"Search","field":"q","code":"invalid"}]}'
        )
        message = _extract_api_message(raw)
        self.assertIn("Validation Failed", message)
        self.assertIn("only logical operators", message)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_rate_limit_wait_prefers_retry_after(self, mock_uniform) -> None:
        wait_seconds = _rate_limit_wait_seconds(
            {
                "Retry-After": "17",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "9999999999",
            },
            now=100,
        )
        self.assertEqual(wait_seconds, 18.5)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_rate_limit_wait_uses_reset_when_remaining_is_zero(self, mock_uniform) -> None:
        wait_seconds = _rate_limit_wait_seconds(
            {
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "125",
            },
            now=100,
        )
        self.assertEqual(wait_seconds, 26.5)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_rate_limit_wait_falls_back_to_one_minute(self, mock_uniform) -> None:
        wait_seconds = _rate_limit_wait_seconds({}, now=100)
        self.assertEqual(wait_seconds, 61.5)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_rate_limit_wait_ignores_reset_when_remaining_is_not_zero(self, mock_uniform) -> None:
        wait_seconds = _rate_limit_wait_seconds(
            {
                "X-RateLimit-Remaining": "12",
                "X-RateLimit-Reset": "100000",
            },
            now=100,
        )
        self.assertEqual(wait_seconds, 61.5)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_rate_limit_wait_uses_exponential_secondary_fallback(self, mock_uniform) -> None:
        wait_seconds = _rate_limit_wait_seconds({}, now=100, fallback_attempt=3)
        self.assertEqual(wait_seconds, 241.5)

    @unittest.mock.patch("github_harvester.github_api.random.uniform", return_value=1.5)
    def test_wait_for_rate_limit_respects_max_wait(self, mock_uniform) -> None:
        client = GitHubClient(max_rate_limit_wait=10)
        with self.assertRaises(GitHubApiError):
            client._wait_for_rate_limit({"Retry-After": "11"})

    def test_rate_limit_on_final_attempt_reports_specific_error(self) -> None:
        import urllib.error
        import urllib.request
        from unittest.mock import patch

        client = GitHubClient(max_retries=0)
        error = urllib.error.HTTPError(
            url="https://api.github.com/search/repositories",
            code=403,
            msg="Forbidden",
            hdrs={"Retry-After": "1"},
            fp=BytesIO(b'{"message":"API rate limit exceeded"}'),
        )
        with patch.object(urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(GitHubApiError, "лимит запросов GitHub"):
                client.search_page("test", "stars", "desc", page=1, per_page=1)

    def test_client_uses_current_github_api_version_header(self) -> None:
        captured_headers = {}

        class FakeResponse:
            headers = {}
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

            def read(self) -> bytes:
                return b'{"items":[]}'

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            captured_headers.update(request.headers)
            return FakeResponse()

        import urllib.request
        from unittest.mock import patch

        client = GitHubClient()
        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            client.search_page("test", "stars", "desc", page=1, per_page=1)

        self.assertEqual(captured_headers["X-github-api-version"], GITHUB_API_VERSION)

    def test_graphql_posts_authorized_request_with_variables(self) -> None:
        captured_headers = {}
        captured_body = b""

        class FakeResponse:
            headers = {}

            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

            def read(self) -> bytes:
                return b'{"data":{"viewer":{"login":"octocat"}}}'

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            nonlocal captured_body
            captured_headers.update(request.headers)
            captured_body = request.data
            return FakeResponse()

        import urllib.request
        from unittest.mock import patch

        client = GitHubClient(token="ghp_token")
        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            payload = client.graphql("query($id: ID!) { node(id: $id) { id } }", {"id": "R_1"})

        body = json.loads(captured_body.decode("utf-8"))
        self.assertEqual(payload["data"]["viewer"]["login"], "octocat")
        self.assertEqual(body["variables"], {"id": "R_1"})
        self.assertEqual(captured_headers["Authorization"], "Bearer ghp_token")
        self.assertEqual(captured_headers["X-github-api-version"], GITHUB_API_VERSION)

    def test_client_fetches_repository_readme_text(self) -> None:
        captured_url = ""
        readme_bytes = "# Project\n\nOSINT automation toolkit".encode("utf-8")
        encoded_readme = base64.b64encode(readme_bytes).decode("ascii")

        class FakeResponse:
            headers = {}
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "encoding": "base64",
                        "content": encoded_readme,
                        "size": len(readme_bytes),
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            nonlocal captured_url
            captured_url = request.full_url
            return FakeResponse()

        import urllib.request
        from unittest.mock import patch

        repo = Repo(
            id=1,
            full_name="team/project",
            clone_url="https://github.com/team/project.git",
            html_url="https://github.com/team/project",
            description="",
            stargazers_count=1,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        client = GitHubClient()
        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            readme_text = client.get_repository_readme_text(repo)

        self.assertEqual(readme_text, "# Project\n\nOSINT automation toolkit")
        self.assertEqual(captured_url, "https://api.github.com/repos/team/project/readme")

    def test_client_fetches_repository_tree_paths(self) -> None:
        captured_url = ""

        class FakeResponse:
            headers = {}
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, traceback) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps(
                    {
                        "truncated": False,
                        "tree": [
                            {"path": "src/osint/client.py", "type": "blob", "size": 100},
                            {"path": "docs", "type": "tree"},
                            {"path": "README.md", "type": "blob", "size": 200},
                        ],
                    }
                ).encode("utf-8")

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            nonlocal captured_url
            captured_url = request.full_url
            return FakeResponse()

        import urllib.request
        from unittest.mock import patch

        repo = Repo(
            id=1,
            full_name="team/project",
            clone_url="https://github.com/team/project.git",
            html_url="https://github.com/team/project",
            description="",
            stargazers_count=1,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        client = GitHubClient()
        with patch.object(urllib.request, "urlopen", side_effect=fake_urlopen):
            paths, truncated = client.get_repository_tree_paths(repo)

        self.assertEqual(paths, ["src/osint/client.py", "README.md"])
        self.assertFalse(truncated)
        self.assertEqual(
            captured_url,
            "https://api.github.com/repos/team/project/git/trees/main?recursive=1",
        )


if __name__ == "__main__":
    unittest.main()
