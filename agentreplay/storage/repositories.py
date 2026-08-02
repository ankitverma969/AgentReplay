"""Repository implementations for AgentReplay SQLite storage."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from types import MappingProxyType
from typing import Any, cast

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.exceptions import StorageError
from agentreplay.storage.base import EventQuery, RunQuery
from agentreplay.storage.connection import SQLiteConnectionManager
from agentreplay.types import JSONValue, Metadata

OwnerType = str

_RUN_SORT_COLUMNS = {
    "started_at": "started_at",
    "ended_at": "ended_at",
    "duration_ms": "duration_ms",
    "name": "name",
    "status": "status",
}
_EVENT_SORT_COLUMNS = {
    "sequence": "sequence",
    "timestamp": "timestamp",
    "duration_ms": "duration_ms",
    "event_type": "event_type",
}


class MetadataRepository:
    """Persist and load normalized metadata rows."""

    def replace_metadata(
        self,
        connection: sqlite3.Connection,
        *,
        owner_type: OwnerType,
        owner_id: str,
        metadata: Mapping[str, JSONValue],
    ) -> None:
        """Replace metadata for an owner."""
        self.delete_metadata(connection, owner_type=owner_type, owner_id=owner_id)
        if not metadata:
            return
        rows = [
            (owner_type, owner_id, key, _json_dumps(value))
            for key, value in metadata.items()
        ]
        connection.executemany(
            """
            INSERT INTO metadata(owner_type, owner_id, key, value_json)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )

    def load_metadata(
        self,
        connection: sqlite3.Connection,
        *,
        owner_type: OwnerType,
        owner_id: str,
    ) -> Metadata:
        """Load metadata for an owner."""
        rows = connection.execute(
            """
            SELECT key, value_json
            FROM metadata
            WHERE owner_type = ? AND owner_id = ?
            ORDER BY key ASC
            """,
            (owner_type, owner_id),
        ).fetchall()
        return {str(row["key"]): _json_loads(str(row["value_json"])) for row in rows}

    def delete_metadata(
        self,
        connection: sqlite3.Connection,
        *,
        owner_type: OwnerType,
        owner_id: str,
    ) -> int:
        """Delete metadata for an owner."""
        cursor = connection.execute(
            "DELETE FROM metadata WHERE owner_type = ? AND owner_id = ?",
            (owner_type, owner_id),
        )
        return cursor.rowcount


