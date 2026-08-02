"""Filtering predicates for debugger timeline entries."""

from __future__ import annotations

from agentreplay.core.events import (
    EXCEPTION_RAISED,
    LATENCY_RECORDED,
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
)
from agentreplay.debugger.models import DebuggerFilter
from agentreplay.replay.playback import TimelineEntry

_TOOL_EVENTS = frozenset((TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED))
_LLM_EVENTS = frozenset((LLM_REQUEST, LLM_RESPONSE))
_MEMORY_EVENTS = frozenset((MEMORY_READ, MEMORY_WRITE))


def entry_matches_filter(entry: TimelineEntry, event_filter: DebuggerFilter) -> bool:
    """Return whether an entry should be visible under the active filters."""
    if not event_filter.active:
        return True
    event = entry.event
    checks = (
        event_filter.errors and event.event_type in {EXCEPTION_RAISED, TOOL_FAILED},
        event_filter.warnings and event.event_type == WARNING_RAISED,
        event_filter.tool_events and event.event_type in _TOOL_EVENTS,
        event_filter.llm_events and event.event_type in _LLM_EVENTS,
        event_filter.memory_events and event.event_type in _MEMORY_EVENTS,
        event_filter.retries and event.event_type == RETRY_RECORDED,
        event_filter.slow_events
        and (
            event.duration_ms >= event_filter.slow_threshold_ms
            or _payload_float(event.payload.get("latency_ms"))
            >= event_filter.slow_threshold_ms
            or (
                event.event_type == LATENCY_RECORDED
                and _payload_float(event.payload.get("duration_ms"))
                >= event_filter.slow_threshold_ms
            )
        ),
        event_filter.expensive_events
        and _event_cost(event.payload) >= event_filter.expensive_threshold,
    )
    return any(checks)


def _event_cost(payload: object) -> float:
    """Return a best-effort cost amount from an event payload."""
    if not isinstance(payload, dict):
        return 0.0
    direct = _payload_float(payload.get("cost"))
    if direct:
        return direct
    nested = payload.get("cost")
    if isinstance(nested, dict):
        return _payload_float(nested.get("amount"))
    return _payload_float(payload.get("amount"))


def _payload_float(value: object) -> float:
    """Convert a payload value to a float when possible."""
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


__all__ = ["entry_matches_filter"]
