# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.diff import DiffEngine


class TestDiffEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_diff(self):
        orig = "def add(a, b):\n    return a + b\n"
        mod = "def add(a, b):\n    # Optimized\n    return a + b\n"

        diff = DiffEngine.create_diff("math.py", orig, mod)
        self.assertEqual(diff.file_path, "math.py")
        self.assertGreater(diff.additions, 0)
        self.assertIn("+    # Optimized", diff.patch_text)

    def test_apply_and_rollback_file_change(self):
        test_file = self.root / "example.txt"
        test_file.write_text("initial content", encoding="utf-8")

        # Apply
        ok, msg = DiffEngine.apply_file_change(self.root, "example.txt", "updated content")
        self.assertTrue(ok)
        self.assertEqual(test_file.read_text(encoding="utf-8"), "updated content")

        # Rollback
        ok_rb, msg_rb = DiffEngine.rollback_file_change(self.root, "example.txt")
        self.assertTrue(ok_rb)
        self.assertEqual(test_file.read_text(encoding="utf-8"), "initial content")


if __name__ == "__main__":
    unittest.main()
