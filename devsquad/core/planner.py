# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Plan, approve, build: Apex proposes a plan you can edit, and approving it puts the tasks on the board."""

import json
import pathlib
import re
import time
import uuid

from .knowledge import KnowledgeBase
from typing import Any, Dict, List, Optional

from .taskboard import OWNERS, TaskBoard

OWNER_WORK = {
    "apex": "Write the spec and data model",
    "alpha_be": "Build the backend and API",
    "beta_fe": "Build the screens",
    "gamma_qa": "Write and run the tests",
    "delta_devops": "Set up CI and deployment",
    "zeta_docs": "Write the docs",
}


def _first_json_object(text: str) -> Optional[Dict[str, Any]]:
    """The first JSON object in a model's reply, which may wrap it in prose or a code fence."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(text[start:i + 1])
                        return value if isinstance(value, dict) else None
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _clean_list(items: Any, limit: int = 8, length: int = 220) -> List[str]:
    if not isinstance(items, list):
        return []
    return [re.sub(r"\s+", " ", str(x)).strip()[:length] for x in items if str(x).strip()][:limit]


class Planner:
    def __init__(self, root: Optional[pathlib.Path] = None):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.folder = self.root / ".devsquad" / "plans"

    def _template_plan(self, goal: str, note: str) -> Dict[str, Any]:
        return {
            "summary": f"Build: {goal}",
            "tasks": [{"title": f"{work}: {goal}"[:140], "owner": owner, "detail": ""} for owner, work in OWNER_WORK.items()],
            "risks": [],
            "questions": [],
            "source": "template",
            "note": note,
        }

    def propose(self, goal: str, provider: Any = None, reference: str = "") -> Dict[str, Any]:
        goal = re.sub(r"\s+", " ", goal or "").strip()[:400]
        if not goal:
            raise ValueError("Describe what you want built.")
        if provider is None or "template" in getattr(provider, "provider_name", "template"):
            plan = self._template_plan(goal, "Template mode: this is a standard task list, not an AI plan. Connect Ollama for a real plan with risks and questions.")
        else:
            prompt = (
                "You are Apex, the tech lead. Plan this work for a team of six: apex (spec), alpha_be (backend), "
                "beta_fe (frontend), gamma_qa (tests), delta_devops (CI and deploy), zeta_docs (docs).\n"
                f"GOAL: {goal}\n\n{reference}\n\n"
                'Reply with only JSON: {"summary": "...", "tasks": [{"title": "...", "owner": "alpha_be", "detail": "..."}], '
                '"risks": ["..."], "questions": ["questions the user must answer before building"]}. '
                "Keep tasks small and concrete. Use only the owners listed."
            )
            try:
                reply = provider.complete(prompt, system="You plan software work. You reply with JSON only.", max_tokens=1800)
                data = _first_json_object(reply.text or "")
            except Exception as e:   # a model that's down shouldn't lose the person's goal
                data, reply = None, None
                failure = str(e)
            else:
                failure = "the reply wasn't valid JSON"
            tasks = []
            for t in (data or {}).get("tasks") or []:
                if isinstance(t, dict) and str(t.get("title", "")).strip():
                    owner = t.get("owner") if t.get("owner") in OWNERS and t.get("owner") else "alpha_be"
                    tasks.append({"title": re.sub(r"\s+", " ", str(t["title"])).strip()[:140], "owner": owner,
                                  "detail": re.sub(r"\s+", " ", str(t.get("detail", ""))).strip()[:600]})
            if data and tasks:
                plan = {"summary": str(data.get("summary") or goal)[:600], "tasks": tasks[:15],
                        "risks": _clean_list(data.get("risks")), "questions": _clean_list(data.get("questions")),
                        "source": getattr(provider, "model", "model"), "note": ""}
            else:
                plan = self._template_plan(goal, f"The model's plan couldn't be used ({failure}), so this is the standard task list.")
        plan.update({"id": f"plan-{uuid.uuid4().hex[:8]}", "goal": goal, "status": "proposed", "created": time.time()})
        # Each owner decides from their field guides, with the guide named, even with no AI connected
        kb, seen, decisions = KnowledgeBase(self.root), set(), []
        for owner in ["apex"] + [t.get("owner") or "" for t in plan["tasks"]]:
            if owner and owner not in seen:
                seen.add(owner)
                decisions += [d for d in kb.decide(owner, goal, k=2) if d["decision"] not in {x["decision"] for x in decisions}]
        plan["decisions"] = decisions[:10]
        self._save(plan)
        return plan

    def _path(self, plan_id: str) -> pathlib.Path:
        if not re.fullmatch(r"plan-[a-f0-9]{8}", plan_id or ""):
            raise ValueError("That plan doesn't exist.")
        return self.folder / f"{plan_id}.json"

    def _save(self, plan: Dict[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        self._path(plan["id"]).write_text(json.dumps(plan, indent=2), encoding="utf-8")

    def get(self, plan_id: str) -> Dict[str, Any]:
        path = self._path(plan_id)
        if not path.is_file():
            raise ValueError("That plan doesn't exist.")
        return json.loads(path.read_text(encoding="utf-8"))

    def approve(self, plan_id: str, board: TaskBoard, tasks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Puts the plan's tasks on the board. `tasks` is the person's edited list, if they changed it."""
        plan = self.get(plan_id)
        if plan.get("status") == "approved":
            raise ValueError("This plan was already approved.")
        chosen = tasks if tasks is not None else plan["tasks"]
        cards = []
        for t in chosen:
            title = re.sub(r"\s+", " ", str((t or {}).get("title", ""))).strip()
            if not title:
                continue
            owner = t.get("owner") if t.get("owner") in OWNERS else ""
            body = f"{t.get('detail', '')}\n\nFrom the plan: {plan['goal']}".strip()
            cards.append(board.create(title, body=body, owner=owner, plan_id=plan_id))
        if not cards:
            raise ValueError("The plan has no tasks to add.")
        plan.update(status="approved", tasks=chosen, approved=time.time(), card_ids=[c["id"] for c in cards])
        self._save(plan)
        return {"plan": plan, "cards": cards}
