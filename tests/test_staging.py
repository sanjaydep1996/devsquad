# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.diff import DiffEngine
from devsquad.core.staging import StagingDeck


class TestStagingDeck(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.staging = StagingDeck(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_task_lifecycle(self):
        # Create
        task = self.staging.create_task("task-123", "Add rate limiter")
        self.assertEqual(task.status, "staged")

        # Add diff
        diff = DiffEngine.create_diff("auth.py", "x = 1\n", "x = 2\n")
        task.diffs.append(diff)
        self.staging.save_task(task)

        # Load
        loaded = self.staging.load_task("task-123")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.goal, "Add rate limiter")
        self.assertEqual(len(loaded.diffs), 1)

        # List
        tasks = self.staging.list_tasks()
        self.assertEqual(len(tasks), 1)

        # Apply
        target = self.root / "auth.py"
        target.write_text("x = 1\n", encoding="utf-8")
        results = self.staging.apply_task("task-123")
        self.assertEqual(target.read_text(encoding="utf-8"), "x = 2\n")

        # Rollback
        self.staging.rollback_task("task-123")
        self.assertEqual(target.read_text(encoding="utf-8"), "x = 1\n")


if __name__ == "__main__":
    unittest.main()
