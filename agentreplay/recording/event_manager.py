"""Thread-safe in-memory event management for AgentReplay recording."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import replace
from threading import RLock

from agentreplay.core.clocks import Clock
from agentreplay.core.events import EventRecord, EventType
from agentreplay.core.ids import IdGenerator
from agentreplay.exceptions import AgentReplayError
from agentreplay.recording.metadata import MetadataCollector
from agentreplay.recording.serializers import EventSerializer


class EventManager:
    """Append, update, and snapshot in-memory event records."""

    def __init__(
        self,
        *,
        clock: Clock,
        id_generator: IdGenerator,
        serializer: EventSerializer,
        metadata_collector: MetadataCollector,
    ) -> None:
        """Create an event manager."""
        self._clock = clock
        self._id_generator = id_generator
        self._serializer = serializer
        self._metadata_collector = metadata_collector
        self._events_by_run: dict[str, list[EventRecord]] = defaultdict(list)
        self._event_index: dict[str, tuple[str, int]] = {}
        self._sequence_by_run: dict[str, int] = defaultdict(int)
        self._lock = RLock()

    def append_event(
        self,
        *,
        run_id: str,
        event_type: EventType,
        parent_event_id: str | None,
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
        duration_ms: float = 0.0,
        event_id: str | None = None,
    ) -> EventRecord:
        """Append a new event record to a run."""
        with self._lock:
            sequence = self._sequence_by_run[run_id] + 1
            self._sequence_by_run[run_id] = sequence
            record = EventRecord(
                event_id=self._id_generator.new_id() if event_id is None else event_id,
                run_id=run_id,
                parent_event_id=parent_event_id,
                sequence=sequence,
                event_type=event_type,
                timestamp=self._clock.now(),
                duration_ms=max(duration_ms, 0.0),
                metadata=self._metadata_collector.collect_event_metadata(metadata),
                payload=self._serializer.serialize_payload(payload),
            )
            self._events_by_run[run_id].append(record)
            self._event_index[record.event_id] = (
                run_id,
                len(self._events_by_run[run_id]) - 1,
            )
            return record

    def finish_event(
        self,
        event_id: str,
        *,
        duration_ms: float,
        metadata: Mapping[str, object] | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Update an existing event with its final duration and optional details."""
        with self._lock:
            run_id, index = self._event_position(event_id)
            current = self._events_by_run[run_id][index]

            merged_metadata: dict[str, object] = dict(current.metadata)
            if metadata is not None:
                merged_metadata.update(metadata)
            merged_payload: dict[str, object] = dict(current.payload)
            if payload is not None:
                merged_payload.update(payload)

            updated = replace(
                current,
                duration_ms=max(duration_ms, 0.0),
                metadata=self._metadata_collector.collect_event_metadata(
                    merged_metadata
                ),
                payload=self._serializer.serialize_payload(merged_payload),
            )
            self._events_by_run[run_id][index] = updated
            return updated

    def events_for_run(self, run_id: str) -> tuple[EventRecord, ...]:
        """Return events for a run in recorded sequence order."""
        with self._lock:
            return tuple(self._events_by_run.get(run_id, ()))

    def all_events(self) -> tuple[EventRecord, ...]:
        """Return all events grouped by run creation order."""
        with self._lock:
            return tuple(
                event for events in self._events_by_run.values() for event in events
            )

    def _event_position(self, event_id: str) -> tuple[str, int]:
        """Return the internal location for an event id."""
        position = self._event_index.get(event_id)
        if position is None:
            msg = f"Unknown AgentReplay event id: {event_id}"
            raise AgentReplayError(msg)
        return position


__all__ = ["EventManager"]
