"""Replay command for the AgentReplay CLI."""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.exceptions import ReplayError
from agentreplay.replay import ALLOWED_PLAYBACK_SPEEDS, ReplayEngine
from agentreplay.replay.playback import TimelineEntry
from agentreplay.storage import SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``replay`` command."""
    parser = subparsers.add_parser("replay", help="Replay a recorded execution.")
    parser.add_argument("run_id", nargs="?", help="Run identifier to replay.")
    parser.add_argument("--file", help="Path to an exported AgentReplay JSON file.")
    parser.add_argument(
        "--speed",
        type=float,
        choices=ALLOWED_PLAYBACK_SPEEDS,
        default=1.0,
        help="Playback speed.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON."
    )
    parser.add_argument(
        "--timeline",
        action="store_true",
        help="Render the recorded execution timeline.",
    )
    parser.add_argument("--step", action="store_true", help="Replay one event.")
    parser.add_argument("--from", dest="from_event", help="Start at an event id.")
    parser.add_argument("--to", dest="to_event", help="End at an event id.")
    parser.add_argument(
        "--from-timestamp",
        help="Start at the first event at or after an ISO timestamp.",
    )
    add_storage_argument(parser)
    parser.set_defaults(handler=handle)


def handle(args: argparse.Namespace) -> int:
    """Handle the ``replay`` command."""
    try:
        engine = _load_engine(args)
        if args.from_event:
            engine.seek(args.from_event)
        if args.from_timestamp:
            engine.jump_to_timestamp(datetime.fromisoformat(args.from_timestamp))
        if args.step:
            entry = engine.step_forward()
            output: object = None if entry is None else entry.to_dict()
            _write_output(output, json_output=args.json)
            return 0

        timeline = engine.timeline()
        if args.from_event or args.to_event:
            timeline = timeline.slice_by_event_ids(args.from_event, args.to_event)

        if args.json:
            _write_output(timeline.to_dict(), json_output=True)
        else:
            rendered = timeline.render(include_details=False)
            write_line(rendered)
    except (ReplayError, ValueError) as exc:
        write_line(f"agentreplay replay: {exc}")
        return 1
    return 0


def _load_engine(args: argparse.Namespace) -> ReplayEngine:
    """Load a replay engine from a file or SQLite storage."""
    if args.file:
        engine = ReplayEngine(speed=args.speed)
        engine.load_file(args.file)
        return engine
    if not args.run_id:
        msg = "RUN_ID is required unless --file is provided."
        raise ReplayError(msg)
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    engine = ReplayEngine(storage=storage, speed=args.speed)
    engine.load(args.run_id)
    return engine


def _write_output(output: object, *, json_output: bool) -> None:
    """Write replay output in the selected format."""
    if json_output:
        write_line(json.dumps(output, sort_keys=True))
    elif output is None:
        write_line("No event")
    elif isinstance(output, TimelineEntry):
        write_line(output.label)
    else:
        write_line(str(output))


__all__ = ["handle", "register"]
