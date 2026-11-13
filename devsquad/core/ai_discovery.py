# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Local AI & Machine Environment Inspector: discovers installed AI CLIs, local models, and configurations."""

import json
import os
import pathlib
import shutil
import subprocess
import urllib.request
from typing import Any, Dict, List, Optional


class AIDiscoveryEngine:
    """Discovers installed AI CLIs (Claude, Gemini, Cursor, Aider, Ollama) and local model weights."""

    KNOWN_CLIS = [
        {"name": "claude", "display_name": "Claude Code CLI", "provider": "anthropic"},
        {"name": "gemini", "display_name": "Gemini Developer CLI", "provider": "google"},
        {"name": "gh", "display_name": "GitHub CLI (Copilot)", "provider": "github"},
        {"name": "aider", "display_name": "Aider Pair-Programmer", "provider": "aider"},
        {"name": "cursor", "display_name": "Cursor Editor CLI", "provider": "cursor"},
        {"name": "ollama", "display_name": "Ollama Local Daemon", "provider": "ollama"},
    ]

    def __init__(self, workspace_root: Optional[pathlib.Path] = None):
        self.workspace_root = (workspace_root or pathlib.Path.cwd()).resolve()

    def detect_installed_clis(self) -> List[Dict[str, Any]]:
        """Inspects PATH to locate installed developer AI command line tools."""
        results = []
        for item in self.KNOWN_CLIS:
            bin_name = item["name"]
            bin_path = shutil.which(bin_name)
            detected = bin_path is not None
            version = None

            if detected:
                try:
                    out = subprocess.check_output(
                        [bin_path, "--version"],
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=1.5,
                    ).strip()
                    version = out.split("\n")[0][:60]
                except Exception:
                    version = "Installed (executable)"

            results.append({
                "id": bin_name,
                "name": item["display_name"],
                "provider": item["provider"],
                "installed": detected,
                "path": bin_path or "",
                "version": version or "Not installed",
            })
        return results

    def detect_local_models(self, ollama_url: str = "http://localhost:11434") -> List[Dict[str, Any]]:
        """Queries local Ollama or OpenAI-compatible server for downloaded model weights."""
        models = []
        try:
            req = urllib.request.Request(f"{ollama_url.rstrip('/')}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    for m in data.get("models", []):
                        models.append({
                            "name": m.get("name"),
                            "size_bytes": m.get("size", 0),
                            "modified_at": m.get("modified_at", ""),
                            "runtime": "ollama",
                            "family": m.get("details", {}).get("family", "unknown"),
                        })
        except Exception:
            pass
        return models

    def detect_local_configs(self) -> Dict[str, Any]:
        """Inspects home directory and current workspace for existing AI configs and conventions."""
        home = pathlib.Path.home()
        configs = {
            "claude_config": (home / ".claude.json").exists() or (home / ".claude").exists(),
            "cursor_rules": (self.workspace_root / ".cursorrules").exists(),
            "claude_instructions": (self.workspace_root / "CLAUDE.md").exists(),
            "aider_config": (home / ".aider.conf.yml").exists() or (self.workspace_root / ".aider.conf.yml").exists(),
            "env_keys": {
                "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
                "google": bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")),
                "openai": bool(os.getenv("OPENAI_API_KEY")),
            },
        }
        return configs

    def full_inventory(self) -> Dict[str, Any]:
        """Compiles a complete developer machine AI hardware and software inventory."""
        clis = self.detect_installed_clis()
        models = self.detect_local_models()
        configs = self.detect_local_configs()

        installed_count = sum(1 for c in clis if c["installed"])
        has_local_daemon = len(models) > 0 or any(c["id"] == "ollama" and c["installed"] for c in clis)

        return {
            "status": "ready",
            "installed_clis": clis,
            "installed_cli_count": installed_count,
            "local_models": models,
            "local_model_count": len(models),
            "configs": configs,
            "has_local_daemon": has_local_daemon,
            # DevSquad only uses free AI, so a paid key never changes the suggestion
            "suggested_provider": "ollama" if has_local_daemon else "template",
        }
