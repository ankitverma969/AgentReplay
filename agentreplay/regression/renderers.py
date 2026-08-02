"""Renderers for AgentReplay regression analysis reports."""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Mapping

from agentreplay.config import get_settings
from agentreplay.regression.models import RegressionFinding, RegressionReport
from agentreplay.security import SecurityEngine
from agentreplay.security.config import security_config_from_settings
from agentreplay.types import JSONValue


def render_summary(report: RegressionReport) -> str:
    """Render a compact regression summary."""
    counts = report.summary_counts
    return "\n".join(
        [
            report.summary(),
            (
                "Severity: "
                + ", ".join(
                    f"{severity}={count}"
                    for severity, count in sorted(counts.by_severity.items())
                )
                if counts.by_severity
                else "Severity: none"
            ),
            (
                "Impact: "
                f"time={report.impact.execution_time_ms:.3f}ms, "
                f"cost={report.impact.cost:.6f}, "
                f"tokens={report.impact.tokens}, "
                f"reliability={report.impact.reliability:.3f}"
            ),
        ]
    )


def render_console(report: RegressionReport) -> str:
    """Render a readable console report."""
    lines = [
        "AgentReplay Regression Analysis",
        f"Runs: {report.baseline_run_id} -> {report.target_run_id}",
        f"Summary: {report.summary()}",
        "Impact:",
        f"- Execution time: {report.impact.execution_time_ms:.3f} ms",
        f"- Cost: {report.impact.cost:.6f}",
        f"- Tokens: {report.impact.tokens}",
        f"- Reliability: {report.impact.reliability:.3f}",
    ]
    if report.findings:
        lines.append("Findings:")
        lines.extend(_console_finding(finding) for finding in report.findings)
    if report.recommendations:
        lines.append("Recommendations:")
        lines.extend(f"- {recommendation}" for recommendation in report.recommendations)
    return "\n".join(lines)


def render_json(report: RegressionReport) -> str:
    """Render a machine-readable JSON report."""
    security = SecurityEngine(security_config_from_settings(get_settings()))
    return json.dumps(security.sanitize(report.to_dict()), sort_keys=True)


def render_markdown(report: RegressionReport) -> str:
    """Render a Markdown regression report."""
    lines = [
        "# AgentReplay Regression Analysis",
        "",
        f"**Runs:** `{report.baseline_run_id}` -> `{report.target_run_id}`",
        "",
        f"**Summary:** {report.summary()}",
        "",
        "## Impact",
        "",
        f"- Execution time: `{report.impact.execution_time_ms:.3f} ms`",
        f"- Cost: `{report.impact.cost:.6f}`",
        f"- Tokens: `{report.impact.tokens}`",
        f"- Failure rate: `{report.impact.failure_rate:.6f}`",
        f"- Reliability: `{report.impact.reliability:.3f}`",
    ]
    if report.findings:
        lines.extend(["", "## Findings"])
        for finding in report.findings:
            lines.extend(
                [
                    "",
                    f"### {finding.title}",
                    "",
                    f"- Kind: `{finding.kind}`",
                    f"- Category: `{finding.category}`",
                    f"- Severity: `{finding.severity}`",
                    f"- Location: `{finding.location}`",
                    f"- Likely cause: {finding.root_cause.likely_cause}",
                    f"- Confidence: `{finding.root_cause.confidence:.2f}`",
                ]
            )
    if report.recommendations:
        lines.extend(["", "## Recommendations"])
        lines.extend(f"- {recommendation}" for recommendation in report.recommendations)
    return "\n".join(lines)


