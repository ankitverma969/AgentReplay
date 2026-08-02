"""Shared constants for the AgentReplay package."""

from pathlib import Path
from typing import Final

PACKAGE_NAME: Final[str] = "agentreplay"
LOGGER_NAME: Final[str] = "agentreplay"

EVENT_SCHEMA_VERSION: Final[int] = 1
SQLITE_SCHEMA_VERSION: Final[int] = 1

DEFAULT_DB_PATH: Final[Path] = Path(".agentreplay") / "agentreplay.sqlite"
CONFIG_FILE_NAMES: Final[tuple[str, ...]] = ("agentreplay.toml", ".agentreplay.toml")

ENV_PREFIX: Final[str] = "AGENTREPLAY_"
ENV_ENABLED: Final[str] = f"{ENV_PREFIX}ENABLED"
ENV_DB_PATH: Final[str] = f"{ENV_PREFIX}DB_PATH"
ENV_REDACTION: Final[str] = f"{ENV_PREFIX}REDACTION"
ENV_LOG_LEVEL: Final[str] = f"{ENV_PREFIX}LOG_LEVEL"
ENV_STORAGE_BACKEND: Final[str] = f"{ENV_PREFIX}STORAGE_BACKEND"
ENV_FAIL_MODE: Final[str] = f"{ENV_PREFIX}FAIL_MODE"
ENV_CONFIG_PATH: Final[str] = f"{ENV_PREFIX}CONFIG"
ENV_PLUGINS_ENABLED: Final[str] = f"{ENV_PREFIX}PLUGINS_ENABLED"
ENV_PLUGIN_AUTO_DISCOVER: Final[str] = f"{ENV_PREFIX}PLUGIN_AUTO_DISCOVER"
ENV_DISABLED_PLUGINS: Final[str] = f"{ENV_PREFIX}DISABLED_PLUGINS"
ENV_PLUGIN_CONFIG_PREFIX: Final[str] = f"{ENV_PREFIX}PLUGIN_CONFIG_"

__all__ = [
    "CONFIG_FILE_NAMES",
    "DEFAULT_DB_PATH",
    "ENV_CONFIG_PATH",
    "ENV_DB_PATH",
    "ENV_ENABLED",
    "ENV_FAIL_MODE",
    "ENV_DISABLED_PLUGINS",
    "ENV_PLUGIN_AUTO_DISCOVER",
    "ENV_PLUGIN_CONFIG_PREFIX",
    "ENV_PLUGINS_ENABLED",
    "ENV_LOG_LEVEL",
    "ENV_PREFIX",
    "ENV_REDACTION",
    "ENV_STORAGE_BACKEND",
    "EVENT_SCHEMA_VERSION",
    "LOGGER_NAME",
    "PACKAGE_NAME",
    "SQLITE_SCHEMA_VERSION",
]
