"""Lessons from reviews, the research desk, shipping a reviewed change, and the code review agent."""

import pathlib
import subprocess
import tempfile
import unittest

from devsquad.core.code_review import CodeReviewer, parse_diff
from devsquad.core.diff import FileDiff
from devsquad.core.knowledge import KnowledgeBase
from devsquad.core.research import ResearchDesk, choose_method
from devsquad.core.runner import TestRunResult
from devsquad.core.shipping import ShipError, Shipper
from devsquad.core.staging import StagingDeck
from devsquad.server.v5_api import V5Api


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


class Repo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = pathlib.Path(self.tmp.name)
        self.remote, self.root = base / "remote.git", base / "app"
        git(base, "init", "-q", "--bare", str(self.remote))
        self.root.mkdir()
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "config", "user.email", "dev@example.com"); git(self.root, "config", "user.name", "Dev")
        (self.root / "app.py").write_text("print('hi')\n")
        (self.root / "notes.txt").write_text("my uncommitted work\n")
        git(self.root, "add", "app.py"); git(self.root, "commit", "-q", "-m", "init")
        git(self.root, "remote", "add", "origin", str(self.remote))
        self.deck = StagingDeck(self.root)
        task = self.deck.create_task("task-ship01", "Add a greeting")
        task.git_branch = "feat/greeting"
        task.artifacts["COMMIT_MSG"] = "feat: add a greeting"
        task.artifacts["decisions.md"] = "# Decisions from the field guides\n\n- **alpha_be**: Validate at the edge\n"
        task.diffs = [FileDiff("src/greet.py", "", "def greet():\n    return 'hi'\n", "+def greet():", 2, 0, is_new=True)]
        task.test_result = TestRunResult(True, 0, 0.4, "pytest", "ok")
        task.status = "tested_green"
        self.deck.save_task(task)
        self.task = self.deck.load_task("task-ship01")


class LessonTests(Repo):
    def test_a_rejection_becomes_a_rule_the_agents_use(self):
        api = V5Api(self.root, provider=lambda: None, run_task=lambda g, r: None, staging=self.deck)
        status, body = api.handle("POST", "/api/v5/review/task-ship01/lesson",
                                  {"verdict": "avoid", "reason": "Never log the password reset token, even in debug", "reject": True})
        self.assertEqual(status, 200, body)
        self.assertEqual((body["lesson"]["field"], body["status"]), ("Security", "rejected"))
        kb = KnowledgeBase(self.root)
        titles = [e.title for e in kb.brief("alpha_be", "Add a password reset token email")]
        self.assertTrue(any(t.startswith("Avoid: Never log the password reset token") for t in titles), titles)

    def test_a_lesson_needs_a_reason(self):
        api = V5Api(self.root, provider=lambda: None, run_task=lambda g, r: None, staging=self.deck)
        self.assertEqual(api.handle("POST", "/api/v5/review/task-ship01/lesson", {"verdict": "keep", "reason": "ok"})[0], 400)
        self.assertEqual(api.handle("POST", "/api/v5/review/nope/lesson", {"verdict": "keep", "reason": "a good reason"})[0], 404)


