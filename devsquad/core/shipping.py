# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Ship from the Review Desk: a reviewed change becomes a branch, a commit and a pull request.

The change is committed in a separate git worktree, so your working copy, your current branch and
anything uncommitted are never touched. Nothing is pushed until you confirm the preview.
"""

import pathlib
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Dict, List, Optional

Run = Callable[[List[str], Optional[str]], subprocess.CompletedProcess]


def _run(argv: List[str], cwd: Optional[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120)


class ShipError(ValueError):
    """Shown to the person as is."""


class Shipper:
    def __init__(self, root: pathlib.Path, run: Optional[Run] = None):
        self.root = root.resolve()
        self.run = run or _run

    def _git(self, *args: str, cwd: Optional[pathlib.Path] = None) -> subprocess.CompletedProcess:
        return self.run(["git", *args], str(cwd or self.root))

    @staticmethod
    def branch_for(task: Any) -> str:
        raw = (getattr(task, "git_branch", "") or f"devsquad/{task.task_id}").strip()
        clean = re.sub(r"[^A-Za-z0-9._/-]+", "-", raw).strip("-/.")
        clean = re.sub(r"\.\.+|//+", "-", clean)
        return clean[:80] or f"devsquad/{task.task_id}"

    def _safe_path(self, rel: str) -> str:
        p = pathlib.PurePosixPath(rel)
        if p.is_absolute() or ".." in p.parts or not rel.strip() or p.parts[0] == ".git":
            raise ShipError(f"Refusing an unsafe file path in the change: {rel}")
        return str(p)

    def preview(self, task: Any) -> Dict[str, Any]:
        problems = []
        if self._git("rev-parse", "--is-inside-work-tree").returncode != 0:
            problems.append("This folder isn't a git repository.")
        remote = self._git("remote", "get-url", "origin")
        if remote.returncode != 0:
            problems.append("There's no 'origin' remote to push to.")
        branch = self.branch_for(task)
        if self._git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}").returncode == 0:
            problems.append(f"A branch called {branch} already exists here. Rename or delete it first.")
        try:
            gh = self.run(["gh", "auth", "status"], str(self.root))
            gh_ok = gh.returncode == 0
        except FileNotFoundError:
            gh_ok = False
        if not gh_ok:
            problems.append("The GitHub CLI isn't signed in (run `gh auth login`), so the pull request can't be opened. The branch can still be pushed.")
        files = [{"path": d.file_path, "additions": d.additions, "deletions": d.deletions, "new": d.is_new, "deleted": d.is_deleted} for d in task.diffs]
        if not files:
            problems.append("This change has no files.")
        message = (task.artifacts.get("COMMIT_MSG") or f"feat: {task.goal}").strip()
        title = message.splitlines()[0][:120]
        tests = task.test_result
        body = [f"## What\n{task.goal}", "", "## Files"] + [f"- `{f['path']}` (+{f['additions']} / -{f['deletions']})" for f in files]
        body += ["", "## Tests", (f"`{tests.command}`: {'passed' if tests.passed else 'failed'} in {tests.duration_s:.1f}s" if tests else "No test run was recorded.")]
        if task.artifacts.get("decisions.md"):
            body += ["", task.artifacts["decisions.md"].replace("# Decisions from the field guides", "## Decisions from the field guides").strip()]
        body += ["", f"Shipped from the DevSquad Review Desk (run `{task.task_id}`)."]
        blocking = [p for p in problems if "GitHub CLI" not in p]
        return {"task_id": task.task_id, "branch": branch, "remote": remote.stdout.strip() if remote.returncode == 0 else "",
                "files": files, "commit_message": message, "pr_title": title, "pr_body": "\n".join(body),
                "tests_passed": bool(tests and tests.passed), "can_open_pr": gh_ok, "problems": problems, "ready": not blocking}

    def ship(self, task: Any, confirm: bool) -> Dict[str, Any]:
        if confirm is not True:
            raise ShipError("Nothing was shipped: confirm the preview first.")
        plan = self.preview(task)
        if not plan["ready"]:
            raise ShipError(" ".join(p for p in plan["problems"] if "GitHub CLI" not in p))
        branch, work = plan["branch"], pathlib.Path(tempfile.mkdtemp(prefix="devsquad-ship-"))
        shutil.rmtree(work)
        added = self._git("worktree", "add", "-b", branch, str(work), "HEAD")
        if added.returncode != 0:
            raise ShipError("Couldn't create the branch: " + (added.stderr or added.stdout).strip()[:300])
        try:
            for d in task.diffs:
                target = work / self._safe_path(d.file_path)
                if d.is_deleted:
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(d.modified_content, encoding="utf-8")
            self._git("add", "-A", cwd=work)
            committed = self._git("commit", "-m", plan["commit_message"], cwd=work)
            if committed.returncode != 0:
                raise ShipError("Couldn't commit: " + (committed.stderr or committed.stdout).strip()[:300])
            sha = self._git("rev-parse", "--short", "HEAD", cwd=work).stdout.strip()
            pushed = self._git("push", "-u", "origin", branch, cwd=work)
            if pushed.returncode != 0:
                raise ShipError(f"Committed {sha} on {branch}, but the push failed: " + (pushed.stderr or pushed.stdout).strip()[:300])
            result = {"ok": True, "branch": branch, "commit": sha, "pushed": True, "pr_url": None, "note": ""}
            if plan["can_open_pr"]:
                body = work.parent / f"{work.name}-pr.md"
                body.write_text(plan["pr_body"], encoding="utf-8")
                try:
                    pr = self.run(["gh", "pr", "create", "--head", branch, "--title", plan["pr_title"], "--body-file", str(body)], str(work))
                finally:
                    body.unlink(missing_ok=True)
                url = re.search(r"https://\S+/pull/\d+", pr.stdout or "")
                if pr.returncode == 0 and url:
                    result["pr_url"] = url.group(0)
                else:
                    result["note"] = "The branch is pushed, but GitHub didn't open the pull request: " + (pr.stderr or pr.stdout).strip()[:300]
            else:
                result["note"] = "The branch is pushed. Sign in with `gh auth login` to open pull requests from here."
            return result
        finally:
            self._git("worktree", "remove", "--force", str(work))
            shutil.rmtree(work, ignore_errors=True)
