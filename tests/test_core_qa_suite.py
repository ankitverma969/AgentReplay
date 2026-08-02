from __future__ import annotations

import asyncio
from collections.abc import Iterator, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from agentreplay import Recorder, SQLiteStorage
from agentreplay.config import load_settings
from agentreplay.core.events import (
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LATENCY_RECORDED,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    TOKEN_USAGE_RECORDED,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ConfigurationError
from agentreplay.storage import Pagination


@pytest.fixture
def recorder() -> Recorder:
    """Return a recorder configured for explicit run control."""
    return Recorder(auto_start=False)


@pytest.fixture
def storage(tmp_path: Path) -> Iterator[SQLiteStorage]:
    """Return an isolated SQLite storage backend."""
    backend = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    try:
        yield backend
    finally:
        backend.close()


def test_01_record_basic_run() -> None:
    with Recorder(name="basic", metadata={"suite": "qa"}) as active:
        active.user_prompt("hello")
        active.assistant_response("hi")

    trace = active.trace()

    assert trace.run.name == "basic"
    assert trace.run.status == "completed"
    assert trace.run.metadata["suite"] == "qa"
    assert [event.event_type for event in trace.events] == [
        RUN_STARTED,
        USER_PROMPT,
        ASSISTANT_RESPONSE,
        RUN_FINISHED,
    ]
    run_payload = cast(
        Mapping[str, object],
        TraceSnapshot(run=trace.run, events=trace.events).to_dict()["run"],
    )
    assert run_payload["status"] == "completed"


def test_02_record_nested_events() -> None:
    with (
        Recorder(name="nested") as active,
        active.span(CUSTOM_EVENT, payload={"name": "outer"}) as outer,
    ):
        inner = active.custom_event("inner")

    assert outer.event_id is not None
    assert inner.parent_event_id == outer.event_id
    outer_event = next(
        event for event in active.events() if event.event_id == outer.event_id
    )
    assert outer_event.duration_ms >= 0.0
    assert outer_event.metadata["status"] == "completed"


def test_03_record_async_events() -> None:
    async def run_agent() -> Recorder:
        async with Recorder(name="async") as active:
            active.user_prompt("async prompt")
            await asyncio.sleep(0)
            active.assistant_response("async response")
            return active

    active = asyncio.run(run_agent())

    assert [event.event_type for event in active.trace().events] == [
        RUN_STARTED,
        USER_PROMPT,
        ASSISTANT_RESPONSE,
        RUN_FINISHED,
    ]


def test_04_record_concurrent_events(recorder: Recorder) -> None:
    def record_one(index: int) -> str:
        with recorder.run(name=f"run-{index}"):
            run_id = recorder.current_run_id()
            assert run_id is not None
            recorder.custom_event("worker", payload={"index": index})
            return run_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        run_ids = tuple(executor.map(record_one, range(12)))

    assert len(set(run_ids)) == 12
    for run_id in run_ids:
        events = recorder.events(run_id)
        assert [event.event_type for event in events] == [
            RUN_STARTED,
            CUSTOM_EVENT,
            RUN_FINISHED,
        ]
        assert all(event.run_id == run_id for event in events)


@pytest.mark.parametrize("tool_name", ["search"])
def test_05_record_tool_events(tool_name: str) -> None:
    with Recorder(name="tools") as active:
        started = active.tool_started(tool_name, arguments={"q": "agentreplay"})
        finished = active.tool_finished(tool_name, result={"ok": True}, duration_ms=3.5)
        failed = active.tool_failed("calculator", ValueError("bad expression"))

    assert started.event_type == TOOL_STARTED
    assert finished.event_type == TOOL_FINISHED
    assert finished.duration_ms == 3.5
    assert finished.payload["result"] == {"ok": True}
    assert failed.event_type == TOOL_FAILED
    failed_exception = cast(Mapping[str, object], failed.payload["exception"])
    assert failed_exception["type"] == "ValueError"


def test_06_record_exception() -> None:
    active = Recorder(name="exception")

    with pytest.raises(RuntimeError, match="boom"), active:
        raise RuntimeError("boom")

    trace = active.trace()
    exception = next(
        event for event in trace.events if event.event_type == EXCEPTION_RAISED
    )
    exception_payload = cast(Mapping[str, object], exception.payload["exception"])
    assert trace.run.status == "failed"
    assert exception_payload["message"] == "boom"


def test_07_record_retry() -> None:
    with Recorder(name="retry") as active:
        retry = active.retry(attempt=2, reason="rate_limit", delay_ms=250.0)

    assert retry.event_type == RETRY_RECORDED
    assert retry.payload == {
        "attempt": 2,
        "reason": "rate_limit",
        "delay_ms": 250.0,
    }


def test_08_record_metadata() -> None:
    with Recorder(
        name="metadata", metadata={"owner": "qa"}, tags=("nightly",)
    ) as active:
        event = active.custom_event(
            "checkpoint",
            payload={"step": 1},
            metadata={"component": "planner"},
        )

    trace = active.trace()
    assert trace.run.metadata["owner"] == "qa"
    assert trace.run.tags == ("nightly",)
    assert event.metadata["component"] == "planner"
    with pytest.raises(TypeError):
        event.metadata["component"] = "mutated"  # type: ignore[index]


def test_09_record_token_usage() -> None:
    with Recorder(name="tokens") as active:
        event = active.token_usage(
            input_tokens=11,
            output_tokens=7,
            total_tokens=18,
        )

    assert event.event_type == TOKEN_USAGE_RECORDED
    assert event.payload["total_tokens"] == 18


def test_10_record_latency() -> None:
    with Recorder(name="latency") as active:
        event = active.latency(latency_ms=42.5, operation="tool.search")

    assert event.event_type == LATENCY_RECORDED
    assert event.duration_ms == 42.5
    assert event.payload["operation"] == "tool.search"


def test_11_save_to_sqlite(storage: SQLiteStorage) -> None:
    with Recorder(name="persist") as active:
        active.user_prompt("save me")

    run_id = active.last_run_id()
    assert run_id is not None
    active.save_to_storage(storage)

    assert storage.load_run(run_id) == active.trace().run
    assert len(storage.load_events(run_id)) == len(active.trace().events)


def test_12_load_from_sqlite(storage: SQLiteStorage) -> None:
    with Recorder(name="load") as active:
        active.user_prompt("load me")
        active.assistant_response("loaded")

    run_id = active.last_run_id()
    assert run_id is not None
    active.save_to_storage(storage)

    loaded = Recorder.load_from_storage(storage, run_id)

    assert loaded == active.trace()
    assert loaded.events[1].payload["prompt"] == "load me"


def test_13_update_run(storage: SQLiteStorage) -> None:
    with Recorder(name="before") as active:
        active.user_prompt("update")

    run = active.trace().run
    storage.save_run(run)
    storage.update_run(replace(run, name="after", metadata={"updated": True}))

    updated = storage.load_run(run.run_id)
    assert updated is not None
    assert updated.name == "after"
    assert updated.metadata["updated"] is True


def test_14_delete_run(storage: SQLiteStorage) -> None:
    with Recorder(name="delete") as active:
        active.user_prompt("delete")

    trace = active.trace()
    storage.save_run(trace.run)
    storage.bulk_insert_events(trace.events)
    storage.delete_run(trace.run.run_id)

    assert storage.load_run(trace.run.run_id) is None
    assert storage.load_events(trace.run.run_id) == ()


def test_15_bulk_insert(storage: SQLiteStorage) -> None:
    with Recorder(name="bulk") as active:
        for index in range(10):
            active.custom_event("item", payload={"index": index})

    trace = active.trace()
    storage.save_run(trace.run)

    assert storage.bulk_insert_events(trace.events) == len(trace.events)
    assert storage.load_events(trace.run.run_id) == trace.events


def test_16_pagination(storage: SQLiteStorage) -> None:
    created_ids: list[str] = []
    for index in range(5):
        with Recorder(name=f"page-{index}") as active:
            active.custom_event("page")
        trace = active.trace()
        storage.save_run(trace.run)
        storage.bulk_insert_events(trace.events)
        created_ids.append(trace.run.run_id)

    page = storage.list_runs(
        pagination=Pagination(limit=2, offset=1),
        sort_by="name",
        sort_direction="asc",
    )

    assert [run.name for run in page] == ["page-1", "page-2"]
    assert {run.run_id for run in page} <= set(created_ids)


def test_17_configuration_from_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text(
        "\n".join(
            [
                "enabled = true",
                'db_path = "qa.sqlite"',
                'log_level = "INFO"',
                "redaction_enabled = false",
            ],
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_file, environ={})

    assert settings.enabled is True
    assert settings.db_path == Path("qa.sqlite")
    assert settings.log_level == "INFO"
    assert settings.redaction_enabled is False
    assert settings.config_file == config_file


def test_18_configuration_from_env() -> None:
    settings = load_settings(
        environ={
            "AGENTREPLAY_ENABLED": "yes",
            "AGENTREPLAY_DB_PATH": "env.sqlite",
            "AGENTREPLAY_LOG_LEVEL": "debug",
            "AGENTREPLAY_PLUGINS_ENABLED": "false",
        },
    )

    assert settings.enabled is True
    assert settings.db_path == Path("env.sqlite")
    assert settings.log_level == "DEBUG"
    assert settings.plugins_enabled is False


def test_19_invalid_configuration() -> None:
    with pytest.raises(ConfigurationError, match="log level"):
        load_settings(environ={"AGENTREPLAY_LOG_LEVEL": "LOUD"})


def test_20_thread_safety(recorder: Recorder) -> None:
    run_id = recorder.start_run(name="thread-safe")
    barrier = Barrier(8)

    def record_many(worker: int) -> None:
        barrier.wait(timeout=5)
        for index in range(25):
            recorder.record_event(
                CUSTOM_EVENT,
                run_id=run_id,
                payload={"name": "thread-safe", "worker": worker, "index": index},
            )

    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(executor.map(record_many, range(8)))
    recorder.end_run(run_id)

    events = recorder.events(run_id)
    custom_events = [event for event in events if event.event_type == CUSTOM_EVENT]
    sequences = [event.sequence for event in events]
    loaded_indexes = {
        (cast(int, event.payload["worker"]), cast(int, event.payload["index"]))
        for event in custom_events
    }

    assert len(custom_events) == 200
    assert len(loaded_indexes) == 200
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
