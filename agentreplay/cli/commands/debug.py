"""Interactive debugger command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.debugger import DebuggerEngine
from agentreplay.exceptions import DebuggerError
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``debug`` command."""
    parser = subparsers.add_parser("debug", help="Open the time travel debugger.")
    parser.add_argument("run_id", nargs="?", help="Run identifier or 'latest'.")
    parser.add_argument("--file", help="Path to an exported AgentReplay JSON file.")
    parser.add_argument(
        "--theme",
        choices=("dark", "light"),
        default="dark",
        help="Debugger color theme.",
    )
    parser.add_argument(
        "--diff-run",
        help="Run id to compare against when using current-event diff.",
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``debug`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    engine = DebuggerEngine(storage=storage)
    try:
        if args.file:
            session = engine.load_file(args.file)
        else:
            if not args.run_id:
                msg = "RUN_ID is required unless --file is provided."
                raise DebuggerError(msg)
            session = engine.load(args.run_id)
        engine.run(
            session,
            theme=args.theme,
            diff_run_id=args.diff_run,
        )
    except DebuggerError as exc:
        write_line(f"agentreplay debug: {exc}")
        return 1
    finally:
        engine.close()
    return 0


__all__ = ["handle", "register"]
