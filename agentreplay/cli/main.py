"""Command line entrypoint for AgentReplay."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from agentreplay.cli.commands import (
    debug,
    diff,
    export,
    inspect,
    plugins,
    profile,
    record,
    replay,
    runs,
    security,
    telemetry,
    version,
)
from agentreplay.logging import setup_logging


def build_parser() -> argparse.ArgumentParser:
    """Build the AgentReplay command line parser."""
    parser = argparse.ArgumentParser(
        prog="agentreplay",
        description="Inspect, replay, compare, and export AI agent executions.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print the AgentReplay version and exit.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose AgentReplay logging.",
    )

    subparsers = parser.add_subparsers(dest="command")
    version.register(subparsers)
    runs.register(subparsers)
    record.register(subparsers)
    replay.register(subparsers)
    debug.register(subparsers)
    diff.register(subparsers)
    inspect.register(subparsers)
    export.register(subparsers)
    plugins.register(subparsers)
    profile.register(subparsers)
    security.register(subparsers)
    telemetry.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AgentReplay CLI.

    Args:
        argv: Optional argument sequence excluding the executable name.

    Returns:
        A process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        setup_logging(level="DEBUG")

    if args.version:
        return version.handle(args)

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0
    return int(handler(args))


__all__ = ["build_parser", "main"]
