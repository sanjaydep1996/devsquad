# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Zero-dependency multi-AI providers using Python standard library urllib."""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional
from .base import BaseProvider, LLMResponse, LLMUsage


class OllamaProvider(BaseProvider):
    """Local, private, and free provider using local Ollama daemon."""

    def __init__(self, model: str = "qwen2.5-coder:7b", base_url: str = "http://localhost:11434"):
        super().__init__(model=model)
        self.base_url = base_url.rstrip("/")

    @property
    def provider_name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        start_time = time.time()
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            }
        }
        if system:
            payload["system"] = system

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Ollama connection failed ({self.base_url}): {e}") from e

        latency_ms = (time.time() - start_time) * 1000.0
        prompt_tokens = data.get("prompt_eval_count", len(prompt) // 4)
        output_tokens = data.get("eval_count", len(data.get("response", "")) // 4)

        return LLMResponse(
            text=data.get("response", "").strip(),
            usage=LLMUsage(input_tokens=prompt_tokens, output_tokens=output_tokens),
            latency_ms=latency_ms,
            model=self.model,
            provider=self.provider_name,
            cost_usd=0.0,
            raw=data,
        )


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider using Messages API via standard library urllib."""

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-latest"):
        super().__init__(model=model)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY", "")

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.startswith("sk-ant"))

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError("AnthropicProvider requires a valid ANTHROPIC_API_KEY.")

        start_time = time.time()
        url = "https://api.anthropic.com/v1/messages"

        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Anthropic API call failed: {e}") from e

        latency_ms = (time.time() - start_time) * 1000.0
        content_blocks = data.get("content", [])
        text_output = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")

        usage_raw = data.get("usage", {})
        in_tok = usage_raw.get("input_tokens", len(prompt) // 4)
        out_tok = usage_raw.get("output_tokens", len(text_output) // 4)

        # Estimate pricing ($3/M in, $15/M out for Sonnet)
        cost = (in_tok * 0.000003) + (out_tok * 0.000015)

        return LLMResponse(
            text=text_output.strip(),
            usage=LLMUsage(input_tokens=in_tok, output_tokens=out_tok),
            latency_ms=latency_ms,
            model=self.model,
            provider=self.provider_name,
            cost_usd=round(cost, 6),
            raw=data,
        )


class GeminiProvider(BaseProvider):
    """Google Gemini provider via standard library urllib."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-2.0-flash"):
        super().__init__(model=model)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

    @property
    def provider_name(self) -> str:
        return "gemini"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        if not self.is_available():
            raise RuntimeError("GeminiProvider requires GEMINI_API_KEY or GOOGLE_API_KEY.")

        start_time = time.time()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these guidelines."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            }
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"Gemini API call failed: {e}") from e

        latency_ms = (time.time() - start_time) * 1000.0
        candidates = data.get("candidates", [])
        text_output = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text_output = "".join(p.get("text", "") for p in parts)

        usage_meta = data.get("usageMetadata", {})
        in_tok = usage_meta.get("promptTokenCount", len(prompt) // 4)
        out_tok = usage_meta.get("candidatesTokenCount", len(text_output) // 4)

        return LLMResponse(
            text=text_output.strip(),
            usage=LLMUsage(input_tokens=in_tok, output_tokens=out_tok),
            latency_ms=latency_ms,
            model=self.model,
            provider=self.provider_name,
            cost_usd=round((in_tok * 0.0000001) + (out_tok * 0.0000004), 6),
            raw=data,
        )


class OpenAICompatibleProvider(BaseProvider):
    """OpenAI / ChatGPT / Local server provider (LM Studio, llama.cpp, vLLM, OpenAI)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        super().__init__(model=model)
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    @property
    def provider_name(self) -> str:
        return "openai" if "api.openai.com" in self.base_url else "openai-compatible"

    def is_available(self) -> bool:
        if "api.openai.com" in self.base_url:
            return bool(self.api_key)
        # Local server check
        return urllib.parse.urlsplit(self.base_url).hostname in ("localhost", "127.0.0.1", "::1")

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        start_time = time.time()
        url = f"{self.base_url}/chat/completions"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            raise RuntimeError(f"OpenAI compatible endpoint failed ({url}): {e}") from e

        latency_ms = (time.time() - start_time) * 1000.0
        choices = data.get("choices", [])
        text_output = choices[0].get("message", {}).get("content", "").strip() if choices else ""

        usage_raw = data.get("usage") or {}
        in_tok = usage_raw.get("prompt_tokens", len(prompt) // 4)
        out_tok = usage_raw.get("completion_tokens", len(text_output) // 4)

        is_cloud = "api.openai.com" in self.base_url
        cost = ((in_tok * 0.00000015) + (out_tok * 0.0000006)) if is_cloud else 0.0

        return LLMResponse(
            text=text_output,
            usage=LLMUsage(input_tokens=in_tok, output_tokens=out_tok),
            latency_ms=latency_ms,
            model=self.model,
            provider=self.provider_name,
            cost_usd=round(cost, 6),
            raw=data,
        )


class TemplateProvider(BaseProvider):
    """Deterministic fallback provider for testing and offline demo modes."""

    def __init__(self, model: str = "template-offline"):
        super().__init__(model=model)

    @property
    def provider_name(self) -> str:
        return "template"

    def is_available(self) -> bool:
        return True

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        time.sleep(0.05)
        # Deterministic code synthesis based on keywords in prompt
        if "test" in prompt.lower() or "qa" in prompt.lower():
            code = (
                "import unittest\n\n"
                "class TestFeature(unittest.TestCase):\n"
                "    def test_example(self):\n"
                "        self.assertTrue(True)\n\n"
                "if __name__ == '__main__':\n"
                "    unittest.main()\n"
            )
        elif "spec" in prompt.lower() or "architect" in prompt.lower():
            code = (
                "# Architecture Specification\n\n"
                "## Objectives\n"
                "- Implement clean modular service boundaries\n"
                "- Enforce test-driven verification\n"
            )
        else:
            code = (
                "# Implementation generated by DevSquad Alpha\n"
                "def execute_task():\n"
                "    return {'status': 'success', 'verified': True}\n"
            )

        return LLMResponse(
            text=code,
            usage=LLMUsage(input_tokens=len(prompt) // 4, output_tokens=len(code) // 4),
            latency_ms=50.0,
            model=self.model,
            provider=self.provider_name,
            cost_usd=0.0,
        )
