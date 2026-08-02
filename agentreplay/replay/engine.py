"""Read-only replay engine for AgentReplay traces."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from agentreplay.constants import EVENT_SCHEMA_VERSION
from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ReplayError
from agentreplay.replay.controller import PlaybackState, ReplayController
from agentreplay.replay.iterator import ReplayIterator
from agentreplay.replay.playback import EventTimeline, TimelineEntry
from agentreplay.replay.session import ReplaySession
from agentreplay.storage import SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue, Metadata


class ReplayEngine:
    """Load and replay previously recorded AgentReplay runs without side effects."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        speed: float = 1.0,
    ) -> None:
        """Create a replay engine."""
        self._storage = storage
        self._default_speed = speed
        self._session: ReplaySession | None = None
        self._controller: ReplayController | None = None

    @property
    def session(self) -> ReplaySession | None:
        """Return the currently loaded replay session."""
        return self._session

    @property
    def controller(self) -> ReplayController | None:
        """Return the current replay controller."""
        return self._controller

    def load(self, run_id: str) -> ReplaySession:
        """Load a run and its recorded events from storage."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        run = storage.load_run(run_id)
        if run is None:
            msg = f"Replay run not found: {run_id}"
            raise ReplayError(msg)
        events = storage.load_events(run_id)
        return self.load_trace(TraceSnapshot(run=run, events=events))

    def load_trace(self, trace: TraceSnapshot) -> ReplaySession:
        """Load a trace snapshot into the replay engine."""
        session = ReplaySession(trace=trace, timeline=EventTimeline.from_trace(trace))
        self._session = session
        self._controller = ReplayController(session.timeline, speed=self._default_speed)
        return session

    def load_json(self, data: str | bytes | Mapping[str, object]) -> ReplaySession:
        """Load a replay session from exported JSON data."""
        if isinstance(data, str | bytes):
            try:
                loaded: Any = json.loads(data)
            except json.JSONDecodeError as exc:
                msg = "Replay JSON is invalid."
                raise ReplayError(msg) from exc
        else:
            loaded = data
        if not isinstance(loaded, Mapping):
            msg = "Replay JSON must be an object."
            raise ReplayError(msg)
        return self.load_trace(_trace_from_mapping(loaded))

    def load_file(self, path: str | Path) -> ReplaySession:
        """Load a replay session from a JSON file."""
        try:
            content = Path(path).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            msg = f"Replay file could not be read: {path}"
            raise ReplayError(msg) from exc
        return self.load_json(content)

    def iterator(self) -> ReplayIterator:
        """Return an iterator over the loaded timeline."""
        session = self._require_session()
        index = self._require_controller().index
        return ReplayIterator(session.timeline, start_index=index)

    def timeline(self) -> EventTimeline:
        """Return the loaded event timeline."""
        return self._require_session().timeline

    def render_timeline(self, *, include_details: bool = False) -> str:
        """Render the loaded timeline as human-readable text."""
        return self.timeline().render(include_details=include_details)

    def play(self, *, real_time: bool = False) -> tuple[TimelineEntry, ...]:
        """Replay sequentially from the current position."""
        return self._require_controller().play(real_time=real_time)

    def pause(self) -> PlaybackState:
        """Pause playback."""
        return self._require_controller().pause()

    def resume(self, *, real_time: bool = False) -> tuple[TimelineEntry, ...]:
        """Resume playback."""
        return self._require_controller().resume(real_time=real_time)

    def stop(self) -> PlaybackState:
        """Stop playback and reset to the beginning."""
        return self._require_controller().stop()

    def seek(self, event_id: str) -> TimelineEntry:
        """Seek to an event by id."""
        return self._require_controller().seek(event_id)

    def jump_to_event(self, event_id: str) -> TimelineEntry:
        """Jump to an event by id."""
        return self._require_controller().jump_to_event(event_id)

    def jump_to_timestamp(self, timestamp: datetime) -> TimelineEntry:
        """Jump to the first event at or after a timestamp."""
        return self._require_controller().jump_to_timestamp(timestamp)

    def step_forward(self) -> TimelineEntry | None:
        """Step forward by one event."""
        return self._require_controller().step_forward()

    def step_backward(self) -> TimelineEntry | None:
        """Step backward by one event."""
        return self._require_controller().step_backward()

    def set_speed(self, speed: float) -> float:
        """Set the playback speed."""
        return float(self._require_controller().set_speed(speed))

    def _require_session(self) -> ReplaySession:
        """Return the loaded session or raise a replay error."""
        if self._session is None:
            msg = (
                "No AgentReplay session loaded. "
                "Call load(), load_json(), or load_file()."
            )
            raise ReplayError(msg)
        return self._session

    def _require_controller(self) -> ReplayController:
        """Return the loaded controller or raise a replay error."""
        if self._controller is None:
            msg = (
                "No AgentReplay session loaded. "
                "Call load(), load_json(), or load_file()."
            )
            raise ReplayError(msg)
        return self._controller


def _trace_from_mapping(data: Mapping[str, object]) -> TraceSnapshot:
    """Parse a trace snapshot from exported JSON data."""
    schema_version = data.get("schema_version")
    if schema_version is not None and schema_version != EVENT_SCHEMA_VERSION:
        msg = (
            f"Unsupported AgentReplay event schema version {schema_version!r}; "
            f"expected {EVENT_SCHEMA_VERSION}."
        )
        raise ReplayError(msg)
    trace_data = data.get("trace", data)
    if not isinstance(trace_data, Mapping):
        msg = "Replay JSON trace must be an object."
        raise ReplayError(msg)
    run_data = trace_data.get("run")
    events_data = trace_data.get("events")
    if not isinstance(run_data, Mapping):
        msg = "Replay JSON is missing a valid run object."
        raise ReplayError(msg)
    if not isinstance(events_data, list):
        msg = "Replay JSON is missing a valid events list."
        raise ReplayError(msg)
    return TraceSnapshot(
        run=_run_from_mapping(run_data),
        events=tuple(_event_from_mapping(event) for event in events_data),
    )


def _run_from_mapping(data: Mapping[str, object]) -> RunRecord:
    """Parse a run record from JSON mapping data."""
    try:
        return RunRecord(
            run_id=_required_str(data, "run_id"),
            name=_optional_str(data.get("name")),
            status=cast(RunStatus, _required_str(data, "status")),
            started_at=_required_datetime(data, "started_at"),
            ended_at=_optional_datetime(data.get("ended_at")),
            duration_ms=_float_value(data.get("duration_ms", 0.0)),
            metadata=_mapping_metadata(data.get("metadata")),
            tags=tuple(str(tag) for tag in _list_value(data.get("tags"))),
        )
    except (TypeError, ValueError) as exc:
        msg = "Replay JSON contains a corrupted run record."
        raise ReplayError(msg) from exc


def _event_from_mapping(data: object) -> EventRecord:
    """Parse an event record from JSON mapping data."""
    if not isinstance(data, Mapping):
        msg = "Replay JSON contains a non-object event."
        raise ReplayError(msg)
    try:
        return EventRecord(
            event_id=_required_str(data, "event_id"),
            run_id=_required_str(data, "run_id"),
            parent_event_id=_optional_str(data.get("parent_event_id")),
            sequence=int(data.get("sequence", 0)),
            event_type=_required_str(data, "event_type"),
            timestamp=_required_datetime(data, "timestamp"),
            duration_ms=_float_value(data.get("duration_ms", 0.0)),
            metadata=_mapping_metadata(data.get("metadata")),
            payload=_mapping_metadata(data.get("payload")),
        )
    except (TypeError, ValueError) as exc:
        msg = "Replay JSON contains a corrupted event record."
        raise ReplayError(msg) from exc


def _required_str(data: Mapping[str, object], key: str) -> str:
    """Read a required string field."""
    value = data.get(key)
    if not isinstance(value, str):
        msg = f"Replay JSON field {key!r} must be a string."
        raise ReplayError(msg)
    return value


def _optional_str(value: object) -> str | None:
    """Read an optional string field."""
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "Replay JSON optional string field has an invalid value."
        raise ReplayError(msg)
    return value


def _required_datetime(data: Mapping[str, object], key: str) -> datetime:
    """Read a required ISO datetime field."""
    value = _required_str(data, key)
    return datetime.fromisoformat(value)


def _optional_datetime(value: object) -> datetime | None:
    """Read an optional ISO datetime field."""
    if value is None:
        return None
    if not isinstance(value, str):
        msg = "Replay JSON optional datetime field has an invalid value."
        raise ReplayError(msg)
    return datetime.fromisoformat(value)


def _mapping_metadata(value: object) -> Metadata:
    """Read an optional metadata or payload mapping."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = "Replay JSON metadata and payload fields must be objects."
        raise ReplayError(msg)
    return cast(
        Metadata, {str(key): cast(JSONValue, item) for key, item in value.items()}
    )


def _float_value(value: object) -> float:
    """Read a JSON value as a float."""
    if not isinstance(value, str | int | float):
        msg = "Replay JSON numeric field has an invalid value."
        raise ReplayError(msg)
    return float(value)


def _list_value(value: object) -> list[object]:
    """Read an optional list field."""
    if value is None:
        return []
    if not isinstance(value, list):
        msg = "Replay JSON tags field must be a list."
        raise ReplayError(msg)
    return value


__all__ = ["ReplayEngine"]
