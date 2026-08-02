"""Report renderers for AgentReplay execution diffs."""

from __future__ import annotations

import html
import json

from agentreplay.diff.models import DiffChange, DiffResult


def render_summary(result: DiffResult) -> str:
    """Render a compact summary report."""
    return result.summary()


def render_json(result: DiffResult) -> str:
    """Render a machine-readable JSON report."""
    return json.dumps(result.to_dict(), sort_keys=True)


def render_console(result: DiffResult, *, verbose: bool = False) -> str:
    """Render a readable console report."""
    lines = [
        "AgentReplay Diff",
        f"Runs: {result.left_run_id} -> {result.right_run_id}",
        f"Summary: {result.summary()}",
    ]
    if result.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in result.warnings)
    if not result.changes:
        return "\n".join(lines)

    lines.append("Changes:")
    for change in result.changes:
        lines.append(_console_change(change, verbose=verbose))
    return "\n".join(lines)


def render_markdown(result: DiffResult, *, verbose: bool = False) -> str:
    """Render a Markdown report."""
    lines = [
        "# AgentReplay Diff",
        "",
        f"**Runs:** `{result.left_run_id}` -> `{result.right_run_id}`",
        "",
        f"**Summary:** {result.summary()}",
    ]
    if result.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in result.warnings)
    if result.changes:
        lines.extend(["", "## Changes"])
        for change in result.changes:
            lines.append(
                "- "
                f"`{change.change_type}` "
                f"`{change.severity}` "
                f"`{change.category}` "
                f"{change.location}: {change.description}"
            )
            if verbose:
                lines.append(f"  Old: `{_value_text(change.old_value)}`")
                lines.append(f"  New: `{_value_text(change.new_value)}`")
    return "\n".join(lines)


def render_html(result: DiffResult, *, verbose: bool = False) -> str:
    """Render a dependency-free HTML report."""
    change_items = "\n".join(
        _html_change(change, verbose=verbose) for change in result.changes
    )
    warnings = "\n".join(
        f"<li>{html.escape(warning)}</li>" for warning in result.warnings
    )
    warnings_section = (
        f"<section><h2>Warnings</h2><ul>{warnings}</ul></section>"
        if result.warnings
        else ""
    )
    changes_section = (
        f"<section><h2>Changes</h2><ul>{change_items}</ul></section>"
        if result.changes
        else "<section><h2>Changes</h2><p>No differences found.</p></section>"
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>AgentReplay Diff</title>",
            "</head>",
            "<body>",
            "<h1>AgentReplay Diff</h1>",
            (
                f"<p><strong>Runs:</strong> {html.escape(result.left_run_id)} "
                f"&rarr; {html.escape(result.right_run_id)}</p>"
            ),
            f"<p><strong>Summary:</strong> {html.escape(result.summary())}</p>",
            warnings_section,
            changes_section,
            "</body>",
            "</html>",
        ]
    )


def _console_change(change: DiffChange, *, verbose: bool) -> str:
    """Render one console change line."""
    base = (
        f"- [{change.severity}] {change.change_type} "
        f"{change.category} at {change.location}: {change.description}"
    )
    if not verbose:
        return base
    return (
        f"{base}\n"
        f"  old={_value_text(change.old_value)}\n"
        f"  new={_value_text(change.new_value)}"
    )


def _html_change(change: DiffChange, *, verbose: bool) -> str:
    """Render one HTML change item."""
    details = ""
    if verbose:
        details = (
            "<pre>"
            f"old={html.escape(_value_text(change.old_value))}\n"
            f"new={html.escape(_value_text(change.new_value))}"
            "</pre>"
        )
    return (
        "<li>"
        f"<strong>{html.escape(change.severity)}</strong> "
        f"{html.escape(change.change_type)} "
        f"{html.escape(change.category)} at "
        f"<code>{html.escape(change.location)}</code>: "
        f"{html.escape(change.description)}"
        f"{details}"
        "</li>"
    )


def _value_text(value: object) -> str:
    """Return compact JSON text for a changed value."""
    return json.dumps(value, sort_keys=True)


__all__ = [
    "render_console",
    "render_html",
    "render_json",
    "render_markdown",
    "render_summary",
]
