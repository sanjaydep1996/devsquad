import http.client
import json
import pathlib
import tempfile
import threading
import unittest

from devsquad.core.flight_recorder import FlightRecorder
from devsquad.core.replay import agent_id, build_replay
from devsquad.core.staging import StagingDeck
from devsquad.server.server import start_studio_server


class TestReplay(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)

    def test_steps_come_from_the_flight_recorder(self):
        rec = FlightRecorder(self.root)
        rec.record_event("task-1", 1, "Apex", "PLANNING", payload={"message": "Planning login", "goal": "Add login"})
        rec.record_event("task-1", 2, "Alpha", "CODING", payload={"message": "Writing auth.py"})
        rec.record_event("task-1", 3, "Gamma", "TESTS_RED", status="error", payload={"message": "1 failed"})
        r = build_replay(self.root, "task-1", provider="ollama", model="qwen2.5-coder:7b")
        self.assertEqual(r["goal"], "Add login")
        self.assertEqual([s["agent_name"] for s in r["steps"]], ["apex", "alpha_be", "gamma_qa"])
        self.assertEqual(r["steps"][1]["tool_name"], "CODING: Writing auth.py")
        self.assertEqual(r["steps"][2]["status"], "failed")
        self.assertEqual((r["total_cost_usd"], r["steps"][0]["provider"]), (0.0, "ollama"))

    def test_older_runs_replay_from_their_log(self):
        deck = StagingDeck(self.root)
        task = deck.create_task("task-old", "Fix the header")
        task.relay_logs = ["[10:00:00] [Apex] PLANNING: Plan it", "[10:00:04] [Delta] CI_READY: Pipeline added"]
        deck.save_task(task)
        r = build_replay(self.root, "task-old", staging=deck)
        self.assertEqual([s["agent_name"] for s in r["steps"]], ["apex", "delta_devops"])
        self.assertEqual(r["steps"][0]["duration_ms"], 4000)

    def test_unknown_or_unsafe_ids_have_no_replay(self):
        self.assertIsNone(build_replay(self.root, "nope"))
        self.assertIsNone(build_replay(self.root, "../../etc/passwd"))

    def test_agent_names_map_to_teammates(self):
        self.assertEqual([agent_id(n) for n in ("Alpha BE", "beta", "Zeta", "System")], ["alpha_be", "beta_fe", "zeta_docs", "System"])

    def test_route_over_http(self):
        FlightRecorder(self.root).record_event("task-9", 1, "Apex", "PLANNING", payload={"message": "go"})
        server = start_studio_server(self.root, port=0)
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        conn.request("GET", "/api/replay?session_id=task-9"); resp = conn.getresponse()
        self.assertEqual((resp.status, json.loads(resp.read())["step_count"]), (200, 1))
        conn.request("GET", "/api/replay?session_id=missing"); resp = conn.getresponse(); resp.read()
        self.assertEqual(resp.status, 404)
        conn.close()


if __name__ == "__main__":
    unittest.main()
