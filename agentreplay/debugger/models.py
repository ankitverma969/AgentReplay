"""Typed models used by the AgentReplay interactive debugger."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue

SearchField: TypeAlias = Literal[
    "prompt",
    "model",
    "tool",
    "provider",
    "event_type",
    "metadata",
    "error",
    "warning",
]
EventExportFormat: TypeAlias = Literal["json", "markdown", "html", "clipboard"]
DebuggerTheme: TypeAlias = Literal["dark", "light"]


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Search expression and target fields for debugger event search."""

    text: str
    fields: tuple[SearchField, ...] = (
        "prompt",
        "model",
        "tool",
        "provider",
        "event_type",
        "metadata",
        "error",
        "warning",
    )
    regex: bool = False
    case_sensitive: bool = False

    def __post_init__(self) -> None:
        """Validate search query values."""
        if not self.text:
            msg = "Search text must not be empty."
            raise ValueError(msg)
        if not self.fields:
            msg = "At least one search field is required."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SearchMatch:
    """One debugger search hit."""

    entry_index: int
    event_id: str
    field: SearchField
    excerpt: str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of this match."""
        return {
            "entry_index": self.entry_index,
            "event_id": self.event_id,
            "field": self.field,
            "excerpt": self.excerpt,
        }


@dataclass(frozen=True, slots=True)
class DebuggerFilter:
    """Event filters supported by the interactive debugger."""

    errors: bool = False
    warnings: bool = False
    tool_events: bool = False
    llm_events: bool = False
    memory_events: bool = False
    slow_events: bool = False
    expensive_events: bool = False
    retries: bool = False
    slow_threshold_ms: float = 1_000.0
    expensive_threshold: float = 1.0

    @property
    def active(self) -> bool:
        """Return whether any event filter is enabled."""
        return any(
            (
                self.errors,
                self.warnings,
                self.tool_events,
                self.llm_events,
                self.memory_events,
                self.slow_events,
                self.expensive_events,
                self.retries,
            )
        )


@dataclass(frozen=True, slots=True)
class DebuggerStats:
    """Aggregate execution statistics displayed by the debugger."""

    total_events: int
    latency_ms: float
    cost: float
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    retries: int
    warnings: int
    errors: int
    slowest_tool_event_id: str | None
    slowest_tool_ms: float
    largest_prompt_event_id: str | None
    largest_prompt_chars: int
    largest_response_event_id: str | None
    largest_response_chars: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of debugger statistics."""
        return {
            "total_events": self.total_events,
            "latency_ms": self.latency_ms,
            "cost": self.cost,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "retries": self.retries,
            "warnings": self.warnings,
            "errors": self.errors,
            "slowest_tool_event_id": self.slowest_tool_event_id,
            "slowest_tool_ms": self.slowest_tool_ms,
            "largest_prompt_event_id": self.largest_prompt_event_id,
            "largest_prompt_chars": self.largest_prompt_chars,
            "largest_response_event_id": self.largest_response_event_id,
            "largest_response_chars": self.largest_response_chars,
        }


@dataclass(frozen=True, slots=True)
class EventInspection:
    """Structured details for the currently selected debugger event."""

    event_id: str
    event_type: str
    timestamp: str
    duration_ms: float
    parent_event_id: str | None
    children: tuple[str, ...]
    payload: dict[str, JSONValue]
    metadata: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of this inspection."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "parent_event_id": self.parent_event_id,
            "children": list(self.children),
            "payload": self.payload,
            "metadata": self.metadata,
        }


__all__ = [
    "DebuggerFilter",
    "DebuggerStats",
    "DebuggerTheme",
    "EventExportFormat",
    "EventInspection",
    "SearchField",
    "SearchMatch",
    "SearchQuery",
]
