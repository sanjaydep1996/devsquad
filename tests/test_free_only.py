# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""DevSquad only uses free AI: nothing it does can spend money, whatever keys are in the shell."""

import json
import os
import pathlib
import unittest
from unittest.mock import MagicMock, patch

import devsquad.llm as llm
from devsquad.llm.factory import get_provider
from devsquad.llm.providers import OllamaProvider, OpenAICompatibleProvider, TemplateProvider

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAID_KEYS = {"ANTHROPIC_API_KEY": "sk-ant-x", "OPENAI_API_KEY": "sk-x"}


class TestFreeOnly(unittest.TestCase):
    def setUp(self):
        p = patch.object(OllamaProvider, "is_available", return_value=False)
        p.start()
        self.addCleanup(p.stop)

    def test_no_paid_provider_exists(self):
        self.assertFalse(hasattr(llm, "AnthropicProvider"))

    def test_no_source_file_has_a_paid_ai_address(self):
        for path in (ROOT / "devsquad").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for address in ("api.anthropic.com", "api.openai.com", "openrouter.ai", "api.groq.com", "generativelanguage.googleapis.com"):
                self.assertNotIn(address, text, f"{address} in {path}")

    def test_keys_in_the_shell_are_ignored(self):
        with patch.dict(os.environ, PAID_KEYS, clear=True):
            self.assertIsInstance(get_provider(), TemplateProvider)

    def test_asking_for_a_paid_service_stays_free(self):
        for name in ("anthropic", "openai", "claude", "groq"):
            with patch.dict(os.environ, PAID_KEYS, clear=True):
                self.assertIsInstance(get_provider(provider_type=name), TemplateProvider, name)

    def test_discovery_never_suggests_a_paid_service(self):
        from devsquad.core.ai_discovery import AIDiscoveryEngine
        with patch.dict(os.environ, {**PAID_KEYS, "GEMINI_API_KEY": "AIzaX"}, clear=True):
            inventory = AIDiscoveryEngine().full_inventory()
        self.assertIn(inventory["suggested_provider"], ("ollama", "template"))

    def test_ollama_is_used_when_running(self):
        with patch.dict(os.environ, PAID_KEYS, clear=True), patch.object(OllamaProvider, "is_available", return_value=True):
            self.assertIsInstance(get_provider(), OllamaProvider)

    @patch("urllib.request.urlopen")
    def test_compatible_provider_refuses_cloud_addresses(self, urlopen):
        for url in ("https://api.example.com/v1", "https://localhost.evil.example/v1"):
            provider = OpenAICompatibleProvider(base_url=url, api_key="k")
            self.assertFalse(provider.is_available(), url)
            with self.assertRaisesRegex(RuntimeError, "this computer"):
                provider.complete("hi")
        urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_local_server_is_free_and_gets_no_paid_key(self, urlopen):
        resp = MagicMock()
        resp.read.return_value = json.dumps({"choices": [{"message": {"content": "hello"}}]}).encode()
        urlopen.return_value.__enter__.return_value = resp
        with patch.dict(os.environ, PAID_KEYS, clear=True):
            result = OpenAICompatibleProvider(base_url="http://localhost:1234/v1").complete("hi")
        self.assertEqual(result.cost_usd, 0.0)
        self.assertNotIn("Authorization", urlopen.call_args[0][0].headers)


if __name__ == "__main__":
    unittest.main()
