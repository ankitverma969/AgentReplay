"""Placeholder ``replay`` command for the AgentReplay CLI."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import (
    add_storage_argument,
    phase_message,
    write_line,
)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``replay`` command."""
    parser = subparsers.add_parser("replay", help="Replay a recorded execution.")
    parser.add_argument("run_id", nargs="?", help="Run identifier to replay.")
    parser.add_argument(
        "--policy",
        choices=("strict", "lenient", "inspect_only"),
        default="inspect_only",
        help="Replay policy.",
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Handle the Phase 1 ``replay`` command."""
    write_line(phase_message("replay", "Phase 4"))
    return 0


__all__ = ["handle", "register"]
