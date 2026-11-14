# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""The v0.5 routes under /api/v5/, shared by the standard server and the FastAPI server.

Both servers already refuse requests from other sites before they get here, so this module only
routes and validates. It returns (HTTP status, JSON body), or (HTTP status, Download) for exports.
"""

import pathlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.bootstrapper import Bootstrapper, BootstrapError
from ..core.devops_desk import DevOpsDesk
from ..core.doc_reader import describe_image
from ..core.export import Download, as_download, plan_markdown, postmortem_markdown, replay_markdown
from ..core.files import ProjectFiles
from ..core.flaky_detector import FlakyTestDetector
from ..core.planner import Planner
from ..core.replay import build_replay
from ..core.setup_check import SetupCheck
from ..core.staging import StagingDeck
from ..core.status import TEAM, StatusBoard, StatusReporter
from ..core.taskboard import BoardError, TaskBoard

PREFIX = "/api/v5/"
Result = Tuple[int, Any]
OUTCOMES = {"tested_green": "tests passed", "tested_red": "tests failed", "staged": "not tested yet",
            "applied": "applied to the repo", "rejected": "rejected"}


class V5Api:
    def __init__(self, root: pathlib.Path, provider: Callable[[], Any], run_task: Callable[[str, str], Any],
                 setup: Optional[SetupCheck] = None, staging: Optional[StagingDeck] = None,
                 status: Optional[Callable[[], StatusReporter]] = None):
        """`provider` returns the current AI provider. `run_task(goal, reference)` runs the agents and returns the staged task.
        `status` builds the status reporter the chat uses, so a desk card says the same as a status question."""
        self.root = root
        self.provider = provider
        self.run_task = run_task
        self.setup = setup or SetupCheck(root)
        self.board = TaskBoard(root)
        self.planner = Planner(root)
        self.staging = staging or StagingDeck(root)
        self.status = status or (lambda: StatusReporter(self.staging, StatusBoard()))

    # ----- helpers -----
    def image_reader(self) -> Optional[Callable[[bytes], Optional[str]]]:
        """Describes images with a local vision model, if one is installed. Asked for only when an image is attached."""
        cache: Dict[str, Optional[str]] = {}

        def read(data: bytes) -> Optional[str]:
            if "model" not in cache:
                from ..core.setup_check import vision_model
                cache["model"] = vision_model(self.setup.models() or [])
            return describe_image(data, cache["model"], self.setup.ollama_url) if cache["model"] else None
        return read

    def reference(self, names: Any) -> str:
        names = [str(n) for n in names] if isinstance(names, list) else []
        return ProjectFiles(self.root).context_for(names, describe_image=self.image_reader()) if names else ""

    # ----- routing -----
    def handle(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Result:
        payload = payload if isinstance(payload, dict) else {}
        route = path[len(PREFIX):].strip("/")
        try:
            return self._route(method, route, payload)
        except (BoardError, BootstrapError, ValueError) as e:
            return 400, {"ok": False, "error": str(e)}

    def _route(self, method: str, route: str, p: Dict[str, Any]) -> Result:
        card = re.fullmatch(r"board/([a-z0-9][a-z0-9-]{0,80})(?:/(move|assign))?", route)
        plan = re.fullmatch(r"plan/(plan-[a-f0-9]{8})(?:/(approve))?", route)
        export = re.fullmatch(r"export/(plan|replay|postmortem)/([A-Za-z0-9_-]{1,80})\.(md|pdf)", route)
        desk = re.fullmatch(r"desk/([a-z_]{1,20})", route)

        if route == "setup" and method == "GET":
            return 200, self.setup.status()
        if route == "setup/pull" and method == "POST":
            result = self.setup.pull(str(p.get("model", "")))
            return (200 if result["ok"] else 400), result

        if route == "board" and method == "GET":
            return 200, self.board.columns()
        if route == "board" and method == "POST":
            return 201, self.board.create(str(p.get("title", "")), body=str(p.get("body", "")),
                                          status=str(p.get("status") or "backlog"), owner=str(p.get("owner") or ""))
        if route == "board/sync" and method == "POST":
            return 200, self.board.sync_github()
        if card and method == "DELETE" and not card.group(2):
            return (200, {"ok": True}) if self.board.delete(card.group(1)) else (404, {"ok": False, "error": "That card doesn't exist."})
        if card and method == "POST" and card.group(2) == "move":
            return 200, self.board.move(card.group(1), str(p.get("status", "")))
        if card and method == "POST" and not card.group(2):
            fields = {k: str(p[k]) for k in ("title", "body", "owner") if k in p}
            return 200, self.board.update(card.group(1), **fields)
        if card and method == "POST" and card.group(2) == "assign":
            return self._assign(card.group(1), p)

        if route == "plan" and method == "POST":
            return 201, self.planner.propose(str(p.get("goal", "")), self.provider(), self.reference(p.get("files")))
        if plan and method == "GET" and not plan.group(2):
            return 200, self.planner.get(plan.group(1))
        if plan and method == "POST" and plan.group(2) == "approve":
            tasks = p.get("tasks") if isinstance(p.get("tasks"), list) else None
            return 200, self.planner.approve(plan.group(1), self.board, tasks)

        if route == "devops/generate" and method == "POST":
            return 200, DevOpsDesk(self.root).generate()
        if route == "devops/apply" and method == "POST":
            paths = p.get("paths") if isinstance(p.get("paths"), list) else []
            return 200, DevOpsDesk(self.root).apply([str(x) for x in paths], overwrite=bool(p.get("overwrite")))

        if route == "greenfield" and method == "POST":
            return 201, Bootstrapper(self.root).generate(str(p.get("prompt", "")), self.provider())
        if route == "greenfield/apply" and method == "POST":
            return 200, Bootstrapper(self.root).apply(str(p.get("slug", "")), str(p.get("target", "")))

        if export and method == "GET":
            return self._export(*export.groups())
        if desk and method == "POST":
            return self._desk(desk.group(1), p)

        if route == "flaky" and method == "POST":
            result = FlakyTestDetector(self.root).run_real(str(p.get("command", "")), runs=int(p.get("runs") or 10))
            return (400 if result["status"] == "error" else 200), result

        return 404, {"ok": False, "error": "Not found"}

    def _export(self, kind: str, ident: str, fmt: str) -> Result:
        """A plan, a run's replay or a run's post-mortem, as a Markdown or PDF download."""
        if kind == "plan":
            plan = self.planner.get(ident)
            return 200, as_download(plan_markdown(plan), f"devsquad-{ident}", fmt, f"Plan: {plan.get('goal', '')}"[:90])
        provider = self.provider()
        replay = build_replay(self.root, ident, self.staging, getattr(provider, "provider_name", ""), getattr(provider, "model", ""))
        if not replay:
            return 404, {"ok": False, "error": "No recorded run with that id."}
        if kind == "replay":
            return 200, as_download(replay_markdown(replay), f"devsquad-replay-{ident}", fmt, f"Replay: {replay.get('goal', '')}"[:90])
        md = postmortem_markdown(replay, self.staging.load_task(ident))
        return 200, as_download(md, f"devsquad-postmortem-{ident}", fmt, f"Post-mortem: {replay.get('goal', '')}"[:90])

    def _desk(self, agent_id: str, p: Dict[str, Any]) -> Result:
        """What one teammate's desk card shows: their cards on the board and the recorded status."""
        if agent_id not in TEAM:
            return 404, {"ok": False, "error": "Nobody sits at that desk."}
        names = p.get("names") if isinstance(p.get("names"), dict) else {}
        names = {k: str(v) for k, v in names.items() if isinstance(k, str)}
        report = self.status().answer("status", selected=agent_id, names=names) or {}
        person = next((a for a in report.get("agents", []) if a["id"] == agent_id), {})
        mine = [c for c in self.board.list() if c.get("owner") == agent_id]
        oldest_first = lambda cards: sorted(cards, key=lambda c: c.get("created") or 0)
        current = next(iter(oldest_first([c for c in mine if c["status"] == "in_progress"])), None)
        backlog = oldest_first([c for c in mine if c["status"] == "backlog"])
        tasks = sorted(self.staging.list_tasks(), key=lambda t: t.created_at, reverse=True)
        last = tasks[0] if tasks else None
        slim = lambda c: {k: c.get(k) for k in ("id", "title", "status", "issue", "issue_url", "task_id")} if c else None
        return 200, {
            "id": agent_id, "name": person.get("name") or TEAM[agent_id][0], "role": TEAM[agent_id][1],
            "state": person.get("state", "idle"), "working_on": person.get("working_on", ""), "last_done": person.get("last_done", ""),
            "eta": report.get("eta", ""), "blockers": report.get("blockers", []), "decisions": report.get("decisions", []),
            "cards": {"current": slim(current), "next": slim(backlog[0] if backlog else None), "backlog": len(backlog),
                      "review": sum(1 for c in mine if c["status"] == "review")},
            "last_run": {"task_id": last.task_id, "goal": last.goal, "outcome": OUTCOMES.get(last.status, last.status),
                         "when": last.created_at} if last else None,
        }

    def _assign(self, card_id: str, p: Dict[str, Any]) -> Result:
        """Hands a card to the squad: it moves to In progress, the agents run, and it lands on the Review Desk."""
        card = self.board.get(card_id)
        if card["status"] in ("review", "merged"):
            raise BoardError("This card is already past the build step.")
        self.board.move(card_id, "in_progress")
        goal = card["title"] + (f"\n\n{card['body']}" if card.get("body") else "")
        try:
            task = self.run_task(goal, self.reference(p.get("files")))
        except Exception as e:
            self.board.update(card_id, status="backlog", body=(card.get("body", "") + f"\n\nLast run failed: {e}").strip())
            return 500, {"ok": False, "error": f"The squad couldn't finish this card: {e}", "card": self.board.get(card_id)}
        updated = self.board.update(card_id, status="review", task_id=getattr(task, "task_id", ""))
        return 200, {"ok": True, "card": updated, "task_id": getattr(task, "task_id", ""), "status": getattr(task, "status", "")}
