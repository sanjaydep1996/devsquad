# Changelog

All notable changes to DevSquad are documented in this file.
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
