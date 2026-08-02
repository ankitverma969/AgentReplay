from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import cast

import pytest
from agentreplay import DiffEngine, RegressionEngine, ReplayEngine, SQLiteStorage
from agentreplay.constants import EVENT_SCHEMA_VERSION
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    COST_RECORDED,
    CUSTOM_EVENT,
    FUNCTION_CALL,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    TOKEN_USAGE_RECORDED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ReplayError
from agentreplay.regression.models import MetricDelta, RegressionReport
from agentreplay.types import JSONValue


@pytest.fixture
def replay_trace() -> TraceSnapshot:
    """Return a representative trace for replay tests."""
    return _trace("replay")


def test_01_replay_run(tmp_path: Path, replay_trace: TraceSnapshot) -> None:
    storage = SQLiteStorage(tmp_path / "replay.sqlite")
    try:
        storage.save_run(replay_trace.run)
        storage.bulk_insert_events(replay_trace.events)

        session = ReplayEngine(storage=storage).load(replay_trace.run.run_id)

        assert session.run_id == replay_trace.run.run_id
        assert session.timeline.entries[0].label == "Run Started"
        assert session.timeline.entries[-1].label == "Run Finished"
    finally:
        storage.close()


def test_02_replay_json(replay_trace: TraceSnapshot) -> None:
    payload = json.dumps(
        {"schema_version": EVENT_SCHEMA_VERSION, "trace": replay_trace.to_dict()}
    )

    session = ReplayEngine().load_json(payload)

    assert session.run_id == "replay"
    assert len(session.timeline.entries) == len(replay_trace.events)


def test_03_replay_file(tmp_path: Path, replay_trace: TraceSnapshot) -> None:
    path = tmp_path / "trace.json"
    path.write_text(json.dumps({"trace": replay_trace.to_dict()}), encoding="utf-8")

    session = ReplayEngine().load_file(path)

    assert session.trace == replay_trace
    assert "Prompt" in session.timeline.render()


def test_04_pause_replay(replay_trace: TraceSnapshot) -> None:
    engine = ReplayEngine()
    engine.load_trace(replay_trace)

    state = engine.pause()

    assert state.status == "paused"
    assert state.index == 0


def test_05_resume_replay(replay_trace: TraceSnapshot) -> None:
    engine = ReplayEngine()
    engine.load_trace(replay_trace)
    engine.pause()

    emitted = engine.resume()

    assert len(emitted) == len(replay_trace.events)
    assert engine.controller is not None
    assert engine.controller.status == "completed"


def test_06_step_replay(replay_trace: TraceSnapshot) -> None:
    engine = ReplayEngine()
    engine.load_trace(replay_trace)

    first = engine.step_forward()
    second = engine.step_forward()
    previous = engine.step_backward()

    assert first is not None
    assert first.event.event_type == RUN_STARTED
    assert second is not None
    assert previous == second


def test_07_seek_replay(replay_trace: TraceSnapshot) -> None:
    engine = ReplayEngine()
    session = engine.load_trace(replay_trace)
    target = session.timeline.entries[3]

    found = engine.seek(target.event.event_id)

    assert found == target
    assert engine.controller is not None
    assert engine.controller.index == 3


def test_08_replay_invalid_run(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "missing.sqlite")
    try:
        with pytest.raises(ReplayError, match="not found"):
            ReplayEngine(storage=storage).load("missing")
        with pytest.raises(ReplayError, match="invalid"):
            ReplayEngine().load_json("{not-json")
    finally:
        storage.close()


def test_09_diff_identical_runs() -> None:
    trace = _trace("same")

    result = DiffEngine().compare(trace, trace)

    assert result.has_changes is False
    assert result.stats.changed == 0
    assert result.summary() == "No differences found between same and same."


def test_10_diff_modified_runs() -> None:
    baseline = _trace("baseline", assistant_response="old")
    target = _trace("target", assistant_response="new", model_name="gpt-large")

    result = DiffEngine().compare(baseline, target)
    categories = {change.category for change in result.changes}

    assert {"assistant_response", "model"} <= categories
    assert result.stats.modified >= 2


