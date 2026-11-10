# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Ephemeral Git Worktree Isolation: manages sandboxed branch worktrees for safe multi-agent execution."""

import os
import pathlib
import shutil
import subprocess
from typing import Dict, List, Optional


class WorktreeManager:
    """Manages ephemeral git worktrees under .devsquad/worktrees/."""

    def __init__(self, root: pathlib.Path):
        self.root = root.resolve()
        self.worktree_dir = self.root / ".devsquad" / "worktrees"
        self.worktree_dir.mkdir(parents=True, exist_ok=True)

    def _run_git(self, args: List[str], cwd: Optional[pathlib.Path] = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git"] + args,
            cwd=str(cwd or self.root),
            capture_output=True,
            text=True,
            check=False,
        )

    def is_git_repo(self) -> bool:
        res = self._run_git(["rev-parse", "--is-inside-work-tree"])
        return res.returncode == 0

    def create_worktree(self, task_id: str, base_ref: str = "HEAD") -> pathlib.Path:
        """Spins up an ephemeral isolated git worktree for a task."""
        target_path = self.worktree_dir / task_id
        branch_name = f"devsquad/{task_id}"

        if target_path.exists():
            return target_path

        if not self.is_git_repo():
            # Fallback to directory copy for non-git workspaces
            shutil.copytree(self.root, target_path, ignore=shutil.ignore_patterns(".devsquad", ".git", "__pycache__", "node_modules"))
            return target_path

        # Create branch and isolated worktree
        res = self._run_git(["worktree", "add", "-b", branch_name, str(target_path), base_ref])
        if res.returncode != 0:
            # If branch already exists, checkout without -b
            res = self._run_git(["worktree", "add", str(target_path), branch_name])
            if res.returncode != 0:
                # Direct directory fallback
                shutil.copytree(self.root, target_path, ignore=shutil.ignore_patterns(".devsquad", ".git", "__pycache__", "node_modules"))

        return target_path

    def cleanup_worktree(self, task_id: str, delete_branch: bool = True) -> bool:
        """Removes an ephemeral worktree and cleans up git metadata."""
        target_path = self.worktree_dir / task_id
        branch_name = f"devsquad/{task_id}"

        if not target_path.exists():
            return False

        if self.is_git_repo():
            self._run_git(["worktree", "remove", "--force", str(target_path)])
            self._run_git(["worktree", "prune"])
            if delete_branch:
                self._run_git(["branch", "-D", branch_name])

        if target_path.exists():
            shutil.rmtree(target_path, ignore_errors=True)

        return True

    def list_worktrees(self) -> List[Dict]:
        """Returns all active worktrees associated with this workspace."""
        if not self.is_git_repo():
            if not self.worktree_dir.exists():
                return []
            return [{"task_id": p.name, "path": str(p), "branch": "local"} for p in self.worktree_dir.iterdir() if p.is_dir()]

        res = self._run_git(["worktree", "list", "--porcelain"])
        if res.returncode != 0:
            return []

        worktrees = []
        current = {}
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                if current and ".devsquad/worktrees" in current.get("worktree", ""):
                    p = pathlib.Path(current["worktree"])
                    worktrees.append({
                        "task_id": p.name,
                        "path": current.get("worktree"),
                        "branch": current.get("branch", "").replace("refs/heads/", ""),
                    })
                current = {}
                continue
            if line.startswith("worktree "):
                current["worktree"] = line[9:].strip()
            elif line.startswith("branch "):
                current["branch"] = line[7:].strip()

        if current and ".devsquad/worktrees" in current.get("worktree", ""):
            p = pathlib.Path(current["worktree"])
            worktrees.append({
                "task_id": p.name,
                "path": current.get("worktree"),
                "branch": current.get("branch", "").replace("refs/heads/", ""),
            })

        return worktrees
