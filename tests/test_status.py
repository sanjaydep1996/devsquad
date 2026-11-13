# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Status answers: "What is Delta working on?" gets facts DevSquad actually has, never invented progress."""

import pathlib
import tempfile
import unittest

from devsquad.core.runner import TestRunResult
from devsquad.core.staging import StagingDeck
from devsquad.core.status import StatusBoard, StatusReporter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class StatusTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.staging = StagingDeck(pathlib.Path(tmp.name))
        self.clock = FakeClock()
        self.board = StatusBoard(clock=self.clock)
        self.reporter = StatusReporter(self.staging, self.board, provider_name="ollama", model="qwen2.5-coder:7b")

    def finished_task(self, tid, goal, status="tested_green", seconds=40, failure=None):
        task = self.staging.create_task(tid, goal)
        task.status = status
        task.relay_logs = ["[10:00:00] [System] ANALYSIS: start", f"[10:00:{seconds:02d}] [Delta] STAGED: done"]
        task.git_branch = "feat/" + tid
        task.test_result = TestRunResult(passed=status == "tested_green", exit_code=0 if status == "tested_green" else 1,
                                         duration_s=1.0, command="pytest", output="", failure_summary=failure)
        self.staging.save_task(task)
        return task

    def start(self, goal="Add login page", agent="Alpha", event="CODING", message="Implementing solution in src/login.py..."):
        self.board.record("System", "ANALYSIS", {"task_id": "task-live", "goal": goal, "message": "Analyzing"})
        self.clock.now += 5
        self.board.record(agent, event, {"task_id": "task-live", "goal": goal, "message": message})


class TestIsItAQuestion(StatusTestCase):
    def test_status_questions_are_answered(self):
        for q in ("What is Delta working on?", "what's alpha doing", "Any blockers?", "ETA for the login page?",
                  "status", "Is Gamma blocked?", "How is the team doing?", "What decisions do you need from me?",
                  "who is working right now?", "give me a status update"):
            self.assertIsNotNone(self.reporter.answer(q), q)

    def test_tasks_are_not_mistaken_for_questions(self):
        for q in ("Build a login page", "Add a status column to the orders table", "Fix the blocked user bug",
                  "Create an ETA calculator for deliveries", "Write tests for the progress bar"):
            self.assertIsNone(self.reporter.answer(q), q)


class TestWhoIsAsked(StatusTestCase):
    def test_finds_the_agent_by_default_name_role_or_custom_name(self):
        cases = {"What is Delta working on?": "delta_devops", "what is the backend dev doing?": "alpha_be",
                 "Is QA blocked?": "gamma_qa", "what's Priya doing?": "apex", "status of beta fe": "beta_fe"}
        for q, expected in cases.items():
            self.assertEqual(self.reporter.answer(q, names={"apex": "Priya"})["agents"][0]["id"], expected, q)

    def test_no_name_means_the_selected_agent(self):
        self.assertEqual(self.reporter.answer("what are you working on?", selected="zeta_docs")["agents"][0]["id"], "zeta_docs")

    def test_team_questions_cover_everyone(self):
        self.assertEqual(len(self.reporter.answer("How is the team doing?")["agents"]), 6)

    def test_answers_use_the_custom_name(self):
        self.assertEqual(self.reporter.answer("what is apex doing?", names={"apex": "Priya"})["agents"][0]["name"], "Priya")


class TestWhatTheyAreDoing(StatusTestCase):
    def test_idle_is_reported_as_idle(self):
        report = self.reporter.answer("What is Delta working on?")["agents"][0]
        self.assertEqual(report["state"], "idle")
        self.assertIn("isn't working on anything", report["working_on"])

    def test_the_agent_on_the_current_stage_is_working(self):
        self.start()
        self.clock.now += 7
        report = self.reporter.answer("what is alpha doing?")["agents"][0]
        self.assertEqual(report["state"], "working")
        self.assertIn("Add login page", report["working_on"])
        self.assertIn("Implementing solution in src/login.py", report["working_on"])
        self.assertIn("7 seconds", report["working_on"])

    def test_an_agent_whose_stage_comes_later_is_waiting(self):
        self.start()
        report = self.reporter.answer("What is Delta working on?")["agents"][0]
        self.assertEqual(report["state"], "waiting")
        self.assertIn("Add login page", report["working_on"])

    def test_an_agent_whose_stage_is_over_says_so(self):
        self.start()
        report = self.reporter.answer("what is apex doing?")["agents"][0]
        self.assertEqual(report["state"], "done")

    def test_agents_with_no_stage_in_the_relay_say_so(self):
        self.start()
        report = self.reporter.answer("what is beta fe doing?")["agents"][0]
        self.assertEqual(report["state"], "idle")
        self.assertIn("no stage", report["working_on"])

    def test_a_finished_run_goes_back_to_idle(self):
        self.start()
        self.board.finish()
        self.assertEqual(self.reporter.answer("what is alpha doing?")["agents"][0]["state"], "idle")

    def test_last_finished_work_is_reported(self):
        self.finished_task("t1", "Add signup form")
        report = self.reporter.answer("What is Delta working on?")["agents"][0]
        self.assertIn("Add signup form", report["last_done"])


