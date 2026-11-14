# Changelog

All notable changes to DevSquad are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-11-13

### Added
- **Workshop** panel in the studio with five tabs: Task board, Plan then build, New app, DevOps desk and Setup.
- **Task board** (`devsquad/core/taskboard.py`): cards as Markdown files in `.devsquad/tasks/`, four columns, Assign to squad, and read-only GitHub Issues import through `gh`.
- **Plan, then build** (`devsquad/core/planner.py`): editable plans with owners, risks and questions; approval adds cards to the board.
- **Greenfield bootstrapper** (`devsquad/core/bootstrapper.py`): one sentence becomes a FastAPI + SQLite app with login, a web page, tests, README and ADR, staged and copied only into an empty folder.
- **DevOps desk** (`devsquad/core/devops_desk.py`): Dockerfile, compose, CI, Cloud Run, Kubernetes and `.env.example` drafted from what the project actually uses.
- **First-run setup** (`devsquad/core/setup_check.py`): checks for Ollama, models, git and pytest, with model downloads.
- **PDF and image reading** (`devsquad/core/doc_reader.py`): PDF text extraction with the standard library; image descriptions from a local vision model.
- `/api/v5/` routes shared by the standard and FastAPI servers (`devsquad/server/v5_api.py`), behind the same local-only guard.

- **Walk into the 3D office**: view presets (Overview, Desks, Meeting room, Lounge, Window, Walk in), turn and zoom buttons, zoom toward the pointer, right-drag to move, double-click to go to a spot or see a person's face, and keyboard controls (W A S D, Q E, + -, 1-6, R), with a help card.
- **Session Replay of relay runs**: `/api/replay` replays a run step by step from the flight recorder, or from its log for older runs. Replay returned 404 before.
- **Realistic, rigged people** in the 3D office: eight Microsoft Rocketbox avatars (MIT, notice in `devsquad/web/models/people/`) converted to glTF, with recorded walk, sit, typing, talk, listen, present, coffee and phone motion. You can pick your look in Settings. The drawn people remain the fallback.
- **Task board on the office wall**: the Workshop board drawn as sticky notes; a card moving to In progress sends its owner to the board and back to their desk. New **Board** view (key 7).
- **Desk card**: click a desk or a person for their card, next card, last run, ETA and blockers (`POST /api/v5/desk/<id>`).
- **Know-how: field guides** (`devsquad/knowledge/*.md`, `devsquad/core/knowledge.py`): fundamentals and decision rules in eight fields, Research included. Agents look up what fits each task, decide from it and name the guide: in the run log, `decisions.md`, plans and desk cards. Projects can add their own in `.devsquad/knowledge/`. New Workshop tab and `/api/v5/knowledge` routes.
- **Reef tank** in the 3D office, beside the server rack: two clownfish at their anemone and two blue tangs.
- **Your own people**: a model in `.devsquad/people/` (kept out of git) replaces the shipped one with the same name.
- **Export as Markdown or PDF**: plans, run replays and post-mortems (`GET /api/v5/export/<plan|replay|postmortem>/<id>.<md|pdf>`), with a standard-library PDF writer (`devsquad/core/export.py`).

### Changed
- **More realistic people**: one smooth head shape with eyes that blink, eyelids, brows, nose, ears and mouth; hair that follows a real hairline; shaped torso, hands and shoes; fabric and skin materials; weight shifts and a hip sway when walking.
- **People don't walk through or circle each other**: walkers keep to their right and slow down behind someone going the same way. Name tags no longer pile up.
- **You walk the floor**: checking in at desks, watching whoever is on a real task, coffee, whiteboard, window and sofa, and leading meetings from the head of the table.
- **DEVSQUAD sign** is now light letters on a dark panel, readable by day and by night.
- **Panels**: content is never squashed (the Roadmap's Mermaid graph was cut to one line); Review Desk, Settings and Visual QA fit on phones; Escape closes every panel.
- **Tidier topbar**: the everyday actions stay in view and 16 other tools are grouped under Build, Quality and Tools menus (keyboard friendly). At 1280 to 1440 px the topbar is two rows instead of four or five, and on phones it is one row that scrolls sideways, so the office gets the space.
- **README screenshots** now show the current 3D office (night and day) and the Workshop board.
- **Flight Recorder shows real runs only**: pick a run, scrub its recorded steps and write its post-mortem from the record. The sample timeline and the made-up post-mortem are gone.
- **Flaky tests are real**: the runner now runs your test command repeatedly with a different hash seed per run and reports actual results. The old simulation is kept only as a deprecated function that says it ran nothing.

## [0.1.0] - 2026-11-09

### Added
- **Core Staging & Unified Diff Engine** (`devsquad/core/`):
  - In-repo context scanner detecting languages, project files, and test runners (`pytest`, `npm test`, `cargo test`, `go test`).
  - Unified diff generation with atomic patch application and one-click rollback from `.devsquad.bak`.
  - Staging Deck managing quarantined task manifests in `.devsquad/staging/`.
- **Specialized Multi-Agent Swarm** (`devsquad/agents/`):
  - **Apex**: Lead Architect generating contract specifications (`spec.md`).
  - **Alpha**: Senior Engineer implementing clean, modular code.
  - **Gamma**: QA Specialist generating tests and running the test runner in a subprocess.
  - **Delta**: DevOps Specialist preparing git branches and conventional commits.
- **Closed-Loop Auto-Healing Relay** (`devsquad/runtime/`):
  - Autonomous pipeline relaying tasks from Spec ➔ Code ➔ Test ➔ Git Branch.
  - Automated test diagnosis: on failure, test tracebacks loop back to Alpha for up to 3 self-healing iterations until tests are green.
- **Local-First Model Layer** (`devsquad/llm/`):
  - Zero-dependency stdlib networking for Ollama (local default), OpenAI-compatible, Anthropic, and Template fallbacks.
- **DevSquad Studio & Review Desk** (`devsquad/server/`, `devsquad/web/`):
  - Zero-dependency local web server on port 8080 with Server-Sent Events (SSE).
  - Retro-modern virtual office canvas showing Apex, Alpha, Gamma, and Delta working in real-time.
  - The Review Desk: visual split diff viewer, test runner output logs, and 1-click apply/rollback.
- **CLI Commands** (`devsquad/cli.py`):
  - `devsquad init`: Scans repository and creates `.devsquad/config.json`.
  - `devsquad task "<goal>"`: Dispatches full autonomous relay in the terminal.
  - `devsquad up`: Launches the interactive Studio web workspace.
  - `devsquad review [task_id]`: Terminal diff inspector.
  - `devsquad apply <task_id>`: Applies verified diffs to codebase.
  - `devsquad rollback <task_id>`: Restores working tree.
