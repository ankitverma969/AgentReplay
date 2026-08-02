"""Bridge between the public SDK and AgentReplay Plugin SDK."""

from __future__ import annotations

from typing import Any, ClassVar, cast

from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginMetadata, PluginType
from agentreplay.sdk.app import SDKContext
from agentreplay.sdk.extensions import (
    SDKAnalyzer,
    SDKCLICommand,
    SDKExporter,
    SDKReportExtension,
    SDKStorageFactory,
    SDKVisualization,
)
from agentreplay.sdk.models import SDKExtensionMetadata


class AgentReplaySDKPlugin(AgentReplayPlugin):
    """Base class for plugins that expose SDK extensions."""

    name = "agentreplay-sdk-plugin"
    version = "0.1.0"
    plugin_type: ClassVar[PluginType] = "sdk_analyzer"
    summary = "AgentReplay SDK extension plugin."

    def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
        """Return SDK extensions owned by this plugin."""
        return ()

    def register(self, app: object) -> None:
        """Register SDK extensions through the legacy plugin facade."""
        context = SDKContext()
        plugin_app = cast(PluginApp, app)
        for extension in self.sdk_extensions(context):
            _register_extension(plugin_app, extension)


def plugin_metadata_from_sdk(metadata: SDKExtensionMetadata) -> PluginMetadata:
    """Convert SDK extension metadata to Plugin SDK metadata."""
    plugin_type = {
        "analyzer": "sdk_analyzer",
        "exporter": "sdk_exporter",
        "storage": "sdk_storage",
        "visualization": "sdk_visualization",
        "framework_adapter": "agent_framework",
        "report": "sdk_report",
        "cli_command": "cli_command",
    }[metadata.kind]
    return PluginMetadata(
        name=metadata.name,
        version=metadata.version,
        plugin_type=cast(PluginType, plugin_type),
        summary=metadata.summary,
        min_agentreplay_version=metadata.compatibility.min_sdk_version,
        max_agentreplay_version=metadata.compatibility.max_sdk_version,
        config_schema=metadata.config_schema,
    )


def _register_extension(app: PluginApp, extension: object) -> None:
    """Register one SDK extension with the existing plugin app facade."""
    metadata = cast(Any, extension).metadata
    if metadata.kind == "analyzer":
        app.register_sdk_analyzer(metadata.name, extension)
    elif metadata.kind == "exporter":
        app.register_sdk_exporter(metadata.name, extension)
    elif metadata.kind == "storage":
        app.register_sdk_storage(metadata.name, extension)
    elif metadata.kind == "visualization":
        app.register_sdk_visualization(metadata.name, extension)
    elif metadata.kind == "framework_adapter":
        app.register_agent_framework(metadata.name, extension)
    elif metadata.kind == "report":
        app.register_sdk_report(metadata.name, extension)
    elif metadata.kind == "cli_command":
        app.register_cli_command(metadata.name, cast(Any, extension).register)


def analyzer_plugin(extension: SDKAnalyzer) -> AgentReplaySDKPlugin:
    """Create a plugin wrapper for one analyzer extension."""

    class _AnalyzerPlugin(AgentReplaySDKPlugin):
        name = extension.metadata.name
        version = extension.metadata.version
        plugin_type: ClassVar[PluginType] = "sdk_analyzer"
        summary = extension.metadata.summary

        def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
            return (extension,)

    return _AnalyzerPlugin()


def exporter_plugin(extension: SDKExporter) -> AgentReplaySDKPlugin:
    """Create a plugin wrapper for one exporter extension."""

    class _ExporterPlugin(AgentReplaySDKPlugin):
        name = extension.metadata.name
        version = extension.metadata.version
        plugin_type: ClassVar[PluginType] = "sdk_exporter"
        summary = extension.metadata.summary

        def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
            return (extension,)

    return _ExporterPlugin()


def report_plugin(
    extension: SDKReportExtension | SDKVisualization,
) -> AgentReplaySDKPlugin:
    """Create a plugin wrapper for one report or visualization extension."""

    class _ReportPlugin(AgentReplaySDKPlugin):
        name = extension.metadata.name
        version = extension.metadata.version
        plugin_type: ClassVar[PluginType] = "sdk_report"
        summary = extension.metadata.summary

        def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
            return (extension,)

    return _ReportPlugin()


def storage_plugin(extension: SDKStorageFactory) -> AgentReplaySDKPlugin:
    """Create a plugin wrapper for one storage extension."""

    class _StoragePlugin(AgentReplaySDKPlugin):
        name = extension.metadata.name
        version = extension.metadata.version
        plugin_type: ClassVar[PluginType] = "sdk_storage"
        summary = extension.metadata.summary

        def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
            return (extension,)

    return _StoragePlugin()


def cli_plugin(extension: SDKCLICommand) -> AgentReplaySDKPlugin:
    """Create a plugin wrapper for one CLI extension."""

    class _CLIPlugin(AgentReplaySDKPlugin):
        name = extension.metadata.name
        version = extension.metadata.version
        plugin_type: ClassVar[PluginType] = "cli_command"
        summary = extension.metadata.summary

        def sdk_extensions(self, _context: SDKContext) -> tuple[object, ...]:
            return (extension,)

    return _CLIPlugin()


__all__ = [
    "AgentReplaySDKPlugin",
    "analyzer_plugin",
    "cli_plugin",
    "exporter_plugin",
    "plugin_metadata_from_sdk",
    "report_plugin",
    "storage_plugin",
]
