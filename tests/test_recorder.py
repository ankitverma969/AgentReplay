from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from agentreplay import Recorder, record
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
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
)
from agentreplay.exceptions import AgentReplayError


def test_context_manager_records_run_lifecycle_and_events() -> None:
    with Recorder(name="agent", metadata={"case": "basic"}, tags=("test",)) as recorder:
        run_id = recorder.current_run_id()
        recorder.system_prompt("Be concise.")
        recorder.user_prompt("Hello")
        recorder.llm_request(provider_name="openai", model_name="gpt-test")
        recorder.llm_response(
            provider_name="openai",
            model_name="gpt-test",
            response={"content": "Hi"},
            token_usage={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            cost={"amount": 0.01, "currency": "USD"},
            latency_ms=12.5,
        )
        recorder.assistant_response("Hi")

    assert run_id is not None
    trace = recorder.trace(run_id)
    assert trace.run.status == "completed"
    assert trace.run.name == "agent"
    assert trace.run.duration_ms >= 0.0
    assert trace.run.metadata["case"] == "basic"

    event_types = [event.event_type for event in trace.events]
    assert event_types == [
        RUN_STARTED,
        SYSTEM_PROMPT,
        USER_PROMPT,
        LLM_REQUEST,
        LLM_RESPONSE,
        ASSISTANT_RESPONSE,
        RUN_FINISHED,
    ]
    assert trace.events[3].payload["model_name"] == "gpt-test"
    assert trace.events[4].payload["latency_ms"] == 12.5


def test_manual_api_records_required_event_categories() -> None:
    recorder = Recorder(auto_start=False)
    run_id = recorder.start_run(name="manual")

    recorder.tool_started("search", arguments={"query": "agent replay"})
    recorder.tool_finished("search", result=["result"], duration_ms=2.0)
    recorder.tool_failed("calc", ValueError("bad input"), duration_ms=1.0)
    recorder.function_call("rank", arguments={"limit": 3}, result=1)
    recorder.memory_read("conversation", value=["hello"])
    recorder.memory_write("conversation", value=["hello", "world"])
    recorder.custom_event("checkpoint", payload={"step": 1})
    recorder.warning("retrying slow tool", category="RuntimeWarning")
    recorder.retry(attempt=2, reason="timeout", delay_ms=100.0)
    recorder.token_usage(input_tokens=10, output_tokens=5, total_tokens=15)
    recorder.cost(amount=0.25, currency="USD")
    recorder.latency(latency_ms=33.3, operation="tool.search")
    recorder.end_run()

    event_types = [event.event_type for event in recorder.events(run_id)]
    assert event_types == [
        RUN_STARTED,
        TOOL_STARTED,
        TOOL_FINISHED,
        TOOL_FAILED,
        FUNCTION_CALL,
        MEMORY_READ,
        MEMORY_WRITE,
        CUSTOM_EVENT,
        WARNING_RAISED,
        RETRY_RECORDED,
        TOKEN_USAGE_RECORDED,
        COST_RECORDED,
        LATENCY_RECORDED,
        RUN_FINISHED,
    ]


def test_nested_span_assigns_parent_event_id() -> None:
    recorder = Recorder()

    with (
        recorder,
        recorder.span("agent.step.started", payload={"step": "outer"}) as span,
    ):
        child = recorder.custom_event("inside")

    assert span.event_id is not None
    assert child.parent_event_id == span.event_id
    span_event = next(
        event for event in recorder.events() if event.event_id == span.event_id
    )
    assert span_event.duration_ms >= 0.0
    assert span_event.metadata["status"] == "completed"


def test_context_manager_records_exception_and_preserves_it() -> None:
    recorder = Recorder()

    with pytest.raises(RuntimeError, match="boom"), recorder:
        raise RuntimeError("boom")

    trace = recorder.trace()
    assert trace.run.status == "failed"
    assert EXCEPTION_RAISED in [event.event_type for event in trace.events]


def test_recording_without_active_run_raises() -> None:
    recorder = Recorder(auto_start=False)

    with pytest.raises(AgentReplayError):
        recorder.user_prompt("missing run")


def test_recording_after_run_finished_raises() -> None:
    recorder = Recorder(auto_start=False)

    recorder.start_run()
    recorder.end_run()

    with pytest.raises(AgentReplayError):
        recorder.user_prompt("finished run")


def test_record_decorator_can_use_existing_recorder() -> None:
    recorder = Recorder(auto_start=False)

    @record(name="decorated", recorder=recorder)
    def agent(value: int) -> int:
        return value + 1

    assert agent(41) == 42
    assert recorder.list_runs()[0].name == "decorated"
    assert recorder.trace().run.status == "completed"


def test_async_context_records_events() -> None:
    async def run_agent() -> Recorder:
        async with Recorder(name="async-agent") as recorder:
            recorder.user_prompt("hello async")
            await asyncio.sleep(0)
            recorder.assistant_response("hello")
            return recorder

    recorder = asyncio.run(run_agent())

    trace = recorder.trace()
    assert trace.run.status == "completed"
    assert [event.event_type for event in trace.events] == [
        RUN_STARTED,
        USER_PROMPT,
        ASSISTANT_RESPONSE,
        RUN_FINISHED,
    ]


def test_concurrent_threaded_runs_keep_context_isolated() -> None:
    recorder = Recorder(auto_start=False)

    def run_agent(index: int) -> str:
        with recorder.run(name=f"agent-{index}"):
            run_id = recorder.current_run_id()
            recorder.custom_event("thread", payload={"index": index})
            assert run_id is not None
            return run_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        run_ids = tuple(executor.map(run_agent, range(8)))

    assert len(set(run_ids)) == 8
    for run_id in run_ids:
        events = recorder.events(run_id)
        assert events[0].event_type == RUN_STARTED
        assert events[-1].event_type == RUN_FINISHED
        assert all(event.run_id == run_id for event in events)


def test_async_decorator_records_into_existing_recorder() -> None:
    recorder = Recorder(auto_start=False)

    @record(name="async-decorated", recorder=recorder)
    async def agent() -> str:
        await asyncio.sleep(0)
        return "done"

    assert asyncio.run(agent()) == "done"
    assert recorder.trace().run.name == "async-decorated"
