"""SQLite schema metadata and migrations for AgentReplay storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from agentreplay.constants import SQLITE_SCHEMA_VERSION
from agentreplay.exceptions import StorageError

MIGRATION_001: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runs (
        run_id TEXT PRIMARY KEY,
        name TEXT,
        status TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        duration_ms REAL NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_tags (
        run_id TEXT NOT NULL,
        tag TEXT NOT NULL,
        position INTEGER NOT NULL,
        PRIMARY KEY (run_id, tag),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        parent_event_id TEXT,
        sequence INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        duration_ms REAL NOT NULL,
        payload_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
        FOREIGN KEY (parent_event_id) REFERENCES events(event_id) ON DELETE SET NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metadata (
        owner_type TEXT NOT NULL,
        owner_id TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        PRIMARY KEY (owner_type, owner_id, key),
        CHECK (owner_type IN ('run', 'event'))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        attachment_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        event_id TEXT,
        name TEXT NOT NULL,
        content_type TEXT,
        uri TEXT NOT NULL,
        size_bytes INTEGER,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE,
        FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_started_at ON runs(started_at)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_run_tags_tag ON run_tags(tag)",
    "CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_events_run_sequence ON events(run_id, sequence)",
    "CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_parent_event ON events(parent_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_metadata_owner ON metadata(owner_type, owner_id)",
    "CREATE INDEX IF NOT EXISTS idx_metadata_key ON metadata(key)",
    "CREATE INDEX IF NOT EXISTS idx_attachments_run_id ON attachments(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_attachments_event_id ON attachments(event_id)",
    "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)",
)

MIGRATIONS: tuple[tuple[str, ...], ...] = (MIGRATION_001,)


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Apply pending SQLite schema migrations."""
    try:
        _ensure_migration_table(connection)
        current_version = schema_version(connection)
        for version, statements in enumerate(MIGRATIONS, start=1):
            if version > current_version:
                _execute_many(connection, statements)
    except sqlite3.Error as exc:
        msg = "Could not initialize AgentReplay SQLite schema."
        raise StorageError(msg) from exc


def schema_version(connection: sqlite3.Connection) -> int:
    """Return the current SQLite schema version."""
    _ensure_migration_table(connection)
    row = connection.execute(
        "SELECT MAX(version) AS version FROM schema_migrations"
    ).fetchone()
    value = row["version"] if row is not None else None
    return 0 if value is None else int(value)


def _ensure_migration_table(connection: sqlite3.Connection) -> None:
    """Ensure the schema migration table exists."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """,
    )


def _execute_many(connection: sqlite3.Connection, statements: Iterable[str]) -> None:
    """Execute a sequence of migration SQL statements."""
    for statement in statements:
        connection.execute(statement)


__all__ = [
    "MIGRATIONS",
    "SQLITE_SCHEMA_VERSION",
    "apply_migrations",
    "schema_version",
]
