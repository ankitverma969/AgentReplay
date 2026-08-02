"""Base plugin contract for AgentReplay extensions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from agentreplay.plugins.models import (
    ConfigValueType,
    HookName,
    PluginDependency,
    PluginMetadata,
    PluginType,
)
from agentreplay.types import Metadata


class AgentReplayPlugin:
    """Base class for external AgentReplay plugins.

    Plugins subclass this class and override ``register()`` to contribute
    adapters, exporters, CLI commands, event processors, metadata collectors, or
    other extension points.
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = "0.0.0"
    plugin_type: ClassVar[PluginType] = "event_processor"
    summary: ClassVar[str] = ""
    min_agentreplay_version: ClassVar[str | None] = None
    max_agentreplay_version: ClassVar[str | None] = None
    dependencies: ClassVar[tuple[PluginDependency, ...]] = ()
    config_schema: ClassVar[Mapping[str, ConfigValueType]] = {}
    hooks: ClassVar[tuple[HookName, ...]] = ()

    def metadata(self) -> PluginMetadata:
        """Return static plugin metadata."""
        return PluginMetadata(
            name=self.name,
            version=self.version,
            plugin_type=self.plugin_type,
            summary=self.summary,
            min_agentreplay_version=self.min_agentreplay_version,
            max_agentreplay_version=self.max_agentreplay_version,
            dependencies=self.dependencies,
            config_schema=dict(self.config_schema),
        )

    def validate_config(self, config: Metadata) -> None:
        """Validate plugin-specific configuration.

        Subclasses can override this for richer validation. The default
        implementation validates against ``config_schema``.
        """

    def register(self, app: object) -> None:
        """Register plugin capabilities with an AgentReplay plugin app."""

    def on_plugin_loaded(self, app: object) -> None:
        """Run after plugin registration succeeds."""

    def on_plugin_unloaded(self, app: object) -> None:
        """Run before plugin registrations are removed."""


__all__ = ["AgentReplayPlugin"]
