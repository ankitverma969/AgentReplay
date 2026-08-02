from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from agentreplay import DiffEngine, SQLiteStorage
from agentreplay.cli.main import main
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    COST_RECORDED,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    FUNCTION_CALL,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    SYSTEM_PROMPT,
    TOKEN_USAGE_RECORDED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.core.traces import TraceSnapshot
from agentreplay.diff.renderers import render_console, render_html, render_markdown
from agentreplay.exceptions import DiffError
from agentreplay.types import JSONValue


def test_diff_engine_reports_no_changes_for_identical_recordings() -> None:
    trace = _trace("left")

    result = DiffEngine().compare(trace, trace)

    assert result.has_changes is False
    assert result.stats.changed == 0
    assert result.summary() == "No differences found between left and left."


def test_diff_engine_highlights_prompt_model_tool_and_response_changes() -> None:
    left = _trace("left")
    right = _trace(
        "right",
        user_prompt="hello there",
        model_name="gpt-next",
        tool_name="search_docs",
        tool_result="new result",
        assistant_response="new answer",
    )

    result = DiffEngine().compare(left, right)
    descriptions = {change.description for change in result.changes}
    categories = {change.category for change in result.changes}

    assert "Prompt changed." in descriptions
    assert "Model changed." in descriptions
    assert "Different tool selected." in descriptions
    assert "Tool output changed." in descriptions
    assert "Final assistant response changed." in descriptions
    assert {"prompt", "model", "tool_calls", "tool_outputs"} <= categories
    assert result.stats.modified >= 5


def test_diff_engine_reports_added_and_removed_events() -> None:
    left = _trace("left")
    right = replace(
        _trace("right"),
        events=(
            *_trace("right").events[:-1],
            _event("event-extra", "right", 8, WARNING_RAISED, {"message": "careful"}),
            _trace("right").events[-1],
        ),
    )

    added = DiffEngine().compare(left, right)
    removed = DiffEngine().compare(right, left)

    assert any(change.change_type == "added" for change in added.changes)
    assert any(change.change_type == "removed" for change in removed.changes)
    assert any(change.category == "warnings" for change in added.changes)


def test_diff_engine_compares_metadata_latency_usage_cost_memory_and_errors() -> None:
    left = _diagnostic_trace("left")
    right = _diagnostic_trace(
        "right",
        metadata={"suite": "nightly", "attempt": 2},
        latency_ms=80.0,
        total_tokens=99,
        cost_amount=0.25,
        memory_value="after",
        exception_message="boom",
    )

    result = DiffEngine().compare(left, right)
    categories = {change.category for change in result.changes}

    assert {
        "custom_metadata",
        "latency",
        "token_usage",
        "cost",
        "memory",
        "errors",
    } <= categories
    assert result.changes_by_severity("high")


def test_diff_engine_compares_execution_graph_parent_changes() -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    left_parent = _event("parent-1", "left", 1, TOOL_STARTED, {"tool_name": "lookup"})
    left_child = _event(
        "child-1",
        "left",
        2,
        TOOL_FINISHED,
        {"tool_name": "lookup", "result": "ok"},
        parent_event_id=left_parent.event_id,
    )
    right_parent = _event(
        "parent-2",
        "right",
        1,
        FUNCTION_CALL,
        {"function_name": "lookup"},
        timestamp=timestamp,
    )
    right_child = _event(
        "child-1",
        "right",
        2,
        TOOL_FINISHED,
        {"tool_name": "lookup", "result": "ok"},
        parent_event_id=right_parent.event_id,
        timestamp=timestamp + timedelta(milliseconds=1),
    )

    result = DiffEngine().compare(
        TraceSnapshot(run=_run("left"), events=(left_parent, left_child)),
        TraceSnapshot(run=_run("right"), events=(right_parent, right_child)),
    )

    assert any(change.category == "execution_graph" for change in result.changes)


