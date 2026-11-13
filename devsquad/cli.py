# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""DevSquad Command-Line Interface."""

import argparse
import json
import os
import pathlib
import sys
import webbrowser
from typing import List, Optional

from .core.context import RepoContextEngine
from .core.diff import DiffEngine
from .core.staging import StagingDeck
from .llm.factory import get_provider
from .runtime.relay import AutonomousRelay
from .server.server import start_studio_server


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="devsquad",
        description="DevSquad: Local-first autonomous AI engineering studio for real-world codebases.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # init
    sub.add_parser("init", help="Inspect active repository and initialize DevSquad configuration")

    # task
    p_task = sub.add_parser("task", help="Execute an autonomous feature relay (Spec -> Code -> Test -> Git Branch)")
    p_task.add_argument("goal", help="Engineering goal or feature description (e.g., 'Add JWT refresh rotation')")
    p_task.add_argument("--file", dest="target_file", help="Explicit target file to implement")
    p_task.add_argument("--test-file", dest="test_file", help="Explicit test file to verify")
    p_task.add_argument("--provider", choices=["ollama", "openai-compatible", "template"], help="Free AI provider (default: Ollama if running, else template)")
    p_task.add_argument("--model", help="Model name (e.g. qwen2.5-coder:7b)")

    # up
    p_up = sub.add_parser("up", help="Launch DevSquad Studio web interface and live virtual office")
    p_up.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    p_up.add_argument("--no-browser", action="store_true", help="Don't auto-open browser")
    p_up.add_argument("--fastapi", action="store_true", help="Launch via FastAPI & Uvicorn with WebSockets")

    # review
    p_review = sub.add_parser("review", help="Inspect staged tasks, test results, and unified diffs")
    p_review.add_argument("task_id", nargs="?", help="Specific task ID to review")

    # apply
    p_apply = sub.add_parser("apply", help="Apply staged task diffs directly to the repository")
    p_apply.add_argument("task_id", help="Task ID to apply")

    # rollback
    p_rollback = sub.add_parser("rollback", help="Rollback previously applied task from backup")
    p_rollback.add_argument("task_id", help="Task ID to rollback")

    return p


def run_init() -> int:
    root = pathlib.Path.cwd()
    engine = RepoContextEngine(root)
    meta = engine.analyze()

    print(f"\n\033[1;36m🛡️ DevSquad initialized for:\033[0m \033[1m{root.name}\033[0m")
    print(f"• Detected Languages:  {', '.join(meta.languages) or 'generic'}")
    print(f"• Total Files Scanned: {meta.total_files}")
    if meta.test_runners:
        print(f"• Active Test Harness: {' '.join(meta.test_runners[0].command)}")
    else:
        print("• Active Test Harness: None detected (defaulting to unittest)")
    if meta.rule_files:
        print(f"• Rules & Guidelines:  {', '.join(meta.rule_files)}")

    # Create .devsquad folder
    ds_dir = root / ".devsquad"
    ds_dir.mkdir(parents=True, exist_ok=True)
    cfg = ds_dir / "config.json"
    cfg.write_text(json.dumps({
        "repo_name": root.name,
        "languages": meta.languages,
        "test_command": meta.test_runners[0].command if meta.test_runners else ["pytest"],
    }, indent=2), encoding="utf-8")

    print(f"\n\033[1;32m✓ Repository ready for autonomous engineering with DevSquad!\033[0m\n")
    return 0


def run_task(args: argparse.Namespace) -> int:
    root = pathlib.Path.cwd()
    provider = get_provider(provider_type=args.provider, model=args.model)

    print(f"\n\033[1;36m🚀 DevSquad Autonomous Relay: '{args.goal}'\033[0m")
    print(f"• Provider: \033[1;33m{provider.provider_name}\033[0m ({provider.model})")
    print("-" * 65)

    def on_event(agent: str, event: str, data: dict):
        color = "\033[1;34m" if agent == "Apex" else "\033[1;36m" if agent == "Alpha" else "\033[1;32m" if agent == "Gamma" else "\033[1;33m"
        print(f"  {color}[{agent}]\033[0m {data.get('message', event)}")

    relay = AutonomousRelay(provider=provider, root=root, event_callback=on_event)
    staged = relay.run_task(
        goal=args.goal,
        target_file=args.target_file,
        test_file=args.test_file,
    )

    print("-" * 65)
    status_icon = "✅" if staged.status == "tested_green" else "⚠️"
    print(f"{status_icon} \033[1mTask {staged.task_id} completed: status={staged.status}\033[0m")
    print(f"• Git Branch: \033[1;35m{staged.git_branch}\033[0m")
    print(f"• Diffs Staged: {len(staged.diffs)} file(s)")
    for d in staged.diffs:
        print(f"  - \033[1m{d.file_path}\033[0m (+{d.additions} -{d.deletions})")

    print(f"\n\033[2mTo review and apply changes to your workspace:\033[0m")
    print(f"  \033[1mdevsquad review {staged.task_id}\033[0m  OR  \033[1mdevsquad apply {staged.task_id}\033[0m\n")
    return 0


