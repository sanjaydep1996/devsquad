# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Unit tests for DevSquad Studio v0.3.0 features."""

import pathlib
import tempfile
import unittest

from devsquad.core.artifacts import ArtifactsPublisher
from devsquad.core.flaky_detector import FlakyTestDetector
from devsquad.core.mcp_hub import MCPHub
from devsquad.core.roadmap import SpecRoadmapProjector
from devsquad.core.visual_qa import VisualQAAuditor


class TestDevSquadV3Features(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_artifacts_adr_and_openapi(self):
        publisher = ArtifactsPublisher(self.root)

        # Test ADR creation
        adr = publisher.generate_adr(
            title="Database Isolation for Worktrees",
            context="Concurrent multi-agent relays need isolated SQLite databases.",
            decision="Adopted ephemeral SQLite files per worktree.",
            consequences="Prevents locked database contention.",
            status="Accepted",
            adr_number=1,
        )
        self.assertEqual(adr.number, 1)
        self.assertIn("# 0001. Database Isolation for Worktrees", adr.markdown_content)
        self.assertIn("## Context", adr.markdown_content)
        self.assertIn("## Decision", adr.markdown_content)

        # Test OpenAPI AST extraction
        sample_code = (
            "@app.get('/api/users')\n"
            "def list_users():\n"
            "    '''Returns list of active workspace users.'''\n"
            "    return []\n\n"
            "@app.post('/api/users')\n"
            "def create_user():\n"
            "    return {'ok': True}\n"
        )
        specs = publisher.extract_openapi_specs(sample_code)
        self.assertIn("/api/users", specs["paths"])
        self.assertIn("get", specs["paths"]["/api/users"])
        self.assertIn("post", specs["paths"]["/api/users"])

        # Test Changelog generation
        commits = [
            "feat(auth): add OAuth2 refresh token rotation",
            "fix(server): handle null relay gracefully",
            "docs(readme): add MIT license attribution",
        ]
        changelog = publisher.generate_release_changelog("0.3.0", commits)
        self.assertIn("### ✨ Features", changelog)
        self.assertIn("### 🐛 Bug Fixes", changelog)
        self.assertIn("### 📚 Documentation", changelog)

    def test_mcp_hub_jsonrpc(self):
        hub = MCPHub(self.root)

        # Test initialize
        init_res = hub.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertIn("serverInfo", init_res["result"])
        self.assertEqual(init_res["result"]["serverInfo"]["name"], "DevSquad MCP Desk Hub")

        # Test tools/list
        list_res = hub.handle_jsonrpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"desk": "all"}})
        tools = list_res["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("run_test_suite", tool_names)
        self.assertIn("ast_blast_radius", tool_names)
        self.assertIn("flaky_stress_runner", tool_names)

        # Test tools/call
        call_res = hub.handle_jsonrpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "ast_blast_radius", "arguments": {"files": ["main.py"]}},
        })
        self.assertIn("content", call_res["result"])

    def test_roadmap_projector_dag(self):
        projector = SpecRoadmapProjector()
        prd = (
            "# Feature: Global Rate Limiting\n\n"
            "## Objectives\n"
            "- Prevent 429 API quota exhaustion\n"
            "- Protect auth endpoints\n\n"
            "## User Stories\n"
            "- As an engineer, I want exponential backoff retry\n"
        )
        plan = projector.parse_prd(prd)
        self.assertEqual(plan.project_title, "Feature: Global Rate Limiting")
        self.assertGreaterEqual(len(plan.tasks), 3)
        self.assertIn("graph TD", plan.mermaid_dag)
        self.assertGreater(plan.total_estimated_tokens, 0)
        self.assertEqual(plan.tasks[0].task_id, "TASK-1")

    def test_flaky_test_stress_runner(self):
        detector = FlakyTestDetector()
        res = detector.stress_test("tests/test_async_auth.py::test_token_exchange", iterations=10, simulated_flaky_rate=0.30)
        self.assertEqual(res.total_runs, 10)
        self.assertFalse(res.verified_deterministic)   # a simulation proves nothing, and says so
        self.assertIn("Simulation only", res.root_cause_diagnosis)

    def test_visual_qa_auditor(self):
        auditor = VisualQAAuditor(self.root)
        dirty_html = (
            "<html><body>\n"
            "<button style='height:24px;'>Small</button>\n"
            "<button><svg></svg></button>\n"
            "<img src='test.png'>\n"
            "</body></html>"
        )
        report = auditor.audit_html(dirty_html, source_name="dirty.html")
        self.assertLess(report.score, 100)
        rule_ids = {i.rule_id for i in report.issues}
        self.assertIn("WCAG-TAP-TARGET", rule_ids)
        self.assertIn("A11Y-ICON-LABEL", rule_ids)
        self.assertIn("CLS-IMAGE-DIMS", rule_ids)

        clean_html = (
            "<html><body><main>\n"
            "<button style='min-height:44px;min-width:44px;' aria-label='Save'>Save</button>\n"
            "<img src='test.png' width='200' height='100' alt='banner'>\n"
            "</main></body></html>"
        )
        clean_report = auditor.audit_html(clean_html, source_name="clean.html")
        self.assertEqual(clean_report.score, 100)
        self.assertEqual(clean_report.viewport_status, "PASS_MOBILE_AND_DESKTOP")


if __name__ == "__main__":
    unittest.main()
