"""Small public API surface for Phase 1 foundation services."""

from collections.abc import Mapping
from pathlib import Path

from agentreplay.config import Settings, configure, get_settings, reset_settings
from agentreplay.container import Container, create_container
from agentreplay.recording import Recorder, record
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
    "Container",
    "EventQuery",
    "Pagination",
    "Recorder",
    "RunQuery",
    "SQLiteStorage",
    "Settings",
    "StorageBackend",
    "configure",
    "create_container",
    "get_settings",
    "load_config",
    "record",
    "reset_settings",
]