class ResearchTests(unittest.TestCase):
    def test_the_question_picks_the_method(self):
        self.assertEqual(choose_method("Why do people drop out of the trial?"), "interviews")
        self.assertEqual(choose_method("Can users finish checkout on mobile?"), "usability")
        self.assertEqual(choose_method("How many people use dark mode?"), "survey")
        self.assertEqual(choose_method("Which version of the pricing page converts better?"), "ab_test")
        self.assertEqual(choose_method("Where would people look for billing in the menu?"), "card_sort")
        self.assertEqual(choose_method("How do teams plan their week over time?"), "diary")

    def test_a_plan_has_everything_to_run_the_study_and_exports(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            api = V5Api(root, provider=lambda: None, run_task=lambda g, r: None)
            status, plan = api.handle("POST", "/api/v5/research", {"question": "Why do people drop off during onboarding?"})
            self.assertEqual(status, 201)
            self.assertEqual(plan["method"], "usability")
            self.assertTrue(plan["script"] and plan["participants"] and plan["synthesis"])
            self.assertEqual(api.handle("GET", f"/api/v5/research/{plan['id']}")[1]["question"], plan["question"])
            status, md = api.handle("GET", f"/api/v5/export/research/{plan['id']}.md")
            self.assertEqual(status, 200)
            self.assertIn(b"Research plan", md.data)
            self.assertEqual(api.handle("POST", "/api/v5/research", {"question": "hi"})[0], 400)


class ShipTests(Repo):
    def fake_gh(self, calls):
        def run(argv, cwd):
            if argv[0] == "gh":
                calls.append(argv)
                out = "https://github.com/me/app/pull/7\n" if argv[1:3] == ["pr", "create"] else ""
                return subprocess.CompletedProcess(argv, 0, out, "")
            return subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
        return run

    def test_preview_shows_what_will_happen_and_ships_nothing(self):
        plan = Shipper(self.root, self.fake_gh([])).preview(self.task)
        self.assertTrue(plan["ready"], plan["problems"])
        self.assertEqual((plan["branch"], plan["pr_title"]), ("feat/greeting", "feat: add a greeting"))
        self.assertIn("Decisions from the field guides", plan["pr_body"])
        self.assertEqual(git(self.root, "ls-remote", "origin"), "")

    def test_shipping_needs_confirmation(self):
        with self.assertRaises(ShipError):
            Shipper(self.root, self.fake_gh([])).ship(self.task, confirm=False)

    def test_ship_commits_on_a_new_branch_pushes_and_opens_a_pr_without_touching_the_working_copy(self):
        calls = []
        result = Shipper(self.root, self.fake_gh(calls)).ship(self.task, confirm=True)
        self.assertEqual(result["pr_url"], "https://github.com/me/app/pull/7")
        self.assertIn("feat/greeting", git(self.root, "ls-remote", "origin"))
        self.assertEqual(git(self.root, "show", "feat/greeting:src/greet.py"), "def greet():\n    return 'hi'")
        self.assertEqual(git(self.root, "branch", "--show-current"), "main")
        self.assertFalse((self.root / "src" / "greet.py").exists())
        self.assertEqual((self.root / "notes.txt").read_text(), "my uncommitted work\n")
        self.assertEqual(git(self.root, "worktree", "list").count("\n"), 0)
        self.assertTrue(any(c[1:3] == ["pr", "create"] for c in calls))

    def test_unsafe_paths_are_refused(self):
        self.task.diffs = [FileDiff("../outside.py", "", "x", "+x", 1, 0)]
        with self.assertRaises(ShipError):
            Shipper(self.root, self.fake_gh([])).ship(self.task, confirm=True)
        self.assertEqual(git(self.root, "ls-remote", "origin"), "")


class CodeReviewTests(Repo):
    def test_findings_point_at_new_lines_and_name_their_guide(self):
        (self.root / "app.py").write_text("print('hi')\nimport hashlib, subprocess\nAPI_KEY = 'sk_live_1234567890abcdef'\nsubprocess.run(cmd, shell=True)\nh = hashlib.md5(pw)\n")
        report = CodeReviewer(self.root).review("working")
        rules = {f["rule"]: f for f in report["findings"]}
        self.assertTrue({"secret", "shell", "weak-hash", "no-tests"} <= set(rules), rules.keys())
        self.assertEqual((rules["secret"]["file"], rules["secret"]["line"]), ("app.py", 3))
        self.assertTrue(all(f["source"] for f in report["findings"]))
        self.assertGreater(report["counts"]["high"], 2)

    def test_staged_runs_and_branches_can_be_reviewed(self):
        report = CodeReviewer(self.root, staging=self.deck).review("staged:task-ship01")
        self.assertIn("staged run", report["label"])
        git(self.root, "checkout", "-q", "-b", "feature")
        (self.root / "page.html").write_text("<div onClick=\"go()\"><img src=a.png></div>\n")
        git(self.root, "add", "page.html"); git(self.root, "commit", "-q", "-m", "page")
        rules = {f["rule"] for f in CodeReviewer(self.root).review("feature")["findings"]}
        self.assertTrue({"img-alt", "div-click"} <= rules)
        with self.assertRaises(ValueError):
            CodeReviewer(self.root).review("--output=/tmp/x")

    def test_diff_parser_numbers_added_lines(self):
        files = parse_diff("+++ b/a.py\n@@ -1,2 +1,3 @@\n keep\n+new one\n-old\n+new two\n")
        self.assertEqual(files[0]["added"], [(2, "new one"), (3, "new two")])


if __name__ == "__main__":
    unittest.main()
