"""Regression analysis command for AgentReplay recorded runs."""

from __future__ import annotations

import argparse

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import RegressionError
from agentreplay.regression import RegressionEngine
from agentreplay.regression.models import RegressionReport
from agentreplay.regression.renderers import (
    render_console,
    render_csv,
    render_graph,
    render_html,
    render_json,
    render_markdown,
    render_summary,
)
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``regression`` command."""
    parser = subparsers.add_parser(
        "regression",
        help="Detect regressions and root causes between recorded executions.",
    )
    parser.add_argument("baseline_run", help="Baseline run id or alias.")
    parser.add_argument("target_run", help="Target run id or alias.")
    parser.add_argument("--summary", action="store_true", help="Emit summary only.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    parser.add_argument("--html", action="store_true", help="Emit HTML output.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown output.")
    parser.add_argument("--csv", action="store_true", help="Emit CSV output.")
    parser.add_argument("--graph", action="store_true", help="Emit graph JSON output.")
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``regression`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    engine = RegressionEngine(storage=storage)
    try:
        report = engine.compare(args.baseline_run, args.target_run)
        write_line(_render_result(args, report))
    except (RegressionError, ValueError) as exc:
        write_line(f"agentreplay regression: {exc}")
        return 1
    finally:
        engine.close()
    return 0


def _render_result(args: argparse.Namespace, report: RegressionReport) -> str:
    """Render a regression report in the requested CLI format."""
    selected = sum(
        bool(value)
        for value in (
            args.summary,
            args.json,
            args.html,
            args.markdown,
            args.csv,
            args.graph,
        )
    )
    if selected > 1:
        msg = "Choose only one regression output format."
        raise ValueError(msg)
    if args.summary:
        return render_summary(report)
    if args.json:
        return render_json(report)
    if args.html:
        return render_html(report)
    if args.markdown:
        return render_markdown(report)
    if args.csv:
        return render_csv(report)
    if args.graph:
        return render_graph(report)
    return render_console(report)


__all__ = ["handle", "register"]
