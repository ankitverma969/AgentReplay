"""Replay session model for loaded AgentReplay traces."""

from __future__ import annotations

from dataclasses import dataclass

from agentreplay.core.traces import TraceSnapshot
from agentreplay.replay.playback import EventTimeline
from agentreplay.types import JSONValue


@dataclass(frozen=True, slots=True)
class ReplaySession:
    """Read-only loaded replay session."""

    trace: TraceSnapshot
    timeline: EventTimeline

    @property
    def run_id(self) -> str:
        """Return the replayed run id."""
        return self.trace.run.run_id

    @property
    def warnings(self) -> tuple[str, ...]:
        """Return warnings found while constructing the replay timeline."""
        return self.timeline.warnings

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible replay session representation."""
        return {
            "trace": self.trace.to_dict(),
            "timeline": self.timeline.to_dict(),
        }


__all__ = ["ReplaySession"]
