# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Base agent class for DevSquad specialized personas."""

from abc import ABC
from dataclasses import dataclass, field
from typing import List, Optional
from ..llm.base import BaseProvider, LLMResponse


@dataclass
class AgentMessage:
    sender: str
    content: str
    timestamp: float


class BaseAgent(ABC):
    """Base class for all DevSquad agent personas."""

    def __init__(self, name: str, role: str, system_prompt: str, provider: BaseProvider):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.provider = provider
        self.history: List[AgentMessage] = []

    def think_and_act(self, prompt: str, max_tokens: int = 2500) -> LLMResponse:
        """Executes a completion with the persona's system prompt."""
        return self.provider.complete(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=max_tokens,
        )
