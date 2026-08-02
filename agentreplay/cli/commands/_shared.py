"""Shared helpers for placeholder Phase 1 CLI commands."""

from __future__ import annotations

import argparse
import sys


def phase_message(command: str, phase: str) -> str:
    """Return the standard message for a command reserved for a later phase."""
    return (
        f"agentreplay {command}: command scaffold ready; behavior arrives in {phase}."
    )


def write_line(message: str) -> None:
    """Write one CLI output line to standard output."""
    sys.stdout.write(f"{message}\n")


def add_storage_argument(parser: argparse.ArgumentParser) -> None:
    """Add the standard storage path option used by future commands."""
    parser.add_argument(
        "--db-path",
        help="Path to the AgentReplay SQLite database.",
    )


__all__ = ["add_storage_argument", "phase_message", "write_line"]