def render_html(report: RegressionReport) -> str:
    """Render a dependency-free HTML regression report."""
    finding_items = "\n".join(_html_finding(finding) for finding in report.findings)
    recommendations = "\n".join(
        f"<li>{html.escape(item)}</li>" for item in report.recommendations
    )
    metrics = "\n".join(
        "<tr>"
        f"<td>{html.escape(metric.name)}</td>"
        f"<td>{metric.baseline:.3f}</td>"
        f"<td>{metric.target:.3f}</td>"
        f"<td>{metric.delta:.3f}</td>"
        f"<td>{metric.percent_change:.1%}</td>"
        "</tr>"
        for metric in report.metric_deltas
    )
    graph = html.escape(render_graph(report))
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>AgentReplay Regression Analysis</title>",
            "<style>",
            _css(),
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<h1>AgentReplay Regression Analysis</h1>",
            (
                f"<p><strong>Runs:</strong> {html.escape(report.baseline_run_id)} "
                f"&rarr; {html.escape(report.target_run_id)}</p>"
            ),
            f"<p>{html.escape(report.summary())}</p>",
            "<section><h2>Impact</h2>",
            "<ul>",
            f"<li>Execution time: {report.impact.execution_time_ms:.3f} ms</li>",
            f"<li>Cost: {report.impact.cost:.6f}</li>",
            f"<li>Tokens: {report.impact.tokens}</li>",
            f"<li>Failure rate: {report.impact.failure_rate:.6f}</li>",
            f"<li>Reliability: {report.impact.reliability:.3f}</li>",
            "</ul></section>",
            "<section><h2>Metric Deltas</h2>",
            "<table><thead><tr><th>Metric</th><th>Baseline</th><th>Target</th>"
            "<th>Delta</th><th>%</th></tr></thead>",
            f"<tbody>{metrics}</tbody></table></section>",
            f"<section><h2>Findings</h2><ul>{finding_items}</ul></section>",
            f"<section><h2>Recommendations</h2><ul>{recommendations}</ul></section>",
            f"<section><h2>Execution Graph Diff</h2><pre>{graph}</pre></section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def render_csv(report: RegressionReport) -> str:
    """Render findings as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "finding_id",
            "kind",
            "category",
            "severity",
            "title",
            "location",
            "likely_cause",
            "confidence",
        ]
    )
    for finding in report.findings:
        writer.writerow(
            [
                finding.finding_id,
                finding.kind,
                finding.category,
                finding.severity,
                finding.title,
                finding.location,
                finding.root_cause.likely_cause,
                f"{finding.root_cause.confidence:.3f}",
            ]
        )
    return output.getvalue()


def render_graph(report: RegressionReport) -> str:
    """Render graph-oriented JSON data."""
    return json.dumps(
        {
            "baseline_run_id": report.baseline_run_id,
            "target_run_id": report.target_run_id,
            "execution_graph_diff": report.visualizations.execution_graph_diff,
            "regression_timeline": report.visualizations.regression_timeline,
            "tool_comparison": report.visualizations.tool_comparison,
            "model_comparison": report.visualizations.model_comparison,
        },
        sort_keys=True,
    )


def _console_finding(finding: RegressionFinding) -> str:
    """Render one console finding."""
    return (
        f"- [{finding.severity}] {finding.kind}/{finding.category} "
        f"{finding.title} at {finding.location}: "
        f"{finding.root_cause.likely_cause} "
        f"(confidence={finding.root_cause.confidence:.2f})"
    )


def _html_finding(finding: RegressionFinding) -> str:
    """Render one HTML finding."""
    return (
        "<li>"
        f"<strong>{html.escape(finding.severity)}</strong> "
        f"{html.escape(finding.kind)} / {html.escape(finding.category)}: "
        f"{html.escape(finding.title)} "
        f"<code>{html.escape(finding.location)}</code>"
        f"<p>{html.escape(finding.root_cause.likely_cause)}</p>"
        f"<p>Confidence: {finding.root_cause.confidence:.2f}</p>"
        "</li>"
    )


def _css() -> str:
    """Return small embedded CSS for standalone reports."""
    return """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:0;
background:#f8fafc;color:#111827}
main{max-width:1100px;margin:0 auto;padding:32px}
h1,h2{color:#0f172a}
section{margin:24px 0}
table{border-collapse:collapse;width:100%;background:white}
th,td{border:1px solid #d1d5db;padding:8px;text-align:left}
li{margin:8px 0}
code,pre{background:#e5e7eb;padding:2px 4px;border-radius:4px}
pre{overflow:auto;padding:12px}
""".strip()


def _json_safe(value: object) -> JSONValue:
    """Convert arbitrary values into JSON-compatible data."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return str(value)


__all__ = [
    "render_console",
    "render_csv",
    "render_graph",
    "render_html",
    "render_json",
    "render_markdown",
    "render_summary",
]
