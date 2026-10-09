"""Contract tests for user-controlled Qwen thinking mode. No API calls or billing."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from grading_api import openai_client


class QwenThinkingModeTests(unittest.TestCase):
    def send(self, model: str, setting: str | None, max_tokens: int = 450) -> dict:
        client = openai_client.OpenAIResponsesClient.__new__(
            openai_client.OpenAIResponsesClient
        )
        # The transport is mocked: no real API key, network, or paid request.
        client._settings = SimpleNamespace(openai_api_key="test-key")
        sent_bodies: list[dict] = []

        def mock_send(_url, body, _curl):
            sent_bodies.append(json.loads(body))
            return '{"choices": []}'

        with patch.dict(os.environ, {}, clear=False), \
                patch.object(openai_client, "_find_curl_executable", return_value="curl"), \
                patch.object(client, "_post_json_with_curl", side_effect=mock_send):
            os.environ.pop("GRADING_QWEN_THINKING_MODE", None)
            if setting is not None:
                os.environ["GRADING_QWEN_THINKING_MODE"] = setting
            response = client._post_json("https://example.test/v1/chat/completions", {
                "model": model,
                "messages": [{"role": "user", "content": "hello"}],
                "max_tokens": max_tokens,
            })
        self.assertEqual(response, {"choices": []})
        self.assertEqual(len(sent_bodies), 1)
        return sent_bodies[0]

    def test_dated_qwen_flash_enabled(self):
        request = self.send("qwen3.7-flash-2026-07-15", "on")
        self.assertIs(request["enable_thinking"], True)
        self.assertEqual(request["max_tokens"], 4096)

    def test_dated_qwen_flash_disabled(self):
        request = self.send("qwen3.7-flash-2026-07-15", "off")
        self.assertIs(request["enable_thinking"], False)
        self.assertEqual(request["max_tokens"], 450)

    def test_legacy_unconfigured_qwen_flash_remains_disabled(self):
        request = self.send("qwen3.7-flash-2026-07-15", None)
        self.assertIs(request["enable_thinking"], False)

    def test_qwen_plus_can_use_explicit_setting(self):
        request = self.send("qwen3.7-plus", "on")
        self.assertIs(request["enable_thinking"], True)

    def test_gpt_unchanged_even_when_toggle_on(self):
        request = self.send("gpt-6.1-sol", "on")
        self.assertNotIn("enable_thinking", request)
        self.assertEqual(request["max_tokens"], 450)

    def test_non_qwen_model_unaffected_when_off(self):
        request = self.send("deepseek-chat", "off")
        self.assertNotIn("enable_thinking", request)

    def test_legacy_plus_keeps_provider_default(self):
        request = self.send("qwen3.7-plus", None)
        self.assertNotIn("enable_thinking", request)


if __name__ == "__main__":
    unittest.main()
