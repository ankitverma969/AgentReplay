"""Registration facade exposed to AgentReplay plugins."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentreplay.plugins.models import (
    HookName,
    PluginHookContext,
    PluginHookResult,
    PluginRegistration,
    PluginType,
)
from agentreplay.types import Metadata

PluginHookHandler = Callable[[PluginHookContext], None]
CLICommandRegistrar = Callable[[Any], None]


class Exporter(Protocol):
    """Protocol implemented by plugin-provided exporters."""

    def export(self, trace: object) -> str:
        """Export a trace-like object."""


class EventProcessor(Protocol):
    """Protocol implemented by plugin-provided event processors."""

    def process_event(self, event: object) -> object | None:
        """Process an event and return a replacement or ``None``."""


class MetadataCollector(Protocol):
    """Protocol implemented by plugin-provided metadata collectors."""

    def collect(self) -> Metadata:
        """Return metadata to attach to an execution."""


@dataclass(slots=True)
class PluginApp:
    """Mutable registration facade passed to plugin ``register()`` methods."""

    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("agentreplay.plugins"),
    )
    _active_plugin: str | None = None
    _config_by_plugin: Mapping[str, Metadata] = field(default_factory=dict)
    _registrations: list[PluginRegistration] = field(default_factory=list)
    _hooks: dict[HookName, list[tuple[str, PluginHookHandler]]] = field(
        default_factory=dict,
    )

    def activate(self, plugin_name: str, config: Metadata) -> None:
        """Set the plugin currently allowed to register capabilities."""
        self._active_plugin = plugin_name
        merged = dict(self._config_by_plugin)
        merged[plugin_name] = dict(config)
        self._config_by_plugin = merged

    def deactivate(self) -> None:
        """Clear the active plugin registration context."""
        self._active_plugin = None

    def config(self, plugin_name: str | None = None) -> Metadata:
        """Return plugin-specific configuration."""
        resolved_name = self._require_active_plugin(plugin_name)
        return dict(self._config_by_plugin.get(resolved_name, {}))

    def register_agent_framework(self, name: str, value: object) -> None:
        """Register an agent-framework integration."""
        self._register("agent_framework", name, value)

    def register_llm_provider(self, name: str, value: object) -> None:
        """Register an LLM-provider integration."""
        self._register("llm_provider", name, value)

    def register_storage_backend(self, name: str, value: object) -> None:
        """Register a storage backend factory or implementation."""
        self._register("storage_backend", name, value)

    def register_exporter(
        self,
        name: str,
        value: Exporter | Callable[..., str],
    ) -> None:
        """Register an exporter implementation."""
        self._register("exporter", name, value)

    def register_cli_command(self, name: str, registrar: CLICommandRegistrar) -> None:
        """Register a plugin-provided CLI command registrar."""
        self._register("cli_command", name, registrar)

    def register_event_processor(self, name: str, processor: EventProcessor) -> None:
        """Register an event processor."""
        self._register("event_processor", name, processor)

    def register_metadata_collector(
        self,
        name: str,
        collector: MetadataCollector,
    ) -> None:
        """Register a metadata collector."""
        self._register("metadata_collector", name, collector)

    def register_auth_provider(self, name: str, provider: object) -> None:
        """Register a future authentication provider."""
        self._register("auth_provider", name, provider)

    def register_hook(self, hook: HookName, handler: PluginHookHandler) -> None:
        """Register a lifecycle hook handler for the active plugin."""
        plugin_name = self._require_active_plugin()
        self._hooks.setdefault(hook, []).append((plugin_name, handler))

    def registrations(
        self,
        *,
        plugin_name: str | None = None,
        kind: PluginType | None = None,
    ) -> tuple[PluginRegistration, ...]:
        """Return registered capabilities, optionally filtered."""
        registrations = self._registrations
        if plugin_name is not None:
            registrations = [
                registration
                for registration in registrations
                if registration.plugin_name == plugin_name
            ]
        if kind is not None:
            registrations = [
                registration
                for registration in registrations
                if registration.kind == kind
            ]
        return tuple(registrations)

    def remove_plugin(self, plugin_name: str) -> None:
        """Remove registrations and hooks owned by a plugin."""
        self._registrations = [
            registration
            for registration in self._registrations
            if registration.plugin_name != plugin_name
        ]
        self._hooks = {
            hook: [
                (owner, handler) for owner, handler in handlers if owner != plugin_name
            ]
            for hook, handlers in self._hooks.items()
        }

    def emit_hook(
        self,
        hook: HookName,
        *,
        payload: Metadata | None = None,
    ) -> tuple[PluginHookResult, ...]:
        """Invoke hook handlers and isolate plugin failures."""
        context = PluginHookContext(hook=hook, payload=dict(payload or {}))
        results: list[PluginHookResult] = []
        for plugin_name, handler in tuple(self._hooks.get(hook, ())):
            try:
                handler(context)
            except Exception as exc:
                self.logger.warning(
                    "AgentReplay plugin hook failed: %s.%s: %s",
                    plugin_name,
                    hook,
                    exc,
                )
                results.append(
                    PluginHookResult(
                        hook=hook,
                        plugin_name=plugin_name,
                        succeeded=False,
                        error=str(exc),
                    ),
                )
            else:
                results.append(
                    PluginHookResult(
                        hook=hook,
                        plugin_name=plugin_name,
                        succeeded=True,
                    ),
                )
        return tuple(results)

    def _register(self, kind: PluginType, name: str, value: object) -> None:
        """Register one capability for the active plugin."""
        plugin_name = self._require_active_plugin()
        if not name.strip():
            msg = "Plugin registrations must have a non-empty name."
            raise ValueError(msg)
        self._registrations.append(
            PluginRegistration(
                plugin_name=plugin_name,
                kind=kind,
                name=name.strip(),
                value=value,
            ),
        )

    def _require_active_plugin(self, plugin_name: str | None = None) -> str:
        """Return an explicit or currently active plugin name."""
        resolved_name = plugin_name or self._active_plugin
        if resolved_name is None:
            msg = "Plugin registrations require an active plugin context."
            raise RuntimeError(msg)
        return resolved_name


__all__ = [
    "CLICommandRegistrar",
    "EventProcessor",
    "Exporter",
    "MetadataCollector",
    "PluginApp",
    "PluginHookHandler",
]
