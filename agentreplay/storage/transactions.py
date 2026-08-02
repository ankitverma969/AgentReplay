"""Transaction management for AgentReplay SQLite storage."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from agentreplay.exceptions import StorageError
from agentreplay.storage.connection import SQLiteConnectionManager


class SQLiteTransactionManager:
    """Provide locked SQLite transaction scopes."""

    def __init__(self, connection_manager: SQLiteConnectionManager) -> None:
        """Create a transaction manager."""
        self._connection_manager = connection_manager

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run statements inside a committed or rolled-back transaction."""
        with self._connection_manager.lock:
            connection = self._connection_manager.get_connection()
            try:
                connection.execute("BEGIN")
                yield connection
            except sqlite3.Error as exc:
                connection.rollback()
                msg = "AgentReplay SQLite transaction failed."
                raise StorageError(msg) from exc
            except Exception:
                connection.rollback()
                raise
            else:
                connection.commit()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Return a locked connection for read-only operations."""
        with self._connection_manager.lock:
            yield self._connection_manager.get_connection()


__all__ = ["SQLiteTransactionManager"]
