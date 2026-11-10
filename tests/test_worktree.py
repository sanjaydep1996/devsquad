# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.worktree import WorktreeManager


class TestWorktreeManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.mgr = WorktreeManager(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fallback_creation_and_cleanup(self):
        # Create a sample file
        (self.root / "app.py").write_text("print('hello world')")
        
        # Test creation fallback
        wt = self.mgr.create_worktree("task-test-01")
        self.assertTrue(wt.exists())
        self.assertTrue((wt / "app.py").exists())
        self.assertEqual((wt / "app.py").read_text(), "print('hello world')")

        # Test listing
        wts = self.mgr.list_worktrees()
        self.assertEqual(len(wts), 1)
        self.assertEqual(wts[0]["task_id"], "task-test-01")

        # Test cleanup
        cleaned = self.mgr.cleanup_worktree("task-test-01")
        self.assertTrue(cleaned)
        self.assertFalse(wt.exists())


if __name__ == "__main__":
    unittest.main()
