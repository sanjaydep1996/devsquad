# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Session replay: a past relay run, step by step, from the flight recorder (or the run's log for older runs)."""

import datetime
import pathlib
import re
from typing import Any, Dict, List, Optional

from .flight_recorder import FlightRecorder

# The names agents log under, mapped to the studio's teammate ids
AGENT_IDS = {"apex": "apex", "alpha": "alpha_be", "beta": "beta_fe", "gamma": "gamma_qa", "delta": "delta_devops", "zeta": "zeta_docs"}
LOG_LINE = re.compile(r"\[(\d\d):(\d\d):(\d\d)\] \[([^\]]+)\] ([A-Za-z0-9_]+): (.*)")


def agent_id(name: str) -> str:
    first = re.split(r"[\s_]", (name or "").strip().lower())[0] if name else ""
    return AGENT_IDS.get(first, name or "System")


def _step(index: int, agent: str, action: str, message: str, when: float, seconds: float, status: str,
          provider: str, model: str) -> Dict[str, Any]:
    return {
        "step_index": index,
        "timestamp": datetime.datetime.fromtimestamp(when, datetime.timezone.utc).isoformat(),
        "agent_name": agent_id(agent),
        "tool_name": f"{action}: {message}"[:160] if message else action,
        "provider": provider or "local",
        "model": model or "template",
        # Local models cost nothing, and the relay doesn't count tokens, so these are honest zeros
        "tokens_in": 0, "tokens_out": 0, "cache_read": 0, "cache_write": 0, "cost_usd": 0.0,
        "duration_ms": int(max(0.0, seconds) * 1000),
        "status": "failed" if status == "error" else "completed",
    }


def build_replay(root: pathlib.Path, session_id: str, staging: Any = None, provider: str = "", model: str = "") -> Optional[Dict[str, Any]]:
    """The replay for one relay run, or None when there's no such run."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", session_id or ""):
        return None
    steps: List[Dict[str, Any]] = []
    goal = ""
    events = FlightRecorder(root).get_timeline(session_id)
    if events:
        for i, e in enumerate(events):
            after = events[i + 1]["timestamp"] if i + 1 < len(events) else e["timestamp"]
            payload = e.get("payload") or {}
            goal = goal or str(payload.get("goal", ""))
            steps.append(_step(i + 1, e.get("agent", ""), e.get("action", "action"), str(payload.get("message", "")),
                               float(e.get("timestamp", 0)), float(after) - float(e.get("timestamp", 0)),
                               e.get("status", "ok"), provider, model))
    else:
        task = staging.load_task(session_id) if staging is not None else None
        if not task:
            return None
        goal = task.goal
        base = float(getattr(task, "created_at", 0) or 0)
        parsed = []
        for line in task.relay_logs:
            m = LOG_LINE.match(line)
            if m:
                h, mi, s, agent, action, message = m.groups()
                parsed.append((int(h) * 3600 + int(mi) * 60 + int(s), agent, action, message))
        for i, (secs, agent, action, message) in enumerate(parsed):
            nxt = parsed[i + 1][0] if i + 1 < len(parsed) else secs
            status = "error" if action.endswith("_RED") or "FAIL" in action else "ok"
            steps.append(_step(i + 1, agent, action, message, base + (secs - parsed[0][0]), (nxt - secs) % 86400, status, provider, model))
    if not steps:
        return None
    return {"session_id": session_id, "source": "DevSquad relay run", "goal": goal, "step_count": len(steps),
            "steps": steps, "total_tokens": 0, "total_cost_usd": 0.0}
