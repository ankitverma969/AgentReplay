"""Profile command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import ProfilerError
from agentreplay.profiler import ProfilerEngine
from agentreplay.profiler.models import ProfilingReport
from agentreplay.profiler.renderers import (
    render_console,
    render_csv,
    render_html,
    render_json,
    render_markdown,
    render_summary,
    render_timeline,
)
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``profile`` command."""
    parser = subparsers.add_parser("profile", help="Profile a recorded execution.")
    parser.add_argument("run_id", help="Run identifier or 'latest'.")
    parser.add_argument("--summary", action="store_true", help="Emit summary only.")
    parser.add_argument("--timeline", action="store_true", help="Emit timeline data.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--html", action="store_true", help="Emit HTML report.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown report.")
    parser.add_argument("--csv", action="store_true", help="Emit CSV report.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``profile`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    engine = ProfilerEngine(storage=storage)
    try:
        report = engine.profile(args.run_id)
        write_line(_render_result(args, report))
    except (ProfilerError, ValueError) as exc:
        write_line(f"agentreplay profile: {exc}")
        return 1
    finally:
        engine.close()
    return 0


def _render_result(args: argparse.Namespace, report: ProfilingReport) -> str:
    """Render the profile report using CLI-selected output format."""
    selected = sum(
        bool(value)
        for value in (
            args.summary,
            args.timeline,
            args.json,
            args.html,
            args.markdown,
            args.csv,
        )
    )
    if selected > 1:
        msg = "Choose only one profile output format."
        raise ValueError(msg)
    if args.summary:
        return render_summary(report)
    if args.timeline:
        return render_timeline(report)
    if args.json:
        return render_json(report)
    if args.html:
        return render_html(report)
    if args.markdown:
        return render_markdown(report)
    if args.csv:
        return render_csv(report)
    return render_console(report)


__all__ = ["handle", "register"]
