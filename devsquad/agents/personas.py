# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Specialized DevSquad agent personas: Apex, Alpha, Gamma, and Delta."""

import re
from typing import Dict, List, Optional
from .base import BaseAgent
from ..llm.base import BaseProvider


def extract_code_block(text: str, default_ext: str = "py") -> str:
    """Extracts code block content from markdown if present."""
    match = re.search(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


class ApexLead(BaseAgent):
    """Apex: Lead Architect & Systems Engineer."""

    def __init__(self, provider: BaseProvider):
        system_prompt = (
            "You are Apex, the Lead Architect in DevSquad. "
            "Your role is to analyze repository context, enforce architectural consistency, "
            "and create a clear, actionable specification for features and bugfixes. "
            "Always output a structured markdown spec defining: Objectives, File Changes (which files to create/edit), "
            "Interface Contracts, and Verification Criteria."
        )
        super().__init__(name="Apex", role="Lead Architect", system_prompt=system_prompt, provider=provider)

    def plan(self, goal: str, context_summary: str, rules_context: str) -> str:
        prompt = (
            f"GOAL: {goal}\n\n"
            f"REPOSITORY CONTEXT:\n{context_summary}\n\n"
            f"REPOSITORY RULES:\n{rules_context}\n\n"
            "Create the architectural specification for this task. Detail the target files and design decisions."
        )
        resp = self.think_and_act(prompt, max_tokens=1500)
        return resp.text


class AlphaCoder(BaseAgent):
    """Alpha: Senior Full-Stack Engineer."""

    def __init__(self, provider: BaseProvider):
        system_prompt = (
            "You are Alpha, the Senior Software Engineer in DevSquad. "
            "Your role is to write clean, maintainable, modular production code that satisfies Apex's spec. "
            "Always follow existing codebase conventions. Output complete, working file implementations "
            "wrapped in markdown code blocks."
        )
        super().__init__(name="Alpha", role="Senior Engineer", system_prompt=system_prompt, provider=provider)

    def implement(self, goal: str, spec: str, file_path: str, existing_content: Optional[str] = None) -> str:
        prompt = (
            f"GOAL: {goal}\n\n"
            f"SPECIFICATION:\n{spec}\n\n"
            f"TARGET FILE: {file_path}\n"
        )
        if existing_content:
            prompt += f"\nEXISTING FILE CONTENT:\n```\n{existing_content}\n```\n"
        prompt += "\nProvide the complete code for this file. Return ONLY the code in a ``` block."

        resp = self.think_and_act(prompt, max_tokens=2500)
        return extract_code_block(resp.text)

    def auto_heal(self, file_path: str, current_code: str, test_failure_trace: str) -> str:
        """Fixes code based on failing test traceback from Gamma."""
        prompt = (
            f"AUTO-HEAL REQUEST FOR FILE: {file_path}\n\n"
            f"CURRENT CODE:\n```\n{current_code}\n```\n\n"
            f"TEST FAILURE TRACEBACK FROM GAMMA QA:\n```\n{test_failure_trace}\n```\n\n"
            "Analyze the failure cause and fix the code to make tests pass. "
            "Return the corrected complete file code inside a ``` block."
        )
        resp = self.think_and_act(prompt, max_tokens=2500)
        return extract_code_block(resp.text)


class GammaQA(BaseAgent):
    """Gamma: QA & Verification Specialist."""

    def __init__(self, provider: BaseProvider):
        system_prompt = (
            "You are Gamma, the QA & Verification Specialist in DevSquad. "
            "Your job is to ensure zero regressions by writing comprehensive unit and integration tests. "
            "You test edge cases, error conditions, and happy paths. Output runnable test files."
        )
        super().__init__(name="Gamma", role="QA & Verification", system_prompt=system_prompt, provider=provider)

    def write_tests(self, goal: str, spec: str, code_under_test: str, test_file_path: str) -> str:
        prompt = (
            f"GOAL: {goal}\n\n"
            f"SPECIFICATION:\n{spec}\n\n"
            f"CODE UNDER TEST:\n```\n{code_under_test}\n```\n\n"
            f"TARGET TEST FILE: {test_file_path}\n\n"
            "Write comprehensive tests verifying this feature. Return the test code inside a ``` block."
        )
        resp = self.think_and_act(prompt, max_tokens=2000)
        return extract_code_block(resp.text)


class DeltaDevOps(BaseAgent):
    """Delta: DevOps & Release Engineer."""

    def __init__(self, provider: BaseProvider):
        system_prompt = (
            "You are Delta, the DevOps & Git Specialist in DevSquad. "
            "Your job is to prepare clean git branches, write conventional commit messages, "
            "and craft clear PR summaries."
        )
        super().__init__(name="Delta", role="DevOps & Release", system_prompt=system_prompt, provider=provider)

    def prepare_git_metadata(self, goal: str, modified_files: List[str]) -> Dict[str, str]:
        prompt = (
            f"GOAL: {goal}\n"
            f"MODIFIED FILES: {', '.join(modified_files)}\n\n"
            "Suggest:\n"
            "1. Git branch name (e.g. feat/add-jwt-rotation)\n"
            "2. Conventional commit message (e.g. feat(auth): add jwt refresh rotation with tests)\n"
            "3. One-line PR summary"
        )
        resp = self.think_and_act(prompt, max_tokens=500)
        lines = [l.strip() for l in resp.text.splitlines() if l.strip()]

        branch = "feat/devsquad-patch"
        commit = f"feat: {goal}"
        summary = goal

        for line in lines:
            if "branch:" in line.lower() or line.startswith("feat/"):
                clean = re.sub(r".*branch:?\s*", "", line, flags=re.IGNORECASE).strip("` ")
                if "/" in clean:
                    branch = clean
            elif "commit:" in line.lower():
                commit = re.sub(r".*commit:?\s*", "", line, flags=re.IGNORECASE).strip("` ")

        return {
            "branch": branch,
            "commit_message": commit,
            "summary": summary,
        }
