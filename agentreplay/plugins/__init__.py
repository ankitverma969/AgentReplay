"""Plugin SDK for external AgentReplay extensions."""

from agentreplay.plugins.app import (
    CLICommandRegistrar,
    CustomMetric,
    CustomProfiler,
    CustomRecommendation,
    EventProcessor,
    Exporter,
    MetadataCollector,
    PluginApp,
    PluginHookHandler,
    RegressionAnalyzer,
    RegressionRecommendation,
    RegressionRule,
    ReportExtension,
    TelemetryAttributeEnricher,
)
from agentreplay.plugins.base import AgentReplayPlugin
from agentreplay.plugins.compatibility import (
    ensure_agentreplay_compatible,
    satisfies_version_constraint,
)
from agentreplay.plugins.discovery import PluginLoader
from agentreplay.plugins.entrypoints import (
    ADAPTER_ENTRY_POINT_GROUP,
    PLUGIN_ENTRY_POINT_GROUP,
)
from agentreplay.plugins.manager import PluginManager
from agentreplay.plugins.models import (
    CONFIG_VALUE_TYPES,
    HOOK_NAMES,
    PLUGIN_TYPES,
    ConfigValueType,
    DiscoveredPlugin,
    HookName,
    PluginDependency,
    PluginHookContext,
    PluginHookResult,
    PluginMetadata,
    PluginRecord,
    PluginRegistration,
    PluginStatus,
    PluginType,
)
from agentreplay.plugins.registry import PluginRegistry
from agentreplay.plugins.resolver import PluginDependencyResolver
from agentreplay.plugins.validator import PluginValidator

__all__ = [
    "ADAPTER_ENTRY_POINT_GROUP",
    "CONFIG_VALUE_TYPES",
    "CLICommandRegistrar",
    "ConfigValueType",
    "CustomMetric",
    "CustomProfiler",
    "CustomRecommendation",
    "DiscoveredPlugin",
    "EventProcessor",
    "Exporter",
    "HOOK_NAMES",
    "HookName",
    "MetadataCollector",
    "PLUGIN_TYPES",
    "PLUGIN_ENTRY_POINT_GROUP",
    "PluginApp",
    "PluginDependency",
    "PluginDependencyResolver",
    "PluginHookContext",
    "PluginHookHandler",
    "PluginHookResult",
    "PluginLoader",
    "PluginManager",
    "PluginMetadata",
    "PluginRecord",
    "PluginRegistration",
    "PluginRegistry",
    "PluginStatus",
    "PluginType",
    "PluginValidator",
    "ReportExtension",
    "RegressionAnalyzer",
    "RegressionRecommendation",
    "RegressionRule",
    "TelemetryAttributeEnricher",
    "AgentReplayPlugin",
    "ensure_agentreplay_compatible",
    "satisfies_version_constraint",
]
