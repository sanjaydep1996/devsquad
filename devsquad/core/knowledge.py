# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Field guides: the fundamentals each agent refers to when a task is assigned to them.

The guides ship in devsquad/knowledge/ (architecture, backend, frontend, testing, devops, security,
docs and research). A project can add its own in .devsquad/knowledge/*.md, in the same format.
Looking things up is local keyword matching, so it costs nothing and works without any AI. Each entry
carries a decision rule, so an agent can decide on its own and say which guide the decision came from.
"""

import pathlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SHIPPED = pathlib.Path(__file__).resolve().parent.parent / "knowledge"
AGENT_FIELDS: Dict[str, List[str]] = {
    "apex": ["Architecture", "Research", "Security"],
    "alpha_be": ["Backend", "Security", "Testing"],
    "beta_fe": ["Frontend", "Research"],
    "gamma_qa": ["Testing", "Security"],
    "delta_devops": ["DevOps", "Security"],
    "zeta_docs": ["Docs", "Research"],
}
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "with", "by", "is", "it", "be", "add", "make", "new", "when", "this", "that"}


def _words(text: str) -> set:
    return {w for w in _WORD.findall((text or "").lower()) if w not in _STOP and len(w) > 1}


@dataclass
class Entry:
    field: str
    title: str
    decide: str
    body: str = ""
    tags: List[str] = field(default_factory=list)
    when: List[str] = field(default_factory=list)
    owners: List[str] = field(default_factory=list)
    source: str = "shipped"

    def as_dict(self) -> Dict:
        return {"field": self.field, "title": self.title, "decide": self.decide, "body": self.body,
                "tags": self.tags, "when": self.when, "source": self.source}


def parse_guide(text: str, source: str) -> List[Entry]:
    head = re.match(r"---\n(.*?)\n---\n", text, re.S)
    meta = dict(line.split(":", 1) for line in (head.group(1).splitlines() if head else []) if ":" in line)
    field_name = meta.get("field", "General").strip()
    owners = [o.strip() for o in meta.get("owners", "").split(",") if o.strip()]
    entries = []
    for block in re.split(r"^## ", text[head.end() if head else 0:], flags=re.M)[1:]:
        lines = block.strip().splitlines()
        title, props, body = lines[0].strip(), {}, []
        for line in lines[1:]:
            key, _, value = line.partition(":")
            if key.strip() in ("tags", "when", "decide") and value:
                props[key.strip()] = value.strip()
            elif line.strip():
                body.append(line.strip())
        if not props.get("decide"):
            continue
        split = lambda s: [x.strip().lower() for x in (s or "").split(",") if x.strip()]
        entries.append(Entry(field_name, title[:120], props["decide"][:600], " ".join(body)[:900],
                             split(props.get("tags")), split(props.get("when")), owners, source))
    return entries


class KnowledgeBase:
    def __init__(self, root: Optional[pathlib.Path] = None):
        self.entries: List[Entry] = []
        for path in sorted(SHIPPED.glob("*.md")):
            self.entries += parse_guide(path.read_text(encoding="utf-8"), "shipped")
        own = (root or pathlib.Path.cwd()) / ".devsquad" / "knowledge"
        if own.is_dir():
            for path in sorted(own.glob("*.md"))[:50]:
                try:
                    self.entries += parse_guide(path.read_text(encoding="utf-8")[:200_000], "project")
                except (OSError, UnicodeDecodeError):
                    continue

    def fields(self) -> List[Dict]:
        out: Dict[str, Dict] = {}
        for e in self.entries:
            f = out.setdefault(e.field, {"field": e.field, "agents": [a for a, fs in AGENT_FIELDS.items() if e.field in fs], "entries": []})
            f["entries"].append(e.as_dict())
        return list(out.values())

    @staticmethod
    def _score(e: Entry, goal: str, words: set) -> float:
        g = " " + " ".join(_WORD.findall(goal.lower())) + " "
        when = sum(3.0 for w in e.when if f" {w} " in g or (len(w) > 4 and w in g))
        tags = sum(1.0 for t in e.tags if f" {t} " in g)
        overlap = 0.3 * len(words & _words(e.title + " " + e.decide))
        return when + tags + overlap if (when or tags) else 0.0

    def brief(self, agent: str, goal: str, k: int = 4) -> List[Entry]:
        """The entries from this agent's fields that fit the task best."""
        fields, words = AGENT_FIELDS.get(agent, []), _words(goal)
        scored = [(self._score(e, goal, words), i, e) for i, e in enumerate(self.entries) if e.field in fields]
        scored = [s for s in scored if s[0] > 0]
        scored.sort(key=lambda s: (-s[0], s[1]))
        return [e for _, _, e in scored[:k]]

    def decide(self, agent: str, goal: str, k: int = 3) -> List[Dict]:
        """Decisions this agent takes on its own for the task, each with the guide it came from."""
        return [{"owner": agent, "field": e.field, "decision": e.decide, "why": e.body or e.title, "source": f"{e.field} guide: {e.title}"}
                for e in self.brief(agent, goal, k)]

    @staticmethod
    def as_prompt(entries: List[Entry]) -> str:
        if not entries:
            return ""
        return "FUNDAMENTALS TO APPLY (from the team's field guides):\n" + "\n".join(f"- [{e.field}] {e.title}: {e.decide}" for e in entries)
