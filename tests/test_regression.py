from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentreplay import (
    RegressionEngine,
    RegressionFinding,
    RegressionReport,
    RootCause,
    SQLiteStorage,
)
from agentreplay.cli.main import build_parser, main
from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import RegressionError
from agentreplay.plugins import PluginApp
from agentreplay.regression.renderers import (
    render_csv,
    render_graph,
    render_html,
    render_json,
    render_markdown,
    render_summary,
)
from agentreplay.types import JSONValue


def test_regression_engine_detects_root_causes_and_recommendations() -> None:
    report = RegressionEngine().compare(_baseline_trace(), _target_trace())

    titles = {finding.title for finding in report.findings}

    assert "Execution Time Ms Increased" in titles
    assert "Cost Increased" in titles
    assert "Tokens Increased" in titles
    assert "Prompt changed" in titles
    assert "Different model" in titles
    assert "Additional tool call" in titles
    assert report.summary_counts.regressions >= 3
    assert report.impact.execution_time_ms > 0
    assert report.impact.cost > 0
    assert report.impact.tokens > 0
    assert any(
        finding.root_cause.affected_downstream_events
        for finding in report.findings
        if finding.evidence_event_ids
    )
    assert "Reduce prompt size." in report.recommendations
    assert report.trend.latency_direction == "up"


def test_regression_engine_detects_improvements_without_false_positive() -> None:
    report = RegressionEngine().compare(_target_trace(), _baseline_trace())

    assert any(finding.kind == "improvement" for finding in report.findings)
    assert any(finding.title == "Cost Decreased" for finding in report.findings)

    identical = RegressionEngine().compare(_baseline_trace(), _baseline_trace())
    assert identical.summary_counts.regressions == 0
    assert identical.summary_counts.behavior_changes == 0