def test_11_diff_missing_events() -> None:
    baseline = _trace("baseline")
    target = TraceSnapshot(run=_run("target"), events=baseline.events[:-2])

    result = DiffEngine().compare(baseline, target)

    assert any(change.change_type == "removed" for change in result.changes)
    assert result.stats.removed >= 1


def test_12_regression_latency() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", latency_ms=10.0),
        _trace("target", latency_ms=50.0),
    )

    assert _metric(report, "latency_average_ms").delta > 0
    assert _finding_titles(report, "Latency Average Ms Increased")


def test_13_regression_cost() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", cost=0.01),
        _trace("target", cost=0.20),
    )

    assert _metric(report, "cost").delta > 0
    assert report.impact.cost > 0


def test_14_regression_token() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", tokens=100),
        _trace("target", tokens=250),
    )

    assert _metric(report, "tokens").delta > 0
    assert report.impact.tokens > 0


def test_15_regression_model() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", model_name="gpt-small"),
        _trace("target", model_name="gpt-large"),
    )

    assert _finding_titles(report, "Different model")
    assert report.visualizations.model_comparison


def test_16_regression_tool() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", tool_name="search"),
        _trace("target", tool_name="calculator"),
    )

    assert any(finding.category == "tooling" for finding in report.findings)
    assert report.visualizations.tool_comparison


def test_17_regression_retry() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", retries=0),
        _trace("target", retries=3),
    )

    assert _metric(report, "retries").delta == 3
    assert any(finding.category == "infrastructure" for finding in report.findings)


def test_18_regression_memory() -> None:
    report = RegressionEngine().compare(
        _trace("baseline", memory_value="cached"),
        _trace("target", memory_value="reloaded", memory_writes=1),
    )

    assert _metric(report, "memory_operations").delta > 0
    assert any(finding.category == "memory" for finding in report.findings)


def test_19_regression_graph() -> None:
    baseline = _graph_trace(
        "baseline",
        parent_id="baseline-model",
        parent_type=LLM_REQUEST,
    )
    target = _graph_trace(
        "target",
        parent_id="target-tool-router",
        parent_type=FUNCTION_CALL,
    )

    report = RegressionEngine().compare(baseline, target)

    assert report.visualizations.execution_graph_diff
    assert _finding_titles(report, "Execution graph changed")


@pytest.mark.performance
def test_20_large_replay_performance() -> None:
    run = _run("large")
    events = tuple(
        _event(f"large-{index}", run.run_id, index, CUSTOM_EVENT, {"name": "tick"})
        for index in range(1, 5_001)
    )

    started = perf_counter()
    session = ReplayEngine().load_trace(TraceSnapshot(run=run, events=events))
    elapsed = perf_counter() - started

    assert len(session.timeline.entries) == 5_000
    assert elapsed < 5.0


