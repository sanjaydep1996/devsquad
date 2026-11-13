import http.client
import json
import pathlib
import subprocess
import tempfile
import threading
import types
import unittest

from devsquad.core.bootstrapper import Bootstrapper, BootstrapError
from devsquad.core.devops_desk import DevOpsDesk
from devsquad.core.planner import Planner
from devsquad.core.setup_check import RECOMMENDED_MODEL, SetupCheck, vision_model
from devsquad.core.taskboard import BoardError, TaskBoard
from devsquad.server.server import start_studio_server
from devsquad.server.v5_api import V5Api


class FakeProvider:
    provider_name = "ollama"
    model = "qwen2.5-coder:7b"

    def __init__(self, reply="", fail=False):
        self.reply, self.fail, self.prompts = reply, fail, []

    def complete(self, prompt, system="", max_tokens=0):
        self.prompts.append(prompt)
        if self.fail:
            raise ConnectionError("Ollama isn't answering")
        return types.SimpleNamespace(text=self.reply)


class Template:
    provider_name = "template"
    model = "template"


class TempRoot(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)


class TestTaskBoard(TempRoot):
    def setUp(self):
        super().setUp()
        self.clock = iter(range(1000, 2000))
        self.board = TaskBoard(self.root, clock=lambda: next(self.clock))

    def test_cards_are_markdown_files_in_the_repo(self):
        card = self.board.create("Add password reset", body="Email a link.", owner="alpha_be")
        path = self.root / ".devsquad" / "tasks" / f"{card['id']}.md"
        text = path.read_text()
        self.assertTrue(text.startswith("---\n"))
        self.assertIn("title: Add password reset", text)
        self.assertIn("status: backlog", text)
        self.assertTrue(text.rstrip().endswith("Email a link."))

    def test_columns_and_moves(self):
        a = self.board.create("A")
        self.board.create("B")
        self.board.move(a["id"], "review")
        cols = {c["id"]: [x["title"] for x in c["cards"]] for c in self.board.columns()["columns"]}
        self.assertEqual(cols, {"backlog": ["B"], "in_progress": [], "review": ["A"], "merged": []})

    def test_bad_input_is_refused(self):
        with self.assertRaises(BoardError):
            self.board.create("  ")
        with self.assertRaises(BoardError):
            self.board.create("x", owner="mallory")
        card = self.board.create("x")
        with self.assertRaises(BoardError):
            self.board.move(card["id"], "done-ish")
        with self.assertRaises(BoardError):
            self.board.get("../../etc/passwd")

    def test_new_lines_in_titles_cannot_add_fields(self):
        card = self.board.create("Hi\nstatus: merged")
        self.assertEqual(card["status"], "backlog")

    def test_delete(self):
        card = self.board.create("x")
        self.assertTrue(self.board.delete(card["id"]))
        self.assertFalse(self.board.delete(card["id"]))

    def test_github_sync_imports_new_issues_once(self):
        issues = [{"number": 7, "title": "Login is slow", "body": "Takes 9s", "url": "https://github.com/o/r/issues/7"},
                  {"number": 8, "title": "Typo", "body": "", "url": "u"}]
        argv_seen = []

        def gh(argv):
            argv_seen.append(argv)
            return subprocess.CompletedProcess(argv, 0, json.dumps(issues), "")
        first = self.board.sync_github(run=gh)
        second = self.board.sync_github(run=gh)
        self.assertEqual((first["imported"], second["imported"]), (2, 0))
        self.assertEqual(argv_seen[0][:3], ["gh", "issue", "list"])
        self.assertNotIn("close", argv_seen[0])
        card = [c for c in self.board.list() if c.get("issue") == 7][0]
        self.assertEqual(card["title"], "#7 Login is slow")

    def test_github_sync_errors_are_clear(self):
        def missing(argv):
            raise FileNotFoundError()
        with self.assertRaisesRegex(BoardError, "isn't installed"):
            self.board.sync_github(run=missing)
        with self.assertRaisesRegex(BoardError, "gh auth login"):
            self.board.sync_github(run=lambda a: subprocess.CompletedProcess(a, 1, "", "not logged in"))


