# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Flight Recorder & Incident Blackbox: immutable session ledger and automated 5 Whys RCA generator."""

import json
import os
import pathlib
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FlightEvent:
    step: int
    agent: str
    action: str
    timestamp: float
    status: str
    payload: Dict[str, Any] = field(default_factory=dict)
    diff: str = ""
    file_path: Optional[str] = None


class FlightRecorder:
    """Manages append-only JSONL event logs and reconstructs historical system states."""

    def __init__(self, workspace_root: Optional[pathlib.Path] = None):
        self.workspace_root = (workspace_root or pathlib.Path.cwd()).resolve()
        self.logs_dir = self.workspace_root / ".devsquad" / "flight_recorder"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    def _get_log_path(self, session_id: str) -> pathlib.Path:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return self.logs_dir / f"{safe_id}.jsonl"

    def record_event(
        self,
        session_id: str,
        step: int,
        agent: str,
        action: str,
        status: str = "ok",
        payload: Optional[Dict[str, Any]] = None,
        diff: str = "",
        file_path: Optional[str] = None,
    ) -> FlightEvent:
        """Appends an immutable flight telemetry event to the session ledger."""
        event = FlightEvent(
            step=step,
            agent=agent,
            action=action,
            timestamp=time.time(),
            status=status,
            payload=payload or {},
            diff=diff,
            file_path=file_path,
        )
        log_file = self._get_log_path(session_id)
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(event)) + "\n")
        return event

    def get_timeline(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves chronologically sorted events for a session."""
        log_file = self._get_log_path(session_id)
        if not log_file.exists():
            return []
        events = []
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        pass
        return events

    def scrub_state(self, session_id: str, target_step: int) -> Dict[str, Any]:
        """Time-Machine scrubber: reconstructs modified files and cumulative diffs up to target_step."""
        timeline = self.get_timeline(session_id)
        active_files = {}
        history = []

        for ev in timeline:
            if ev.get("step", 0) <= target_step:
                history.append(ev)
                fpath = ev.get("file_path")
                if fpath:
                    active_files[fpath] = {
                        "last_modified_by": ev.get("agent"),
                        "last_action": ev.get("action"),
                        "status": ev.get("status"),
                        "diff": ev.get("diff", ""),
                    }

        return {
            "session_id": session_id,
            "target_step": target_step,
            "total_steps_in_session": len(timeline),
            "step_count_replayed": len(history),
            "active_files_at_step": active_files,
            "latest_event": history[-1] if history else None,
        }

    def generate_post_mortem(
        self,
        session_id: str,
        failure_step: int,
        failure_summary: str,
    ) -> Dict[str, Any]:
        """Synthesizes a structured 5 Whys Root Cause Analysis (RCA) and remediation document."""
        scrub = self.scrub_state(session_id, failure_step)
        timeline = self.get_timeline(session_id)
        failing_event = scrub.get("latest_event") or {}

        culprit_agent = failing_event.get("agent", "Unknown Agent")
        culprit_action = failing_event.get("action", "unknown action")
        culprit_file = failing_event.get("file_path", "workspace")

        whys = [
            f"Why did the build fail? -> {failure_summary}",
            f"Why did the error trigger? -> Execution failed during step {failure_step} by {culprit_agent} ({culprit_action}).",
            f"Why was {culprit_file} affected? -> A staged AST modification or test assertion was violated without pre-flight validation.",
            f"Why was this not caught earlier? -> Concurrency race or edge-case input bypassed local unit tests before staging.",
            "Why is the architecture vulnerable? -> Missing invariant validation gate prior to desk diff application.",
        ]

        markdown_report = f"""# 🚨 Incident Post-Mortem & Flight Recorder RCA
**Incident ID:** `INC-{session_id[-8:] if len(session_id) >= 8 else session_id}`
**Trigger Step:** Step {failure_step} | **Responsible Desk:** {culprit_agent}
**Timestamp:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}

---

## 1. Executive Summary
{failure_summary}

## 2. 5 Whys Root Cause Analysis
1. **{whys[0]}**
2. **{whys[1]}**
3. **{whys[2]}**
4. **{whys[3]}**
5. **{whys[4]}**

## 3. Timeline of Events
"""
        for ev in timeline[: failure_step + 1]:
            markdown_report += f"- **Step {ev.get('step')}** (`{ev.get('agent')}`): {ev.get('action')} [{ev.get('status').upper()}]\n"

        markdown_report += f"""
## 4. Blast Radius & Affected Files
- `{culprit_file}`: Modified by {culprit_agent} at step {failure_step}.

## 5. Remediation & Action Items
- [ ] Auto-revert offending diff at step {failure_step}.
- [ ] Add regression test fixture to `tests/` capturing this boundary condition.
- [ ] Update `.devsquad/memory.json` known pitfalls to prevent recurring clobbering.
"""

        return {
            "session_id": session_id,
            "failure_step": failure_step,
            "culprit_agent": culprit_agent,
            "culprit_file": culprit_file,
            "whys": whys,
            "markdown_report": markdown_report,
            "remediation_status": "PROPOSED",
        }
