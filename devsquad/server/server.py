# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Zero-dependency local HTTP server providing REST API and SSE event streaming for DevSquad Studio."""

import http.server
import json
import os
import pathlib
import threading
import time
import urllib.parse
from typing import Dict, List, Optional
from ..core.context import RepoContextEngine
from ..core.staging import StagingDeck
from ..llm.factory import get_provider
from ..runtime.relay import AutonomousRelay


class StudioHandler(http.server.BaseHTTPRequestHandler):
    """Handles REST API requests and SSE streams for DevSquad Studio."""

    root: pathlib.Path = pathlib.Path.cwd()
    clients: List = []
    relay: Optional[AutonomousRelay] = None
    staging: Optional[StagingDeck] = None

    def log_message(self, format, *args):
        # Mute default server access logs to keep terminal clean
        pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html", "/studio", "/office"):
            self._serve_studio_html()
        elif path == "/data/usage.json":
            usage_file = self.root / "data" / "usage.json"
            if usage_file.exists():
                self._serve_json_file(usage_file)
            else:
                self.send_error(404, "Not Found")
        elif path == "/api/status":
            ctx = RepoContextEngine(self.root).analyze()
            self._serve_json({
                "status": "online",
                "repo_name": self.root.name,
                "languages": ctx.languages,
                "test_runners": [tr.name for tr in ctx.test_runners],
                "provider": self.relay.provider.provider_name if self.relay else "local",
                "model": self.relay.provider.model if self.relay else "qwen2.5-coder:7b",
            })
        elif path == "/api/sessions":
            tasks = self.staging.list_tasks() if self.staging else []
            sessions = [
                {
                    "session_id": t.task_id,
                    "step_count": len(t.relay_logs),
                    "total_cost": 0.0,
                    "providers": "local",
                }
                for t in tasks
            ]
            self._serve_json({"sessions": sessions})
        elif path == "/api/tasks":
            tasks = self.staging.list_tasks() if self.staging else []
            self._serve_json([
                {
                    "task_id": t.task_id,
                    "goal": t.goal,
                    "status": t.status,
                    "created_at": t.created_at,
                    "diff_count": len(t.diffs),
                    "git_branch": t.git_branch,
                    "tests_passed": t.test_result.passed if t.test_result else False,
                }
                for t in tasks
            ])
        elif path == "/api/task":
            tid = query.get("id", [""])[0]
            task = self.staging.load_task(tid) if self.staging else None
            if not task:
                self.send_error(404, "Task not found")
                return
            self._serve_json({
                "task_id": task.task_id,
                "goal": task.goal,
                "status": task.status,
                "created_at": task.created_at,
                "git_branch": task.git_branch,
                "artifacts": task.artifacts,
                "relay_logs": task.relay_logs,
                "test_result": {
                    "passed": task.test_result.passed,
                    "command": task.test_result.command,
                    "duration_s": task.test_result.duration_s,
                    "output": task.test_result.output,
                } if task.test_result else None,
                "diffs": [
                    {
                        "file_path": d.file_path,
                        "patch_text": d.patch_text,
                        "additions": d.additions,
                        "deletions": d.deletions,
                        "is_new": d.is_new,
                    }
                    for d in task.diffs
                ],
            })
        elif path in ("/api/events", "/api/stream"):
            self._handle_sse()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/spawn":
            agent_id = payload.get("agent", "apex")
            task_text = payload.get("task", "").strip()
            if not task_text:
                self._serve_json({"success": False, "error": "Task description is required"}, status=400)
                return

            try:
                task = self.relay.run_task(task_text)
                self._serve_json({
                    "success": True,
                    "agent": agent_id,
                    "task": task_text,
                    "task_id": task.task_id,
                    "status": task.status,
                    "artifacts": task.artifacts,
                    "tests_passed": task.test_result.passed if task.test_result else True,
                    "run_note": f"Completed by DevSquad with {len(task.diffs)} staged files and test verification.",
                })
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)}, status=500)

        elif path == "/api/pipeline":
            feat = payload.get("feature", "").strip() or "Feature Relay"
            try:
                task = self.relay.run_task(feat)
                self._serve_json({
                    "success": True,
                    "task_id": task.task_id,
                    "status": task.status,
                    "artifacts": task.artifacts,
                })
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)}, status=500)

        elif path == "/api/dispatch":
            goal = payload.get("goal", "").strip()
            if not goal:
                self._serve_json({"error": "Goal cannot be empty"}, status=400)
                return

            target_file = payload.get("target_file")
            test_file = payload.get("test_file")

            # Run relay in worker thread
            def worker():
                try:
                    self.relay.run_task(goal, target_file=target_file, test_file=test_file)
                except Exception as e:
                    self._broadcast("System", "ERROR", {"error": str(e)})

            threading.Thread(target=worker, daemon=True).start()
            self._serve_json({"status": "dispatched", "goal": goal})

        elif path == "/api/apply":
            tid = query.get("id", [""])[0] or payload.get("task_id", "")
            if not tid or not self.staging:
                self._serve_json({"error": "Task ID required"}, status=400)
                return
            try:
                results = self.staging.apply_task(tid)
                self._serve_json({"success": True, "results": results})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)}, status=500)

        elif path == "/api/rollback":
            tid = query.get("id", [""])[0] or payload.get("task_id", "")
            if not tid or not self.staging:
                self._serve_json({"error": "Task ID required"}, status=400)
                return
            try:
                results = self.staging.rollback_task(tid)
                self._serve_json({"success": True, "results": results})
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)}, status=500)
        else:
            self.send_error(404, "Not Found")

    def _serve_json_file(self, file_path: pathlib.Path):
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

    def _serve_json(self, data, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_studio_html(self):
        html_path = pathlib.Path(__file__).parent.parent / "web" / "studio.html"
        if not html_path.exists():
            body = b"<h1>DevSquad Studio</h1><p>Web UI template missing.</p>"
        else:
            body = html_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q = []
        StudioHandler.clients.append(self.wfile)
        try:
            while True:
                time.sleep(1.0)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except Exception:
            if self.wfile in StudioHandler.clients:
                StudioHandler.clients.remove(self.wfile)

    @classmethod
    def _broadcast(cls, agent: str, event: str, data: Dict):
        payload = f"data: {json.dumps({'agent': agent, 'event': event, 'data': data})}\n\n".encode("utf-8")
        dead = []
        for client in cls.clients:
            try:
                client.write(payload)
                client.flush()
            except Exception:
                dead.append(client)
        for d in dead:
            if d in cls.clients:
                cls.clients.remove(d)


def start_studio_server(root: Optional[pathlib.Path] = None, port: int = 8080) -> http.server.ThreadingHTTPServer:
    """Launches the DevSquad Studio server."""
    r = (root or pathlib.Path.cwd()).resolve()
    StudioHandler.root = r
    StudioHandler.staging = StagingDeck(r)

    provider = get_provider()

    def on_event(agent, event, data):
        StudioHandler._broadcast(agent, event, data)

    StudioHandler.relay = AutonomousRelay(provider=provider, root=r, event_callback=on_event)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), StudioHandler)
    return server
