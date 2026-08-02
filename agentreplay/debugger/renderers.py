"""Human-readable renderers for debugger panels and exports."""

from __future__ import annotations

import html
import json
from collections.abc import Mapping

from agentreplay.debugger.models import DebuggerStats, EventInspection
from agentreplay.replay.playback import TimelineEntry
from agentreplay.types import JSONValue


def render_event_inspection(inspection: EventInspection) -> str:
    """Render a selected event for the center debugger panel."""
    sections = [
        f"Event Type: {inspection.event_type}",
        f"Event ID: {inspection.event_id}",
        f"Timestamp: {inspection.timestamp}",
        f"Duration: {inspection.duration_ms:.3f} ms",
        f"Parent: {inspection.parent_event_id or '-'}",
        f"Children: {', '.join(inspection.children) if inspection.children else '-'}",
    ]
    payload = _json_block(inspection.payload)
    if payload:
        sections.append(f"Payload:\n{payload}")
    return "\n\n".join(sections)


def render_metadata(metadata: Mapping[str, JSONValue]) -> str:
    """Render metadata for the right debugger panel."""
    if not metadata:
        return "No metadata recorded for this event."
    return _json_block(metadata)


def render_stats(stats: DebuggerStats) -> str:
    """Render aggregate execution statistics."""
    return "\n".join(
        (
            f"Total Events: {stats.total_events}",
            f"Latency: {stats.latency_ms:.3f} ms",
            f"Cost: {stats.cost:.6f}",
            f"Tokens: {stats.total_tokens}",
            f"Prompt Tokens: {stats.prompt_tokens}",
            f"Completion Tokens: {stats.completion_tokens}",
            f"Retries: {stats.retries}",
            f"Warnings: {stats.warnings}",
            f"Errors: {stats.errors}",
            f"Slowest Tool: {stats.slowest_tool_event_id or '-'} "
            f"({stats.slowest_tool_ms:.3f} ms)",
            f"Largest Prompt: {stats.largest_prompt_event_id or '-'} "
            f"({stats.largest_prompt_chars} chars)",
            f"Largest Response: {stats.largest_response_event_id or '-'} "
            f"({stats.largest_response_chars} chars)",
        )
    )


def render_timeline_tree(entries: tuple[TimelineEntry, ...]) -> tuple[str, ...]:
    """Render a compact text tree for timelines and logs."""
    lines: list[str] = []
    for entry in entries:
        branch = "  " * entry.depth
        concurrent = " [parallel]" if entry.is_concurrent else ""
        lines.append(f"{branch}{entry.label}{concurrent} ({entry.event.event_id})")
    return tuple(lines)


def render_event_export(entry: TimelineEntry, export_format: str) -> str:
    """Render one selected event in an export format."""
    event_dict = entry.event.to_dict()
    if export_format in {"json", "clipboard"}:
        return json.dumps(event_dict, sort_keys=True, indent=2)
    if export_format == "markdown":
        return _markdown_event(entry, event_dict)
    if export_format == "html":
        return _html_event(entry, event_dict)
    msg = f"Unsupported debugger export format: {export_format}"
    raise ValueError(msg)


def _markdown_event(
    entry: TimelineEntry,
    event_dict: Mapping[str, JSONValue],
) -> str:
    """Render one event as Markdown."""
    return "\n".join(
        (
            f"# {entry.label}",
            "",
            f"- Event ID: `{entry.event.event_id}`",
            f"- Event Type: `{entry.event.event_type}`",
            f"- Timestamp: `{entry.event.timestamp.isoformat()}`",
            f"- Duration: `{entry.event.duration_ms:.3f} ms`",
            "",
            "```json",
            json.dumps(event_dict, sort_keys=True, indent=2),
            "```",
        )
    )


def _html_event(entry: TimelineEntry, event_dict: Mapping[str, JSONValue]) -> str:
    """Render one event as a standalone HTML document."""
    body = html.escape(json.dumps(event_dict, sort_keys=True, indent=2))
    title = html.escape(entry.label)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><pre>{body}</pre></body></html>"
    )


def _json_block(value: Mapping[str, JSONValue]) -> str:
    """Render a JSON-like mapping as pretty text."""
    return json.dumps(value, sort_keys=True, indent=2)


__all__ = [
    "render_event_export",
    "render_event_inspection",
    "render_metadata",
    "render_stats",
    "render_timeline_tree",
]
