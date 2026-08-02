"""List command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse
import json

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.storage import Pagination, SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``list`` command."""
    parser = subparsers.add_parser("list", help="List recorded executions.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum runs to list.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``list`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        runs = storage.list_runs(pagination=Pagination(limit=args.limit))
        if args.json:
            write_line(json.dumps([run.to_dict() for run in runs], sort_keys=True))
        elif not runs:
            write_line("No recorded runs found.")
        else:
            for run in runs:
                write_line(
                    f"{run.run_id} {run.status} "
                    f"{run.started_at.isoformat()} {run.name or ''}".rstrip(),
                )
    finally:
        storage.close()
    return 0


__all__ = ["handle", "register"]
