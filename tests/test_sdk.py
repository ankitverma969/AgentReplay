from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

import pytest
from agentreplay import AgentReplaySDK, SDKError, create_sdk
from agentreplay.cli.commands._shared import write_line
from agentreplay.cli.main import main
from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import SDKError as ImportedSDKError
from agentreplay.plugins import PluginApp
from agentreplay.sdk import (
    DEPRECATION_POLICY,
    SDK_API_VERSION,
    AnalyzerResult,
    BaseAnalyzer,
    ExportResult,
    ReportSection,
    SDKCompatibility,
    SDKContext,
    SDKEvent,
    SDKEventBus,
    SDKExtensionMetadata,
    SDKExtensionRegistry,
    SDKHookContext,
    SDKHookManager,
    SDKVersion,
    analyzer_metadata,
    analyzer_plugin,
    cli_plugin,
    compatible,
    deprecated,
    ensure_sdk_compatible,
)
from agentreplay.sdk.cli import register_sdk_cli_commands
from agentreplay.sdk.extensions import BaseCLICommand
from agentreplay.sdk.plugin import plugin_metadata_from_sdk


def test_sdk_metadata_versioning_and_compatibility() -> None:
    metadata = SDKExtensionMetadata(
        name="latency",
        version="0.1.0",
        kind="analyzer",
        compatibility=compatible(min_sdk_version="0.1.0"),
    )

    ensure_sdk_compatible(metadata)

    assert str(SDKVersion.parse("1.2.3")) == "1.2.3"
    assert metadata.to_dict()["name"] == "latency"
    assert SDK_API_VERSION == "0.1.0"
    assert "semantic versioning" in DEPRECATION_POLICY


def test_sdk_rejects_incompatible_extensions() -> None:
    metadata = SDKExtensionMetadata(
        name="future",
        version="0.1.0",
        kind="analyzer",
        compatibility=SDKCompatibility(min_sdk_version="99.0.0"),
    )

    with pytest.raises(SDKError):
        ensure_sdk_compatible(metadata)


def test_deprecated_decorator_warns() -> None:
    @deprecated("old")
    def old_function() -> str:
        return "ok"

    with pytest.warns(DeprecationWarning, match="old"):
        assert old_function() == "ok"


def test_event_bus_is_typed_and_isolates_failures() -> None:
    bus = SDKEventBus()
    seen: list[SDKEvent] = []

    def broken(_event: SDKEvent) -> None:
        raise RuntimeError("boom")

    bus.subscribe("run.started", seen.append)
    bus.subscribe("run.started", broken)
    event = bus.publish("run.started", payload={"run_id": "run-1"}, source="test")

    assert event.name == "run.started"
    assert seen[0].payload["run_id"] == "run-1"
    assert bus.subscribers("run.started") == 2

    bus.unsubscribe("run.started", seen.append)
    assert bus.subscribers("run.started") == 2


def test_hook_manager_returns_success_and_failure_results() -> None:
    hooks = SDKHookManager()

    def ok(context: SDKHookContext) -> None:
        assert context.payload["run_id"] == "run-1"

    def broken(_context: SDKHookContext) -> None:
        raise RuntimeError("bad")

    hooks.register("before_export", ok, extension_name="ok")
    hooks.register("before_export", broken, extension_name="broken")
    results = hooks.emit("before_export", payload={"run_id": "run-1"})

    assert [result.succeeded for result in results] == [True, False]
    assert results[1].error == "bad"


def test_sdk_registry_and_facade_register_extensions(tmp_path: Path) -> None:
    class LatencyAnalyzer(BaseAnalyzer):
        metadata = analyzer_metadata("latency")

        def analyze(self, trace: TraceSnapshot) -> AnalyzerResult:
            return AnalyzerResult(
                analyzer=self.metadata.name,
                metrics={"events": len(trace.events)},
            )

    sdk = create_sdk(storage=None, metadata={"source": "test"})
    analyzer = LatencyAnalyzer()
    sdk.register(analyzer)

    assert isinstance(sdk, AgentReplaySDK)
    assert sdk.registry.require("analyzer", "latency") is analyzer
    assert (
        sdk.context.sqlite_storage(tmp_path / "sdk.sqlite").db_path.name == "sdk.sqlite"
    )
    assert sdk.context.replay_engine() is not None
    assert sdk.context.diff_engine() is not None
    assert sdk.context.profiler_engine() is not None
    assert sdk.context.security_engine() is not None
    assert sdk.context.regression_engine() is not None
    assert sdk.context.reporting_engine() is not None
    assert sdk.context.observability_engine() is not None


