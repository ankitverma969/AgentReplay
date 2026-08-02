from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from agentreplay import ReportingEngine, SQLiteStorage
from agentreplay.cli.main import main
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_STARTED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.plugins import AgentReplayPlugin, PluginApp
from agentreplay.reporting import ReportOptions
from agentreplay.reporting.renderers import (
    render_html,
    render_json_bundle,
    render_markdown_summary,
    render_zip_package,
)
from agentreplay.types import JSONValue


def test_reporting_engine_generates_offline_html_bundle() -> None:
    bundle = ReportingEngine().generate_trace(_trace("run-report"))
    html = render_html(bundle)

    assert bundle.run_id == "run-report"
    assert bundle.nodes
    assert bundle.edges
    assert bundle.timeline
    assert bundle.profiler["summary"]
    assert bundle.security["findings"]
    assert "sk-test-secret" not in json.dumps(bundle.trace)
    assert '<script type="application/json" id="agentreplay-report-data">' in html
    assert "https://" not in html
    assert "cdn" not in html.lower()
    assert "Interactive execution DAG" in html
    assert "Search and Filters" in html
    assert "High Contrast" in html
    assert "skip-link" in html


def test_reporting_renderers_emit_json_markdown_zip_and_compressed_html() -> None:
    bundle = ReportingEngine().generate_trace(
        _trace("run-report"),
        options=ReportOptions(theme="light", compress=True),
    )

    html = render_html(bundle, compress=True)
    json_bundle = json.loads(render_json_bundle(bundle))
    markdown = render_markdown_summary(bundle)
    zip_bytes = render_zip_package(bundle)

    assert bundle.theme == "light"
    assert "\n" not in html[:500]
    assert json_bundle["run_id"] == "run-report"
    assert "# AgentReplay Trace Report" in markdown
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        assert {"report.html", "summary.md", "bundle.json"} <= set(archive.namelist())


def test_reporting_generates_diff_report() -> None:
    left = _trace("left")
    right = _trace("right", answer="different answer")

    bundle = ReportingEngine().generate_trace(
        left,
        options=ReportOptions(compare_run_id="right"),
        compare_trace=right,
    )

    assert bundle.diff is not None
    stats = cast(Mapping[str, JSONValue], bundle.diff["stats"])
    assert cast(int, stats["changed"]) >= 1
    html = render_html(bundle)
    assert "Diff Report" in html
    assert "Side-by-side comparison" in html
    assert "diff-grid" in html


