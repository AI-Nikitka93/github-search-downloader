import unittest
import tempfile
import shutil
import os
from pathlib import Path
from github_harvester.models import Repo
from github_harvester.ai_exporter import export_repo_for_ai
from github_harvester.downloader import build_repo_folder_name
from github_harvester.ai_planner import parse_json_object
from github_harvester.ai_providers import validate_and_fetch_models
from github_harvester.exporters import export_to_csv

class TestAuditFixes(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_ai_exporter_total_cap_stops_outer_walk(self):
        repo = self.tmp_dir / "repo"
        repo.mkdir()
        dir1 = repo / "dir1"
        dir1.mkdir()
        (dir1 / "big.txt").write_text("A" * 20000, encoding="utf-8")
        dir2 = repo / "dir2"
        dir2.mkdir()
        (dir2 / "small.txt").write_text("B" * 100, encoding="utf-8")

        out_path = export_repo_for_ai(
            repo_name="test/repo",
            repo_path=repo,
            output_root=self.tmp_dir,
            max_file_size=50000,
            max_total_size=10000,
        )
        content = out_path.read_text(encoding="utf-8")
        self.assertIn("Remaining repository files omitted", content)
        self.assertNotIn('<file path="dir2/small.txt">', content)

    def test_downloader_no_slash_in_full_name(self):
        r = Repo(
            id=1,
            full_name="singlename",
            clone_url="https://github.com/example/singlename.git",
            html_url="https://github.com/example/singlename",
            description="Test description",
            stargazers_count=10,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            pushed_at="2026-01-01T00:00:00Z",
            forks_count=0,
            open_issues_count=0,
            watchers_count=10,
            size_kb=100,
            license_spdx_id="MIT",
        )
        folder = build_repo_folder_name(r)
        self.assertTrue(folder.startswith("singlename"))

    def test_parse_json_object_multi_block(self):
        raw = '''Thinking process:
```json
{
  "example": "not_response"
}
```
Here is the response:
```json
{
  "query": "k8s operators",
  "folder_name": "example_k8s",
  "sort": "stars"
}
```'''
        result = parse_json_object(raw)
        self.assertIn("query", result)

    def test_cloudflare_validation_requires_account_id(self):
        res = validate_and_fetch_models("cloudflare", "api_key", account_id="")
        self.assertFalse(res.success)

    def test_csv_export_utf8_sig(self):
        r = Repo(
            id=1,
            full_name="user/тест",
            clone_url="https://github.com/user/test.git",
            html_url="https://github.com/user/test",
            description="Описание",
            stargazers_count=10,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
            pushed_at="2026-01-01T00:00:00Z",
            forks_count=0,
            open_issues_count=0,
            watchers_count=10,
            size_kb=100,
            license_spdx_id="MIT",
        )
        csv_file = self.tmp_dir / "repos.csv"
        export_to_csv(csv_file, [r])
        raw_bytes = csv_file.read_bytes()
        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

if __name__ == '__main__':
    unittest.main()
