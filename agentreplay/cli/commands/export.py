"""Placeholder ``export`` command for the AgentReplay CLI."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import (
    add_storage_argument,
    phase_message,
    write_line,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``export`` command."""
    parser = subparsers.add_parser("export", help="Export a recorded execution.")
    parser.add_argument("run_id", nargs="?", help="Run identifier to export.")
    parser.add_argument("--output", "-o", help="Output file path.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Handle the Phase 1 ``export`` command."""
    write_line(phase_message("export", "Phase 2"))
    return 0


__all__ = ["handle", "register"]
