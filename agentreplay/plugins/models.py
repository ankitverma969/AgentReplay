"""Data models used by the AgentReplay Plugin SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from agentreplay.types import Metadata

PluginType = Literal[
    "agent_framework",
    "llm_provider",
    "storage_backend",
    "exporter",
    "cli_command",
    "event_processor",
    "metadata_collector",
    "secret_detector",
    "pii_detector",
    "redaction_rule",
    "auth_provider",
]
PluginStatus = Literal["discovered", "loaded", "disabled", "failed", "unloaded"]
ConfigValueType = Literal["str", "int", "float", "bool", "list", "dict", "any"]
HookName = Literal[
    "before_run",
    "after_run",
    "before_event",
    "after_event",
    "before_replay",
    "after_replay",
    "before_export",
    "after_export",
    "plugin_loaded",
    "plugin_unloaded",
]

PLUGIN_TYPES: tuple[PluginType, ...] = (
    "agent_framework",
    "llm_provider",
    "storage_backend",
    "exporter",
    "cli_command",
    "event_processor",
    "metadata_collector",
    "secret_detector",
    "pii_detector",
    "redaction_rule",
    "auth_provider",
)
HOOK_NAMES: tuple[HookName, ...] = (
    "before_run",
    "after_run",
    "before_event",
    "after_event",
    "before_replay",
    "after_replay",
    "before_export",
    "after_export",
    "plugin_loaded",
    "plugin_unloaded",
)
CONFIG_VALUE_TYPES: tuple[ConfigValueType, ...] = (
    "str",
    "int",
    "float",
    "bool",
    "list",
    "dict",
    "any",
)


@dataclass(frozen=True, slots=True)
class PluginDependency:
    """Dependency declared by an AgentReplay plugin."""

    name: str
    version_constraint: str | None = None
    optional: bool = False


@dataclass(frozen=True, slots=True)
class PluginMetadata:
    """Static metadata declared by an AgentReplay plugin."""

    name: str
    version: str
    plugin_type: PluginType
    summary: str = ""
    min_agentreplay_version: str | None = None
    max_agentreplay_version: str | None = None
    dependencies: tuple[PluginDependency, ...] = ()
    config_schema: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginHookContext:
    """Context passed to lifecycle hook handlers."""

    hook: HookName
    plugin_name: str | None = None
    payload: Metadata = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginHookResult:
    """Result of invoking one plugin hook handler."""

    hook: HookName
    plugin_name: str
    succeeded: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class PluginRegistration:
    """One capability registered by a plugin."""

    plugin_name: str
    kind: PluginType
    name: str
    value: object


@dataclass(frozen=True, slots=True)
class DiscoveredPlugin:
    """Entry-point candidate discovered before plugin loading."""

    name: str
    source: str
    value: object


@dataclass(frozen=True, slots=True)
class PluginRecord:
    """Registry record for one plugin."""

    metadata: PluginMetadata
    status: PluginStatus
    source: str
    plugin: object | None = None
    error: str | None = None
    loaded_at: datetime | None = None

    def mark(self, status: PluginStatus, *, error: str | None = None) -> PluginRecord:
        """Return a copy with an updated status."""
        return PluginRecord(
            metadata=self.metadata,
            status=status,
            source=self.source,
            plugin=self.plugin,
            error=error,
            loaded_at=datetime.now(UTC) if status == "loaded" else self.loaded_at,
        )


__all__ = [
    "CONFIG_VALUE_TYPES",
    "HOOK_NAMES",
    "PLUGIN_TYPES",
    "ConfigValueType",
    "DiscoveredPlugin",
    "HookName",
    "PluginDependency",
    "PluginHookContext",
    "PluginHookResult",
    "PluginMetadata",
    "PluginRecord",
    "PluginRegistration",
    "PluginStatus",
    "PluginType",
]
