# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Unit tests for DevSquad v0.4.0 core engines: AI Discovery, Flight Recorder, and Git Bisect."""

import json
import pathlib
import shutil
import tempfile
import sys
import unittest

from devsquad.core.ai_discovery import AIDiscoveryEngine
from devsquad.core.flight_recorder import FlightEvent, FlightRecorder
from devsquad.core.git_bisect import AutonomousBisect


class TestAIDiscoveryEngine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = pathlib.Path(self.tmp)
        self.engine = AIDiscoveryEngine(workspace_root=self.root)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_detect_installed_clis(self):
        clis = self.engine.detect_installed_clis()
        self.assertIsInstance(clis, list)
        self.assertTrue(len(clis) >= 5)
        ids = [c["id"] for c in clis]
        self.assertIn("claude", ids)
        self.assertIn("gemini", ids)
        self.assertIn("cursor", ids)
        self.assertIn("ollama", ids)

    def test_detect_local_configs(self):
        (self.root / "CLAUDE.md").write_text("# Claude Code Guidelines\n", encoding="utf-8")
        (self.root / ".cursorrules").write_text("Strict TypeScript\n", encoding="utf-8")
        configs = self.engine.detect_local_configs()
        self.assertTrue(configs["claude_instructions"])
        self.assertTrue(configs["cursor_rules"])

    def test_full_inventory(self):
        inventory = self.engine.full_inventory()
        self.assertEqual(inventory["status"], "ready")
        self.assertIn("installed_clis", inventory)
        self.assertIn("suggested_provider", inventory)


