# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Exports a plan, a run's replay or a run's post-mortem as Markdown or PDF.

Everything in an export comes from what DevSquad recorded. The PDF writer uses the standard
library only and the PDF's built-in fonts, so exporting needs nothing installed.
"""

import datetime
import re
import zlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

TEAM_NAMES = {"apex": "Apex", "alpha_be": "Alpha BE", "beta_fe": "Beta FE", "gamma_qa": "Gamma QA",
              "delta_devops": "Delta", "zeta_docs": "Zeta", "": "Unassigned"}
OUTCOMES = {"tested_green": "tests passed", "tested_red": "tests failed", "staged": "not tested yet",
            "applied": "applied to the repo", "rejected": "rejected"}


@dataclass
class Download:
    """A file the server sends as a download rather than JSON."""
    filename: str
    content_type: str
    data: bytes


def _when(ts: Any) -> str:
    try:
        return datetime.datetime.fromtimestamp(float(ts), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return "unknown"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------- Markdown ----------
def plan_markdown(plan: Dict[str, Any]) -> str:
    lines = [f"# Plan: {plan.get('goal', '')}", "",
             f"**Plan:** `{plan.get('id', '')}` · **Status:** {plan.get('status', 'proposed')} · "
             f"**Created:** {_when(plan.get('created'))} · **Written by:** {plan.get('source') or 'template'}", ""]
    if plan.get("summary"):
        lines += [str(plan["summary"]), ""]
    if plan.get("note"):
        lines += [f"> {plan['note']}", ""]
    lines += ["## Tasks", ""]
    for i, t in enumerate(plan.get("tasks") or [], 1):
        lines.append(f"{i}. **{t.get('title', '')}** ({TEAM_NAMES.get(t.get('owner') or '', t.get('owner'))})")
        if t.get("detail"):
            lines.append(f"   {t['detail']}")
    if plan.get("decisions"):
        lines += ["", "## Decisions from the field guides", ""] + [f"- **{TEAM_NAMES.get(d.get('owner', ''), d.get('owner'))}**: {d.get('decision')} ({d.get('source')})" for d in plan["decisions"]]
    for title, key in (("Risks", "risks"), ("Questions to answer before building", "questions")):
        items = plan.get(key) or []
        lines += ["", f"## {title}", ""] + ([f"- {x}" for x in items] or ["- None recorded."])
    lines += ["", f"_Exported from DevSquad on {_now()}._", ""]
    return "\n".join(lines)


def _step_line(s: Dict[str, Any]) -> str:
    clock = str(s.get("timestamp", ""))[11:19] or "--:--:--"
    took = s.get("duration_ms", 0) / 1000
    who = TEAM_NAMES.get(s.get("agent_name", ""), s.get("agent_name", ""))
    mark = " (failed)" if s.get("status") == "failed" else ""
    return f"{s.get('step_index')}. {clock} · {who} · {s.get('tool_name', '')} · {took:.0f} s{mark}"


def replay_markdown(replay: Dict[str, Any]) -> str:
    steps = replay.get("steps") or []
    first = steps[0] if steps else {}
    lines = [f"# Run replay: {replay.get('goal') or replay.get('session_id')}", "",
             f"**Run:** `{replay.get('session_id')}` · **{len(steps)} steps** · "
             f"**Model:** {first.get('provider', 'local')} / {first.get('model', 'template')} · **Cost:** $0.00 (local model)", "",
             "## Steps", ""]
    lines += [_step_line(s) for s in steps]
    total = sum(s.get("duration_ms", 0) for s in steps) / 1000
    lines += ["", f"Total time: {total:.0f} s.", "", f"_Exported from DevSquad on {_now()}._", ""]
    return "\n".join(lines)


def postmortem_markdown(replay: Dict[str, Any], task: Any = None) -> str:
    """A blameless post-mortem built only from the run's record. Nothing in it is guessed."""
    steps = replay.get("steps") or []
    status = getattr(task, "status", "") if task else ""
    result = getattr(task, "test_result", None) if task else None
    failed = next((s for s in steps if s.get("status") == "failed"), None)
    failure = (getattr(result, "failure_summary", None) or "").strip() if result and not result.passed else ""
    lines = [f"# Post-mortem: {replay.get('goal') or replay.get('session_id')}", "",
             f"**Run:** `{replay.get('session_id')}` · **Outcome:** {OUTCOMES.get(status, status or 'unknown')} · **Written:** {_now()}", ""]
    if failed or failure:
        where = failed or (steps[-1] if steps else {})
        who = TEAM_NAMES.get(where.get("agent_name", ""), where.get("agent_name", "?"))
        lines += ["## What failed", "", f"- {failure or where.get('tool_name', 'A step failed.')}", "",
                  "## Where it was caught", "", f"- Step {where.get('step_index', '?')}, {who}: {where.get('tool_name', '')}", ""]
        if result is not None:
            lines += [f"- Test command: `{result.command}` (exit code {result.exit_code})", ""]
    else:
        lines += ["## What failed", "", "- No failure was recorded in this run.", ""]
    lines += ["## Timeline", ""] + [_step_line(s) for s in steps] + [""]
    diffs = getattr(task, "diffs", None) or []
    lines += ["## Files changed", ""]
    lines += [f"- {d.file_path} (+{d.additions} / -{d.deletions}{', new file' if d.is_new else ''})" for d in diffs] or ["- No file changes were recorded."]
    if result is not None and result.output and not result.passed:
        lines += ["", "## Test output (last lines)", "", "```"] + result.output.strip().splitlines()[-25:] + ["```"]
    lines += ["", "## Root cause", "",
              "Not known from the record. Read the diff and the full test output to confirm it." if (failed or failure)
              else "Nothing failed, so there is no root cause to find.", "",
              "## Next steps", ""]
    if failed or failure:
        lines += ["- [ ] Read the full test output for the failing step.",
                  "- [ ] Check the files changed above, then fix or reject the change in the Review Desk.",
                  "- [ ] Add a test that reproduces the failure, so it can't come back unnoticed."]
    else:
        lines += ["- [ ] Review the change in the Review Desk before applying it."]
    lines += ["", f"_Exported from DevSquad on {_now()}._", ""]
    return "\n".join(lines)


