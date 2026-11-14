# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Flaky test finder: runs a real test command many times and reports what actually happened.

Each run gets a different PYTHONHASHSEED, so tests that depend on set or dict order show up too.
A failing run's seed is kept, so the failure can be replayed. Causes are only suggested when the
test output contains a clear clue, and they're labelled as likely, never as certain.
"""

import os
import random
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

MAX_RUNS = 50
CLUES = [  # pattern in the failing output, likely cause, what usually fixes it
    (r"timed? ?out|TimeoutError|deadline exceeded", "A timeout: the test waits on something that is sometimes slow.",
     "Wait for the condition instead of a fixed time, or raise the limit for this test."),
    (r"ConnectionRefused|ECONNREFUSED|Connection reset|getaddrinfo|Name or service not known|network",
     "The network or a service the test needs wasn't ready.", "Fake the service in the test, or wait until it's up before the test starts."),
    (r"\bdatetime\b|\btime\.time\b|timestamp|\bnow\(\)|timezone", "The test depends on the clock.",
     "Freeze the time in the test, or compare times with a tolerance."),
    (r"\brandom\b|shuffle|uuid", "The test depends on random values.", "Seed the random generator in the test, or don't assert on random output."),
    (r"database is locked|deadlock|OperationalError|IntegrityError|already exists",
     "State left over from another test or run (database rows, files).", "Give each test its own database or temp folder and clean up after it."),
    (r"Task was destroyed|was never awaited|Event loop is closed|RuntimeWarning: coroutine",
     "Async work that wasn't awaited.", "Await every task the test starts before it ends."),
]


@dataclass
class FlakyTestResult:
    """Outcome of the old simulated stress test, kept for scripts that still call stress_test()."""
    test_identifier: str
    total_runs: int
    passed_runs: int
    failed_runs: int
    flakiness_percentage: float
    is_flaky: bool
    root_cause_diagnosis: str
    hardening_patch: str
    verified_deterministic: bool


def _tail(text: str, lines: int = 25, chars: int = 3000) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])[-chars:]


class FlakyTestDetector:
    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def run_real(self, command: str, runs: int = 10, timeout_s: float = 120.0,
                 run: Optional[Callable[..., subprocess.CompletedProcess]] = None) -> Dict[str, Any]:
        """Runs `command` `runs` times in the project folder. Exit code 0 is a pass.

        The command is split like a shell command but not run through a shell.
        """
        try:
            argv = shlex.split(command or "")
        except ValueError as e:
            return {"status": "error", "error": f"The test command can't be read: {e}"}
        if not argv:
            return {"status": "error", "error": "Give the test command, for example: python3 -m pytest tests/test_login.py::test_token"}
        runs = max(2, min(int(runs or 10), MAX_RUNS))
        run = run or subprocess.run
        results: List[Dict[str, Any]] = []
        started = time.monotonic()
        for i in range(runs):
            seed = random.randint(0, 2 ** 32 - 1)
            env = dict(os.environ, PYTHONHASHSEED=str(seed))
            t0 = time.monotonic()
            try:
                proc = run(argv, cwd=str(self.repo_root), env=env, capture_output=True, text=True, timeout=timeout_s)
                passed, output = proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")
                code: Optional[int] = proc.returncode
            except FileNotFoundError:
                return {"status": "error", "error": f"`{argv[0]}` isn't installed or isn't on the PATH."}
            except subprocess.TimeoutExpired as e:
                passed, code = False, None
                output = f"{e.stdout or ''}{e.stderr or ''}\nThe run timed out after {timeout_s:.0f} seconds."
            results.append({"run": i + 1, "passed": passed, "exit_code": code, "seed": seed,
                            "seconds": round(time.monotonic() - t0, 2), "output": output})

        failed = [r for r in results if not r["passed"]]
        passed_count = runs - len(failed)
        if not failed:
            status, summary = "stable", f"Passed all {runs} runs. No flakiness seen at this many runs."
        elif passed_count == 0:
            status, summary = "always_fails", f"Failed all {runs} runs. This is a real failure, not a flaky one."
        else:
            status = "flaky"
            summary = f"Flaky: failed {len(failed)} of {runs} runs with no code change between them."

        clues = []
        if status == "flaky":
            joined = "\n".join(r["output"] for r in failed)
            for pattern, cause, fix in CLUES:
                if re.search(pattern, joined, re.I):
                    clues.append({"likely_cause": cause, "usual_fix": fix})
        durations = [r["seconds"] for r in results]
        return {
            "status": status,
            "command": command,
            "summary": summary,
            "total_runs": runs,
            "passed_runs": passed_count,
            "failed_runs": len(failed),
            "failure_rate": round(100.0 * len(failed) / runs, 1),
            "seconds": round(time.monotonic() - started, 1),
            "slowest_run_seconds": max(durations),
            "fastest_run_seconds": min(durations),
            "clues": clues[:4],
            "replay": (f"PYTHONHASHSEED={failed[0]['seed']} {command}" if status == "flaky" else ""),
            "first_failure": ({"run": failed[0]["run"], "seed": failed[0]["seed"], "exit_code": failed[0]["exit_code"],
                               "output": _tail(failed[0]["output"])} if failed else None),
            "runs": [{k: r[k] for k in ("run", "passed", "exit_code", "seed", "seconds")} for r in results],
        }

    def stress_test(self, test_name: str, iterations: int = 10, simulated_flaky_rate: float = 0.20) -> FlakyTestResult:
        """Deprecated: a simulation that runs nothing. Use run_real() for real results."""
        failed = sum(1 for _ in range(iterations) if random.random() < simulated_flaky_rate)
        return FlakyTestResult(test_name, iterations, iterations - failed, failed, round(100.0 * failed / iterations, 1),
                               failed > 0, "Simulation only: no test was run.", "", False)
