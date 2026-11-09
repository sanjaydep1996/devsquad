# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

import json
import pathlib
import tempfile
import unittest
from devsquad.server.server import StudioHandler


class TestStudioServerAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        StudioHandler.root = self.root

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_handler_initialization(self):
        self.assertEqual(StudioHandler.root, self.root)


if __name__ == "__main__":
    unittest.main()
