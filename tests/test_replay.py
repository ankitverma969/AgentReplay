from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter

import pytest
from agentreplay import Recorder, ReplayEngine, SQLiteStorage
from agentreplay.cli.main import main
from agentreplay.constants import EVENT_SCHEMA_VERSION
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    LLM_REQUEST,
    LLM_RESPONSE,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    EventRecord,
)
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ReplayError


def test_replay_engine_loads_run_from_storage_and_renders_timeline(
    tmp_path: Path,
) -> None:
    storage = SQLiteStorage(tmp_path / "replay.sqlite")
    recorder = _record_sample(storage)
    run_id = recorder.last_run_id()
    assert run_id is not None
    engine = ReplayEngine(storage=storage)

    session = engine.load(run_id)

    assert session.run_id == run_id
    assert engine.render_timeline() == "\n".join(
        [
            "Run Started",
            "\u2193",
            "Prompt",
            "\u2193",
            "LLM Request",
            "\u2193",
            "LLM Response",
            "\u2193",
            "Assistant Response",
            "\u2193",
            "Run Finished",
        ],
    )
    storage.close()


def test_replay_playback_controls() -> None:
    engine = ReplayEngine(speed=1.0)
    engine.load_trace(_trace("run-1"))

    assert engine.pause().status == "paused"
    assert engine.step_forward() is not None
    first = engine.step_backward()
    assert first is not None
    assert first.label == "Run Started"
    engine.set_speed(2.0)
    emitted = engine.resume()
    assert emitted
    assert engine.controller is not None
    assert engine.controller.status == "completed"
    last = engine.step_backward()
    assert last is not None
    assert last.label == "Run Finished"
    assert engine.stop().status == "stopped"


def test_replay_seek_jump_to_event_and_timestamp() -> None:
    engine = ReplayEngine()
    session = engine.load_trace(_trace("run-1"))
    target = session.timeline.entries[2]

    assert engine.seek(target.event.event_id) == target
    assert engine.jump_to_event(target.event.event_id) == target
    assert engine.jump_to_timestamp(target.event.timestamp) == target

    with pytest.raises(ReplayError):
        engine.seek("missing")
    with pytest.raises(ReplayError):
        engine.jump_to_timestamp(target.event.timestamp + timedelta(days=1))


def test_replay_timeline_supports_nested_and_concurrent_events() -> None:
    timestamp = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    run = _run("run-1")
    root = _event("event-1", run.run_id, 1, RUN_STARTED, timestamp=timestamp)
    parent = _event("event-2", run.run_id, 2, TOOL_STARTED, timestamp=timestamp)
    child = _event(
        "event-3",
        run.run_id,
        3,
        TOOL_FINISHED,
        parent_event_id=parent.event_id,
        timestamp=timestamp,
    )
    engine = ReplayEngine()

    session = engine.load_trace(TraceSnapshot(run=run, events=(root, parent, child)))

    assert [entry.depth for entry in session.timeline.entries] == [0, 0, 1]
    assert all(entry.is_concurrent for entry in session.timeline.entries)
    assert session.timeline.entries[2].is_concurrent is True
    assert "  Tool Finished" in session.timeline.render()


def test_replay_loads_from_json_and_file(tmp_path: Path) -> None:
    trace = _trace("run-json")
    data = {"schema_version": EVENT_SCHEMA_VERSION, "trace": trace.to_dict()}
    json_text = json.dumps(data)
    json_file = tmp_path / "trace.json"
    json_file.write_text(json_text, encoding="utf-8")

    from_json = ReplayEngine().load_json(json_text)
    from_file = ReplayEngine().load_file(json_file)

    assert from_json.run_id == "run-json"
    assert from_file.run_id == "run-json"