class TestSetupCheck(TempRoot):
    def check(self, models, which=None):
        c = SetupCheck(self.root, which=which or (lambda name: None))
        c.models = lambda: models
        return c

    def test_nothing_installed(self):
        s = self.check(None).status()
        self.assertFalse(s["ready"])
        self.assertIn("template mode", s["mode"])
        self.assertIn("ollama.com", s["next_step"])

    def test_ollama_running_without_the_coding_model(self):
        s = self.check(["llama3:8b"]).status()
        coding = [c for c in s["checks"] if c["id"] == "coding_model"][0]
        self.assertFalse(coding["ok"])
        self.assertEqual(coding["pull"], RECOMMENDED_MODEL)

    def test_ready_with_the_coding_model_and_git(self):
        (self.root / ".git").mkdir()
        s = self.check(["qwen2.5-coder:7b", "llava:latest"]).status()
        self.assertTrue(s["ready"])
        self.assertEqual(s["vision_model"], "llava:latest")
        self.assertIn("real AI", s["mode"])

    def test_vision_model_names(self):
        self.assertEqual(vision_model(["qwen2.5-coder:7b", "library/moondream:1.8b"]), "library/moondream:1.8b")
        self.assertIsNone(vision_model(["qwen2.5-coder:7b"]))

    def test_pull_refuses_bad_names_and_a_stopped_ollama(self):
        self.assertIn("valid model", self.check([]).pull("x; rm -rf /")["error"])
        self.assertIn("isn't running", self.check(None).pull("llava")["error"])


class TestPlanner(TempRoot):
    def test_template_mode_says_it_is_a_template(self):
        plan = Planner(self.root).propose("Add dark mode", Template())
        self.assertEqual(plan["source"], "template")
        self.assertIn("not an AI plan", plan["note"])
        self.assertEqual(len(plan["tasks"]), 6)

    def test_model_plan_is_used_and_cleaned(self):
        reply = 'Sure!\n```json\n{"summary": "Dark mode", "tasks": [{"title": "Theme tokens", "owner": "beta_fe"}, ' \
                '{"title": "Save choice", "owner": "hacker"}], "risks": ["Contrast"], "questions": ["Follow the OS?"]}\n```'
        provider = FakeProvider(reply)
        plan = Planner(self.root).propose("Add dark mode", provider, reference="REFERENCE: brief")
        self.assertEqual([t["owner"] for t in plan["tasks"]], ["beta_fe", "alpha_be"])
        self.assertEqual(plan["questions"], ["Follow the OS?"])
        self.assertIn("REFERENCE: brief", provider.prompts[0])

    def test_a_failing_model_falls_back_and_says_why(self):
        plan = Planner(self.root).propose("Add dark mode", FakeProvider(fail=True))
        self.assertEqual(plan["source"], "template")
        self.assertIn("isn't answering", plan["note"])

    def test_approving_puts_the_edited_tasks_on_the_board_once(self):
        planner, board = Planner(self.root), TaskBoard(self.root)
        plan = planner.propose("Add dark mode", Template())
        result = planner.approve(plan["id"], board, tasks=[{"title": "Only this", "owner": "beta_fe"}])
        self.assertEqual([c["title"] for c in board.list()], ["Only this"])
        self.assertEqual(result["cards"][0]["plan_id"], plan["id"])
        with self.assertRaisesRegex(ValueError, "already approved"):
            planner.approve(plan["id"], board)

    def test_plan_ids_cannot_reach_other_files(self):
        with self.assertRaises(ValueError):
            Planner(self.root).get("../../secrets")


class TestDevOpsDesk(TempRoot):
    def setUp(self):
        super().setUp()
        (self.root / "requirements.txt").write_text("fastapi\nuvicorn\n")
        (self.root / "app").mkdir()
        (self.root / "app" / "main.py").write_text(
            'import os\nfrom fastapi import FastAPI\napp = FastAPI()\nDB = os.getenv("DATABASE_URL", "sqlite:///x.db")\n'
            'KEY = os.environ["STRIPE_SECRET_KEY"]\nLEVEL = os.environ.get("LOG_LEVEL", "info")\n')
        (self.root / "web.js").write_text("const k = process.env.API_TOKEN;\n")
        self.desk = DevOpsDesk(self.root)

    def test_reads_the_project_instead_of_guessing(self):
        info = self.desk.analyze()
        self.assertEqual((info["language"], info["framework"]), ("python", "fastapi"))
        self.assertIn("uvicorn app.main:app", info["start_command"])
        names = {v["name"]: v for v in info["env_vars"]}
        self.assertEqual(set(names), {"DATABASE_URL", "STRIPE_SECRET_KEY", "LOG_LEVEL", "API_TOKEN"})
        self.assertTrue(names["STRIPE_SECRET_KEY"]["secret"])
        self.assertFalse(names["LOG_LEVEL"]["secret"])

    def test_env_example_never_contains_secret_defaults(self):
        self.desk.generate()
        env = (self.root / ".devsquad" / "devops" / ".env.example").read_text()
        self.assertIn("DATABASE_URL=\n", env)
        self.assertIn("LOG_LEVEL=info", env)
        self.assertNotIn("sqlite:///x.db", env)

    def test_generates_the_files_without_touching_the_project(self):
        r = self.desk.generate()
        self.assertEqual({f["path"] for f in r["files"]}, {"Dockerfile", ".dockerignore", "docker-compose.yml",
                         ".github/workflows/ci.yml", "deploy/cloudrun.yaml", "deploy/k8s.yaml", ".env.example"})
        self.assertFalse((self.root / "Dockerfile").exists())
        docker = (self.root / ".devsquad" / "devops" / "Dockerfile").read_text()
        self.assertIn("USER", docker)

    def test_apply_copies_only_what_is_chosen_and_keeps_existing_files(self):
        self.desk.generate()
        (self.root / ".env.example").write_text("MINE=1\n")
        r = self.desk.apply(["Dockerfile", ".env.example", "../../outside"])
        self.assertEqual(r["written"], ["Dockerfile"])
        self.assertIn(".env.example", r["skipped"])
        self.assertEqual((self.root / ".env.example").read_text(), "MINE=1\n")
        self.assertFalse((self.root.parent / "outside").exists())
        self.assertEqual(self.desk.apply([".env.example"], overwrite=True)["written"], [".env.example"])


