"""Execution statistics for AgentReplay debugger sessions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    RETRY_RECORDED,
    SYSTEM_PROMPT,
    TOOL_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
)
from agentreplay.debugger.models import DebuggerStats
from agentreplay.replay.playback import TimelineEntry

_PROMPT_KEYS = frozenset(("prompt", "messages", "input", "instructions"))
_RESPONSE_KEYS = frozenset(("response", "output", "result", "content"))
_TOOL_EVENTS = frozenset((TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED))


def calculate_stats(entries: Iterable[TimelineEntry]) -> DebuggerStats:
    """Calculate aggregate statistics from timeline entries."""
    total_events = 0
    latency_ms = 0.0
    cost = 0.0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    retries = 0
    warnings = 0
    errors = 0
    slowest_tool_event_id: str | None = None
    slowest_tool_ms = 0.0
    largest_prompt_event_id: str | None = None
    largest_prompt_chars = 0
    largest_response_event_id: str | None = None
    largest_response_chars = 0

    for entry in entries:
        total_events += 1
        event = entry.event
        latency_ms += max(event.duration_ms, 0.0)
        payload = event.payload
        cost += _cost(payload)
        prompt_tokens += _int_value(_nested_value(payload, "prompt_tokens"))
        completion_tokens += _int_value(_nested_value(payload, "completion_tokens"))
        total_tokens += _int_value(_nested_value(payload, "total_tokens"))
        if event.event_type == RETRY_RECORDED:
            retries += 1
        if event.event_type == WARNING_RAISED:
            warnings += 1
        if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
            errors += 1
        if event.event_type in _TOOL_EVENTS and event.duration_ms >= slowest_tool_ms:
            slowest_tool_ms = event.duration_ms
            slowest_tool_event_id = event.event_id

        prompt_chars = _text_size(payload, _PROMPT_KEYS)
        if (
            event.event_type in {USER_PROMPT, SYSTEM_PROMPT, LLM_REQUEST}
            and prompt_chars >= largest_prompt_chars
        ):
            largest_prompt_chars = prompt_chars
            largest_prompt_event_id = event.event_id

        response_chars = _text_size(payload, _RESPONSE_KEYS)
        if (
            event.event_type in {ASSISTANT_RESPONSE, LLM_RESPONSE, TOOL_FINISHED}
            and response_chars >= largest_response_chars
        ):
            largest_response_chars = response_chars
            largest_response_event_id = event.event_id

    if total_tokens == 0:
        total_tokens = prompt_tokens + completion_tokens
    return DebuggerStats(
        total_events=total_events,
        latency_ms=latency_ms,
        cost=cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        retries=retries,
        warnings=warnings,
        errors=errors,
        slowest_tool_event_id=slowest_tool_event_id,
        slowest_tool_ms=slowest_tool_ms,
        largest_prompt_event_id=largest_prompt_event_id,
        largest_prompt_chars=largest_prompt_chars,
        largest_response_event_id=largest_response_event_id,
        largest_response_chars=largest_response_chars,
    )


def _nested_value(mapping: Mapping[str, object], key: str) -> object:
    """Find a value by key in a JSON-like mapping."""
    if key in mapping:
        return mapping[key]
    for value in mapping.values():
        if isinstance(value, Mapping):
            found = _nested_value(value, key)
            if found is not None:
                return found
    return None


def _int_value(value: object) -> int:
    """Convert a JSON-like value to an integer when possible."""
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


def _cost(mapping: Mapping[str, object]) -> float:
    """Read a cost amount from a payload mapping."""
    cost = mapping.get("cost")
    if isinstance(cost, Mapping):
        return _float_value(cost.get("amount"))
    return _float_value(cost) + _float_value(mapping.get("amount"))


def _float_value(value: object) -> float:
    """Convert a JSON-like value to a float when possible."""
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


def _text_size(mapping: Mapping[str, object], keys: frozenset[str]) -> int:
    """Return the largest text size under matching payload keys."""
    largest = 0
    for key, value in mapping.items():
        normalized = key.lower()
        if normalized in keys or any(marker in normalized for marker in keys):
            largest = max(largest, len(_stringify(value)))
    return largest


def _stringify(value: object) -> str:
    """Return a compact string representation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


__all__ = ["calculate_stats"]
