# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Provider factory. DevSquad only uses free AI: Ollama, another local server, or templates."""

import os
from typing import Optional
from .base import BaseProvider
from .providers import OllamaProvider, OpenAICompatibleProvider, TemplateProvider


def get_provider(
    provider_type: Optional[str] = None,
    model: Optional[str] = None,
) -> BaseProvider:
    """Returns a free provider. Keys for paid services are never read, and paid names fall back to templates."""
    ptype = provider_type or os.getenv("DEVSQUAD_PROVIDER")

    if ptype == "ollama":
        return OllamaProvider(model=model or "qwen2.5-coder:7b")
    if ptype == "openai-compatible":
        local = OpenAICompatibleProvider(
            base_url=os.getenv("DEVSQUAD_LOCAL_LLM_URL", "http://localhost:1234/v1"),
            model=model or "local-model",
        )
        return local if local.is_available() else TemplateProvider()
    if ptype:
        # "template", or a paid service DevSquad doesn't support
        return TemplateProvider()

    # Nothing requested: use Ollama if it's running, because it's free and stays on this computer
    ollama = OllamaProvider(model=model or "qwen2.5-coder:7b")
    if ollama.is_available():
        return ollama
    return TemplateProvider()