class TestBootstrapper(TempRoot):
    def test_known_kinds_of_app_without_a_model(self):
        b = Bootstrapper(self.root)
        spec = b.design("Build me an inventory app with login", Template())
        self.assertEqual((spec["record"], spec["plural"], spec["source"]), ("item", "items", "keywords"))
        self.assertEqual(spec["app_name"], "Inventory")

    def test_model_designs_the_data_but_never_the_code(self):
        reply = '{"app_name": "Gym Log", "record": "workout", "plural": "workouts", "fields": [' \
                '{"name": "exercise", "type": "str"}, {"name": "reps", "type": "int"}, {"name": "id", "type": "int"}, ' \
                '{"name": "import", "type": "str"}, {"name": "weight", "type": "float"}]}'
        r = Bootstrapper(self.root).generate("a gym tracker", FakeProvider(reply))
        self.assertEqual([f["name"] for f in r["spec"]["fields"]], ["exercise", "reps", "weight"])
        main = (self.root / r["staged_at"] / "app" / "main.py").read_text()
        self.assertIn("CREATE TABLE IF NOT EXISTS workouts", main)
        compile(main, "main.py", "exec")

    def test_unusable_model_output_falls_back_to_keywords(self):
        spec = Bootstrapper(self.root).design("a blog", FakeProvider("no json here"))
        self.assertEqual((spec["record"], spec["source"]), ("post", "keywords"))

    def test_generated_files(self):
        r = Bootstrapper(self.root).generate("make a todo tracker", Template())
        self.assertEqual(set(r["files"]), {"app/__init__.py", "app/main.py", "app/static/index.html", "tests/__init__.py",
                                           "tests/test_app.py", "requirements.txt", ".gitignore", "README.md",
                                           "docs/adr/0001-initial-architecture.md"})
        for f in ("app/main.py", "tests/test_app.py"):
            compile((self.root / r["staged_at"] / f).read_text(), f, "exec")
        main = (self.root / r["staged_at"] / "app" / "main.py").read_text()
        self.assertIn("pbkdf2_hmac", main)
        self.assertIn("owner_id = ?", main)

    def test_apply_only_writes_into_a_new_or_empty_folder(self):
        b = Bootstrapper(self.root)
        slug = b.generate("make a todo tracker", Template())["slug"]
        target = self.root.parent / (self.root.name + "-newapp")
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(target)]))
        self.assertIn("app/main.py", b.apply(slug, str(target))["files"])
        with self.assertRaisesRegex(BootstrapError, "already has files"):
            b.apply(slug, str(target))
        with self.assertRaises(BootstrapError):
            b.apply("../x", str(target) + "2")
        with self.assertRaises(BootstrapError):
            b.design("   ")


class TestV5Assign(TempRoot):
    def test_assign_runs_the_squad_and_moves_the_card_to_review(self):
        goals = []
        api = V5Api(self.root, Template, lambda goal, ref: goals.append(goal) or types.SimpleNamespace(task_id="task-1", status="staged"))
        card = api.board.create("Add CSV export", body="Admins only")
        status, body = api.handle("POST", f"/api/v5/board/{card['id']}/assign", {})
        self.assertEqual(status, 200)
        self.assertEqual((body["card"]["status"], body["card"]["task_id"]), ("review", "task-1"))
        self.assertEqual(goals, ["Add CSV export\n\nAdmins only"])
        self.assertEqual(api.handle("POST", f"/api/v5/board/{card['id']}/assign", {})[0], 400)

    def test_a_failed_run_puts_the_card_back_with_the_reason(self):
        def boom(goal, ref):
            raise RuntimeError("model crashed")
        api = V5Api(self.root, Template, boom)
        card = api.board.create("X")
        status, body = api.handle("POST", f"/api/v5/board/{card['id']}/assign", {})
        self.assertEqual(status, 500)
        self.assertEqual(body["card"]["status"], "backlog")
        self.assertIn("model crashed", body["card"]["body"])


