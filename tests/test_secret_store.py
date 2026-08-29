from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from github_harvester.secret_store import (
    SecretStoreError,
    delete_secret,
    has_secret,
    load_secret,
    secret_name_for_ai_provider,
    store_secret,
)


@unittest.skipUnless(os.name == "nt", "Windows DPAPI secret store is only available on Windows")
class TestSecretStore(unittest.TestCase):
    def test_round_trip_uses_local_encrypted_file_without_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)
            secret = "ghp_" + "a" * 36

            path = store_secret("github_token", secret, base_dir=base_dir)

            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            self.assertEqual(payload["provider"], "windows-dpapi")
            self.assertEqual(payload["scope"], "current-user")
            self.assertTrue(has_secret("github_token", base_dir=base_dir))
            self.assertNotIn(secret, raw)
            self.assertNotIn("ghp_", raw)
            self.assertEqual(load_secret("github_token", base_dir=base_dir), secret)

            self.assertTrue(delete_secret("github_token", base_dir=base_dir))
            self.assertFalse(has_secret("github_token", base_dir=base_dir))
            self.assertEqual(load_secret("github_token", base_dir=base_dir), "")

    def test_rejects_invalid_secret_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(SecretStoreError):
                store_secret("../token", "secret", base_dir=Path(tmp_dir))

    def test_ai_provider_secret_name_is_deterministic_and_safe(self) -> None:
        first = secret_name_for_ai_provider("openai-compatible", "https://api.example.com/v1")
        second = secret_name_for_ai_provider("openai_compatible", "https://api.example.com/v1/")
        other = secret_name_for_ai_provider("openai-compatible", "https://openrouter.ai/api/v1")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertLessEqual(len(first), 64)
        self.assertTrue(first.startswith("ai_openai-compatible_"))
        self.assertNotIn("api.example.com", first)
