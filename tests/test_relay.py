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


    def test_each_agent_works_from_its_field_guides(self):
        prompts = []
        real = self.provider.complete
        self.provider.complete = lambda prompt, **kw: (prompts.append(prompt), real(prompt, **kw))[1]
        events = []
        relay = AutonomousRelay(provider=self.provider, root=self.root, event_callback=lambda a, e, d: events.append((a, e, d.get("message", ""))))
        task = relay.run_task(goal="Add login with password reset by email", target_file="src/feature.py", test_file="tests/test_feature.py")
        drawing = [m for a, e, m in events if e == "DRAWING_ON"]
        self.assertTrue(any("Store passwords properly" in m for m in drawing))
        self.assertIn("Security guide", task.artifacts["decisions.md"])
        self.assertTrue(any("FUNDAMENTALS TO APPLY" in p for p in prompts))


if __name__ == "__main__":
    unittest.main()
