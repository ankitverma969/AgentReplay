"""Typed configuration loading for AgentReplay."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Final, Literal, cast

from agentreplay.constants import (
    CONFIG_FILE_NAMES,
    DEFAULT_DB_PATH,
    ENV_CONFIG_PATH,
    ENV_DB_PATH,
    ENV_DISABLED_PLUGINS,
    ENV_ENABLED,
    ENV_FAIL_MODE,
    ENV_LOG_LEVEL,
    ENV_PLUGIN_AUTO_DISCOVER,
    ENV_PLUGIN_CONFIG_PREFIX,
    ENV_PLUGINS_ENABLED,
    ENV_REDACTION,
    ENV_STORAGE_BACKEND,
)
from agentreplay.exceptions import ConfigurationError
from agentreplay.types import JSONValue, Metadata

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
    plugins_enabled: bool = True
    plugin_auto_discover: bool = True
    disabled_plugins: tuple[str, ...] = ()
    plugin_config: Mapping[str, Metadata] = field(default_factory=dict)


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
    plugins_enabled: bool | None = None,
    plugin_auto_discover: bool | None = None,
    disabled_plugins: tuple[str, ...] | None = None,
    plugin_config: Mapping[str, Metadata] | None = None,
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
    _put_if_not_none(overrides, "plugins_enabled", plugins_enabled)
    _put_if_not_none(overrides, "plugin_auto_discover", plugin_auto_discover)
    _put_if_not_none(overrides, "disabled_plugins", disabled_plugins)
    _put_if_not_none(overrides, "plugin_config", plugin_config)

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
        ENV_PLUGINS_ENABLED: "plugins_enabled",
        ENV_PLUGIN_AUTO_DISCOVER: "plugin_auto_discover",
        ENV_DISABLED_PLUGINS: "disabled_plugins",
    }
    for env_name, key in env_to_key.items():
        if env_name in environ:
            values[key] = environ[env_name]
    plugin_config = _plugin_environment_values(environ)
    if plugin_config:
        values["plugin_config"] = plugin_config
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
        elif key == "plugins_enabled":
            updated = replace(
                updated,
                plugins_enabled=_parse_bool(value, key=key, source=source),
            )
        elif key == "plugin_auto_discover":
            updated = replace(
                updated,
                plugin_auto_discover=_parse_bool(value, key=key, source=source),
            )
        elif key == "disabled_plugins":
            updated = replace(
                updated,
                disabled_plugins=_parse_string_tuple(value, key=key, source=source),
            )
        elif key == "plugin_config":
            plugin_config = {
                plugin_name: dict(plugin_values)
                for plugin_name, plugin_values in updated.plugin_config.items()
            }
            for plugin_name, plugin_values in _parse_plugin_config(
                value,
                key=key,
                source=source,
            ).items():
                existing = dict(plugin_config.get(plugin_name, {}))
                existing.update(plugin_values)
                plugin_config[plugin_name] = existing
            updated = replace(
                updated,
                plugin_config=plugin_config,
            )
        elif key == "plugins":
            updated = _apply_plugins_table(updated, value, source=source)
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


def _parse_string_tuple(value: object, *, key: str, source: str) -> tuple[str, ...]:
    """Parse string-list configuration values."""
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list | tuple):
        values: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                msg = f"Configuration key {key!r} from {source} must contain strings."
                raise ConfigurationError(msg)
            values.append(item.strip())
        return tuple(values)
    msg = f"Configuration key {key!r} from {source} must be a string list."
    raise ConfigurationError(msg)


def _apply_plugins_table(
    settings: Settings,
    value: object,
    *,
    source: str,
) -> Settings:
    """Apply the nested ``plugins`` configuration table."""
    if not isinstance(value, Mapping):
        msg = f"Configuration key 'plugins' from {source} must be a table."
        raise ConfigurationError(msg)

    updated = settings
    plugin_config: dict[str, Metadata] = dict(settings.plugin_config)
    for raw_key, item in value.items():
        key = str(raw_key)
        if key == "enabled":
            updated = replace(
                updated,
                plugins_enabled=_parse_bool(item, key=key, source=source),
            )
        elif key == "auto_discover":
            updated = replace(
                updated,
                plugin_auto_discover=_parse_bool(item, key=key, source=source),
            )
        elif key == "disabled":
            updated = replace(
                updated,
                disabled_plugins=_parse_string_tuple(item, key=key, source=source),
            )
        elif isinstance(item, Mapping):
            plugin_config[key] = _parse_metadata_mapping(item, key=key, source=source)
        else:
            msg = f"Plugin config table {key!r} from {source} must be a table."
            raise ConfigurationError(msg)
    return replace(updated, plugin_config=plugin_config)


def _parse_plugin_config(
    value: object,
    *,
    key: str,
    source: str,
) -> Mapping[str, Metadata]:
    """Parse explicit plugin configuration mappings."""
    if not isinstance(value, Mapping):
        msg = f"Configuration key {key!r} from {source} must be a mapping."
        raise ConfigurationError(msg)
    parsed: dict[str, Metadata] = {}
    for plugin_name, plugin_values in value.items():
        if not isinstance(plugin_name, str) or not plugin_name.strip():
            msg = f"Configuration key {key!r} from {source} has an invalid plugin name."
            raise ConfigurationError(msg)
        if not isinstance(plugin_values, Mapping):
            msg = (
                f"Configuration key {key!r} for plugin {plugin_name!r} "
                f"from {source} must be a mapping."
            )
            raise ConfigurationError(msg)
        parsed[plugin_name.strip()] = _parse_metadata_mapping(
            plugin_values,
            key=plugin_name,
            source=source,
        )
    return parsed


def _parse_metadata_mapping(
    value: Mapping[object, object],
    *,
    key: str,
    source: str,
) -> Metadata:
    """Parse a plugin metadata/config mapping into JSON-compatible values."""
    parsed: dict[str, JSONValue] = {}
    for raw_key, item in value.items():
        if not isinstance(raw_key, str) or not raw_key.strip():
            msg = f"Plugin config {key!r} from {source} must use string keys."
            raise ConfigurationError(msg)
        parsed[raw_key.strip()] = _parse_json_value(item, key=raw_key, source=source)
    return parsed


def _parse_json_value(value: object, *, key: str, source: str) -> JSONValue:
    """Parse a value allowed in plugin configuration."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return [_parse_json_value(item, key=key, source=source) for item in value]
    if isinstance(value, Mapping):
        return _parse_metadata_mapping(value, key=key, source=source)
    msg = f"Plugin config value {key!r} from {source} must be JSON-compatible."
    raise ConfigurationError(msg)


