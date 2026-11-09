# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.llm.providers import TemplateProvider
from devsquad.runtime.relay import AutonomousRelay


class TestAutonomousRelay(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.provider = TemplateProvider()

        # Create mock repo
        (self.root / "src").mkdir()
        (self.root / "src" / "feature.py").write_text("# initial\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_relay_execution(self):
        events = []

        def on_event(agent, event, data):
            events.append((agent, event))

        relay = AutonomousRelay(
            provider=self.provider,
            root=self.root,
            event_callback=on_event,
        )

        task = relay.run_task(
            goal="Add user profile endpoint",
            target_file="src/feature.py",
            test_file="tests/test_feature.py",
        )

        self.assertIsNotNone(task)
        self.assertIn("spec.md", task.artifacts)
        self.assertIn("src/feature.py", task.artifacts)
        self.assertIn("tests/test_feature.py", task.artifacts)
        self.assertGreater(len(task.diffs), 0)
        self.assertTrue(any(ag == "Apex" for ag, _ in events))
        self.assertTrue(any(ag == "Alpha" for ag, _ in events))
        self.assertTrue(any(ag == "Gamma" for ag, _ in events))
        self.assertTrue(any(ag == "Delta" for ag, _ in events))


if __name__ == "__main__":
    unittest.main()