def test_replay_handles_partial_recordings_and_missing_parents() -> None:
    run = _run("run-1", status="running")
    event = _event(
        "event-2",
        run.run_id,
        2,
        CUSTOM_EVENT,
        parent_event_id="missing-parent",
    )
    session = ReplayEngine().load_trace(TraceSnapshot(run=run, events=(event,)))

    assert "Run appears to be a partial recording." in session.warnings
    assert "Event sequence has gaps." in session.warnings
    assert "Some events reference missing parent events." in session.warnings
    assert session.timeline.entries[0].warnings == ("Missing parent event.",)


def test_replay_rejects_missing_corrupted_and_version_mismatched_data() -> None:
    engine = ReplayEngine()

    with pytest.raises(ReplayError):
        engine.play()
    with pytest.raises(ReplayError):
        engine.load_json("not json")
    with pytest.raises(ReplayError):
        engine.load_json({"schema_version": EVENT_SCHEMA_VERSION + 1, "trace": {}})
    with pytest.raises(ReplayError):
        engine.load_json({"trace": {"run": {}, "events": []}})


def test_replay_iterator_starts_at_controller_position() -> None:
    engine = ReplayEngine()
    session = engine.load_trace(_trace("run-1"))
    second = session.timeline.entries[1]
    engine.seek(second.event.event_id)

    entries = tuple(engine.iterator())

    assert entries[0] == second


def test_replay_cli_loads_from_database(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli.sqlite"
    storage = SQLiteStorage(db_path)
    recorder = _record_sample(storage)
    run_id = recorder.last_run_id()
    assert run_id is not None
    storage.close()

    exit_code = main(["replay", run_id, "--db-path", str(db_path), "--timeline"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Run Started" in captured.out
    assert "LLM Request" in captured.out


def test_replay_cli_loads_from_file_as_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace = _trace("run-file")
    json_file = tmp_path / "trace.json"
    json_file.write_text(json.dumps({"trace": trace.to_dict()}), encoding="utf-8")

    exit_code = main(["replay", "--file", str(json_file), "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out)["entries"][0]["label"] == "Run Started"


@pytest.mark.performance
def test_replay_timeline_build_is_linear_enough_for_large_traces() -> None:
    run = _run("run-large")
    events = tuple(
        _event(f"event-{index}", run.run_id, index, CUSTOM_EVENT)
        for index in range(1, 2501)
    )

    started = perf_counter()
    session = ReplayEngine().load_trace(TraceSnapshot(run=run, events=events))
    elapsed = perf_counter() - started

    assert len(session.timeline.entries) == 2500
    assert elapsed < 2.0


def _record_sample(storage: SQLiteStorage) -> Recorder:
    """Record and persist a sample trace."""
    with Recorder(name="sample") as recorder:
        recorder.user_prompt("hello")
        recorder.llm_request(provider_name="example", model_name="demo")
        recorder.llm_response(response="hi")
        recorder.assistant_response("hi")
    recorder.save_to_storage(storage)
    return recorder


def _trace(run_id: str) -> TraceSnapshot:
    """Create a sample trace."""
    run = _run(run_id)
    events = (
        _event("event-1", run_id, 1, RUN_STARTED),
        _event("event-2", run_id, 2, USER_PROMPT),
        _event("event-3", run_id, 3, LLM_REQUEST),
        _event("event-4", run_id, 4, LLM_RESPONSE),
        _event("event-5", run_id, 5, ASSISTANT_RESPONSE),
        _event("event-6", run_id, 6, RUN_FINISHED),
    )
    return TraceSnapshot(run=run, events=events)


def _run(run_id: str, *, status: RunStatus = "completed") -> RunRecord:
    """Create a run record for replay tests."""
    started_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    ended_at = None if status == "running" else started_at + timedelta(milliseconds=50)
    return RunRecord(
        run_id=run_id,
        name="agent",
        status=status,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=0.0 if ended_at is None else 50.0,
        metadata={},
        tags=(),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    *,
    parent_event_id: str | None = None,
    timestamp: datetime | None = None,
) -> EventRecord:
    """Create an event record for replay tests."""
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
        duration_ms=float(sequence),
        metadata={},
        payload={"event_type": event_type},
    )
