# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Code review agent: Gamma reviews a change against the Testing, Security and other field guides.

It reads only the lines a change adds, so every finding points at new code. The checks are
deterministic pattern rules, each tied to the field-guide entry it comes from, so a finding always
says why. It works on uncommitted changes, a branch, a GitHub pull request or a staged relay run.
"""

import hashlib
import pathlib
import re
import subprocess
from typing import Any, Callable, Dict, List, Optional, Tuple

CODE = r"\.(py|js|jsx|ts|tsx|go|rb|java|kt|php|cs|rs)$"
RULES: List[Dict[str, Any]] = [
    {"id": "secret", "field": "Security", "guide": "Least privilege everywhere", "severity": "high", "files": r".*",
     "pattern": r"""(?i)(api[_-]?key|secret|passw(or)?d|token)\s*[:=]\s*['"][^'"\s]{8,}['"]""",
     "message": "Looks like a secret written into the code. Read it from the environment instead, and rotate it if it was ever committed."},
    {"id": "sql-string", "field": "Security", "guide": "Never build queries or commands from strings", "severity": "high", "files": CODE,
     "pattern": r"""(?i)(execute|query|raw)\s*\(\s*(f['"]|['"][^'"]*['"]\s*(%|\+|\.format))[^)]*\b(select|insert|update|delete)\b|\b(select|insert|update|delete)\b[^'"]*['"]\s*(%|\+)""",
     "message": "A SQL query is built from a string. Use parameters so input can't change the query."},
    {"id": "shell", "field": "Security", "guide": "Never build queries or commands from strings", "severity": "high", "files": CODE,
     "pattern": r"shell\s*=\s*True|os\.system\(|child_process\.exec\(",
     "message": "Runs a command through the shell. Pass an argument list instead, so input can't add commands."},
    {"id": "eval", "field": "Security", "guide": "Never build queries or commands from strings", "severity": "high", "files": CODE,
     "pattern": r"(?<![\w.])(eval|exec)\s*\(|new Function\(",
     "message": "Evaluates code at run time. Use a parser or a lookup table instead."},
    {"id": "weak-hash", "field": "Security", "guide": "Store passwords properly", "severity": "high", "files": CODE,
     "pattern": r"(?i)(md5|sha1)\s*\(|hashlib\.(md5|sha1)\b",
     "message": "MD5 and SHA-1 are too fast for passwords or tokens. Use Argon2id, bcrypt or PBKDF2."},
    {"id": "tls-off", "field": "Security", "guide": "Treat tokens as secrets", "severity": "high", "files": CODE,
     "pattern": r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false|InsecureSkipVerify\s*:\s*true",
     "message": "Turns off certificate checks, so traffic can be intercepted."},
    {"id": "inner-html", "field": "Security", "guide": "Never build queries or commands from strings", "severity": "medium", "files": r"\.(js|jsx|ts|tsx|html|vue|svelte)$",
     "pattern": r"\.innerHTML\s*=(?!\s*['\"`]\s*['\"`])|dangerouslySetInnerHTML",
     "message": "Writes HTML directly. Escape anything that came from a user, or build elements instead."},
    {"id": "bare-except", "field": "Backend", "guide": "Log for the person on call", "severity": "medium", "files": r"\.py$",
     "pattern": r"^\s*except\s*:\s*(pass)?\s*$|except Exception\s*:\s*pass",
     "message": "Swallows every error silently. Catch the specific error and log it with context."},
    {"id": "debug-print", "field": "Backend", "guide": "Log for the person on call", "severity": "low", "files": CODE,
     "pattern": r"^\s*(print\(|console\.log\(|debugger;)",
     "message": "Debug output left in. Use the logger, or remove it."},
    {"id": "no-timeout", "field": "Architecture", "guide": "Design for failure", "severity": "medium", "files": r"\.py$",
     "pattern": r"requests\.(get|post|put|delete|patch)\((?![^)]*timeout)",
     "message": "Network call without a timeout can hang forever. Add timeout=."},
    {"id": "img-alt", "field": "Frontend", "guide": "Accessible by default", "severity": "medium", "files": r"\.(html|jsx|tsx|vue|svelte)$",
     "pattern": r"<img(?![^>]*\balt=)[^>]*>",
     "message": "Image without alt text. Screen readers can't describe it."},
    {"id": "div-click", "field": "Frontend", "guide": "Accessible by default", "severity": "medium", "files": r"\.(html|jsx|tsx|vue|svelte)$",
     "pattern": r"<(div|span)[^>]*\bon[Cc]lick=",
     "message": "A clickable div can't be reached by keyboard. Use a button."},
    {"id": "latest-tag", "field": "DevOps", "guide": "Build once, configure per environment", "severity": "low", "files": r"(Dockerfile|\.ya?ml)$",
     "pattern": r"(FROM|image:)\s*\S+:latest\b",
     "message": "The :latest tag changes under you. Pin a version."},
    {"id": "todo", "field": "Docs", "guide": "Document the change with the change", "severity": "low", "files": r".*",
     "pattern": r"\b(TODO|FIXME|XXX)\b",
     "message": "A TODO left in the change. Finish it or turn it into a card on the board."},
]
Run = Callable[[List[str], Optional[str]], subprocess.CompletedProcess]


def parse_diff(text: str) -> List[Dict[str, Any]]:
    """Files in a unified diff, with the line numbers of the lines it adds."""
    files: List[Dict[str, Any]] = []
    current, line = None, 0
    for raw in (text or "").splitlines():
        if raw.startswith("+++ "):
            path = raw[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            current = None if path == "/dev/null" else {"path": path, "added": []}
            if current:
                files.append(current)
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            line = int(m.group(1)) if m else 0
        elif current is not None and raw.startswith("+") and not raw.startswith("+++"):
            current["added"].append((line, raw[1:]))
            line += 1
        elif current is not None and not raw.startswith("-"):
            line += 1
    return files


class CodeReviewer:
    def __init__(self, root: pathlib.Path, run: Optional[Run] = None, staging: Any = None):
        self.root = root
        self.run = run or (lambda argv, cwd: subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60))
        self.staging = staging

    def _diff(self, target: str) -> Tuple[str, str]:
        target = (target or "working").strip()
        if target.startswith("staged:"):
            task = self.staging.load_task(target[7:]) if self.staging else None
            if not task:
                raise ValueError("That staged run doesn't exist.")
            return "\n".join(d.patch_text for d in task.diffs), f"the staged run {task.task_id}"
        if re.fullmatch(r"(pr:)?#?\d{1,7}", target):
            n = re.sub(r"\D", "", target)
            try:
                r = self.run(["gh", "pr", "diff", n], str(self.root))
            except FileNotFoundError:
                raise ValueError("The GitHub CLI (gh) isn't installed, so pull requests can't be read.")
            if r.returncode != 0:
                raise ValueError("Couldn't read that pull request: " + (r.stderr or r.stdout).strip()[:200])
            return r.stdout, f"pull request #{n}"
        if target == "working":
            r = self.run(["git", "diff", "HEAD"], str(self.root))
            if r.returncode != 0:
                raise ValueError("This folder isn't a git repository with a commit yet.")
            return r.stdout, "your uncommitted changes"
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", target) or target.startswith("-"):
            raise ValueError("That isn't a branch name.")
        base = next((b for b in ("main", "master", "develop") if self.run(["git", "rev-parse", "--verify", "--quiet", b], str(self.root)).returncode == 0), None)
        if not base:
            raise ValueError("Couldn't find main, master or develop to compare the branch with.")
        r = self.run(["git", "diff", f"{base}...{target}"], str(self.root))
        if r.returncode != 0:
            raise ValueError(f"Couldn't compare {target} with {base}: " + (r.stderr or "").strip()[:200])
        return r.stdout, f"branch {target} against {base}"

    def review(self, target: str) -> Dict[str, Any]:
        text, label = self._diff(target)
        files = parse_diff(text)
        findings: List[Dict[str, Any]] = []
        for f in files:
            for rule in RULES:
                if not re.search(rule["files"], f["path"]):
                    continue
                for line, code in f["added"]:
                    if re.search(rule["pattern"], code):
                        fid = hashlib.sha1(f"{f['path']}:{line}:{rule['id']}".encode()).hexdigest()[:10]
                        findings.append({"id": fid, "file": f["path"], "line": line, "severity": rule["severity"], "rule": rule["id"],
                                         "field": rule["field"], "message": rule["message"], "source": f"{rule['field']} guide: {rule['guide']}",
                                         "snippet": code.strip()[:200]})
        code_files = [f["path"] for f in files if re.search(CODE, f["path"]) and f["added"]]
        tests = [p for p in (f["path"] for f in files) if re.search(r"(^|/)(tests?|__tests__|spec)/|test_|_test\.|\.test\.|\.spec\.", p)]
        if code_files and not tests:
            findings.append({"id": "no-tests", "file": code_files[0], "line": 0, "severity": "medium", "rule": "no-tests", "field": "Testing",
                             "message": f"{len(code_files)} code file(s) changed with no test changes. Add a test that proves the new behaviour.",
                             "source": "Testing guide: Test pyramid", "snippet": ""})
        order = {"high": 0, "medium": 1, "low": 2}
        findings.sort(key=lambda x: (order[x["severity"]], x["file"], x["line"]))
        counts = {s: sum(1 for x in findings if x["severity"] == s) for s in order}
        summary = (f"Gamma reviewed {label}: {len(files)} file(s), {sum(len(f['added']) for f in files)} added line(s). "
                   + (f"{counts['high']} high, {counts['medium']} medium and {counts['low']} low finding(s)." if findings else "Nothing to flag."))
        return {"target": target or "working", "label": label, "files": len(files), "findings": findings[:200], "counts": counts, "summary": summary}
