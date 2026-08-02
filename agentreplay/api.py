"""Small public API surface for Phase 1 foundation services."""

from collections.abc import Mapping
from pathlib import Path

from agentreplay.adapters.openai_agents import (
    AgentReplay,
    OpenAIAgentsConfig,
    instrument,
    record_agent,
)
from agentreplay.config import Settings, configure, get_settings, reset_settings
from agentreplay.container import Container, create_container
from agentreplay.diff import DiffEngine
from agentreplay.observability import (
    CorrelationContext,
    ObservabilityConfig,
    ObservabilityEngine,
    TelemetryExportResult,
    TelemetryMetrics,
    TelemetryTrace,
)
from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginManager
from agentreplay.recording import Recorder, record
from agentreplay.replay import ReplayEngine
from agentreplay.security import (
    RedactionStrategy,
    SecurityConfig,
    SecurityEngine,
    SecurityFinding,
    SecurityReport,
    SecurityRule,
)
from agentreplay.storage import (
    EventQuery,
    Pagination,
    RunQuery,
    SQLiteStorage,
    StorageBackend,
)


def load_config(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load AgentReplay settings without changing global package state.

    Args:
        config_path: Optional explicit TOML configuration file path.
        environ: Optional environment mapping for deterministic tests.

    Returns:
        A fully resolved settings object.
    """
    from agentreplay.config import load_settings

    return load_settings(config_path=config_path, environ=environ)


__all__ = [
    "AgentReplay",
    "Container",
    "DiffEngine",
    "EventQuery",
    "ObservabilityConfig",
    "ObservabilityEngine",
    "OpenAIAgentsConfig",
    "Pagination",
    "PluginApp",
    "PluginManager",
    "Recorder",
    "RedactionStrategy",
    "ReplayEngine",
    "RunQuery",
    "SQLiteStorage",
    "Settings",
    "SecurityConfig",
    "SecurityEngine",
    "SecurityFinding",
    "SecurityReport",
    "SecurityRule",
    "StorageBackend",
    "TelemetryExportResult",
    "TelemetryMetrics",
    "TelemetryTrace",
    "AgentReplayPlugin",
    "CorrelationContext",
    "configure",
    "create_container",
    "get_settings",
    "instrument",
    "load_config",
    "record",
    "record_agent",
    "reset_settings",
]
