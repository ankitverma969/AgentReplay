"""Replay iterator primitives."""

from __future__ import annotations

from agentreplay.replay.playback import EventTimeline, TimelineEntry


class ReplayIterator:
    """Iterator over replay timeline entries."""

    def __init__(self, timeline: EventTimeline, *, start_index: int = 0) -> None:
        """Create a replay iterator."""
        self._timeline = timeline
        self._index = start_index

    def __iter__(self) -> ReplayIterator:
        """Return this iterator."""
        return self

    def __next__(self) -> TimelineEntry:
        """Return the next replay timeline entry."""
        if self._index >= len(self._timeline.entries):
            raise StopIteration
        entry = self._timeline.entries[self._index]
        self._index += 1
        return entry


__all__ = ["ReplayIterator"]
