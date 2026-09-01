import os
import stat
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from github_harvester.ai_exporter import export_repo_for_ai
from github_harvester.downloader import safe_rmtree_windows
from github_harvester.github_auth import GitHubOAuthDeviceFlow
from github_harvester.updater import UpdateDownloader


class TestStabilityFixes(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_safe_rmtree_windows_deletes_readonly_files(self):
        """Verifies that read-only git pack files on Windows NTFS are successfully removed."""
        target = self.work_dir / "locked_repo"
        git_dir = target / ".git" / "objects"
        git_dir.mkdir(parents=True)
        pack_file = git_dir / "pack-abc.pack"
        pack_file.write_bytes(b"dummy git binary data")
        os.chmod(pack_file, stat.S_IREAD)

        success = safe_rmtree_windows(target, retries=3, delay=0.02)
        self.assertTrue(success)
        self.assertFalse(target.exists())

    def test_ai_exporter_posix_paths_and_size_caps(self):
        """Verifies that XML export uses POSIX slashes and truncates oversized files."""
        repo = self.work_dir / "test_repo"
        sub = repo / "nested" / "folder"
        sub.mkdir(parents=True)

        f1 = sub / "script.py"
        f1.write_text("print('hello')", encoding="utf-8")

        huge_file = sub / "huge.txt"
        huge_file.write_text("X" * (500 * 1024), encoding="utf-8")

        xml_file = export_repo_for_ai(
            repo_name="org/test_repo",
            repo_path=repo,
            output_root=self.work_dir,
            max_file_size=100 * 1024,  # 100 KB limit
        )

        self.assertTrue(xml_file.exists())
        content = xml_file.read_text(encoding="utf-8")

        # Must use POSIX slashes
        self.assertIn('<file path="nested/folder/script.py">', content)
        # Must truncate huge file
        self.assertIn('<file path="nested/folder/huge.txt">', content)
        self.assertIn("Truncated: file size", content)

    def test_poll_for_token_cancel_event_terminates_immediately(self):
        """Verifies that poll_for_token aborts cleanly when cancel_event is set."""
        flow = GitHubOAuthDeviceFlow()
        cancel_event = threading.Event()

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"error": "authorization_pending"}'
        mock_resp.__enter__.return_value = mock_resp

        def _cancel():
            time.sleep(0.1)
            cancel_event.set()

        threading.Thread(target=_cancel, daemon=True).start()

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(RuntimeError) as ctx:
                flow.poll_for_token(
                    device_code="dummy_code",
                    interval=1,
                    cancel_event=cancel_event,
                    max_duration_seconds=5,
                )
            self.assertIn("отменена пользователем", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
