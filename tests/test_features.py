# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.blast_radius import BlastRadiusAnalyzer
from devsquad.llm.providers import TemplateProvider
from devsquad.runtime.swarm import BugSwarm


class TestNewFeatures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        (self.root / "src").mkdir(parents=True, exist_ok=True)
        (self.root / "tests").mkdir(parents=True, exist_ok=True)

        # Create caller and callee
        (self.root / "src" / "service.py").write_text("class Service: pass")
        (self.root / "src" / "controller.py").write_text("from src.service import Service\ndef handle(): pass")
        (self.root / "tests" / "test_service.py").write_text("from src.service import Service\ndef test(): pass")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_blast_radius_analyzer(self):
        analyzer = BlastRadiusAnalyzer(self.root)
        res = analyzer.analyze(["src/service.py"])
        self.assertEqual(res["modified_count"], 1)
        self.assertGreaterEqual(res["affected_callers_count"], 1)
        
        # Verify node types
        types = [n["type"] for n in res["nodes"]]
        self.assertIn("modified", types)
        self.assertIn("consumer_risk", types)

    def test_bug_swarm_execution(self):
        swarm = BugSwarm(TemplateProvider(), self.root)
        task = swarm.run_swarm("NullPointerException in Auth", "Traceback: line 42 in auth.py")
        self.assertTrue(task.task_id.startswith("bug-"))
        self.assertEqual(len(task.diffs), 2)
        self.assertIn("triage_spec.md", task.artifacts)


if __name__ == "__main__":
    unittest.main()
