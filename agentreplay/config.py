"""Typed configuration loading for AgentReplay."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, Literal, cast

from agentreplay.constants import (
    CONFIG_FILE_NAMES,
    DEFAULT_DB_PATH,
    ENV_CONFIG_PATH,
    ENV_DB_PATH,
    ENV_ENABLED,
    ENV_FAIL_MODE,
    ENV_LOG_LEVEL,
    ENV_REDACTION,
    ENV_STORAGE_BACKEND,
)
from agentreplay.exceptions import ConfigurationError

LogLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]
StorageBackendName = Literal["sqlite"]
FailMode = Literal["fail_open", "fail_closed"]

_VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)
_VALID_STORAGE_BACKENDS: Final[frozenset[str]] = frozenset({"sqlite"})
_VALID_FAIL_MODES: Final[frozenset[str]] = frozenset({"fail_open", "fail_closed"})
_TRUE_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES: Final[frozenset[str]] = frozenset({"0", "false", "no", "off"})

_ACTIVE_SETTINGS: Settings | None = None


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved AgentReplay settings.

    The defaults are intentionally local and conservative. AgentReplay does not
    require network services, API keys, or telemetry to operate.
    """

    enabled: bool = False
    db_path: Path = DEFAULT_DB_PATH
    redaction_enabled: bool = True
    log_level: LogLevel = "WARNING"
    storage_backend: StorageBackendName = "sqlite"
    fail_mode: FailMode = "fail_open"
    config_file: Path | None = None


def load_settings(
    config_path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, object] | None = None,
) -> Settings:
    """Load settings from defaults, TOML configuration, environment, and overrides.

    Args:
        config_path: Optional explicit TOML file path.
        environ: Optional environment mapping. Defaults to ``os.environ``.
        overrides: Optional explicit values with highest precedence.

    Returns:
        A fully validated settings object.

    Raises:
        ConfigurationError: If a file or value cannot be parsed.
    """
    env = os.environ if environ is None else environ
    explicit_config_path = _resolve_optional_path(config_path)
    env_config_path = _resolve_optional_path(env.get(ENV_CONFIG_PATH))
    selected_config_path = (
        explicit_config_path or env_config_path or _find_config_file()
    )

    settings = Settings()
    if selected_config_path is not None:
        config_values = _read_config_file(selected_config_path)
        settings = _apply_mapping(
            settings,
            config_values,
            source=str(selected_config_path),
        )
        settings = replace(settings, config_file=selected_config_path)

    settings = _apply_mapping(settings, _environment_values(env), source="environment")
    if overrides is not None:
        settings = _apply_mapping(settings, overrides, source="overrides")

    return settings


def configure(
    *,
    enabled: bool | None = None,
    db_path: str | Path | None = None,
    redaction_enabled: bool | None = None,
    log_level: str | None = None,
    storage_backend: str | None = None,
    fail_mode: str | None = None,
    config_path: str | Path | None = None,
) -> Settings:
    """Load and store process-wide AgentReplay settings.

    Explicit keyword arguments have the highest priority. Values set to ``None``
    are ignored so callers can override only the fields they need.
    """
    global _ACTIVE_SETTINGS

    overrides: dict[str, object] = {}
    _put_if_not_none(overrides, "enabled", enabled)
    _put_if_not_none(overrides, "db_path", db_path)
    _put_if_not_none(overrides, "redaction_enabled", redaction_enabled)
    _put_if_not_none(overrides, "log_level", log_level)
    _put_if_not_none(overrides, "storage_backend", storage_backend)
    _put_if_not_none(overrides, "fail_mode", fail_mode)

    _ACTIVE_SETTINGS = load_settings(config_path=config_path, overrides=overrides)
    return _ACTIVE_SETTINGS


def get_settings() -> Settings:
    """Return the active settings, loading defaults if needed."""
    global _ACTIVE_SETTINGS

    if _ACTIVE_SETTINGS is None:
        _ACTIVE_SETTINGS = load_settings()
    return _ACTIVE_SETTINGS


def reset_settings() -> None:
    """Clear cached process-wide settings.

    This is mainly useful for tests and long-running processes that need to
    re-read environment or configuration file changes.
    """
    global _ACTIVE_SETTINGS

    _ACTIVE_SETTINGS = None


def _put_if_not_none(
    values: dict[str, object],
    key: str,
    value: object | None,
) -> None:
    """Add a value to a mapping when the value is present."""
    if value is not None:
        values[key] = value


def _resolve_optional_path(value: str | Path | None) -> Path | None:
    """Resolve an optional path value without requiring it to exist."""
    if value is None:
        return None
    return Path(value).expanduser()


def _find_config_file() -> Path | None:
    """Find the first supported config file in the current working directory."""
    for file_name in CONFIG_FILE_NAMES:
        candidate = Path.cwd() / file_name
        if candidate.is_file():
            return candidate
    return None


