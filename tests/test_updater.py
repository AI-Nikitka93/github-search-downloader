from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch
import urllib.error

from github_harvester.updater import (
    ReleaseAsset,
    AssetInfo,
    CheckResult,
    ReleaseInfo,
    SelfUpdater,
    UpdateChecker,
    UpdateDownloader,
)
from github_harvester.version import SemVer


class TestUpdater(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_update_checker_parse_release(self):
        checker = UpdateChecker(cache_dir=self.cache_dir)
        raw_json = {
            "tag_name": "v2.0.0",
            "name": "Release 2.0.0",
            "published_at": "2026-09-01T12:00:00Z",
            "html_url": "https://github.com/owner/repo/releases/tag/v2.0.0",
            "body": "### Changes\n- New feature",
            "prerelease": False,
            "assets": [
                {
                    "name": "GithubSearchDownloader-v2.0.0-windows-x64-portable.zip",
                    "browser_download_url": "https://github.com/owner/repo/releases/download/v2.0.0/portable.zip",
                    "size": 15000000,
                },
                {
                    "name": "checksums.sha256",
                    "browser_download_url": "https://github.com/owner/repo/releases/download/v2.0.0/checksums.sha256",
                    "size": 128,
                },
            ],
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(raw_json).encode("utf-8")
        mock_resp.headers = {"ETag": '"etag123"'}
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = checker.check_for_updates(force=True)

        self.assertTrue(res.update_available)
        self.assertIsNotNone(res.latest_release)
        self.assertEqual(res.latest_release.version_str, "2.0.0")
        self.assertEqual(len(res.latest_release.assets), 2)
        self.assertIsNotNone(res.latest_release.portable_zip_asset)
        self.assertIsNotNone(res.latest_release.checksum_asset)

    def test_update_checker_etag_not_modified(self):
        checker = UpdateChecker(cache_dir=self.cache_dir)

        # Pre-seed cache
        checker._write_cache({
            "last_checked_ts": 0,
            "last_checked_utc": "2026-01-01T00:00:00Z",
            "etag": "etag-xyz",
            "release_data": {
                "tag_name": "v1.0.0",
                "name": "Release 1.0.0",
                "published_at": "2026-01-01T00:00:00Z",
                "html_url": "https://github.com/owner/repo",
                "body": "No updates",
                "prerelease": False,
                "assets": [],
            },
        })

        http_err = urllib.error.HTTPError(
            url="https://api.github.com",
            code=304,
            msg="Not Modified",
            hdrs={},
            fp=None,
        )

        with patch("urllib.request.urlopen", side_effect=http_err):
            res = checker.check_for_updates(force=True)

        self.assertFalse(res.update_available)

    def test_downloader_zip_slip_rejection(self):
        downloader = UpdateDownloader(download_dir=self.cache_dir)

        # 1. Relative traversal
        zip_path = self.cache_dir / "malicious.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("../../evil.exe", b"malicious content")

        with self.assertRaises(ValueError) as ctx:
            downloader.safe_extract_zip(zip_path, self.cache_dir / "extracted")
        self.assertIn("Zip Slip", str(ctx.exception))

        # 2. Windows drive-relative prefix
        zip_path_drive = self.cache_dir / "malicious_drive.zip"
        with zipfile.ZipFile(zip_path_drive, "w") as zf:
            zf.writestr("C:evil.exe", b"malicious content")

        with self.assertRaises(ValueError) as ctx:
            downloader.safe_extract_zip(zip_path_drive, self.cache_dir / "extracted2")
        self.assertIn("Zip Slip", str(ctx.exception))

        # 3. Windows DOS device name
        zip_path_dev = self.cache_dir / "malicious_dev.zip"
        with zipfile.ZipFile(zip_path_dev, "w") as zf:
            zf.writestr("sub/CON.txt", b"device content")

        with self.assertRaises(ValueError) as ctx:
            downloader.safe_extract_zip(zip_path_dev, self.cache_dir / "extracted3")
        self.assertIn("reserved device name", str(ctx.exception))

    def test_downloader_safe_extract(self):
        downloader = UpdateDownloader(download_dir=self.cache_dir)

        zip_path = self.cache_dir / "safe.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("app/main.exe", b"safe content")
            zf.writestr("app/config.json", b"{}")

        extract_dir = self.cache_dir / "extracted"
        downloader.safe_extract_zip(zip_path, extract_dir)
        self.assertTrue((extract_dir / "app" / "main.exe").exists())
        self.assertEqual((extract_dir / "app" / "main.exe").read_bytes(), b"safe content")

    def test_self_updater_batch_script_generation(self):
        updater_dir = self.cache_dir / "updater"
        updater_dir.mkdir(parents=True, exist_ok=True)
        bat_path = updater_dir / "apply_update.bat"

        # Generate batch script
        SelfUpdater._write_updater_script(
            bat_path=bat_path,
            pid=12345,
            source_dir=self.cache_dir / "extracted",
            target_dir=self.cache_dir / "installed_app",
            target_exe=self.cache_dir / "installed_app" / "app.exe",
        )

        self.assertTrue(bat_path.exists())
        content = bat_path.read_text(encoding="utf-8")
        self.assertIn("taskkill /F /PID 12345", content)
        self.assertIn("robocopy", content)
        self.assertIn("del /F /Q", content)


if __name__ == "__main__":
    unittest.main()
