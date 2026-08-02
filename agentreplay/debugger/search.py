"""Fast search helpers for debugger timelines."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from re import Pattern

from agentreplay.core.events import (
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    SYSTEM_PROMPT,
    TOOL_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
)
from agentreplay.debugger.models import SearchField, SearchMatch, SearchQuery
from agentreplay.replay.playback import TimelineEntry
from agentreplay.types import JSONValue, Metadata

_PROMPT_KEYS = frozenset(("prompt", "messages", "input", "instructions"))
_MODEL_KEYS = frozenset(("model", "model_name"))
_TOOL_KEYS = frozenset(("tool", "tool_name", "function_name", "name"))
_PROVIDER_KEYS = frozenset(("provider", "provider_name"))
_ERROR_KEYS = frozenset(("error", "errors", "exception", "traceback"))
_WARNING_KEYS = frozenset(("warning", "warnings", "message"))


def search_entries(
    entries: Iterable[TimelineEntry],
    query: SearchQuery,
) -> tuple[SearchMatch, ...]:
    """Search timeline entries and return matching locations."""
    matcher = _compile_matcher(query)
    matches: list[SearchMatch] = []
    for entry in entries:
        for field in query.fields:
            text = _field_text(entry, field)
            if not text:
                continue
            found = matcher.search(text)
            if found is None:
                continue
            matches.append(
                SearchMatch(
                    entry_index=entry.index,
                    event_id=entry.event.event_id,
                    field=field,
                    excerpt=_excerpt(text, found.start(), found.end()),
                )
            )
    return tuple(matches)


def _compile_matcher(query: SearchQuery) -> Pattern[str]:
    """Compile a search matcher for literal or regex matching."""
    flags = 0 if query.case_sensitive else re.IGNORECASE
    pattern = query.text if query.regex else re.escape(query.text)
    try:
        return re.compile(pattern, flags)
    except re.error as exc:
        msg = f"Invalid debugger search regex: {query.text}"
        raise ValueError(msg) from exc


def _field_text(entry: TimelineEntry, field: SearchField) -> str:
    """Return searchable text for a single field."""
    event = entry.event
    if field == "event_type":
        return event.event_type
    if field == "metadata":
        return _json_text(event.metadata)
    if field == "prompt":
        if event.event_type in {USER_PROMPT, SYSTEM_PROMPT, LLM_REQUEST}:
            return _selected_mapping_text(event.payload, _PROMPT_KEYS)
        return ""
    if field == "model":
        if event.event_type in {LLM_REQUEST, LLM_RESPONSE}:
            return _selected_mapping_text(event.payload, _MODEL_KEYS)
        return ""
    if field == "tool":
        if event.event_type in {TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED}:
            return _selected_mapping_text(event.payload, _TOOL_KEYS)
        return ""
    if field == "provider":
        if event.event_type in {LLM_REQUEST, LLM_RESPONSE}:
            return _selected_mapping_text(event.payload, _PROVIDER_KEYS)
        return ""
    if field == "error":
        if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
            return _selected_mapping_text(event.payload, _ERROR_KEYS)
        return ""
    if event.event_type == WARNING_RAISED:
        return _selected_mapping_text(event.payload, _WARNING_KEYS)
    return ""


def _selected_mapping_text(metadata: Metadata, keys: frozenset[str]) -> str:
    """Extract searchable text for selected mapping keys."""
    values: list[JSONValue] = []
    for key, value in metadata.items():
        normalized = key.lower()
        if normalized in keys or any(marker in normalized for marker in keys):
            values.append(value)
    if not values:
        return _json_text(metadata)
    return " ".join(_json_text(value) for value in values)


def _json_text(value: object) -> str:
    """Convert JSON-like values to deterministic searchable text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


def _excerpt(text: str, start: int, end: int, *, radius: int = 48) -> str:
    """Build a compact match excerpt."""
    lower = max(0, start - radius)
    upper = min(len(text), end + radius)
    prefix = "..." if lower else ""
    suffix = "..." if upper < len(text) else ""
    return f"{prefix}{text[lower:upper]}{suffix}"


__all__ = ["search_entries"]
