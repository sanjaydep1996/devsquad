# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Subprocess test runner: safely executes test suites and extracts failure diagnostics."""

import os
import pathlib
import subprocess
import time
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TestRunResult:
    passed: bool
    exit_code: int
    duration_s: float
    command: str
    output: str
    failure_summary: Optional[str] = None


class SandboxRunner:
    """Executes local test harnesses with timeouts and structured diagnosis."""

    def __init__(self, root: Optional[pathlib.Path] = None, timeout_s: float = 60.0):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.timeout_s = timeout_s

    def run_tests(self, command: Optional[List[str]] = None) -> TestRunResult:
        """Runs the test suite and captures output."""
        cmd = command or ["pytest", "-v"]
        cmd_str = " ".join(cmd)
        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=self.timeout_s,
                env=os.environ.copy(),
            )
            duration = time.time() - start
            passed = (proc.returncode == 0)
            output = proc.stdout or ""
            failure_summary = None if passed else self._extract_failure_summary(output)

            return TestRunResult(
                passed=passed,
                exit_code=proc.returncode,
                duration_s=round(duration, 3),
                command=cmd_str,
                output=output,
                failure_summary=failure_summary,
            )

        except subprocess.TimeoutExpired as e:
            duration = time.time() - start
            return TestRunResult(
                passed=False,
                exit_code=124,
                duration_s=round(duration, 3),
                command=cmd_str,
                output=f"Test run timed out after {self.timeout_s}s.\n{e.stdout or ''}",
                failure_summary=f"TimeoutExpired: Test execution took longer than {self.timeout_s} seconds.",
            )
        except Exception as e:
            duration = time.time() - start
            return TestRunResult(
                passed=False,
                exit_code=1,
                duration_s=round(duration, 3),
                command=cmd_str,
                output=f"Subprocess execution error: {e}",
                failure_summary=str(e),
            )

    @staticmethod
    def _extract_failure_summary(output: str) -> str:
        """Extracts key traceback or failure summary from test output."""
        lines = output.splitlines()
        failures = []
        capture = False

        for line in lines:
            if "FAILURES" in line or "ERRORS" in line or "AssertionError" in line or "FAILED" in line:
                capture = True
            if capture:
                failures.append(line)
                if len(failures) > 25:
                    failures.append("... [truncated diagnostics]")
                    break

        if not failures:
            # Fallback to the last 15 lines of output
            failures = lines[-15:]

        return "\n".join(failures).strip()
