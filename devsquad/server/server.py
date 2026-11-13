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
from .guard import is_local_host, origin_is_this_server
from ..core.files import MAX_FILE_BYTES, FileRejected, ProjectFiles
from ..core.status import StatusBoard, StatusReporter
from ..core.artifacts import ArtifactsPublisher
from ..core.blast_radius import BlastRadiusAnalyzer
from ..core.chaos import ChaosLab
from ..core.context import RepoContextEngine
from ..core.flaky_detector import FlakyTestDetector
from ..core.mcp_hub import MCPHub
from ..core.memory import MemoryLake
from ..core.merge_arena import MergeConflictArena
from ..core.roadmap import SpecRoadmapProjector
from ..core.security_vault import SecurityVault
from ..core.staging import StagingDeck
from ..core.visual_qa import VisualQAAuditor
from ..core.worktree import WorktreeManager
from ..llm.factory import get_provider
from ..llm.hybrid_router import HybridModelRouter
from ..runtime.relay import AutonomousRelay
from ..runtime.swarm import BugSwarm


class StudioHandler(http.server.BaseHTTPRequestHandler):
    """Handles REST API requests and SSE streams for DevSquad Studio."""

    root: pathlib.Path = pathlib.Path.cwd()
    clients: List = []
    clients_lock: threading.Lock = threading.Lock()
    relay: Optional[AutonomousRelay] = None
    staging: Optional[StagingDeck] = None
    board: StatusBoard = StatusBoard()
    chaos_lab: ChaosLab = ChaosLab()
    model_router: HybridModelRouter = HybridModelRouter()
    mcp_hub: MCPHub = MCPHub()
    roadmap_projector: SpecRoadmapProjector = SpecRoadmapProjector()
    flaky_detector: FlakyTestDetector = FlakyTestDetector()
    visual_auditor: VisualQAAuditor = VisualQAAuditor()
    artifacts_publisher: ArtifactsPublisher = ArtifactsPublisher()

    def log_message(self, format, *args):
        # Mute default server access logs to keep terminal clean
        pass

    def do_HEAD(self):
        if self._refuse_outsiders(changes_state=False):
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def _refuse_outsiders(self, changes_state: bool) -> bool:
        """Sends a 403 and returns True unless the request comes from the studio's own page or a local tool."""
        ok = is_local_host(self.headers.get("Host"))
        if ok and changes_state:
            ok = origin_is_this_server(self.headers.get("Origin"), self.server.server_address[1])
        if not ok:
            self.send_error(403, "DevSquad Studio only answers to its own local page")
        return not ok

    def do_GET(self):
        if self._refuse_outsiders(changes_state=False):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/files":
            self._serve_json({"files": ProjectFiles(self.root).list()})
        elif path.startswith("/api/files/"):
            self._download_file(urllib.parse.unquote(path[len("/api/files/"):]))
        elif path in ("/", "/index.html", "/studio", "/office"):
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
        elif path == "/api/worktrees":
            mgr = WorktreeManager(self.root)
            self._serve_json(mgr.list_worktrees())
        elif path == "/api/memory":
            lake = MemoryLake(self.root)
            self._serve_json(lake.data)
        elif path == "/api/blast-radius":
            tid = query.get("task_id", [""])[0]
            files = [f.strip() for f in query.get("files", [""])[0].split(",") if f.strip()]
            if tid and self.staging:
                t = self.staging.load_task(tid)
                if t:
                    files = [d.file_path for d in t.diffs]
            if not files:
                files = ["devsquad/server/server.py"]
            analyzer = BlastRadiusAnalyzer(self.root)
            self._serve_json(analyzer.analyze(files))
        elif path == "/api/v1/chaos/presets":
            self._serve_json({"presets": self.chaos_lab.list_presets()})
        elif path == "/api/v1/security/audit":
            report = SecurityVault(self.root).scan_repo()
            self._serve_json({
                "status": report.status,
                "security_score": report.security_score,
                "files_scanned": report.files_scanned,
                "total_vulnerabilities": report.total_vulnerabilities,
                "critical_count": report.critical_count,
                "high_count": report.high_count,
                "medium_count": report.medium_count,
                "low_count": report.low_count,
                "vulnerabilities": report.vulnerabilities,
                "recommendations": report.recommendations,
            })
        elif path == "/api/v1/models/local":
            self._serve_json(self.model_router.get_router_status())
        elif path == "/api/v1/mcp/desks":
            self._serve_json({
                "desks": self.mcp_hub.desk_bindings,
                "all_tools": self.mcp_hub.list_tools_for_desk("all"),
            })
        elif path == "/api/v1/artifacts/adrs":
            adr_dir = self.root / "docs" / "adr"
            adrs = []
            if adr_dir.exists():
                for p in sorted(adr_dir.glob("*.md")):
                    adrs.append({"filename": p.name, "content": p.read_text(encoding="utf-8")})
            self._serve_json({"adrs": adrs})
        elif path == "/api/v1/visual/audit":
            index_path = self.root / "index.html"
            content = index_path.read_text(encoding="utf-8") if index_path.exists() else "<html><body></body></html>"
            report = self.visual_auditor.audit_html(content, source_name="index.html")
            self._serve_json({
                "url_or_file": report.url_or_file,
                "score": report.score,
                "viewport_status": report.viewport_status,
                "total_issues": report.total_issues,
                "issues": [
                    {
                        "rule_id": i.rule_id,
                        "severity": i.severity,
                        "element_snippet": i.element_snippet,
                        "description": i.description,
                        "remediation_hint": i.remediation_hint,
                    }
                    for i in report.issues
                ],
                "recommendations": report.recommendations,
            })
        elif path in ("/api/events", "/api/stream"):
            self._handle_sse()
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        if self._refuse_outsiders(changes_state=True):
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        if path == "/api/files":
            # Uploads are raw bytes, so they're handled before the body is read as JSON
            self._upload_file((query.get("name") or [""])[0], content_length)
            return
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/ask":
            # A status question gets an answer from recorded facts; anything else comes back as not answered
            reporter = StatusReporter(
                self.staging or StagingDeck(self.root), self.board,
                provider_name=self.relay.provider.provider_name if self.relay else "",
                model=self.relay.provider.model if self.relay else "",
            )
            names = payload.get("names") if isinstance(payload.get("names"), dict) else {}
            report = reporter.answer(str(payload.get("question", "")), selected=payload.get("selected"), names={k: str(v) for k, v in names.items()})
            self._serve_json(report or {"answered": False})
            return

        if path == "/api/spawn":
            if not self.relay:
                self._serve_json({"success": False, "error": "Relay engine is not initialized"}, status=503)
                return
            agent_id = payload.get("agent", "apex")
            task_text = payload.get("task", "").strip()
            if not task_text:
                self._serve_json({"success": False, "error": "Task description is required"}, status=400)
                return

            try:
                reference = ProjectFiles(self.root).context_for(payload.get("files") or [])
                try:
                    task = self.relay.run_task(task_text, reference=reference)
                finally:
                    self.board.finish()   # also when the run fails, so nobody is left "working" forever
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
            if not self.relay:
                self._serve_json({"success": False, "error": "Relay engine is not initialized"}, status=503)
                return
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
            if not self.relay:
                self._serve_json({"error": "Relay engine is not initialized"}, status=503)
                return
            goal = payload.get("goal", "").strip()
            if not goal:
                self._serve_json({"error": "Goal cannot be empty"}, status=400)
                return

            target_file = payload.get("target_file")
            test_file = payload.get("test_file")

            # Run relay in worker thread
            def worker():
                try:
                    if self.relay:
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

        elif path == "/api/memory/ingest":
            lake = MemoryLake(self.root)
            results = lake.ingest_all()
            self._serve_json({"success": True, "results": results, "data": lake.data})

        elif path == "/api/bug-swarm":
            title = payload.get("title", "").strip() or "Reported Issue"
            trace = payload.get("trace", "").strip()
            tf = payload.get("target_file")
            provider = self.relay.provider if self.relay else get_provider()
            swarm = BugSwarm(provider, self.root)
            try:
                task = swarm.run_swarm(title, trace, target_file=tf)
                self._serve_json({
                    "success": True,
                    "task_id": task.task_id,
                    "status": task.status,
                    "artifacts": task.artifacts,
                    "diff_count": len(task.diffs),
                    "tests_passed": task.test_result.passed if task.test_result else False,
                })
            except Exception as e:
                self._serve_json({"success": False, "error": str(e)}, status=500)

        elif path == "/api/v1/conflicts/resolve":
            arena = MergeConflictArena(self.root)
            fp = payload.get("file_path", "example.py")
            base = payload.get("base_code", "def greet(name):\n    return f'Hello {name}'\n")
            a_code = payload.get("agent_a_code", "import logging\n\ndef greet(name):\n    logging.info('greet called')\n    return f'Hello {name}'\n")
            b_code = payload.get("agent_b_code", "def greet(name, title=''):\n    prefix = f'{title} ' if title else ''\n    return f'Hello {prefix}{name}'\n")
            res = arena.negotiate_resolution(fp, base, a_code, b_code)
            self._serve_json({
                "session_id": res.session_id,
                "file_path": res.file_path,
                "status": res.status,
                "conflicts_detected": res.conflicts_detected,
                "conflicts_resolved": res.conflicts_resolved,
                "dialogue": res.dialogue,
                "resolved_code": res.resolved_code,
                "ast_valid": res.ast_valid,
                "compromise_summary": res.compromise_summary,
            })

        elif path == "/api/v1/chaos/inject":
            fault = payload.get("fault_type", "FLAKY_ENDPOINT")
            service = payload.get("service_name", "DevSquad Core Relay")
            incident = self.chaos_lab.inject_fault(fault, service)
            self._serve_json({
                "incident_id": incident.incident_id,
                "fault_type": incident.fault_type,
                "service_name": incident.service_name,
                "severity": incident.severity,
                "status": incident.status,
                "error_message": incident.error_message,
                "impact_description": incident.impact_description,
            })

        elif path == "/api/v1/chaos/heal":
            inc_id = payload.get("incident_id", "")
            try:
                plan = self.chaos_lab.trigger_self_healing(inc_id)
                self._serve_json({
                    "incident_id": plan.incident_id,
                    "root_cause": plan.root_cause,
                    "resilience_pattern": plan.resilience_pattern,
                    "verified_by_qa": plan.verified_by_qa,
                    "recovery_time_ms": plan.recovery_time_ms,
                    "summary": plan.summary,
                    "patch_code": plan.patch_code,
                    "regression_test_code": plan.regression_test_code,
                })
            except Exception as e:
                self._serve_json({"error": str(e)}, status=400)

        elif path == "/api/v1/artifacts/adr":
            title = payload.get("title", "New Architecture Decision")
            ctx = payload.get("context", "Need clean-room modular architecture.")
            dec = payload.get("decision", "Adopted micro-core modular engine.")
            cons = payload.get("consequences", "Zero external dependencies.")
            status = payload.get("status", "Accepted")
            adr = self.artifacts_publisher.generate_adr(title, ctx, dec, cons, status=status)
            self._serve_json({
                "number": adr.number,
                "title": adr.title,
                "status": adr.status,
                "date": adr.date,
                "markdown": adr.markdown_content,
            })

        elif path == "/api/v1/mcp/rpc":
            res = self.mcp_hub.handle_jsonrpc(payload)
            self._serve_json(res)

        elif path == "/api/v1/roadmap/parse":
            prd_text = payload.get("prd_text", "# Feature: Real-Time Sync\n\n## Objectives\n- Zero latency\n- 100% tests")
            plan = self.roadmap_projector.parse_prd(prd_text)
            self._serve_json({
                "project_title": plan.project_title,
                "objectives": plan.objectives,
                "tasks": [
                    {
                        "task_id": t.task_id,
                        "title": t.title,
                        "assigned_agent": t.assigned_agent,
                        "role_description": t.role_description,
                        "dependencies": t.dependencies,
                        "estimated_tokens": t.estimated_tokens,
                        "status": t.status,
                    }
                    for t in plan.tasks
                ],
                "mermaid_dag": plan.mermaid_dag,
                "execution_order": plan.execution_order,
                "total_estimated_tokens": plan.total_estimated_tokens,
            })

        elif path == "/api/v1/flaky/stress-test":
            test_name = payload.get("test_name", "test_async_token_rotation")
            iterations = int(payload.get("iterations", 10))
            flaky_result = self.flaky_detector.stress_test(test_name, iterations=iterations)
            self._serve_json({
                "test_identifier": flaky_result.test_identifier,
                "total_runs": flaky_result.total_runs,
                "passed_runs": flaky_result.passed_runs,
                "failed_runs": flaky_result.failed_runs,
                "flakiness_percentage": flaky_result.flakiness_percentage,
                "is_flaky": flaky_result.is_flaky,
                "root_cause_diagnosis": flaky_result.root_cause_diagnosis,
                "hardening_patch": flaky_result.hardening_patch,
                "verified_deterministic": flaky_result.verified_deterministic,
            })
        else:
            self.send_error(404, "Not Found")

    def do_DELETE(self):
        if self._refuse_outsiders(changes_state=True):
            return
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/files/") and ProjectFiles(self.root).delete(urllib.parse.unquote(path[len("/api/files/"):])):
            self._serve_json({"success": True})
        else:
            self.send_error(404, "Not Found")

    def _upload_file(self, name: str, content_length: int):
        if content_length > MAX_FILE_BYTES:
            self._serve_json({"error": f"That file is over the {MAX_FILE_BYTES // (1024 * 1024)} MB limit."}, status=413)
            return
        try:
            info = ProjectFiles(self.root).save(name, self.rfile.read(content_length))
        except FileRejected as e:
            self._serve_json({"error": str(e)}, status=400)
            return
        self._serve_json({"success": True, "file": info})

    def _download_file(self, name: str):
        data = ProjectFiles(self.root).read(name)
        if data is None:
            self.send_error(404, "Not Found")
            return
        safe = ProjectFiles.safe_name(name)
        self.send_response(200)
        # Always a download, never a page: an uploaded .html file must not run on the studio's own address
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(safe)}")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_json_file(self, file_path: pathlib.Path):
        try:
            content = file_path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, str(e))

    def _serve_json(self, data, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
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
        self.end_headers()

        with StudioHandler.clients_lock:
            StudioHandler.clients.append(self.wfile)
        try:
            while True:
                time.sleep(1.0)
                self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except Exception:
            with StudioHandler.clients_lock:
                if self.wfile in StudioHandler.clients:
                    StudioHandler.clients.remove(self.wfile)

    @classmethod
    def _broadcast(cls, agent: str, event: str, data: Dict):
        payload = f"data: {json.dumps({'agent': agent, 'event': event, 'data': data})}\n\n".encode("utf-8")
        with cls.clients_lock:
            clients_copy = list(cls.clients)
        dead = []
        for client in clients_copy:
            try:
                client.write(payload)
                client.flush()
            except Exception:
                dead.append(client)
        if dead:
            with cls.clients_lock:
                for d in dead:
                    if d in cls.clients:
                        cls.clients.remove(d)


def start_studio_server(root: Optional[pathlib.Path] = None, port: int = 8080) -> http.server.ThreadingHTTPServer:
    """Launches the DevSquad Studio server."""
    r = (root or pathlib.Path.cwd()).resolve()
    StudioHandler.root = r
    StudioHandler.staging = StagingDeck(r)

    provider = get_provider()

    StudioHandler.board = StatusBoard()

    def on_event(agent, event, data):
        if event == "STAGED":
            StudioHandler.board.finish()
        else:
            StudioHandler.board.record(agent, event, data)
        StudioHandler._broadcast(agent, event, data)

    StudioHandler.relay = AutonomousRelay(provider=provider, root=r, event_callback=on_event)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), StudioHandler)
    return server
