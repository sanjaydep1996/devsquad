# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Multi-Tool Ingestion & Memory Lake: unifies session context and rules across Claude Code, Cursor, Aider, and DevSquad."""

import json
import os
import pathlib
import re
import time
from typing import Dict, List, Optional


class MemoryLake:
    """Aggregates and persists engineering memory and cross-tool session logs."""

    def __init__(self, root: pathlib.Path):
        self.root = root.resolve()
        self.memory_file = self.root / ".devsquad" / "memory.json"
        self.data: Dict = {
            "version": "1.0.0",
            "last_updated": 0,
            "conventions": [],
            "frequent_files": {},
            "sessions": [],
            "known_pitfalls": [],
        }
        self.load()

    def load(self):
        if self.memory_file.exists():
            try:
                self.data = json.loads(self.memory_file.read_text(encoding="utf-8"))
            except Exception:
                pass

    def save(self):
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.data["last_updated"] = time.time()
        self.memory_file.write_text(json.dumps(self.data, indent=2), encoding="utf-8")

    def ingest_cursor(self) -> int:
        """Ingests .cursorrules and cursor configurations."""
        count = 0
        cursorrules = self.root / ".cursorrules"
        if cursorrules.exists():
            try:
                content = cursorrules.read_text(encoding="utf-8")
                rules = [r.strip() for r in content.splitlines() if r.strip() and not r.startswith("#")]
                for r in rules:
                    if r not in self.data["conventions"]:
                        self.data["conventions"].append(f"[Cursor] {r}")
                        count += 1
            except Exception:
                pass
        return count

    def ingest_aider(self) -> int:
        """Ingests .aider.chat.history.md if present."""
        count = 0
        aider_hist = self.root / ".aider.chat.history.md"
        if aider_hist.exists():
            try:
                text = aider_hist.read_text(encoding="utf-8")
                # Extract user prompts
                prompts = re.findall(r"^####\s+(.+)$", text, re.MULTILINE)
                for p in prompts[-10:]:
                    self.data["sessions"].append({
                        "tool": "aider",
                        "summary": p.strip(),
                        "timestamp": time.time(),
                    })
                    count += 1
            except Exception:
                pass
        return count

    def ingest_claude_code(self) -> int:
        """Ingests Claude Code project configuration and conventions."""
        count = 0
        claude_md = self.root / "CLAUDE.md"
        if claude_md.exists():
            try:
                text = claude_md.read_text(encoding="utf-8")
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("- ") or line.startswith("* "):
                        clean_rule = line[2:].strip()
                        if clean_rule and clean_rule not in self.data["conventions"]:
                            self.data["conventions"].append(f"[Claude Code] {clean_rule}")
                            count += 1
            except Exception:
                pass
        return count

    def record_task_outcome(self, task_id: str, goal: str, passed: bool, touched_files: List[str], error_trace: Optional[str] = None):
        """Records a completed DevSquad task into the memory lake."""
        self.data["sessions"].append({
            "tool": "devsquad",
            "task_id": task_id,
            "goal": goal,
            "passed": passed,
            "files": touched_files,
            "timestamp": time.time(),
        })

        for f in touched_files:
            self.data["frequent_files"][f] = self.data["frequent_files"].get(f, 0) + 1

        if not passed and error_trace:
            first_line = error_trace.strip().splitlines()[-1] if error_trace.strip() else "Unknown failure"
            if first_line not in self.data["known_pitfalls"]:
                self.data["known_pitfalls"].append(first_line[:200])

        self.save()

    def ingest_all(self) -> Dict[str, int]:
        """Ingests across all supported AI coding tool sources."""
        results = {
            "cursor": self.ingest_cursor(),
            "aider": self.ingest_aider(),
            "claude_code": self.ingest_claude_code(),
        }
        self.save()
        return results

    def get_agent_context(self) -> str:
        """Produces formatted memory context for agent prompts."""
        conventions = "\n".join(f"- {c}" for c in self.data.get("conventions", [])[:8])
        pitfalls = "\n".join(f"- Avoid: {p}" for p in self.data.get("known_pitfalls", [])[:5])

        sections = []
        if conventions:
            sections.append(f"### Project Conventions & Ingested Rules:\n{conventions}")
        if pitfalls:
            sections.append(f"### Known Past Pitfalls to Avoid:\n{pitfalls}")

        return "\n\n".join(sections)
