# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Blast-Radius Analyzer: inspects import graphs and AST dependencies to quantify change impact."""

import ast
import os
import pathlib
import re
from typing import Dict, List, Set


class BlastRadiusAnalyzer:
    """Analyzes AST import dependencies and callers to compute the blast radius of changes."""

    def __init__(self, root: pathlib.Path):
        self.root = root.resolve()

    def _get_python_files(self) -> List[pathlib.Path]:
        py_files = []
        for p in self.root.rglob("*.py"):
            parts = p.parts
            if any(part in (".git", ".devsquad", "__pycache__", "venv", ".venv", "env") for part in parts):
                continue
            py_files.append(p)
        return py_files

    def _parse_imports(self, file_path: pathlib.Path) -> Set[str]:
        """Extracts imported module names from a Python source file."""
        imported = set()
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        imported.add(n.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module)
        except Exception:
            try:
                content = file_path.read_text(encoding="utf-8")
                matches = re.findall(r"^(?:from|import)\s+([\w\.]+)", content, re.MULTILINE)
                imported.update(matches)
            except Exception:
                pass
        return imported

    def analyze(self, modified_files: List[str]) -> Dict:
        """Computes direct impacts, caller risks, and graph nodes/edges."""
        all_files = self._get_python_files()
        
        file_imports: Dict[str, Set[str]] = {}
        for f in all_files:
            rel = str(f.relative_to(self.root))
            file_imports[rel] = self._parse_imports(f)

        nodes = []
        links = []
        visited = set()

        # 1. Direct modifications
        for mf in modified_files:
            visited.add(mf)
            nodes.append({
                "id": mf,
                "name": pathlib.Path(mf).name,
                "type": "modified",
                "risk": "high" if "core" in mf or "base" in mf else "medium",
            })

        # 2. Find callers / dependents
        callers = set()
        for candidate, imports in file_imports.items():
            if candidate in modified_files:
                continue
            
            for mf in modified_files:
                stem = pathlib.Path(mf).stem
                parts = mf.replace("/", ".").replace(".py", "")
                if any(stem in imp or parts in imp for imp in imports):
                    callers.add(candidate)
                    links.append({
                        "source": candidate,
                        "target": mf,
                        "kind": "imports",
                    })

        for c in callers:
            is_test = "test" in c.lower()
            nodes.append({
                "id": c,
                "name": pathlib.Path(c).name,
                "type": "test_coverage" if is_test else "consumer_risk",
                "risk": "low" if is_test else "medium",
            })

        risk_level = "LOW"
        if len(callers) > 4 or any("core" in f for f in modified_files):
            risk_level = "HIGH"
        elif len(callers) > 0 or len(modified_files) > 1:
            risk_level = "MEDIUM"

        return {
            "modified_count": len(modified_files),
            "affected_callers_count": len(callers),
            "risk_level": risk_level,
            "nodes": nodes,
            "links": links,
        }
