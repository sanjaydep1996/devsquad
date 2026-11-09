# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Repository context engine: scans project structure, detects frameworks, test harnesses, and rules."""

import os
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


IGNORE_PATTERNS = {
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    "__pycache__", ".pytest_cache", ".idea", ".vscode", ".next",
    ".DS_Store", "target", "coverage", ".coverage"
}


@dataclass
class TestRunnerConfig:
    name: str
    command: List[str]
    config_file: Optional[str] = None


@dataclass
class RepoMetadata:
    root: pathlib.Path
    languages: List[str] = field(default_factory=list)
    test_runners: List[TestRunnerConfig] = field(default_factory=list)
    rule_files: List[str] = field(default_factory=list)
    total_files: int = 0
    key_files: List[str] = field(default_factory=list)


class RepoContextEngine:
    """Discovers repository metadata, project conventions, and active test harnesses."""

    def __init__(self, root: Optional[pathlib.Path] = None):
        self.root = (root or pathlib.Path.cwd()).resolve()

    def analyze(self) -> RepoMetadata:
        """Inspects the repository and returns detected languages, test commands, and rules."""
        meta = RepoMetadata(root=self.root)
        extensions: Set[str] = set()

        for dirpath, dirnames, filenames in os.walk(self.root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS and not d.startswith(".")]

            rel_dir = pathlib.Path(dirpath).relative_to(self.root)
            depth = len(rel_dir.parts)
            if depth > 5:
                continue

            for f in filenames:
                if f.startswith(".") and f not in (".cursorrules", ".env.example"):
                    continue

                meta.total_files += 1
                ext = pathlib.Path(f).suffix.lower()
                if ext:
                    extensions.add(ext)

                rel_file = (rel_dir / f).as_posix() if str(rel_dir) != "." else f
                if f in ("CLAUDE.md", ".cursorrules", "AGENTS.md", "CONTRIBUTING.md"):
                    meta.rule_files.append(rel_file)
                elif f in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod", "pom.xml", "Makefile"):
                    meta.key_files.append(rel_file)

        # Detect languages
        if any(e in extensions for e in (".py", ".pyw")):
            meta.languages.append("python")
        if any(e in extensions for e in (".ts", ".tsx")):
            meta.languages.append("typescript")
        if any(e in extensions for e in (".js", ".jsx", ".mjs")):
            meta.languages.append("javascript")
        if ".rs" in extensions:
            meta.languages.append("rust")
        if ".go" in extensions:
            meta.languages.append("go")
        if ".java" in extensions:
            meta.languages.append("java")

        # Detect test runners
        self._detect_test_runners(meta)
        return meta

    def _detect_test_runners(self, meta: RepoMetadata):
        # Python: pytest / unittest
        if (self.root / "pytest.ini").exists() or (self.root / "tests").exists() or (self.root / "pyproject.toml").exists():
            meta.test_runners.append(TestRunnerConfig(name="pytest", command=["pytest", "-v"]))
        elif (self.root / "test").exists():
            meta.test_runners.append(TestRunnerConfig(name="unittest", command=["python3", "-m", "unittest", "discover"]))

        # Node / JS / TS
        pkg_json = self.root / "package.json"
        if pkg_json.exists():
            meta.test_runners.append(TestRunnerConfig(name="npm-test", command=["npm", "test"], config_file="package.json"))

        # Rust
        if (self.root / "Cargo.toml").exists():
            meta.test_runners.append(TestRunnerConfig(name="cargo-test", command=["cargo", "test"], config_file="Cargo.toml"))

        # Go
        if (self.root / "go.mod").exists():
            meta.test_runners.append(TestRunnerConfig(name="go-test", command=["go", "test", "./..."], config_file="go.mod"))

    def get_file_tree(self, max_files: int = 120) -> str:
        """Returns a compact visual tree of the repository."""
        lines = []
        count = 0

        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in IGNORE_PATTERNS and not d.startswith(".")]
            rel_dir = pathlib.Path(dirpath).relative_to(self.root)
            depth = len(rel_dir.parts)
            if depth > 3:
                continue

            indent = "  " * depth
            if str(rel_dir) != ".":
                lines.append(f"{indent}📁 {rel_dir.name}/")

            for f in sorted(filenames):
                if f.startswith(".") and f not in (".cursorrules",):
                    continue
                count += 1
                if count > max_files:
                    lines.append(f"{indent}  ... ({meta_total} more files)")
                    return "\n".join(lines)
                lines.append(f"{indent}  📄 {f}")

        return "\n".join(lines)

    def read_rules_context(self) -> str:
        """Loads repository custom rules (CLAUDE.md, .cursorrules) if present."""
        rules = []
        for cand in ("CLAUDE.md", ".cursorrules", "AGENTS.md"):
            p = self.root / cand
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8")[:4000]
                    rules.append(f"--- {cand} ---\n{content}\n")
                except Exception:
                    pass
        return "\n".join(rules)
