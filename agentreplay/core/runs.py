"""Run lifecycle records for AgentReplay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue, Metadata

RunStatus: TypeAlias = Literal["running", "completed", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class RunRecord:
    """Immutable in-memory record of one agent execution run."""

    run_id: str
    name: str | None
    status: RunStatus
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float
    metadata: Metadata
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Make metadata immutable after construction."""
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation."""
        return {
            "run_id": self.run_id,
            "name": self.name,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "metadata": dict(self.metadata),
            "tags": list(self.tags),
        }


__all__ = ["RunRecord", "RunStatus"]
