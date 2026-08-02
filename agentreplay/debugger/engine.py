"""Debugger engine for loading read-only time travel sessions."""

from __future__ import annotations

from pathlib import Path

from agentreplay.core.traces import TraceSnapshot
from agentreplay.debugger.models import DebuggerTheme
from agentreplay.debugger.session import DebuggerSession
from agentreplay.exceptions import DebuggerError, ReplayError, StorageError
from agentreplay.replay import ReplayEngine
from agentreplay.storage import Pagination, SQLiteStorage, StorageBackend


class DebuggerEngine:
    """Load recorded executions and launch the interactive debugger."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        replay_engine: ReplayEngine | None = None,
    ) -> None:
        """Create a debugger engine."""
        self._storage = storage
        self._replay_engine = replay_engine

    def load(self, run_id: str) -> DebuggerSession:
        """Load a run by id from storage."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        resolved_run_id = self.resolve_run_id(run_id)
        replay_engine = ReplayEngine(storage=storage)
        self._replay_engine = replay_engine
        try:
            return DebuggerSession(replay_engine.load(resolved_run_id))
        except ReplayError as exc:
            msg = str(exc)
            raise DebuggerError(msg) from exc

    def load_file(self, path: str | Path) -> DebuggerSession:
        """Load a debugger session from an exported JSON file."""
        replay_engine = ReplayEngine()
        self._replay_engine = replay_engine
        try:
            return DebuggerSession(replay_engine.load_file(path))
        except ReplayError as exc:
            msg = str(exc)
            raise DebuggerError(msg) from exc

    def load_trace(self, trace: TraceSnapshot) -> DebuggerSession:
        """Load a debugger session from an in-memory trace snapshot."""
        replay_engine = ReplayEngine()
        self._replay_engine = replay_engine
        try:
            return DebuggerSession(replay_engine.load_trace(trace))
        except ReplayError as exc:
            msg = str(exc)
            raise DebuggerError(msg) from exc

    def resolve_run_id(self, run_id: str) -> str:
        """Resolve the special ``latest`` run id against configured storage."""
        if run_id != "latest":
            return run_id
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.list_runs(pagination=Pagination(limit=1))
        if not runs:
            msg = "No recorded runs found."
            raise DebuggerError(msg)
        return runs[0].run_id

    def run(
        self,
        session: DebuggerSession,
        *,
        theme: DebuggerTheme = "dark",
        diff_run_id: str | None = None,
    ) -> None:
        """Launch the full-screen debugger UI."""
        try:
            from agentreplay.debugger.app import DebuggerApp
        except ModuleNotFoundError as exc:
            if exc.name != "textual":
                raise
            msg = (
                "The interactive debugger requires the optional 'debugger' extra. "
                "Install it with: python -m pip install 'agentreplay[debugger]'."
            )
            raise DebuggerError(msg) from exc
        DebuggerApp(
            session=session,
            theme=theme,
            storage=self._storage,
            diff_run_id=diff_run_id,
        ).run()

    def close(self) -> None:
        """Close owned storage resources."""
        if self._storage is not None:
            try:
                self._storage.close()
            except StorageError:
                return


__all__ = ["DebuggerEngine"]
