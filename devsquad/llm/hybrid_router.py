# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Hybrid Model Router: routes tasks between local offline runtimes (Ollama/vLLM) and cloud models."""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from .base import BaseProvider, LLMResponse, LLMUsage


@dataclass
class LocalModelInfo:
    """Metadata about a detected local model."""
    name: str
    runtime: str  # 'ollama' or 'vllm'
    size_bytes: int
    parameter_size: str
    quantization: str
    is_ready: bool


class HybridModelRouter:
    """Manages local vs cloud AI model dispatch and tracks cost savings."""

    # Benchmark pricing for savings estimation ($ per 1M tokens)
    FRONTIER_INPUT_PRICE_PER_M = 3.00
    FRONTIER_OUTPUT_PRICE_PER_M = 15.00

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        vllm_url: str = "http://localhost:8000/v1",
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.vllm_url = vllm_url.rstrip("/")
        self.total_local_input_tokens = 0
        self.total_local_output_tokens = 0

    def discover_local_models(self) -> List[LocalModelInfo]:
        """Discovers running local models from Ollama and vLLM."""
        models: List[LocalModelInfo] = []

        # 1. Query Ollama /api/tags
        try:
            req = urllib.request.Request(f"{self.ollama_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    details = m.get("details", {})
                    models.append(
                        LocalModelInfo(
                            name=m.get("name", "unknown"),
                            runtime="ollama",
                            size_bytes=m.get("size", 0),
                            parameter_size=details.get("parameter_size", "unknown"),
                            quantization=details.get("quantization_level", "unknown"),
                            is_ready=True,
                        )
                    )
        except Exception:
            pass

        # 2. Query vLLM /v1/models
        try:
            req = urllib.request.Request(f"{self.vllm_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("data", []):
                    models.append(
                        LocalModelInfo(
                            name=m.get("id", "vllm-model"),
                            runtime="vllm",
                            size_bytes=0,
                            parameter_size="unknown",
                            quantization="FP16/AWQ",
                            is_ready=True,
                        )
                    )
        except Exception:
            pass

        # Default fallbacks if local daemon is temporarily offline
        if not models:
            models.append(
                LocalModelInfo(
                    name="qwen2.5-coder:7b",
                    runtime="ollama",
                    size_bytes=4700000000,
                    parameter_size="7.6B",
                    quantization="Q4_K_M",
                    is_ready=False,
                )
            )
            models.append(
                LocalModelInfo(
                    name="deepseek-coder-v2:lite",
                    runtime="ollama",
                    size_bytes=8900000000,
                    parameter_size="16B",
                    quantization="Q4_K_M",
                    is_ready=False,
                )
            )

        return models

    def record_usage(self, input_tokens: int, output_tokens: int) -> float:
        """Records local token usage and returns calculated dollar savings."""
        self.total_local_input_tokens += input_tokens
        self.total_local_output_tokens += output_tokens
        return self.calculate_savings_usd()

    def calculate_savings_usd(self) -> float:
        """Calculates total dollar savings by routing tokens locally instead of cloud APIs."""
        saved_input = (self.total_local_input_tokens / 1_000_000.0) * self.FRONTIER_INPUT_PRICE_PER_M
        saved_output = (self.total_local_output_tokens / 1_000_000.0) * self.FRONTIER_OUTPUT_PRICE_PER_M
        return round(saved_input + saved_output, 4)

    def get_router_status(self) -> Dict[str, Any]:
        """Returns the current status of the Hybrid Router."""
        models = self.discover_local_models()
        any_ready = any(m.is_ready for m in models)
        savings = self.calculate_savings_usd()

        return {
            "mode": "hybrid",
            "active_runtime": "ollama" if any_ready else "cloud_fallback",
            "local_daemon_online": any_ready,
            "models_available": [
                {
                    "name": m.name,
                    "runtime": m.runtime,
                    "parameter_size": m.parameter_size,
                    "quantization": m.quantization,
                    "ready": m.is_ready,
                }
                for m in models
            ],
            "metrics": {
                "local_input_tokens": self.total_local_input_tokens,
                "local_output_tokens": self.total_local_output_tokens,
                "total_local_tokens": self.total_local_input_tokens + self.total_local_output_tokens,
                "estimated_savings_usd": savings,
            },
        }
