from __future__ import annotations

from pathlib import Path

import pytest
from agentreplay.config import Settings, configure, load_settings, reset_settings
from agentreplay.exceptions import ConfigurationError


def test_default_settings_are_local_and_conservative() -> None:
    settings = load_settings(environ={})

    assert settings == Settings()
    assert settings.enabled is False
    assert settings.redaction_enabled is True


def test_environment_overrides_defaults() -> None:
    settings = load_settings(
        environ={
            "AGENTREPLAY_ENABLED": "true",
            "AGENTREPLAY_DB_PATH": "custom.sqlite",
            "AGENTREPLAY_REDACTION": "false",
            "AGENTREPLAY_LOG_LEVEL": "debug",
            "AGENTREPLAY_STORAGE_BACKEND": "sqlite",
            "AGENTREPLAY_FAIL_MODE": "fail_closed",
        },
    )

    assert settings.enabled is True
    assert settings.db_path == Path("custom.sqlite")
    assert settings.redaction_enabled is False
    assert settings.log_level == "DEBUG"
    assert settings.storage_backend == "sqlite"
    assert settings.fail_mode == "fail_closed"


def test_config_file_is_loaded(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text(
        "\n".join(
            [
                "enabled = true",
                'db_path = "from-file.sqlite"',
                "redaction_enabled = false",
                'log_level = "INFO"',
            ],
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_file, environ={})

    assert settings.enabled is True
    assert settings.db_path == Path("from-file.sqlite")
    assert settings.redaction_enabled is False
    assert settings.log_level == "INFO"
    assert settings.config_file == config_file


def test_invalid_environment_value_raises_configuration_error() -> None:
    with pytest.raises(ConfigurationError):
        load_settings(environ={"AGENTREPLAY_ENABLED": "maybe"})


def test_configure_stores_settings() -> None:
    reset_settings()

    settings = configure(enabled=True)

    assert settings.enabled is True
    reset_settings()
