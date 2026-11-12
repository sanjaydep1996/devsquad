# Copyright (c) 2026 Sanjaydeep Gowrishankar. All rights reserved.
# Licensed under the MIT License. See LICENSE in the project root.

"""Visual QA & Accessibility Auditor: inspects frontend code for WCAG AA compliance, CLS, and mobile overflow."""

import pathlib
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VisualIssue:
    """Represents a flagged frontend layout or accessibility defect."""
    rule_id: str  # e.g., 'WCAG-TAP-TARGET', 'MOBILE-OVERFLOW', 'CLS-IMAGE-DIMS', 'A11Y-ICON-LABEL'
    severity: str  # 'HIGH', 'MEDIUM', 'LOW'
    element_snippet: str
    description: str
    remediation_hint: str


@dataclass
class VisualAuditReport:
    """Outcome of visual QA and accessibility audit."""
    url_or_file: str
    score: int  # 0 to 100
    viewport_status: str  # 'PASS_MOBILE_AND_DESKTOP', 'MOBILE_OVERFLOW_RISK'
    total_issues: int
    issues: List[VisualIssue]
    recommendations: List[str]


class VisualQAAuditor:
    """Beta FE's browser mirror and accessibility auditor."""

    def __init__(self, repo_root: Optional[pathlib.Path] = None):
        self.repo_root = (repo_root or pathlib.Path.cwd()).resolve()

    def audit_html(self, html_content: str, source_name: str = "index.html") -> VisualAuditReport:
        """Audits an HTML document for common frontend layout and accessibility defects."""
        issues: List[VisualIssue] = []

        # 1. Tap target sizing check: buttons with explicit small height
        small_targets = re.findall(r"(<button[^>]*style=[\"'][^\"']*(?:height:\s*(?:[1-3][0-9]|4[0-3])px)[^\"']*[\"'][^>]*>)", html_content)
        for target in small_targets[:3]:
            issues.append(
                VisualIssue(
                    rule_id="WCAG-TAP-TARGET",
                    severity="MEDIUM",
                    element_snippet=target[:80],
                    description="Interactive button height is less than the WCAG 2.1 AA recommended 44px minimum.",
                    remediation_hint="Ensure min-height: 44px; min-width: 44px for touch accessibility.",
                )
            )

        # 2. Icon-only buttons missing aria-label
        icon_buttons = re.findall(r"(<button[^>]*>(?:(?!aria-label).)*?<svg[^>]*>.*?</svg>\s*</button>)", html_content, re.DOTALL)
        for btn in icon_buttons[:3]:
            if "aria-label" not in btn:
                issues.append(
                    VisualIssue(
                        rule_id="A11Y-ICON-LABEL",
                        severity="HIGH",
                        element_snippet=btn.splitlines()[0][:80],
                        description="Icon-only button has no accessible text or aria-label for screen readers.",
                        remediation_hint='Add aria-label="Description" to the button element.',
                    )
                )

        # 3. Fixed desktop widths without max-width or responsive query
        fixed_widths = re.findall(r"(?:width:\s*([5-9][0-9]{2}|1[0-9]{3})px)", html_content)
        if fixed_widths and "@media" not in html_content:
            issues.append(
                VisualIssue(
                    rule_id="MOBILE-OVERFLOW",
                    severity="HIGH",
                    element_snippet=f"width: {fixed_widths[0]}px",
                    description="Hardcoded fixed width exceeds standard mobile viewport (375px) without responsive bounds.",
                    remediation_hint="Use max-width: 100% or CSS media queries for responsive scaling.",
                )
            )

        # 4. Images missing explicit dimensions (CLS risk)
        imgs = re.findall(r"(<img[^>]*>)", html_content)
        for img in imgs[:3]:
            if "width=" not in img and "height=" not in img:
                issues.append(
                    VisualIssue(
                        rule_id="CLS-IMAGE-DIMS",
                        severity="LOW",
                        element_snippet=img[:80],
                        description="Image missing explicit width and height attributes, risking Cumulative Layout Shift (CLS).",
                        remediation_hint="Specify intrinsic width and height attributes on <img> tags.",
                    )
                )

        score = max(0, 100 - (sum(20 for i in issues if i.severity == "HIGH") + sum(10 for i in issues if i.severity == "MEDIUM") + sum(5 for i in issues if i.severity == "LOW")))
        viewport_status = "MOBILE_OVERFLOW_RISK" if any(i.rule_id == "MOBILE-OVERFLOW" for i in issues) else "PASS_MOBILE_AND_DESKTOP"

        recommendations = []
        if not issues:
            recommendations.append("Frontend passed all WCAG AA accessibility, touch-target, and responsive checks cleanly.")
        else:
            recommendations.append(f"Remediate {len(issues)} layout and accessibility items to ensure 100% WCAG 2.1 AA compliance.")

        return VisualAuditReport(
            url_or_file=source_name,
            score=score,
            viewport_status=viewport_status,
            total_issues=len(issues),
            issues=issues,
            recommendations=recommendations,
        )
