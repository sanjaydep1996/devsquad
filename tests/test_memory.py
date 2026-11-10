# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.memory import MemoryLake


class TestMemoryLake(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.lake = MemoryLake(self.root)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cursor_and_claude_ingestion(self):
        # Create mock .cursorrules
        (self.root / ".cursorrules").write_text("Always use absolute imports\nUse pydantic v2\n")
        # Create mock CLAUDE.md
        (self.root / "CLAUDE.md").write_text("- Never push to main directly\n- Run pytest before PR\n")

        res = self.lake.ingest_all()
        self.assertEqual(res["cursor"], 2)
        self.assertEqual(res["claude_code"], 2)

        ctx = self.lake.get_agent_context()
        self.assertIn("[Cursor] Always use absolute imports", ctx)
        self.assertIn("[Claude Code] Never push to main directly", ctx)

    def test_task_outcome_recording(self):
        self.lake.record_task_outcome("task-123", "Fix auth", False, ["auth.py"], "ValueError: Invalid secret key")
        self.assertIn("ValueError: Invalid secret key", self.lake.data["known_pitfalls"])
        self.assertEqual(self.lake.data["frequent_files"].get("auth.py"), 1)


if __name__ == "__main__":
    unittest.main()