# ---------- PDF ----------
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + \
    [278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667,
     778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556,
     556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
_BOLD = [278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278] + [556] * 10 + \
    [333, 333, 584, 584, 584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778, 667,
     778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611,
     611, 278, 278, 556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584]
_PAGE_W, _PAGE_H, _MARGIN = 595, 842, 56


def _cp1252(text: str) -> bytes:
    return text.encode("cp1252", errors="replace")


def _width(raw: bytes, font: str, size: float) -> float:
    if font == "F3":
        return len(raw) * 600 * size / 1000
    table = _BOLD if font == "F2" else _HELV
    return sum(table[c - 32] if 32 <= c < 127 else 556 for c in raw) * size / 1000


def _wrap(text: str, font: str, size: float, width: float) -> List[bytes]:
    words, lines, line = _cp1252(text).split(b" "), [], b""
    for w in words:
        trial = line + (b" " if line else b"") + w
        if line and _width(trial, font, size) > width:
            lines.append(line)
            line = w
        else:
            line = trial
        while _width(line, font, size) > width and len(line) > 1:   # a single word wider than the page
            cut = len(line)
            while cut > 1 and _width(line[:cut], font, size) > width:
                cut -= 1
            lines.append(line[:cut])
            line = line[cut:]
    lines.append(line)
    return lines


def _plain(text: str) -> str:
    """Drops Markdown emphasis marks that a plain PDF line can't show."""
    return re.sub(r"\*\*(.+?)\*\*|__(.+?)__|`([^`]+)`|_(.+?)_", lambda m: next(g for g in m.groups() if g is not None), text)


def _pdf_string(raw: bytes) -> bytes:
    return b"(" + raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def markdown_to_pdf(markdown: str, title: str = "") -> bytes:
    """A simple, readable A4 PDF of a Markdown document: headings, paragraphs, lists and code blocks."""
    pages: List[List[bytes]] = [[]]
    y = _PAGE_H - _MARGIN
    usable = _PAGE_W - 2 * _MARGIN

    def emit(raw: bytes, font: str, size: float, x: float, gap: float) -> None:
        nonlocal y
        if y - gap < _MARGIN:
            pages.append([])
            y = _PAGE_H - _MARGIN
        y -= gap
        pages[-1].append(b"BT /%s %.1f Tf %.1f %.1f Td %s Tj ET" % (font.encode(), size, x, y, _pdf_string(raw)))

    in_code = False
    for line in markdown.replace("\r", "").split("\n"):
        if line.strip().startswith("```"):
            in_code = not in_code
            y -= 3
            continue
        if in_code:
            for chunk in _wrap(line.replace("\t", "    ") or " ", "F3", 8.5, usable - 10):
                emit(chunk, "F3", 8.5, _MARGIN + 10, 11)
            continue
        if not line.strip():
            y -= 6
            continue
        heading = re.match(r"(#{1,3})\s+(.*)", line)
        bullet = re.match(r"(\s*)(?:[-*+]|(\d+)\.)\s+(.*)", line)
        if heading:
            size = {1: 18, 2: 13.5, 3: 11.5}[len(heading.group(1))]
            y -= 8 if len(heading.group(1)) > 1 else 0
            for chunk in _wrap(_plain(heading.group(2)), "F2", size, usable):
                emit(chunk, "F2", size, _MARGIN, size * 1.35)
            y -= 3
        elif bullet:
            indent = _MARGIN + 6 + min(len(bullet.group(1)), 6) * 4
            mark = (bullet.group(2) + ".") if bullet.group(2) else "•"
            body = re.sub(r"^\[( |x)\]\s*", lambda m: "[x] " if m.group(1) == "x" else "[ ] ", bullet.group(3))
            chunks = _wrap(_plain(body), "F1", 10, usable - (indent - _MARGIN) - 14)
            emit(_cp1252(mark), "F1", 10, indent, 14)
            y += 14
            for i, chunk in enumerate(chunks):
                emit(chunk, "F1", 10, indent + 14, 14 if i == 0 else 13)
        else:
            text = line.strip()
            font = "F1"
            if text.startswith(">"):
                text = text.lstrip("> ")
            for chunk in _wrap(_plain(text), font, 10, usable):
                emit(chunk, font, 10, _MARGIN, 14)

    # Assemble: catalog, page tree, fonts, then each page and its content
    objects: List[bytes] = []
    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")          # filled in once the page tree number is known
    tree = add(b"")
    fonts = [add(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding /WinAnsiEncoding >>" % name)
             for name in (b"Helvetica", b"Helvetica-Bold", b"Courier")]
    kids = []
    for n, ops in enumerate(pages, 1):
        footer = b"BT /F1 8 Tf %d 30 Td %s Tj ET" % (_MARGIN, _pdf_string(_cp1252(f"{title or 'DevSquad'} · page {n} of {len(pages)}")))
        stream = zlib.compress(b"\n".join(ops + [footer]))
        content = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %d %d] /Contents %d 0 R "
                        b"/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R >> >> >>"
                        % (tree, _PAGE_W, _PAGE_H, content, *fonts)))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % tree
    objects[tree - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    info = add(b"<< /Title %s /Producer (DevSquad) >>" % _pdf_string(_cp1252(title or "DevSquad export")))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, info, xref)
    return bytes(out)


def as_download(markdown: str, stem: str, fmt: str, title: str) -> Download:
    if fmt == "pdf":
        return Download(f"{stem}.pdf", "application/pdf", markdown_to_pdf(markdown, title))
    return Download(f"{stem}.md", "text/markdown; charset=utf-8", markdown.encode("utf-8"))
