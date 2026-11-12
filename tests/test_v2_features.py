# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Unit tests for DevSquad Studio v0.2.0 features."""

import pathlib
import tempfile
import unittest

from devsquad.core.chaos import ChaosLab
from devsquad.core.merge_arena import MergeConflictArena
from devsquad.core.security_vault import SecurityVault
from devsquad.llm.hybrid_router import HybridModelRouter


class TestDevSquadV2Features(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_merge_arena_ast_negotiation(self):
        arena = MergeConflictArena(self.root)
        base = "def get_data(x):\n    return x\n"
        code_a = "import os\n\ndef get_data(x, log=True):\n    return f'A:{x}'\n"
        code_b = "import sys\n\ndef get_data(x, default=''):\n    return f'B:{x}'\n"

        res = arena.negotiate_resolution("test_service.py", base, code_a, code_b)
        self.assertIn(res.status, ("VERIFIED_SYNTAX_OK", "RESOLVED_CLEAN"))
        self.assertTrue(res.ast_valid)
        self.assertGreater(len(res.dialogue), 0)
        self.assertTrue("import os" in res.resolved_code or "import sys" in res.resolved_code)

    def test_chaos_lab_outage_and_healing(self):
        chaos = ChaosLab()
        incident = chaos.inject_fault("FLAKY_ENDPOINT", "Core Relay")
        self.assertEqual(incident.fault_type, "FLAKY_ENDPOINT")
        self.assertEqual(incident.status, "TRIGGERED")

        plan = chaos.trigger_self_healing(incident.incident_id)
        self.assertEqual(plan.incident_id, incident.incident_id)
        self.assertTrue(plan.verified_by_qa)
        self.assertIn("retry_with_exponential_backoff", plan.patch_code)
        self.assertEqual(incident.status, "HEALED")

    def test_security_vault_scanner(self):
        vault = SecurityVault(self.root)

        # Dirty code with secret leak and unsafe sink
        dirty_code = (
            "openai_key = 'sk-1234567890abcdef1234567890abcdef'\n"
            "element.innerHTML = '<h1>' + userInput + '</h1>'\n"
            "subprocess.run('rm -rf ' + path, shell=True)\n"
        )
        vulns = vault.scan_code(dirty_code, file_name="dirty.py")
        self.assertGreaterEqual(len(vulns), 3)

        categories = {v.category for v in vulns}
        self.assertIn("SECRET_LEAK", categories)
        self.assertIn("XSS_SINK", categories)
        self.assertIn("COMMAND_INJECTION", categories)

        # Clean code
        clean_code = "def safe_add(a: int, b: int) -> int:\n    return a + b\n"
        clean_vulns = vault.scan_code(clean_code, file_name="clean.py")
        self.assertEqual(len(clean_vulns), 0)

    def test_hybrid_model_router_savings(self):
        router = HybridModelRouter()
        savings = router.record_usage(input_tokens=1_000_000, output_tokens=500_000)
        # 1M input @ $3.00 + 0.5M output @ $15.00 = $3.00 + $7.50 = $10.50
        self.assertAlmostEqual(savings, 10.50, places=2)
        status = router.get_router_status()
        self.assertEqual(status["mode"], "hybrid")
        self.assertGreaterEqual(len(status["models_available"]), 2)


if __name__ == "__main__":
    unittest.main()