def test_sdk_registry_rejects_duplicate_names() -> None:
    registry = SDKExtensionRegistry()

    class Analyzer(BaseAnalyzer):
        metadata = analyzer_metadata("dup")

    registry.register_analyzer(Analyzer())

    with pytest.raises(SDKError):
        registry.register_analyzer(Analyzer())


def test_sdk_analyzer_exporter_and_report_shapes() -> None:
    trace = _trace()
    analyzer = BaseAnalyzer()
    analyzer.metadata = analyzer_metadata("base")

    class Exporter:
        metadata = SDKExtensionMetadata(
            name="xml",
            version="0.1.0",
            kind="exporter",
        )

        def export(
            self,
            trace: TraceSnapshot,
            destination: str | None = None,
        ) -> ExportResult:
            return ExportResult(
                exporter=self.metadata.name,
                content_type="application/xml",
                bytes_written=len(trace.events),
                uri=destination,
            )

    section = ReportSection(title="Stats", html="<p>ok</p>")

    assert analyzer.analyze(trace).to_dict()["analyzer"] == "base"
    assert Exporter().export(trace, "out.xml").content_type == "application/xml"
    assert section.title == "Stats"


def test_sdk_plugin_bridge_registers_extensions() -> None:
    class Analyzer(BaseAnalyzer):
        metadata = analyzer_metadata("bridge")

    plugin = analyzer_plugin(Analyzer())
    app = PluginApp()
    app.activate(plugin.name, {})
    plugin.register(app)

    registrations = app.registrations(kind="sdk_analyzer")
    assert registrations[0].name == "bridge"
    assert plugin_metadata_from_sdk(Analyzer.metadata).plugin_type == "sdk_analyzer"


def test_sdk_cli_command_extension_registers_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Command(BaseCLICommand):
        metadata = SDKExtensionMetadata(
            name="myplugin",
            version="0.1.0",
            kind="cli_command",
        )

        def register(
            self,
            subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
        ) -> None:
            parser = subparsers.add_parser("myplugin")
            parser.add_argument("action", choices=("analyze",))
            parser.set_defaults(handler=self.handle)

        def handle(self, args: argparse.Namespace) -> int:
            write_line(f"myplugin {args.action}")
            return 0

    sdk = AgentReplaySDK(SDKContext())
    sdk.register(Command())
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    sdk.install_cli_commands(subparsers)

    args = parser.parse_args(["myplugin", "analyze"])
    assert args.handler(args) == 0
    assert "myplugin analyze" in capsys.readouterr().out


def test_sdk_cli_plugin_helper_registers_plugin_commands() -> None:
    class Command(BaseCLICommand):
        metadata = SDKExtensionMetadata(
            name="plugin-command",
            version="0.1.0",
            kind="cli_command",
        )

        def register(
            self,
            subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
        ) -> None:
            parser = subparsers.add_parser("plugin-command")
            parser.set_defaults(handler=lambda _args: 0)

    plugin = cli_plugin(Command())
    app = PluginApp()
    app.activate(plugin.name, {})
    plugin.register(app)

    class Manager:
        def __init__(self, plugin_app: PluginApp) -> None:
            self.app = plugin_app

        def load_plugins(self) -> tuple[object, ...]:
            return (plugin,)

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    count = register_sdk_cli_commands(
        subparsers,
        manager=Manager(app),  # type: ignore[arg-type]
    )

    assert count == 1
    assert parser.parse_args(["plugin-command"]).handler(None) == 0


def test_public_sdk_imports_and_cli_help() -> None:
    assert ImportedSDKError is SDKError
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def _trace() -> TraceSnapshot:
    run = RunRecord(
        run_id="run-1",
        name="sdk",
        status="completed",
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ms=1.0,
        metadata={},
    )
    event = EventRecord(
        event_id="event-1",
        run_id=run.run_id,
        parent_event_id=None,
        sequence=1,
        event_type="custom.event",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        duration_ms=1.0,
        metadata={},
        payload={"prompt": "hello"},
    )
    return TraceSnapshot(run=run, events=(event,))
