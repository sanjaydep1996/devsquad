# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""First-run setup: what a new user needs before the agents can do real work, and the next step for each gap."""

import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

RECOMMENDED_MODEL = "qwen2.5-coder:7b"
VISION_MODELS = ("llava", "llama3.2-vision", "moondream", "bakllava", "minicpm-v", "qwen2.5vl")
MODEL_NAME = re.compile(r"[a-z0-9][a-z0-9._/-]{0,80}(:[a-z0-9._-]{1,40})?")


def vision_model(models: List[str]) -> Optional[str]:
    """The first installed model that can look at images, if any."""
    for name in models:
        if name.split(":")[0].split("/")[-1] in VISION_MODELS:
            return name
    return None


class SetupCheck:
    def __init__(self, root: Optional[pathlib.Path] = None, ollama_url: str = "http://localhost:11434",
                 which: Callable[[str], Optional[str]] = shutil.which):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.ollama_url = ollama_url.rstrip("/")
        self.which = which

    def _get(self, path: str, timeout: float = 1.5) -> Optional[Dict[str, Any]]:
        try:
            with urllib.request.urlopen(f"{self.ollama_url}{path}", timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            return None

    def models(self) -> Optional[List[str]]:
        """Installed Ollama models, or None when Ollama isn't running."""
        tags = self._get("/api/tags")
        if tags is None:
            return None
        return sorted(m.get("name", "") for m in tags.get("models", []) if m.get("name"))

    def status(self) -> Dict[str, Any]:
        models = self.models()
        running = models is not None
        has_coder = bool(models) and any(m.split(":")[0] == RECOMMENDED_MODEL.split(":")[0] for m in models)
        seeing = vision_model(models or [])
        try:
            import pytest  # noqa: F401
            has_pytest = True
        except ImportError:
            has_pytest = False
        checks = [
            {"id": "ollama_installed", "ok": bool(self.which("ollama")) or running, "title": "Ollama is installed",
             "fix": "Install Ollama from ollama.com. It's free and runs AI models on your computer."},
            {"id": "ollama_running", "ok": running, "title": "Ollama is running",
             "fix": "Start it with `ollama serve`, or open the Ollama app."},
            {"id": "coding_model", "ok": has_coder, "title": f"A coding model is downloaded ({RECOMMENDED_MODEL})",
             "fix": f"Download it here, or run `ollama pull {RECOMMENDED_MODEL}` (about 4.7 GB).", "pull": RECOMMENDED_MODEL},
            {"id": "vision_model", "ok": bool(seeing), "optional": True, "title": "A model that can read images (optional)",
             "fix": "Download `llava` so agents can read screenshots and mockups (about 4.7 GB).", "pull": "llava"},
            {"id": "git_repo", "ok": (self.root / ".git").exists(), "title": "The project folder is a git repository",
             "fix": "Run `git init` in your project folder so changes can be reviewed and undone."},
            {"id": "pytest", "ok": has_pytest, "optional": True, "title": "pytest is installed (optional)",
             "fix": f"Run `{pathlib.Path(sys.executable).name} -m pip install pytest` so the agents' tests can run."},
        ]
        needed = [c for c in checks if not c["ok"] and not c.get("optional")]
        return {
            "ready": not needed,
            "mode": "real AI on this computer" if running and has_coder else "template mode (example output, not AI)",
            "models": models or [],
            "vision_model": seeing,
            "checks": checks,
            "next_step": needed[0]["fix"] if needed else "You're set. Describe a feature or an app to build.",
        }

    def pull(self, model: str, timeout: float = 3600.0) -> Dict[str, Any]:
        """Downloads a model through Ollama. Can take many minutes on a slow connection."""
        model = (model or "").strip().lower()
        if not MODEL_NAME.fullmatch(model):
            return {"ok": False, "error": "That isn't a valid model name."}
        if self.models() is None:
            return {"ok": False, "error": "Ollama isn't running. Start it first."}
        body = json.dumps({"name": model, "stream": False}).encode("utf-8")
        req = urllib.request.Request(f"{self.ollama_url}/api/pull", data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"ok": False, "error": f"The download failed: {e}"}
        if result.get("error"):
            return {"ok": False, "error": result["error"]}
        return {"ok": True, "model": model, "status": result.get("status", "success")}
