from __future__ import annotations

import io
import json
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from github_harvester.github_auth import GitHubOAuthDeviceFlow, get_github_cli_token


class TestGitHubAuth(unittest.TestCase):
    def test_request_device_code_success(self):
        flow = GitHubOAuthDeviceFlow()
        mock_payload = {
            "device_code": "dev12345",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://github.com/login/device",
            "expires_in": 900,
            "interval": 5,
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = flow.request_device_code()

        self.assertEqual(info["device_code"], "dev12345")
        self.assertEqual(info["user_code"], "WDJB-MJHT")
        self.assertEqual(info["verification_uri"], "https://github.com/login/device")

    def test_poll_for_token_success(self):
        flow = GitHubOAuthDeviceFlow()
        mock_payload = {
            "access_token": "gho_16C7e42F292c6912E7710c838347Ae178B4a",
            "token_type": "bearer",
            "scope": "repo,read:user",
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            token = flow.poll_for_token("dev12345", interval=1)

        self.assertEqual(token, "gho_16C7e42F292c6912E7710c838347Ae178B4a")

    def test_poll_for_token_expired_error(self):
        flow = GitHubOAuthDeviceFlow()
        mock_payload = {
            "error": "expired_token",
            "error_description": "The device code has expired.",
        }

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(mock_payload).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with self.assertRaises(RuntimeError) as ctx:
                flow.poll_for_token("dev12345", interval=1)
            self.assertIn("код просрочен", str(ctx.exception))

    def test_get_github_cli_token_fallback(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            token = get_github_cli_token()
            self.assertIsNone(token)


if __name__ == "__main__":
    unittest.main()
