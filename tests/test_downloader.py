from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from github_harvester.downloader import (
    CloneOptions,
    build_description_slug,
    build_git_clone_command,
    build_repo_folder_name,
    find_existing_repo_path,
    sanitize_path_segment,
)
from github_harvester.models import Repo


class TestDownloaderHelpers(unittest.TestCase):
    def test_sanitize_path_segment(self) -> None:
        self.assertEqual(sanitize_path_segment("repo:name"), "repo_name")
        self.assertEqual(sanitize_path_segment("name."), "name")
        self.assertEqual(sanitize_path_segment("   "), "unknown")
        self.assertEqual(sanitize_path_segment("CON"), "reserved_CON")
        self.assertEqual(sanitize_path_segment("COM1.txt"), "reserved_COM1.txt")

    def test_build_description_slug(self) -> None:
        slug = build_description_slug("Powerful OSINT tool for cyber investigation and threat hunting")
        self.assertTrue(slug.startswith("powerful_osint_cyber_investigation"))

    def test_build_repo_folder_name(self) -> None:
        repo = Repo(
            id=1,
            full_name="owner/my-awesome-repo",
            clone_url="https://example.com/owner/my-awesome-repo",
            html_url="https://example.com/owner/my-awesome-repo",
            description="Advanced OSINT framework for intelligence analysis",
            stargazers_count=0,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        name = build_repo_folder_name(repo)
        self.assertIn("my-awesome-repo", name)
        self.assertIn("advanced_osint_framework", name)

    def test_build_repo_folder_name_avoids_windows_reserved_device_names(self) -> None:
        repo = Repo(
            id=1,
            full_name="owner/CON",
            clone_url="https://example.com/owner/CON",
            html_url="https://example.com/owner/CON",
            description="",
            stargazers_count=0,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        self.assertEqual(build_repo_folder_name(repo), "reserved_CON")

    def test_find_existing_repo_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            owner_dir = Path(temp_dir)
            existing = owner_dir / "projectx__osint_automation"
            existing.mkdir()
            result = find_existing_repo_path(owner_dir, "projectx")
            self.assertEqual(result, existing)

    def test_build_git_clone_command_defaults_to_fast_shallow_partial_clone(self) -> None:
        repo = Repo(
            id=1,
            full_name="owner/project",
            clone_url="https://example.com/owner/project.git",
            html_url="https://example.com/owner/project",
            description="",
            stargazers_count=0,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        command = build_git_clone_command(repo, Path("target"), CloneOptions())
        self.assertEqual(command[:2], ["git", "clone"])
        self.assertIn("--depth", command)
        self.assertIn("1", command)
        self.assertIn("--filter=blob:none", command)
        self.assertIn("--single-branch", command)
        self.assertIn("--no-tags", command)
        self.assertEqual(command[-2:], [repo.clone_url, "target"])

    def test_build_git_clone_command_can_request_full_clone(self) -> None:
        repo = Repo(
            id=1,
            full_name="owner/project",
            clone_url="https://example.com/owner/project.git",
            html_url="https://example.com/owner/project",
            description="",
            stargazers_count=0,
            language="Python",
            topics=[],
            default_branch="main",
            created_at="",
            updated_at="",
            pushed_at="",
        )
        options = CloneOptions(depth=0, partial_clone=False, single_branch=False, no_tags=False)
        command = build_git_clone_command(repo, Path("target"), options)
        self.assertNotIn("--depth", command)
        self.assertNotIn("--filter=blob:none", command)
        self.assertNotIn("--single-branch", command)
        self.assertNotIn("--no-tags", command)
        self.assertEqual(command[-2:], [repo.clone_url, "target"])


if __name__ == "__main__":
    unittest.main()
