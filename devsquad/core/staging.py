# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Staging Deck: manages task proposals, verified diffs, review status, and atomic workspace apply."""

import json
import pathlib
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional
from .diff import DiffEngine, FileDiff
from .runner import TestRunResult


@dataclass
class StagedTask:
    task_id: str
    goal: str
    status: str  # "staged", "tested_green", "tested_red", "applied", "rejected"
    created_at: float
    diffs: List[FileDiff] = field(default_factory=list)
    test_result: Optional[TestRunResult] = None
    git_branch: Optional[str] = None
    artifacts: Dict[str, str] = field(default_factory=dict)
    relay_logs: List[str] = field(default_factory=list)


class StagingDeck:
    """Manages proposed workspace mutations before they touch the real repository."""

    def __init__(self, root: Optional[pathlib.Path] = None):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.staging_dir = (self.root / ".devsquad" / "staging").resolve()
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def _sanitize_id(self, task_id: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_\-]", "", task_id)
        if not cleaned:
            raise ValueError(f"Invalid task ID: {task_id}")
        target = (self.staging_dir / cleaned).resolve()
        if not target.is_relative_to(self.staging_dir):
            raise ValueError(f"Directory traversal detected in task ID: {task_id}")
        return cleaned

    def create_task(self, task_id: str, goal: str) -> StagedTask:
        """Initializes a new staged task entry."""
        tid = self._sanitize_id(task_id)
        task = StagedTask(
            task_id=tid,
            goal=goal,
            status="staged",
            created_at=time.time(),
        )
        self.save_task(task)
        return task

    def save_task(self, task: StagedTask):
        """Persists task state to .devsquad/staging/<task_id>/manifest.json."""
        tid = self._sanitize_id(task.task_id)
        task_dir = self.staging_dir / tid
        task_dir.mkdir(parents=True, exist_ok=True)

        manifest = task_dir / "manifest.json"
        data = asdict(task)
        manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Save individual diff files for easy inspection
        diffs_dir = task_dir / "diffs"
        diffs_dir.mkdir(parents=True, exist_ok=True)
        for d in task.diffs:
            safe_name = d.file_path.replace("/", "__") + ".patch"
            (diffs_dir / safe_name).write_text(d.patch_text, encoding="utf-8")

    def load_task(self, task_id: str) -> Optional[StagedTask]:
        """Loads a task by ID."""
        try:
            tid = self._sanitize_id(task_id)
        except ValueError:
            return None
        manifest = self.staging_dir / tid / "manifest.json"
        if not manifest.exists():
            return None

        data = json.loads(manifest.read_text(encoding="utf-8"))
        diffs = [FileDiff(**d) for d in data.get("diffs", [])]
        test_res_data = data.get("test_result")
        test_res = TestRunResult(**test_res_data) if test_res_data else None

        return StagedTask(
            task_id=data["task_id"],
            goal=data["goal"],
            status=data["status"],
            created_at=data["created_at"],
            diffs=diffs,
            test_result=test_res,
            git_branch=data.get("git_branch"),
            artifacts=data.get("artifacts", {}),
            relay_logs=data.get("relay_logs", []),
        )

    def list_tasks(self) -> List[StagedTask]:
        """Returns all staged tasks sorted by creation date."""
        tasks = []
        if not self.staging_dir.exists():
            return []

        for p in sorted(self.staging_dir.iterdir(), reverse=True):
            if p.is_dir() and (p / "manifest.json").exists():
                t = self.load_task(p.name)
                if t:
                    tasks.append(t)
        return tasks

    def apply_task(self, task_id: str) -> List[str]:
        """Applies all staged file changes to the real repository."""
        task = self.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in Staging Deck.")

        results = []
        for d in task.diffs:
            ok, msg = DiffEngine.apply_file_change(
                self.root,
                d.file_path,
                d.modified_content,
                backup=True,
            )
            results.append(msg)
            if not ok:
                # Rollback previously applied in this task
                raise RuntimeError(f"Failed applying staged changes: {msg}")

        task.status = "applied"
        self.save_task(task)
        return results

    def rollback_task(self, task_id: str) -> List[str]:
        """Rolls back all files modified in a task using backups."""
        task = self.load_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found in Staging Deck.")

        results = []
        for d in task.diffs:
            ok, msg = DiffEngine.rollback_file_change(self.root, d.file_path)
            results.append(msg)

        task.status = "rejected"
        self.save_task(task)
        return results
