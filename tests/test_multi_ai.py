# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Tests for DevSquad multi-AI providers and local-first fallback behavior."""

import os
import unittest
from unittest.mock import patch

import devsquad.llm as llm
from devsquad.llm.factory import get_provider
from devsquad.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    TemplateProvider,
)


class TestMultiAIProviders(unittest.TestCase):
    def test_default_is_free_and_local(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            provider = get_provider()
            self.assertIsInstance(provider, TemplateProvider)
            self.assertEqual(provider.provider_name, "template")

    def test_ollama_preferred_when_running(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(OllamaProvider, "is_available", return_value=True):
            provider = get_provider()
            self.assertIsInstance(provider, OllamaProvider)
            self.assertEqual(provider.provider_name, "ollama")

    def test_explicit_provider_instantiation(self):
        anthropic = get_provider(provider_type="anthropic")
        self.assertIsInstance(anthropic, AnthropicProvider)

        gemini = get_provider(provider_type="gemini")
        self.assertIsInstance(gemini, GeminiProvider)

        openai = get_provider(provider_type="openai")
        self.assertIsInstance(openai, OpenAICompatibleProvider)

        ollama = get_provider(provider_type="ollama")
        self.assertIsInstance(ollama, OllamaProvider)

    def test_env_key_routing(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-test"}, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            provider = get_provider()
            self.assertIsInstance(provider, AnthropicProvider)

        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyTest"}, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            provider = get_provider()
            self.assertIsInstance(provider, GeminiProvider)

        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True), patch.object(OllamaProvider, "is_available", return_value=False):
            provider = get_provider()
            self.assertIsInstance(provider, OpenAICompatibleProvider)

    def test_template_provider_synthesis(self):
        p = TemplateProvider()
        self.assertTrue(p.is_available())
        res = p.complete("Generate a unit test for payment gateway")
        self.assertIn("unittest", res.text)
        self.assertEqual(res.cost_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
