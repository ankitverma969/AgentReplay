"""Logging setup helpers for AgentReplay."""

from __future__ import annotations

import logging as stdlib_logging
from logging import Logger

from agentreplay.config import Settings, get_settings
from agentreplay.constants import LOGGER_NAME
from agentreplay.exceptions import ConfigurationError


def setup_logging(
    settings: Settings | None = None, *, level: str | None = None
) -> Logger:
    """Configure and return the AgentReplay package logger.

    Args:
        settings: Optional resolved settings object.
        level: Optional log level override.

    Returns:
        The package-level logger.

    Raises:
        ConfigurationError: If the requested level is not recognized.
    """
    resolved_settings = get_settings() if settings is None else settings
    selected_level = resolved_settings.log_level if level is None else level
    numeric_level = stdlib_logging.getLevelName(selected_level.upper())
    if not isinstance(numeric_level, int):
        msg = f"Unknown AgentReplay log level: {selected_level}"
        raise ConfigurationError(msg)

    logger = stdlib_logging.getLogger(LOGGER_NAME)
    logger.setLevel(numeric_level)
    if not logger.handlers:
        logger.addHandler(stdlib_logging.NullHandler())
    return logger


__all__ = ["setup_logging"]
