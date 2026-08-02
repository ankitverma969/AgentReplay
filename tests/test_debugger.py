from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from agentreplay import DebuggerEngine, SQLiteStorage
from agentreplay.cli.main import main
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LLM_REQUEST,
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
from agentreplay.debugger.app import DebuggerApp
from agentreplay.debugger.models import DebuggerFilter, SearchQuery
from agentreplay.debugger.renderers import render_event_export
from agentreplay.debugger.session import DebuggerSession
from agentreplay.exceptions import DebuggerError
from agentreplay.types import JSONValue


def test_debugger_engine_loads_run_from_storage(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "debugger.sqlite")
    trace = _trace("run-debug")
    storage.save_run(trace.run)
    storage.bulk_insert_events(trace.events)

    session = DebuggerEngine(storage=storage).load("run-debug")
    entry = session.current_entry()

    assert session.run_id == "run-debug"
    assert entry is not None
    assert entry.event.event_type == RUN_STARTED
    storage.close()


def test_debugger_session_navigates_jumps_collapses_and_inspects() -> None:
    session = _session(_trace("run-debug"))

    assert session.next_event() is not None
    current = session.current_entry()
    assert current is not None
    assert current.event.event_type == USER_PROMPT
    assert session.previous_event() is not None
    jumped = session.jump_to_event("run-debug-event-4")
    assert jumped.event.event_type == TOOL_STARTED
    assert session.go_to_timestamp(jumped.event.timestamp).event.event_id == (
        "run-debug-event-4"
    )

    session.collapse_current()
    assert all(
        entry.event.parent_event_id != jumped.event.event_id
        for entry in session.visible_entries()
    )
    session.expand_current()
    assert any(
        entry.event.parent_event_id == jumped.event.event_id
        for entry in session.visible_entries()
    )

    inspection = session.inspect_current()
    assert inspection is not None
    assert inspection.children == ("run-debug-event-5",)


def test_debugger_search_supports_fields_and_regex() -> None:
    session = _session(_trace("run-debug"))

    prompt_matches = session.search(SearchQuery("refund policy", fields=("prompt",)))
    regex_matches = session.search(
        SearchQuery("gpt-[a-z]+", fields=("model",), regex=True),
    )

    assert prompt_matches[0].event_id == "run-debug-event-2"
    assert regex_matches[0].event_id == "run-debug-event-3"
    with pytest.raises(ValueError, match="Invalid debugger search regex"):
        session.search(SearchQuery("[", regex=True))


def test_debugger_filters_statistics_and_exports() -> None:
    session = _session(_trace("run-debug"))

    session.set_filter(DebuggerFilter(errors=True))
    assert [entry.event.event_type for entry in session.visible_entries()] == [
        EXCEPTION_RAISED
    ]
    stats = session.statistics()
    assert stats.total_events == 9
    assert stats.errors == 1
    assert stats.warnings == 1
    assert stats.retries == 1
    assert stats.total_tokens == 12
    assert stats.cost == 0.25
    assert stats.slowest_tool_event_id == "run-debug-event-5"

    session.jump_to_event("run-debug-event-7")
    entry = session.current_entry()
    assert entry is not None
    assert json.loads(render_event_export(entry, "json"))["event_id"] == (
        "run-debug-event-7"
    )
    assert "# Assistant Response" in render_event_export(entry, "markdown")
    assert "<html" in render_event_export(entry, "html")


def test_debugger_engine_loads_from_exported_json(tmp_path: Path) -> None:
    json_file = tmp_path / "trace.json"
    json_file.write_text(
        json.dumps({"trace": _trace("run-file").to_dict()}),
        encoding="utf-8",
    )

    session = DebuggerEngine().load_file(json_file)

    assert session.run_id == "run-file"


def test_debugger_missing_run_and_cli_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    storage = SQLiteStorage(tmp_path / "missing.sqlite")

    with pytest.raises(DebuggerError):
        DebuggerEngine(storage=storage).load("missing")

    exit_code = main(["debug", "--db-path", str(tmp_path / "missing.sqlite")])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RUN_ID is required" in captured.out
    storage.close()


