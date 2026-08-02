"""Event alignment strategies for AgentReplay execution diffs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, TypeAlias

from agentreplay.core.events import (
    FUNCTION_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    EventRecord,
)

MatchKind: TypeAlias = Literal["matched", "added", "removed"]


@dataclass(frozen=True, slots=True)
class EventMatch:
    """Alignment result for one event position in a two-run comparison."""

    kind: MatchKind
    left_event: EventRecord | None
    right_event: EventRecord | None
    left_index: int | None
    right_index: int | None


class EventMatcher:
    """Align two event sequences without mutating either run."""

    def align(
        self,
        left_events: Sequence[EventRecord],
        right_events: Sequence[EventRecord],
    ) -> tuple[EventMatch, ...]:
        """Return a read-only alignment of two event sequences."""
        common_ids = {event.event_id for event in left_events} & {
            event.event_id for event in right_events
        }
        left_keys = [_signature(event, common_ids) for event in left_events]
        right_keys = [_signature(event, common_ids) for event in right_events]
        matcher = SequenceMatcher(
            a=left_keys,
            b=right_keys,
            autojunk=False,
        )
        matches: list[EventMatch] = []
        opcodes = matcher.get_opcodes()
        for opcode, left_start, left_end, right_start, right_end in opcodes:
            if opcode == "equal":
                matches.extend(
                    EventMatch(
                        kind="matched",
                        left_event=left_events[left_index],
                        right_event=right_events[right_index],
                        left_index=left_index,
                        right_index=right_index,
                    )
                    for left_index, right_index in zip(
                        range(left_start, left_end),
                        range(right_start, right_end),
                        strict=True,
                    )
                )
            elif opcode == "delete":
                matches.extend(
                    EventMatch(
                        kind="removed",
                        left_event=left_events[index],
                        right_event=None,
                        left_index=index,
                        right_index=None,
                    )
                    for index in range(left_start, left_end)
                )
            elif opcode == "insert":
                matches.extend(
                    EventMatch(
                        kind="added",
                        left_event=None,
                        right_event=right_events[index],
                        left_index=None,
                        right_index=index,
                    )
                    for index in range(right_start, right_end)
                )
            else:
                matches.extend(
                    _replace_matches(
                        left_events,
                        right_events,
                        left_start,
                        left_end,
                        right_start,
                        right_end,
                    )
                )
        return tuple(matches)


def _replace_matches(
    left_events: Sequence[EventRecord],
    right_events: Sequence[EventRecord],
    left_start: int,
    left_end: int,
    right_start: int,
    right_end: int,
) -> tuple[EventMatch, ...]:
    """Pair replaced ranges where possible and mark leftovers as added or removed."""
    matches: list[EventMatch] = []
    paired = min(left_end - left_start, right_end - right_start)
    for offset in range(paired):
        left_index = left_start + offset
        right_index = right_start + offset
        matches.append(
            EventMatch(
                kind="matched",
                left_event=left_events[left_index],
                right_event=right_events[right_index],
                left_index=left_index,
                right_index=right_index,
            )
        )
    for left_index in range(left_start + paired, left_end):
        matches.append(
            EventMatch(
                kind="removed",
                left_event=left_events[left_index],
                right_event=None,
                left_index=left_index,
                right_index=None,
            )
        )
    for right_index in range(right_start + paired, right_end):
        matches.append(
            EventMatch(
                kind="added",
                left_event=None,
                right_event=right_events[right_index],
                left_index=None,
                right_index=right_index,
            )
        )
    return tuple(matches)


def _signature(event: EventRecord, common_ids: set[str]) -> str:
    """Return a stable matching signature for an event."""
    if event.event_id in common_ids:
        return f"id:{event.event_id}"
    semantic_name = _semantic_name(event)
    if semantic_name is None:
        return f"type:{event.event_type}"
    return f"type:{event.event_type}:name:{semantic_name}"


def _semantic_name(event: EventRecord) -> str | None:
    """Return a semantic event name when it is safe to use for alignment."""
    if event.event_type in {TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED}:
        value = event.payload.get("tool_name")
        return value if isinstance(value, str) else None
    if event.event_type == FUNCTION_CALL:
        value = event.payload.get("function_name")
        return value if isinstance(value, str) else None
    return None


__all__ = ["EventMatch", "EventMatcher", "MatchKind"]
