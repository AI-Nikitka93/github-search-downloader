from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from github_harvester.ai_exporter import export_repo_for_ai, sanitize_path_segment, generate_repo_map


class TestAIExporter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.temp_dir.name)
        self.repo_dir = self.root_path / "test_repo"
        self.repo_dir.mkdir()

        # Create normal files
        (self.repo_dir / "main.py").write_text("print('hello world')", encoding="utf-8")
        (self.repo_dir / "README.md").write_text("# Test Repo\nDocumentation", encoding="utf-8")

        # Create a subfolder
        sub_dir = self.repo_dir / "src"
        sub_dir.mkdir()
        (sub_dir / "lib.py").write_text("def add(a, b): return a + b", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sanitize_path_segment(self):
        self.assertEqual(sanitize_path_segment("owner/repo"), "owner_repo")
        self.assertEqual(sanitize_path_segment("..\\evil/path:test*"), ".._evil_path_test_")
        self.assertEqual(sanitize_path_segment("normal-name_123"), "normal-name_123")

    def test_generate_repo_map(self):
        tree = generate_repo_map(self.repo_dir)
        self.assertIn("main.py", tree)
        self.assertIn("README.md", tree)
        self.assertIn("src", tree)

    def test_generate_repo_map_symlink_cycle_safe(self):
        loop_target = self.repo_dir / "src" / "cycle"
        try:
            os.symlink(str(self.repo_dir), str(loop_target), target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks require administrator privileges or Developer Mode on this system")

        tree = generate_repo_map(self.repo_dir)
        self.assertIsInstance(tree, str)
        self.assertNotIn("cycle/cycle", tree)

    def test_export_repo_for_ai_xml_format(self):
        out_root = self.root_path / "output"
        result_path = export_repo_for_ai(
            repo_name="owner/test_repo",
            repo_path=self.repo_dir,
            output_root=out_root,
        )

        self.assertTrue(result_path.exists())
        content = result_path.read_text(encoding="utf-8")
        self.assertIn("<repository name=\"owner/test_repo\">", content)
        self.assertIn("<file path=\"main.py\">", content)
        self.assertIn("print('hello world')", content)
        self.assertIn("def add(a, b): return a + b", content)

    def test_symlink_traversal_skipped(self):
        # Create an external sensitive file
        external_secret = self.root_path / "secret_keys.txt"
        external_secret.write_text("SUPER_SECRET_KEY=12345", encoding="utf-8")

        # Attempt to symlink inside repo pointing outside
        symlink_target = self.repo_dir / "symlink_to_secret.txt"
        try:
            os.symlink(str(external_secret), str(symlink_target))
        except (OSError, NotImplementedError):
            # On Windows without SeCreateSymbolicLinkPrivilege, symlinks might fail; skip test if so
            self.skipTest("Symlinks require administrator privileges or Developer Mode on this system")

        out_root = self.root_path / "output_symlink"
        result_path = export_repo_for_ai(
            repo_name="owner/test_repo",
            repo_path=self.repo_dir,
            output_root=out_root,
        )

        content = result_path.read_text(encoding="utf-8")
        self.assertNotIn("SUPER_SECRET_KEY=12345", content)


if __name__ == "__main__":
    unittest.main()