def _plugin_environment_values(environ: Mapping[str, str]) -> dict[str, Metadata]:
    """Collect plugin-specific settings from environment variables."""
    values: dict[str, dict[str, JSONValue]] = {}
    for env_name, env_value in environ.items():
        if not env_name.startswith(ENV_PLUGIN_CONFIG_PREFIX):
            continue
        remainder = env_name.removeprefix(ENV_PLUGIN_CONFIG_PREFIX)
        if "__" not in remainder:
            continue
        plugin_name, config_key = remainder.split("__", 1)
        if not plugin_name or not config_key:
            continue
        normalized_plugin = plugin_name.lower().replace("_", "-")
        values.setdefault(normalized_plugin, {})[config_key.lower()] = (
            _parse_environment_json_value(env_value)
        )
    return {key: dict(value) for key, value in values.items()}


def _parse_environment_json_value(value: str) -> JSONValue:
    """Parse primitive JSON-like plugin values from environment strings."""
    normalized = value.strip()
    lowered = normalized.lower()
    if lowered in _TRUE_VALUES:
        return True
    if lowered in _FALSE_VALUES:
        return False
    if lowered == "none" or lowered == "null":
        return None
    try:
        return int(normalized)
    except ValueError:
        pass
    try:
        return float(normalized)
    except ValueError:
        return value


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
