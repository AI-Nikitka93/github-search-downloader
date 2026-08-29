from __future__ import annotations

import sys
import json
import unittest
from unittest import mock
import urllib.error
import socket
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from github_harvester.ai_planner import (
    AiPlannerError,
    AiProviderConfig,
    list_ai_models,
    list_ollama_models,
    normalize_plan,
    parse_json_object,
    parse_ollama_tags_payload,
    request_ai,
    request_ollama,
    sanitize_planner_query,
    sanitize_folder_name,
)


class TestAiPlanner(unittest.TestCase):
    def test_sanitize_folder_name(self) -> None:
        self.assertEqual(sanitize_folder_name("OSINT: AI / Project"), "OSINT_AI_Project")
        self.assertEqual(sanitize_folder_name("   "), "project")

    def test_parse_json_object_with_noise(self) -> None:
        raw = "text before {\"query\":\"osint ai\",\"max_repos\":50} text after"
        parsed = parse_json_object(raw)
        self.assertEqual(parsed["query"], "osint ai")
        self.assertEqual(parsed["max_repos"], 50)

    def test_normalize_plan_defaults(self) -> None:
        payload = {"query": "osint ai"}
        result = normalize_plan(payload, task_text="fallback")
        self.assertEqual(result.query, "osint ai")
        self.assertEqual(result.max_age_years, 5)
        self.assertEqual(result.max_repos, 100)
        self.assertEqual(result.batch_size, 100)
        self.assertEqual(result.sort, "stars")
        self.assertEqual(result.order, "desc")

    def test_parse_ollama_tags_payload(self) -> None:
        payload = {
            "models": [
                {"name": "qwen-14b-general:latest"},
                {"name": "QWEN-14B-GENERAL:latest"},
                {"name": "qwen-30b-long-pro"},
            ]
        }
        models = parse_ollama_tags_payload(payload)
        self.assertEqual(models, ["qwen-14b-general:latest", "qwen-30b-long-pro"])

    def test_list_ollama_models_connection_refused_message_is_user_friendly(self) -> None:
        refused = urllib.error.URLError(ConnectionRefusedError(10061, "Подключение не установлено"))
        with mock.patch("github_harvester.ai_planner.urllib.request.urlopen", side_effect=refused):
            with self.assertRaises(AiPlannerError) as ctx:
                list_ollama_models("http://127.0.0.1:11434", timeout=1)

        message = str(ctx.exception)
        self.assertIn("Ollama не запущен", message)
        self.assertIn("http://127.0.0.1:11434", message)
        self.assertIn("ollama serve", message)
        self.assertNotIn("urlopen error", message)
        self.assertNotIn("WinError 10061", message)

    def test_request_ai_openai_compatible_chat_completions(self) -> None:
        provider = AiProviderConfig(
            provider_type="openai-compatible",
            endpoint="https://api.example.com/v1",
            model="example-model",
            api_key="sk_test_secret",
            timeout=15,
            temperature=0.2,
            num_predict=128,
        )
        captured: dict[str, object] = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["authorization"] = request.get_header("Authorization")
            captured["payload"] = json.loads(request.data.decode("utf-8"))
            return _FakeResponse()

        with mock.patch("github_harvester.ai_planner.urllib.request.urlopen", side_effect=fake_urlopen):
            raw = request_ai(provider, "Return JSON.", retries=0)

        self.assertEqual(raw, '{"ok":true}')
        self.assertEqual(captured["url"], "https://api.example.com/v1/chat/completions")
        self.assertEqual(captured["authorization"], "Bearer sk_test_secret")
        self.assertEqual(captured["timeout"], 15)
        payload = captured["payload"]
        self.assertEqual(payload["model"], "example-model")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 128)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["messages"][0]["role"], "user")

    def test_list_ai_models_openai_compatible(self) -> None:
        provider = AiProviderConfig(
            provider_type="openai-compatible",
            endpoint="https://api.example.com/v1",
            model="",
            api_key="sk_test_secret",
        )

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"data":[{"id":"z-model"},{"id":"a-model"}]}'

        with mock.patch("github_harvester.ai_planner.urllib.request.urlopen", return_value=_FakeResponse()):
            models = list_ai_models(provider, timeout=10)

        self.assertEqual(models, ["a-model", "z-model"])

    def test_request_ollama_retries_timeout(self) -> None:
        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=5)

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"response":"{\\"ok\\":true}"}'

        with mock.patch(
            "github_harvester.ai_planner.urllib.request.urlopen",
            side_effect=[TimeoutError("timed out"), _FakeResponse()],
        ):
            raw = request_ollama(provider, "test prompt", retries=1)
        self.assertIn('"ok"', raw)

    def test_request_ollama_sends_provider_generation_options(self) -> None:
        provider = AiProviderConfig(
            endpoint="http://127.0.0.1:11434",
            model="dummy",
            timeout=5,
            temperature=0.1,
            num_ctx=8192,
            num_predict=256,
        )
        captured_payload: dict[str, object] = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return b'{"response":"{\\"ok\\":true}"}'

        def fake_urlopen(request, timeout):  # noqa: ANN001, ANN202
            del timeout
            captured_payload.update(json.loads(request.data.decode("utf-8")))
            return _FakeResponse()

        with mock.patch("github_harvester.ai_planner.urllib.request.urlopen", side_effect=fake_urlopen):
            request_ollama(provider, "test prompt", retries=0)

        self.assertEqual(
            captured_payload["options"],
            {
                "temperature": 0.1,
                "num_ctx": 8192,
                "num_predict": 256,
            },
        )

    def test_request_ollama_timeout_error_message(self) -> None:
        provider = AiProviderConfig(endpoint="http://127.0.0.1:11434", model="dummy", timeout=5)
        with mock.patch(
            "github_harvester.ai_planner.urllib.request.urlopen",
            side_effect=urllib.error.URLError(socket.timeout("timed out")),
        ):
            with self.assertRaises(AiPlannerError) as ctx:
                request_ollama(provider, "test prompt", retries=0)
        self.assertIn("не ответил", str(ctx.exception))

    def test_sanitize_planner_query_removes_structured_qualifiers(self) -> None:
        raw = (
            'topic:ai-agent OR topic:automation language:python '
            'created:>=2024-01-01 stars:>=100 fork:false archived:false'
        )
        query = sanitize_planner_query(raw)
        self.assertNotIn("language:", query.lower())
        self.assertNotIn("created:", query.lower())
        self.assertNotIn("stars:", query.lower())
        self.assertNotIn("fork:", query.lower())
        self.assertNotIn("archived:", query.lower())
        self.assertIn("ai-agent", query.lower())
        self.assertIn("automation", query.lower())


if __name__ == "__main__":
    unittest.main()
