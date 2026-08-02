"""CLI integration helpers for public SDK command extensions."""

from __future__ import annotations

import argparse
import logging

from agentreplay.plugins import PluginManager


def register_sdk_cli_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    manager: PluginManager | None = None,
    logger: logging.Logger | None = None,
) -> int:
    """Register CLI commands contributed by loaded plugins.

    Plugin failures are isolated by ``PluginManager``. Individual command
    registration failures are logged and skipped so built-in commands remain
    available.
    """
    resolved_manager = PluginManager() if manager is None else manager
    resolved_logger = (
        logging.getLogger("agentreplay.sdk.cli") if logger is None else logger
    )
    count = 0
    records = resolved_manager.load_plugins()
    for registration in resolved_manager.app.registrations(kind="cli_command"):
        registrar = registration.value
        try:
            if callable(registrar):
                registrar(subparsers)
            elif hasattr(registrar, "register"):
                registrar.register(subparsers)
            else:
                continue
        except Exception as exc:
            resolved_logger.warning(
                "AgentReplay SDK CLI extension failed: %s.%s: %s",
                registration.plugin_name,
                registration.name,
                exc,
            )
            continue
        count += 1
    return count if records or count else 0


__all__ = ["register_sdk_cli_commands"]
