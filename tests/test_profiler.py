from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from agentreplay import ProfilerEngine, SQLiteStorage
from agentreplay.cli.main import main
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
    RUN_STARTED,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ProfilerError
from agentreplay.plugins import AgentReplayPlugin, PluginApp
from agentreplay.profiler.models import OptimizationRecommendation
from agentreplay.profiler.renderers import (
    render_csv,
    render_html,
    render_json,
    render_markdown,
    render_summary,
    render_timeline,
)
from agentreplay.types import JSONValue


def test_profiler_calculates_duration_token_cost_model_tool_and_memory() -> None:
    report = ProfilerEngine().profile(_trace("run-profile"))

    assert report.run_id == "run-profile"
    assert report.duration.count == len(_trace("run-profile").events)
    assert report.duration.total_ms >= 3_500.0
    assert report.duration.p95_ms >= report.duration.p50_ms
    assert report.token_analysis.prompt_tokens == 80
    assert report.token_analysis.completion_tokens == 20
    assert report.token_analysis.total_tokens == 100
    assert report.cost_analysis.total_cost == pytest.approx(1.5)
    assert report.cost_analysis.cost_per_model["gpt-demo"] == pytest.approx(1.5)
    assert report.model_analysis.models_used == ("gpt-demo",)
    assert report.model_analysis.provider_distribution == {"openai": 2}
    assert report.tool_analysis.most_used_tool == "lookup"
    assert report.tool_analysis.slowest_tool == "lookup"
    assert report.tool_analysis.profiles[0].failure_rate > 0
    assert report.memory_analysis.reads == 2
    assert report.memory_analysis.writes == 1


def test_profiler_detects_bottlenecks_and_recommendations() -> None:
    report = ProfilerEngine().profile(_trace("run-profile"))
    categories = {bottleneck.category for bottleneck in report.bottlenecks}
    recommendation_categories = {
        recommendation.category for recommendation in report.recommendations
    }

    assert "slow_tool_call" in categories
    assert "slow_model_call" in categories
    assert "expensive_operation" in categories
    assert "duplicate_events" in categories
    assert "repeated_calls" in categories
    assert "redundant_memory_reads" in categories
    assert "excessive_retries" in categories
    assert "large_prompt" in categories
    assert "large_response" in categories
    assert {
        "prompt_compression",
        "tool_caching",
        "retry_optimization",
        "memory_optimization",
        "cost_reduction",
    } <= recommendation_categories


def test_profiler_renderers_emit_all_requested_formats() -> None:
    report = ProfilerEngine().profile(_trace("run-profile"))

    assert "Profile for run-profile" in render_summary(report)
    assert "Execution Timeline" in render_timeline(report)
    assert json.loads(render_json(report))["run_id"] == "run-profile"
    assert "# AgentReplay Profile" in render_markdown(report)
    assert "<html" in render_html(report)
    assert "section,metric,value" in render_csv(report)


