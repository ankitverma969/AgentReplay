"""Stable public SDK and extension platform for AgentReplay."""

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.sdk.app import AgentReplaySDK, SDKContext, create_sdk
from agentreplay.sdk.cli import register_sdk_cli_commands
from agentreplay.sdk.compat import (
    DEPRECATION_POLICY,
    SDK_API_VERSION,
    compatible,
    deprecated,
    ensure_sdk_compatible,
)
from agentreplay.sdk.events import SDKEventBus, SDKEventHandler
from agentreplay.sdk.extensions import (
    BaseAnalyzer,
    BaseCLICommand,
    BaseExporter,
    BaseReportExtension,
    SDKAnalyzer,
    SDKCLICommand,
    SDKExporter,
    SDKFrameworkAdapter,
    SDKReportExtension,
    SDKStorageFactory,
    SDKVisualization,
    analyzer_metadata,
    exporter_metadata,
)
from agentreplay.sdk.hooks import SDKHookHandler, SDKHookManager
from agentreplay.sdk.models import (
    AnalyzerResult,
    ExportResult,
    ReportSection,
    SDKCompatibility,
    SDKEvent,
    SDKEventName,
    SDKExtensionKind,
    SDKExtensionMetadata,
    SDKHookContext,
    SDKHookName,
    SDKHookResult,
    SDKStability,
    SDKVersion,
)
from agentreplay.sdk.plugin import (
    AgentReplaySDKPlugin,
    analyzer_plugin,
    cli_plugin,
    exporter_plugin,
    plugin_metadata_from_sdk,
    report_plugin,
    storage_plugin,
)
from agentreplay.sdk.registry import SDKExtensionRegistry

__all__ = [
    "DEPRECATION_POLICY",
    "SDK_API_VERSION",
    "AgentReplaySDK",
    "AgentReplaySDKPlugin",
    "AnalyzerResult",
    "BaseAnalyzer",
    "BaseCLICommand",
    "BaseExporter",
    "BaseReportExtension",
    "EventRecord",
    "ExportResult",
    "ReportSection",
    "RunRecord",
    "SDKAnalyzer",
    "SDKCLICommand",
    "SDKCompatibility",
    "SDKContext",
    "SDKEvent",
    "SDKEventBus",
    "SDKEventHandler",
    "SDKEventName",
    "SDKExporter",
    "SDKExtensionKind",
    "SDKExtensionMetadata",
    "SDKFrameworkAdapter",
    "SDKHookContext",
    "SDKHookHandler",
    "SDKHookManager",
    "SDKHookName",
    "SDKHookResult",
    "SDKReportExtension",
    "SDKStability",
    "SDKStorageFactory",
    "SDKVersion",
    "SDKVisualization",
    "SDKExtensionRegistry",
    "TraceSnapshot",
    "analyzer_metadata",
    "analyzer_plugin",
    "cli_plugin",
    "compatible",
    "create_sdk",
    "deprecated",
    "ensure_sdk_compatible",
    "exporter_metadata",
    "exporter_plugin",
    "plugin_metadata_from_sdk",
    "register_sdk_cli_commands",
    "report_plugin",
    "storage_plugin",
]
