from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentreplay import Recorder, SQLiteStorage
from agentreplay.core.events import (
    CUSTOM_EVENT,
    RUN_FINISHED,
    RUN_STARTED,
    USER_PROMPT,
    EventRecord,
)
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.exceptions import AgentReplayError, StorageError
from agentreplay.storage import EventQuery, Pagination, RunQuery
from agentreplay.storage.schema import SQLITE_SCHEMA_VERSION, schema_version
from agentreplay.types import JSONValue


def test_sqlite_storage_creates_and_loads_run(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1", metadata={"suite": "storage"}, tags=("fast", "sqlite"))

    storage.create_run(run)
    loaded = storage.load_run("run-1")

    assert loaded == run
    assert storage.db_path == tmp_path / "agentreplay.sqlite"
    storage.close()


def test_sqlite_storage_updates_run(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1", status="running")
    storage.create_run(run)

    updated = replace(
        run,
        status="completed",
        ended_at=run.started_at + timedelta(seconds=1),
        duration_ms=1000.0,
        metadata={"suite": "updated"},
        tags=("done",),
    )
    storage.update_run(updated)

    assert storage.load_run("run-1") == updated
    storage.close()


def test_sqlite_storage_save_run_upserts(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1", name="before")

    storage.save_run(run)
    storage.save_run(replace(run, name="after"))

    loaded = storage.load_run("run-1")
    assert loaded is not None
    assert loaded.name == "after"
    storage.close()


def test_sqlite_storage_rejects_duplicate_create(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1")

    storage.create_run(run)

    with pytest.raises(StorageError):
        storage.create_run(run)
    storage.close()


def test_sqlite_storage_searches_runs_with_filters(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    first = _run(
        "run-1",
        name="alpha agent",
        metadata={"framework": "manual"},
        tags=("nightly",),
    )
    second = _run(
        "run-2",
        name="beta agent",
        started_at=first.started_at + timedelta(seconds=5),
        metadata={"framework": "langgraph"},
        tags=("nightly", "graph"),
    )
    storage.save_run(first)
    storage.save_run(second)

    results = storage.search_runs(
        RunQuery(
            name_contains="agent",
            tags=("nightly", "graph"),
            metadata_equals={"framework": "langgraph"},
            sort_by="started_at",
            sort_direction="asc",
        ),
    )

    assert results == (second,)
    assert storage.list_runs(pagination=Pagination(limit=1))[0].run_id == "run-2"
    storage.close()


def test_sqlite_storage_saves_loads_filters_and_streams_events(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1")
    storage.save_run(run)
    root = _event("event-1", run.run_id, 1, RUN_STARTED, metadata={"phase": "root"})
    child = _event(
        "event-2",
        run.run_id,
        2,
        CUSTOM_EVENT,
        parent_event_id=root.event_id,
        metadata={"phase": "child"},
    )
    final = _event("event-3", run.run_id, 3, RUN_FINISHED)

    assert storage.bulk_insert_events((root, child, final)) == 3

    assert storage.load_events(run.run_id) == (root, child, final)
    assert storage.load_events(
        run.run_id,
        query=EventQuery(
            run_id=run.run_id,
            event_types=(CUSTOM_EVENT,),
            parent_event_id=root.event_id,
            metadata_equals={"phase": "child"},
        ),
    ) == (child,)
    assert storage.load_events(
        run.run_id,
        query=EventQuery(
            run_id=run.run_id,
            sort_by="sequence",
            sort_direction="desc",
            pagination=Pagination(limit=2),
        ),
    ) == (final, child)
    assert tuple(storage.stream_events(run.run_id, batch_size=1)) == (
        root,
        child,
        final,
    )
    storage.close()


def test_sqlite_storage_deletes_events_and_run(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = _run("run-1")
    storage.save_run(run)
    storage.bulk_insert_events(
        (
            _event("event-1", run.run_id, 1, RUN_STARTED),
            _event("event-2", run.run_id, 2, RUN_FINISHED),
        ),
    )

    assert storage.delete_events(run.run_id) == 2
    assert storage.load_events(run.run_id) == ()

    storage.bulk_insert_events((_event("event-3", run.run_id, 1, RUN_STARTED),))
    storage.delete_run(run.run_id)
    assert storage.load_run(run.run_id) is None
    assert storage.load_events(run.run_id) == ()
    storage.close()


def test_sqlite_storage_reports_schema_version(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")

    with storage._transaction_manager.connection() as connection:
        assert schema_version(connection) == SQLITE_SCHEMA_VERSION
    storage.close()


def test_recorder_can_save_and_load_trace_through_storage(tmp_path: Path) -> None:
    with Recorder(name="persisted") as recorder:
        recorder.user_prompt("hello")
        recorder.assistant_response("hi")
    run_id = recorder.last_run_id()
    assert run_id is not None

    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    recorder.save_to_storage(storage)
    trace = Recorder.load_from_storage(storage, run_id)

    assert trace.run.name == "persisted"
    assert [event.event_type for event in trace.events] == [
        RUN_STARTED,
        USER_PROMPT,
        "response.assistant",
        RUN_FINISHED,
    ]
    storage.close()


def test_recorder_load_from_storage_rejects_unknown_run(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")

    with pytest.raises(AgentReplayError):
        Recorder.load_from_storage(storage, "missing")
    storage.close()


def _run(
    run_id: str,
    *,
    name: str | None = "agent",
    status: RunStatus = "completed",
    started_at: datetime | None = None,
    metadata: dict[str, JSONValue] | None = None,
    tags: tuple[str, ...] = (),
) -> RunRecord:
    """Build a run record for storage tests."""
    started = (
        datetime(2026, 1, 1, 12, 0, tzinfo=UTC) if started_at is None else started_at
    )
    ended = started + timedelta(milliseconds=25) if status != "running" else None
    return RunRecord(
        run_id=run_id,
        name=name,
        status=status,
        started_at=started,
        ended_at=ended,
        duration_ms=0.0 if ended is None else 25.0,
        metadata={} if metadata is None else metadata,
        tags=tags,
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    *,
    parent_event_id: str | None = None,
    metadata: dict[str, JSONValue] | None = None,
) -> EventRecord:
    """Build an event record for storage tests."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, sequence, tzinfo=UTC),
        duration_ms=float(sequence),
        metadata={} if metadata is None else metadata,
        payload={"kind": event_type, "sequence": sequence},
    )
