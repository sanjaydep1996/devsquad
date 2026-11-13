# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Status answers for questions like "What is Delta working on?".

Everything reported here comes from what DevSquad has recorded: the stage a running
task is on, past tasks in the Staging Deck and their test results. Nothing is invented,
so an idle agent is reported as idle.
"""

import re
import statistics
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from .staging import StagedTask, StagingDeck

# The relay's stages, in order, and which teammate owns each
STAGE_ORDER = ["apex", "alpha_be", "gamma_qa", "delta_devops"]
LOG_NAME_TO_ID = {"Apex": "apex", "Alpha": "alpha_be", "Gamma": "gamma_qa", "Delta": "delta_devops"}
TEAM = {
    "apex": ("Apex", "plans the work and writes the spec", ["apex", "architect", "tech lead", "lead"]),
    "alpha_be": ("Alpha BE", "writes the code", ["alpha be", "alpha", "backend"]),
    "beta_fe": ("Beta FE", "frontend", ["beta fe", "beta", "frontend", "front end", "ui dev"]),
    "gamma_qa": ("Gamma QA", "writes and runs the tests", ["gamma qa", "gamma", "qa", "tester"]),
    "zeta_docs": ("Zeta", "docs", ["zeta", "docs", "technical writer"]),
    "delta_devops": ("Delta", "prepares the branch and commit message", ["delta", "devops", "dev ops"]),
}
WAITING_REVIEW = ("staged", "tested_green", "tested_red")

# A message is a status question only if it matches one of these. Plain tasks such as
# "Fix the blocked user bug" must not match, so each pattern needs question wording.
QUESTION_PATTERNS = [
    r"^\s*(status|progress|update|eta|blockers?)\s*\??\s*$",
    r"\bwhat(?:'s| is| are| r)\b.*\b(working on|doing|up to|status|progress|blocking|blocked|eta|pending)\b",
    r"\bwho(?:'s| is)\b.*\b(working|busy|free|idle|blocked)\b",
    r"\b(is|are)\b .*\b(blocked|stuck|busy|free|idle|done|finished|working)\b.*\?",
    r"\bany\b.*\b(blockers?|updates?|progress|decisions?|issues)\b",
    r"\bhow\b.*\b(is|are|'s)\b.*\b(going|doing|progressing)\b",
    r"\b(how long|when will|how much longer|what's the eta|eta for|eta\?)",
    r"\bstatus (update|report|of|for|on)\b|\b(give|show) me .*\b(status|update|progress)\b",
    r"\bwhat\b.*\b(decisions?|approvals?)\b.*\b(need|waiting|pending|from me)\b|\bdecisions? needed\b",
    r"\b(what should|what can) (i|we) (do|improve)\b.*\?",
]
TEAM_WORDS = re.compile(r"\b(team|everyone|everybody|all of you|squad|who)\b", re.I)


def _seconds(text: str) -> Optional[int]:
    m = re.match(r"\[(\d\d):(\d\d):(\d\d)\]", text)
    return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) if m else None


def _duration(task: StagedTask) -> Optional[int]:
    """How long a finished task took, from the first and last lines of its log."""
    if len(task.relay_logs) < 2:
        return None
    a, b = _seconds(task.relay_logs[0]), _seconds(task.relay_logs[-1])
    if a is None or b is None:
        return None
    return (b - a) % 86400   # a run can cross midnight


def _span(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 90:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = round(seconds / 60)
    return f"{minutes} minutes"


class StatusBoard:
    """What is running right now, fed by the relay's events. Kept in memory only."""

    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self.current: Optional[Dict[str, Any]] = None

    def record(self, agent: str, event: str, data: Optional[Dict[str, Any]] = None) -> None:
        data = data or {}
        now = self._clock()
        with self._lock:
            task_id = data.get("task_id")
            if self.current is None or (task_id and task_id != self.current["task_id"]):
                self.current = {"task_id": task_id, "goal": data.get("goal") or "a task", "started": now}
            self.current.update(agent=LOG_NAME_TO_ID.get(agent), event=event, message=data.get("message", ""), stage_started=now)

    def finish(self) -> None:
        with self._lock:
            self.current = None

    def snapshot(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return dict(self.current, now=self._clock()) if self.current else None


class StatusReporter:
    """Builds the answer to a status question."""

    def __init__(self, staging: StagingDeck, board: StatusBoard, provider_name: str = "", model: str = ""):
        self.staging = staging
        self.board = board
        self.provider_name = provider_name or ""
        self.model = model or ""

    # ----- who and whether -----
    @staticmethod
    def is_status_question(question: str) -> bool:
        q = (question or "").strip().lower()
        return bool(q) and len(q) <= 200 and any(re.search(p, q) for p in QUESTION_PATTERNS)

    @staticmethod
    def _who(question: str, names: Dict[str, str], selected: Optional[str]) -> List[str]:
        q = " " + re.sub(r"[^a-z0-9 ]+", " ", question.lower()) + " "
        found = []
        for agent_id, (_, _, aliases) in TEAM.items():
            words = list(aliases)
            custom = (names or {}).get(agent_id)
            if custom:
                words.insert(0, re.sub(r"[^a-z0-9 ]+", " ", custom.lower()).strip())
            # Longest alias first, so "beta fe" wins over a shorter word inside it
            if any(w and f" {w} " in q for w in sorted(words, key=len, reverse=True)):
                found.append(agent_id)
        if found:
            return found
        if TEAM_WORDS.search(question) or not selected or selected not in TEAM:
            return list(TEAM)
        return [selected]

    # ----- the parts of an answer -----
    def _agent(self, agent_id: str, name: str, run: Optional[Dict[str, Any]], tasks: List[StagedTask]) -> Dict[str, Any]:
        state, working_on = "idle", f"{name} isn't working on anything right now."
        if run:
            goal = run["goal"]
            if agent_id not in STAGE_ORDER:
                working_on = f"{name} has no stage in the current relay, so there is no work for {name} on \"{goal}\"."
            elif run["agent"] == agent_id:
                state = "working"
                working_on = f"{name} is on \"{goal}\": {run['message'].rstrip('.')}. This stage started {_span(run['now'] - run['stage_started'])} ago."
            elif run["agent"] in STAGE_ORDER and STAGE_ORDER.index(agent_id) > STAGE_ORDER.index(run["agent"]):
                state = "waiting"
                working_on = f"{name} is waiting for their turn on \"{goal}\". {name} {TEAM[agent_id][1]}, which comes after the current stage."
            elif run["agent"] in STAGE_ORDER:
                state = "done"
                working_on = f"{name} has finished their part of \"{goal}\". The task has moved on to a later stage."
            else:
                state = "waiting"
                working_on = f"\"{goal}\" has just started. {name} {TEAM[agent_id][1]} when it reaches their stage."
        last = tasks[0] if tasks else None
        outcome = {"tested_green": "tests passed", "tested_red": "tests failed", "applied": "applied to the repo",
                   "rejected": "rejected", "staged": "staged"}
        last_done = f"Last finished task: \"{last.goal}\" ({outcome.get(last.status, last.status)})." if last and agent_id in STAGE_ORDER else ""
        return {"id": agent_id, "name": name, "state": state, "working_on": working_on, "last_done": last_done}

    def _eta(self, run: Optional[Dict[str, Any]], tasks: List[StagedTask]) -> str:
        if not run:
            return "Nothing is running, so there is nothing to estimate."
        durations = [d for d in (_duration(t) for t in tasks[:10]) if d]
        if not durations:
            return "No estimate yet: there are no finished tasks to compare with."
        typical, elapsed = statistics.median(durations), run["now"] - run["started"]
        basis = f"based on the last {len(durations)} finished task{'s' if len(durations) != 1 else ''}, which typically took {_span(typical)}"
        if elapsed > typical:
            return f"This is taking longer than usual: {_span(elapsed)} so far, against a typical {_span(typical)}. That's an estimate {basis}."
        return f"About {_span(typical - elapsed)} left. That's an estimate {basis}."

    def _blockers(self, tasks: List[StagedTask]) -> List[str]:
        blockers = []
        if "template" in self.provider_name.lower():
            blockers.append("No local AI is connected. Tasks run in template mode, so the output is example files, not real work.")
        # Several tasks often fail for one reason, so each reason is reported once
        by_reason: Dict[str, List[str]] = {}
        for t in tasks:
            if t.status == "tested_red":
                reason = (t.test_result.failure_summary if t.test_result else "") or "the test run failed"
                by_reason.setdefault(reason.strip().splitlines()[0][:160], []).append(t.goal)
        for reason, goals in by_reason.items():
            where = f"\"{goals[0]}\"" if len(goals) == 1 else f"{len(goals)} tasks, most recently \"{goals[0]}\""
            blockers.append(f"Tests failed on {where}: {reason}")
        return blockers

    @staticmethod
    def _decisions(tasks: List[StagedTask]) -> List[str]:
        waiting = [t for t in tasks if t.status in WAITING_REVIEW]
        decisions = [
            f"\"{t.goal}\" is waiting in the Review Desk ({'tests passed' if t.status == 'tested_green' else 'tests failed' if t.status == 'tested_red' else 'not tested'}). Apply it or reject it."
            for t in waiting[:3]
        ]
        if len(waiting) > 3:
            decisions.append(f"{len(waiting) - 3} more tasks are waiting in the Review Desk.")
        return decisions

    def _suggestions(self, run: Optional[Dict[str, Any]], tasks: List[StagedTask], decisions: List[str]) -> List[str]:
        tips = []
        if "template" in self.provider_name.lower():
            tips.append("Install Ollama (ollama.com) and run `ollama pull qwen2.5-coder` to get real AI output for free.")
        if any(t.status == "tested_red" and t.test_result and "No such file or directory: 'pytest'" in (t.test_result.failure_summary or "") for t in tasks):
            tips.append("The test runner isn't installed. Run `pip install pytest` so tests can actually run.")
        if any(t.status == "tested_red" for t in tasks):
            tips.append("Open the failing task in the Review Desk and read the test output before applying anything.")
        if len(decisions) > 3:
            tips.append(f"Several tasks are waiting for review. Clear the old ones so new work is easier to check.")
        if not run and not decisions:
            tips.append("The team is free. Give someone a task from the chat box.")
        return tips

    # ----- the answer -----
    def answer(self, question: str, selected: Optional[str] = None, names: Optional[Dict[str, str]] = None) -> Optional[Dict[str, Any]]:
        """The status report for a question, or None when the message isn't a status question."""
        if not self.is_status_question(question):
            return None
        names = names or {}
        run = self.board.snapshot()
        tasks = sorted(self.staging.list_tasks(), key=lambda t: t.created_at, reverse=True)
        if run:
            tasks = [t for t in tasks if t.task_id != run["task_id"]]
        display = lambda agent_id: (names.get(agent_id) or "").strip()[:24] or TEAM[agent_id][0]
        agents = [self._agent(a, display(a), run, tasks) for a in self._who(question, names, selected)]
        decisions = self._decisions(tasks)
        report = {
            "answered": True,
            "agents": agents,
            "eta": self._eta(run, tasks),
            "blockers": self._blockers(tasks),
            "decisions": decisions,
            "suggestions": self._suggestions(run, tasks, decisions),
            "model": self.model,
        }
        lines = [f"{a['working_on']} {a['last_done']}".strip() for a in agents]
        lines.append(f"ETA: {report['eta']}")
        for title, key, empty in (("Blockers", "blockers", "None."), ("Decisions needed", "decisions", "None."), ("Suggestions", "suggestions", "None.")):
            lines.append(f"{title}: " + (" ".join(f"({i}) {x}" for i, x in enumerate(report[key], 1)) if report[key] else empty))
        report["text"] = "\n".join(lines)
        return report
