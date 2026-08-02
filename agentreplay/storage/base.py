"""Storage backend contracts and query models for AgentReplay."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from agentreplay.core.events import EventRecord, EventType
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.types import JSONValue

SortDirection = Literal["asc", "desc"]
RunSortField = Literal["started_at", "ended_at", "duration_ms", "name", "status"]
EventSortField = Literal["sequence", "timestamp", "duration_ms", "event_type"]


@dataclass(frozen=True, slots=True)
class Pagination:
    """Pagination options for storage queries."""

    limit: int | None = None
    offset: int = 0

    def __post_init__(self) -> None:
        """Validate pagination values."""
        if self.limit is not None and self.limit <= 0:
            msg = "Pagination limit must be greater than zero."
            raise ValueError(msg)
        if self.offset < 0:
            msg = "Pagination offset must be zero or greater."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class RunQuery:
    """Filter and sorting options for run searches."""

    statuses: tuple[RunStatus, ...] = ()
    name_contains: str | None = None
    started_at_or_after: datetime | None = None
    started_before: datetime | None = None
    tags: tuple[str, ...] = ()
    metadata_equals: Mapping[str, JSONValue] | None = None
    sort_by: RunSortField = "started_at"
    sort_direction: SortDirection = "desc"
    pagination: Pagination = Pagination()


@dataclass(frozen=True, slots=True)
class EventQuery:
    """Filter and sorting options for event loading."""

    run_id: str
    event_types: tuple[EventType, ...] = ()
    parent_event_id: str | None = None
    timestamp_at_or_after: datetime | None = None
    timestamp_before: datetime | None = None
    metadata_equals: Mapping[str, JSONValue] | None = None
    sort_by: EventSortField = "sequence"
    sort_direction: SortDirection = "asc"
    pagination: Pagination = Pagination()


class StorageBackend(Protocol):
    """Protocol implemented by AgentReplay persistence backends."""

    def create_run(self, run: RunRecord) -> None:
        """Persist a new run."""

    def update_run(self, run: RunRecord) -> None:
        """Update an existing run."""

    def save_run(self, run: RunRecord) -> None:
        """Create or update a run."""

    def delete_run(self, run_id: str) -> None:
        """Delete a run and its stored events."""

    def load_run(self, run_id: str) -> RunRecord | None:
        """Load a run by id."""

    def list_runs(
        self,
        *,
        pagination: Pagination | None = None,
        sort_by: RunSortField = "started_at",
        sort_direction: SortDirection = "desc",
    ) -> tuple[RunRecord, ...]:
        """Load runs with pagination and sorting."""

    def search_runs(self, query: RunQuery) -> tuple[RunRecord, ...]:
        """Search runs with filtering, pagination, and sorting."""

    def save_event(self, event: EventRecord) -> None:
        """Persist a single event."""

    def bulk_insert_events(self, events: Iterable[EventRecord]) -> int:
        """Persist multiple events and return the inserted count."""

    def load_events(
        self,
        run_id: str,
        *,
        query: EventQuery | None = None,
    ) -> tuple[EventRecord, ...]:
        """Load events for one run."""

    def stream_events(
        self,
        run_id: str,
        *,
        query: EventQuery | None = None,
        batch_size: int = 100,
    ) -> Iterator[EventRecord]:
        """Stream events for one run without loading all rows at once."""

    def delete_events(self, run_id: str) -> int:
        """Delete all events for a run and return the deleted count."""

    def close(self) -> None:
        """Release storage resources."""


__all__ = [
    "EventQuery",
    "EventSortField",
    "Pagination",
    "RunQuery",
    "RunSortField",
    "SortDirection",
    "StorageBackend",
]
