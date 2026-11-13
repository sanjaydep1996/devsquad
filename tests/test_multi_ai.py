# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for DevSquad's free AI providers: local models are used, paid services never are."""

import os
import unittest
from unittest.mock import patch

from devsquad.llm.factory import get_provider
from devsquad.llm.providers import OllamaProvider, OpenAICompatibleProvider, TemplateProvider

PAID_KEYS = {"ANTHROPIC_API_KEY": "sk-ant-test", "GEMINI_API_KEY": "AIzaSyTest", "GOOGLE_API_KEY": "AIzaSyTest", "OPENAI_API_KEY": "sk-test"}


class TestFreeProviders(unittest.TestCase):
    def test_default_is_free_and_local(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            self.assertIsInstance(get_provider(), TemplateProvider)

    def test_ollama_preferred_when_running(self):
        with patch.dict(os.environ, PAID_KEYS, clear=True), patch.object(OllamaProvider, "is_available", return_value=True):
            self.assertIsInstance(get_provider(), OllamaProvider)

    def test_paid_keys_never_pick_a_paid_service(self):
        with patch.dict(os.environ, PAID_KEYS, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            self.assertIsInstance(get_provider(), TemplateProvider)

    def test_asking_for_a_paid_service_stays_free(self):
        for name in ("anthropic", "claude", "gemini", "google", "openai", "chatgpt"):
            with patch.dict(os.environ, PAID_KEYS, clear=True):
                self.assertIsInstance(get_provider(provider_type=name), TemplateProvider, name)

    def test_a_local_openai_style_server_is_allowed(self):
        with patch.dict(os.environ, {"DEVSQUAD_LOCAL_LLM_URL": "http://localhost:1234/v1"}, clear=True):
            self.assertIsInstance(get_provider(provider_type="openai-compatible"), OpenAICompatibleProvider)

    def test_template_provider_synthesis(self):
        res = TemplateProvider().complete("Generate a unit test for payment gateway")
        self.assertIn("unittest", res.text)
        self.assertEqual(res.cost_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
