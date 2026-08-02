"""Plugin discovery and loading for AgentReplay."""

from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Iterable

from agentreplay.exceptions import PluginError
from agentreplay.plugins.base import AgentReplayPlugin
from agentreplay.plugins.entrypoints import (
    ADAPTER_ENTRY_POINT_GROUP,
    PLUGIN_ENTRY_POINT_GROUP,
)
from agentreplay.plugins.models import DiscoveredPlugin


class PluginLoader:
    """Discover and instantiate plugins from Python entry points or objects."""

    entry_point_groups: tuple[str, ...] = (
        PLUGIN_ENTRY_POINT_GROUP,
        ADAPTER_ENTRY_POINT_GROUP,
    )

    def discover(self) -> tuple[DiscoveredPlugin, ...]:
        """Discover installed AgentReplay plugin entry points."""
        discovered: list[DiscoveredPlugin] = []
        entry_points = importlib.metadata.entry_points()
        for group in self.entry_point_groups:
            for entry_point in entry_points.select(group=group):
                discovered.append(
                    DiscoveredPlugin(
                        name=entry_point.name,
                        source=f"entry-point:{group}:{entry_point.name}",
                        value=entry_point,
                    ),
                )
        return tuple(discovered)

    def load(self, discovered: DiscoveredPlugin) -> AgentReplayPlugin:
        """Instantiate one discovered plugin."""
        value = discovered.value
        if isinstance(value, importlib.metadata.EntryPoint):
            loaded = value.load()
        else:
            loaded = value
        return self.load_object(loaded, source=discovered.source)

    def load_object(
        self,
        value: object,
        *,
        source: str = "object",
    ) -> AgentReplayPlugin:
        """Instantiate a plugin from a class, instance, or factory."""
        if isinstance(value, AgentReplayPlugin):
            return value
        if isinstance(value, type) and issubclass(value, AgentReplayPlugin):
            return value()
        if callable(value):
            plugin = value()
            if isinstance(plugin, AgentReplayPlugin):
                return plugin
        msg = f"Entry {source!r} did not produce an AgentReplayPlugin."
        raise PluginError(msg)

    def load_module(self, module_name: str, attribute: str) -> AgentReplayPlugin:
        """Hot-load a plugin from ``module.attribute``."""
        module = importlib.import_module(module_name)
        return self.load_object(getattr(module, attribute), source=module_name)

    def discover_objects(
        self,
        plugins: Iterable[object],
    ) -> tuple[DiscoveredPlugin, ...]:
        """Create discovered-plugin records from explicit test or app objects."""
        return tuple(
            DiscoveredPlugin(
                name=getattr(plugin, "name", type(plugin).__name__),
                source="object",
                value=plugin,
            )
            for plugin in plugins
        )


__all__ = ["PluginLoader"]
