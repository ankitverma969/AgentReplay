"""In-memory plugin registry for AgentReplay."""

from __future__ import annotations

from dataclasses import dataclass, field

from agentreplay.exceptions import PluginError
from agentreplay.plugins.models import PluginMetadata, PluginRecord, PluginStatus


@dataclass(slots=True)
class PluginRegistry:
    """Registry of discovered and loaded AgentReplay plugins."""

    _records: dict[str, PluginRecord] = field(default_factory=dict)

    def add(
        self,
        metadata: PluginMetadata,
        *,
        source: str,
        plugin: object | None = None,
        status: PluginStatus = "discovered",
        error: str | None = None,
    ) -> PluginRecord:
        """Add a plugin record."""
        if metadata.name in self._records:
            msg = f"AgentReplay plugin already registered: {metadata.name}"
            raise PluginError(msg)
        record = PluginRecord(
            metadata=metadata,
            status=status,
            source=source,
            plugin=plugin,
            error=error,
        )
        self._records[metadata.name] = record
        return record

    def update(self, record: PluginRecord) -> None:
        """Update an existing plugin record."""
        if record.metadata.name not in self._records:
            msg = f"Unknown AgentReplay plugin: {record.metadata.name}"
            raise PluginError(msg)
        self._records[record.metadata.name] = record

    def get(self, name: str) -> PluginRecord | None:
        """Return one plugin record by name."""
        return self._records.get(name)

    def require(self, name: str) -> PluginRecord:
        """Return one plugin record or raise."""
        record = self.get(name)
        if record is None:
            msg = f"Unknown AgentReplay plugin: {name}"
            raise PluginError(msg)
        return record

    def records(self) -> tuple[PluginRecord, ...]:
        """Return all plugin records sorted by name."""
        return tuple(self._records[name] for name in sorted(self._records))

    def names(self) -> tuple[str, ...]:
        """Return plugin names sorted for stable display."""
        return tuple(sorted(self._records))


__all__ = ["PluginRegistry"]
