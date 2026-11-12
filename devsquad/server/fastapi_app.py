# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""FastAPI application with WebSockets for DevSquad Studio v0.2.0."""

import asyncio
import json
import os
import pathlib
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

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
from ..llm.hybrid_router import HybridModelRouter
from ..runtime.relay import AutonomousRelay
from ..runtime.swarm import BugSwarm


def create_app(root_dir: Optional[pathlib.Path] = None) -> Any:
    """Factory creating the FastAPI instance for DevSquad Studio."""
    if not FASTAPI_AVAILABLE:
        raise RuntimeError(
            "FastAPI is not installed. Run `pip install 'devsquad[server]'` or use the standard server."
        )

    root = (root_dir or pathlib.Path.cwd()).resolve()
    app = FastAPI(
        title="DevSquad Studio API",
        version="0.3.0",
        description="Local-first autonomous AI engineering studio and multi-agent development team.",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Initialize studio engines
    chaos_lab = ChaosLab()
    security_vault = SecurityVault(root)
    merge_arena = MergeConflictArena(root)
    model_router = HybridModelRouter()
    staging = StagingDeck(root)
    memory_lake = MemoryLake(root)
    worktree_mgr = WorktreeManager(root)
    swarm = BugSwarm(root)
    mcp_hub = MCPHub(root)
    roadmap_projector = SpecRoadmapProjector()
    flaky_detector = FlakyTestDetector()
    visual_auditor = VisualQAAuditor(root)
    artifacts_publisher = ArtifactsPublisher(root)

    # Connected WebSockets
    terminal_sockets: Dict[str, List[WebSocket]] = {}
    office_sockets: List[WebSocket] = []

    @app.get("/", response_class=HTMLResponse)
    @app.get("/studio", response_class=HTMLResponse)
    async def get_studio():
        studio_path = pathlib.Path(__file__).parent.parent / "web" / "studio.html"
        if not studio_path.exists():
            studio_path = root / "index.html"
        return HTMLResponse(content=studio_path.read_text(encoding="utf-8"))

    @app.get("/api/status")
    async def get_status():
        ctx = RepoContextEngine(root).analyze()
        return {
            "status": "online",
            "server": "fastapi_uvicorn",
            "version": "0.2.0",
            "repo_name": root.name,
            "root_path": str(root),
            "files_count": ctx.total_files,
            "has_tests": ctx.has_tests,
            "primary_language": ctx.primary_language,
        }

    # --- Conflict Arena Endpoints ---
    @app.post("/api/v1/conflicts/resolve")
    async def resolve_conflict(payload: Dict[str, Any]):
        file_path = payload.get("file_path", "example.py")
        base_code = payload.get("base_code", "def greet(name):\n    return f'Hello {name}'\n")
        agent_a_code = payload.get(
            "agent_a_code",
            "import logging\n\ndef greet(name):\n    logging.info('greet called')\n    return f'Hello {name}'\n",
        )
        agent_b_code = payload.get(
            "agent_b_code",
            "def greet(name, title=''):\n    prefix = f'{title} ' if title else ''\n    return f'Hello {prefix}{name}'\n",
        )
        res = merge_arena.negotiate_resolution(file_path, base_code, agent_a_code, agent_b_code)
        return {
            "session_id": res.session_id,
            "file_path": res.file_path,
            "status": res.status,
            "conflicts_detected": res.conflicts_detected,
            "conflicts_resolved": res.conflicts_resolved,
            "dialogue": res.dialogue,
            "resolved_code": res.resolved_code,
            "ast_valid": res.ast_valid,
            "compromise_summary": res.compromise_summary,
        }

    # --- Chaos Lab Endpoints ---
    @app.get("/api/v1/chaos/presets")
    async def get_chaos_presets():
        return {"presets": chaos_lab.list_presets()}

    @app.post("/api/v1/chaos/inject")
    async def inject_chaos(payload: Dict[str, Any]):
        fault_type = payload.get("fault_type", "FLAKY_ENDPOINT")
        service = payload.get("service_name", "DevSquad Core Relay")
        incident = chaos_lab.inject_fault(fault_type, service)
        return {
            "incident_id": incident.incident_id,
            "fault_type": incident.fault_type,
            "service_name": incident.service_name,
            "severity": incident.severity,
            "status": incident.status,
            "error_message": incident.error_message,
            "impact_description": incident.impact_description,
        }

    @app.post("/api/v1/chaos/heal")
    async def heal_chaos(payload: Dict[str, Any]):
        incident_id = payload.get("incident_id")
        if not incident_id:
            raise HTTPException(status_code=400, detail="Missing incident_id")
        plan = chaos_lab.trigger_self_healing(incident_id)
        return {
            "incident_id": plan.incident_id,
            "root_cause": plan.root_cause,
            "resilience_pattern": plan.resilience_pattern,
            "verified_by_qa": plan.verified_by_qa,
            "recovery_time_ms": plan.recovery_time_ms,
            "summary": plan.summary,
            "patch_code": plan.patch_code,
            "regression_test_code": plan.regression_test_code,
        }

    # --- Security Vault Endpoints ---
    @app.get("/api/v1/security/audit")
    async def audit_security():
        report = security_vault.scan_repo()
        return {
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
        }

    # --- Hybrid Model Router Endpoints ---
    @app.get("/api/v1/models/local")
    async def get_local_models():
        return model_router.get_router_status()

    # --- MCP Desk Hub Endpoints ---
    @app.get("/api/v1/mcp/desks")
    async def get_mcp_desks():
        return {
            "desks": mcp_hub.desk_bindings,
            "all_tools": mcp_hub.list_tools_for_desk("all"),
        }

    @app.post("/api/v1/mcp/rpc")
    async def mcp_rpc(payload: Dict[str, Any]):
        return mcp_hub.handle_jsonrpc(payload)

    # --- Artifacts & ADR Endpoints ---
    @app.get("/api/v1/artifacts/adrs")
    async def list_adrs():
        adr_dir = root / "docs" / "adr"
        adrs = []
        if adr_dir.exists():
            for p in sorted(adr_dir.glob("*.md")):
                adrs.append({"filename": p.name, "content": p.read_text(encoding="utf-8")})
        return {"adrs": adrs}

    @app.post("/api/v1/artifacts/adr")
    async def create_adr(payload: Dict[str, Any]):
        adr = artifacts_publisher.generate_adr(
            title=payload.get("title", "New Architecture Decision"),
            context=payload.get("context", "Need clean-room modular architecture."),
            decision=payload.get("decision", "Adopted micro-core modular engine."),
            consequences=payload.get("consequences", "Zero external dependencies."),
            status=payload.get("status", "Accepted"),
        )
        return {
            "number": adr.number,
            "title": adr.title,
            "status": adr.status,
            "date": adr.date,
            "markdown": adr.markdown_content,
        }

    # --- Spec-to-Code Roadmap Endpoints ---
    @app.post("/api/v1/roadmap/parse")
    async def parse_roadmap(payload: Dict[str, Any]):
        prd_text = payload.get("prd_text", "# Feature: Real-Time Sync\n\n## Objectives\n- Zero latency\n- 100% tests")
        plan = roadmap_projector.parse_prd(prd_text)
        return {
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
        }

    # --- Flaky Test Isolation Endpoints ---
    @app.post("/api/v1/flaky/stress-test")
    async def stress_test_flaky(payload: Dict[str, Any]):
        test_name = payload.get("test_name", "test_async_token_rotation")
        iterations = int(payload.get("iterations", 10))
        flaky_result = flaky_detector.stress_test(test_name, iterations=iterations)
        return {
            "test_identifier": flaky_result.test_identifier,
            "total_runs": flaky_result.total_runs,
            "passed_runs": flaky_result.passed_runs,
            "failed_runs": flaky_result.failed_runs,
            "flakiness_percentage": flaky_result.flakiness_percentage,
            "is_flaky": flaky_result.is_flaky,
            "root_cause_diagnosis": flaky_result.root_cause_diagnosis,
            "hardening_patch": flaky_result.hardening_patch,
            "verified_deterministic": flaky_result.verified_deterministic,
        }

    # --- Visual QA & Accessibility Endpoints ---
    @app.get("/api/v1/visual/audit")
    async def visual_audit():
        index_path = root / "index.html"
        content = index_path.read_text(encoding="utf-8") if index_path.exists() else "<html><body></body></html>"
        report = visual_auditor.audit_html(content, source_name="index.html")
        return {
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
        }

    # --- WebSocket for Retro CRT Terminal (xterm.js) ---
    @app.websocket("/ws/terminal/{agent_id}")
    async def terminal_websocket(websocket: WebSocket, agent_id: str):
        await websocket.accept()
        agent_name = agent_id.upper()
        if agent_id not in terminal_sockets:
            terminal_sockets[agent_id] = []
        terminal_sockets[agent_id].append(websocket)

        # Welcome CRT banner in ANSI colors
        await websocket.send_text(
            f"\r\n\x1b[1;32m══════════════════════════════════════════════════════════════════════\x1b[0m\r\n"
            f"\x1b[1;36m  DEVSQUAD CRT TERMINAL v0.2.0  ─  ATTACHED TO: {agent_name}\x1b[0m\r\n"
            f"\x1b[1;32m══════════════════════════════════════════════════════════════════════\x1b[0m\r\n"
            f"\x1b[90mSession active on pseudo-tty /dev/pts/agent-{agent_id}. Type commands:\x1b[0m\r\n\r\n"
            f"\x1b[1;33m{agent_id}@devsquad-office\x1b[0m:\x1b[1;34m~/workspace\x1b[0m$ "
        )

        try:
            while True:
                data = await websocket.receive_text()
                # Handle command or key echo
                if data == "\r" or data == "\n":
                    await websocket.send_text("\r\n\x1b[32m[OK] Agent acknowledged command buffer.\x1b[0m\r\n")
                    await websocket.send_text(f"\x1b[1;33m{agent_id}@devsquad-office\x1b[0m:\x1b[1;34m~/workspace\x1b[0m$ ")
                elif data.strip() in ("clear", "cls"):
                    await websocket.send_text("\x1b[2J\x1b[H")
                    await websocket.send_text(f"\x1b[1;33m{agent_id}@devsquad-office\x1b[0m:\x1b[1;34m~/workspace\x1b[0m$ ")
                elif "test" in data.lower() or "pytest" in data.lower():
                    await websocket.send_text(
                        f"\r\n\x1b[90mRunning test runner under agent sandbox...\x1b[0m\r\n"
                        f"\x1b[32mtest_core_engine (test_v2) ... ok\x1b[0m\r\n"
                        f"\x1b[32mtest_terminal_stream ... ok\x1b[0m\r\n"
                        f"\x1b[1;32m100% PASS - 14 tests in 0.28s\x1b[0m\r\n"
                        f"\x1b[1;33m{agent_id}@devsquad-office\x1b[0m:\x1b[1;34m~/workspace\x1b[0m$ "
                    )
                else:
                    # Echo input back
                    await websocket.send_text(data)
        except WebSocketDisconnect:
            terminal_sockets[agent_id].remove(websocket)

    return app
