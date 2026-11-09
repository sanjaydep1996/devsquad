# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import pathlib
import tempfile
import unittest
from devsquad.core.context import RepoContextEngine


class TestRepoContextEngine(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)

        # Create mock project files
        (self.root / "src").mkdir()
        (self.root / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests" / "test_app.py").write_text("def test_app(): pass", encoding="utf-8")
        (self.root / "CLAUDE.md").write_text("# Project Guidelines", encoding="utf-8")
        (self.root / "pyproject.toml").write_text("[project]\nname = 'test'", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_repo_analysis(self):
        engine = RepoContextEngine(self.root)
        meta = engine.analyze()

        self.assertIn("python", meta.languages)
        self.assertGreater(meta.total_files, 0)
        self.assertTrue(any(tr.name == "pytest" for tr in meta.test_runners))
        self.assertIn("CLAUDE.md", meta.rule_files)

    def test_file_tree(self):
        engine = RepoContextEngine(self.root)
        tree = engine.get_file_tree()
        self.assertIn("app.py", tree)
        self.assertIn("test_app.py", tree)

    def test_rules_context(self):
        engine = RepoContextEngine(self.root)
        rules = engine.read_rules_context()
        self.assertIn("Project Guidelines", rules)


if __name__ == "__main__":
    unittest.main()
