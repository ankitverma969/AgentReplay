"""Plugin management commands for the AgentReplay CLI."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from agentreplay.cli.commands._shared import write_line
from agentreplay.plugins import PluginManager

_DISABLED_PLUGINS_PATH = Path(".agentreplay") / "disabled_plugins.txt"


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``plugins`` command group."""
    parser = subparsers.add_parser("plugins", help="Manage AgentReplay plugins.")
    plugin_subparsers = parser.add_subparsers(dest="plugin_command")

    list_parser = plugin_subparsers.add_parser("list", help="List plugins.")
    list_parser.set_defaults(handler=handle_list)

    info_parser = plugin_subparsers.add_parser("info", help="Show plugin details.")
    info_parser.add_argument("name", help="Plugin name.")
    info_parser.set_defaults(handler=handle_info)

    install_parser = plugin_subparsers.add_parser("install", help="Install a plugin.")
    install_parser.add_argument(
        "package",
        help="Package spec, such as agentreplay-crewai.",
    )
    install_parser.set_defaults(handler=handle_install)

    disable_parser = plugin_subparsers.add_parser("disable", help="Disable a plugin.")
    disable_parser.add_argument("name", help="Plugin name.")
    disable_parser.set_defaults(handler=handle_disable)

    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Handle ``agentreplay plugins`` as a list command."""
    return handle_list(_args)


def handle_list(_args: argparse.Namespace) -> int:
    """List discovered plugins."""
    manager = PluginManager(disabled_plugins=_read_disabled_plugins())
    records = manager.load_plugins()
    if not records:
        write_line("No AgentReplay plugins discovered.")
        return 0
    for record in records:
        write_line(
            f"{record.metadata.name} {record.metadata.version} "
            f"{record.metadata.plugin_type} {record.status}"
        )
    return 0


def handle_info(args: argparse.Namespace) -> int:
    """Show details for one plugin."""
    manager = PluginManager(disabled_plugins=_read_disabled_plugins())
    records = manager.load_plugins()
    record = next((item for item in records if item.metadata.name == args.name), None)
    if record is None:
        write_line(f"agentreplay plugins info: unknown plugin {args.name}")
        return 1
    metadata = record.metadata
    write_line(f"Name: {metadata.name}")
    write_line(f"Version: {metadata.version}")
    write_line(f"Type: {metadata.plugin_type}")
    write_line(f"Status: {record.status}")
    write_line(f"Source: {record.source}")
    if metadata.summary:
        write_line(f"Summary: {metadata.summary}")
    if metadata.dependencies:
        dependencies = ", ".join(
            dependency.name for dependency in metadata.dependencies
        )
        write_line(f"Dependencies: {dependencies}")
    if record.error:
        write_line(f"Error: {record.error}")
    return 0


def handle_install(args: argparse.Namespace) -> int:
    """Install a plugin package through pip."""
    command = [sys.executable, "-m", "pip", "install", args.package]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        write_line(f"agentreplay plugins install: pip failed for {args.package}")
        return int(result.returncode)
    write_line(f"Installed AgentReplay plugin package: {args.package}")
    return 0


def handle_disable(args: argparse.Namespace) -> int:
    """Persistently disable a plugin for local CLI discovery."""
    disabled = set(_read_disabled_plugins())
    disabled.add(args.name)
    _DISABLED_PLUGINS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _DISABLED_PLUGINS_PATH.write_text(
        "\n".join(sorted(disabled)) + "\n",
        encoding="utf-8",
    )
    write_line(f"Disabled AgentReplay plugin: {args.name}")
    return 0


def _read_disabled_plugins() -> tuple[str, ...]:
    """Read locally disabled plugin names."""
    if not _DISABLED_PLUGINS_PATH.is_file():
        return ()
    return tuple(
        line.strip()
        for line in _DISABLED_PLUGINS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


__all__ = [
    "handle",
    "handle_disable",
    "handle_info",
    "handle_install",
    "handle_list",
    "register",
]