def test_profiler_loads_from_storage_and_cli_formats(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "profile.sqlite"
    storage = SQLiteStorage(db_path)
    trace = _trace("run-storage")
    storage.save_run(trace.run)
    storage.bulk_insert_events(trace.events)
    storage.close()

    assert main(["profile", "run-storage", "--db-path", str(db_path), "--summary"]) == 0
    assert "Profile for run-storage" in capsys.readouterr().out

    assert main(["profile", "run-storage", "--db-path", str(db_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["run_id"] == "run-storage"

    assert main(["profile", "run-storage", "--db-path", str(db_path), "--csv"]) == 0
    assert "duration,total_ms" in capsys.readouterr().out

    assert (
        main(
            [
                "profile",
                "run-storage",
                "--db-path",
                str(db_path),
                "--summary",
                "--json",
            ]
        )
        == 1
    )
    assert "Choose only one profile output format" in capsys.readouterr().out


def test_profiler_handles_missing_runs(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "missing.sqlite")

    with pytest.raises(ProfilerError):
        ProfilerEngine(storage=storage).profile("missing")
    storage.close()


def test_profiler_custom_metrics_and_recommendations_are_isolated() -> None:
    report = ProfilerEngine(
        custom_metrics={
            "event_count": lambda trace: len(trace.events),
            "broken": _broken_metric,
        },
        custom_recommendations={
            "cache": _cache_recommendation,
            "broken": _broken_recommendation,
        },
    ).profile(_trace("run-profile"))

    assert report.custom_metrics["event_count"] == len(_trace("run-profile").events)
    assert report.custom_metrics["broken"] == {"error": "metric exploded"}
    assert any(
        recommendation.description == "Plugin recommendation."
        for recommendation in report.recommendations
    )
    assert any(
        recommendation.description == "Custom recommendation broken failed."
        for recommendation in report.recommendations
    )


def test_plugin_app_registers_profiler_capabilities() -> None:
    app = PluginApp()
    app.activate("profiler", {})
    _ProfilerPlugin().register(app)
    app.deactivate()

    kinds = {registration.kind for registration in app.registrations()}

    assert {"custom_profiler", "custom_metric", "custom_recommendation"} <= kinds


def test_profiler_large_trace_is_linear_enough() -> None:
    trace = _large_trace("run-large", count=20_000)

    started = perf_counter()
    report = ProfilerEngine().profile(trace)
    elapsed = perf_counter() - started

    assert report.duration.count == 20_000
    assert report.duration.p99_ms >= 0.0
    assert len(report.visualizations.execution_timeline) == 10_000
    assert elapsed < 8.0


class _ProfilerPlugin(AgentReplayPlugin):
    name = "profiler"
    version = "1.0.0"
    plugin_type = "custom_profiler"

    def register(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        app.register_custom_profiler("extra-profile", _PluginProfiler())
        app.register_custom_metric("extra-metric", _PluginMetric())
        app.register_custom_recommendation(
            "extra-recommendation",
            _PluginRecommendation(),
        )


class _PluginProfiler:
    """Plugin profiler stub for registration coverage."""

    def profile(self, trace: object) -> object:
        """Return a plugin profile."""
        return {"trace": str(trace)}


class _PluginMetric:
    """Plugin metric stub for registration coverage."""

    def measure(self, trace: object) -> object:
        """Return a plugin metric."""
        return str(trace)


class _PluginRecommendation:
    """Plugin recommendation stub for registration coverage."""

    def recommend(self, profile: object) -> object:
        """Return plugin recommendations."""
        return (str(profile),)


def _broken_metric(trace: TraceSnapshot) -> JSONValue:
    """Raise a metric error for isolation coverage."""
    assert trace.run.run_id
    raise RuntimeError("metric exploded")


def _cache_recommendation(
    report: object,
) -> tuple[OptimizationRecommendation, ...]:
    """Return a custom recommendation for isolation coverage."""
    assert report is not None
    return (
        OptimizationRecommendation(
            category="tool_caching",
            severity="info",
            description="Plugin recommendation.",
            rationale="Plugin saw repeated calls.",
        ),
    )


def _broken_recommendation(report: object) -> tuple[OptimizationRecommendation, ...]:
    """Raise a recommendation error for isolation coverage."""
    assert report is not None
    raise RuntimeError("recommendation exploded")


def _trace(run_id: str) -> TraceSnapshot:
    """Create a representative profiling trace."""
    large_prompt = "p" * 4_100
    large_response = "r" * 8_100
    events = (
        _event(f"{run_id}-event-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(f"{run_id}-event-2", run_id, 2, USER_PROMPT, {"prompt": large_prompt}),
        _event(
            f"{run_id}-event-3",
            run_id,
            3,
            LLM_REQUEST,
            {
                "provider_name": "openai",
                "model_name": "gpt-demo",
                "token_usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 20,
                    "total_tokens": 100,
                },
                "cost": {"amount": 1.5, "currency": "USD"},
            },
            duration_ms=2_000.0,
        ),
        _event(
            f"{run_id}-event-4",
            run_id,
            4,
            LLM_RESPONSE,
            {"provider_name": "openai", "model_name": "gpt-demo"},
            duration_ms=2_500.0,
        ),
        _event(
            f"{run_id}-event-5",
            run_id,
            5,
            TOOL_STARTED,
            {"tool_name": "lookup", "arguments": {"query": "refund"}},
            duration_ms=1_500.0,
        ),
        _event(
            f"{run_id}-event-6",
            run_id,
            6,
            TOOL_FINISHED,
            {"tool_name": "lookup", "result": "30 days"},
            duration_ms=1_750.0,
        ),
        _event(
            f"{run_id}-event-7",
            run_id,
            7,
            TOOL_FAILED,
            {"tool_name": "lookup", "error": "timeout"},
            duration_ms=1_200.0,
        ),
        _event(f"{run_id}-event-8", run_id, 8, MEMORY_READ, {"key": "state"}),
        _event(f"{run_id}-event-9", run_id, 9, MEMORY_READ, {"key": "state"}),
        _event(
            f"{run_id}-event-10",
            run_id,
            10,
            MEMORY_WRITE,
            {"key": "state", "value": {"ok": True}},
        ),
        _event(f"{run_id}-event-11", run_id, 11, RETRY_RECORDED, {"attempt": 1}),
        _event(f"{run_id}-event-12", run_id, 12, RETRY_RECORDED, {"attempt": 2}),
        _event(f"{run_id}-event-13", run_id, 13, RETRY_RECORDED, {"attempt": 3}),
        _event(
            f"{run_id}-event-14",
            run_id,
            14,
            ASSISTANT_RESPONSE,
            {"response": large_response},
        ),
        _event(f"{run_id}-event-15", run_id, 15, COST_RECORDED, {"amount": 0.0}),
        _event(
            f"{run_id}-event-16",
            run_id,
            16,
            EXCEPTION_RAISED,
            {"exception": {"type": "RuntimeError", "message": "boom"}},
        ),
        _event(f"{run_id}-event-17", run_id, 17, CUSTOM_EVENT, {"name": "same"}),
        _event(f"{run_id}-event-18", run_id, 18, CUSTOM_EVENT, {"name": "same"}),
        _event(f"{run_id}-event-19", run_id, 19, CUSTOM_EVENT, {"name": "same"}),
        _event(f"{run_id}-event-20", run_id, 20, CUSTOM_EVENT, {"name": "same"}),
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
            duration_ms=float(index % 25),
        )
        for index in range(1, count + 1)
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _run(run_id: str) -> RunRecord:
    """Create a profiling run record."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name="agent",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=10),
        duration_ms=10_000.0,
        metadata={},
        tags=("profile",),
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