class TestFlightRecorder(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = pathlib.Path(self.tmp)
        self.recorder = FlightRecorder(workspace_root=self.root)
        self.session_id = "test-session-001"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_record_and_get_timeline(self):
        ev1 = self.recorder.record_event(
            session_id=self.session_id,
            step=1,
            agent="apex",
            action="plan_feature",
            diff="--- a/file.py\n+++ b/file.py",
            file_path="file.py",
        )
        self.assertEqual(ev1.step, 1)

        ev2 = self.recorder.record_event(
            session_id=self.session_id,
            step=2,
            agent="beta_fe",
            action="render_component",
            status="error",
            diff="--- a/ui.tsx\n+++ b/ui.tsx",
            file_path="ui.tsx",
        )
        self.assertEqual(ev2.status, "error")

        timeline = self.recorder.get_timeline(self.session_id)
        self.assertEqual(len(timeline), 2)
        self.assertEqual(timeline[0]["agent"], "apex")
        self.assertEqual(timeline[1]["agent"], "beta_fe")

    def test_scrub_state(self):
        for i in range(1, 4):
            self.recorder.record_event(
                session_id=self.session_id,
                step=i,
                agent=f"agent_{i}",
                action=f"action_{i}",
                file_path=f"file_{i}.py",
                diff=f"diff_{i}",
            )

        scrubbed = self.recorder.scrub_state(self.session_id, target_step=2)
        self.assertEqual(scrubbed["target_step"], 2)
        self.assertEqual(scrubbed["step_count_replayed"], 2)
        self.assertIn("file_1.py", scrubbed["active_files_at_step"])
        self.assertIn("file_2.py", scrubbed["active_files_at_step"])
        self.assertNotIn("file_3.py", scrubbed["active_files_at_step"])

    def test_generate_post_mortem(self):
        self.recorder.record_event(
            session_id=self.session_id,
            step=1,
            agent="apex",
            action="init",
            file_path="app.py",
        )
        self.recorder.record_event(
            session_id=self.session_id,
            step=2,
            agent="gamma_qa",
            action="test_failed",
            status="error",
            file_path="app.py",
        )

        pm = self.recorder.generate_post_mortem(
            session_id=self.session_id,
            failure_step=2,
            failure_summary="AssertionError: Expected 200 got 500 in payment webhook",
        )
        self.assertEqual(pm["failure_step"], 2)
        self.assertEqual(pm["culprit_agent"], "gamma_qa")
        self.assertEqual(len(pm["whys"]), 5)
        self.assertIn("AssertionError", pm["markdown_report"])
        self.assertIn("What the record shows", pm["markdown_report"])


class TestAutonomousBisect(unittest.TestCase):
    def setUp(self):
        self.bisect = AutonomousBisect()

    def test_simulate_bisect(self):
        # 5 candidate commits: newest (0) to oldest (4)
        # Commit 2 introduced the bug, so 0 and 1 are bad, 2 is the culprit, 3 and 4 are good.
        commits = [
            {"sha": "c0000000", "author": "Alice", "date": "2026-11-13", "message": "feat: newest"},
            {"sha": "c1111111", "author": "Bob", "date": "2026-11-12", "message": "refactor: middle"},
            {"sha": "c2222222", "author": "Charlie", "date": "2026-11-11", "message": "fix: regression culprit"},
            {"sha": "c3333333", "author": "Dana", "date": "2026-11-10", "message": "docs: older good"},
            {"sha": "c4444444", "author": "Eve", "date": "2026-11-09", "message": "initial commit"},
        ]

        # Evaluator: commits with index >= 3 are GOOD (True), index <= 2 are BAD (False)
        def evaluator(c):
            idx = [x["sha"] for x in commits].index(c["sha"])
            return idx >= 3

        result = self.bisect.simulate_bisect(commits, evaluator)
        self.assertEqual(result["status"], "isolated")
        self.assertEqual(result["culprit"]["sha"], "c2222222")
        self.assertEqual(result["culprit"]["author"], "Charlie")
        self.assertIn("git revert", result["remediation"]["recommended_command"])


import shutil
import subprocess
import tempfile


def git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


class TestRealBisect(unittest.TestCase):
    """Runs the person's own test command on real commits in a scratch worktree."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name) / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.email", "t@example.com")
        git(self.repo, "config", "user.name", "Tester")
        # check.py fails when VALUE is wrong. Commit 4 of 6 breaks it, and the message gives no hint.
        values = ["1", "1", "1", "2", "2", "2"]
        messages = ["initial", "docs: readme", "feat: logging", "feat: harmless refactor", "chore: tidy", "feat: newest"]
        (self.repo / "check.py").write_text("import sys\nfrom value import VALUE\nsys.exit(0 if VALUE == 1 else 1)\n")
        for i, (v, m) in enumerate(zip(values, messages)):
            (self.repo / "value.py").write_text(f"VALUE = {v}\n# {i}\n")
            git(self.repo, "add", "-A")
            git(self.repo, "commit", "-q", "-m", m)
        self.shas = git(self.repo, "log", "--format=%H").splitlines()   # newest first
        self.bisect = AutonomousBisect(self.repo)

    def test_finds_the_commit_that_really_broke_the_test(self):
        result = self.bisect.bisect_with_test_command(f"{sys.executable} check.py", lookback=6)
        self.assertEqual(result["status"], "isolated")
        self.assertEqual(result["culprit"]["message"], "feat: harmless refactor")
        self.assertEqual(result["culprit"]["sha"], self.shas[2])
        self.assertIn("git revert", result["remediation"]["recommended_command"])
        self.assertTrue(all(s["verdict"] in ("GOOD", "BAD") for s in result["bisect_steps"]))

    def test_a_scary_commit_message_does_not_make_it_the_culprit(self):
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "fix: error handling regression break")
        result = AutonomousBisect(self.repo).bisect_with_test_command(f"{sys.executable} check.py", lookback=7)
        self.assertEqual(result["culprit"]["message"], "feat: harmless refactor")

    def test_a_passing_newest_commit_means_no_regression(self):
        result = self.bisect.bisect_with_test_command(f"{sys.executable} -c pass", lookback=6)
        self.assertEqual(result["status"], "no_regression")
        self.assertNotIn("culprit", result)

    def test_a_failure_older_than_the_window_says_so(self):
        result = self.bisect.bisect_with_test_command(f"{sys.executable} -c 'import sys; sys.exit(1)'", lookback=6)
        self.assertEqual(result["status"], "older_than_window")
        self.assertNotIn("culprit", result)

    def test_the_working_tree_is_never_touched(self):
        (self.repo / "uncommitted.txt").write_text("keep me")
        head = git(self.repo, "rev-parse", "HEAD")
        self.bisect.bisect_with_test_command(f"{sys.executable} check.py", lookback=6)
        self.assertEqual(git(self.repo, "rev-parse", "HEAD"), head)
        self.assertEqual((self.repo / "uncommitted.txt").read_text(), "keep me")
        self.assertEqual(git(self.repo, "worktree", "list").count("\n"), 0)   # the scratch worktree is gone

    def test_a_command_that_hangs_is_stopped(self):
        result = AutonomousBisect(self.repo, timeout_s=1).bisect_with_test_command(f"{sys.executable} -c 'import time; time.sleep(30)'", lookback=6)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIn("time", result["error"].lower())

    def test_an_empty_command_is_an_error(self):
        self.assertEqual(self.bisect.bisect_with_test_command("", lookback=6)["status"], "error")


class TestRelayRecordsToTheFlightRecorder(unittest.TestCase):
    def test_every_relay_stage_is_recorded_and_a_failure_gets_a_factual_post_mortem(self):
        from devsquad.llm.providers import TemplateProvider
        from devsquad.runtime.relay import AutonomousRelay
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            (root / "requirements.txt").write_text("")
            task = AutonomousRelay(provider=TemplateProvider(), root=root).run_task("Add a health check")
            timeline = FlightRecorder(workspace_root=root).get_timeline(task.task_id)
            self.assertEqual(len(timeline), len(task.relay_logs))
            self.assertEqual([e["step"] for e in timeline], list(range(1, len(timeline) + 1)))
            self.assertEqual({e["agent"] for e in timeline} >= {"Apex", "Alpha", "Gamma", "Delta"}, True)
            failed = [e for e in timeline if e["status"] == "error"]
            if task.status == "tested_red":
                self.assertTrue(failed)
                pm = FlightRecorder(workspace_root=root).generate_post_mortem(task.task_id, failed[0]["step"], "tests failed")
                self.assertIn(failed[0]["payload"]["message"][:30], pm["markdown_report"])


class TestPostMortemIsFactual(unittest.TestCase):
    def test_it_reports_only_what_was_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            rec = FlightRecorder(workspace_root=pathlib.Path(tmp))
            rec.record_event("s1", 1, "Apex", "PLANNING", payload={"message": "Planning the login page"})
            rec.record_event("s1", 2, "Alpha", "CODING", payload={"message": "Edited src/login.py"}, file_path="src/login.py", diff="+ return 500")
            rec.record_event("s1", 3, "Gamma", "VERIFIED_RED", status="error", payload={"message": "2 tests failed"})
            pm = rec.generate_post_mortem("s1", 3, "AssertionError: expected 200 got 500")
            report = pm["markdown_report"]
            for fact in ("AssertionError: expected 200 got 500", "Gamma", "VERIFIED_RED", "src/login.py", "Alpha", "+ return 500"):
                self.assertIn(fact, report)
            for invented in ("Concurrency race", "Missing invariant validation gate", "pre-flight validation"):
                self.assertNotIn(invented, report)
            self.assertIn("not known", report.lower())


if __name__ == "__main__":
    unittest.main()
