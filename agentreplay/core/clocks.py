"""Clock abstractions used for deterministic timing in AgentReplay."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Protocol for replaceable wall-clock providers."""

    def now(self) -> datetime:
        """Return the current timezone-aware timestamp."""


class SystemClock:
    """Clock implementation backed by the system UTC clock."""

    def now(self) -> datetime:
        """Return the current UTC timestamp."""
        return datetime.now(UTC)


__all__ = ["Clock", "SystemClock"]
