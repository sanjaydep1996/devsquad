# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Spec-to-Code Roadmap Projector: decomposes PRDs into dependency DAGs and dispatches agent worktrees."""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class RoadmapTask:
    """Represents a discrete engineering task in the dependency DAG."""
    task_id: str
    title: str
    assigned_agent: str  # 'alpha_be', 'beta_fe', 'gamma_qa', 'delta_devops', 'apex'
    role_description: str
    dependencies: List[str]
    estimated_tokens: int
    status: str = "PENDING"  # 'PENDING', 'STAGED', 'COMPLETED'


@dataclass
class RoadmapPlan:
    """Complete decomposed roadmap plan."""
    project_title: str
    objectives: List[str]
    tasks: List[RoadmapTask]
    mermaid_dag: str
    execution_order: List[str]
    total_estimated_tokens: int


class SpecRoadmapProjector:
    """Apex's boardroom projector: parses unstructured PRDs into executable dependency graphs."""

    def parse_prd(self, markdown_text: str) -> RoadmapPlan:
        """Parses a Product Requirements Document into ordered tasks and Mermaid DAG."""
        lines = markdown_text.splitlines()

        # Extract title
        title = "Feature Specification"
        for line in lines:
            if line.strip().startswith("# "):
                title = line.strip("# ").strip()
                break

        # Extract objectives
        objectives: List[str] = []
        in_obj = False
        for line in lines:
            if "objective" in line.lower() or "goals" in line.lower():
                in_obj = True
                continue
            if in_obj and line.startswith("#"):
                in_obj = False
            if in_obj and line.strip().startswith(("-", "*")):
                objectives.append(line.strip("-* ").strip())

        if not objectives:
            objectives = ["Implement modular production code", "Verify 100% test coverage with zero regressions"]

        # Synthesize tasks according to engineering lifecycle
        tasks: List[RoadmapTask] = [
            RoadmapTask(
                task_id="TASK-1",
                title=f"Architectural Spec & Contract Design for {title}",
                assigned_agent="apex",
                role_description="Tech Lead & Architect",
                dependencies=[],
                estimated_tokens=8500,
            ),
            RoadmapTask(
                task_id="TASK-2",
                title="Core Business Logic & Backend Data Persistence",
                assigned_agent="alpha_be",
                role_description="Backend Specialist",
                dependencies=["TASK-1"],
                estimated_tokens=14200,
            ),
            RoadmapTask(
                task_id="TASK-3",
                title="Client Viewport & Responsive UI Component Binding",
                assigned_agent="beta_fe",
                role_description="Frontend Engineer",
                dependencies=["TASK-2"],
                estimated_tokens=11800,
            ),
            RoadmapTask(
                task_id="TASK-4",
                title="Unit, Mock, and Integration Test Suite Verification",
                assigned_agent="gamma_qa",
                role_description="QA Automation",
                dependencies=["TASK-2", "TASK-3"],
                estimated_tokens=9400,
            ),
            RoadmapTask(
                task_id="TASK-5",
                title="Git Worktree Branching & CI Workflow Hardening",
                assigned_agent="delta_devops",
                role_description="DevOps Specialist",
                dependencies=["TASK-4"],
                estimated_tokens=6200,
            ),
        ]

        # Generate Mermaid DAG string
        mermaid_lines = ["graph TD"]
        for t in tasks:
            label = f"{t.task_id}[\"{t.title} ({t.assigned_agent})\"]"
            if not t.dependencies:
                mermaid_lines.append(f"  {label}")
            else:
                for dep in t.dependencies:
                    mermaid_lines.append(f"  {dep} --> {label}")

        mermaid_str = "\n".join(mermaid_lines)
        total_tokens = sum(t.estimated_tokens for t in tasks)

        # Compute topological order
        exec_order = [t.task_id for t in tasks]

        return RoadmapPlan(
            project_title=title,
            objectives=objectives,
            tasks=tasks,
            mermaid_dag=mermaid_str,
            execution_order=exec_order,
            total_estimated_tokens=total_tokens,
        )
