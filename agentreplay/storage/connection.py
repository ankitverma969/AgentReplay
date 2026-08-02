"""SQLite connection management for AgentReplay storage."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from agentreplay.exceptions import StorageError


class SQLiteConnectionManager:
    """Manage the reusable SQLite connection used by the storage backend."""

    def __init__(
        self,
        db_path: str | Path = ".agentreplay/agentreplay.sqlite",
        *,
        timeout: float = 30.0,
    ) -> None:
        """Create a SQLite connection manager."""
        self._db_path = Path(db_path).expanduser()
        self._timeout = timeout
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    @property
    def lock(self) -> RLock:
        """Return the lock guarding the shared SQLite connection."""
        return self._lock

    @property
    def db_path(self) -> Path:
        """Return the configured database path."""
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Return a lazily created SQLite connection."""
        with self._lock:
            if self._connection is None:
                self._connection = self._connect()
            return self._connection

    def close(self) -> None:
        """Close the managed connection if it is open."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def _connect(self) -> sqlite3.Connection:
        """Open and configure the SQLite connection."""
        if str(self._db_path) != ":memory:":
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            connection = sqlite3.connect(
                self._db_path,
                timeout=self._timeout,
                isolation_level=None,
                check_same_thread=False,
            )
        except sqlite3.Error as exc:
            msg = f"Could not open AgentReplay SQLite database: {self._db_path}"
            raise StorageError(msg) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        return connection


__all__ = ["SQLiteConnectionManager"]
