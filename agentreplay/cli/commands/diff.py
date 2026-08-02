"""Diff command for the AgentReplay CLI."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.diff import DiffEngine
from agentreplay.diff.models import DiffResult
from agentreplay.diff.renderers import (
    render_console,
    render_html,
    render_json,
    render_markdown,
    render_summary,
)
from agentreplay.exceptions import DiffError
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``diff`` command."""
    parser = subparsers.add_parser("diff", help="Compare two recorded executions.")
    parser.add_argument("left_run_id", help="Baseline run identifier.")
    parser.add_argument("right_run_id", help="Candidate run identifier.")
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    parser.add_argument("--html", action="store_true", help="Emit an HTML report.")
    parser.add_argument(
        "--markdown", action="store_true", help="Emit a Markdown report."
    )
    parser.add_argument("--summary", action="store_true", help="Emit summary only.")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include old and new values in human-readable reports.",
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``diff`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        result = DiffEngine(storage=storage).compare(
            args.left_run_id,
            args.right_run_id,
        )
        write_line(_render_result(args, result))
    except (DiffError, ValueError) as exc:
        write_line(f"agentreplay diff: {exc}")
        return 1
    finally:
        storage.close()
    return 0


def _render_result(args: argparse.Namespace, result: DiffResult) -> str:
    """Render a diff result using the selected CLI output format."""
    if args.json:
        return render_json(result)
    if args.html:
        return render_html(result, verbose=args.verbose)
    if args.markdown:
        return render_markdown(result, verbose=args.verbose)
    if args.summary:
        return render_summary(result)
    return render_console(result, verbose=args.verbose)


__all__ = ["handle", "register"]
