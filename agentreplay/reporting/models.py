"""Typed models for AgentReplay standalone trace reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue

ReportTheme: TypeAlias = Literal["dark", "light", "print"]
ReportExtensionKind: TypeAlias = Literal["section", "chart", "widget"]


@dataclass(frozen=True, slots=True)
class ReportOptions:
    """Options used while generating a trace report."""

    theme: ReportTheme = "dark"
    compress: bool = False
    compare_run_id: str | None = None
    visualization_limit: int = 10_000

    def __post_init__(self) -> None:
        """Validate report options."""
        if self.visualization_limit <= 0:
            msg = "Report visualization limit must be greater than zero."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class ReportMetric:
    """One display metric in a trace report."""

    label: str
    value: str
    tone: str = "neutral"

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {"label": self.label, "value": self.value, "tone": self.tone}


@dataclass(frozen=True, slots=True)
class ReportNode:
    """Execution graph node for a report."""

    event_id: str
    label: str
    event_type: str
    parent_event_id: str | None
    duration_ms: float
    timestamp: str
    severity: str = "normal"

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "event_id": self.event_id,
            "label": self.label,
            "event_type": self.event_type,
            "parent_event_id": self.parent_event_id,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "severity": self.severity,
        }


@dataclass(frozen=True, slots=True)
class ReportEdge:
    """Execution graph edge for a report."""

    source_event_id: str
    target_event_id: str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "source_event_id": self.source_event_id,
            "target_event_id": self.target_event_id,
        }


@dataclass(frozen=True, slots=True)
class ReportTimelineItem:
    """Timeline item for report rendering."""

    event_id: str
    label: str
    event_type: str
    start_ms: float
    duration_ms: float
    depth: int
    category: str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "event_id": self.event_id,
            "label": self.label,
            "event_type": self.event_type,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "depth": self.depth,
            "category": self.category,
        }


@dataclass(frozen=True, slots=True)
class SearchDocument:
    """Search index document embedded in a report."""

    event_id: str
    text: str
    fields: dict[str, str]

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {"event_id": self.event_id, "text": self.text, "fields": self.fields}


@dataclass(frozen=True, slots=True)
class ReportExtension:
    """Plugin-provided report extension output."""

    name: str
    kind: ReportExtensionKind
    html: str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {"name": self.name, "kind": self.kind, "html": self.html}


@dataclass(frozen=True, slots=True)
class ReportBundle:
    """Complete report bundle before rendering."""

    run_id: str
    run_name: str | None
    generated_at: str
    theme: ReportTheme
    metrics: tuple[ReportMetric, ...]
    nodes: tuple[ReportNode, ...]
    edges: tuple[ReportEdge, ...]
    timeline: tuple[ReportTimelineItem, ...]
    trace_tree: tuple[ReportTimelineItem, ...]
    search_index: tuple[SearchDocument, ...]
    filter_counts: dict[str, int]
    trace: dict[str, JSONValue]
    profiler: dict[str, JSONValue]
    security: dict[str, JSONValue]
    diff: dict[str, JSONValue] | None = None
    extensions: tuple[ReportExtension, ...] = ()
    warnings: tuple[str, ...] = ()
    assets_compressed: bool = False
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "generated_at": self.generated_at,
            "theme": self.theme,
            "metrics": [metric.to_dict() for metric in self.metrics],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "timeline": [item.to_dict() for item in self.timeline],
            "trace_tree": [item.to_dict() for item in self.trace_tree],
            "search_index": [document.to_dict() for document in self.search_index],
            "filter_counts": self.filter_counts,
            "trace": self.trace,
            "profiler": self.profiler,
            "security": self.security,
            "diff": self.diff,
            "extensions": [extension.to_dict() for extension in self.extensions],
            "warnings": list(self.warnings),
            "assets_compressed": self.assets_compressed,
            "metadata": self.metadata,
        }


__all__ = [
    "ReportBundle",
    "ReportEdge",
    "ReportExtension",
    "ReportExtensionKind",
    "ReportMetric",
    "ReportNode",
    "ReportOptions",
    "ReportTheme",
    "ReportTimelineItem",
    "SearchDocument",
]
