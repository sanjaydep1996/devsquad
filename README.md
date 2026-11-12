# 🛡️ DevSquad · Autonomous AI Engineering Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/sanjaydep1996/devsquad/actions/workflows/ci.yml/badge.svg)](https://github.com/sanjaydep1996/devsquad/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen.svg)](https://sanjaydep1996.github.io/devsquad/)

> **A local-first, zero-bloat autonomous engineering studio that gives solo developers an on-demand virtual team (Architect, Coder, QA, DevOps) to build, test, and branch features on real-world codebases.**

**[▶ Open Live Interactive Demo](https://sanjaydep1996.github.io/devsquad/)** *(runs 100% in-browser with live animated agents, Review Desk, and Whiteboard)*

<p align="center">
  <img src="docs/screenshot-office.jpg" alt="DevSquad 2D Pixel Office" width="100%" />
</p>

---

## 💥 The Problem DevSquad Solves

Current AI coding tools fall into two frustrating extremes:

1. **The "Toy Project" Trap (ChatDev, MetaGPT)**: Multi-agent frameworks that simulate an entire software company, but only build trivial 200-line Python games in empty folders. They cannot read your existing 50,000-line repo, understand your database schema, or run your existing test suite.
2. **The "Destructive Overwriter" (Early Devin, OpenHands)**: Monolithic black boxes running in heavy Docker containers that directly modify your working tree without isolation, frequently introducing subtle bugs, breaking builds, and clobbering uncommitted work.

### 🌟 The DevSquad Difference
- **Operates on Your Real Repo**: DevSquad reads your existing project files, respects `.gitignore`, `CLAUDE.md`, `.cursorrules`, and detects your local test runners (`pytest`, `npm test`, `cargo test`, `go test`).
- **Zero Runtime Dependencies**: Written entirely using Python's standard library. Zero heavy Docker daemons, zero npm build steps. Boots in 1 second.
- **The "Review Desk" (Human-in-the-Loop)**: Agents **never** directly overwrite your files. All work is quarantined in a Staging Deck as clean unified diffs. You inspect the visual diff, verify real test results, and apply or rollback with a single click.
- **Interactive Whiteboard & Blast-Radius AST Analyzer**: Maps file modifications to callers, consumers, and test coverage before anything touches your branch.
- **Closed-Loop Auto-Healing**: When Gamma QA detects a failing test, it passes the failure stack trace back to Alpha to auto-heal the code before presenting the solution to you.
- **Ephemeral Git Worktree Isolation**: Background branch worktrees (`.devsquad/worktrees/<task-id>`) sandbox every run, keeping your active branch pristine.
- **100% Local & Private**: Runs on local Ollama models (`qwen2.5-coder`, `deepseek-coder`) with zero data leaving your machine.

---

## 🏢 Interactive Virtual Office & Features

<p align="center">
  <img src="docs/screenshot-inspector.jpg" alt="DevSquad Agent Inspector & Whiteboard" width="100%" />
</p>

DevSquad combines high-fidelity terminal execution with a retro **2D Pixel Office** canvas running at 60 FPS:

### 1. 🔍 Interactive Blast-Radius Visualizer (On the Office Whiteboard)
Click directly on the **Whiteboard** on the office back wall or click **Blast Radius** in the topbar to inspect AST dependencies:
- **Direct Modifications (Amber)**: Code units being added or edited.
- **Caller / Consumer Risks (Red)**: Existing files and functions in the repo that import or call the modified components.
- **Active Test Coverage (Green)**: Verified test suites guarding the callers.
- **Overall Risk Rating**: Automatically calculates `LOW`, `MEDIUM`, or `HIGH` blast-radius risk.

### 2. 🌿 Ephemeral Git Worktree Isolation
- Agents branch off `HEAD` into `.devsquad/worktrees/<task-id>` without touching unstaged working edits.
- Allows running multiple autonomous relays simultaneously without branch interference.

### 3. 🐛 Issue-to-Repro Bug Swarm
Paste a GitHub Issue, Sentry error log, or raw stack trace:
1. **Apex Lead**: Triages the error and builds a root-cause spec.
2. **Gamma QA**: Auto-generates a minimal reproduction test (`tests/test_repro.py`) proving the failure (RED).
3. **Alpha Coder**: Crafts the targeted patch.
4. **Closed-Loop Verification**: Re-runs the test until GREEN with zero regressions.

### 4. 🧠 Multi-Tool Memory Lake
- Unifies sessions, rules, and conventions across **Claude Code** (`CLAUDE.md`), **Cursor** (`.cursorrules`), and **Aider** into `.devsquad/memory.json`.
- Injects past pitfalls and rules into agent prompts so past mistakes are never repeated.

### 5. 📋 The Review Desk
- Quarantined staging deck managing all proposed changes.
- View test pass/fail banners, execution time, and syntax-colored unified diffs.
- 1-click **Apply to Workspace** (with `.devsquad.bak` backups) and **Rollback**.

---

## 👥 The Squad

DevSquad breaks engineering work across four specialized personas:

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  📐 APEX     │ ──▶ │  💻 ALPHA    │ ──▶ │  🧪 GAMMA    │ ──▶ │  🌿 DELTA    │
│  Lead        │     │  Senior      │     │  QA & Test   │     │  DevOps &    │
│  Architect   │     │  Engineer    │     │  Specialist  │     │  Release     │
│              │     │              │     │              │     │              │
│  Drafts spec │     │  Implements  │     │  Runs local  │     │  Prepares    │
│  & contracts │     │  clean code  │     │  test suite  │     │  git branch  │
└──────────────┘     └──────┬───────┘     └──────┬───────┘     └──────────────┘
                            ▲                    │
                            └──── Auto-Healer ───┘
                                  (On Test Fail)
```

1. **Apex (Lead Architect)**: Reads the repository structure, conventions, and rules. Decomposes your goal into a clean specification (`spec.md`) and contract definition.
2. **Alpha (Senior Engineer)**: Implements modular, production-ready code fulfilling Apex's spec while adhering to your codebase style.
3. **Gamma (QA Specialist)**: Writes comprehensive test suites and **executes your local test runner in a background subprocess**. If tests fail, Gamma guides Alpha through an iterative auto-healing loop.
4. **Delta (DevOps Engineer)**: Generates a dedicated git branch name (e.g. `feat/jwt-refresh-rotation`) and formats conventional commit messages.

---

## 🚀 Quickstart

DevSquad requires **Python 3.10+** and zero external packages.

```bash
# 1. Clone DevSquad
git clone https://github.com/sanjaydep1996/devsquad.git
cd devsquad

# 2. Run in any repository you are working on
python3 -m devsquad.cli init

# 3. Launch the visual DevSquad Studio
python3 -m devsquad.cli up
```

Open `http://localhost:8080` to access the **DevSquad Studio**:
- **Virtual Office**: Watch Apex, Alpha, Gamma, and Delta collaborate in real-time.
- **Task Dispatcher**: Dispatch features, refactors, or bugfixes via a single prompt.
- **The Review Desk**: Inspect side-by-side diffs, view test execution logs, and click **"Apply to Codebase"** or **"Rollback"**.
- **Interactive Whiteboard**: Click the back wall whiteboard to inspect real-time AST blast radius.

---

## 🕹️ CLI Usage

Prefer working directly in the terminal? DevSquad provides clean, intuitive CLI commands:

```bash
# 1. Initialize DevSquad in your current repo
devsquad init

# 2. Dispatch an autonomous feature relay
devsquad task "Add rate limiting middleware with unit tests"

# 3. Inspect staged diffs and test results in the terminal
devsquad review

# 4. Apply the verified staged diffs to your live workspace
devsquad apply <task_id>

# 5. Rollback anytime if needed
devsquad rollback <task_id>
```

---

## 🧪 Testing & Verification

DevSquad includes full unit test coverage across repo scanning, diff computation, task staging, AST blast-radius analysis, git worktree isolation, bug swarm, and multi-agent relay orchestration:

```bash
python3 -m unittest discover tests -v
```

---

## 🏛️ Architecture & Principles

- **[ADR 0001: Autonomous Relay Architecture & The Review Desk](docs/adr/0001-autonomous-relay-and-staging-desk.md)**
- **Local-First by Design**: Prioritizes local Ollama endpoints. Cloud keys (Anthropic / OpenAI) are optional and never required.
- **Zero Hallucinated Clobbering**: No agent writes directly to your git working tree without staged approval.

---

## 📄 License & Attribution

DevSquad is open-source software licensed under the **[MIT License](LICENSE)**.

```text
MIT License

Copyright (c) 2026 Sanjaydeep Gowrishankar

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

Created and maintained with ❤️ by **[Sanjaydeep Gowrishankar](https://github.com/sanjaydep1996)**.