def test_diff_cli_renders_json_markdown_html_and_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "diff.sqlite"
    storage = SQLiteStorage(db_path)
    left = _trace("left")
    right = _trace("right", assistant_response="different")
    storage.save_run(left.run)
    storage.bulk_insert_events(left.events)
    storage.save_run(right.run)
    storage.bulk_insert_events(right.events)
    storage.close()

    assert main(["diff", "left", "right", "--db-path", str(db_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["stats"]["modified"] >= 1

    assert main(["diff", "left", "right", "--db-path", str(db_path), "--markdown"]) == 0
    assert "# AgentReplay Diff" in capsys.readouterr().out

    assert main(["diff", "left", "right", "--db-path", str(db_path), "--html"]) == 0
    assert "<html" in capsys.readouterr().out

    assert main(["diff", "left", "right", "--db-path", str(db_path), "--summary"]) == 0
    assert "differences between left and right" in capsys.readouterr().out


def test_diff_renderers_include_verbose_values() -> None:
    result = DiffEngine().compare(_trace("left"), _trace("right", user_prompt="new"))

    assert "old=" in render_console(result, verbose=True)
    assert "Old:" in render_markdown(result, verbose=True)
    assert "<pre>" in render_html(result, verbose=True)


def test_diff_engine_handles_missing_runs_gracefully(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "missing.sqlite")
    engine = DiffEngine(storage=storage)

    with pytest.raises(DiffError):
        engine.compare("missing-left", "missing-right")
    storage.close()


def test_diff_engine_warns_for_partial_and_empty_recordings() -> None:
    partial = TraceSnapshot(run=_run("partial", status="running"), events=())
    complete = _trace("complete")

    result = DiffEngine().compare(partial, complete)

    assert "At least one run appears to be a partial recording." in result.warnings
    assert "At least one run has no recorded events." in result.warnings


def test_diff_engine_compares_large_runs_efficiently() -> None:
    left = _large_trace("left", count=3000)
    right = _large_trace("right", count=3000, changed_index=1499)

    started = perf_counter()
    result = DiffEngine().compare(left, right)
    elapsed = perf_counter() - started

    assert result.stats.modified == 1
    assert elapsed < 2.0


def _trace(
    run_id: str,
    *,
    user_prompt: str = "hello",
    system_prompt: str = "be concise",
    model_name: str = "gpt-demo",
    provider_name: str = "openai",
    tool_name: str = "lookup",
    tool_result: str = "old result",
    assistant_response: str = "old answer",
) -> TraceSnapshot:
    """Create a representative agent trace for diff tests."""
    events = (
        _event(f"{run_id}-event-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(
            f"{run_id}-event-2",
            run_id,
            2,
            SYSTEM_PROMPT,
            {"prompt": system_prompt},
        ),
        _event(f"{run_id}-event-3", run_id, 3, USER_PROMPT, {"prompt": user_prompt}),
        _event(
            f"{run_id}-event-4",
            run_id,
            4,
            LLM_REQUEST,
            {"provider_name": provider_name, "model_name": model_name},
        ),
        _event(
            f"{run_id}-event-5",
            run_id,
            5,
            TOOL_STARTED,
            {"tool_name": tool_name, "arguments": {"query": user_prompt}},
        ),
        _event(
            f"{run_id}-event-6",
            run_id,
            6,
            TOOL_FINISHED,
            {"tool_name": tool_name, "result": tool_result},
            duration_ms=10.0,
        ),
        _event(
            f"{run_id}-event-7",
            run_id,
            7,
            ASSISTANT_RESPONSE,
            {"response": assistant_response},
        ),
        _event(f"{run_id}-event-8", run_id, 8, RUN_FINISHED, {"status": "completed"}),
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _diagnostic_trace(
    run_id: str,
    *,
    metadata: dict[str, JSONValue] | None = None,
    latency_ms: float = 40.0,
    total_tokens: int = 42,
    cost_amount: float = 0.1,
    memory_value: str = "before",
    exception_message: str = "nope",
) -> TraceSnapshot:
    """Create a trace that covers diagnostic event categories."""
    events = (
        _event(
            f"{run_id}-diag-1",
            run_id,
            1,
            LLM_RESPONSE,
            {
                "response": "ok",
                "latency_ms": latency_ms,
                "token_usage": {"total_tokens": total_tokens},
                "cost": {"amount": cost_amount, "currency": "USD"},
            },
        ),
        _event(
            f"{run_id}-diag-2",
            run_id,
            2,
            TOKEN_USAGE_RECORDED,
            {"total_tokens": total_tokens},
        ),
        _event(f"{run_id}-diag-3", run_id, 3, COST_RECORDED, {"amount": cost_amount}),
        _event(
            f"{run_id}-diag-4",
            run_id,
            4,
            LATENCY_RECORDED,
            {"latency_ms": latency_ms},
        ),
        _event(
            f"{run_id}-diag-5",
            run_id,
            5,
            MEMORY_READ,
            {"key": "state", "value": memory_value},
        ),
        _event(
            f"{run_id}-diag-6",
            run_id,
            6,
            MEMORY_WRITE,
            {"key": "state", "value": memory_value},
        ),
        _event(
            f"{run_id}-diag-7",
            run_id,
            7,
            FUNCTION_CALL,
            {"function_name": "score", "result": 1},
        ),
        _event(
            f"{run_id}-diag-8",
            run_id,
            8,
            RETRY_RECORDED,
            {"attempt": 1, "reason": "rate"},
        ),
        _event(f"{run_id}-diag-9", run_id, 9, WARNING_RAISED, {"message": "slow"}),
        _event(
            f"{run_id}-diag-10",
            run_id,
            10,
            EXCEPTION_RAISED,
            {"exception": {"type": "ValueError", "message": exception_message}},
        ),
    )
    return TraceSnapshot(
        run=_run(run_id, metadata={} if metadata is None else metadata),
        events=events,
    )


def _large_trace(
    run_id: str,
    *,
    count: int,
    changed_index: int | None = None,
) -> TraceSnapshot:
    """Create a large trace for diff performance tests."""
    events = tuple(
        _event(
            f"{run_id}-large-{index}",
            run_id,
            index + 1,
            CUSTOM_EVENT,
            {
                "name": "checkpoint",
                "value": "changed" if index == changed_index else "same",
            },
        )
        for index in range(count)
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _run(
    run_id: str,
    *,
    status: RunStatus = "completed",
    metadata: dict[str, JSONValue] | None = None,
) -> RunRecord:
    """Create a run record."""
    started_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    ended_at = None if status == "running" else started_at + timedelta(milliseconds=80)
    return RunRecord(
        run_id=run_id,
        name="agent",
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=0.0 if ended_at is None else 80.0,
        metadata={} if metadata is None else metadata,
        tags=("diff",),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, JSONValue],
    *,
    parent_event_id: str | None = None,
    timestamp: datetime | None = None,
    duration_ms: float | None = None,
) -> EventRecord:
    """Create an event record."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=(
            datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(milliseconds=sequence)
            if timestamp is None
            else timestamp
        ),
        duration_ms=float(sequence) if duration_ms is None else duration_ms,
        metadata={},
        payload=payload,
    )