class TestEta(StatusTestCase):
    def test_no_history_means_no_estimate(self):
        self.start()
        self.assertIn("No estimate", self.reporter.answer("ETA?")["eta"])

    def test_estimate_comes_from_past_tasks_and_says_so(self):
        for i, secs in enumerate((30, 40, 50)):
            self.finished_task(f"t{i}", f"task {i}", seconds=secs)
        self.start()
        self.clock.now += 5     # 10 seconds into the run
        eta = self.reporter.answer("ETA?")["eta"]
        self.assertIn("30 seconds", eta)
        self.assertIn("3 finished tasks", eta)
        self.assertIn("estimate", eta.lower())

    def test_a_run_past_its_usual_time_says_it_is_overdue(self):
        self.finished_task("t1", "task", seconds=20)
        self.start()
        self.clock.now += 60
        self.assertIn("longer than usual", self.reporter.answer("ETA?")["eta"])

    def test_nothing_running_means_nothing_to_estimate(self):
        self.assertIn("Nothing is running", self.reporter.answer("ETA?")["eta"])


class TestBlockersDecisionsSuggestions(StatusTestCase):
    def test_template_mode_is_a_blocker(self):
        reporter = StatusReporter(self.staging, self.board, provider_name="template", model="template-offline")
        answer = reporter.answer("Any blockers?")
        self.assertTrue(any("template" in b.lower() for b in answer["blockers"]))
        self.assertTrue(any("Ollama" in s for s in answer["suggestions"]))

    def test_failed_tests_are_a_blocker_with_the_reason(self):
        self.finished_task("t1", "Add signup form", status="tested_red", failure="AssertionError: expected 200 got 500")
        answer = self.reporter.answer("Any blockers?")
        self.assertTrue(any("Add signup form" in b and "expected 200 got 500" in b for b in answer["blockers"]))

    def test_one_cause_across_many_tasks_is_reported_once(self):
        for i in range(4):
            self.finished_task(f"t{i}", f"task {i}", status="tested_red", failure="[Errno 2] No such file or directory: 'pytest'")
        answer = self.reporter.answer("Any blockers?")
        self.assertEqual(len(answer["blockers"]), 1)
        self.assertIn("4 tasks", answer["blockers"][0])
        self.assertTrue(any("pip install pytest" in s for s in answer["suggestions"]))
        self.assertEqual(len(answer["decisions"]), 4)       # three tasks plus "1 more"
        self.assertIn("1 more", answer["decisions"][-1])

    def test_no_blockers_says_none(self):
        self.assertEqual(self.reporter.answer("Any blockers?")["blockers"], [])

    def test_tasks_waiting_for_review_are_decisions(self):
        self.finished_task("t1", "Add signup form")
        self.finished_task("t2", "Old one", status="applied")
        decisions = self.reporter.answer("What decisions do you need?")["decisions"]
        self.assertEqual(len(decisions), 1)
        self.assertIn("Add signup form", decisions[0])
        self.assertIn("Review Desk", decisions[0])

    def test_an_idle_team_with_nothing_pending_suggests_starting_a_task(self):
        self.assertTrue(any("task" in s.lower() for s in self.reporter.answer("status")["suggestions"]))

    def test_the_answer_has_plain_text_too(self):
        self.finished_task("t1", "Add signup form", status="tested_red", failure="boom")
        text = self.reporter.answer("What is Delta working on?")["text"]
        for heading in ("ETA", "Blockers", "Decisions needed", "Suggestions"):
            self.assertIn(heading, text)


class TestAskOverHttp(unittest.TestCase):
    def setUp(self):
        import http.client, json, threading
        from devsquad.server.server import start_studio_server
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.server = start_studio_server(pathlib.Path(tmp.name), port=0)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

        def ask(question, **extra):
            conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=20)
            try:
                conn.request("POST", "/api/ask", body=json.dumps({"question": question, **extra}))
                return json.loads(conn.getresponse().read())
            finally:
                conn.close()
        self.ask = ask

    def test_a_question_is_answered_and_a_task_is_not(self):
        answer = self.ask("What is Delta working on?", names={"delta_devops": "Dev"})
        self.assertTrue(answer["answered"])
        self.assertEqual(answer["agents"][0]["name"], "Dev")
        self.assertEqual(self.ask("Build a login page"), {"answered": False})

    def test_after_a_real_run_the_team_is_idle_and_the_task_needs_a_decision(self):
        import http.client, json
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=60)
        conn.request("POST", "/api/spawn", body=json.dumps({"agent": "apex", "task": "Add a health check"}))
        self.assertEqual(conn.getresponse().status, 200)
        conn.close()
        answer = self.ask("How is the team doing?")
        self.assertTrue(all(a["state"] == "idle" for a in answer["agents"]))
        self.assertTrue(any("Add a health check" in d for d in answer["decisions"]))


if __name__ == "__main__":
    unittest.main()
