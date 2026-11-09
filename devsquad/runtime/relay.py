# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Autonomous Relay Engine: orchestrates the multi-agent pipeline with closed-loop auto-healing."""

import pathlib
import time
import uuid
from typing import Callable, Dict, List, Optional
from ..agents.personas import AlphaCoder, ApexLead, DeltaDevOps, GammaQA
from ..core.context import RepoContextEngine
from ..core.diff import DiffEngine, FileDiff
from ..core.runner import SandboxRunner, TestRunResult
from ..core.staging import StagedTask, StagingDeck
from ..llm.base import BaseProvider


class AutonomousRelay:
    """Executes end-to-end engineering tasks across specialized agent personas."""

    def __init__(
        self,
        provider: BaseProvider,
        root: Optional[pathlib.Path] = None,
        event_callback: Optional[Callable[[str, str, Dict], None]] = None,
        max_heal_retries: int = 3,
    ):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.provider = provider
        self.event_cb = event_callback or (lambda agent, event, data: None)
        self.max_heal_retries = max_heal_retries

        self.context_engine = RepoContextEngine(self.root)
        self.staging = StagingDeck(self.root)
        self.runner = SandboxRunner(self.root)

        self.apex = ApexLead(provider)
        self.alpha = AlphaCoder(provider)
        self.gamma = GammaQA(provider)
        self.delta = DeltaDevOps(provider)

    def _log(self, task: StagedTask, agent: str, event: str, message: str, data: Optional[Dict] = None):
        payload = data or {}
        entry = f"[{time.strftime('%H:%M:%S')}] [{agent}] {event}: {message}"
        task.relay_logs.append(entry)
        self.event_cb(agent, event, {"message": message, **payload})

    def run_task(
        self,
        goal: str,
        target_file: Optional[str] = None,
        test_file: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> StagedTask:
        """Executes the full relay: Spec -> Code -> Test -> Auto-Heal -> Git metadata -> Staging."""
        tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
        task = self.staging.create_task(tid, goal)

        # 1. Repo Context Analysis
        self._log(task, "System", "ANALYSIS", f"Analyzing repository context at {self.root.name}...")
        meta = self.context_engine.analyze()
        tree = self.context_engine.get_file_tree(max_files=60)
        rules = self.context_engine.read_rules_context()

        # Target defaults
        t_file = target_file or ("src/feature.py" if "python" in meta.languages else "src/feature.js")
        t_test = test_file or ("tests/test_feature.py" if "python" in meta.languages else "tests/feature.test.js")

        # 2. Stage 1: Apex Architect
        self._log(task, "Apex", "PLANNING", f"Creating architecture specification for '{goal}'...")
        context_str = f"Languages: {', '.join(meta.languages)}\nFiles:\n{tree}"
        spec = self.apex.plan(goal, context_str, rules)
        task.artifacts["spec.md"] = spec
        self._log(task, "Apex", "SPEC_READY", f"Architecture specification drafted ({len(spec.splitlines())} lines).")

        # 3. Stage 2: Alpha Code Implementation
        self._log(task, "Alpha", "CODING", f"Implementing solution in {t_file}...")
        existing_code = ""
        full_t_path = self.root / t_file
        if full_t_path.exists():
            try:
                existing_code = full_t_path.read_text(encoding="utf-8")
            except Exception:
                pass

        impl_code = self.alpha.implement(goal, spec, t_file, existing_code)
        task.artifacts[t_file] = impl_code
        self._log(task, "Alpha", "CODE_READY", f"Implementation completed for {t_file}.")

        # 4. Stage 3: Gamma QA Test Suite Generation
        self._log(task, "Gamma", "TEST_DESIGN", f"Generating verification tests in {t_test}...")
        test_code = self.gamma.write_tests(goal, spec, impl_code, t_test)
        task.artifacts[t_test] = test_code
        self._log(task, "Gamma", "TESTS_READY", f"Test suite written for {t_test}.")

        # Compute Diffs
        file_diff = DiffEngine.create_diff(t_file, existing_code, impl_code)
        existing_test = ""
        if (self.root / t_test).exists():
            try:
                existing_test = (self.root / t_test).read_text(encoding="utf-8")
            except Exception:
                pass
        test_diff = DiffEngine.create_diff(t_test, existing_test, test_code)
        task.diffs = [file_diff, test_diff]

        # 5. Stage 4: Closed-Loop Test Execution & Auto-Healing
        self._log(task, "Gamma", "VERIFYING", "Executing local test runner in sandbox...")

        # Find best test command
        test_cmd = meta.test_runners[0].command if meta.test_runners else ["python3", "-m", "unittest", "discover"]

        # In a real environment we can temporarily test in-memory or run configured test suite
        test_res = self.runner.run_tests(test_cmd)
        task.test_result = test_res

        heal_attempt = 0
        while not test_res.passed and heal_attempt < self.max_heal_retries:
            heal_attempt += 1
            self._log(
                task,
                "Gamma",
                "TEST_FAILED",
                f"Tests failed (attempt {heal_attempt}/{self.max_heal_retries}). Sending traceback to Alpha...",
                {"traceback": test_res.failure_summary},
            )

            # Alpha Auto-Heals
            self._log(task, "Alpha", "HEALING", f"Auto-healing patch (iteration #{heal_attempt})...")
            impl_code = self.alpha.auto_heal(t_file, impl_code, test_res.failure_summary or test_res.output)
            task.artifacts[t_file] = impl_code

            # Re-compute diff
            file_diff = DiffEngine.create_diff(t_file, existing_code, impl_code)
            task.diffs = [file_diff, test_diff]

            # Re-run
            self._log(task, "Gamma", "REVERIFYING", f"Re-running test suite after heal #{heal_attempt}...")
            test_res = self.runner.run_tests(test_cmd)
            task.test_result = test_res

        if test_res.passed:
            task.status = "tested_green"
            self._log(task, "Gamma", "VERIFIED_GREEN", f"All tests PASSED in {test_res.duration_s}s! Zero regressions.")
        else:
            task.status = "tested_red"
            self._log(task, "Gamma", "VERIFIED_RED", f"Test harness reported failures. Retained in Staging Deck for review.")

        # 6. Stage 5: Delta DevOps Git Preparation
        self._log(task, "Delta", "GIT_PREP", "Preparing branch name and conventional commit message...")
        git_meta = self.delta.prepare_git_metadata(goal, [t_file, t_test])
        task.git_branch = git_meta.get("branch", f"feat/{tid}")
        task.artifacts["COMMIT_MSG"] = git_meta.get("commit_message", f"feat: {goal}")
        self._log(task, "Delta", "STAGED", f"Branch '{task.git_branch}' prepared. Ready for human review at Review Desk.")

        # Save to Staging Deck
        self.staging.save_task(task)
        return task
