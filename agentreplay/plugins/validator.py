"""Validation helpers for AgentReplay plugins."""

from __future__ import annotations

import re
from collections.abc import Mapping

from agentreplay.exceptions import PluginError
from agentreplay.plugins.base import AgentReplayPlugin
from agentreplay.plugins.compatibility import ensure_agentreplay_compatible
from agentreplay.plugins.models import CONFIG_VALUE_TYPES, PLUGIN_TYPES, PluginMetadata
from agentreplay.types import JSONValue, Metadata
from agentreplay.version import __version__

_PLUGIN_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")


class PluginValidator:
    """Validate plugin instances, metadata, and plugin-specific config."""

    def validate_plugin(self, plugin: object) -> AgentReplayPlugin:
        """Validate and return a typed plugin instance."""
        if not isinstance(plugin, AgentReplayPlugin):
            msg = "AgentReplay plugins must subclass AgentReplayPlugin."
            raise PluginError(msg)
        metadata = plugin.metadata()
        self.validate_metadata(metadata)
        ensure_agentreplay_compatible(
            plugin_name=metadata.name,
            agentreplay_version=__version__,
            min_version=metadata.min_agentreplay_version,
            max_version=metadata.max_agentreplay_version,
        )
        return plugin

    def validate_metadata(self, metadata: PluginMetadata) -> None:
        """Validate static plugin metadata."""
        if not _PLUGIN_NAME_PATTERN.fullmatch(metadata.name):
            msg = (
                "Plugin names must start with a lowercase letter and contain "
                "only lowercase letters, numbers, dots, underscores, or hyphens."
            )
            raise PluginError(msg)
        if not metadata.version.strip():
            msg = f"Plugin {metadata.name!r} must declare a non-empty version."
            raise PluginError(msg)
        if metadata.plugin_type not in PLUGIN_TYPES:
            msg = (
                f"Plugin {metadata.name!r} has unsupported type "
                f"{metadata.plugin_type!r}."
            )
            raise PluginError(msg)
        for key, value_type in metadata.config_schema.items():
            if not isinstance(key, str) or not key.strip():
                msg = f"Plugin {metadata.name!r} has an invalid config key."
                raise PluginError(msg)
            if value_type not in CONFIG_VALUE_TYPES:
                msg = (
                    f"Plugin {metadata.name!r} config key {key!r} declares "
                    f"unsupported type {value_type!r}."
                )
                raise PluginError(msg)

    def validate_config(
        self,
        metadata: PluginMetadata,
        config: Metadata,
        plugin: AgentReplayPlugin,
    ) -> None:
        """Validate plugin configuration against schema and plugin hook."""
        schema = metadata.config_schema
        for key, value in config.items():
            expected = schema.get(key)
            if expected is not None and not _matches_type(value, expected):
                msg = (
                    f"Plugin {metadata.name!r} config key {key!r} must be "
                    f"of type {expected}."
                )
                raise PluginError(msg)
        plugin.validate_config(config)


def _matches_type(value: JSONValue, expected: object) -> bool:
    """Return whether a JSON value matches a plugin schema type name."""
    if expected == "any":
        return True
    if expected == "str":
        return isinstance(value, str)
    if expected == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "float":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "list":
        return isinstance(value, list | tuple)
    if expected == "dict":
        return isinstance(value, Mapping)
    return False


__all__ = ["PluginValidator"]
