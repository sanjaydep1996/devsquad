# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Provider factory: resolves the best available provider with local-first priority."""

import os
from typing import Optional
from .base import BaseProvider
from .providers import (
    AnthropicProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    TemplateProvider,
)


def get_provider(
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseProvider:
    """Returns the requested provider or auto-detects the best available one."""
    ptype = provider_type or os.getenv("DEVSQUAD_PROVIDER")

    if ptype == "ollama":
        return OllamaProvider(model=model or "qwen2.5-coder:7b")
    elif ptype == "anthropic":
        return AnthropicProvider(model=model or "claude-3-5-sonnet-20241022")
    elif ptype == "openai-compatible":
        return OpenAICompatibleProvider(model=model or "local-model")
    elif ptype == "template":
        return TemplateProvider()

    # Automatic Detection:
    # 1. Local Ollama (private, free default)
    ollama = OllamaProvider(model=model or "qwen2.5-coder:7b")
    if ollama.is_available():
        return ollama

    # 2. Anthropic API key in environment
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model=model or "claude-3-5-sonnet-20241022")

    # 3. OpenAI key in environment
    if os.getenv("OPENAI_API_KEY"):
        return OpenAICompatibleProvider(
            base_url="https://api.openai.com/v1",
            api_key=os.getenv("OPENAI_API_KEY"),
            model=model or "gpt-4o-mini",
        )

    # 4. Fallback to TemplateProvider
    return TemplateProvider()
