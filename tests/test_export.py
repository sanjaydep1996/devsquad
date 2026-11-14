"""Exports (plan, replay, post-mortem as Markdown or PDF) and the desk status card."""

import http.client
import json
import pathlib
import tempfile
import threading
import unittest

from devsquad.core.diff import FileDiff
from devsquad.core.doc_reader import pdf_text
from devsquad.core.export import Download, markdown_to_pdf, plan_markdown, postmortem_markdown, replay_markdown
from devsquad.core.replay import build_replay
from devsquad.core.runner import TestRunResult
from devsquad.core.staging import StagingDeck
from devsquad.core.status import StatusBoard, StatusReporter
from devsquad.server.server import start_studio_server
from devsquad.server.v5_api import V5Api

try:
    from fastapi.testclient import TestClient
    from devsquad.server.fastapi_app import create_app
except ImportError:  # FastAPI is optional
    TestClient = None

LOGS = [
    "[09:00:00] [Apex] PLAN: Writing the spec",
    "[09:00:04] [Alpha] CODE: Adding the invite route",
    "[09:00:09] [Gamma] TESTS_RED: 1 test failed",
    "[09:00:11] [Delta] COMMIT_MSG: Prepared the branch",
]


def staged_run(root: pathlib.Path, task_id: str = "task-abc123", red: bool = True) -> StagingDeck:
    deck = StagingDeck(root)
    task = deck.create_task(task_id, "Add team invites by email")
    task.relay_logs = list(LOGS) if red else [l.replace("TESTS_RED: 1 test failed", "TESTS_GREEN: all tests passed") for l in LOGS]
    task.status = "tested_red" if red else "tested_green"
    task.test_result = TestRunResult(passed=not red, exit_code=1 if red else 0, duration_s=1.2, command="pytest",
                                     output="E   AssertionError: expected 201", failure_summary="AssertionError: expected 201" if red else None)
    task.diffs = [FileDiff("app/invites.py", "", "def invite(): pass\n", "+def invite(): pass", 1, 0, is_new=True)]
    deck.save_task(task)
    return deck


class PdfTests(unittest.TestCase):
    def test_pdf_is_a_real_pdf_our_own_reader_can_read(self):
        data = markdown_to_pdf("# Plan: invites\n\nSome text here.\n\n- first point\n- second point\n\n```\ncode line\n```\n", title="Plan")
        self.assertTrue(data.startswith(b"%PDF-1.4"))
        self.assertTrue(data.rstrip().endswith(b"%%EOF"))
        text = pdf_text(data)
        for part in ("Plan: invites", "Some text here.", "first point", "code line"):
            self.assertIn(part, text)

    def test_long_documents_break_onto_more_pages(self):
        md = "# Long\n\n" + "\n".join(f"- line number {i} with a few words to wrap" for i in range(200))
        data = markdown_to_pdf(md)
        self.assertGreater(data.count(b"/Type /Page "), 2)
        self.assertIn("line number 199", pdf_text(data))

    def test_characters_outside_the_pdf_font_do_not_break_it(self):
        data = markdown_to_pdf("# Ünïcode — “quotes” 🚀 and (brackets) \\ slash")
        text = pdf_text(data)
        self.assertIn("(brackets)", text)
        self.assertIn("quotes", text)


