"""Inspect command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse
import json

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import StorageError
from agentreplay.storage import Pagination, SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``inspect`` command."""
    parser = subparsers.add_parser("inspect", help="Inspect a recorded execution.")
    parser.add_argument("run_id", help="Run identifier or 'latest'.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``inspect`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        run_id = _resolve_run_id(storage, args.run_id)
        run = storage.load_run(run_id)
        if run is None:
            write_line(f"agentreplay inspect: unknown run {run_id}")
            return 1
        events = storage.load_events(run_id)
        payload = {
            "run": run.to_dict(),
            "event_count": len(events),
            "first_event": events[0].to_dict() if events else None,
            "last_event": events[-1].to_dict() if events else None,
        }
        if args.json:
            write_line(json.dumps(payload, sort_keys=True))
        else:
            write_line(f"Run {run.run_id}")
            write_line(f"Status: {run.status}")
            write_line(f"Name: {run.name or ''}".rstrip())
            write_line(f"Started: {run.started_at.isoformat()}")
            write_line(f"Duration ms: {run.duration_ms}")
            write_line(f"Events: {len(events)}")
    except StorageError as exc:
        write_line(f"agentreplay inspect: {exc}")
        return 1
    finally:
        storage.close()
    return 0


def _resolve_run_id(storage: SQLiteStorage, run_id: str) -> str:
    """Resolve the special ``latest`` run id."""
    if run_id != "latest":
        return run_id
    runs = storage.list_runs(pagination=Pagination(limit=1))
    if not runs:
        msg = "No recorded runs found."
        raise StorageError(msg)
    return runs[0].run_id


__all__ = ["handle", "register"]
