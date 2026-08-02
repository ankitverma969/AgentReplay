"""Read-only debugger session state for time travel inspection."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from agentreplay.debugger.filters import entry_matches_filter
from agentreplay.debugger.models import (
    DebuggerFilter,
    DebuggerStats,
    EventInspection,
    SearchMatch,
    SearchQuery,
)
from agentreplay.debugger.search import search_entries
from agentreplay.debugger.statistics import calculate_stats
from agentreplay.exceptions import DebuggerError
from agentreplay.replay.playback import TimelineEntry
from agentreplay.replay.session import ReplaySession


class DebuggerSession:
    """Interactive read-only view over a replay session."""

    def __init__(self, replay_session: ReplaySession) -> None:
        """Create a debugger session."""
        self._replay_session = replay_session
        self._index = 0
        self._collapsed_event_ids: set[str] = set()
        self._filter = DebuggerFilter()
        self._logs: list[str] = []
        self._children_by_parent = _children_by_parent(replay_session.timeline.entries)
        self._entry_by_id = {
            entry.event.event_id: entry for entry in replay_session.timeline.entries
        }
        self._index_by_event_id = {
            entry.event.event_id: entry.index
            for entry in replay_session.timeline.entries
        }

    @property
    def replay_session(self) -> ReplaySession:
        """Return the underlying replay session."""
        return self._replay_session

    @property
    def run_id(self) -> str:
        """Return the debugged run id."""
        return self._replay_session.run_id

    @property
    def index(self) -> int:
        """Return the selected timeline index."""
        return self._index

    @property
    def logs(self) -> tuple[str, ...]:
        """Return debugger log messages."""
        return tuple(self._logs)

    @property
    def event_filter(self) -> DebuggerFilter:
        """Return the active debugger filter."""
        return self._filter

    def current_entry(self) -> TimelineEntry | None:
        """Return the selected timeline entry."""
        entries = self._replay_session.timeline.entries
        if not entries:
            return None
        return entries[self._index]

    def next_event(self) -> TimelineEntry | None:
        """Move to the next visible event."""
        visible = self.visible_entries()
        current_visible = _visible_position(visible, self._index)
        if current_visible is None:
            return self._select_visible(visible, 0)
        return self._select_visible(visible, current_visible + 1)

    def previous_event(self) -> TimelineEntry | None:
        """Move to the previous visible event."""
        visible = self.visible_entries()
        current_visible = _visible_position(visible, self._index)
        if current_visible is None:
            return self._select_visible(visible, len(visible) - 1)
        return self._select_visible(visible, current_visible - 1)

    def jump_to_event(self, event_id: str) -> TimelineEntry:
        """Jump to an event by id."""
        if event_id not in self._index_by_event_id:
            msg = f"Debugger event not found: {event_id}"
            raise DebuggerError(msg)
        self._index = self._index_by_event_id[event_id]
        self.log(f"Jumped to event {event_id}.")
        return self._entry_by_id[event_id]

    def go_to_timestamp(self, timestamp: datetime) -> TimelineEntry:
        """Jump to the first event at or after a timestamp."""
        for entry in self._replay_session.timeline.entries:
            if entry.event.timestamp >= timestamp:
                self._index = entry.index
                self.log(f"Jumped to timestamp {timestamp.isoformat()}.")
                return entry
        msg = f"No event exists at or after timestamp {timestamp.isoformat()}."
        raise DebuggerError(msg)

    def step_forward(self) -> TimelineEntry | None:
        """Step forward by one visible event."""
        return self.next_event()

    def step_backward(self) -> TimelineEntry | None:
        """Step backward by one visible event."""
        return self.previous_event()

    def collapse_current(self) -> None:
        """Collapse the currently selected event subtree."""
        entry = self.current_entry()
        if entry is not None:
            self._collapsed_event_ids.add(entry.event.event_id)
            self.log(f"Collapsed {entry.event.event_id}.")

    def expand_current(self) -> None:
        """Expand the currently selected event subtree."""
        entry = self.current_entry()
        if entry is not None:
            self._collapsed_event_ids.discard(entry.event.event_id)
            self.log(f"Expanded {entry.event.event_id}.")

    def expand_all(self) -> None:
        """Expand every collapsed event subtree."""
        self._collapsed_event_ids.clear()
        self.log("Expanded all event subtrees.")

    def set_filter(self, event_filter: DebuggerFilter) -> None:
        """Replace the active event filter."""
        self._filter = event_filter
        visible = self.visible_entries()
        if visible and self.current_entry() not in visible:
            self._index = visible[0].index
        self.log("Updated event filters.")

    def toggle_filter(self, name: str) -> DebuggerFilter:
        """Toggle a named boolean filter and return the new filter."""
        if not hasattr(self._filter, name):
            msg = f"Unknown debugger filter: {name}"
            raise DebuggerError(msg)
        current = getattr(self._filter, name)
        if not isinstance(current, bool):
            msg = f"Debugger filter is not toggleable: {name}"
            raise DebuggerError(msg)
        updated = replace(self._filter, **{name: not current})
        self.set_filter(updated)
        return updated

    def visible_entries(self) -> tuple[TimelineEntry, ...]:
        """Return entries visible after collapse and filter state are applied."""
        visible: list[TimelineEntry] = []
        collapsed_depth: int | None = None
        for entry in self._replay_session.timeline.entries:
            if collapsed_depth is not None:
                if entry.depth > collapsed_depth:
                    continue
                collapsed_depth = None
            if not entry_matches_filter(entry, self._filter):
                continue
            visible.append(entry)
            if entry.event.event_id in self._collapsed_event_ids:
                collapsed_depth = entry.depth
        return tuple(visible)

    def search(self, query: SearchQuery) -> tuple[SearchMatch, ...]:
        """Search visible events."""
        matches = search_entries(self.visible_entries(), query)
        self.log(f"Search found {len(matches)} matches for {query.text!r}.")
        if matches:
            self.jump_to_event(matches[0].event_id)
        return matches

    def inspect_current(self) -> EventInspection | None:
        """Return structured details for the selected event."""
        entry = self.current_entry()
        if entry is None:
            return None
        event = entry.event
        return EventInspection(
            event_id=event.event_id,
            event_type=event.event_type,
            timestamp=event.timestamp.isoformat(),
            duration_ms=event.duration_ms,
            parent_event_id=event.parent_event_id,
            children=tuple(
                child.event.event_id
                for child in self._children_by_parent.get(event.event_id, ())
            ),
            payload=dict(event.payload),
            metadata=dict(event.metadata),
        )

    def statistics(self) -> DebuggerStats:
        """Return aggregate execution statistics."""
        return calculate_stats(self._replay_session.timeline.entries)

    def event_window(
        self,
        *,
        size: int = 200,
        center_index: int | None = None,
    ) -> tuple[TimelineEntry, ...]:
        """Return a bounded visible event window for virtual rendering."""
        visible = self.visible_entries()
        if not visible:
            return ()
        selected = self._index if center_index is None else center_index
        visible_position = _visible_position(visible, selected) or 0
        half = max(size // 2, 1)
        start = max(visible_position - half, 0)
        end = min(start + size, len(visible))
        return visible[start:end]

    def log(self, message: str) -> None:
        """Append a debugger log message."""
        self._logs.append(message)

    def _select_visible(
        self,
        visible: tuple[TimelineEntry, ...],
        position: int,
    ) -> TimelineEntry | None:
        """Select an entry by visible position."""
        if not visible:
            return None
        bounded = min(max(position, 0), len(visible) - 1)
        entry = visible[bounded]
        self._index = entry.index
        return entry


def _children_by_parent(
    entries: tuple[TimelineEntry, ...],
) -> dict[str, tuple[TimelineEntry, ...]]:
    """Build child-entry lookup by parent event id."""
    children: dict[str, list[TimelineEntry]] = {}
    for entry in entries:
        parent_event_id = entry.event.parent_event_id
        if parent_event_id is None:
            continue
        children.setdefault(parent_event_id, []).append(entry)
    return {key: tuple(value) for key, value in children.items()}


def _visible_position(
    visible: tuple[TimelineEntry, ...],
    index: int,
) -> int | None:
    """Return a timeline index's position within a visible entry tuple."""
    for position, entry in enumerate(visible):
        if entry.index == index:
            return position
    return None


__all__ = ["DebuggerSession"]
