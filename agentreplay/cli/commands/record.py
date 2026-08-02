"""Placeholder ``record`` command for the AgentReplay CLI."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import (
    add_storage_argument,
    phase_message,
    write_line,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``record`` command."""
    parser = subparsers.add_parser("record", help="Record an execution.")
    parser.add_argument("name", nargs="?", help="Optional run name.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Handle the Phase 1 ``record`` command."""
    write_line(phase_message("record", "Phase 2"))
    return 0


__all__ = ["handle", "register"]
