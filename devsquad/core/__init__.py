# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""DevSquad core engine modules."""

from .context import RepoContextEngine, RepoMetadata
from .diff import DiffEngine, FileDiff
from .runner import SandboxRunner, TestRunResult
from .staging import StagingDeck, StagedTask
from .merge_arena import MergeConflictArena, ConflictHunk, NegotiationResult
from .chaos import ChaosLab, ChaosIncident, HealingPlan
from .security_vault import SecurityVault, SecurityVulnerability, VaultAuditReport
from .artifacts import ArtifactsPublisher, ADRDocument
from .mcp_hub import MCPHub, MCPToolDefinition
from .roadmap import SpecRoadmapProjector, RoadmapPlan, RoadmapTask
from .flaky_detector import FlakyTestDetector, FlakyTestResult
from .visual_qa import VisualQAAuditor, VisualAuditReport, VisualIssue
from .ai_discovery import AIDiscoveryEngine
from .flight_recorder import FlightRecorder, FlightEvent
from .git_bisect import AutonomousBisect

__all__ = [
    "RepoContextEngine",
    "RepoMetadata",
    "DiffEngine",
    "FileDiff",
    "SandboxRunner",
    "TestRunResult",
    "StagingDeck",
    "StagedTask",
    "MergeConflictArena",
    "ConflictHunk",
    "NegotiationResult",
    "ChaosLab",
    "ChaosIncident",
    "HealingPlan",
    "SecurityVault",
    "SecurityVulnerability",
    "VaultAuditReport",
    "ArtifactsPublisher",
    "ADRDocument",
    "MCPHub",
    "MCPToolDefinition",
    "SpecRoadmapProjector",
    "RoadmapPlan",
    "RoadmapTask",
    "FlakyTestDetector",
    "FlakyTestResult",
    "VisualQAAuditor",
    "VisualAuditReport",
    "VisualIssue",
    "AIDiscoveryEngine",
    "FlightRecorder",
    "FlightEvent",
    "AutonomousBisect",
]
