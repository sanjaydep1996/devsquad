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

        message = lambda ev: (ev.get("payload") or {}).get("message", "")
        before = [ev for ev in timeline if ev.get("step", 0) < failure_step]
        last_change = next((ev for ev in reversed(before) if ev.get("file_path")), None)
        by_agent: Dict[str, int] = {}
        for ev in before:
            by_agent[ev.get("agent", "?")] = by_agent.get(ev.get("agent", "?"), 0) + 1

        # Every line comes from the recording or the failure text. Nothing here is guessed.
        whys = [
            f"What failed: {failure_summary}",
            f"Where it was caught: step {failure_step}, {culprit_agent} ({culprit_action})" + (f": {message(failing_event)}" if message(failing_event) else ""),
            (f"Last recorded change before it: {last_change.get('file_path')} by {last_change.get('agent')} at step {last_change.get('step')}"
             if last_change else "Last recorded change before it: none was recorded"),
            "What ran before it: " + (", ".join(f"{agent} ({n} step{'s' if n != 1 else ''})" for agent, n in by_agent.items()) or "nothing was recorded"),
            "Root cause: not known from the record. Read the diff and the full test output to confirm it.",
        ]

        markdown_report = f"""# Incident post-mortem
**Session:** `{session_id}`
**Failed at:** step {failure_step}, {culprit_agent}
**Written:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}

## What the record shows
""" + "".join(f"{i}. {w}\n" for i, w in enumerate(whys, 1)) + """
## Timeline
"""
        for ev in timeline[:failure_step]:
            markdown_report += f"- Step {ev.get('step')} · {ev.get('agent')} · {ev.get('action')} [{str(ev.get('status', '')).upper()}]" + (f": {message(ev)}" if message(ev) else "") + "\n"
        if last_change and last_change.get("diff"):
            markdown_report += f"\n## Last recorded change: {last_change.get('file_path')}\n```diff\n{last_change.get('diff')[:3000]}\n```\n"
        markdown_report += """
## Next steps
- [ ] Read the full test output for the failing step.
- [ ] Check the last recorded change above, then fix or revert it.
- [ ] Add a test that reproduces the failure, so it can't come back unnoticed.
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
