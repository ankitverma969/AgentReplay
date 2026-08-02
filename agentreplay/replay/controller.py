"""Playback controller for read-only AgentReplay replay sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from time import sleep

from agentreplay.exceptions import ReplayError
from agentreplay.replay.playback import EventTimeline, TimelineEntry
from agentreplay.replay.policies import (
    PlaybackSpeed,
    ReplayStatus,
    validate_playback_speed,
)
from agentreplay.types import JSONValue


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """Serializable playback controller state."""

    status: ReplayStatus
    index: int
    speed: PlaybackSpeed
    current_event_id: str | None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of the playback state."""
        return {
            "status": self.status,
            "index": self.index,
            "speed": self.speed,
            "current_event_id": self.current_event_id,
        }


class ReplayController:
    """Control playback over an immutable event timeline."""

    def __init__(
        self,
        timeline: EventTimeline,
        *,
        speed: float = 1.0,
    ) -> None:
        """Create a replay controller."""
        self._timeline = timeline
        self._speed = validate_playback_speed(speed)
        self._index = 0
        self._status: ReplayStatus = "loaded"

    @property
    def status(self) -> ReplayStatus:
        """Return the current replay status."""
        return self._status

    @property
    def speed(self) -> PlaybackSpeed:
        """Return the current playback speed."""
        return self._speed

    @property
    def index(self) -> int:
        """Return the current timeline index."""
        return self._index

    def state(self) -> PlaybackState:
        """Return the current playback state."""
        current = self.current()
        return PlaybackState(
            status=self._status,
            index=self._index,
            speed=self._speed,
            current_event_id=None if current is None else current.event.event_id,
        )

    def set_speed(self, speed: float) -> PlaybackSpeed:
        """Set playback speed."""
        self._speed = validate_playback_speed(speed)
        return self._speed

    def current(self) -> TimelineEntry | None:
        """Return the current timeline entry, if any."""
        if not self._timeline.entries:
            return None
        bounded_index = min(self._index, len(self._timeline.entries) - 1)
        return self._timeline.entries[bounded_index]

    def play(self, *, real_time: bool = False) -> tuple[TimelineEntry, ...]:
        """Play sequentially from the current position to completion or pause."""
        if not self._timeline.entries:
            self._status = "completed"
            return ()
        if self._status == "stopped":
            self._index = 0
        self._status = "playing"
        emitted: list[TimelineEntry] = []
        while self._status == "playing" and self._index < len(self._timeline.entries):
            entry = self._timeline.entries[self._index]
            emitted.append(entry)
            self._index += 1
            if real_time and self._index < len(self._timeline.entries):
                _sleep_until_next(
                    entry,
                    self._timeline.entries[self._index],
                    self._speed,
                )
        if self._index >= len(self._timeline.entries):
            self._status = "completed"
        return tuple(emitted)

    def pause(self) -> PlaybackState:
        """Pause playback at the current position."""
        if self._status in {"loaded", "playing"}:
            self._status = "paused"
        return self.state()

    def resume(self, *, real_time: bool = False) -> tuple[TimelineEntry, ...]:
        """Resume playback from the current position."""
        if self._status not in {"paused", "loaded", "stopped"}:
            return ()
        return self.play(real_time=real_time)

    def stop(self) -> PlaybackState:
        """Stop playback and reset to the beginning."""
        self._status = "stopped"
        self._index = 0
        return self.state()

    def seek(self, event_id: str) -> TimelineEntry:
        """Seek to an event by id and return it."""
        index = self._timeline.find_event_index(event_id)
        if index is None:
            msg = f"Replay event not found: {event_id}"
            raise ReplayError(msg)
        self._index = index
        if self._status == "completed":
            self._status = "paused"
        return self._timeline.entries[index]

    def jump_to_event(self, event_id: str) -> TimelineEntry:
        """Jump to an event by id and return it."""
        return self.seek(event_id)

    def jump_to_timestamp(self, timestamp: datetime) -> TimelineEntry:
        """Jump to the first event at or after a timestamp."""
        index = self._timeline.find_timestamp_index(timestamp)
        if index is None:
            msg = f"Replay timestamp is after the final event: {timestamp.isoformat()}"
            raise ReplayError(msg)
        self._index = index
        if self._status == "completed":
            self._status = "paused"
        return self._timeline.entries[index]

    def step_forward(self) -> TimelineEntry | None:
        """Advance by one event and return the emitted entry."""
        if self._index >= len(self._timeline.entries):
            self._status = "completed"
            return None
        entry = self._timeline.entries[self._index]
        self._index += 1
        if self._index >= len(self._timeline.entries):
            self._status = "completed"
        elif self._status not in {"playing", "paused"}:
            self._status = "paused"
        return entry

    def step_backward(self) -> TimelineEntry | None:
        """Move one event backward and return the current entry."""
        if not self._timeline.entries:
            return None
        self._index = max(self._index - 1, 0)
        if self._status in {"completed", "stopped"}:
            self._status = "paused"
        return self._timeline.entries[self._index]


def _sleep_until_next(
    current_entry: TimelineEntry,
    next_entry: TimelineEntry,
    speed: PlaybackSpeed,
) -> None:
    """Sleep for the scaled time gap between two recorded events."""
    gap = (next_entry.event.timestamp - current_entry.event.timestamp).total_seconds()
    if gap > 0:
        sleep(gap / speed)


__all__ = ["PlaybackState", "ReplayController"]