def run_up(args: argparse.Namespace) -> int:
    root = pathlib.Path.cwd()
    port = args.port
    url = f"http://localhost:{port}"

    if getattr(args, "fastapi", False):
        try:
            import uvicorn
            from .server.fastapi_app import create_app
            app = create_app(root)
            print(f"\n\033[1;36m🛡️ DevSquad Studio (FastAPI & WebSockets) online at:\033[0m \033[4;32m{url}\033[0m")
            print(f"• Repository: \033[1m{root.name}\033[0m")
            print(f"• Real-time WebSockets, CRT Terminal, and API active.\n")
            if not args.no_browser:
                try: webbrowser.open(url)
                except Exception: pass
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
            return 0
        except ImportError:
            print("\033[1;33m⚠️ FastAPI/Uvicorn not installed. Falling back to built-in HTTP server.\033[0m")
            print("  Run \033[1mpip install 'devsquad[server]'\033[0m to enable WebSockets & FastAPI.")

    server = start_studio_server(root=root, port=port)

    print(f"\n\033[1;36m🛡️ DevSquad Studio online at:\033[0m \033[4;32m{url}\033[0m")
    print(f"• Repository: \033[1m{root.name}\033[0m")
    print(f"• Virtual Office, Review Desk, and Task Dispatcher active.\n")

    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        print("\033[2mPress Ctrl+C to stop studio.\033[0m")
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[1;33mDevSquad Studio stopped.\033[0m")
    return 0


def run_review(args: argparse.Namespace) -> int:
    staging = StagingDeck(pathlib.Path.cwd())
    if args.task_id:
        task = staging.load_task(args.task_id)
        if not task:
            print(f"\033[1;31mTask {args.task_id} not found.\033[0m")
            return 1
        tasks = [task]
    else:
        tasks = staging.list_tasks()

    if not tasks:
        print("\nNo staged tasks found. Run `devsquad task '<goal>'` first.\n")
        return 0

    print(f"\n\033[1;36m📋 DevSquad Staging Deck ({len(tasks)} tasks):\033[0m")
    for t in tasks:
        print(f"\n• \033[1m{t.task_id}\033[0m: {t.goal} [{t.status}]")
        print(f"  Branch: {t.git_branch} | Diffs: {len(t.diffs)}")
        for d in t.diffs:
            print(f"  📄 \033[1m{d.file_path}\033[0m (+{d.additions} -{d.deletions})")
            if d.patch_text:
                for line in d.patch_text.splitlines()[:15]:
                    color = "\033[32m" if line.startswith("+") else "\033[31m" if line.startswith("-") else "\033[2m"
                    print(f"     {color}{line}\033[0m")
                if len(d.patch_text.splitlines()) > 15:
                    print(f"     \033[2m... (+{len(d.patch_text.splitlines()) - 15} lines)\033[0m")

    print(f"\n\033[2mTo apply to workspace: devsquad apply <task_id>\033[0m\n")
    return 0


def run_apply(args: argparse.Namespace) -> int:
    staging = StagingDeck(pathlib.Path.cwd())
    try:
        results = staging.apply_task(args.task_id)
        print(f"\n\033[1;32m✓ Staged changes applied to codebase:\033[0m")
        for r in results:
            print(f"  • {r}")
        print(f"\n\033[2mTo rollback if needed: devsquad rollback {args.task_id}\033[0m\n")
        return 0
    except Exception as e:
        print(f"\n\033[1;31mFailed applying task {args.task_id}:\033[0m {e}\n")
        return 1


def run_rollback(args: argparse.Namespace) -> int:
    staging = StagingDeck(pathlib.Path.cwd())
    try:
        results = staging.rollback_task(args.task_id)
        print(f"\n\033[1;33m✓ Rolled back task {args.task_id}:\033[0m")
        for r in results:
            print(f"  • {r}")
        print()
        return 0
    except Exception as e:
        print(f"\n\033[1;31mRollback failed for {args.task_id}:\033[0m {e}\n")
        return 1


def main(args: Optional[List[str]] = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)

    if parsed.command == "init":
        return run_init()
    elif parsed.command == "task":
        return run_task(parsed)
    elif parsed.command == "up":
        return run_up(parsed)
    elif parsed.command == "review":
        return run_review(parsed)
    elif parsed.command == "apply":
        return run_apply(parsed)
    elif parsed.command == "rollback":
        return run_rollback(parsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
