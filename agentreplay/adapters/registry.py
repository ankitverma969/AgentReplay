"""Adapter registry for explicit and plugin-discovered integrations."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentreplay.adapters.base import AgentReplayAdapter
from agentreplay.exceptions import AdapterError


@dataclass(slots=True)
class AdapterRegistry:
    """In-memory registry for AgentReplay adapters."""

    _adapters: dict[str, AgentReplayAdapter] = field(default_factory=dict)

    def register(self, adapter: AgentReplayAdapter) -> None:
        """Register an adapter by name.

        Raises:
            AdapterError: If another adapter already uses the same name.
        """
        if adapter.name in self._adapters:
            msg = f"AgentReplay adapter already registered: {adapter.name}"
            raise AdapterError(msg)
        self._adapters[adapter.name] = adapter

    def names(self) -> tuple[str, ...]:
        """Return registered adapter names sorted for stable display."""
        return tuple(sorted(self._adapters))


__all__ = ["AdapterRegistry"]