class TestV5OverHttp(TempRoot):
    def setUp(self):
        super().setUp()
        self.server = start_studio_server(self.root, port=0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def call(self, path, method="GET", payload=None, origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        try:
            conn.request(method, path, body=json.dumps(payload) if payload is not None else None, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except ValueError:
                return resp.status, raw
        finally:
            conn.close()

    def test_board_round_trip(self):
        me = f"http://127.0.0.1:{self.port}"
        status, card = self.call("/api/v5/board", "POST", {"title": "Ship v0.5", "owner": "delta_devops"}, origin=me)
        self.assertEqual(status, 201)
        self.assertEqual(self.call(f"/api/v5/board/{card['id']}/move", "POST", {"status": "merged"}, origin=me)[1]["status"], "merged")
        cols = self.call("/api/v5/board")[1]["columns"]
        self.assertEqual([c["title"] for c in cols], ["Backlog", "In progress", "Review Desk", "Merged"])
        self.assertEqual(cols[3]["cards"][0]["title"], "Ship v0.5")
        self.assertEqual(self.call(f"/api/v5/board/{card['id']}", "DELETE", origin=me)[0], 200)

    def test_other_sites_cannot_change_anything(self):
        evil = "https://evil.example"
        for path, payload in [("/api/v5/board", {"title": "x"}), ("/api/v5/devops/apply", {"paths": ["Dockerfile"]}),
                              ("/api/v5/greenfield/apply", {"slug": "a", "target": "/tmp/x"}), ("/api/v5/flaky", {"command": "ls"}),
                              ("/api/v5/setup/pull", {"model": "llava"})]:
            self.assertEqual(self.call(path, "POST", payload, origin=evil)[0], 403, path)
        self.assertFalse((self.root / ".devsquad" / "tasks").exists())

    def test_plan_then_approve(self):
        me = f"http://localhost:{self.port}"
        status, plan = self.call("/api/v5/plan", "POST", {"goal": "Add search"}, origin=me)
        self.assertEqual(status, 201)
        status, result = self.call(f"/api/v5/plan/{plan['id']}/approve", "POST", {}, origin=me)
        self.assertEqual(status, 200)
        self.assertEqual(len(result["cards"]), len(plan["tasks"]))

    def test_errors_are_json_with_a_message(self):
        status, body = self.call("/api/v5/board", "POST", {"title": ""}, origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(status, 400)
        self.assertIn("needs a title", body["error"])
        self.assertEqual(self.call("/api/v5/nope")[0], 404)

    def test_greenfield_and_devops_over_http(self):
        me = f"http://127.0.0.1:{self.port}"
        status, app = self.call("/api/v5/greenfield", "POST", {"prompt": "a recipe app"}, origin=me)
        self.assertEqual((status, app["spec"]["record"]), (201, "recipe"))
        status, desk = self.call("/api/v5/devops/generate", "POST", {}, origin=me)
        self.assertEqual(status, 200)
        self.assertEqual({f["path"] for f in desk["files"]}, {".env.example"})   # an empty folder isn't an app yet
        self.assertIn("No Python or Node project", desk["note"])



try:
    from fastapi.testclient import TestClient
    from devsquad.server.fastapi_app import create_app
except ImportError:  # FastAPI is optional
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI isn't installed")
class TestV5OnFastApi(TempRoot):
    def test_same_routes_and_same_guard(self):
        client = TestClient(create_app(self.root), base_url="http://localhost:8080")
        me = {"Origin": "http://localhost:8080"}
        r = client.post("/api/v5/board", json={"title": "From FastAPI"}, headers=me)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(client.get("/api/v5/board").json()["columns"][0]["cards"][0]["title"], "From FastAPI")
        self.assertEqual(client.post("/api/v5/board", json={"title": "x"}, headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(client.post("/api/v5/board", json={"title": ""}, headers=me).status_code, 400)
        self.assertEqual(client.post("/api/v1/flaky/stress-test", json={"command": ""}, headers=me).json()["status"], "error")


if __name__ == "__main__":
    unittest.main()
