"""HTML trace report command for AgentReplay."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import ReportingError
from agentreplay.reporting import ReportingEngine, ReportOptions
from agentreplay.reporting.renderers import render_html
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``report`` command."""
    parser = subparsers.add_parser("report", help="Generate an HTML trace report.")
    parser.add_argument("run_id", help="Run identifier or 'latest'.")
    parser.add_argument("--html", action="store_true", help="Emit HTML output.")
    parser.add_argument("--dark", action="store_true", help="Use the dark theme.")
    parser.add_argument("--light", action="store_true", help="Use the light theme.")
    parser.add_argument("--output", "-o", help="Output HTML file path.")
    parser.add_argument("--compress", action="store_true", help="Compress HTML assets.")
    parser.add_argument(
        "--compare", metavar="RUN2", help="Compare against another run."
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``report`` command."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    engine = ReportingEngine(storage=storage)
    try:
        if args.dark and args.light:
            msg = "Choose only one report theme."
            raise ValueError(msg)
        theme: Literal["dark", "light", "print"] = "light" if args.light else "dark"
        bundle = engine.generate(
            args.run_id,
            options=ReportOptions(
                theme=theme,
                compress=args.compress,
                compare_run_id=args.compare,
            ),
        )
        output = render_html(bundle, compress=args.compress)
        if args.output:
            Path(args.output).expanduser().write_text(output, encoding="utf-8")
        else:
            write_line(output)
    except (ReportingError, ValueError) as exc:
        write_line(f"agentreplay report: {exc}")
        return 1
    finally:
        engine.close()
    return 0


__all__ = ["handle", "register"]
