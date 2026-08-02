"""Placeholder ``list`` command for the AgentReplay CLI."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import (
    add_storage_argument,
    phase_message,
    write_line,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``list`` command."""
    parser = subparsers.add_parser("list", help="List recorded executions.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Handle the Phase 1 ``list`` command."""
    write_line(phase_message("list", "Phase 2"))
    return 0


__all__ = ["handle", "register"]
