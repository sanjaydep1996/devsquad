# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Provider factory: resolves the best available provider with local-first priority."""

import os
from typing import Optional
from .base import BaseProvider
from .providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    TemplateProvider,
)


def get_provider(
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseProvider:
    """Returns requested provider or auto-detects the best available one (local-first)."""
    ptype = provider_type or os.getenv("DEVSQUAD_PROVIDER")

    # Explicit provider requests
    if ptype in ("anthropic", "claude"):
        return AnthropicProvider(model=model or "claude-3-5-sonnet-latest")
    if ptype in ("gemini", "google"):
        return GeminiProvider(model=model or "gemini-2.0-flash")
    if ptype in ("openai", "chatgpt"):
        return OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            model=model or "gpt-4o-mini",
        )
    if ptype == "ollama":
        return OllamaProvider(model=model or "qwen2.5-coder:7b")
    if ptype == "openai-compatible":
        return OpenAICompatibleProvider(
            base_url=os.getenv("DEVSQUAD_LOCAL_LLM_URL", "http://localhost:1234/v1"),
            model=model or "local-model",
        )
    if ptype == "template":
        return TemplateProvider()

    # Auto-detection: 1. Local Ollama if available
    ollama = OllamaProvider(model=model or "qwen2.5-coder:7b")
    if ollama.is_available():
        return ollama

    # 2. Check environment keys
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model=model or "claude-3-5-sonnet-latest")
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return GeminiProvider(model=model or "gemini-2.0-flash")
    if os.getenv("OPENAI_API_KEY"):
        return OpenAICompatibleProvider(base_url="https://api.openai.com/v1", model=model or "gpt-4o-mini")

    # 3. Fallback to deterministic offline template mode
    return TemplateProvider()
