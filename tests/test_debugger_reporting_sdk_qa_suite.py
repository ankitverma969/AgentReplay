from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from agentreplay import (
    AgentReplaySDK,
    DebuggerEngine,
    ReportingEngine,
    SDKContext,
)
from agentreplay.cli.commands._shared import write_line
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    COST_RECORDED,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.debugger.app import DebuggerApp
from agentreplay.debugger.models import SearchQuery
from agentreplay.debugger.renderers import (
    render_event_export,
    render_metadata,
    render_stats,
    render_timeline_tree,
)
from agentreplay.debugger.session import DebuggerSession
from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginManager
from agentreplay.reporting import ReportOptions
from agentreplay.reporting.renderers import (
    render_html,
    render_json_bundle,
    render_markdown_summary,
)
from agentreplay.sdk import (
    AnalyzerResult,
    BaseAnalyzer,
    BaseCLICommand,
    BaseExporter,
    ExportResult,
    SDKEvent,
    SDKExtensionMetadata,
    SDKHookContext,
    analyzer_metadata,
    exporter_metadata,
)
from agentreplay.types import JSONValue


@pytest.fixture
def trace() -> TraceSnapshot:
    """Return a representative trace for debugger, reporting, and SDK tests."""
    return _trace("qa-run")


@pytest.fixture
def session(trace: TraceSnapshot) -> DebuggerSession:
    """Return a debugger session loaded from the representative trace."""
    return DebuggerEngine().load_trace(trace)


def test_01_launch_debugger(session: DebuggerSession) -> None:
    async def run_app() -> None:
        app = DebuggerApp(session=session)
        async with app.run_test():
            assert app.session.run_id == "qa-run"
            assert any("Debugger loaded run qa-run" in log for log in app.session.logs)

    asyncio.run(run_app())


def test_02_keyboard_shortcuts(session: DebuggerSession) -> None:
    async def run_app() -> None:
        app = DebuggerApp(session=session)
        async with app.run_test() as pilot:
            await pilot.press("n")
            assert app.session.current_entry() is not None
            assert app.session.index == 1
            await pilot.press("p")
            assert app.session.index == 0
            await pilot.press("?")
            assert any("Keyboard Shortcuts" in log for log in app.session.logs)

    asyncio.run(run_app())


def test_03_search(session: DebuggerSession) -> None:
    matches = session.search(SearchQuery("refund policy", fields=("prompt",)))

    assert matches[0].event_id == "qa-run-event-2"
    assert matches[0].field == "prompt"
    entry = session.current_entry()
    assert entry is not None
    assert entry.event.event_id == "qa-run-event-2"


def test_04_jump_event(session: DebuggerSession) -> None:
    entry = session.jump_to_event("qa-run-event-6")

    assert entry.event.event_type == TOOL_FINISHED
    assert session.index == 5
    assert "Jumped to event qa-run-event-6." in session.logs


def test_05_timeline(session: DebuggerSession) -> None:
    lines = render_timeline_tree(session.visible_entries())

    assert lines[0] == "Run Started (qa-run-event-1)"
    assert any("Tool Finished" in line for line in lines)
    assert any("qa-run-event-6" in line for line in lines)


def test_06_metadata_panel(session: DebuggerSession) -> None:
    session.jump_to_event("qa-run-event-6")
    inspection = session.inspect_current()

    assert inspection is not None
    assert inspection.metadata["cache_hit"] is True
    assert '"cache_hit": true' in render_metadata(inspection.metadata)


def test_07_statistics(session: DebuggerSession) -> None:
    stats = session.statistics()
    rendered = render_stats(stats)

    assert stats.total_events == 14
    assert stats.total_tokens == 33
    assert stats.cost == 1.0
    assert stats.errors == 1
    assert "Total Events: 14" in rendered


def test_08_export_html(session: DebuggerSession) -> None:
    session.jump_to_event("qa-run-event-8")
    entry = session.current_entry()

    assert entry is not None
    exported = render_event_export(entry, "html")

    assert "<!doctype html>" in exported
    assert "<h1>Assistant Response</h1>" in exported


def test_09_export_markdown(session: DebuggerSession) -> None:
    session.jump_to_event("qa-run-event-8")
    entry = session.current_entry()

    assert entry is not None
    exported = render_event_export(entry, "markdown")

    assert exported.startswith("# Assistant Response")
    assert "```json" in exported


def test_10_export_json(session: DebuggerSession) -> None:
    session.jump_to_event("qa-run-event-8")
    entry = session.current_entry()

    assert entry is not None
    exported = json.loads(render_event_export(entry, "json"))

    assert exported["event_id"] == "qa-run-event-8"
    assert exported["payload"]["response"] == "Refunds take 30 days."


def test_11_html_report(trace: TraceSnapshot) -> None:
    bundle = ReportingEngine().generate_trace(trace)
    html = render_html(bundle)

    assert bundle.run_id == "qa-run"
    assert "AgentReplay Trace Report" in html
    assert "Execution Timeline" in html
    assert "Interactive execution DAG" in html


