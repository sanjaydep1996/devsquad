# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""DevOps Desk: Docker, CI, .env.example and deploy files, worked out from the project itself.

No AI is involved, so the output is the same every time and works in template mode. Files are
staged in .devsquad/devops/ for review, and applying them never overwrites a file unless asked.
"""

import json
import pathlib
import re
import shutil
from typing import Any, Dict, List, Optional

SKIP_DIRS = {".git", ".devsquad", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache", "site-packages"}
ENV_PATTERNS = [
    re.compile(r"""os\.getenv\(\s*["']([A-Z][A-Z0-9_]*)["']\s*(?:,\s*(?P<d>["'][^"']*["']|[\w.\-]+))?"""),
    re.compile(r"""os\.environ\.get\(\s*["']([A-Z][A-Z0-9_]*)["']\s*(?:,\s*(?P<d>["'][^"']*["']|[\w.\-]+))?"""),
    re.compile(r"""os\.environ\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]"""),
    re.compile(r"""process\.env\.([A-Z][A-Z0-9_]*)"""),
    re.compile(r"""process\.env\[\s*["']([A-Z][A-Z0-9_]*)["']\s*\]"""),
]
SECRET_WORDS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "PASS", "PRIVATE", "CREDENTIAL", "DSN", "DATABASE_URL")
# Variables the platform sets, which don't belong in .env.example
PLATFORM_VARS = {"HOME", "PATH", "USER", "PWD", "SHELL", "TERM", "LANG", "TMPDIR", "CI", "NODE_ENV", "PYTHONPATH"}


