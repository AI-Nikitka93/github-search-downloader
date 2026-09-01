from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

from github_harvester.ai_providers import (
    PROVIDERS,
    ModelInfo,
    ValidationResult,
    detect_provider_from_key,
    parse_models_response,
    validate_and_fetch_models,
)


class TestAiProviders(unittest.TestCase):
    def test_detect_provider_from_key(self):
        self.assertEqual(detect_provider_from_key("sk-or-v1-abc1234567890"), "openrouter")
        self.assertEqual(detect_provider_from_key("gsk_2mJWNL06Ophy4TQzdunnWGdyb3FY"), "groq")
        self.assertEqual(detect_provider_from_key("nvapi-Up6xmRe2c_taqUT_2xB5Yv2IJnn"), "nvidia")
        self.assertEqual(detect_provider_from_key("cfut_T1PrUFyvkGAcAnojTeGXOW2g9"), "cloudflare")
        self.assertEqual(detect_provider_from_key("sk-proj-abc123456789012345678"), "openai")
        self.assertEqual(detect_provider_from_key("sk-deepseek12345678901234567890"), "deepseek")
        self.assertEqual(detect_provider_from_key("Yohta2VL0B9VQqgxW91Y2ejQ3W5NBb64"), "mistral")
        self.assertIsNone(detect_provider_from_key(""))
        self.assertIsNone(detect_provider_from_key("short"))

    def test_parse_models_response_openrouter(self):
        payload = {
            "data": [
                {
                    "id": "meta-llama/llama-3.3-70b-instruct:free",
                    "name": "Llama 3.3 70B (Free)",
                    "context_length": 131072,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
                {
                    "id": "anthropic/claude-3.5-sonnet",
                    "name": "Claude 3.5 Sonnet",
                    "context_length": 200000,
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                },
                {
                    "id": "deepseek/deepseek-r1:free",
                    "name": "DeepSeek R1 (Free)",
                    "context_length": 65536,
                    "pricing": {"prompt": "0", "completion": "0"},
                },
            ]
        }
        models = parse_models_response("openrouter", payload)
        self.assertEqual(len(models), 3)

        # Free models should come first
        self.assertTrue(models[0].is_free)
        self.assertTrue(models[1].is_free)
        self.assertIn(":free", models[0].id)
        self.assertIn(":free", models[1].id)
        self.assertFalse(models[2].is_free)
        self.assertTrue(models[2].is_recommended)

    def test_validate_and_fetch_models_success(self):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_data = {
            "data": [
                {"id": "codestral-latest", "name": "Codestral"},
                {"id": "mistral-large-latest", "name": "Mistral Large"},
            ]
        }
        mock_resp.read.return_value = json.dumps(mock_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            res = validate_and_fetch_models(
                provider_id="mistral",
                api_key="dummy_key_12345",
                timeout=5,
            )

        self.assertTrue(res.success)
        self.assertEqual(res.provider_id, "mistral")
        self.assertEqual(len(res.models), 2)
        self.assertEqual(res.models[0].id, "codestral-latest")

    def test_validate_and_fetch_models_401_unauthorized(self):
        err = urllib.error.HTTPError(
            url="https://api.openai.com/v1/models",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error": {"message": "Invalid API key"}}'),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            res = validate_and_fetch_models(
                provider_id="openai",
                api_key="invalid_key",
                timeout=5,
            )

        self.assertFalse(res.success)
        self.assertEqual(res.http_status, 401)
        self.assertIn("Неверный API-ключ", res.error_message)

    def test_validate_and_fetch_models_403_groq_vpn_hint(self):
        err = urllib.error.HTTPError(
            url="https://api.groq.com/openai/v1/models",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=MagicMock(read=lambda: b"Access denied"),
        )
        with patch("urllib.request.urlopen", side_effect=err):
            res = validate_and_fetch_models(
                provider_id="groq",
                api_key="gsk_12345",
                timeout=5,
            )

        self.assertFalse(res.success)
        self.assertEqual(res.http_status, 403)
        self.assertIn("VPN", res.error_message)


if __name__ == "__main__":
    unittest.main()
