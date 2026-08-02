"""Trace snapshots for AgentReplay."""

from __future__ import annotations

from dataclasses import dataclass

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.types import JSONValue


@dataclass(frozen=True, slots=True)
class TraceSnapshot:
    """Immutable snapshot of one recorded run and its ordered events."""

    run: RunRecord
    events: tuple[EventRecord, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation."""
        return {
            "run": self.run.to_dict(),
            "events": [event.to_dict() for event in self.events],
        }


__all__ = ["TraceSnapshot"]
