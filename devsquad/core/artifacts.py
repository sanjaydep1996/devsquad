# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Artifacts Engine: generates Architecture Decision Records (ADRs), OpenAPI specs, and release changelogs."""

import ast
import datetime
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ADRDocument:
    """Represents a standardized Architecture Decision Record."""
    number: int
    title: str
    status: str  # 'Draft', 'Proposed', 'Accepted', 'Superseded'
    date: str
    context: str
    decision: str
    consequences: str
    markdown_content: str


class ArtifactsPublisher:
    """Zeta and Apex's publishing engine for living system documentation."""

    def __init__(self, repo_root: Optional[pathlib.Path] = None):
        self.repo_root = (repo_root or pathlib.Path.cwd()).resolve()

    def generate_adr(
        self,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        status: str = "Accepted",
        adr_number: Optional[int] = None,
    ) -> ADRDocument:
        """Generates a standardized Architecture Decision Record in Markdown."""
        if adr_number is None:
            # Count existing ADRs
            adr_dir = self.repo_root / "docs" / "adr"
            adr_dir.mkdir(parents=True, exist_ok=True)
            existing = list(adr_dir.glob("*.md"))
            adr_number = len(existing) + 1

        num_str = f"{adr_number:04d}"
        today = datetime.date.today().isoformat()

        content = (
            f"# {num_str}. {title}\n\n"
            f"Date: {today}\n"
            f"Status: {status}\n\n"
            f"## Context\n\n{context.strip()}\n\n"
            f"## Decision\n\n{decision.strip()}\n\n"
            f"## Consequences\n\n{consequences.strip()}\n"
        )

        return ADRDocument(
            number=adr_number,
            title=title,
            status=status,
            date=today,
            context=context,
            decision=decision,
            consequences=consequences,
            markdown_content=content,
        )

    def extract_openapi_specs(self, source_code: str) -> Dict[str, Any]:
        """Parses Python AST decorators to extract OpenAPI 3.0 path definitions."""
        paths: Dict[str, Any] = {}

        try:
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for decorator in node.decorator_list:
                        # Match @app.get('/path') or @app.post('/path')
                        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                            method = decorator.func.attr.lower()
                            if method in ("get", "post", "put", "delete", "patch"):
                                if decorator.args and isinstance(decorator.args[0], ast.Constant):
                                    route_path = str(decorator.args[0].value)
                                    doc = ast.get_docstring(node) or f"Endpoint for {node.name}"
                                    if route_path not in paths:
                                        paths[route_path] = {}
                                    paths[route_path][method] = {
                                        "summary": node.name.replace("_", " ").title(),
                                        "description": doc.strip(),
                                        "operationId": node.name,
                                        "responses": {
                                            "200": {"description": "Successful operation"}
                                        }
                                    }
        except Exception:
            pass

        return {
            "openapi": "3.0.3",
            "info": {
                "title": "DevSquad Auto-Generated API Spec",
                "version": "1.0.0",
                "description": "Extracted directly from source code AST decorators.",
            },
            "paths": paths,
        }

    def generate_release_changelog(
        self, version: str, commit_messages: List[str]
    ) -> str:
        """Formats conventional commits into a clean Markdown CHANGELOG section."""
        today = datetime.date.today().isoformat()
        feats, fixes, docs, chore = [], [], [], []

        for msg in commit_messages:
            clean = msg.strip()
            if clean.startswith("feat"):
                feats.append(clean)
            elif clean.startswith("fix"):
                fixes.append(clean)
            elif clean.startswith("docs"):
                docs.append(clean)
            else:
                chore.append(clean)

        lines = [f"## [{version}] - {today}\n"]
        if feats:
            lines.append("### ✨ Features")
            for f in feats: lines.append(f"- {f}")
            lines.append("")
        if fixes:
            lines.append("### 🐛 Bug Fixes")
            for fx in fixes: lines.append(f"- {fx}")
            lines.append("")
        if docs:
            lines.append("### 📚 Documentation")
            for d in docs: lines.append(f"- {d}")
            lines.append("")
        if chore:
            lines.append("### 🔧 Maintenance & Refactoring")
            for c in chore: lines.append(f"- {c}")
            lines.append("")

        return "\n".join(lines).strip()
