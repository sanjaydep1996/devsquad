# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Research desk: a research question becomes a study plan you can run with real users.

The method comes from the Research field guide (interviews to learn why, usability tests to check a
design, surveys to measure how many, card sorting for navigation, diary studies for behaviour over
time, A/B tests to compare two versions). Plans work without AI; a local model can add tailored questions.
"""

import json
import re
import time
import uuid
from typing import Any, Dict, List, Optional

METHODS: Dict[str, Dict[str, Any]] = {
    "interviews": {"name": "User interviews", "best_for": "learning why people do what they do", "sample": "5 to 8 people", "time": "2 to 4 weeks"},
    "usability": {"name": "Usability testing", "best_for": "checking whether a design or flow works", "sample": "5 to 8 people", "time": "1 to 2 weeks"},
    "survey": {"name": "Survey", "best_for": "measuring how many people think or do something", "sample": "100 or more responses", "time": "1 to 2 weeks"},
    "card_sort": {"name": "Card sorting", "best_for": "deciding how navigation and menus are organised", "sample": "15 to 30 people", "time": "1 week"},
    "diary": {"name": "Diary study", "best_for": "understanding behaviour over days or weeks", "sample": "10 to 15 people", "time": "2 to 8 weeks"},
    "ab_test": {"name": "A/B test", "best_for": "comparing two versions on a real metric", "sample": "enough traffic for statistical significance", "time": "1 to 4 weeks"},
}
RULES = [
    ("ab_test", r"\b(which (version|design|one)|compare|a/b|ab test|versus|vs\.?|convert(s|ion)? better|variant)\b"),
    ("card_sort", r"\b(navigation|menu|categor|information architecture|where (do|would) .* (find|look)|labels?|organi[sz]e)\b"),
    ("diary", r"\b(over time|daily|every day|weekly|habit|routine|long[- ]term|across (days|weeks))\b"),
    ("survey", r"\b(how many|how often|what percent|what share|most (people|users)|satisf|nps|rate|ranking|prefer)\b"),
    ("usability", r"\b(can (users|people|they)|usab|confus|stuck|flow|onboarding|checkout|sign ?up|find (the|it)|easy to|redesign|prototype)\b"),
    ("interviews", r".*"),
]


def choose_method(question: str) -> str:
    q = (question or "").lower()
    return next(key for key, pattern in RULES if re.search(pattern, q))


def _script(method: str, question: str) -> List[Dict[str, Any]]:
    topic = question.rstrip("?. ")
    if method in ("interviews", "diary"):
        return [
            {"part": "Warm-up (5 min)", "items": ["Thank them, explain there are no wrong answers, and ask to record.", "Tell me a bit about your role and a normal day."]},
            {"part": "Context (10 min)", "items": ["Walk me through the last time you did this, step by step.", "What were you trying to get done? What did you use?"]},
            {"part": "Deep dive (20 min)", "items": [f"Tell me about a time when {topic.lower()} came up. What happened?", "What was the hardest part? Why?", "What did you try instead? How did that go?", "If you could change one thing, what would it be?"]},
            {"part": "Reaction (10 min)", "items": ["Show the concept or current screen. What do you expect this to do?", "What's missing for you?"]},
            {"part": "Wrap-up (5 min)", "items": ["Is there anything I should have asked?", "Thank them; note anything to follow up."]},
        ]
    if method == "usability":
        return [
            {"part": "Set-up (5 min)", "items": ["Explain you're testing the design, not them, and ask them to think aloud."]},
            {"part": "Tasks (30 min)", "items": [f"Task 1: a realistic goal related to: {topic}. Don't explain how.", "Task 2: the next most common goal.", "Task 3: an edge case (an error, an empty state).", "For each task note: success, time, wrong turns, and quotes."]},
            {"part": "Debrief (10 min)", "items": ["What was easiest? What was most frustrating?", "Rate the difficulty of each task from 1 to 5."]},
        ]
    if method == "card_sort":
        return [{"part": "Card sort (20 min)", "items": ["Give 30 to 50 cards, one per page or feature.", "Ask them to group the cards and name each group.", "Ask where they'd expect to find the three most important cards."]}]
    if method == "ab_test":
        return [{"part": "Experiment set-up", "items": ["Version A: today's design. Version B: one clear change.", "Split traffic randomly; keep everything else the same.", "Decide the run length and the minimum sample before starting, and don't peek early."]}]
    return [{"part": "Survey (10 min to answer)", "items": ["Screener: one question that confirms they're in the target group.", "Behaviour: how often do you do this? (never to daily)", f"Attitude: how much do you agree: \"{topic}\" (1 to 5)", "Open: what's the one thing you'd change?"]}]


class ResearchDesk:
    def __init__(self, root):
        self.folder = root / ".devsquad" / "research"

    def plan(self, question: str, provider: Any = None) -> Dict[str, Any]:
        question = re.sub(r"\s+", " ", question or "").strip()[:300]
        if len(question) < 8:
            raise ValueError("Write the question you want answered, for example: Why do people drop off at checkout?")
        method = choose_method(question)
        m = METHODS[method]
        plan = {
            "id": f"research-{uuid.uuid4().hex[:8]}", "question": question, "method": method, "method_name": m["name"],
            "why": f"{m['name']} is best for {m['best_for']}, which is what this question needs.",
            "sample": m["sample"], "timeline": m["time"],
            "participants": ["People who did this in the last month (not colleagues or friends).", "A mix of new and experienced users.", "Screen them with one question that confirms they fit."],
            "script": _script(method, question),
            "synthesis": ["Write each observation on its own note (quote or behaviour, plus who).", "Group notes into themes (affinity mapping) and name each theme as an insight with its evidence.", "Rank fixes on an impact and effort matrix; pick the top three."],
            "success_metric": "Decide now which result would change the plan, and which metric you'll watch after shipping.",
            "source": "Research guide", "created": time.time(), "tailored": [],
        }
        if provider is not None and "template" not in getattr(provider, "provider_name", "template"):
            try:
                reply = provider.complete(
                    f"Research question: {question}\nMethod: {m['name']}\nWrite 6 open, non-leading questions about real past experiences. "
                    'Reply with only JSON: {"questions": ["..."]}', system="You are a careful user researcher. JSON only.", max_tokens=600)
                data = json.loads(re.search(r"\{.*\}", reply.text or "", re.S).group(0))
                plan["tailored"] = [re.sub(r"\s+", " ", str(q)).strip()[:200] for q in data.get("questions", []) if str(q).strip()][:8]
            except Exception:
                plan["tailored"] = []   # the standard plan still stands
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / f"{plan['id']}.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return plan

    def get(self, plan_id: str) -> Dict[str, Any]:
        if not re.fullmatch(r"research-[a-f0-9]{8}", plan_id or ""):
            raise ValueError("That research plan doesn't exist.")
        path = self.folder / f"{plan_id}.json"
        if not path.is_file():
            raise ValueError("That research plan doesn't exist.")
        return json.loads(path.read_text(encoding="utf-8"))


def research_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# Research plan: {plan['question']}", "", f"**Method:** {plan['method_name']} · **Sample:** {plan['sample']} · **Timeline:** {plan['timeline']}", "", plan["why"], "",
             "## Participants", ""] + [f"- {p}" for p in plan["participants"]] + ["", "## Guide", ""]
    for part in plan["script"]:
        lines += [f"### {part['part']}", ""] + [f"- {i}" for i in part["items"]] + [""]
    if plan.get("tailored"):
        lines += ["## Questions tailored to this study", ""] + [f"- {q}" for q in plan["tailored"]] + [""]
    lines += ["## Making sense of it", ""] + [f"- {s}" for s in plan["synthesis"]] + ["", "## Success", "", plan["success_metric"], "",
              f"_From the {plan['source']} in DevSquad._", ""]
    return "\n".join(lines)
