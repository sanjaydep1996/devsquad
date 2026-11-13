# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""The v0.5 routes under /api/v5/, shared by the standard server and the FastAPI server.

Both servers already refuse requests from other sites before they get here, so this module only
routes and validates. It returns (HTTP status, JSON body).
"""

import pathlib
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..core.bootstrapper import Bootstrapper, BootstrapError
from ..core.devops_desk import DevOpsDesk
from ..core.doc_reader import describe_image
from ..core.files import ProjectFiles
from ..core.flaky_detector import FlakyTestDetector
from ..core.planner import Planner
from ..core.setup_check import SetupCheck
from ..core.taskboard import BoardError, TaskBoard

PREFIX = "/api/v5/"
Result = Tuple[int, Dict[str, Any]]


class V5Api:
    def __init__(self, root: pathlib.Path, provider: Callable[[], Any], run_task: Callable[[str, str], Any],
                 setup: Optional[SetupCheck] = None):
        """`provider` returns the current AI provider. `run_task(goal, reference)` runs the agents and returns the staged task."""
        self.root = root
        self.provider = provider
        self.run_task = run_task
        self.setup = setup or SetupCheck(root)
        self.board = TaskBoard(root)
        self.planner = Planner(root)

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

        if route == "flaky" and method == "POST":
            result = FlakyTestDetector(self.root).run_real(str(p.get("command", "")), runs=int(p.get("runs") or 10))
            return (400 if result["status"] == "error" else 200), result

        return 404, {"ok": False, "error": "Not found"}

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
