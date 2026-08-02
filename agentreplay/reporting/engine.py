"""Read-only rich HTML trace report generator."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol, cast

from agentreplay.core.events import (
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    TOOL_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.diff import DiffEngine
from agentreplay.exceptions import DiffError, ProfilerError, ReportingError
from agentreplay.profiler import ProfilerEngine
from agentreplay.profiler.models import ProfilingReport
from agentreplay.replay import ReplayEngine
from agentreplay.replay.playback import TimelineEntry
from agentreplay.reporting.models import (
    ReportBundle,
    ReportEdge,
    ReportExtension,
    ReportExtensionKind,
    ReportMetric,
    ReportNode,
    ReportOptions,
    ReportTimelineItem,
    SearchDocument,
)
from agentreplay.security import SecurityEngine
from agentreplay.security.reports import render_json as render_security_json
from agentreplay.storage import Pagination, SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue

_TOOL_EVENTS = frozenset((TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED))
_MODEL_EVENTS = frozenset((LLM_REQUEST, LLM_RESPONSE))
_MEMORY_EVENTS = frozenset((MEMORY_READ, MEMORY_WRITE))
_TEXT_FIELDS = (
    "prompt",
    "messages",
    "input",
    "instructions",
    "tool_name",
    "function_name",
    "model_name",
    "provider_name",
    "provider",
    "error",
    "exception",
    "warning",
    "message",
)


class ReportPluginExtension(Protocol):
    """Protocol for plugin-provided report sections, charts, or widgets."""

    def render(self, report: object) -> str:
        """Render extension HTML for a report bundle."""


class ReportingEngine:
    """Generate standalone offline trace reports from recorded AgentReplay data."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        security_engine: SecurityEngine | None = None,
        profiler_engine: ProfilerEngine | None = None,
        diff_engine: DiffEngine | None = None,
        extensions: Mapping[str, ReportPluginExtension] | None = None,
        charts: Mapping[str, ReportPluginExtension] | None = None,
        widgets: Mapping[str, ReportPluginExtension] | None = None,
    ) -> None:
        """Create a reporting engine."""
        self._storage = storage
        self._security_engine = (
            SecurityEngine() if security_engine is None else security_engine
        )
        self._profiler_engine = profiler_engine
        self._diff_engine = diff_engine
        self._extensions = dict(extensions or {})
        self._charts = dict(charts or {})
        self._widgets = dict(widgets or {})

    def generate(
        self,
        run_id: str,
        *,
        options: ReportOptions | None = None,
    ) -> ReportBundle:
        """Generate a report bundle from a storage-backed run id."""
        resolved_options = ReportOptions() if options is None else options
        trace = self.load(run_id)
        compare_trace = (
            None
            if resolved_options.compare_run_id is None
            else self.load(resolved_options.compare_run_id)
        )
        return self.generate_trace(
            trace,
            options=resolved_options,
            compare_trace=compare_trace,
        )

    def generate_trace(
        self,
        trace: TraceSnapshot,
        *,
        options: ReportOptions | None = None,
        compare_trace: TraceSnapshot | None = None,
    ) -> ReportBundle:
        """Generate a report bundle from an in-memory trace snapshot."""
        resolved_options = ReportOptions() if options is None else options
        security_report = self._security_engine.verify(
            trace.to_dict(),
            source=trace.run.run_id,
        )
        sanitized_trace = self._security_engine.sanitize_trace(trace)
        replay = ReplayEngine()
        session = replay.load_trace(sanitized_trace)
        profiler = self._profile(sanitized_trace)
        diff_data = self._diff(sanitized_trace, compare_trace)
        entries = session.timeline.entries
        nodes = _nodes(entries)
        bundle = ReportBundle(
            run_id=sanitized_trace.run.run_id,
            run_name=sanitized_trace.run.name,
            generated_at=datetime.now(UTC).isoformat(),
            theme=resolved_options.theme,
            metrics=_metrics(
                sanitized_trace, profiler.to_dict(), security_report.to_dict()
            ),
            nodes=nodes,
            edges=_edges(nodes),
            timeline=_timeline(entries, limit=resolved_options.visualization_limit),
            trace_tree=_timeline(entries, limit=resolved_options.visualization_limit),
            search_index=_search_index(entries),
            filter_counts=_filter_counts(sanitized_trace.events),
            trace=sanitized_trace.to_dict(),
            profiler=profiler.to_dict(),
            security=json.loads(render_security_json(security_report)),
            diff=diff_data,
            warnings=session.warnings,
            assets_compressed=resolved_options.compress,
            metadata={
                "event_count": len(sanitized_trace.events),
                "comparison_run_id": (
                    None if compare_trace is None else compare_trace.run.run_id
                ),
                "visualization_limit": resolved_options.visualization_limit,
            },
        )
        return _with_extensions(bundle, self._extensions, self._charts, self._widgets)

    def load(self, run_id: str) -> TraceSnapshot:
        """Load a trace from storage."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        resolved_run_id = self.resolve_run_id(run_id)
        run = storage.load_run(resolved_run_id)
        if run is None:
            msg = f"Report run not found: {resolved_run_id}"
            raise ReportingError(msg)
        return TraceSnapshot(
            run=run,
            events=tuple(storage.stream_events(resolved_run_id, batch_size=5_000)),
        )

    def resolve_run_id(self, run_id: str) -> str:
        """Resolve the special ``latest`` run id."""
        if run_id != "latest":
            return run_id
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.list_runs(pagination=Pagination(limit=1))
        if not runs:
            msg = "No recorded runs found."
            raise ReportingError(msg)
        return runs[0].run_id

    def close(self) -> None:
        """Release storage resources."""
        if self._storage is not None:
            self._storage.close()

    def _profile(self, trace: TraceSnapshot) -> ProfilingReport:
        """Profile a trace for report inclusion."""
        profiler = (
            ProfilerEngine(storage=self._storage)
            if self._profiler_engine is None
            else self._profiler_engine
        )
        try:
            return profiler.profile(trace)
        except ProfilerError as exc:
            msg = f"Profiler results could not be generated: {exc}"
            raise ReportingError(msg) from exc

    def _diff(
        self,
        trace: TraceSnapshot,
        compare_trace: TraceSnapshot | None,
    ) -> dict[str, JSONValue] | None:
        """Generate optional diff data."""
        if compare_trace is None:
            return None
        diff_engine = (
            DiffEngine(storage=self._storage)
            if self._diff_engine is None
            else self._diff_engine
        )
        try:
            return diff_engine.compare(trace, compare_trace).to_dict()
        except DiffError as exc:
            msg = f"Diff report could not be generated: {exc}"
            raise ReportingError(msg) from exc


def _metrics(
    trace: TraceSnapshot,
    profiler: Mapping[str, JSONValue],
    security: Mapping[str, JSONValue],
) -> tuple[ReportMetric, ...]:
    """Build overview metrics for the report."""
    duration = cast(Mapping[str, JSONValue], profiler.get("duration", {}))
    tokens = cast(Mapping[str, JSONValue], profiler.get("token_analysis", {}))
    cost = cast(Mapping[str, JSONValue], profiler.get("cost_analysis", {}))
    findings = security.get("findings", [])
    return (
        ReportMetric("Events", str(len(trace.events))),
        ReportMetric(
            "Status",
            trace.run.status,
            "success" if trace.run.status == "completed" else "warning",
        ),
        ReportMetric("Duration", f"{_float(duration.get('total_ms')):.3f} ms"),
        ReportMetric("Tokens", str(_int(tokens.get("total_tokens")))),
        ReportMetric("Cost", f"{_float(cost.get('total_cost')):.6f}"),
        ReportMetric(
            "Security Findings", str(len(findings) if isinstance(findings, list) else 0)
        ),
    )


def _nodes(entries: tuple[TimelineEntry, ...]) -> tuple[ReportNode, ...]:
    """Build execution graph nodes."""
    return tuple(
        ReportNode(
            event_id=entry.event.event_id,
            label=entry.label,
            event_type=entry.event.event_type,
            parent_event_id=entry.event.parent_event_id,
            duration_ms=entry.event.duration_ms,
            timestamp=entry.event.timestamp.isoformat(),
            severity=_severity(entry.event),
        )
        for entry in entries
    )


def _edges(nodes: tuple[ReportNode, ...]) -> tuple[ReportEdge, ...]:
    """Build graph edges from parent relationships and sequence order."""
    node_ids = {node.event_id for node in nodes}
    edges: list[ReportEdge] = []
    previous: str | None = None
    for node in nodes:
        if node.parent_event_id is not None and node.parent_event_id in node_ids:
            edges.append(ReportEdge(node.parent_event_id, node.event_id))
        elif previous is not None:
            edges.append(ReportEdge(previous, node.event_id))
        previous = node.event_id
    return tuple(edges)


def _timeline(
    entries: tuple[TimelineEntry, ...],
    *,
    limit: int,
) -> tuple[ReportTimelineItem, ...]:
    """Build timeline rows."""
    if not entries:
        return ()
    first = entries[0].event.timestamp
    return tuple(
        ReportTimelineItem(
            event_id=entry.event.event_id,
            label=entry.label,
            event_type=entry.event.event_type,
            start_ms=max(
                (entry.event.timestamp - first).total_seconds() * 1_000.0, 0.0
            ),
            duration_ms=entry.event.duration_ms,
            depth=entry.depth,
            category=_category(entry.event),
        )
        for entry in entries[:limit]
    )


def _search_index(entries: tuple[TimelineEntry, ...]) -> tuple[SearchDocument, ...]:
    """Build a compact client-side search index."""
    documents: list[SearchDocument] = []
    for entry in entries:
        fields = {
            "event_type": entry.event.event_type,
            "payload": _selected_text(entry.event.payload),
            "metadata": _selected_text(entry.event.metadata),
        }
        documents.append(
            SearchDocument(
                event_id=entry.event.event_id,
                text=" ".join(fields.values()),
                fields=fields,
            )
        )
    return tuple(documents)


def _filter_counts(events: tuple[EventRecord, ...]) -> dict[str, int]:
    """Build client filter counts."""
    counts: Counter[str] = Counter()
    for event in events:
        category = _category(event)
        counts[category] += 1
        if event.event_type == WARNING_RAISED:
            counts["warnings"] += 1
        if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
            counts["errors"] += 1
        if event.event_type == RETRY_RECORDED:
            counts["retries"] += 1
        if _event_cost(event) > 0:
            counts["expensive"] += 1
        if event.duration_ms >= 1_000:
            counts["slow"] += 1
    return dict(counts)


def _with_extensions(
    bundle: ReportBundle,
    sections: Mapping[str, ReportPluginExtension],
    charts: Mapping[str, ReportPluginExtension],
    widgets: Mapping[str, ReportPluginExtension],
) -> ReportBundle:
    """Render plugin-provided extensions with failure isolation."""
    extensions: list[ReportExtension] = []
    for kind, group in (
        ("section", sections),
        ("chart", charts),
        ("widget", widgets),
    ):
        for name, extension in group.items():
            try:
                html = extension.render(bundle)
            except Exception as exc:
                html = f"<p>Report extension failed: {str(exc)}</p>"
            extensions.append(
                ReportExtension(
                    name=name,
                    kind=cast(ReportExtensionKind, kind),
                    html=html,
                )
            )
    return ReportBundle(
        run_id=bundle.run_id,
        run_name=bundle.run_name,
        generated_at=bundle.generated_at,
        theme=bundle.theme,
        metrics=bundle.metrics,
        nodes=bundle.nodes,
        edges=bundle.edges,
        timeline=bundle.timeline,
        trace_tree=bundle.trace_tree,
        search_index=bundle.search_index,
        filter_counts=bundle.filter_counts,
        trace=bundle.trace,
        profiler=bundle.profiler,
        security=bundle.security,
        diff=bundle.diff,
        extensions=tuple(extensions),
        warnings=bundle.warnings,
        assets_compressed=bundle.assets_compressed,
        metadata=bundle.metadata,
    )


def _severity(event: EventRecord) -> str:
    """Return event visual severity."""
    if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
        return "error"
    if event.event_type == WARNING_RAISED:
        return "warning"
    if event.duration_ms >= 1_000:
        return "slow"
    return "normal"


def _category(event: EventRecord) -> str:
    """Return event category for filtering and charts."""
    if event.event_type in _TOOL_EVENTS:
        return "tools"
    if event.event_type in _MODEL_EVENTS:
        return "models"
    if event.event_type in _MEMORY_EVENTS:
        return "memory"
    if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
        return "errors"
    if event.event_type == WARNING_RAISED:
        return "warnings"
    if event.event_type == RETRY_RECORDED:
        return "retries"
    return "events"


def _selected_text(mapping: Mapping[str, object]) -> str:
    """Return selected searchable text from a mapping."""
    values: list[str] = []
    for key, value in mapping.items():
        normalized = key.lower()
        if normalized in _TEXT_FIELDS or any(
            field in normalized for field in _TEXT_FIELDS
        ):
            values.append(_stringify(value))
    if not values:
        values.append(json.dumps(mapping, sort_keys=True, default=str))
    return " ".join(values)


def _event_cost(event: EventRecord) -> float:
    """Return event cost if present."""
    cost = event.payload.get("cost")
    if isinstance(cost, Mapping):
        return _float(cost.get("amount"))
    return _float(cost) + _float(event.payload.get("amount"))


def _stringify(value: object) -> str:
    """Return deterministic string text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _float(value: object) -> float:
    """Convert JSON-like value to float."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _int(value: object) -> int:
    """Convert JSON-like value to integer."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


__all__ = ["ReportPluginExtension", "ReportingEngine"]
