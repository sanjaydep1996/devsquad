# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Base interface and dataclasses for DevSquad LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class LLMResponse:
    text: str
    usage: LLMUsage
    latency_ms: float
    model: str
    provider: str
    cost_usd: float = 0.0
    raw: Dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    """Abstract base class for all DevSquad LLM providers."""

    def __init__(self, model: str):
        self.model = model

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    def is_available(self) -> bool:
        pass

    @abstractmethod
    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
    ) -> LLMResponse:
        pass
