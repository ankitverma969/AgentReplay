"""Version command for the AgentReplay CLI."""

from __future__ import annotations

import argparse
import sys

from agentreplay.version import __version__


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``version`` command."""
    parser = subparsers.add_parser("version", help="Print the AgentReplay version.")
    parser.set_defaults(handler=handle)


def handle(_args: argparse.Namespace) -> int:
    """Print the AgentReplay package version."""
    sys.stdout.write(f"agentreplay {__version__}\n")
    return 0


__all__ = ["handle", "register"]
