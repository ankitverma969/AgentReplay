"""High-level Plugin SDK manager for AgentReplay."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence

from agentreplay.config import Settings, get_settings
from agentreplay.exceptions import PluginError
from agentreplay.plugins.app import PluginApp
from agentreplay.plugins.base import AgentReplayPlugin
from agentreplay.plugins.discovery import PluginLoader
from agentreplay.plugins.models import (
    DiscoveredPlugin,
    HookName,
    PluginHookResult,
    PluginMetadata,
    PluginRecord,
    PluginStatus,
)
from agentreplay.plugins.registry import PluginRegistry
from agentreplay.plugins.resolver import PluginDependencyResolver
from agentreplay.plugins.validator import PluginValidator
from agentreplay.types import Metadata


class PluginManager:
    """Discover, validate, load, and unload AgentReplay plugins."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        app: PluginApp | None = None,
        registry: PluginRegistry | None = None,
        loader: PluginLoader | None = None,
        validator: PluginValidator | None = None,
        resolver: PluginDependencyResolver | None = None,
        disabled_plugins: Sequence[str] = (),
        fail_open: bool = True,
        logger: logging.Logger | None = None,
    ) -> None:
        """Create a plugin manager."""
        self.settings = get_settings() if settings is None else settings
        self.app = PluginApp() if app is None else app
        self.registry = PluginRegistry() if registry is None else registry
        self.loader = PluginLoader() if loader is None else loader
        self.validator = PluginValidator() if validator is None else validator
        self.resolver = PluginDependencyResolver() if resolver is None else resolver
        self.fail_open = fail_open
        self.logger = (
            logging.getLogger("agentreplay.plugins") if logger is None else logger
        )
        self._explicit_disabled = frozenset(disabled_plugins)

    def load_plugins(
        self,
        plugins: Iterable[object] = (),
        *,
        discover: bool | None = None,
    ) -> tuple[PluginRecord, ...]:
        """Discover and load plugins, returning registry records."""
        candidates: list[DiscoveredPlugin] = []
        should_discover = (
            self.settings.plugin_auto_discover if discover is None else discover
        )
        if should_discover:
            candidates.extend(self.loader.discover())
        candidates.extend(self.loader.discover_objects(plugins))
        records = self._prepare_records(tuple(candidates))
        enabled_records = tuple(
            record for record in records if record.status != "disabled"
        )
        try:
            ordered = self.resolver.resolve(enabled_records)
        except PluginError as exc:
            self._handle_failure("dependency-resolution", exc)
            ordered = enabled_records if self.fail_open else ()
        for record in ordered:
            self._load_record(record)
        return self.registry.records()

    def load_plugin(self, plugin: object, *, source: str = "object") -> PluginRecord:
        """Hot-load one plugin object, class, or factory."""
        discovered = DiscoveredPlugin(
            name=getattr(plugin, "name", source),
            source=source,
            value=plugin,
        )
        records = self._prepare_records((discovered,))
        if not records:
            msg = f"Plugin {source!r} was disabled."
            raise PluginError(msg)
        record = records[0]
        if record.status != "disabled":
            self._load_record(record)
        return self.registry.require(record.metadata.name)

    def unload_plugin(self, name: str) -> None:
        """Unload one plugin and remove its registrations."""
        record = self.registry.require(name)
        plugin = record.plugin
        if isinstance(plugin, AgentReplayPlugin):
            try:
                plugin.on_plugin_unloaded(self.app)
                self.app.emit_hook(
                    "plugin_unloaded",
                    payload={"plugin_name": name},
                )
            except Exception as exc:
                self._handle_failure(name, exc)
        self.app.remove_plugin(name)
        self.registry.update(record.mark("unloaded"))

    def disable_plugin(self, name: str) -> None:
        """Mark a plugin disabled for this manager instance."""
        record = self.registry.require(name)
        self.registry.update(record.mark("disabled"))
        self.app.remove_plugin(name)

    def emit_hook(
        self,
        hook: HookName,
        *,
        payload: Metadata | None = None,
    ) -> tuple[PluginHookResult, ...]:
        """Emit a lifecycle hook to loaded plugins."""
        return self.app.emit_hook(hook, payload=payload)

    def _prepare_records(
        self,
        candidates: tuple[DiscoveredPlugin, ...],
    ) -> tuple[PluginRecord, ...]:
        """Load plugin objects enough to validate and register records."""
        prepared: list[PluginRecord] = []
        for candidate in candidates:
            try:
                plugin = self.loader.load(candidate)
                validated = self.validator.validate_plugin(plugin)
                metadata = validated.metadata()
                config = self.settings.plugin_config.get(metadata.name, {})
                self.validator.validate_config(metadata, config, validated)
                status: PluginStatus = (
                    "disabled" if self._is_disabled(metadata.name) else "discovered"
                )
                record = self.registry.add(
                    metadata,
                    source=candidate.source,
                    plugin=validated,
                    status=status,
                )
                prepared.append(record)
            except Exception as exc:
                self._record_failed_candidate(candidate, exc)
        return tuple(prepared)

    def _load_record(self, record: PluginRecord) -> None:
        """Register one prepared plugin record."""
        plugin = record.plugin
        if not isinstance(plugin, AgentReplayPlugin):
            msg = f"Plugin record {record.metadata.name!r} has no plugin instance."
            self._handle_failure(record.metadata.name, PluginError(msg))
            return
        config = self.settings.plugin_config.get(record.metadata.name, {})
        try:
            self.app.activate(record.metadata.name, config)
            plugin.register(self.app)
            plugin.on_plugin_loaded(self.app)
            self.app.emit_hook(
                "plugin_loaded",
                payload={"plugin_name": record.metadata.name},
            )
        except Exception as exc:
            self.registry.update(record.mark("failed", error=str(exc)))
            self.app.remove_plugin(record.metadata.name)
            self._handle_failure(record.metadata.name, exc)
        else:
            self.registry.update(record.mark("loaded"))
        finally:
            self.app.deactivate()

    def _record_failed_candidate(
        self,
        candidate: DiscoveredPlugin,
        exc: Exception,
    ) -> None:
        """Store a failed discovery record when enough information is available."""
        self.logger.warning(
            "AgentReplay plugin failed to load: %s: %s",
            candidate.name,
            exc,
        )
        fallback_name = _fallback_plugin_name(candidate.name)
        if self.registry.get(fallback_name) is None:
            self.registry.add(
                PluginMetadata(
                    name=fallback_name,
                    version="unknown",
                    plugin_type="event_processor",
                    summary="Plugin failed before metadata could be loaded.",
                ),
                source=candidate.source,
                status="failed",
                error=str(exc),
            )
        if not self.fail_open:
            raise PluginError(str(exc)) from exc

    def _handle_failure(self, plugin_name: str, exc: Exception) -> None:
        """Handle plugin failures according to manager policy."""
        self.logger.warning("AgentReplay plugin failure: %s: %s", plugin_name, exc)
        if not self.fail_open:
            raise PluginError(str(exc)) from exc

    def _is_disabled(self, name: str) -> bool:
        """Return whether a plugin is disabled by settings or manager input."""
        disabled = set(self.settings.disabled_plugins) | set(self._explicit_disabled)
        return not self.settings.plugins_enabled or name in disabled


def _fallback_plugin_name(name: str) -> str:
    """Return a registry-safe name for failed plugin candidates."""
    lowered = name.strip().lower() or "unknown"
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in lowered)
    if not safe[0].isalpha():
        safe = f"plugin-{safe}"
    return safe


__all__ = ["PluginManager"]
