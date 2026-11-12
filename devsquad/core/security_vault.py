# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Security Vault: Zeta's pentest hub, secret leak prevention, and automated code vulnerability scanner."""

import os
import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SecurityVulnerability:
    """Represents a flagged security risk in source code or configuration."""
    rule_id: str
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    category: str  # 'SECRET_LEAK', 'XSS_SINK', 'COMMAND_INJECTION', 'PATH_TRAVERSAL', 'INSECURE_CONFIG'
    file_path: str
    line_number: int
    matched_snippet: str
    description: str
    remediation_hint: str
    suggested_patch: Optional[str] = None


@dataclass
class VaultAuditReport:
    """Comprehensive repository security assessment report."""
    status: str  # 'SECURE', 'WARNING', 'LOCKDOWN'
    security_score: int  # 0 to 100
    files_scanned: int
    total_vulnerabilities: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    vulnerabilities: List[Dict[str, Any]]
    recommendations: List[str]


class SecurityVault:
    """Zeta's Cyber Bunker: scans staged code and repository files for security vulnerabilities."""

    SECRET_PATTERNS = [
        ("SEC-001", "CRITICAL", "OpenAI API Key", r"sk-[a-zA-Z0-9]{32,}", "Store in environment variable or secrets manager."),
        ("SEC-002", "CRITICAL", "Anthropic API Key", r"sk-ant-[a-zA-Z0-9_\-]{32,}", "Do not commit API tokens to client bundles or git."),
        ("SEC-003", "CRITICAL", "GitHub Personal Access Token", r"gh[pousr]_[a-zA-Z0-9]{36,}", "Revoke token immediately and use GITHUB_TOKEN in CI."),
        ("SEC-004", "CRITICAL", "AWS Access Key ID", r"AKIA[0-9A-Z]{16}", "Use IAM roles or AWS SSM Parameter Store."),
        ("SEC-005", "CRITICAL", "Private Key Header", r"-----BEGIN (?:RSA|OPENSSH|EC|DSA)? PRIVATE KEY-----", "Private keys must never be committed."),
    ]

    CODE_VULN_PATTERNS = [
        ("VULN-XSS-1", "HIGH", "XSS_SINK", r"\.innerHTML\s*=", "Unsafe DOM sink. Use .textContent or sanitize with DOMPurify.", "element.textContent = safeValue;"),
        ("VULN-XSS-2", "HIGH", "XSS_SINK", r"dangerouslySetInnerHTML\s*=", "React unsafe HTML sink. Sanitize input before rendering.", "<div dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(content) }} />"),
        ("VULN-XSS-3", "HIGH", "XSS_SINK", r"eval\(", "Direct eval() execution allows arbitrary code injection.", "JSON.parse(data) or structured parser"),
        ("VULN-CMD-1", "CRITICAL", "COMMAND_INJECTION", r"subprocess\.(?:run|Popen|call)\([^)]*shell\s*=\s*True", "Shell execution with shell=True invites command injection.", "subprocess.run([binary, *args], shell=False)"),
        ("VULN-SQL-1", "HIGH", "COMMAND_INJECTION", r"(?:SELECT|INSERT|UPDATE|DELETE)[^;]*%s|f\"(?:SELECT|INSERT|UPDATE|DELETE)", "Unparameterized SQL string formatting. Use parameterized queries.", "cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))"),
        ("VULN-PATH-1", "HIGH", "PATH_TRAVERSAL", r"(?:\.\./|\.\.\\)", "Relative path traversal pattern detected in file routing.", "pathlib.Path(p).resolve() with strict prefix checking"),
    ]

    def __init__(self, repo_root: Optional[pathlib.Path] = None):
        self.repo_root = (repo_root or pathlib.Path.cwd()).resolve()

    def scan_code(self, code: str, file_name: str = "snippet.py") -> List[SecurityVulnerability]:
        """Scans a single string of code for secrets and vulnerabilities."""
        vulns: List[SecurityVulnerability] = []
        lines = code.splitlines()

        for idx, line in enumerate(lines, start=1):
            # Check secret leaks
            for rule_id, severity, label, pattern, hint in self.SECRET_PATTERNS:
                if re.search(pattern, line):
                    # Mask the matched token for security
                    masked = re.sub(pattern, "[REDACTED_SECRET]", line.strip())
                    vulns.append(
                        SecurityVulnerability(
                            rule_id=rule_id,
                            severity=severity,
                            category="SECRET_LEAK",
                            file_path=file_name,
                            line_number=idx,
                            matched_snippet=masked,
                            description=f"Hardcoded {label} detected in source.",
                            remediation_hint=hint,
                        )
                    )

            # Check code vulnerabilities
            for rule_id, severity, category, pattern, desc, patch in self.CODE_VULN_PATTERNS:
                if re.search(pattern, line):
                    vulns.append(
                        SecurityVulnerability(
                            rule_id=rule_id,
                            severity=severity,
                            category=category,
                            file_path=file_name,
                            line_number=idx,
                            matched_snippet=line.strip()[:120],
                            description=desc,
                            remediation_hint=f"Refactor to safe pattern: {patch}",
                            suggested_patch=patch,
                        )
                    )

        return vulns

    def scan_repo(self, target_files: Optional[List[str]] = None) -> VaultAuditReport:
        """Audits the entire repository or a subset of staged files."""
        all_vulns: List[SecurityVulnerability] = []
        scanned_count = 0

        if target_files:
            file_paths = [self.repo_root / f for f in target_files]
        else:
            file_paths = []
            for ext in ("*.py", "*.html", "*.js", "*.ts", "*.json", "*.env*"):
                for p in self.repo_root.rglob(ext):
                    parts = p.parts
                    if any(part in (".git", ".devsquad", "__pycache__", "venv", ".venv", "node_modules", "dist") for part in parts):
                        continue
                    file_paths.append(p)

        for p in file_paths:
            if not p.is_file():
                continue
            scanned_count += 1
            try:
                rel_path = str(p.relative_to(self.repo_root))
                content = p.read_text(encoding="utf-8", errors="ignore")
                file_vulns = self.scan_code(content, file_name=rel_path)
                all_vulns.extend(file_vulns)
            except Exception:
                continue

        crit = sum(1 for v in all_vulns if v.severity == "CRITICAL")
        high = sum(1 for v in all_vulns if v.severity == "HIGH")
        med = sum(1 for v in all_vulns if v.severity == "MEDIUM")
        low = sum(1 for v in all_vulns if v.severity == "LOW")

        score = max(0, 100 - (crit * 30 + high * 15 + med * 5 + low * 2))
        status = "CRITICAL_LOCKDOWN" if crit > 0 else ("WARNING" if high > 0 else "SECURE")

        recommendations = []
        if crit > 0:
            recommendations.append(f"URGENT: Found {crit} critical issues (secret leaks or shell injections). Vault lockdown active.")
        if high > 0:
            recommendations.append(f"Sanitize {high} high-severity DOM sinks or unparameterized queries.")
        if not all_vulns:
            recommendations.append("All repository files passed Zeta's Pentest & Secret Guard with zero vulnerabilities.")

        return VaultAuditReport(
            status=status,
            security_score=score,
            files_scanned=scanned_count,
            total_vulnerabilities=len(all_vulns),
            critical_count=crit,
            high_count=high,
            medium_count=med,
            low_count=low,
            vulnerabilities=[
                {
                    "rule_id": v.rule_id,
                    "severity": v.severity,
                    "category": v.category,
                    "file_path": v.file_path,
                    "line_number": v.line_number,
                    "matched_snippet": v.matched_snippet,
                    "description": v.description,
                    "remediation_hint": v.remediation_hint,
                    "suggested_patch": v.suggested_patch,
                }
                for v in all_vulns
            ],
            recommendations=recommendations,
        )
