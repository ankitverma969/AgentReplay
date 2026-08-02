"""Playback timeline models for AgentReplay replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    COST_RECORDED,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    FUNCTION_CALL,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    SYSTEM_PROMPT,
    TOKEN_USAGE_RECORDED,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
    EventType,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.types import JSONValue

_DISPLAY_LABELS: dict[EventType, str] = {
    RUN_STARTED: "Run Started",
    RUN_FINISHED: "Run Finished",
    USER_PROMPT: "Prompt",
    SYSTEM_PROMPT: "System Prompt",
    ASSISTANT_RESPONSE: "Assistant Response",
    LLM_REQUEST: "LLM Request",
    LLM_RESPONSE: "LLM Response",
    TOOL_STARTED: "Tool Started",
    TOOL_FINISHED: "Tool Finished",
    TOOL_FAILED: "Tool Failed",
    FUNCTION_CALL: "Function Call",
    MEMORY_READ: "Memory Read",
    MEMORY_WRITE: "Memory Write",
    CUSTOM_EVENT: "Custom Event",
    WARNING_RAISED: "Warning",
    EXCEPTION_RAISED: "Exception",
    RETRY_RECORDED: "Retry",
    TOKEN_USAGE_RECORDED: "Token Usage",
    COST_RECORDED: "Cost",
    LATENCY_RECORDED: "Latency",
}


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    """One display-ready event in a replay timeline."""

    index: int
    event: EventRecord
    label: str
    depth: int
    is_concurrent: bool
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of this entry."""
        return {
            "index": self.index,
            "event": self.event.to_dict(),
            "label": self.label,
            "depth": self.depth,
            "is_concurrent": self.is_concurrent,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class EventTimeline:
    """Display-ready timeline for a recorded run."""

    entries: tuple[TimelineEntry, ...]
    warnings: tuple[str, ...] = ()

    @classmethod
    def from_trace(cls, trace: TraceSnapshot) -> EventTimeline:
        """Build a timeline from a trace snapshot."""
        events = tuple(
            sorted(trace.events, key=lambda event: (event.sequence, event.timestamp))
        )
        event_ids = {event.event_id for event in events}
        depths = _calculate_depths(events)
        timestamp_counts = _timestamp_counts(events)
        warnings = _trace_warnings(trace, event_ids)
        entries = tuple(
            TimelineEntry(
                index=index,
                event=event,
                label=event_label(event),
                depth=depths.get(event.event_id, 0),
                is_concurrent=timestamp_counts[event.timestamp] > 1,
                warnings=_event_warnings(event, event_ids),
            )
            for index, event in enumerate(events)
        )
        return cls(entries=entries, warnings=warnings)

    def __len__(self) -> int:
        """Return the number of entries in the timeline."""
        return len(self.entries)

    def __iter__(self) -> ReplayTimelineIterator:
        """Iterate timeline entries from the beginning."""
        return ReplayTimelineIterator(self)

    def entry_at(self, index: int) -> TimelineEntry:
        """Return an entry by index."""
        return self.entries[index]

    def find_event_index(self, event_id: str) -> int | None:
        """Return the index for an event id if present."""
        for entry in self.entries:
            if entry.event.event_id == event_id:
                return entry.index
        return None

    def find_timestamp_index(self, timestamp: datetime) -> int | None:
        """Return the first entry at or after a timestamp."""
        for entry in self.entries:
            if entry.event.timestamp >= timestamp:
                return entry.index
        return None

    def slice_by_index(
        self, start: int | None = None, end: int | None = None
    ) -> EventTimeline:
        """Return a timeline slice using entry indexes."""
        lower = 0 if start is None else max(start, 0)
        upper = (
            len(self.entries) if end is None else min(end, len(self.entries) - 1) + 1
        )
        return EventTimeline(entries=self.entries[lower:upper], warnings=self.warnings)

    def slice_by_event_ids(
        self,
        start_event_id: str | None = None,
        end_event_id: str | None = None,
    ) -> EventTimeline:
        """Return a timeline slice bounded by event ids."""
        start = (
            None if start_event_id is None else self.find_event_index(start_event_id)
        )
        end = None if end_event_id is None else self.find_event_index(end_event_id)
        return self.slice_by_index(start=start, end=end)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of the timeline."""
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "warnings": list(self.warnings),
        }

    def render(
        self,
        *,
        include_details: bool = False,
        mark_concurrent: bool = False,
    ) -> str:
        """Render the timeline as human-readable text."""
        lines: list[str] = []
        for position, entry in enumerate(self.entries):
            indent = "  " * entry.depth
            concurrent = (
                " [concurrent]" if mark_concurrent and entry.is_concurrent else ""
            )
            lines.append(f"{indent}{entry.label}{concurrent}")
            if include_details:
                lines.append(f"{indent}  event_id={entry.event.event_id}")
                lines.append(f"{indent}  type={entry.event.event_type}")
            if position < len(self.entries) - 1:
                lines.append(f"{indent}\u2193")
        return "\n".join(lines)


class ReplayTimelineIterator:
    """Forward iterator over timeline entries."""

    def __init__(self, timeline: EventTimeline, *, start_index: int = 0) -> None:
        """Create a replay timeline iterator."""
        self._timeline = timeline
        self._index = start_index

    def __iter__(self) -> ReplayTimelineIterator:
        """Return this iterator."""
        return self

    def __next__(self) -> TimelineEntry:
        """Return the next timeline entry."""
        if self._index >= len(self._timeline.entries):
            raise StopIteration
        entry = self._timeline.entries[self._index]
        self._index += 1
        return entry


def event_label(event: EventRecord) -> str:
    """Return the display label for an event."""
    return _DISPLAY_LABELS.get(
        event.event_type, event.event_type.replace(".", " ").title()
    )


def _calculate_depths(events: tuple[EventRecord, ...]) -> dict[str, int]:
    """Calculate nesting depth for each event."""
    by_id = {event.event_id: event for event in events}
    depths: dict[str, int] = {}

    def depth_for(event: EventRecord, seen: frozenset[str]) -> int:
        if event.event_id in depths:
            return depths[event.event_id]
        if event.parent_event_id is None or event.parent_event_id not in by_id:
            depths[event.event_id] = 0
            return 0
        if event.event_id in seen:
            depths[event.event_id] = 0
            return 0
        parent = by_id[event.parent_event_id]
        depth = depth_for(parent, seen | {event.event_id}) + 1
        depths[event.event_id] = depth
        return depth

    for event in events:
        depth_for(event, frozenset())
    return depths


def _timestamp_counts(events: tuple[EventRecord, ...]) -> dict[datetime, int]:
    """Count events by timestamp to mark concurrent timeline entries."""
    counts: dict[datetime, int] = {}
    for event in events:
        counts[event.timestamp] = counts.get(event.timestamp, 0) + 1
    return counts


def _trace_warnings(trace: TraceSnapshot, event_ids: set[str]) -> tuple[str, ...]:
    """Return warnings for partial or suspicious traces."""
    warnings: list[str] = []
    if not trace.events:
        warnings.append("Run has no recorded events.")
    if trace.run.status == "running":
        warnings.append("Run appears to be a partial recording.")
    sequences = sorted(event.sequence for event in trace.events)
    if sequences and (
        sequences[0] != 1 or sequences != list(range(sequences[0], sequences[-1] + 1))
    ):
        warnings.append("Event sequence has gaps.")
    missing_parents = [
        event.parent_event_id
        for event in trace.events
        if event.parent_event_id is not None and event.parent_event_id not in event_ids
    ]
    if missing_parents:
        warnings.append("Some events reference missing parent events.")
    return tuple(warnings)


def _event_warnings(event: EventRecord, event_ids: set[str]) -> tuple[str, ...]:
    """Return event-level warnings."""
    if event.parent_event_id is not None and event.parent_event_id not in event_ids:
        return ("Missing parent event.",)
    return ()


__all__ = ["EventTimeline", "ReplayTimelineIterator", "TimelineEntry", "event_label"]
