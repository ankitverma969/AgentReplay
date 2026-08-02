"""Public SDK application facade for AgentReplay extension developers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentreplay.config import Settings, get_settings
from agentreplay.diff import DiffEngine
from agentreplay.observability import ObservabilityEngine
from agentreplay.profiler import ProfilerEngine
from agentreplay.recording import Recorder
from agentreplay.regression import RegressionEngine
from agentreplay.replay import ReplayEngine
from agentreplay.reporting import ReportingEngine
from agentreplay.sdk.events import SDKEventBus
from agentreplay.sdk.extensions import (
    SDKAnalyzer,
    SDKCLICommand,
    SDKExporter,
    SDKFrameworkAdapter,
    SDKReportExtension,
    SDKStorageFactory,
    SDKVisualization,
)
from agentreplay.sdk.hooks import SDKHookManager
from agentreplay.sdk.registry import SDKExtensionRegistry
from agentreplay.security import SecurityEngine
from agentreplay.storage import SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue, Metadata


@dataclass(slots=True)
class SDKContext:
    """Stable SDK context passed to extensions."""

    settings: Settings = field(default_factory=get_settings)
    storage: StorageBackend | None = None
    events: SDKEventBus = field(default_factory=SDKEventBus)
    hooks: SDKHookManager = field(default_factory=SDKHookManager)
    registry: SDKExtensionRegistry = field(default_factory=SDKExtensionRegistry)

    def sqlite_storage(self, db_path: str | Path | None = None) -> SQLiteStorage:
        """Create the default SQLite storage backend."""
        return SQLiteStorage(db_path) if db_path is not None else SQLiteStorage()

    def recorder(self, **kwargs: Any) -> Recorder:
        """Create a recorder through the stable SDK surface."""
        self.hooks.emit("before_recording", payload={"kwargs": _json_safe(kwargs)})
        return Recorder(**kwargs)

    def replay_engine(self) -> ReplayEngine:
        """Create a replay engine."""
        return ReplayEngine(storage=self.storage)

    def diff_engine(self) -> DiffEngine:
        """Create a diff engine."""
        return DiffEngine(storage=self.storage)

    def profiler_engine(self) -> ProfilerEngine:
        """Create a profiler engine."""
        return ProfilerEngine(storage=self.storage)

    def security_engine(self) -> SecurityEngine:
        """Create a security engine."""
        return SecurityEngine()

    def regression_engine(self) -> RegressionEngine:
        """Create a regression engine."""
        return RegressionEngine(storage=self.storage)

    def reporting_engine(self) -> ReportingEngine:
        """Create a reporting engine."""
        return ReportingEngine(storage=self.storage)

    def observability_engine(self) -> ObservabilityEngine:
        """Create an observability engine."""
        return ObservabilityEngine()

    def register_analyzer(self, analyzer: SDKAnalyzer) -> None:
        """Register a custom analyzer."""
        self.registry.register_analyzer(analyzer)

    def register_exporter(self, exporter: SDKExporter) -> None:
        """Register a custom exporter."""
        self.registry.register_exporter(exporter)

    def register_storage(self, storage: SDKStorageFactory) -> None:
        """Register a custom storage factory."""
        self.registry.register_storage(storage)

    def register_visualization(self, visualization: SDKVisualization) -> None:
        """Register a custom visualization."""
        self.registry.register_visualization(visualization)

    def register_framework_adapter(self, adapter: SDKFrameworkAdapter) -> None:
        """Register a custom framework adapter."""
        self.registry.register_framework_adapter(adapter)

    def register_report(self, report: SDKReportExtension) -> None:
        """Register a custom report extension."""
        self.registry.register_report(report)

    def register_cli_command(self, command: SDKCLICommand) -> None:
        """Register a custom CLI command."""
        self.registry.register_cli_command(command)


class AgentReplaySDK:
    """Developer platform facade for AgentReplay extensions."""

    def __init__(self, context: SDKContext | None = None) -> None:
        """Create an SDK facade."""
        self.context = SDKContext() if context is None else context

    @property
    def events(self) -> SDKEventBus:
        """Return the typed SDK event bus."""
        return self.context.events

    @property
    def hooks(self) -> SDKHookManager:
        """Return the SDK hook manager."""
        return self.context.hooks

    @property
    def registry(self) -> SDKExtensionRegistry:
        """Return the extension registry."""
        return self.context.registry

    def register(self, extension: object) -> None:
        """Register a typed SDK extension by metadata kind."""
        metadata = getattr(extension, "metadata", None)
        kind = getattr(metadata, "kind", None)
        if kind == "analyzer":
            self.context.register_analyzer(extension)  # type: ignore[arg-type]
        elif kind == "exporter":
            self.context.register_exporter(extension)  # type: ignore[arg-type]
        elif kind == "storage":
            self.context.register_storage(extension)  # type: ignore[arg-type]
        elif kind == "visualization":
            self.context.register_visualization(extension)  # type: ignore[arg-type]
        elif kind == "framework_adapter":
            self.context.register_framework_adapter(extension)  # type: ignore[arg-type]
        elif kind == "report":
            self.context.register_report(extension)  # type: ignore[arg-type]
        elif kind == "cli_command":
            self.context.register_cli_command(extension)  # type: ignore[arg-type]
        else:
            from agentreplay.exceptions import SDKError

            msg = "Object is not a recognized AgentReplay SDK extension."
            raise SDKError(msg)

    def install_cli_commands(
        self,
        subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    ) -> None:
        """Install registered SDK CLI command extensions."""
        for metadata in self.registry.list("cli_command"):
            command = self.registry.require("cli_command", metadata.name)
            command.register(subparsers)  # type: ignore[attr-defined]


def create_sdk(
    *,
    storage: StorageBackend | None = None,
    metadata: Metadata | None = None,
) -> AgentReplaySDK:
    """Create an AgentReplay SDK facade for extension code."""
    context = SDKContext(storage=storage)
    if metadata:
        context.events.publish(
            "event.created",
            payload={"metadata": dict(metadata)},
            source="sdk",
        )
    return AgentReplaySDK(context)


def _json_safe(value: object) -> JSONValue:
    """Convert SDK metadata payloads into JSON-compatible values."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(item) for item in value]
    return str(value)


__all__ = ["AgentReplaySDK", "SDKContext", "create_sdk"]