class DevOpsDesk:
    def __init__(self, root: Optional[pathlib.Path] = None):
        self.root = (root or pathlib.Path.cwd()).resolve()
        self.stage = self.root / ".devsquad" / "devops"

    def _files(self, suffixes: tuple) -> List[pathlib.Path]:
        found = []
        for p in self.root.rglob("*"):
            if len(found) > 4000:
                break
            if p.is_file() and p.suffix in suffixes and not (set(p.relative_to(self.root).parts[:-1]) & SKIP_DIRS):
                found.append(p)
        return found

    def _read(self, rel: str) -> str:
        p = self.root / rel
        try:
            return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        except OSError:
            return ""

    # ----- what the project is -----
    def analyze(self) -> Dict[str, Any]:
        pyproject, requirements, package = self._read("pyproject.toml"), self._read("requirements.txt"), self._read("package.json")
        deps = (pyproject + requirements).lower()
        py_files = self._files((".py",))
        info: Dict[str, Any] = {"language": "unknown", "python_version": "3.12", "port": 8000, "dependency_files": []}
        for f in ("requirements.txt", "pyproject.toml", "package.json", "package-lock.json"):
            if (self.root / f).is_file():
                info["dependency_files"].append(f)

        if package and not (pyproject or requirements):
            try:
                pkg = json.loads(package)
            except json.JSONDecodeError:
                pkg = {}
            scripts = pkg.get("scripts") or {}
            info.update(language="node", test_command="npm test" if "test" in scripts else "",
                        start_command="npm start" if "start" in scripts else "node index.js",
                        build_command="npm run build" if "build" in scripts else "", port=3000,
                        lockfile=(self.root / "package-lock.json").is_file())
        elif pyproject or requirements or py_files:
            uses_pytest = "pytest" in deps or any("import pytest" in self._read(str(p.relative_to(self.root))) for p in py_files[:300])
            app = self._find_python_app(py_files)
            m = re.search(r'requires-python\s*=\s*"[>=~]*\s*(3\.\d+)', pyproject)
            info.update(language="python", python_version=m.group(1) if m and m.group(1) >= "3.10" else "3.12",
                        test_command="python -m pytest -q" if uses_pytest else "python -m unittest discover -s tests -v",
                        test_runner="pytest" if uses_pytest else "unittest", **app)
        info["env_vars"] = self.env_vars()
        return info

    def _find_python_app(self, py_files: List[pathlib.Path]) -> Dict[str, Any]:
        for p in py_files[:400]:
            text = self._read(str(p.relative_to(self.root)))
            m = re.search(r"^(\w+)\s*=\s*FastAPI\(", text, re.M)
            if m:
                module = ".".join(p.relative_to(self.root).with_suffix("").parts)
                return {"framework": "fastapi", "start_command": f"uvicorn {module}:{m.group(1)} --host 0.0.0.0 --port 8000"}
            m = re.search(r"^(\w+)\s*=\s*Flask\(", text, re.M)
            if m:
                module = ".".join(p.relative_to(self.root).with_suffix("").parts)
                return {"framework": "flask", "start_command": f"gunicorn {module}:{m.group(1)} --bind 0.0.0.0:8000"}
        if (self.root / "manage.py").is_file():
            return {"framework": "django", "start_command": "python manage.py runserver 0.0.0.0:8000"}
        main = next((p for p in py_files if p.name in ("main.py", "app.py", "__main__.py")), None)
        return {"framework": "python", "start_command": f"python {main.relative_to(self.root).as_posix()}" if main else "python -m app"}

    def env_vars(self) -> List[Dict[str, Any]]:
        """Every environment variable the code reads, with its default and where it's used."""
        found: Dict[str, Dict[str, Any]] = {}
        for p in self._files((".py", ".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx")):
            rel = p.relative_to(self.root).as_posix()
            for pattern in ENV_PATTERNS:
                for m in pattern.finditer(self._read(rel)):
                    name = m.group(1)
                    if name in PLATFORM_VARS:
                        continue
                    entry = found.setdefault(name, {"name": name, "default": None, "files": [], "secret": any(w in name for w in SECRET_WORDS)})
                    default = m.groupdict().get("d")
                    if default and entry["default"] is None:
                        entry["default"] = default.strip("\"'")
                    if rel not in entry["files"]:
                        entry["files"].append(rel)
        return sorted(found.values(), key=lambda e: e["name"])

    # ----- the files -----
    def generate(self) -> Dict[str, Any]:
        info = self.analyze()
        files: Dict[str, str] = {}
        if info["language"] in ("python", "node"):
            files["Dockerfile"] = self._dockerfile(info)
            files[".dockerignore"] = ".git\n.devsquad\n__pycache__\n*.pyc\n.venv\nvenv\nnode_modules\n.env\n.pytest_cache\ndist\nbuild\n"
            files["docker-compose.yml"] = self._compose(info)
            files[".github/workflows/ci.yml"] = self._ci(info)
            files["deploy/cloudrun.yaml"] = self._cloudrun(info)
            files["deploy/k8s.yaml"] = self._k8s(info)
        files[".env.example"] = self._env_example(info["env_vars"])
        if self.stage.exists():
            shutil.rmtree(self.stage)
        for rel, content in files.items():
            target = self.stage / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        note = "" if info["language"] in ("python", "node") else (
            "No Python or Node project found here (no requirements.txt, pyproject.toml, package.json or .py files), "
            "so only .env.example was made. Docker, CI and deploy files need to know how the app runs.")
        return {"analysis": info, "note": note, "files": [{"path": rel, "content": content, "exists": (self.root / rel).exists()} for rel, content in files.items()]}

    def apply(self, paths: List[str], overwrite: bool = False) -> Dict[str, List[str]]:
        written, skipped = [], []
        for rel in paths:
            source = (self.stage / rel).resolve()
            if not source.is_file() or not source.is_relative_to(self.stage.resolve()):
                skipped.append(rel)
                continue
            target = self.root / source.relative_to(self.stage.resolve())
            if target.exists() and not overwrite:
                skipped.append(rel)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            written.append(rel)
        return {"written": written, "skipped": skipped}

    def _env_example(self, env: List[Dict[str, Any]]) -> str:
        if not env:
            return "# No environment variables were found in the code.\n"
        lines = ["# Environment variables this project reads. Copy to .env and fill in real values.", "# Never commit .env.", ""]
        for e in env:
            lines.append(f"# Used in: {', '.join(e['files'][:3])}{' and more' if len(e['files']) > 3 else ''}")
            if e["secret"]:
                lines.append("# Secret: set a real value, and keep it out of git.")
            lines.append(f"{e['name']}={'' if e['secret'] or e['default'] is None else e['default']}")
            lines.append("")
        return "\n".join(lines)

    def _dockerfile(self, info: Dict[str, Any]) -> str:
        if info["language"] == "node":
            install = "npm ci" if info.get("lockfile") else "npm install"
            build = f"RUN {info['build_command']}\n" if info.get("build_command") else ""
            return f"""# Built by DevSquad's DevOps Desk. Review before use.
FROM node:22-slim AS build
WORKDIR /app
COPY package*.json ./
RUN {install}
COPY . .
{build}
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app /app
USER node
EXPOSE {info['port']}
CMD [{', '.join(json.dumps(x) for x in info['start_command'].split())}]
"""
        deps = "COPY requirements.txt ./\nRUN pip install --no-cache-dir --prefix=/install -r requirements.txt" if "requirements.txt" in info["dependency_files"] \
            else "COPY pyproject.toml ./\nCOPY . .\nRUN pip install --no-cache-dir --prefix=/install ."
        return f"""# Built by DevSquad's DevOps Desk. Review before use.
FROM python:{info['python_version']}-slim AS build
WORKDIR /app
{deps}

FROM python:{info['python_version']}-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=build /install /usr/local
COPY . .
RUN useradd --create-home appuser
USER appuser
EXPOSE {info['port']}
CMD [{', '.join(json.dumps(x) for x in info['start_command'].split())}]
"""

    def _compose(self, info: Dict[str, Any]) -> str:
        env = "\n    env_file:\n      - .env" if info["env_vars"] else ""
        return f"""# Built by DevSquad's DevOps Desk. Review before use.
services:
  app:
    build: .
    ports:
      - "{info['port']}:{info['port']}"{env}
    restart: unless-stopped
"""

    def _ci(self, info: Dict[str, Any]) -> str:
        if info["language"] == "node":
            setup = """      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: npm
      - run: npm ci"""
            test = info.get("test_command") or "echo 'No test script in package.json'"
        else:
            install = "pip install -r requirements.txt" if "requirements.txt" in info["dependency_files"] else "pip install -e ."
            extra = " pytest" if info.get("test_runner") == "pytest" else ""
            setup = f"""      - uses: actions/setup-python@v5
        with:
          python-version: "{info['python_version']}"
          cache: pip
      - run: python -m pip install --upgrade pip && {install}{' && pip install' + extra if extra else ''}"""
            test = info["test_command"]
        return f"""# Built by DevSquad's DevOps Desk. Review before use.
name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
{setup}
      - run: {test}
  docker:
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4
      - run: docker build -t app:${{{{ github.sha }}}} .
"""

    def _cloudrun(self, info: Dict[str, Any]) -> str:
        return f"""# Built by DevSquad's DevOps Desk. Review before use.
# Deploy with: gcloud run services replace deploy/cloudrun.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: app
spec:
  template:
    spec:
      containers:
        - image: REGION-docker.pkg.dev/PROJECT/REPO/app:latest
          ports:
            - containerPort: {info['port']}
          resources:
            limits:
              cpu: "1"
              memory: 512Mi
"""

    def _k8s(self, info: Dict[str, Any]) -> str:
        return f"""# Built by DevSquad's DevOps Desk. Review before use.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  replicas: 2
  selector:
    matchLabels: {{app: app}}
  template:
    metadata:
      labels: {{app: app}}
    spec:
      containers:
        - name: app
          image: app:latest
          ports:
            - containerPort: {info['port']}
          readinessProbe:
            tcpSocket: {{port: {info['port']}}}
          resources:
            requests: {{cpu: 100m, memory: 128Mi}}
            limits: {{cpu: 500m, memory: 512Mi}}
---
apiVersion: v1
kind: Service
metadata:
  name: app
spec:
  selector: {{app: app}}
  ports:
    - port: 80
      targetPort: {info['port']}
"""