def test_reporting_loads_from_storage_and_cli_writes_output(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "report.sqlite"
    output_path = tmp_path / "report.html"
    storage = SQLiteStorage(db_path)
    trace = _trace("run-storage")
    storage.save_run(trace.run)
    storage.bulk_insert_events(trace.events)
    storage.close()

    exit_code = main(
        [
            "report",
            "run-storage",
            "--db-path",
            str(db_path),
            "--output",
            str(output_path),
            "--light",
            "--compress",
        ]
    )

    assert exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert "AgentReplay Trace Report" in content
    assert "theme-light" in content


def test_reporting_cli_rejects_missing_run_and_conflicting_themes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "missing.sqlite"

    assert main(["report", "missing", "--db-path", str(db_path)]) == 1
    assert (
        main(["report", "missing", "--dark", "--light", "--db-path", str(db_path)]) == 1
    )


def test_plugin_app_registers_report_extensions() -> None:
    app = PluginApp()
    app.activate("reporting", {})
    _ReportingPlugin().register(app)
    app.deactivate()

    kinds = {registration.kind for registration in app.registrations()}

    assert {"report_section", "report_chart", "report_widget"} <= kinds


def test_reporting_engine_includes_plugin_extension_html() -> None:
    bundle = ReportingEngine(
        extensions={"custom": _ReportExtension("<p>Custom section</p>")},
        charts={"chart": _ReportExtension("<div>Custom chart</div>")},
        widgets={"widget": _ReportExtension("<button>Widget</button>")},
    ).generate_trace(_trace("run-report"))
    html = render_html(bundle)

    assert len(bundle.extensions) == 3
    assert "Custom section" in html
    assert "Custom chart" in html
    assert "Widget" in html


@pytest.mark.performance
def test_reporting_large_trace_generation_is_linear_enough() -> None:
    trace = _large_trace("run-large", count=20_000)

    started = perf_counter()
    bundle = ReportingEngine().generate_trace(trace)
    elapsed = perf_counter() - started

    assert len(bundle.nodes) == 20_000
    assert len(bundle.timeline) == 10_000
    assert elapsed < 20.0


class _ReportingPlugin(AgentReplayPlugin):
    name = "reporting"
    version = "1.0.0"
    plugin_type = "report_section"

    def register(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        extension = _ReportExtension("<p>plugin</p>")
        app.register_report_section("section", extension)
        app.register_report_chart("chart", extension)
        app.register_report_widget("widget", extension)


class _ReportExtension:
    """Report extension stub."""

    def __init__(self, html: str) -> None:
        self._html = html

    def render(self, report: object) -> str:
        """Render extension HTML."""
        assert report is not None
        return self._html


def _trace(run_id: str, *, answer: str = "done") -> TraceSnapshot:
    """Create a representative trace for reports."""
    events = (
        _event(f"{run_id}-event-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(
            f"{run_id}-event-2",
            run_id,
            2,
            USER_PROMPT,
            {"prompt": "hello", "api_key": "sk-test-secret"},
        ),
        _event(
            f"{run_id}-event-3",
            run_id,
            3,
            LLM_REQUEST,
            {
                "provider_name": "openai",
                "model_name": "gpt-demo",
                "token_usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
                "cost": {"amount": 0.2, "currency": "USD"},
            },
            duration_ms=1_500.0,
        ),
        _event(
            f"{run_id}-event-4",
            run_id,
            4,
            LLM_RESPONSE,
            {"provider_name": "openai", "model_name": "gpt-demo"},
        ),
        _event(
            f"{run_id}-event-5",
            run_id,
            5,
            TOOL_STARTED,
            {"tool_name": "lookup"},
            duration_ms=1_200.0,
        ),
        _event(
            f"{run_id}-event-6",
            run_id,
            6,
            TOOL_FINISHED,
            {"tool_name": "lookup", "result": "ok"},
        ),
        _event(f"{run_id}-event-7", run_id, 7, MEMORY_READ, {"key": "state"}),
        _event(f"{run_id}-event-8", run_id, 8, MEMORY_WRITE, {"key": "state"}),
        _event(f"{run_id}-event-9", run_id, 9, RETRY_RECORDED, {"attempt": 1}),
        _event(f"{run_id}-event-10", run_id, 10, WARNING_RAISED, {"message": "slow"}),
        _event(
            f"{run_id}-event-11",
            run_id,
            11,
            EXCEPTION_RAISED,
            {"exception": {"type": "RuntimeError", "message": "boom"}},
        ),
        _event(
            f"{run_id}-event-12",
            run_id,
            12,
            ASSISTANT_RESPONSE,
            {"response": answer},
        ),
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _large_trace(run_id: str, *, count: int) -> TraceSnapshot:
    """Create a large trace for performance coverage."""
    events = tuple(
        _event(
            f"{run_id}-event-{index}",
            run_id,
            index,
            CUSTOM_EVENT,
            {"name": f"checkpoint-{index}"},
        )
        for index in range(1, count + 1)
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _run(run_id: str) -> RunRecord:
    """Create a run record."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name="agent",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=10),
        duration_ms=10_000.0,
        metadata={"suite": "reporting"},
        tags=("report",),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, JSONValue],
    *,
    duration_ms: float | None = None,
) -> EventRecord:
    """Create an event record."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=None,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        + timedelta(milliseconds=sequence),
        duration_ms=float(sequence) if duration_ms is None else duration_ms,
        metadata={},
        payload=payload,
    )
