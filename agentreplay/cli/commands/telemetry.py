"""Telemetry commands for AgentReplay observability."""

from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime

from agentreplay.cli.commands._shared import add_storage_argument, write_line
from agentreplay.config import get_settings
from agentreplay.core.events import LLM_RESPONSE, RUN_STARTED, EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import AgentReplayError, StorageError
from agentreplay.observability import (
    CorrelationContext,
    ObservabilityEngine,
    opentelemetry_available,
)
from agentreplay.observability.config import observability_config_from_settings
from agentreplay.storage import Pagination, SQLiteStorage


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the ``telemetry`` command group."""
    parser = subparsers.add_parser(
        "telemetry",
        help="Inspect and export AgentReplay telemetry.",
    )
    telemetry_subparsers = parser.add_subparsers(dest="telemetry_command")

    status = telemetry_subparsers.add_parser("status", help="Show telemetry status.")
    status.set_defaults(handler=handle_status)

    test = telemetry_subparsers.add_parser("test", help="Test telemetry export.")
    test.add_argument("--json", action="store_true", help="Emit JSON output.")
    test.set_defaults(handler=handle_test)

    export = telemetry_subparsers.add_parser(
        "export",
        help="Export a recorded run as telemetry.",
    )
    export.add_argument("run_id", help="Run identifier or 'latest'.")
    export.add_argument("--request-id", help="Correlation request id.")
    export.add_argument("--session-id", help="Correlation session id.")
    export.add_argument("--user-id", help="Optional end-user correlation id.")
    export.add_argument("--json", action="store_true", help="Emit JSON result.")
    add_storage_argument(export)
    export.set_defaults(handler=handle_export)

    config = telemetry_subparsers.add_parser(
        "config",
        help="Print resolved telemetry configuration.",
    )
    config.add_argument("--json", action="store_true", help="Emit JSON output.")
    config.set_defaults(handler=handle_config)
    parser.set_defaults(handler=handle_group)


def handle_group(_args: argparse.Namespace) -> int:
    """Handle telemetry without a subcommand."""
    write_line("agentreplay telemetry: choose status, test, export, or config.")
    return 1


def handle_status(_args: argparse.Namespace) -> int:
    """Print telemetry status."""
    config = observability_config_from_settings(get_settings())
    lines = [
        "AgentReplay Telemetry",
        f"Enabled: {config.enabled}",
        f"Exporter: {config.exporter}",
        f"Endpoint: {config.endpoint or '<none>'}",
        f"Sampling: {config.sampling}",
        f"OpenTelemetry available: {opentelemetry_available()}",
    ]
    write_line("\n".join(lines))
    return 0


def handle_config(args: argparse.Namespace) -> int:
    """Print resolved telemetry configuration."""
    config = observability_config_from_settings(get_settings())
    payload = {
        "enabled": config.enabled,
        "exporter": config.exporter,
        "endpoint": config.endpoint,
        "service_name": config.service_name,
        "service_namespace": config.service_namespace,
        "environment": config.deployment_environment,
        "sampling": config.sampling,
        "sampling_ratio": config.sampling_ratio,
        "timeout_ms": config.timeout_ms,
        "tls_enabled": config.tls_enabled,
        "compression": config.compression,
        "file_path": config.file_path,
        "batch_size": config.batch_size,
        "queue_size": config.queue_size,
        "graceful_shutdown_ms": config.graceful_shutdown_ms,
        "headers": dict(config.headers),
        "auth_token": "<configured>" if config.auth_token else None,
    }
    if args.json:
        write_line(json.dumps(payload, sort_keys=True))
    else:
        write_line("\n".join(f"{key}: {value}" for key, value in payload.items()))
    return 0


def handle_test(args: argparse.Namespace) -> int:
    """Export a synthetic trace to validate telemetry wiring."""
    config = replace(observability_config_from_settings(get_settings()), enabled=True)
    engine = ObservabilityEngine(config)
    try:
        result = engine.export_trace(_synthetic_trace())
    except AgentReplayError as exc:
        write_line(f"agentreplay telemetry test: {exc}")
        return 1
    finally:
        engine.shutdown()
    if args.json:
        write_line(json.dumps(result.to_dict(), sort_keys=True))
    else:
        write_line(result.output or result.message)
    return 0 if result.succeeded else 1


def handle_export(args: argparse.Namespace) -> int:
    """Export a stored run as telemetry."""
    storage = SQLiteStorage(args.db_path) if args.db_path else SQLiteStorage()
    try:
        trace = _load_trace(storage, args.run_id)
        correlation = CorrelationContext(
            run_id=trace.run.run_id,
            request_id=args.request_id,
            session_id=args.session_id,
            user_id=args.user_id,
        )
        engine = ObservabilityEngine(observability_config_from_settings(get_settings()))
        try:
            result = engine.export_trace(trace, correlation=correlation)
        finally:
            engine.shutdown()
        if args.json:
            write_line(json.dumps(result.to_dict(), sort_keys=True))
        else:
            write_line(result.output or result.message)
    except (AgentReplayError, StorageError) as exc:
        write_line(f"agentreplay telemetry export: {exc}")
        return 1
    finally:
        storage.close()
    return 0


def _load_trace(storage: SQLiteStorage, run_id: str) -> TraceSnapshot:
    resolved = _resolve_run_id(storage, run_id)
    run = storage.load_run(resolved)
    if run is None:
        msg = f"Unknown AgentReplay run: {resolved}"
        raise StorageError(msg)
    return TraceSnapshot(run=run, events=storage.load_events(resolved))


def _resolve_run_id(storage: SQLiteStorage, run_id: str) -> str:
    if run_id != "latest":
        return run_id
    runs = storage.list_runs(pagination=Pagination(limit=1))
    if not runs:
        msg = "No recorded runs found."
        raise StorageError(msg)
    return runs[0].run_id


def _synthetic_trace() -> TraceSnapshot:
    now = datetime.now(UTC)
    run = RunRecord(
        run_id="telemetry-test-run",
        name="telemetry-test",
        status="completed",
        started_at=now,
        ended_at=now,
        duration_ms=1.0,
        metadata={"framework": "agentreplay"},
    )
    events = (
        EventRecord(
            event_id="telemetry-test-start",
            run_id=run.run_id,
            parent_event_id=None,
            sequence=1,
            event_type=RUN_STARTED,
            timestamp=now,
            duration_ms=0.1,
            metadata={},
            payload={"name": run.name},
        ),
        EventRecord(
            event_id="telemetry-test-llm",
            run_id=run.run_id,
            parent_event_id="telemetry-test-start",
            sequence=2,
            event_type=LLM_RESPONSE,
            timestamp=now,
            duration_ms=0.9,
            metadata={},
            payload={
                "provider_name": "agentreplay",
                "model_name": "telemetry-test",
                "token_usage": {"total_tokens": 1},
            },
        ),
    )
    return TraceSnapshot(run=run, events=events)


__all__ = [
    "handle_config",
    "handle_export",
    "handle_group",
    "handle_status",
    "handle_test",
    "register",
]
