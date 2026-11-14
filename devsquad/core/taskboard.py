# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Task board: one Markdown file per card in .devsquad/tasks/, so the board lives in git with the code."""

import json
import pathlib
import re
import subprocess
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

COLUMNS = ("backlog", "in_progress", "review", "merged")
COLUMN_TITLES = {"backlog": "Backlog", "in_progress": "In progress", "review": "Review Desk", "merged": "Merged"}
OWNERS = ("apex", "alpha_be", "beta_fe", "gamma_qa", "delta_devops", "zeta_docs", "")
FIELDS = ("id", "title", "status", "owner", "issue", "issue_url", "task_id", "plan_id", "created", "updated")


class BoardError(ValueError):
    """A request the board can't carry out. The message is safe to show to the person."""


def _one_line(value: Any, limit: int = 200) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


class TaskBoard:
    def __init__(self, root: Optional[pathlib.Path] = None, clock: Callable[[], float] = time.time):
        self.folder = (root or pathlib.Path.cwd()).resolve() / ".devsquad" / "tasks"
        self._clock = clock

    # ----- files -----
    def _path(self, card_id: str) -> pathlib.Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,80}", card_id or ""):
            raise BoardError("That card doesn't exist.")
        return self.folder / f"{card_id}.md"

    @staticmethod
    def _parse(text: str) -> Dict[str, Any]:
        m = re.match(r"---\n(.*?)\n---\n?(.*)\Z", text, re.S)
        if not m:
            return {}
        card: Dict[str, Any] = {"body": m.group(2).strip()}
        for line in m.group(1).splitlines():
            key, _, value = line.partition(":")
            if key.strip() in FIELDS:
                card[key.strip()] = value.strip()
        for number in ("issue", "created", "updated"):
            if card.get(number):
                try:
                    card[number] = float(card[number]) if number != "issue" else int(card[number])
                except ValueError:
                    card[number] = None
        return card

    def _write(self, card: Dict[str, Any]) -> Dict[str, Any]:
        self.folder.mkdir(parents=True, exist_ok=True)
        head = "\n".join(f"{k}: {_one_line(card.get(k))}" for k in FIELDS if card.get(k) not in (None, ""))
        self._path(card["id"]).write_text(f"---\n{head}\n---\n{(card.get('body') or '').strip()}\n", encoding="utf-8")
        return self.get(card["id"])

    # ----- cards -----
    def create(self, title: str, body: str = "", status: str = "backlog", owner: str = "", **extra: Any) -> Dict[str, Any]:
        title = _one_line(title, 140)
        if not title:
            raise BoardError("A card needs a title.")
        if status not in COLUMNS:
            raise BoardError(f"Unknown column: {status}.")
        if owner not in OWNERS:
            raise BoardError(f"Unknown teammate: {owner}.")
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].strip("-") or "card"
        now = self._clock()
        card = {"id": f"{slug}-{uuid.uuid4().hex[:6]}", "title": title, "status": status, "owner": owner,
                "created": now, "updated": now, "body": body or ""}
        card.update({k: v for k, v in extra.items() if k in FIELDS and v not in (None, "")})
        return self._write(card)

    def get(self, card_id: str) -> Dict[str, Any]:
        path = self._path(card_id)
        if not path.is_file():
            raise BoardError("That card doesn't exist.")
        return self._parse(path.read_text(encoding="utf-8"))

    def list(self) -> List[Dict[str, Any]]:
        if not self.folder.is_dir():
            return []
        cards = [self._parse(p.read_text(encoding="utf-8")) for p in self.folder.glob("*.md")]
        cards = [c for c in cards if c.get("id") and c.get("status") in COLUMNS]
        return sorted(cards, key=lambda c: c.get("updated") or 0, reverse=True)

    def columns(self) -> Dict[str, Any]:
        cards = self.list()
        return {"columns": [{"id": c, "title": COLUMN_TITLES[c], "cards": [x for x in cards if x["status"] == c]} for c in COLUMNS]}

    def update(self, card_id: str, **fields: Any) -> Dict[str, Any]:
        card = self.get(card_id)
        if "status" in fields and fields["status"] not in COLUMNS:
            raise BoardError(f"Unknown column: {fields['status']}.")
        if "owner" in fields and fields["owner"] not in OWNERS:
            raise BoardError(f"Unknown teammate: {fields['owner']}.")
        for key, value in fields.items():
            if key in FIELDS and key not in ("id", "created"):
                card[key] = value
            elif key == "body":
                card["body"] = value
        card["updated"] = self._clock()
        return self._write(card)

    def move(self, card_id: str, status: str) -> Dict[str, Any]:
        return self.update(card_id, status=status)

    def delete(self, card_id: str) -> bool:
        path = self._path(card_id)
        if not path.is_file():
            return False
        path.unlink()
        return True

    # ----- GitHub Issues -----
    def sync_github(self, run: Optional[Callable[[List[str]], subprocess.CompletedProcess]] = None) -> Dict[str, Any]:
        """Adds open GitHub issues that aren't on the board yet. It only reads issues: it never closes or edits them."""
        run = run or (lambda argv: subprocess.run(argv, cwd=str(self.folder.parent.parent), capture_output=True, text=True, timeout=60))
        try:
            result = run(["gh", "issue", "list", "--state", "open", "--limit", "100", "--json", "number,title,body,url"])
        except FileNotFoundError:
            raise BoardError("The GitHub CLI (gh) isn't installed. Install it and run `gh auth login` to sync issues.")
        except subprocess.TimeoutExpired:
            raise BoardError("GitHub didn't answer in time. Try again.")
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip().splitlines()
            raise BoardError("Couldn't read GitHub issues: " + (detail[0][:200] if detail else "gh failed") + ". Run `gh auth login` if you haven't.")
        try:
            issues = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            raise BoardError("GitHub returned something unexpected. Try again.")
        known = {c.get("issue") for c in self.list() if c.get("issue")}
        added = []
        for issue in issues:
            number = issue.get("number")
            if not isinstance(number, int) or number in known:
                continue
            added.append(self.create(f"#{number} {issue.get('title', '')}", body=issue.get("body") or "", issue=number, issue_url=issue.get("url", "")))
        return {"imported": len(added), "already_on_board": len(issues) - len(added), "cards": added}
