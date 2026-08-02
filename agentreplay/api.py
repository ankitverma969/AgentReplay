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
from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginManager
from agentreplay.recording import Recorder, record
from agentreplay.replay import ReplayEngine
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
    "OpenAIAgentsConfig",
    "Pagination",
    "PluginApp",
    "PluginManager",
    "Recorder",
    "ReplayEngine",
    "RunQuery",
    "SQLiteStorage",
    "Settings",
    "StorageBackend",
    "AgentReplayPlugin",
    "configure",
    "create_container",
    "get_settings",
    "instrument",
    "load_config",
    "record",
    "record_agent",
    "reset_settings",
]