def test_debugger_tui_keyboard_next_previous_and_help() -> None:
    async def run_app() -> None:
        app = DebuggerApp(session=_session(_trace("run-ui")))
        async with app.run_test() as pilot:
            await pilot.press("n")
            entry = app.session.current_entry()
            assert entry is not None
            assert entry.event.event_type == USER_PROMPT
            await pilot.press("p")
            previous = app.session.current_entry()
            assert previous is not None
            assert previous.event.event_type == RUN_STARTED
            await pilot.press("?")
            assert any("Keyboard Shortcuts" in log for log in app.session.logs)

    asyncio.run(run_app())


def test_debugger_large_search_and_stats_are_linear_enough() -> None:
    trace = _large_trace("run-large", count=100_000)
    session = _session(trace)

    started = perf_counter()
    matches = session.search(SearchQuery("needle", fields=("metadata",)))
    stats = session.statistics()
    elapsed = perf_counter() - started

    assert matches[-1].event_id == "run-large-event-99999"
    assert stats.total_events == 100_000
    assert elapsed < 5.0


def _session(trace: TraceSnapshot) -> DebuggerSession:
    """Create a debugger session from a trace."""
    return DebuggerEngine().load_trace(trace)


def _trace(run_id: str) -> TraceSnapshot:
    """Create a representative debugger trace."""
    events = (
        _event(f"{run_id}-event-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(
            f"{run_id}-event-2",
            run_id,
            2,
            USER_PROMPT,
            {"prompt": "explain refund policy"},
        ),
        _event(
            f"{run_id}-event-3",
            run_id,
            3,
            LLM_REQUEST,
            {
                "provider_name": "openai",
                "model_name": "gpt-demo",
                "token_usage": {"prompt_tokens": 5, "completion_tokens": 7},
                "cost": {"amount": 0.25, "currency": "USD"},
            },
        ),
        _event(
            f"{run_id}-event-4",
            run_id,
            4,
            TOOL_STARTED,
            {"tool_name": "lookup", "arguments": {"query": "refund"}},
        ),
        _event(
            f"{run_id}-event-5",
            run_id,
            5,
            TOOL_FINISHED,
            {"tool_name": "lookup", "result": "30 days"},
            parent_event_id=f"{run_id}-event-4",
            duration_ms=1200.0,
        ),
        _event(f"{run_id}-event-6", run_id, 6, RETRY_RECORDED, {"attempt": 1}),
        _event(
            f"{run_id}-event-7",
            run_id,
            7,
            ASSISTANT_RESPONSE,
            {"response": "You have 30 days."},
        ),
        _event(f"{run_id}-event-8", run_id, 8, WARNING_RAISED, {"message": "slow"}),
        _event(
            f"{run_id}-event-9",
            run_id,
            9,
            EXCEPTION_RAISED,
            {"exception": {"type": "RuntimeError", "message": "boom"}},
        ),
    )
    return TraceSnapshot(run=_run(run_id), events=events)


def _large_trace(run_id: str, *, count: int) -> TraceSnapshot:
    """Create a large trace for debugger performance tests."""
    events = tuple(
        _event(
            f"{run_id}-event-{index}",
            run_id,
            index,
            CUSTOM_EVENT,
            {"name": "checkpoint"},
            metadata={"marker": "needle" if index == count - 1 else "hay"},
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
        ended_at=started + timedelta(milliseconds=100),
        duration_ms=100.0,
        metadata={},
        tags=("debugger",),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, JSONValue],
    *,
    parent_event_id: str | None = None,
    duration_ms: float | None = None,
    metadata: dict[str, JSONValue] | None = None,
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
        duration_ms=float(sequence) if duration_ms is None else duration_ms,
        metadata={} if metadata is None else metadata,
        payload=payload,
    )
