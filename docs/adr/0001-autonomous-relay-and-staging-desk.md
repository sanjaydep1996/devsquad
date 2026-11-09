# ADR 0001: Autonomous Relay Architecture & The Review Desk

## Status
Accepted

## Context
Autonomous coding agents (e.g., OpenDevin/OpenHands, early Devin demos, ChatDev) often suffer from two failure modes:
1. **The Toy Project Sandbox**: Generating greenfield toy games in an empty directory without real-world dependencies, schemas, or existing test suites.
2. **Destructive Overwriting**: In-repo agents directly clobbering live working tree files without isolation, creating syntax errors and broken git trees.

## Decision
1. **The Autonomous Relay**: We decouple feature implementation into four specialized personas:
   - **Apex (Architect)**: Produces a structured specification and contract definitions.
   - **Alpha (Engineer)**: Writes modular implementation code respecting codebase conventions.
   - **Gamma (QA)**: Writes tests and executes the local test runner in a subprocess sandbox with an automated feedback/auto-healing loop.
   - **Delta (DevOps)**: Prepares git branch naming and conventional commits.
2. **The Staging Deck**: All agent outputs are quarantined as unified diffs in `.devsquad/staging/<task_id>/`.
3. **The Review Desk**: A visual, human-in-the-loop control deck where developers inspect side-by-side split diffs, review test pass/fail output, and apply or rollback changes with a single click.

## Consequences
- **Positive**: Zero risk of accidental codebase clobbering; verified closed-loop test execution before changes touch disk; zero third-party dependencies required.
- **Trade-off**: Requires staging manifest storage in `.devsquad/` which is git-ignored.
