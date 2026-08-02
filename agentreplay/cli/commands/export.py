"""Export command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentreplay.adapters.langgraph import export_trace
from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.config import get_settings
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import AdapterError, StorageError
from agentreplay.security import SecurityEngine
from agentreplay.security.config import security_config_from_settings
from agentreplay.storage import Pagination, SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``export`` command."""
    parser = subparsers.add_parser("export", help="Export a recorded execution.")
    parser.add_argument("run_id", help="Run identifier or 'latest'.")
    parser.add_argument("--output", "-o", help="Output file path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown output.")
    parser.add_argument("--html", action="store_true", help="Emit HTML output.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``export`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        run_id = _resolve_run_id(storage, args.run_id)
        run = storage.load_run(run_id)
        if run is None:
            write_line(f"agentreplay export: unknown run {run_id}")
            return 1
        trace = TraceSnapshot(run=run, events=storage.load_events(run_id))
        security = SecurityEngine(security_config_from_settings(get_settings()))
        output = _render(security.sanitize_trace(trace), args)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            write_line(output)
    except (AdapterError, StorageError, ValueError) as exc:
        write_line(f"agentreplay export: {exc}")
        return 1
    finally:
        storage.close()
    return 0


def _render(trace: TraceSnapshot, args: argparse.Namespace) -> str:
    """Render a trace in the requested format."""
    requested = sum(bool(value) for value in (args.json, args.markdown, args.html))
    if requested > 1:
        msg = "Choose only one export format."
        raise ValueError(msg)
    if args.markdown:
        return export_trace(trace, export_format="markdown")
    if args.html:
        return export_trace(trace, export_format="html")
    return json.dumps(trace.to_dict(), sort_keys=True)


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