class RunRepository:
    """Repository for run records and run tags."""

    def __init__(self, metadata_repository: MetadataRepository) -> None:
        """Create a run repository."""
        self._metadata_repository = metadata_repository

    def create(self, connection: sqlite3.Connection, run: RunRecord) -> None:
        """Insert a new run."""
        try:
            self._insert_run(connection, run)
        except sqlite3.IntegrityError as exc:
            msg = f"AgentReplay run already exists: {run.run_id}"
            raise StorageError(msg) from exc
        self._replace_tags(connection, run)
        self._metadata_repository.replace_metadata(
            connection,
            owner_type="run",
            owner_id=run.run_id,
            metadata=run.metadata,
        )

    def update(self, connection: sqlite3.Connection, run: RunRecord) -> None:
        """Update an existing run."""
        cursor = connection.execute(
            """
            UPDATE runs
            SET name = ?,
                status = ?,
                started_at = ?,
                ended_at = ?,
                duration_ms = ?,
                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE run_id = ?
            """,
            (
                run.name,
                run.status,
                run.started_at.isoformat(),
                run.ended_at.isoformat() if run.ended_at else None,
                run.duration_ms,
                run.run_id,
            ),
        )
        if cursor.rowcount == 0:
            msg = f"Unknown AgentReplay run id: {run.run_id}"
            raise StorageError(msg)
        self._replace_tags(connection, run)
        self._metadata_repository.replace_metadata(
            connection,
            owner_type="run",
            owner_id=run.run_id,
            metadata=run.metadata,
        )

    def save(self, connection: sqlite3.Connection, run: RunRecord) -> None:
        """Create or update a run."""
        connection.execute(
            """
            INSERT INTO runs(
                run_id, name, status, started_at, ended_at, duration_ms, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            ON CONFLICT(run_id) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                started_at = excluded.started_at,
                ended_at = excluded.ended_at,
                duration_ms = excluded.duration_ms,
                updated_at = excluded.updated_at
            """,
            _run_values(run),
        )
        self._replace_tags(connection, run)
        self._metadata_repository.replace_metadata(
            connection,
            owner_type="run",
            owner_id=run.run_id,
            metadata=run.metadata,
        )

    def delete(self, connection: sqlite3.Connection, run_id: str) -> None:
        """Delete a run and its normalized metadata."""
        event_rows = connection.execute(
            "SELECT event_id FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        for row in event_rows:
            self._metadata_repository.delete_metadata(
                connection,
                owner_type="event",
                owner_id=str(row["event_id"]),
            )
        self._metadata_repository.delete_metadata(
            connection,
            owner_type="run",
            owner_id=run_id,
        )
        connection.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def load(self, connection: sqlite3.Connection, run_id: str) -> RunRecord | None:
        """Load a run by id."""
        row = connection.execute(
            """
            SELECT run_id, name, status, started_at, ended_at, duration_ms
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_run(connection, row)

    def search(
        self, connection: sqlite3.Connection, query: RunQuery
    ) -> tuple[RunRecord, ...]:
        """Search runs with filtering, pagination, and sorting."""
        where, where_params = _run_where(query)
        params = list(where_params)
        sort_column = _RUN_SORT_COLUMNS[query.sort_by]
        direction = query.sort_direction.upper()
        sql = (
            "SELECT run_id, name, status, started_at, ended_at, duration_ms "
            "FROM runs "
            f"{where} "
            f"ORDER BY {sort_column} {direction}, run_id ASC"  # nosec B608
        )
        if query.pagination.limit is not None:
            sql = f"{sql} LIMIT ? OFFSET ?"
            params.extend((query.pagination.limit, query.pagination.offset))
        elif query.pagination.offset:
            sql = f"{sql} LIMIT -1 OFFSET ?"
            params.append(query.pagination.offset)
        rows = connection.execute(sql, tuple(params)).fetchall()
        return tuple(self._row_to_run(connection, row) for row in rows)

    def _insert_run(self, connection: sqlite3.Connection, run: RunRecord) -> None:
        """Insert the run row."""
        connection.execute(
            """
            INSERT INTO runs(
                run_id, name, status, started_at, ended_at, duration_ms, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
            """,
            _run_values(run),
        )

    def _replace_tags(self, connection: sqlite3.Connection, run: RunRecord) -> None:
        """Replace normalized tags for a run."""
        connection.execute("DELETE FROM run_tags WHERE run_id = ?", (run.run_id,))
        connection.executemany(
            "INSERT OR IGNORE INTO run_tags(run_id, tag, position) VALUES (?, ?, ?)",
            [(run.run_id, tag, position) for position, tag in enumerate(run.tags)],
        )

    def _load_tags(
        self, connection: sqlite3.Connection, run_id: str
    ) -> tuple[str, ...]:
        """Load normalized tags for a run."""
        rows = connection.execute(
            "SELECT tag FROM run_tags WHERE run_id = ? ORDER BY position ASC, tag ASC",
            (run_id,),
        ).fetchall()
        return tuple(str(row["tag"]) for row in rows)

    def _row_to_run(
        self, connection: sqlite3.Connection, row: sqlite3.Row
    ) -> RunRecord:
        """Convert a SQLite row to a run record."""
        run_id = str(row["run_id"])
        return RunRecord(
            run_id=run_id,
            name=_optional_str(row["name"]),
            status=cast(RunStatus, str(row["status"])),
            started_at=_parse_datetime(str(row["started_at"])),
            ended_at=_parse_optional_datetime(row["ended_at"]),
            duration_ms=float(row["duration_ms"]),
            metadata=self._metadata_repository.load_metadata(
                connection,
                owner_type="run",
                owner_id=run_id,
            ),
            tags=self._load_tags(connection, run_id),
        )


class EventRepository:
    """Repository for event records."""

    def __init__(self, metadata_repository: MetadataRepository) -> None:
        """Create an event repository."""
        self._metadata_repository = metadata_repository

    def save(self, connection: sqlite3.Connection, event: EventRecord) -> None:
        """Create or update an event."""
        connection.execute(
            """
            INSERT INTO events(
                event_id,
                run_id,
                parent_event_id,
                sequence,
                event_type,
                timestamp,
                duration_ms,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                run_id = excluded.run_id,
                parent_event_id = excluded.parent_event_id,
                sequence = excluded.sequence,
                event_type = excluded.event_type,
                timestamp = excluded.timestamp,
                duration_ms = excluded.duration_ms,
                payload_json = excluded.payload_json
            """,
            _event_values(event),
        )
        self._metadata_repository.replace_metadata(
            connection,
            owner_type="event",
            owner_id=event.event_id,
            metadata=event.metadata,
        )

    def bulk_insert(
        self, connection: sqlite3.Connection, events: Iterable[EventRecord]
    ) -> int:
        """Create or update multiple events."""
        event_list = tuple(events)
        if not event_list:
            return 0
        connection.executemany(
            """
            INSERT INTO events(
                event_id,
                run_id,
                parent_event_id,
                sequence,
                event_type,
                timestamp,
                duration_ms,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                run_id = excluded.run_id,
                parent_event_id = excluded.parent_event_id,
                sequence = excluded.sequence,
                event_type = excluded.event_type,
                timestamp = excluded.timestamp,
                duration_ms = excluded.duration_ms,
                payload_json = excluded.payload_json
            """,
            [_event_values(event) for event in event_list],
        )
        for event in event_list:
            self._metadata_repository.replace_metadata(
                connection,
                owner_type="event",
                owner_id=event.event_id,
                metadata=event.metadata,
            )
        return len(event_list)

    def load(
        self, connection: sqlite3.Connection, query: EventQuery
    ) -> tuple[EventRecord, ...]:
        """Load events matching an event query."""
        return tuple(self.iter_rows(connection, query))

    def stream(
        self,
        connection_manager: SQLiteConnectionManager,
        query: EventQuery,
        *,
        batch_size: int,
    ) -> Iterator[EventRecord]:
        """Stream events matching a query in batches."""
        if batch_size <= 0:
            msg = "Event stream batch size must be greater than zero."
            raise ValueError(msg)
        with connection_manager.lock:
            connection = connection_manager.get_connection()
            cursor = connection.execute(*_event_select(query, include_pagination=True))
            while True:
                rows = cursor.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield self._row_to_event(connection, row)

    def iter_rows(
        self,
        connection: sqlite3.Connection,
        query: EventQuery,
    ) -> Iterator[EventRecord]:
        """Iterate events for a query using the active connection."""
        cursor = connection.execute(*_event_select(query, include_pagination=True))
        for row in cursor:
            yield self._row_to_event(connection, row)

    def delete_for_run(self, connection: sqlite3.Connection, run_id: str) -> int:
        """Delete all events and event metadata for a run."""
        event_rows = connection.execute(
            "SELECT event_id FROM events WHERE run_id = ?",
            (run_id,),
        ).fetchall()
        for row in event_rows:
            self._metadata_repository.delete_metadata(
                connection,
                owner_type="event",
                owner_id=str(row["event_id"]),
            )
        cursor = connection.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
        return cursor.rowcount

    def _row_to_event(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> EventRecord:
        """Convert a SQLite row to an event record."""
        event_id = str(row["event_id"])
        payload = _json_loads(str(row["payload_json"]))
        if not isinstance(payload, Mapping):
            msg = f"Stored AgentReplay event payload is not an object: {event_id}"
            raise StorageError(msg)
        return EventRecord(
            event_id=event_id,
            run_id=str(row["run_id"]),
            parent_event_id=_optional_str(row["parent_event_id"]),
            sequence=int(row["sequence"]),
            event_type=str(row["event_type"]),
            timestamp=_parse_datetime(str(row["timestamp"])),
            duration_ms=float(row["duration_ms"]),
            metadata=self._metadata_repository.load_metadata(
                connection,
                owner_type="event",
                owner_id=event_id,
            ),
            payload=payload,
        )


def _run_values(run: RunRecord) -> tuple[str, str | None, str, str, str | None, float]:
    """Return SQLite values for a run."""
    return (
        run.run_id,
        run.name,
        run.status,
        run.started_at.isoformat(),
        run.ended_at.isoformat() if run.ended_at else None,
        run.duration_ms,
    )


def _event_values(
    event: EventRecord,
) -> tuple[str, str, str | None, int, str, str, float, str]:
    """Return SQLite values for an event."""
    return (
        event.event_id,
        event.run_id,
        event.parent_event_id,
        event.sequence,
        event.event_type,
        event.timestamp.isoformat(),
        event.duration_ms,
        _json_dumps(event.payload),
    )


def _run_where(query: RunQuery) -> tuple[str, tuple[object, ...]]:
    """Build a safe WHERE clause for run searches."""
    clauses: list[str] = []
    params: list[object] = []
    if query.statuses:
        clauses.append(f"status IN ({_placeholders(len(query.statuses))})")
        params.extend(query.statuses)
    if query.name_contains:
        clauses.append("name LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(query.name_contains)}%")
    if query.started_at_or_after:
        clauses.append("started_at >= ?")
        params.append(query.started_at_or_after.isoformat())
    if query.started_before:
        clauses.append("started_at < ?")
        params.append(query.started_before.isoformat())
    for tag in query.tags:
        clauses.append(
            """
            EXISTS (
                SELECT 1 FROM run_tags
                WHERE run_tags.run_id = runs.run_id AND run_tags.tag = ?
            )
            """,
        )
        params.append(tag)
    if query.metadata_equals:
        for key, value in query.metadata_equals.items():
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM metadata
                    WHERE metadata.owner_type = 'run'
                    AND metadata.owner_id = runs.run_id
                    AND metadata.key = ?
                    AND metadata.value_json = ?
                )
                """,
            )
            params.extend((key, _json_dumps(value)))
    if not clauses:
        return "", ()
    return f"WHERE {' AND '.join(clauses)}", tuple(params)


def _event_select(
    query: EventQuery,
    *,
    include_pagination: bool,
) -> tuple[str, tuple[object, ...]]:
    """Build a safe SELECT statement for event queries."""
    clauses = ["run_id = ?"]
    params: list[object] = [query.run_id]
    if query.event_types:
        clauses.append(f"event_type IN ({_placeholders(len(query.event_types))})")
        params.extend(query.event_types)
    if query.parent_event_id is not None:
        clauses.append("parent_event_id = ?")
        params.append(query.parent_event_id)
    if query.timestamp_at_or_after:
        clauses.append("timestamp >= ?")
        params.append(query.timestamp_at_or_after.isoformat())
    if query.timestamp_before:
        clauses.append("timestamp < ?")
        params.append(query.timestamp_before.isoformat())
    if query.metadata_equals:
        for key, value in query.metadata_equals.items():
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM metadata
                    WHERE metadata.owner_type = 'event'
                    AND metadata.owner_id = events.event_id
                    AND metadata.key = ?
                    AND metadata.value_json = ?
                )
                """,
            )
            params.extend((key, _json_dumps(value)))
    sort_column = _EVENT_SORT_COLUMNS[query.sort_by]
    direction = query.sort_direction.upper()
    sql = (
        "SELECT event_id, run_id, parent_event_id, sequence, event_type, "
        "timestamp, duration_ms, payload_json "
        "FROM events "
        f"WHERE {' AND '.join(clauses)} "
        f"ORDER BY {sort_column} {direction}, sequence ASC, event_id ASC"  # nosec B608
    )
    if include_pagination and query.pagination.limit is not None:
        sql = f"{sql} LIMIT ? OFFSET ?"
        params.extend((query.pagination.limit, query.pagination.offset))
    elif include_pagination and query.pagination.offset:
        sql = f"{sql} LIMIT -1 OFFSET ?"
        params.append(query.pagination.offset)
    return sql, tuple(params)


def _placeholders(count: int) -> str:
    """Return SQL placeholders for a non-empty sequence."""
    return ", ".join("?" for _ in range(count))


def _escape_like(value: str) -> str:
    """Escape SQLite LIKE wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _json_dumps(value: JSONValue | Mapping[str, JSONValue]) -> str:
    """Serialize a JSON-compatible value for storage."""
    return json.dumps(_json_ready(value), sort_keys=True, separators=(",", ":"))


def _json_loads(value: str) -> JSONValue:
    """Deserialize a JSON-compatible value from storage."""
    loaded: Any = json.loads(value)
    return cast(JSONValue, loaded)


def _json_ready(value: object) -> object:
    """Return a JSON-serializable equivalent for immutable mapping snapshots."""
    if isinstance(value, Mapping | MappingProxyType):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    return value


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO timestamp stored by AgentReplay."""
    return datetime.fromisoformat(value)


def _parse_optional_datetime(value: object) -> datetime | None:
    """Parse an optional ISO timestamp stored by AgentReplay."""
    if value is None:
        return None
    return _parse_datetime(str(value))


def _optional_str(value: object) -> str | None:
    """Convert a SQLite optional text value."""
    return None if value is None else str(value)


__all__ = ["EventRepository", "MetadataRepository", "RunRepository"]
