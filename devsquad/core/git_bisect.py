# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Autonomous Git Bisect & Regression Teleporter: binary-search regression hunting across commit history."""

import pathlib
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, Optional


class AutonomousBisect:
    """Automates binary-search git bisect to pinpoint the exact commit that introduced a failure."""

    def __init__(self, repo_root: Optional[pathlib.Path] = None, timeout_s: float = 300.0):
        self.repo_root = (repo_root or pathlib.Path.cwd()).resolve()
        self.timeout_s = timeout_s   # per commit

    def get_commit_history(self, count: int = 15) -> List[Dict[str, str]]:
        """Returns recent commits as structured dictionaries."""
        try:
            res = subprocess.check_output(
                ["git", "log", f"-n{count}", "--pretty=format:%H|%an|%ad|%s", "--date=short"],
                cwd=str(self.repo_root),
                stderr=subprocess.PIPE,
                text=True,
            ).strip()
            if not res:
                return []
            commits = []
            for line in res.split("\n"):
                parts = line.split("|", 3)
                if len(parts) == 4:
                    commits.append({
                        "sha": parts[0],
                        "author": parts[1],
                        "date": parts[2],
                        "message": parts[3],
                    })
            return commits
        except Exception:
            return []

    def get_commit_patch(self, sha: str) -> str:
        """Retrieves unified diff introduced by a specific commit."""
        try:
            return subprocess.check_output(
                ["git", "show", "--stat", "--patch", sha],
                cwd=str(self.repo_root),
                stderr=subprocess.PIPE,
                text=True,
                timeout=5.0,
            )[:3000]
        except Exception:
            return ""

    def simulate_bisect(
        self,
        commits: List[Dict[str, str]],
        evaluator_fn: Callable[[Dict[str, str]], bool],
    ) -> Dict[str, Any]:
        """Performs an in-memory binary search given a candidate list of commits in reverse chronological order (newest first).

        evaluator_fn returns True if the commit is 'good' (test passes), False if 'bad'.
        """
        if not commits:
            return {"status": "error", "error": "No commits provided for bisect."}

        # Commits list is newest to oldest: [C_newest (bad), ..., C_oldest (good)]
        # We search for the boundary where it changed from good to bad.
        low = 0
        high = len(commits) - 1
        steps = []
        culprit = None

        while low <= high:
            mid = (low + high) // 2
            candidate = commits[mid]
            passed = evaluator_fn(candidate)
            steps.append({
                "step": len(steps) + 1,
                "sha": candidate["sha"][:8],
                "message": candidate["message"],
                "verdict": "GOOD" if passed else "BAD",
            })

            if not passed:
                # Still bad, check older commits
                culprit = candidate
                low = mid + 1
            else:
                # It passed, regression happened more recently
                high = mid - 1

        if not culprit:
            culprit = commits[0]

        patch = self.get_commit_patch(culprit["sha"])

        return {
            "status": "isolated",
            "total_commits_evaluated": len(steps),
            "bisect_steps": steps,
            "culprit": culprit,
            "culprit_diff": patch,
            "remediation": {
                "strategy": "REVERT_OR_PATCH",
                "recommended_command": f"git revert --no-commit {culprit['sha']}",
                "summary": f"Regression introduced in commit {culprit['sha'][:8]} ('{culprit['message']}') by {culprit['author']}.",
            },
        }

    def _run_in_worktree(self, worktree: pathlib.Path, sha: str, argv: List[str]) -> bool:
        """Checks out one commit in the scratch worktree and runs the test command there. True means it passed."""
        subprocess.run(["git", "checkout", "-q", "--detach", "--force", sha], cwd=str(worktree), check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "clean", "-q", "-fdx"], cwd=str(worktree), check=True, capture_output=True, timeout=60)
        result = subprocess.run(argv, cwd=str(worktree), capture_output=True, timeout=self.timeout_s)
        return result.returncode == 0

    def bisect_with_test_command(
        self,
        test_command: str,
        lookback: int = 10,
    ) -> Dict[str, Any]:
        """Finds the commit that made `test_command` start failing, by running it on real commits.

        The command runs in a scratch git worktree, so the working tree, its uncommitted changes and
        the current branch are never touched. It is split like a shell command but not run through
        a shell. Exit code 0 counts as good, anything else as bad.
        """
        try:
            argv = shlex.split(test_command or "")
        except ValueError as e:
            return {"status": "error", "error": f"The test command can't be read: {e}"}
        if not argv:
            return {"status": "error", "error": "Give the command that shows the failure, for example: python3 -m pytest tests/test_login.py"}
        commits = self.get_commit_history(count=max(2, int(lookback)))
        if len(commits) < 2:
            return {"status": "error", "error": f"Need at least 2 commits to bisect, found {len(commits)}."}

        steps: List[Dict[str, Any]] = []
        verdicts: Dict[int, bool] = {}
        scratch = tempfile.mkdtemp(prefix="devsquad-bisect-")
        worktree = pathlib.Path(scratch) / "wt"
        try:
            subprocess.run(["git", "worktree", "add", "-q", "--detach", str(worktree), commits[0]["sha"]],
                           cwd=str(self.repo_root), check=True, capture_output=True, timeout=120)

            def check(i: int) -> bool:
                if i not in verdicts:
                    verdicts[i] = self._run_in_worktree(worktree, commits[i]["sha"], argv)
                    steps.append({"step": len(steps) + 1, "sha": commits[i]["sha"][:8], "message": commits[i]["message"],
                                  "verdict": "GOOD" if verdicts[i] else "BAD"})
                return verdicts[i]

            # commits are newest first: index 0 should fail and the oldest should pass
            if check(0):
                return {"status": "no_regression", "total_commits_evaluated": len(steps), "bisect_steps": steps,
                        "summary": "The command passes on the newest commit, so there is no regression to find."}
            oldest = len(commits) - 1
            if not check(oldest):
                return {"status": "older_than_window", "total_commits_evaluated": len(steps), "bisect_steps": steps,
                        "summary": f"The command also fails {len(commits)} commits back, so the regression is older. Try a larger lookback."}
            bad, good = 0, oldest
            while good - bad > 1:
                mid = (bad + good) // 2
                if check(mid):
                    good = mid
                else:
                    bad = mid
        except subprocess.TimeoutExpired:
            return {"status": "inconclusive", "bisect_steps": steps,
                    "error": f"The test command timed out after {self.timeout_s:g} seconds on one commit, so the search stopped."}
        except (subprocess.CalledProcessError, OSError) as e:
            detail = getattr(e, "stderr", b"") or b""
            detail = detail.decode("utf-8", "replace") if isinstance(detail, bytes) else str(detail)
            return {"status": "error", "bisect_steps": steps, "error": f"Bisect couldn't run: {(detail.strip() or str(e))[:300]}"}
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=str(self.repo_root), capture_output=True, timeout=60)
            shutil.rmtree(scratch, ignore_errors=True)

        culprit = commits[bad]
        return {
            "status": "isolated",
            "total_commits_evaluated": len(steps),
            "bisect_steps": steps,
            "culprit": culprit,
            "culprit_diff": self.get_commit_patch(culprit["sha"]),
            "remediation": {
                "strategy": "REVIEW_THEN_REVERT_OR_PATCH",
                "recommended_command": f"git revert --no-commit {culprit['sha']}",
                "summary": (f"The command passes on {commits[good]['sha'][:8]} and fails from {culprit['sha'][:8]} "
                            f"('{culprit['message']}') by {culprit['author']}. Check the diff before reverting."),
            },
        }
