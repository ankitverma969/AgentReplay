"""Security scanning commands for AgentReplay traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.config import get_settings
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import StorageError
from agentreplay.security.config import security_config_from_settings
from agentreplay.security.engine import SecurityEngine
from agentreplay.security.models import SecurityReport
from agentreplay.security.reports import (
    render_console,
    render_html,
    render_json,
    render_markdown,
)
from agentreplay.storage import Pagination, SQLiteStorage
from agentreplay.types import JSONValue


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``security`` command group."""
    parser = subparsers.add_parser(
        "security",
        help="Scan and verify traces for secrets and PII.",
    )
    security_subparsers = parser.add_subparsers(dest="security_command")

    scan = security_subparsers.add_parser("scan", help="Scan a trace.")
    scan.add_argument("trace", help="Trace file path, run id, or 'latest'.")
    scan.add_argument("--json", action="store_true", help="Emit JSON output.")
    scan.add_argument("--markdown", action="store_true", help="Emit Markdown output.")
    scan.add_argument("--html", action="store_true", help="Emit HTML output.")
    scan.add_argument("--verbose", action="store_true", help="Show finding details.")
    add_storage_argument(scan)
    scan.set_defaults(handler=handle_scan)

    verify = security_subparsers.add_parser(
        "verify",
        help="Return success only when a trace has no findings.",
    )
    verify.add_argument("trace", help="Trace file path, run id, or 'latest'.")
    add_storage_argument(verify)
    verify.set_defaults(handler=handle_verify)

    report = security_subparsers.add_parser(
        "report",
        help="Render a detailed security report.",
    )
    report.add_argument("trace", help="Trace file path, run id, or 'latest'.")
    report.add_argument("--json", action="store_true", help="Emit JSON output.")
    report.add_argument("--markdown", action="store_true", help="Emit Markdown output.")
    report.add_argument("--html", action="store_true", help="Emit HTML output.")
    report.add_argument("--verbose", action="store_true", help="Show finding details.")
    add_storage_argument(report)
    report.set_defaults(handler=handle_scan)

    rules = security_subparsers.add_parser("rules", help="List active security rules.")
    rules.add_argument("--json", action="store_true", help="Emit JSON output.")
    rules.set_defaults(handler=handle_rules)
    parser.set_defaults(handler=handle_group)


def handle_group(_args: argparse.Namespace) -> int:
    """Handle the security command without a subcommand."""
    write_line("agentreplay security: choose scan, verify, report, or rules.")
    return 1


def handle_scan(args: argparse.Namespace) -> int:
    """Scan a trace and render a report."""
    try:
        source, payload = _load_trace_payload(args.trace, args.db_path)
        engine = _engine()
        report = engine.scan(payload, source=source, include_preview=True)
        write_line(_render_report(report, args))
    except (OSError, StorageError, ValueError) as exc:
        write_line(f"agentreplay security scan: {exc}")
        return 1
    return 0


def handle_verify(args: argparse.Namespace) -> int:
    """Verify that a trace contains no detected sensitive data."""
    try:
        source, payload = _load_trace_payload(args.trace, args.db_path)
        report = _engine().verify(payload, source=source)
    except (OSError, StorageError, ValueError) as exc:
        write_line(f"agentreplay security verify: {exc}")
        return 1
    if report.verify():
        write_line(f"AgentReplay security verify passed: {source}")
        return 0
    write_line(f"AgentReplay security verify failed: {report.summary()}")
    return 2


def handle_rules(args: argparse.Namespace) -> int:
    """Print active security detection rules."""
    engine = _engine()
    rules = [
        {
            "name": rule.name,
            "category": rule.category,
            "kind": rule.kind,
            "risk_level": rule.risk_level,
            "enabled": rule.enabled,
        }
        for rule in engine.rules()
    ]
    if args.json:
        write_line(json.dumps({"rules": rules}, sort_keys=True))
    else:
        if not rules:
            write_line("No active security rules.")
        for rule in rules:
            write_line(
                f"{rule['name']} ({rule['kind']}, "
                f"{rule['category']}, {rule['risk_level']})"
            )
    return 0


def _engine() -> SecurityEngine:
    """Return a security engine from active global settings."""
    return SecurityEngine(security_config_from_settings(get_settings()))


def _render_report(report: SecurityReport, args: argparse.Namespace) -> str:
    requested = sum(bool(value) for value in (args.json, args.markdown, args.html))
    if requested > 1:
        msg = "Choose only one security report format."
        raise ValueError(msg)
    if args.json:
        return render_json(report)
    if args.markdown:
        return render_markdown(report, verbose=args.verbose)
    if args.html:
        return render_html(report, verbose=args.verbose)
    return render_console(report, verbose=args.verbose)


def _load_trace_payload(
    trace: str,
    db_path: str | None,
) -> tuple[str, JSONValue]:
    path = Path(trace).expanduser()
    if path.is_file():
        content = path.read_text(encoding="utf-8")
        try:
            loaded = json.loads(content)
        except json.JSONDecodeError:
            return str(path), {"file_content": content}
        return str(path), _as_json_value(loaded)
    storage = SQLiteStorage(db_path) if db_path else SQLiteStorage()
    try:
        run_id = _resolve_run_id(storage, trace)
        run = storage.load_run(run_id)
        if run is None:
            msg = f"Unknown AgentReplay run: {run_id}"
            raise StorageError(msg)
        snapshot = TraceSnapshot(run=run, events=storage.load_events(run_id))
        return run_id, snapshot.to_dict()
    finally:
        storage.close()


def _resolve_run_id(storage: SQLiteStorage, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    runs = storage.list_runs(pagination=Pagination(limit=1))
    if not runs:
        msg = "No recorded runs found."
        raise StorageError(msg)
    return runs[0].run_id


def _as_json_value(value: Any) -> JSONValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_as_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_json_value(item) for key, item in value.items()}
    return str(value)


__all__ = [
    "handle_group",
    "handle_rules",
    "handle_scan",
    "handle_verify",
    "register",
]