@pytest.mark.performance
def test_12_large_report() -> None:
    bundle = ReportingEngine().generate_trace(
        _large_trace("large-report", count=12_000),
        options=ReportOptions(visualization_limit=5_000),
    )

    assert len(bundle.nodes) == 12_000
    assert len(bundle.timeline) == 5_000
    assert bundle.metadata["event_count"] == 12_000


def test_13_report_search(trace: TraceSnapshot) -> None:
    bundle = ReportingEngine().generate_trace(trace)
    searchable = {document.event_id: document.text for document in bundle.search_index}

    assert "refund policy" in searchable["qa-run-event-2"]
    assert "lookup" in searchable["qa-run-event-5"]
    assert render_json_bundle(bundle).count("refund policy") >= 1
    assert "# AgentReplay Trace Report" in render_markdown_summary(bundle)


def test_14_sdk_hooks() -> None:
    sdk = AgentReplaySDK(SDKContext())
    seen: list[Mapping[str, JSONValue]] = []

    def before_report(context: SDKHookContext) -> None:
        seen.append(context.payload)

    sdk.hooks.register(
        "before_report",
        before_report,
        extension_name="qa-extension",
    )
    results = sdk.hooks.emit("before_report", payload={"run_id": "qa-run"})

    assert results[0].succeeded
    assert seen == [{"run_id": "qa-run"}]


def test_15_sdk_events() -> None:
    sdk = AgentReplaySDK(SDKContext())
    seen: list[SDKEvent] = []

    def collect(event: SDKEvent) -> None:
        seen.append(event)

    sdk.events.subscribe("event.created", collect)
    event = sdk.events.publish(
        "event.created",
        payload={"event_id": "event-1"},
        source="qa",
    )
    sdk.events.unsubscribe("event.created", collect)

    assert event.source == "qa"
    assert seen[0].payload["event_id"] == "event-1"
    assert sdk.events.subscribers("event.created") == 0


def test_16_plugin_loading() -> None:
    app = PluginApp()
    manager = PluginManager(app=app)

    record = manager.load_plugin(_LifecyclePlugin())

    assert record.status == "loaded"
    assert record.metadata.name == "qa-lifecycle"
    assert app.registrations(kind="sdk_analyzer")[0].name == "qa-analyzer"


def test_17_plugin_unload() -> None:
    app = PluginApp()
    manager = PluginManager(app=app)
    manager.load_plugin(_LifecyclePlugin())

    manager.unload_plugin("qa-lifecycle")
    record = manager.registry.require("qa-lifecycle")

    assert record.status == "unloaded"
    assert app.registrations(plugin_name="qa-lifecycle") == ()


def test_18_cli_extension(capsys: pytest.CaptureFixture[str]) -> None:
    sdk = AgentReplaySDK(SDKContext())
    sdk.register(_CLIExtension())
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    sdk.install_cli_commands(subparsers)

    args = parser.parse_args(["qa", "analyze"])

    assert args.handler(args) == 0
    assert "qa analyze" in capsys.readouterr().out


def test_19_custom_analyzer(trace: TraceSnapshot) -> None:
    analyzer = _LatencyAnalyzer()
    sdk = AgentReplaySDK(SDKContext())
    sdk.register(analyzer)

    result = analyzer.analyze(trace)

    assert sdk.registry.require("analyzer", "latency-qa") is analyzer
    assert result.metrics["event_count"] == len(trace.events)
    assert result.recommendations == ("Review slow events.",)


def test_20_custom_exporter(trace: TraceSnapshot, tmp_path: Path) -> None:
    exporter = _JSONLinesExporter()
    sdk = AgentReplaySDK(SDKContext())
    sdk.register(exporter)
    destination = tmp_path / "trace.jsonl"

    result = exporter.export(trace, str(destination))

    assert sdk.registry.require("exporter", "jsonl-qa") is exporter
    assert result.content_type == "application/x-ndjson"
    assert result.bytes_written == destination.stat().st_size
    assert destination.read_text(encoding="utf-8").count("\n") == len(trace.events)


class _LifecyclePlugin(AgentReplayPlugin):
    name = "qa-lifecycle"
    version = "0.1.0"
    plugin_type = "sdk_analyzer"

    def register(self, app: object) -> None:
        """Register a lifecycle analyzer for plugin-manager tests."""
        assert isinstance(app, PluginApp)
        app.register_sdk_analyzer("qa-analyzer", _LatencyAnalyzer())


class _CLIExtension(BaseCLICommand):
    metadata = SDKExtensionMetadata(
        name="qa-cli",
        version="0.1.0",
        kind="cli_command",
    )

    def register(
        self,
        subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    ) -> None:
        """Register a deterministic QA command."""
        parser = subparsers.add_parser("qa")
        parser.add_argument("action", choices=("analyze",))
        parser.set_defaults(handler=self.handle)

    def handle(self, args: argparse.Namespace) -> int:
        """Handle the deterministic QA command."""
        write_line(f"qa {args.action}")
        return 0


