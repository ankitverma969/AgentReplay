"""SQLite storage backend for AgentReplay."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from agentreplay.config import get_settings
from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.storage.base import (
    EventQuery,
    Pagination,
    RunQuery,
    RunSortField,
    SortDirection,
)
from agentreplay.storage.connection import SQLiteConnectionManager
from agentreplay.storage.repositories import (
    EventRepository,
    MetadataRepository,
    RunRepository,
)
from agentreplay.storage.schema import apply_migrations
from agentreplay.storage.transactions import SQLiteTransactionManager


class SQLiteStorage:
    """Production-oriented local SQLite storage backend for AgentReplay."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        connection_manager: SQLiteConnectionManager | None = None,
        transaction_manager: SQLiteTransactionManager | None = None,
    ) -> None:
        """Create and initialize a SQLite storage backend."""
        resolved_path = get_settings().db_path if db_path is None else db_path
        self._connection_manager = (
            SQLiteConnectionManager(resolved_path)
            if connection_manager is None
            else connection_manager
        )
        self._transaction_manager = (
            SQLiteTransactionManager(self._connection_manager)
            if transaction_manager is None
            else transaction_manager
        )
        self._metadata_repository = MetadataRepository()
        self._run_repository = RunRepository(self._metadata_repository)
        self._event_repository = EventRepository(self._metadata_repository)
        self.initialize()

    @property
    def db_path(self) -> Path:
        """Return the SQLite database path."""
        return self._connection_manager.db_path

    def initialize(self) -> None:
        """Apply pending schema migrations."""
        with self._transaction_manager.transaction() as connection:
            apply_migrations(connection)

    def create_run(self, run: RunRecord) -> None:
        """Persist a new run."""
        with self._transaction_manager.transaction() as connection:
            self._run_repository.create(connection, run)

    def update_run(self, run: RunRecord) -> None:
        """Update an existing run."""
        with self._transaction_manager.transaction() as connection:
            self._run_repository.update(connection, run)

    def save_run(self, run: RunRecord) -> None:
        """Create or update a run."""
        with self._transaction_manager.transaction() as connection:
            self._run_repository.save(connection, run)

    def delete_run(self, run_id: str) -> None:
        """Delete a run and its events."""
        with self._transaction_manager.transaction() as connection:
            self._run_repository.delete(connection, run_id)

    def load_run(self, run_id: str) -> RunRecord | None:
        """Load a run by id."""
        with self._transaction_manager.connection() as connection:
            return self._run_repository.load(connection, run_id)

    def list_runs(
        self,
        *,
        pagination: Pagination | None = None,
        sort_by: RunSortField = "started_at",
        sort_direction: SortDirection = "desc",
    ) -> tuple[RunRecord, ...]:
        """Load runs with pagination and sorting."""
        return self.search_runs(
            RunQuery(
                pagination=Pagination() if pagination is None else pagination,
                sort_by=sort_by,
                sort_direction=sort_direction,
            ),
        )

    def search_runs(self, query: RunQuery) -> tuple[RunRecord, ...]:
        """Search runs with filtering, pagination, and sorting."""
        with self._transaction_manager.connection() as connection:
            return self._run_repository.search(connection, query)

    def save_event(self, event: EventRecord) -> None:
        """Persist a single event."""
        with self._transaction_manager.transaction() as connection:
            self._event_repository.save(connection, event)

    def bulk_insert_events(self, events: Iterable[EventRecord]) -> int:
        """Persist multiple events and return the inserted count."""
        with self._transaction_manager.transaction() as connection:
            return self._event_repository.bulk_insert(connection, events)

    def load_events(
        self,
        run_id: str,
        *,
        query: EventQuery | None = None,
    ) -> tuple[EventRecord, ...]:
        """Load events for one run."""
        resolved_query = EventQuery(run_id=run_id) if query is None else query
        with self._transaction_manager.connection() as connection:
            return self._event_repository.load(connection, resolved_query)

    def stream_events(
        self,
        run_id: str,
        *,
        query: EventQuery | None = None,
        batch_size: int = 100,
    ) -> Iterator[EventRecord]:
        """Stream events for one run without loading all rows at once."""
        resolved_query = EventQuery(run_id=run_id) if query is None else query
        return self._event_repository.stream(
            self._connection_manager,
            resolved_query,
            batch_size=batch_size,
        )

    def delete_events(self, run_id: str) -> int:
        """Delete events for a run and return the deleted count."""
        with self._transaction_manager.transaction() as connection:
            return self._event_repository.delete_for_run(connection, run_id)

    def close(self) -> None:
        """Close the SQLite connection."""
        self._connection_manager.close()

    def __enter__(self) -> SQLiteStorage:
        """Enter the SQLite storage context."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Close storage resources when leaving a context."""
        self.close()


__all__ = ["SQLiteStorage"]
