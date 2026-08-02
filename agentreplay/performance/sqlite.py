"""SQLite optimization and analysis utilities for massive traces."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agentreplay.exceptions import PerformanceError
from agentreplay.performance.models import SQLiteOptimizationReport
from agentreplay.storage import SQLiteStorage

_PERFORMANCE_INDEXES = (
    """
    CREATE INDEX IF NOT EXISTS idx_events_run_type_sequence
    ON events(run_id, event_type, sequence)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_run_timestamp_sequence
    ON events(run_id, timestamp, sequence)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_events_run_parent_sequence
    ON events(run_id, parent_event_id, sequence)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_metadata_event_key_value
    ON metadata(owner_type, key, value_json, owner_id)
    """,
)


class SQLiteOptimizer:
    """Apply SQLite tuning and report database statistics."""

    def __init__(self, storage: SQLiteStorage) -> None:
        """Create a SQLite optimizer."""
        self._storage = storage

    def optimize(
        self, *, analyze: bool = True, vacuum: bool = False
    ) -> SQLiteOptimizationReport:
        """Apply safe optimization statements and return database statistics."""
        connection = self._connection()
        try:
            for statement in _PERFORMANCE_INDEXES:
                connection.execute(statement)
            connection.execute("PRAGMA optimize")
            if analyze:
                connection.execute("ANALYZE")
            if vacuum:
                connection.execute("VACUUM")
        except sqlite3.Error as exc:
            msg = "Could not optimize AgentReplay SQLite database."
            raise PerformanceError(msg) from exc
        return self.analyze(analyzed=analyze, vacuumed=vacuum)

    def analyze(
        self, *, analyzed: bool = False, vacuumed: bool = False
    ) -> SQLiteOptimizationReport:
        """Return storage, index, and table statistics."""
        connection = self._connection()
        try:
            indexes = tuple(
                str(row["name"])
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'index' AND name NOT LIKE 'sqlite_autoindex%'
                    ORDER BY name ASC
                    """
                ).fetchall()
            )
            return SQLiteOptimizationReport(
                db_path=str(self._storage.db_path),
                page_count=_pragma_int(connection, "page_count"),
                page_size=_pragma_int(connection, "page_size"),
                freelist_count=_pragma_int(connection, "freelist_count"),
                event_count=_count(connection, "events"),
                run_count=_count(connection, "runs"),
                indexes=indexes,
                analyzed=analyzed,
                vacuumed=vacuumed,
            )
        except sqlite3.Error as exc:
            msg = "Could not analyze AgentReplay SQLite database."
            raise PerformanceError(msg) from exc

    def vacuum(self) -> SQLiteOptimizationReport:
        """Vacuum the SQLite database and return updated statistics."""
        return self.optimize(analyze=True, vacuum=True)

    def _connection(self) -> sqlite3.Connection:
        """Return the managed SQLite connection."""
        return self._storage._connection_manager.get_connection()


def optimize_sqlite(
    db_path: str | Path | None = None,
    *,
    analyze: bool = True,
    vacuum: bool = False,
) -> SQLiteOptimizationReport:
    """Optimize a SQLite database using the default storage backend."""
    storage = SQLiteStorage() if db_path is None else SQLiteStorage(db_path)
    try:
        return SQLiteOptimizer(storage).optimize(analyze=analyze, vacuum=vacuum)
    finally:
        storage.close()


def _pragma_int(connection: sqlite3.Connection, name: str) -> int:
    """Read an integer PRAGMA value."""
    row = connection.execute(f"PRAGMA {name}").fetchone()
    return 0 if row is None else int(row[0])


def _count(connection: sqlite3.Connection, table: str) -> int:
    """Count rows in a known internal table."""
    row = connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
    return 0 if row is None else int(row["count"])


__all__ = ["SQLiteOptimizer", "optimize_sqlite"]