def test_regression_history_resolution_and_trends(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    old = _baseline_trace(run_id="old")
    baseline = _baseline_trace(run_id="baseline-prod", name="prod baseline")
    target = _target_trace(run_id="target")
    for trace in (old, baseline, target):
        storage.save_run(trace.run)
        storage.bulk_insert_events(trace.events)

    engine = RegressionEngine(storage=storage)
    named = engine.compare_named_baseline("prod", "target")
    latest = engine.compare_to_latest("old")
    successful = engine.compare_to_last_successful("target")
    many = engine.compare_many("target", ("old", "baseline-prod"))
    trend = engine.trends(("old", "baseline-prod", "target"))

    assert named.baseline_run_id == "baseline-prod"
    assert latest.target_run_id == "target"
    assert successful.baseline_run_id == "baseline-prod"
    assert len(many) == 2
    assert trend.latency_direction == "up"
    engine.close()


def test_regression_rejects_missing_runs(tmp_path: Path) -> None:
    engine = RegressionEngine(storage=SQLiteStorage(tmp_path / "empty.sqlite"))

    with pytest.raises(RegressionError):
        engine.compare("missing", "also-missing")

    engine.close()


def test_regression_renderers_are_complete() -> None:
    report = RegressionEngine().compare(_baseline_trace(), _target_trace())

    assert "Regression analysis" in render_summary(report)
    assert "AgentReplay Regression Analysis" in render_markdown(report)
    assert "<!doctype html>" in render_html(report)
    assert "finding_id" in render_csv(report)
    assert "execution_graph_diff" in render_graph(report)
    assert json.loads(render_json(report))["summary_counts"]["regressions"] >= 1


def test_regression_cli_formats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    for trace in (_baseline_trace(), _target_trace()):
        storage.save_run(trace.run)
        storage.bulk_insert_events(trace.events)
    db_path = storage.db_path
    storage.close()

    assert "regression" in build_parser().format_help()
    assert (
        main(
            ["regression", "baseline", "target", "--summary", "--db-path", str(db_path)]
        )
        == 0
    )
    assert (
        main(["regression", "baseline", "target", "--json", "--db-path", str(db_path)])
        == 0
    )
    assert (
        main(["regression", "baseline", "target", "--csv", "--db-path", str(db_path)])
        == 0
    )
    assert (
        main(["regression", "baseline", "target", "--graph", "--db-path", str(db_path)])
        == 0
    )

    captured = capsys.readouterr()
    assert "Regression analysis baseline -> target" in captured.out
    assert "finding_id" in captured.out
    assert "execution_graph_diff" in captured.out


def test_regression_cli_rejects_multiple_formats(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    for trace in (_baseline_trace(), _target_trace()):
        storage.save_run(trace.run)
        storage.bulk_insert_events(trace.events)
    db_path = storage.db_path
    storage.close()

    exit_code = main(
        [
            "regression",
            "baseline",
            "target",
            "--json",
            "--summary",
            "--db-path",
            str(db_path),
        ]
    )

    assert exit_code == 1
    assert "Choose only one regression output format." in capsys.readouterr().out


def test_regression_plugin_extensions_are_isolated() -> None:
    def custom_rule(
        _baseline: TraceSnapshot,
        _target: TraceSnapshot,
    ) -> tuple[RegressionFinding, ...]:
        return (
            RegressionFinding(
                finding_id="custom-domain",
                kind="behavior_change",
                category="custom",
                severity="informational",
                title="Domain behavior changed",
                description="Domain-specific behavior changed.",
                location="domain.rule",
                baseline_value="old",
                target_value="new",
                metric_delta=None,
                root_cause=RootCause(
                    what_changed="Domain signal changed.",
                    where_changed="domain.rule",
                    when_changed="2026-01-01T00:00:00+00:00",
                    likely_cause="Custom rule detected a domain signal.",
                    affected_downstream_events=(),
                    confidence=0.9,
                ),
            ),
        )

    def analyzer(_report: RegressionReport) -> dict[str, int]:
        return {"domain_score": 1}

    def recommender(_report: RegressionReport) -> tuple[str, ...]:
        return ("Review domain-specific routing.",)

    engine = RegressionEngine(
        custom_rules={"domain": custom_rule},
        custom_analyzers={"domain": analyzer},
        custom_recommendations={"domain": recommender},
    )
    report = engine.compare(_baseline_trace(), _target_trace())

    assert any(finding.finding_id == "custom-domain" for finding in report.findings)
    assert report.plugin_results["domain"] == {"domain_score": 1}
    assert "Review domain-specific routing." in report.recommendations


def test_plugin_app_registers_regression_extensions() -> None:
    class Rule:
        def analyze(self, baseline: object, target: object) -> tuple[object, ...]:
            return (baseline, target)

    class Analyzer:
        def analyze(self, report: object) -> object:
            return report

    class Recommendation:
        def recommend(self, report: object) -> tuple[object, ...]:
            return (report,)

    app = PluginApp()
    app.activate("plugin", {})
    app.register_regression_rule("rule", Rule())
    app.register_regression_analyzer("analyzer", Analyzer())
    app.register_regression_recommendation("recommendation", Recommendation())

    kinds = {registration.kind for registration in app.registrations()}
    assert "regression_rule" in kinds
    assert "regression_analyzer" in kinds
    assert "regression_recommendation" in kinds


def _baseline_trace(
    *,
    run_id: str = "baseline",
    name: str = "baseline",
) -> TraceSnapshot:
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = RunRecord(
        run_id=run_id,
        name=name,
        status="completed",
        started_at=started,
        ended_at=started + timedelta(milliseconds=100),
        duration_ms=100.0,
        metadata={"env": "prod"},
        tags=("baseline",),
    )
    return TraceSnapshot(
        run=run,
        events=(
            _event("b1", run_id, 1, "run.started", duration_ms=1),
            _event("b2", run_id, 2, "prompt.user", prompt="hello", duration_ms=2),
            _event(
                "b3",
                run_id,
                3,
                "llm.request",
                parent_event_id="b2",
                model_name="gpt-small",
                provider_name="openai",
                tokens=100,
                cost=0.01,
                duration_ms=20,
            ),
            _event(
                "b4",
                run_id,
                4,
                "tool.started",
                parent_event_id="b3",
                tool_name="search",
                duration_ms=10,
            ),
            _event(
                "b5",
                run_id,
                5,
                "tool.finished",
                parent_event_id="b4",
                tool_name="search",
                duration_ms=10,
            ),
            _event("b6", run_id, 6, "memory.read", parent_event_id="b5", duration_ms=2),
            _event(
                "b7",
                run_id,
                7,
                "response.assistant",
                parent_event_id="b6",
                response="short answer",
                duration_ms=5,
            ),
        ),
    )


def _target_trace(*, run_id: str = "target") -> TraceSnapshot:
    started = datetime(2026, 1, 1, 12, 5, tzinfo=UTC)
    run = RunRecord(
        run_id=run_id,
        name="target",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(milliseconds=300),
        duration_ms=300.0,
        metadata={"env": "prod", "release": "new"},
        tags=(),
    )
    return TraceSnapshot(
        run=run,
        events=(
            _event("t1", run_id, 1, "run.started", duration_ms=1),
            _event(
                "t2",
                run_id,
                2,
                "prompt.user",
                prompt="hello with much more context",
                duration_ms=3,
            ),
            _event(
                "t3",
                run_id,
                3,
                "llm.request",
                parent_event_id="t2",
                model_name="gpt-large",
                provider_name="openai",
                tokens=300,
                cost=0.05,
                duration_ms=120,
            ),
            _event(
                "t4",
                run_id,
                4,
                "tool.started",
                parent_event_id="t3",
                tool_name="search",
                duration_ms=40,
            ),
            _event(
                "t5",
                run_id,
                5,
                "tool.finished",
                parent_event_id="t4",
                tool_name="search",
                duration_ms=40,
            ),
            _event(
                "t6",
                run_id,
                6,
                "tool.started",
                parent_event_id="t5",
                tool_name="calculator",
                duration_ms=35,
            ),
            _event(
                "t7", run_id, 7, "retry.recorded", parent_event_id="t6", duration_ms=1
            ),
            _event(
                "t8", run_id, 8, "memory.write", parent_event_id="t7", duration_ms=12
            ),
            _event(
                "t9",
                run_id,
                9,
                "response.assistant",
                parent_event_id="t8",
                response="longer answer",
                duration_ms=10,
            ),
        ),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    *,
    parent_event_id: str | None = None,
    prompt: str | None = None,
    response: str | None = None,
    tool_name: str | None = None,
    model_name: str | None = None,
    provider_name: str | None = None,
    tokens: int = 0,
    cost: float = 0.0,
    duration_ms: float = 1.0,
) -> EventRecord:
    payload: dict[str, JSONValue] = {
        "message": event_type,
        "total_tokens": tokens,
        "cost": cost,
    }
    if prompt is not None:
        payload["prompt"] = prompt
    if response is not None:
        payload["response"] = response
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if model_name is not None:
        payload["model_name"] = model_name
    if provider_name is not None:
        payload["provider_name"] = provider_name
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(seconds=sequence),
        duration_ms=duration_ms,
        metadata={},
        payload=payload,
    )