def _read_config_file(path: Path) -> dict[str, object]:
    """Read an AgentReplay TOML configuration file."""
    if not path.is_file():
        msg = f"AgentReplay config file does not exist: {path}"
        raise ConfigurationError(msg)

    try:
        with path.open("rb") as file_obj:
            loaded = tomllib.load(file_obj)
    except tomllib.TOMLDecodeError as exc:
        msg = f"AgentReplay config file is invalid TOML: {path}"
        raise ConfigurationError(msg) from exc
    except OSError as exc:
        msg = f"AgentReplay config file could not be read: {path}"
        raise ConfigurationError(msg) from exc

    if "agentreplay" in loaded:
        section = loaded["agentreplay"]
        if not isinstance(section, dict):
            msg = "The [agentreplay] configuration section must be a table."
            raise ConfigurationError(msg)
        return cast(dict[str, object], section)

    return cast(dict[str, object], loaded)


def _environment_values(environ: Mapping[str, str]) -> dict[str, object]:
    """Collect AgentReplay settings from environment variables."""
    values: dict[str, object] = {}
    env_to_key = {
        ENV_ENABLED: "enabled",
        ENV_DB_PATH: "db_path",
        ENV_REDACTION: "redaction_enabled",
        ENV_LOG_LEVEL: "log_level",
        ENV_STORAGE_BACKEND: "storage_backend",
        ENV_FAIL_MODE: "fail_mode",
    }
    for env_name, key in env_to_key.items():
        if env_name in environ:
            values[key] = environ[env_name]
    return values


def _apply_mapping(
    settings: Settings,
    values: Mapping[str, object],
    *,
    source: str,
) -> Settings:
    """Apply a validated value mapping to settings."""
    updated = settings
    for key, value in values.items():
        if key == "enabled":
            updated = replace(
                updated, enabled=_parse_bool(value, key=key, source=source)
            )
        elif key == "db_path":
            updated = replace(
                updated, db_path=_parse_path(value, key=key, source=source)
            )
        elif key == "redaction_enabled":
            updated = replace(
                updated,
                redaction_enabled=_parse_bool(value, key=key, source=source),
            )
        elif key == "log_level":
            updated = replace(
                updated,
                log_level=_parse_log_level(value, key=key, source=source),
            )
        elif key == "storage_backend":
            updated = replace(
                updated,
                storage_backend=_parse_storage_backend(value, key=key, source=source),
            )
        elif key == "fail_mode":
            updated = replace(
                updated,
                fail_mode=_parse_fail_mode(value, key=key, source=source),
            )
        elif key == "config_file":
            updated = replace(
                updated,
                config_file=_parse_optional_path(value, key=key, source=source),
            )
        else:
            msg = f"Unknown AgentReplay configuration key {key!r} from {source}."
            raise ConfigurationError(msg)
    return updated


def _parse_bool(value: object, *, key: str, source: str) -> bool:
    """Parse a strict boolean configuration value."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _TRUE_VALUES:
            return True
        if normalized in _FALSE_VALUES:
            return False
    msg = f"Configuration key {key!r} from {source} must be a boolean."
    raise ConfigurationError(msg)


def _parse_path(value: object, *, key: str, source: str) -> Path:
    """Parse a filesystem path configuration value."""
    if isinstance(value, Path):
        return value.expanduser()
    if isinstance(value, str) and value.strip():
        return Path(value).expanduser()
    msg = f"Configuration key {key!r} from {source} must be a non-empty path."
    raise ConfigurationError(msg)


def _parse_optional_path(value: object, *, key: str, source: str) -> Path | None:
    """Parse an optional path configuration value."""
    if value is None:
        return None
    return _parse_path(value, key=key, source=source)


def _parse_log_level(value: object, *, key: str, source: str) -> LogLevel:
    """Parse and normalize a logging level."""
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in _VALID_LOG_LEVELS:
            return cast(LogLevel, normalized)
    msg = f"Configuration key {key!r} from {source} must be a valid log level."
    raise ConfigurationError(msg)


def _parse_storage_backend(
    value: object,
    *,
    key: str,
    source: str,
) -> StorageBackendName:
    """Parse a storage backend name."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _VALID_STORAGE_BACKENDS:
            return cast(StorageBackendName, normalized)
    msg = f"Configuration key {key!r} from {source} must be a supported backend."
    raise ConfigurationError(msg)


def _parse_fail_mode(value: object, *, key: str, source: str) -> FailMode:
    """Parse recorder failure behavior."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _VALID_FAIL_MODES:
            return cast(FailMode, normalized)
    msg = f"Configuration key {key!r} from {source} must be a supported fail mode."
    raise ConfigurationError(msg)


__all__ = [
    "FailMode",
    "LogLevel",
    "Settings",
    "StorageBackendName",
    "configure",
    "get_settings",
    "load_settings",
    "reset_settings",
]