class MarkdownTests(unittest.TestCase):
    def test_plan_lists_tasks_owners_risks_and_questions(self):
        plan = {"id": "plan-0000abcd", "goal": "Add invites", "summary": "Invite people by email.", "status": "proposed", "created": 0,
                "source": "template", "note": "Template mode.", "risks": ["Emails can bounce"], "questions": ["Which email provider?"],
                "tasks": [{"title": "API route", "owner": "alpha_be", "detail": "POST /invites"}, {"title": "Docs", "owner": "zeta_docs", "detail": ""}]}
        md = plan_markdown(plan)
        self.assertIn("# Plan: Add invites", md)
        self.assertIn("API route", md)
        self.assertIn("Alpha BE", md)
        self.assertIn("POST /invites", md)
        self.assertIn("Emails can bounce", md)
        self.assertIn("Which email provider?", md)
        self.assertIn("Template mode.", md)

    def test_replay_and_post_mortem_come_from_the_recorded_run(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            deck = staged_run(root)
            replay = build_replay(root, "task-abc123", deck)
            md = replay_markdown(replay)
            self.assertIn("Add team invites by email", md)
            self.assertIn("Writing the spec", md)
            self.assertIn("4 steps", md)
            pm = postmortem_markdown(replay, deck.load_task("task-abc123"))
            self.assertIn("AssertionError: expected 201", pm)
            self.assertIn("step 3", pm.lower())
            self.assertIn("app/invites.py", pm)
            self.assertIn("not known from the record", pm.lower())
            self.assertNotIn("payment webhook", pm)

    def test_a_green_run_says_nothing_failed(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            deck = staged_run(root, red=False)
            pm = postmortem_markdown(build_replay(root, "task-abc123", deck), deck.load_task("task-abc123"))
            self.assertIn("No failure was recorded", pm)


class ExportRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.deck = staged_run(self.root)
        self.api = V5Api(self.root, provider=lambda: None, run_task=lambda g, r: None, staging=self.deck)

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_kind_exports_as_markdown_and_pdf(self):
        plan = self.api.planner.propose("Add invites", provider=None)
        for path in (f"export/plan/{plan['id']}", "export/replay/task-abc123", "export/postmortem/task-abc123"):
            status, body = self.api.handle("GET", "/api/v5/" + path + ".md")
            self.assertEqual(status, 200, body)
            self.assertIsInstance(body, Download)
            self.assertTrue(body.filename.endswith(".md"))
            self.assertIn("text/markdown", body.content_type)
            status, pdf = self.api.handle("GET", "/api/v5/" + path + ".pdf")
            self.assertEqual(status, 200)
            self.assertEqual(pdf.content_type, "application/pdf")
            self.assertTrue(pdf.data.startswith(b"%PDF"))

    def test_unknown_runs_and_bad_names_are_404s(self):
        for path in ("export/replay/nope.md", "export/postmortem/nope.pdf", "export/plan/plan-12345678.md", "export/plan/..%2F.md", "export/zip/x.md"):
            status, body = self.api.handle("GET", "/api/v5/" + path)
            self.assertIn(status, (400, 404), path)
            self.assertNotIsInstance(body, Download)


class DeskTests(unittest.TestCase):
    def test_desk_shows_the_owners_cards_and_the_recorded_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            deck = staged_run(root)
            board = StatusBoard()
            api = V5Api(root, provider=lambda: None, run_task=lambda g, r: None, staging=deck,
                        status=lambda: StatusReporter(deck, board, provider_name="ollama", model="qwen"))
            doing = api.board.create("Invite API", owner="alpha_be", status="in_progress")
            api.board.create("Rate limits", owner="alpha_be")
            api.board.create("Docs page", owner="zeta_docs")
            status, desk = api.handle("POST", "/api/v5/desk/alpha_be", {"names": {"alpha_be": "Ravi"}})
            self.assertEqual(status, 200, desk)
            self.assertEqual(desk["name"], "Ravi")
            self.assertEqual(desk["cards"]["current"]["id"], doing["id"])
            self.assertEqual(desk["cards"]["next"]["title"], "Rate limits")
            self.assertEqual(desk["cards"]["backlog"], 1)
            self.assertIn("Ravi", desk["working_on"])
            self.assertIn("ETA", "ETA " + desk["eta"])
            self.assertTrue(any("AssertionError" in b for b in desk["blockers"]))
            self.assertEqual(desk["last_run"]["task_id"], "task-abc123")
            self.assertEqual(desk["last_run"]["outcome"], "tests failed")

    def test_unknown_people_are_404s(self):
        with tempfile.TemporaryDirectory() as d:
            api = V5Api(pathlib.Path(d), provider=lambda: None, run_task=lambda g, r: None)
            status, _ = api.handle("POST", "/api/v5/desk/mallory", {})
            self.assertEqual(status, 404)


class OverHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        staged_run(self.root)

    def test_standard_server_sends_files_as_downloads(self):
        server = start_studio_server(self.root, port=0)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        conn.request("GET", "/api/v5/export/postmortem/task-abc123.pdf"); resp = conn.getresponse(); body = resp.read()
        self.assertEqual(resp.status, 200)
        self.assertEqual(resp.getheader("Content-Type"), "application/pdf")
        self.assertIn("attachment", resp.getheader("Content-Disposition"))
        self.assertIn("devsquad-postmortem-task-abc123.pdf", resp.getheader("Content-Disposition"))
        self.assertIn("AssertionError", pdf_text(body))
        conn.request("GET", "/models/people/anim_m.glb"); resp = conn.getresponse(); glb = resp.read()
        self.assertEqual((resp.status, resp.getheader("Content-Type"), glb[:4]), (200, "model/gltf-binary", b"glTF"))
        for bad in ("/models/people/..%2F..%2Fserver%2Fserver.py", "/models/people/LICENSE-Rocketbox.md", "/models/people/nope.glb"):
            conn.request("GET", bad); resp = conn.getresponse(); resp.read()
            self.assertEqual(resp.status, 404, bad)
        conn.request("POST", "/api/v5/desk/gamma_qa", body=json.dumps({}), headers={"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"})
        resp = conn.getresponse(); desk = json.loads(resp.read())
        self.assertEqual((resp.status, desk["name"]), (200, "Gamma QA"))
        conn.close()

    @unittest.skipIf(TestClient is None, "FastAPI isn't installed")
    def test_fastapi_sends_the_same_downloads(self):
        client = TestClient(create_app(self.root), base_url="http://localhost:8080")
        r = client.get("/api/v5/export/replay/task-abc123.md")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn("Writing the spec", r.text)
        self.assertEqual(client.get("/api/v5/export/replay/missing.md").status_code, 404)
        self.assertEqual(client.get("/models/people/anim_f.glb").content[:4], b"glTF")
        self.assertEqual(client.get("/models/people/LICENSE-Rocketbox.md").status_code, 404)
        r = client.post("/api/v5/desk/apex", json={"names": {"apex": "Mira"}}, headers={"Origin": "http://localhost:8080"})
        self.assertEqual(r.json()["name"], "Mira")


if __name__ == "__main__":
    unittest.main()
