"""Read-only execution comparison engine for AgentReplay traces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    COST_RECORDED,
    EXCEPTION_RAISED,
    FUNCTION_CALL,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    SYSTEM_PROMPT,
    TOKEN_USAGE_RECORDED,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.diff.matchers import EventMatch, EventMatcher
from agentreplay.diff.models import (
    ChangeType,
    DiffChange,
    DiffResult,
    DiffSeverity,
    build_result,
)
from agentreplay.exceptions import DiffError
from agentreplay.storage import SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue

DiffInput = TraceSnapshot | str
_MISSING = "<missing>"


class DiffEngine:
    """Compare two recorded executions without executing agents, tools, or LLMs."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        matcher: EventMatcher | None = None,
    ) -> None:
        """Create a diff engine."""
        self._storage = storage
        self._matcher = EventMatcher() if matcher is None else matcher

    def compare(self, left: DiffInput, right: DiffInput) -> DiffResult:
        """Compare two trace snapshots or storage-backed run ids."""
        left_trace = self._resolve_trace(left)
        right_trace = self._resolve_trace(right)
        changes: list[DiffChange] = []
        unchanged = 0

        run_changes, run_unchanged = _compare_runs(left_trace, right_trace)
        changes.extend(run_changes)
        unchanged += run_unchanged

        event_matches = self._matcher.align(left_trace.events, right_trace.events)
        event_context = _EventContext(left_trace.events, right_trace.events)
        for match in event_matches:
            event_changes, event_unchanged = _compare_event_match(
                match,
                event_context,
            )
            changes.extend(event_changes)
            unchanged += event_unchanged

        return build_result(
            left_run_id=left_trace.run.run_id,
            right_run_id=right_trace.run.run_id,
            changes=changes,
            unchanged=unchanged,
            warnings=_diff_warnings(left_trace, right_trace),
        )

    def load(self, run_id: str) -> TraceSnapshot:
        """Load a trace from storage for comparison."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        run = storage.load_run(run_id)
        if run is None:
            msg = f"Diff run not found: {run_id}"
            raise DiffError(msg)
        return TraceSnapshot(run=run, events=storage.load_events(run_id))

    def _resolve_trace(self, value: DiffInput) -> TraceSnapshot:
        """Resolve a trace input without mutating recorded data."""
        if isinstance(value, TraceSnapshot):
            return value
        return self.load(value)


class _EventContext:
    """Parent lookup state used while comparing aligned events."""

    def __init__(
        self,
        left_events: Sequence[EventRecord],
        right_events: Sequence[EventRecord],
    ) -> None:
        """Create parent lookup indexes."""
        self.left_by_id = {event.event_id: event for event in left_events}
        self.right_by_id = {event.event_id: event for event in right_events}

    def parent_label(self, event: EventRecord | None, *, side: str) -> str | None:
        """Return a semantic parent label for one side of the comparison."""
        if event is None or event.parent_event_id is None:
            return None
        lookup = self.left_by_id if side == "left" else self.right_by_id
        parent = lookup.get(event.parent_event_id)
        if parent is None:
            return _MISSING
        return _event_identity(parent)


def _compare_runs(
    left: TraceSnapshot,
    right: TraceSnapshot,
) -> tuple[list[DiffChange], int]:
    """Compare run-level fields."""
    changes: list[DiffChange] = []
    unchanged = 0
    checks: tuple[tuple[str, JSONValue, JSONValue, str, DiffSeverity], ...] = (
        ("run.name", left.run.name, right.run.name, "metadata", "low"),
        ("run.status", left.run.status, right.run.status, "run_metadata", "medium"),
        (
            "run.duration_ms",
            left.run.duration_ms,
            right.run.duration_ms,
            "execution_time",
            _numeric_severity(left.run.duration_ms, right.run.duration_ms),
        ),
        ("run.tags", list(left.run.tags), list(right.run.tags), "metadata", "low"),
    )
    for location, old_value, new_value, category, severity in checks:
        if old_value == new_value:
            unchanged += 1
            continue
        changes.append(
            _change(
                category=category,
                location=location,
                severity=severity,
                description=f"{_title(location)} changed.",
                old_value=old_value,
                new_value=new_value,
            )
        )

    metadata_changes, metadata_unchanged = _compare_values(
        left.run.metadata,
        right.run.metadata,
        location="run.metadata",
        category="custom_metadata",
        severity="low",
    )
    changes.extend(metadata_changes)
    unchanged += metadata_unchanged
    return changes, unchanged


def _compare_event_match(
    match: EventMatch,
    context: _EventContext,
) -> tuple[list[DiffChange], int]:
    """Compare one aligned event match."""
    if match.kind == "added":
        event = _require_event(match.right_event)
        return [
            _change(
                change_type="added",
                category=_event_category(event, "event"),
                location=_event_location(match),
                severity=_event_presence_severity(event),
                description=f"Extra event recorded: {_event_identity(event)}.",
                old_value=None,
                new_value=event.to_dict(),
                new_event_id=event.event_id,
            )
        ], 0
    if match.kind == "removed":
        event = _require_event(match.left_event)
        return [
            _change(
                change_type="removed",
                category=_event_category(event, "event"),
                location=_event_location(match),
                severity=_event_presence_severity(event),
                description=f"Missing event: {_event_identity(event)}.",
                old_value=event.to_dict(),
                new_value=None,
                old_event_id=event.event_id,
            )
        ], 0

    left = _require_event(match.left_event)
    right = _require_event(match.right_event)
    changes: list[DiffChange] = []
    unchanged = 0

    if left.event_type == right.event_type:
        unchanged += 1
    else:
        changes.append(
            _event_change(
                left,
                right,
                category="timeline",
                location=f"{_event_location(match)}.event_type",
                severity="high",
                description="Timeline event type changed.",
                old_value=left.event_type,
                new_value=right.event_type,
            )
        )

    parent_left = context.parent_label(left, side="left")
    parent_right = context.parent_label(right, side="right")
    if parent_left == parent_right:
        unchanged += 1
    else:
        changes.append(
            _event_change(
                left,
                right,
                category="execution_graph",
                location=f"{_event_location(match)}.parent",
                severity="medium",
                description="Execution graph parent changed.",
                old_value=parent_left,
                new_value=parent_right,
            )
        )

    if left.duration_ms == right.duration_ms:
        unchanged += 1
    else:
        changes.append(
            _event_change(
                left,
                right,
                category="latency",
                location=f"{_event_location(match)}.duration_ms",
                severity=_numeric_severity(left.duration_ms, right.duration_ms),
                description="Event duration changed.",
                old_value=left.duration_ms,
                new_value=right.duration_ms,
            )
        )

    metadata_changes, metadata_unchanged = _compare_values(
        left.metadata,
        right.metadata,
        location=f"{_event_location(match)}.metadata",
        category="custom_metadata",
        severity="low",
        old_event=left,
        new_event=right,
    )
    payload_changes, payload_unchanged = _compare_values(
        left.payload,
        right.payload,
        location=f"{_event_location(match)}.payload",
        category=_event_category(left, "payload"),
        severity=_event_payload_severity(left),
        old_event=left,
        new_event=right,
        event_type=left.event_type,
    )
    changes.extend(metadata_changes)
    changes.extend(payload_changes)
    unchanged += metadata_unchanged + payload_unchanged
    return changes, unchanged


def _compare_values(
    old_value: object,
    new_value: object,
    *,
    location: str,
    category: str,
    severity: DiffSeverity,
    old_event: EventRecord | None = None,
    new_event: EventRecord | None = None,
    event_type: str | None = None,
) -> tuple[list[DiffChange], int]:
    """Recursively compare JSON-like values."""
    if old_value == new_value:
        return [], 1
    if isinstance(old_value, Mapping) and isinstance(new_value, Mapping):
        return _compare_mappings(
            old_value,
            new_value,
            location=location,
            category=category,
            severity=severity,
            old_event=old_event,
            new_event=new_event,
            event_type=event_type,
        )
    if _is_sequence(old_value) and _is_sequence(new_value):
        return _compare_sequences(
            cast(Sequence[object], old_value),
            cast(Sequence[object], new_value),
            location=location,
            category=category,
            severity=severity,
            old_event=old_event,
            new_event=new_event,
            event_type=event_type,
        )
    return [
        _change_for_values(
            old_value,
            new_value,
            location=location,
            category=_category_for_location(category, location, event_type),
            severity=_severity_for_location(severity, location, event_type),
            old_event=old_event,
            new_event=new_event,
        )
    ], 0


def _compare_mappings(
    old_mapping: Mapping[object, object],
    new_mapping: Mapping[object, object],
    *,
    location: str,
    category: str,
    severity: DiffSeverity,
    old_event: EventRecord | None,
    new_event: EventRecord | None,
    event_type: str | None,
) -> tuple[list[DiffChange], int]:
    """Compare mapping keys and values."""
    changes: list[DiffChange] = []
    unchanged = 0
    old_keys = {str(key) for key in old_mapping}
    new_keys = {str(key) for key in new_mapping}
    old_by_key = {str(key): value for key, value in old_mapping.items()}
    new_by_key = {str(key): value for key, value in new_mapping.items()}
    for key in sorted(old_keys - new_keys):
        key_location = f"{location}.{key}"
        changes.append(
            _change_for_values(
                old_by_key[key],
                None,
                change_type="removed",
                location=key_location,
                category=_category_for_location(category, key_location, event_type),
                severity=_severity_for_location(severity, key_location, event_type),
                old_event=old_event,
                new_event=new_event,
            )
        )
    for key in sorted(new_keys - old_keys):
        key_location = f"{location}.{key}"
        changes.append(
            _change_for_values(
                None,
                new_by_key[key],
                change_type="added",
                location=key_location,
                category=_category_for_location(category, key_location, event_type),
                severity=_severity_for_location(severity, key_location, event_type),
                old_event=old_event,
                new_event=new_event,
            )
        )
    for key in sorted(old_keys & new_keys):
        nested_changes, nested_unchanged = _compare_values(
            old_by_key[key],
            new_by_key[key],
            location=f"{location}.{key}",
            category=category,
            severity=severity,
            old_event=old_event,
            new_event=new_event,
            event_type=event_type,
        )
        changes.extend(nested_changes)
        unchanged += nested_unchanged
    return changes, unchanged


def _compare_sequences(
    old_sequence: Sequence[object],
    new_sequence: Sequence[object],
    *,
    location: str,
    category: str,
    severity: DiffSeverity,
    old_event: EventRecord | None,
    new_event: EventRecord | None,
    event_type: str | None,
) -> tuple[list[DiffChange], int]:
    """Compare sequence values by position."""
    changes: list[DiffChange] = []
    unchanged = 0
    paired = min(len(old_sequence), len(new_sequence))
    for index in range(paired):
        nested_changes, nested_unchanged = _compare_values(
            old_sequence[index],
            new_sequence[index],
            location=f"{location}[{index}]",
            category=category,
            severity=severity,
            old_event=old_event,
            new_event=new_event,
            event_type=event_type,
        )
        changes.extend(nested_changes)
        unchanged += nested_unchanged
    for index in range(paired, len(old_sequence)):
        item_location = f"{location}[{index}]"
        changes.append(
            _change_for_values(
                old_sequence[index],
                None,
                change_type="removed",
                location=item_location,
                category=_category_for_location(category, item_location, event_type),
                severity=_severity_for_location(severity, item_location, event_type),
                old_event=old_event,
                new_event=new_event,
            )
        )
    for index in range(paired, len(new_sequence)):
        item_location = f"{location}[{index}]"
        changes.append(
            _change_for_values(
                None,
                new_sequence[index],
                change_type="added",
                location=item_location,
                category=_category_for_location(category, item_location, event_type),
                severity=_severity_for_location(severity, item_location, event_type),
                old_event=old_event,
                new_event=new_event,
            )
        )
    return changes, unchanged


def _change_for_values(
    old_value: object,
    new_value: object,
    *,
    location: str,
    category: str,
    severity: DiffSeverity,
    old_event: EventRecord | None,
    new_event: EventRecord | None,
    change_type: str = "modified",
) -> DiffChange:
    """Build a value-level diff change."""
    return _change(
        change_type=cast(ChangeType, change_type),
        category=category,
        location=location,
        severity=severity,
        description=_description_for(location, category, change_type),
        old_value=_json_value(old_value),
        new_value=_json_value(new_value),
        old_event_id=None if old_event is None else old_event.event_id,
        new_event_id=None if new_event is None else new_event.event_id,
    )


def _change(
    *,
    category: str,
    location: str,
    severity: DiffSeverity,
    description: str,
    old_value: JSONValue,
    new_value: JSONValue,
    change_type: str = "modified",
    old_event_id: str | None = None,
    new_event_id: str | None = None,
) -> DiffChange:
    """Build a typed diff change."""
    return DiffChange(
        change_type=cast(ChangeType, change_type),
        category=category,
        location=location,
        severity=severity,
        description=description,
        old_value=old_value,
        new_value=new_value,
        old_event_id=old_event_id,
        new_event_id=new_event_id,
    )


def _event_change(
    left: EventRecord,
    right: EventRecord,
    *,
    category: str,
    location: str,
    severity: DiffSeverity,
    description: str,
    old_value: JSONValue,
    new_value: JSONValue,
) -> DiffChange:
    """Build an event-level modified change."""
    return _change(
        category=category,
        location=location,
        severity=severity,
        description=description,
        old_value=old_value,
        new_value=new_value,
        old_event_id=left.event_id,
        new_event_id=right.event_id,
    )


def _event_location(match: EventMatch) -> str:
    """Return a stable location for an event match."""
    if match.left_index is not None and match.right_index is not None:
        return f"events[{match.left_index}->{match.right_index}]"
    if match.left_index is not None:
        return f"events[{match.left_index}]"
    if match.right_index is not None:
        return f"events[{match.right_index}]"
    return "events"


def _event_identity(event: EventRecord) -> str:
    """Return a concise semantic event identity."""
    name = event.payload.get("tool_name") or event.payload.get("function_name")
    if isinstance(name, str):
        return f"{event.event_type}:{name}"
    custom_name = event.payload.get("name")
    if isinstance(custom_name, str):
        return f"{event.event_type}:{custom_name}"
    return event.event_type


def _event_category(event: EventRecord, default: str) -> str:
    """Return the comparison category for an event."""
    if event.event_type in {USER_PROMPT, SYSTEM_PROMPT}:
        return "prompt"
    if event.event_type == ASSISTANT_RESPONSE:
        return "assistant_response"
    if event.event_type in {LLM_REQUEST, LLM_RESPONSE}:
        return "llm"
    if event.event_type in {TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED}:
        return "tool_calls"
    if event.event_type == FUNCTION_CALL:
        return "function_calls"
    if event.event_type in {MEMORY_READ, MEMORY_WRITE}:
        return "memory"
    if event.event_type == WARNING_RAISED:
        return "warnings"
    if event.event_type == EXCEPTION_RAISED:
        return "errors"
    if event.event_type == RETRY_RECORDED:
        return "retries"
    if event.event_type == TOKEN_USAGE_RECORDED:
        return "token_usage"
    if event.event_type == COST_RECORDED:
        return "cost"
    if event.event_type == LATENCY_RECORDED:
        return "latency"
    return default


def _event_payload_severity(event: EventRecord) -> DiffSeverity:
    """Return default payload severity for an event."""
    if event.event_type in {
        USER_PROMPT,
        SYSTEM_PROMPT,
        ASSISTANT_RESPONSE,
        TOOL_STARTED,
        TOOL_FINISHED,
        TOOL_FAILED,
        EXCEPTION_RAISED,
    }:
        return "high"
    if event.event_type in {
        LLM_REQUEST,
        LLM_RESPONSE,
        FUNCTION_CALL,
        TOKEN_USAGE_RECORDED,
        COST_RECORDED,
        RETRY_RECORDED,
    }:
        return "medium"
    return "low"


def _event_presence_severity(event: EventRecord) -> DiffSeverity:
    """Return severity for a missing or extra event."""
    if event.event_type in {
        EXCEPTION_RAISED,
        TOOL_FAILED,
        ASSISTANT_RESPONSE,
        USER_PROMPT,
        SYSTEM_PROMPT,
    }:
        return "high"
    if event.event_type in {WARNING_RAISED, RETRY_RECORDED, TOKEN_USAGE_RECORDED}:
        return "medium"
    return "low"


def _category_for_location(
    default: str,
    location: str,
    event_type: str | None,
) -> str:
    """Map well-known fields to specific comparison categories."""
    if location.endswith(".prompt"):
        return "system_prompt" if event_type == SYSTEM_PROMPT else "prompt"
    if location.endswith(".response"):
        return "assistant_response" if event_type == ASSISTANT_RESPONSE else "llm"
    if ".tool_name" in location or ".arguments" in location:
        return "tool_calls"
    if ".result" in location and event_type in {TOOL_FINISHED, FUNCTION_CALL}:
        return "tool_outputs" if event_type == TOOL_FINISHED else "function_calls"
    if ".function_name" in location:
        return "function_calls"
    if ".key" in location or ".value" in location:
        return "memory"
    if ".token_usage" in location or "tokens" in location:
        return "token_usage"
    if ".cost" in location or ".amount" in location or ".currency" in location:
        return "cost"
    if ".latency_ms" in location:
        return "latency"
    if ".model_name" in location:
        return "model"
    if ".provider_name" in location:
        return "provider"
    if ".exception" in location:
        return "errors"
    if ".message" in location and event_type == WARNING_RAISED:
        return "warnings"
    return default


def _severity_for_location(
    default: DiffSeverity,
    location: str,
    event_type: str | None,
) -> DiffSeverity:
    """Return severity for a changed field."""
    if ".prompt" in location or (
        ".response" in location and event_type == ASSISTANT_RESPONSE
    ):
        return "high"
    if ".tool_name" in location or ".result" in location or ".exception" in location:
        return "high"
    if any(
        marker in location
        for marker in (
            ".model_name",
            ".provider_name",
            ".token_usage",
            ".cost",
            ".latency_ms",
            "tokens",
        )
    ):
        return "medium"
    return default


def _description_for(location: str, category: str, change_type: str) -> str:
    """Return a concise description for a changed location."""
    field = location.rsplit(".", maxsplit=1)[-1]
    if category == "prompt":
        return "Prompt changed."
    if category == "system_prompt":
        return "System prompt changed."
    if category == "assistant_response":
        return "Final assistant response changed."
    if category == "model":
        return "Model changed."
    if category == "provider":
        return "Provider changed."
    if category == "tool_calls" and field == "tool_name":
        return "Different tool selected."
    if category == "tool_outputs":
        return "Tool output changed."
    if category == "latency":
        return "Latency changed."
    if category == "token_usage":
        return "Token usage changed."
    if category == "cost":
        return "Cost changed."
    if category == "warnings":
        return "Warning changed."
    if category == "errors":
        return "Error changed."
    return f"{_title(field)} {change_type}."


def _numeric_severity(old_value: float, new_value: float) -> DiffSeverity:
    """Return a severity for a numeric delta."""
    delta = abs(new_value - old_value)
    baseline = max(abs(old_value), 1.0)
    if delta >= 1000.0 or delta / baseline >= 0.5:
        return "medium"
    return "low"


def _diff_warnings(
    left: TraceSnapshot,
    right: TraceSnapshot,
) -> tuple[str, ...]:
    """Return run-level warnings about comparison quality."""
    warnings: list[str] = []
    if left.run.status == "running" or right.run.status == "running":
        warnings.append("At least one run appears to be a partial recording.")
    if not left.events or not right.events:
        warnings.append("At least one run has no recorded events.")
    return tuple(warnings)


def _require_event(event: EventRecord | None) -> EventRecord:
    """Return an event from a match or raise a diff error."""
    if event is None:
        msg = "Internal diff alignment produced an empty event."
        raise DiffError(msg)
    return event


def _json_value(value: object) -> JSONValue:
    """Cast known recorded values into the shared JSON value type."""
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if _is_sequence(value):
        return [_json_value(item) for item in cast(Sequence[object], value)]
    return repr(value)


def _is_sequence(value: object) -> bool:
    """Return whether value should be compared as a JSON sequence."""
    return isinstance(value, Sequence) and not isinstance(
        value,
        str | bytes | bytearray,
    )


def _title(value: str) -> str:
    """Return a readable title for a dotted or snake-case location segment."""
    return value.rsplit(".", maxsplit=1)[-1].replace("_", " ").title()


__all__ = ["DiffEngine", "DiffInput"]
