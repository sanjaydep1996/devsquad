# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Unit tests for DevSquad v0.4.0 core engines: AI Discovery, Flight Recorder, and Git Bisect."""

import json
import pathlib
import shutil
import tempfile
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
        self.assertIn("5 Whys Root Cause Analysis", pm["markdown_report"])


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


if __name__ == "__main__":
    unittest.main()
