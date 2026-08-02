"""Chunked and windowed trace readers for massive AgentReplay runs."""

from __future__ import annotations

from datetime import datetime

from agentreplay.core.events import EventRecord
from agentreplay.performance.cache import LRUCache
from agentreplay.performance.models import TraceWindow
from agentreplay.storage import EventQuery, Pagination, SQLiteStorage, StorageBackend


class TraceWindowReader:
    """Load bounded event windows without materializing full traces."""

    def __init__(
        self,
        storage: StorageBackend,
        *,
        default_limit: int = 100,
        cache_size: int = 32,
    ) -> None:
        """Create a trace window reader."""
        if default_limit <= 0:
            msg = "Default window limit must be greater than zero."
            raise ValueError(msg)
        self._storage = storage
        self._default_limit = default_limit
        self._cache: LRUCache[tuple[str, int, int], TraceWindow] = LRUCache(cache_size)

    def first(self, run_id: str, *, limit: int | None = None) -> TraceWindow:
        """Load the first event window."""
        return self.window(run_id, offset=0, limit=limit)

    def next(self, window: TraceWindow) -> TraceWindow:
        """Load the next event window."""
        return self.window(window.run_id, offset=window.next_offset, limit=window.limit)

    def previous(self, window: TraceWindow) -> TraceWindow:
        """Load the previous event window."""
        return self.window(
            window.run_id,
            offset=window.previous_offset,
            limit=window.limit,
        )

    def window(
        self,
        run_id: str,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> TraceWindow:
        """Load an arbitrary sequence-ordered event window."""
        resolved_limit = self._resolve_limit(limit)
        if offset < 0:
            msg = "Window offset must be zero or greater."
            raise ValueError(msg)
        cache_key = (run_id, offset, resolved_limit)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        query = EventQuery(
            run_id=run_id,
            pagination=Pagination(limit=resolved_limit, offset=offset),
        )
        events = self._storage.load_events(run_id, query=query)
        result = TraceWindow(
            run_id=run_id,
            events=events,
            offset=offset,
            limit=resolved_limit,
        )
        self._cache.put(cache_key, result)
        return result

    def jump_to_event(
        self,
        run_id: str,
        event_id: str,
        *,
        limit: int | None = None,
    ) -> TraceWindow:
        """Load a window centered near a target event id."""
        event = find_event(self._storage, run_id, event_id)
        if event is None:
            return self.window(run_id, limit=limit)
        resolved_limit = self._resolve_limit(limit)
        offset = max(0, event.sequence - max(1, resolved_limit // 2) - 1)
        return self.window(run_id, offset=offset, limit=resolved_limit)

    def jump_to_timestamp(
        self,
        run_id: str,
        timestamp: datetime,
        *,
        limit: int | None = None,
    ) -> TraceWindow:
        """Load a window beginning at the first event at or after a timestamp."""
        resolved_limit = self._resolve_limit(limit)
        query = EventQuery(
            run_id=run_id,
            timestamp_at_or_after=timestamp,
            pagination=Pagination(limit=resolved_limit),
        )
        events = self._storage.load_events(run_id, query=query)
        offset = 0 if not events else max(0, events[0].sequence - 1)
        return TraceWindow(
            run_id=run_id,
            events=events,
            offset=offset,
            limit=resolved_limit,
        )

    def stream_chunks(
        self,
        run_id: str,
        *,
        chunk_size: int | None = None,
    ) -> list[TraceWindow]:
        """Load chunk descriptors incrementally for callers that need windows."""
        resolved_limit = self._resolve_limit(chunk_size)
        windows: list[TraceWindow] = []
        offset = 0
        while True:
            window = self.window(run_id, offset=offset, limit=resolved_limit)
            if not window.events:
                break
            windows.append(window)
            if len(window.events) < resolved_limit:
                break
            offset = window.next_offset
        return windows

    def clear_cache(self) -> None:
        """Clear cached windows."""
        self._cache.clear()

    def _resolve_limit(self, limit: int | None) -> int:
        """Resolve and validate a requested window size."""
        resolved = self._default_limit if limit is None else limit
        if resolved <= 0:
            msg = "Window limit must be greater than zero."
            raise ValueError(msg)
        return resolved


def partial_replay(
    storage: StorageBackend,
    run_id: str,
    *,
    offset: int = 0,
    limit: int = 100,
) -> tuple[EventRecord, ...]:
    """Return the visible event subset for windowed replay."""
    return (
        TraceWindowReader(storage, default_limit=limit)
        .window(
            run_id,
            offset=offset,
            limit=limit,
        )
        .events
    )


def find_event(
    storage: StorageBackend,
    run_id: str,
    event_id: str,
    *,
    batch_size: int = 5_000,
) -> EventRecord | None:
    """Find one event id by streaming through the run."""
    for event in storage.stream_events(run_id, batch_size=batch_size):
        if event.event_id == event_id:
            return event
    return None


def default_window_reader(
    db_path: str | None = None,
    *,
    limit: int = 100,
) -> TraceWindowReader:
    """Create a window reader backed by SQLite storage."""
    storage = SQLiteStorage() if db_path is None else SQLiteStorage(db_path)
    return TraceWindowReader(storage, default_limit=limit)


__all__ = [
    "TraceWindowReader",
    "default_window_reader",
    "find_event",
    "partial_replay",
]
