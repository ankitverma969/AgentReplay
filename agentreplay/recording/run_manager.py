"""Thread-safe in-memory run management for AgentReplay recording."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Literal

from agentreplay.core.clocks import Clock
from agentreplay.core.ids import IdGenerator
from agentreplay.core.runs import RunRecord
from agentreplay.exceptions import AgentReplayError
from agentreplay.recording.metadata import MetadataCollector

RunFinishStatus = Literal["completed", "failed", "cancelled"]


class RunManager:
    """Create, finish, and snapshot in-memory run records."""

    def __init__(
        self,
        *,
        clock: Clock,
        id_generator: IdGenerator,
        metadata_collector: MetadataCollector,
    ) -> None:
        """Create a run manager."""
        self._clock = clock
        self._id_generator = id_generator
        self._metadata_collector = metadata_collector
        self._runs: dict[str, RunRecord] = {}
        self._lock = RLock()

    def start_run(
        self,
        *,
        name: str | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: tuple[str, ...] = (),
    ) -> RunRecord:
        """Create and store a running run record."""
        now = self._clock.now()
        run = RunRecord(
            run_id=self._id_generator.new_id(),
            name=name,
            status="running",
            started_at=now,
            ended_at=None,
            duration_ms=0.0,
            metadata=self._metadata_collector.collect_run_metadata(metadata),
            tags=tags,
        )
        with self._lock:
            self._runs[run.run_id] = run
        return run

    def finish_run(
        self,
        run_id: str,
        *,
        status: RunFinishStatus,
        metadata: Mapping[str, object] | None = None,
    ) -> RunRecord:
        """Mark a run as finished and return the updated record."""
        ended_at = self._clock.now()
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                msg = f"Unknown AgentReplay run id: {run_id}"
                raise AgentReplayError(msg)
            if run.status != "running":
                msg = f"AgentReplay run is already finished: {run_id}"
                raise AgentReplayError(msg)

            merged_metadata: dict[str, object] = dict(run.metadata)
            if metadata is not None:
                merged_metadata.update(metadata)
            updated = replace(
                run,
                status=status,
                ended_at=ended_at,
                duration_ms=_duration_ms(run.started_at, ended_at),
                metadata=self._metadata_collector.collect_run_metadata(merged_metadata),
            )
            self._runs[run_id] = updated
            return updated

    def get_run(self, run_id: str) -> RunRecord:
        """Return a run record by id."""
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                msg = f"Unknown AgentReplay run id: {run_id}"
                raise AgentReplayError(msg)
            return run

    def ensure_running(self, run_id: str) -> None:
        """Raise if a run does not exist or is not currently running."""
        run = self.get_run(run_id)
        if run.status != "running":
            msg = f"AgentReplay run is not active: {run_id}"
            raise AgentReplayError(msg)

    def list_runs(self) -> tuple[RunRecord, ...]:
        """Return all runs in creation order."""
        with self._lock:
            return tuple(self._runs.values())


def _duration_ms(started_at: datetime, ended_at: datetime) -> float:
    """Return a non-negative duration in milliseconds for datetime-like values."""
    delta = ended_at - started_at
    total_seconds = float(delta.total_seconds())
    return max(total_seconds * 1000.0, 0.0)


__all__ = ["RunFinishStatus", "RunManager"]
