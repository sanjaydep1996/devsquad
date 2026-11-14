# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Lessons from your reviews: why you kept or rejected a change becomes a rule in the team's field guides.

Lessons are written to .devsquad/knowledge/learned-<field>.md in the field-guide format, so the
agents look them up like any other guide and name the review they came from.
"""

import datetime
import pathlib
import re
from typing import Any, Dict, List

from .knowledge import AGENT_FIELDS

FIELD_HINTS = [
    ("Security", ["secret", "password", "token", "auth", "permission", "injection", "xss", "csrf", "hash", "encrypt", "leak", "sanitize"]),
    ("Testing", ["test", "coverage", "flaky", "assert", "regression", "mock"]),
    ("Frontend", ["ui", "css", "button", "layout", "page", "accessib", "a11y", "mobile", "contrast", "form"]),
    ("DevOps", ["deploy", "docker", "ci", "pipeline", "release", "kubernetes", "env", "build"]),
    ("Docs", ["doc", "readme", "comment", "changelog", "typo", "wording"]),
    ("Architecture", ["design", "architecture", "module", "coupling", "abstraction", "pattern", "structure"]),
]
_STOP = {"the", "and", "for", "with", "this", "that", "from", "into", "when", "they", "them", "were", "have", "dont", "don", "should", "please", "make", "add", "use"}


def field_for(text: str) -> str:
    t = (text or "").lower()
    for name, hints in FIELD_HINTS:
        if any(h in t for h in hints):
            return name
    return "Backend"


def keywords(text: str, limit: int = 8) -> List[str]:
    seen: List[str] = []
    for w in re.findall(r"[a-z][a-z0-9]{3,}", (text or "").lower()):
        if w not in _STOP and w not in seen:
            seen.append(w)
    return seen[:limit]


def _clean(text: str, limit: int) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


class LessonBook:
    def __init__(self, root: pathlib.Path):
        self.folder = root / ".devsquad" / "knowledge"

    def record(self, goal: str, task_id: str, verdict: str, reason: str) -> Dict[str, Any]:
        """Turns one review into a rule. `verdict` is "keep" (do this again) or "avoid" (don't repeat it)."""
        reason, goal = _clean(reason, 400), _clean(goal, 200)
        if verdict not in ("keep", "avoid"):
            raise ValueError("Say whether the team should keep doing this or avoid it.")
        if len(reason) < 8:
            raise ValueError("Write a sentence about why, so the team can learn from it.")
        field = field_for(reason + " " + goal)
        owners = [a for a, fields in AGENT_FIELDS.items() if field in fields]
        path = self.folder / f"learned-{field.lower()}.md"
        self.folder.mkdir(parents=True, exist_ok=True)
        if not path.is_file():
            path.write_text(f"---\nfield: {field}\nowners: {', '.join(owners)}\n---\n", encoding="utf-8")
        title = ("Keep: " if verdict == "keep" else "Avoid: ") + (reason[:70].rstrip(" .,") + ("…" if len(reason) > 70 else ""))
        decide = ("Keep doing this, you approved it: " if verdict == "keep" else "Don't repeat this, you rejected it: ") + reason
        tags = keywords(reason, 6)
        when = keywords(goal + " " + reason, 8)
        day = datetime.date.today().isoformat()
        safe = lambda s: s.replace("\n", " ").replace("##", "#")
        entry = (f"\n## {safe(title)}\ntags: {', '.join(tags)}\nwhen: {', '.join(when)}\ndecide: {safe(decide)}\n"
                 f"Learned from your review of \"{safe(goal)}\" ({task_id}, {day}).\n")
        with path.open("a", encoding="utf-8") as f:
            f.write(entry)
        return {"field": field, "title": title, "decide": decide, "file": str(path.relative_to(self.folder.parent.parent)), "owners": owners}
