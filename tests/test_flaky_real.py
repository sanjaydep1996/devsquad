import pathlib
import subprocess
import sys
import tempfile
import unittest

from devsquad.core.flaky_detector import FlakyTestDetector

# Fails on every third run, using a counter file, so the "flaky" result is the same every time.
FLAKY = """
import pathlib, sys
p = pathlib.Path("count.txt")
n = int(p.read_text()) + 1 if p.exists() else 1
p.write_text(str(n))
if n % 3 == 0:
    print("AssertionError: expected 200, got 503: Connection reset by peer")
    sys.exit(1)
print("ok")
"""


class TestRealFlakyRuns(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = pathlib.Path(tmp.name)
        (self.root / "flaky.py").write_text(FLAKY)
        (self.root / "ok.py").write_text("print('fine')\n")
        (self.root / "broken.py").write_text("raise SystemExit('always broken')\n")
        (self.root / "seed.py").write_text("import os; print(os.environ['PYTHONHASHSEED'])\n")
        self.detector = FlakyTestDetector(self.root)

    def cmd(self, script):
        return f"{sys.executable} {script}"

    def test_a_test_that_sometimes_fails_is_flaky(self):
        r = self.detector.run_real(self.cmd("flaky.py"), runs=6)
        self.assertEqual(r["status"], "flaky")
        self.assertEqual((r["passed_runs"], r["failed_runs"]), (4, 2))
        self.assertEqual([x["passed"] for x in r["runs"]], [True, True, False, True, True, False])
        self.assertEqual(r["first_failure"]["run"], 3)
        self.assertIn("Connection reset", r["first_failure"]["output"])
        self.assertIn("network", r["clues"][0]["likely_cause"])
        self.assertTrue(r["replay"].startswith(f"PYTHONHASHSEED={r['first_failure']['seed']} "))

    def test_a_stable_test_is_reported_stable_with_no_guesses(self):
        r = self.detector.run_real(self.cmd("ok.py"), runs=3)
        self.assertEqual(r["status"], "stable")
        self.assertEqual(r["clues"], [])
        self.assertIsNone(r["first_failure"])

    def test_a_test_that_always_fails_is_not_called_flaky(self):
        r = self.detector.run_real(self.cmd("broken.py"), runs=3)
        self.assertEqual(r["status"], "always_fails")
        self.assertIn("always broken", r["first_failure"]["output"])
        self.assertEqual(r["clues"], [])

    def test_each_run_gets_its_own_hash_seed(self):
        seen = []
        def fake_run(argv, **kw):
            seen.append(kw["env"]["PYTHONHASHSEED"])
            return subprocess.CompletedProcess(argv, 0, "", "")
        r = self.detector.run_real("python3 x.py", runs=5, run=fake_run)
        self.assertEqual(seen, [str(x["seed"]) for x in r["runs"]])
        self.assertGreater(len(set(seen)), 1)

    def test_runs_are_capped_and_floored(self):
        calls = []
        fake = lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")
        self.detector.run_real("x", runs=500, run=fake)
        self.assertEqual(len(calls), 50)
        calls.clear()
        self.detector.run_real("x", runs=1, run=fake)
        self.assertEqual(len(calls), 2)

    def test_timeouts_count_as_failures(self):
        def slow(argv, **kw):
            raise subprocess.TimeoutExpired(argv, kw["timeout"])
        r = self.detector.run_real("x", runs=2, timeout_s=5, run=slow)
        self.assertEqual(r["status"], "always_fails")
        self.assertIn("timed out after 5 seconds", r["first_failure"]["output"])

    def test_bad_commands_give_a_clear_error_and_no_shell_runs(self):
        self.assertEqual(self.detector.run_real("")["status"], "error")
        self.assertEqual(self.detector.run_real("pytest 'unclosed")["status"], "error")
        missing = self.detector.run_real("definitely-not-a-real-command-xyz --flag")
        self.assertIn("isn't installed", missing["error"])
        r = self.detector.run_real(self.cmd("ok.py") + " ; touch hacked", runs=2)
        self.assertFalse((self.root / "hacked").exists())


if __name__ == "__main__":
    unittest.main()