class _LatencyAnalyzer(BaseAnalyzer):
    metadata = analyzer_metadata("latency-qa")

    def analyze(self, trace: TraceSnapshot) -> AnalyzerResult:
        """Return deterministic latency metrics for a recorded trace."""
        slow_events = tuple(
            event.event_id for event in trace.events if event.duration_ms > 1000
        )
        return AnalyzerResult(
            analyzer=self.metadata.name,
            findings=({"slow_events": len(slow_events)},),
            metrics={
                "event_count": len(trace.events),
                "slow_events": len(slow_events),
            },
            recommendations=("Review slow events.",),
        )


class _JSONLinesExporter(BaseExporter):
    metadata = exporter_metadata("jsonl-qa")

    def export(
        self,
        trace: TraceSnapshot,
        destination: str | None = None,
    ) -> ExportResult:
        """Export one trace as newline-delimited event JSON."""
        if destination is None:
            content = "\n".join(
                json.dumps(event.to_dict(), sort_keys=True) for event in trace.events
            )
            return ExportResult(
                exporter=self.metadata.name,
                content_type="application/x-ndjson",
                bytes_written=len(content.encode("utf-8")),
            )
        path = Path(destination)
        path.write_text(
            "\n".join(
                json.dumps(event.to_dict(), sort_keys=True) for event in trace.events
            )
            + "\n",
            encoding="utf-8",
        )
        return ExportResult(
            exporter=self.metadata.name,
            content_type="application/x-ndjson",
            bytes_written=path.stat().st_size,
            uri=str(path),
        )


def _trace(run_id: str) -> TraceSnapshot:
    """Build a deterministic trace for debugger/reporting/SDK tests."""
    events = (
        _event(f"{run_id}-event-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(
            f"{run_id}-event-2",
            run_id,
            2,
            USER_PROMPT,
            {"prompt": "explain refund policy"},
            metadata={"panel": "prompt"},
        ),
        _event(
            f"{run_id}-event-3",
            run_id,
            3,
            LLM_REQUEST,
            {
                "provider_name": "openai",
                "model_name": "gpt-demo",
                "prompt": "explain refund policy",
                "token_usage": {"prompt_tokens": 10, "completion_tokens": 23},
                "cost": {"amount": 0.5, "currency": "USD"},
            },
            duration_ms=1_250.0,
        ),
        _event(
            f"{run_id}-event-4",
            run_id,
            4,
            LLM_RESPONSE,
            {"provider_name": "openai", "model_name": "gpt-demo"},
            parent_event_id=f"{run_id}-event-3",
        ),
        _event(
            f"{run_id}-event-5",
            run_id,
            5,
            TOOL_STARTED,
            {"tool_name": "lookup", "arguments": {"query": "refund"}},
        ),
        _event(
            f"{run_id}-event-6",
            run_id,
            6,
            TOOL_FINISHED,
            {"tool_name": "lookup", "result": "30 days"},
            parent_event_id=f"{run_id}-event-5",
            duration_ms=1_500.0,
            metadata={"cache_hit": True},
        ),
        _event(f"{run_id}-event-7", run_id, 7, MEMORY_READ, {"key": "profile"}),
        _event(
            f"{run_id}-event-8",
            run_id,
            8,
            ASSISTANT_RESPONSE,
            {"response": "Refunds take 30 days."},
        ),
        _event(f"{run_id}-event-9", run_id, 9, MEMORY_WRITE, {"key": "profile"}),
        _event(f"{run_id}-event-10", run_id, 10, RETRY_RECORDED, {"attempt": 1}),
        _event(f"{run_id}-event-11", run_id, 11, WARNING_RAISED, {"message": "slow"}),
        _event(
            f"{run_id}-event-12",
            run_id,
            12,
            EXCEPTION_RAISED,
            {"exception": {"type": "RuntimeError", "message": "boom"}},
        ),
        _event(f"{run_id}-event-13", run_id, 13, COST_RECORDED, {"amount": 0.5}),
        _event(f"{run_id}-event-14", run_id, 14, RUN_FINISHED, {"status": "completed"}),
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _large_trace(run_id: str, *, count: int) -> TraceSnapshot:
    """Build a large deterministic trace for report scalability coverage."""
    events = tuple(
        _event(
            f"{run_id}-event-{index}",
            run_id,
            index,
            CUSTOM_EVENT,
            {"message": f"checkpoint {index}"},
        )
        for index in range(1, count + 1)
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _run(run_id: str) -> RunRecord:
    """Create a deterministic run record."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name="qa-agent",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=2),
        duration_ms=2_000.0,
        metadata={"suite": "debugger-reporting-sdk"},
        tags=("qa",),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: Mapping[str, object],
    *,
    parent_event_id: str | None = None,
    duration_ms: float | None = None,
    metadata: Mapping[str, object] | None = None,
) -> EventRecord:
    """Create a deterministic event record."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        + timedelta(milliseconds=sequence),
        duration_ms=float(sequence) if duration_ms is None else duration_ms,
        metadata={} if metadata is None else _json_mapping(metadata),
        payload=_json_mapping(payload),
    )


def _json_mapping(value: Mapping[str, object]) -> Mapping[str, JSONValue]:
    """Cast test literals to the package JSON mapping type."""
    return cast(Mapping[str, JSONValue], value)
