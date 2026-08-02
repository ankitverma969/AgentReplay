"""Renderers for AgentReplay security scan reports."""

from __future__ import annotations

import html
import json

from agentreplay.security.models import SecurityFinding, SecurityReport


def render_console(report: SecurityReport, *, verbose: bool = False) -> str:
    """Render a security report for terminal output."""
    lines = [
        "AgentReplay Security Report",
        f"Source: {report.source or '<memory>'}",
        f"Summary: {report.summary()}",
    ]
    if not report.findings:
        lines.append("No secrets or PII found.")
        return "\n".join(lines)
    lines.append("Findings:")
    for finding in report.findings:
        lines.append(
            "- "
            f"[{finding.risk_level}] {finding.kind} "
            f"{finding.category} at {finding.path}: {finding.suggested_fix}"
        )
        if verbose:
            lines.append(f"  rule={finding.rule_name}")
            lines.append(f"  preview={finding.to_dict()['matched_preview']}")
            lines.append(f"  redacted={finding.redacted_text}")
    return "\n".join(lines)


def render_json(report: SecurityReport) -> str:
    """Render a security report as JSON."""
    return json.dumps(report.to_dict(), sort_keys=True)


def render_markdown(report: SecurityReport, *, verbose: bool = False) -> str:
    """Render a security report as Markdown."""
    lines = [
        "# AgentReplay Security Report",
        "",
        f"**Source:** `{report.source or '<memory>'}`",
        "",
        f"**Summary:** {report.summary()}",
    ]
    if not report.findings:
        lines.extend(["", "No secrets or PII found."])
        return "\n".join(lines)
    lines.extend(["", "## Findings"])
    for finding in report.findings:
        lines.append(
            "- "
            f"`{finding.risk_level}` `{finding.kind}` `{finding.category}` "
            f"at `{finding.path}`: {finding.suggested_fix}"
        )
        if verbose:
            lines.append(f"  Rule: `{finding.rule_name}`")
            lines.append(f"  Preview: `{finding.to_dict()['matched_preview']}`")
            lines.append(f"  Redacted: `{finding.redacted_text}`")
    return "\n".join(lines)


def render_html(report: SecurityReport, *, verbose: bool = False) -> str:
    """Render a security report as dependency-free HTML."""
    if report.findings:
        findings = "\n".join(
            _html_finding(report_finding, verbose=verbose)
            for report_finding in report.findings
        )
        body = f"<section><h2>Findings</h2><ul>{findings}</ul></section>"
    else:
        body = "<section><p>No secrets or PII found.</p></section>"
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>AgentReplay Security Report</title>",
            "</head>",
            "<body>",
            "<h1>AgentReplay Security Report</h1>",
            (
                "<p><strong>Source:</strong> "
                f"{html.escape(report.source or '<memory>')}</p>"
            ),
            f"<p><strong>Summary:</strong> {html.escape(report.summary())}</p>",
            body,
            "</body>",
            "</html>",
        ]
    )


def _html_finding(report_finding: SecurityFinding, *, verbose: bool) -> str:
    finding = report_finding
    details = ""
    if verbose:
        finding_dict = finding.to_dict()
        details = (
            "<pre>"
            f"rule={html.escape(finding.rule_name)}\n"
            f"preview={html.escape(str(finding_dict['matched_preview']))}\n"
            f"redacted={html.escape(finding.redacted_text)}"
            "</pre>"
        )
    return (
        "<li>"
        f"<strong>{html.escape(finding.risk_level)}</strong> "
        f"{html.escape(finding.kind)} "
        f"{html.escape(finding.category)} at "
        f"<code>{html.escape(finding.path)}</code>: "
        f"{html.escape(finding.suggested_fix)}"
        f"{details}"
        "</li>"
    )


__all__ = ["render_console", "render_html", "render_json", "render_markdown"]
