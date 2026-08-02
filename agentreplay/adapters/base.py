"""Base adapter contract for AgentReplay framework integrations."""

from __future__ import annotations

from typing import Protocol


class AgentReplayAdapter(Protocol):
    """Protocol implemented by framework adapter integrations."""

    @property
    def name(self) -> str:
        """Return the unique adapter name."""

    @property
    def framework(self) -> str:
        """Return the framework identifier supported by the adapter."""

    @property
    def version_support(self) -> str:
        """Return a human-readable framework compatibility range."""

    def is_available(self) -> bool:
        """Return whether optional framework dependencies are importable."""


__all__ = ["AgentReplayAdapter"]