def _trace(
    run_id: str,
    *,
    assistant_response: str = "answer",
    model_name: str = "gpt-small",
    tool_name: str = "search",
    latency_ms: float = 10.0,
    cost: float = 0.01,
    tokens: int = 100,
    retries: int = 0,
    memory_value: str = "cached",
    memory_writes: int = 0,
) -> TraceSnapshot:
    """Build a complete trace with knobs for diff and regression cases."""
    run = _run(run_id, duration_ms=latency_ms + 20.0)
    events: list[EventRecord] = [
        _event(f"{run_id}-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(f"{run_id}-2", run_id, 2, USER_PROMPT, {"prompt": "hello"}),
        _event(
            f"{run_id}-3",
            run_id,
            3,
            LLM_REQUEST,
            {"provider_name": "openai", "model_name": model_name},
            duration_ms=latency_ms,
        ),
        _event(
            f"{run_id}-4",
            run_id,
            4,
            LLM_RESPONSE,
            {
                "response": assistant_response,
                "model_name": model_name,
                "token_usage": {"total_tokens": tokens},
                "cost": {"amount": cost, "currency": "USD"},
                "latency_ms": latency_ms,
            },
            duration_ms=latency_ms,
        ),
        _event(
            f"{run_id}-5",
            run_id,
            5,
            TOOL_STARTED,
            {"tool_name": tool_name, "arguments": {"query": "hello"}},
        ),
        _event(
            f"{run_id}-6",
            run_id,
            6,
            TOOL_FINISHED,
            {"tool_name": tool_name, "result": "ok"},
            duration_ms=latency_ms / 2.0,
        ),
        _event(
            f"{run_id}-7",
            run_id,
            7,
            MEMORY_READ,
            {"key": "state", "value": memory_value},
        ),
        _event(
            f"{run_id}-8",
            run_id,
            8,
            ASSISTANT_RESPONSE,
            {"response": assistant_response},
        ),
        _event(
            f"{run_id}-9",
            run_id,
            9,
            TOKEN_USAGE_RECORDED,
            {"total_tokens": tokens},
        ),
        _event(f"{run_id}-10", run_id, 10, COST_RECORDED, {"amount": cost}),
        _event(
            f"{run_id}-11", run_id, 11, LATENCY_RECORDED, {"latency_ms": latency_ms}
        ),
    ]
    for retry in range(retries):
        events.append(
            _event(
                f"{run_id}-retry-{retry}",
                run_id,
                12 + retry,
                RETRY_RECORDED,
                {"attempt": retry + 1, "reason": "timeout"},
            )
        )
    for write in range(memory_writes):
        events.append(
            _event(
                f"{run_id}-memory-write-{write}",
                run_id,
                20 + write,
                MEMORY_WRITE,
                {"key": "state", "value": f"{memory_value}-{write}"},
            )
        )
    events.append(
        _event(f"{run_id}-finished", run_id, 100, RUN_FINISHED, {"status": "completed"})
    )
    return TraceSnapshot(run=run, events=tuple(events))


def _graph_trace(run_id: str, *, parent_id: str, parent_type: str) -> TraceSnapshot:
    """Build a trace with a parent-child graph relationship."""
    run = _run(run_id)
    start = _event(f"{run_id}-1", run_id, 1, RUN_STARTED, {"name": "graph"})
    parent_payload = (
        {"model_name": "gpt-small"}
        if parent_type == LLM_REQUEST
        else {"function_name": "tool_router"}
    )
    parent = _event(parent_id, run_id, 2, parent_type, parent_payload)
    child = _event(
        "shared-graph-child",
        run_id,
        3,
        TOOL_FINISHED,
        {"tool_name": "search", "result": "ok"},
        parent_event_id=parent.event_id,
    )
    finish = _event(f"{run_id}-4", run_id, 4, RUN_FINISHED, {"status": "completed"})
    return TraceSnapshot(run=run, events=(start, parent, child, finish))


def _run(run_id: str, *, duration_ms: float = 100.0) -> RunRecord:
    """Create a run record."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name=run_id,
        status="completed",
        started_at=started,
        ended_at=started + timedelta(milliseconds=duration_ms),
        duration_ms=duration_ms,
        metadata={},
        tags=(),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: Mapping[str, object],
    *,
    duration_ms: float = 0.0,
    parent_event_id: str | None = None,
) -> EventRecord:
    """Create an event record."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        + timedelta(milliseconds=sequence),
        duration_ms=duration_ms,
        metadata={},
        payload=cast(Mapping[str, JSONValue], payload),
    )


def _metric(report: RegressionReport, name: str) -> MetricDelta:
    """Return a metric delta by name."""
    return next(metric for metric in report.metric_deltas if metric.name == name)


def _finding_titles(report: RegressionReport, title: str) -> bool:
    """Return whether a report contains a finding title."""
    return any(finding.title == title for finding in report.findings)
