from __future__ import annotations

import asyncio
import sys
import types
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, cast

import pytest
from agentreplay import AgentReplay, OpenAIAgentsConfig, Recorder, record_agent
from agentreplay.adapters.openai_agents import OpenAIAgentsTraceProcessor, instrument
from agentreplay.cli.main import main
from agentreplay.core.events import (
    AGENT_STEP_FINISHED,
    AGENT_STEP_STARTED,
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    LLM_REQUEST,
    LLM_RESPONSE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    TOKEN_USAGE_RECORDED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
)
from agentreplay.storage import SQLiteStorage


def test_openai_config_loads_environment_values() -> None:
    config = OpenAIAgentsConfig.from_env(
        {
            "AGENTREPLAY_OPENAI_ENABLED": "true",
            "AGENTREPLAY_OPENAI_RECORD_PROMPTS": "false",
            "AGENTREPLAY_OPENAI_HIDE_PROMPTS": "true",
            "AGENTREPLAY_OPENAI_REDACT_API_KEYS": "true",
            "AGENTREPLAY_OPENAI_IGNORE_TOOLS": "secret,internal",
            "AGENTREPLAY_OPENAI_IGNORE_EVENTS": "guardrail",
            "AGENTREPLAY_OPENAI_SAMPLE_RATE": "0.5",
            "AGENTREPLAY_OPENAI_RUN_NAME": "sdk-run",
        },
    )

    assert config.enabled is True
    assert config.record_prompts is False
    assert config.hide_prompts is True
    assert config.ignore_tools == ("secret", "internal")
    assert config.ignore_events == ("guardrail",)
    assert config.sample_rate == 0.5
    assert config.run_name == "sdk-run"


def test_record_agent_decorator_records_sync_invocation(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "decorator.sqlite")

    @record_agent(recorder=recorder, storage=storage)
    def run_agent(prompt: str) -> str:
        return f"answer: {prompt}"

    assert run_agent("hello") == "answer: hello"

    trace = recorder.trace()
    assert trace.run.name is not None
    assert trace.run.name.endswith("run_agent")
    assert [event.event_type for event in trace.events] == [
        RUN_STARTED,
        USER_PROMPT,
        ASSISTANT_RESPONSE,
        RUN_FINISHED,
    ]
    assert storage.load_run(trace.run.run_id) is not None
    storage.close()


def test_record_agent_decorator_can_be_disabled(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "disabled.sqlite")

    @record_agent(
        recorder=recorder,
        storage=storage,
        config=OpenAIAgentsConfig(enabled=False),
    )
    def run_agent(prompt: str) -> str:
        return prompt

    assert run_agent("hello") == "hello"
    assert recorder.list_runs() == ()
    storage.close()


def test_record_agent_decorator_records_async_invocation(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "async.sqlite")

    @record_agent(recorder=recorder, storage=storage)
    async def run_agent(prompt: str) -> str:
        await asyncio.sleep(0)
        return prompt.upper()

    assert asyncio.run(run_agent("hello")) == "HELLO"
    assert recorder.trace().events[-2].event_type == ASSISTANT_RESPONSE
    storage.close()


def test_agentreplay_context_manager_records_and_persists(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "context.sqlite")
    manager = AgentReplay(storage=storage, auto_instrument=False)

    with manager:
        manager.recorder.user_prompt("hello")

    run_id = manager.last_run_id()
    assert run_id is not None
    assert storage.load_run(run_id) is not None
    storage.close()


def test_trace_processor_records_model_tool_handoff_guardrail_and_usage(
    tmp_path: Path,
) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "processor.sqlite")
    processor = OpenAIAgentsTraceProcessor(
        recorder=recorder,
        storage=storage,
        config=OpenAIAgentsConfig(metadata={"suite": "processor"}),
        serializer=recorder._serializer,
    )
    trace = _Trace("trace-1", "workflow")

    processor.on_trace_start(trace)
    processor.on_span_start(
        _Span(
            "gen-1",
            "trace-1",
            None,
            _SpanData(
                "generation",
                {
                    "input": [{"role": "user", "content": "hello sk-secret"}],
                    "output": [{"role": "assistant", "content": "hi"}],
                    "model": "gpt-test",
                    "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                },
            ),
        ),
    )
    processor.on_span_end(
        _Span(
            "gen-1",
            "trace-1",
            None,
            _SpanData(
                "generation",
                {
                    "output": [{"role": "assistant", "content": "hi"}],
                    "model": "gpt-test",
                    "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
                },
            ),
        ),
    )
    processor.on_span_start(
        _Span(
            "tool-1",
            "trace-1",
            None,
            _SpanData("function", {"name": "lookup", "input": {"q": "hello"}}),
        ),
    )
    processor.on_span_end(
        _Span(
            "tool-1",
            "trace-1",
            None,
            _SpanData("function", {"name": "lookup", "output": "result"}),
        ),
    )
    processor.on_span_start(
        _Span(
            "handoff-1",
            "trace-1",
            None,
            _SpanData("handoff", {"from_agent": "triage", "to_agent": "expert"}),
        ),
    )
    processor.on_span_end(
        _Span(
            "handoff-1",
            "trace-1",
            None,
            _SpanData("handoff", {"from_agent": "triage", "to_agent": "expert"}),
        ),
    )
    processor.on_span_start(
        _Span(
            "guardrail-1",
            "trace-1",
            None,
            _SpanData("guardrail", {"name": "safety", "triggered": False}),
        ),
    )
    processor.on_span_end(
        _Span(
            "guardrail-1",
            "trace-1",
            None,
            _SpanData("guardrail", {"name": "safety", "triggered": False}),
        ),
    )
    processor.on_span_start(
        _Span(
            "retry-1",
            "trace-1",
            None,
            _SpanData("retry", {"attempt": 2, "reason": "rate_limit"}),
        ),
    )
    processor.on_trace_end(trace)

    run_id = recorder.last_run_id()
    assert run_id is not None
    events = storage.load_events(run_id)
    event_types = [event.event_type for event in events]
    assert LLM_REQUEST in event_types
    assert LLM_RESPONSE in event_types
    assert TOOL_STARTED in event_types
    assert TOOL_FINISHED in event_types
    assert TOKEN_USAGE_RECORDED in event_types
    assert RETRY_RECORDED in event_types
    assert CUSTOM_EVENT in event_types
    prompt = next(event for event in events if event.event_type == USER_PROMPT)
    assert prompt.payload["prompt"] == "hello [redacted]"
    storage.close()


def test_trace_processor_honors_ignored_tools(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "ignored.sqlite")
    processor = OpenAIAgentsTraceProcessor(
        recorder=recorder,
        storage=storage,
        config=OpenAIAgentsConfig(ignore_tools=("secret_tool",)),
        serializer=recorder._serializer,
    )
    trace = _Trace("trace-ignored", "workflow")

    processor.on_trace_start(trace)
    processor.on_span_start(
        _Span(
            "tool",
            "trace-ignored",
            None,
            _SpanData("function", {"name": "secret_tool", "input": {}}),
        ),
    )
    processor.on_span_end(
        _Span(
            "tool",
            "trace-ignored",
            None,
            _SpanData("function", {"name": "secret_tool", "output": "hidden"}),
        ),
    )
    processor.on_trace_end(trace)

    assert TOOL_STARTED not in [event.event_type for event in recorder.events()]
    storage.close()


def test_attach_installs_hooks_and_preserves_existing_hooks(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "hooks.sqlite")
    recorder = Recorder(auto_start=False)
    manager = AgentReplay(recorder=recorder, storage=storage, auto_instrument=False)
    previous = _PreviousHooks()
    agent = _Agent("assistant", previous)
    tool = _Tool("lookup")

    manager.attach(agent)
    hooks = cast(Any, agent.hooks)
    asyncio.run(hooks.on_start(object(), agent))
    asyncio.run(
        hooks.on_tool_start(_ToolContext("lookup", {"q": "hi"}), agent, tool),
    )
    asyncio.run(
        hooks.on_tool_end(_ToolContext("lookup", {}), agent, tool, "ok"),
    )
    asyncio.run(hooks.on_handoff(object(), agent, _Agent("triage", None)))
    asyncio.run(hooks.on_end(object(), agent, "done"))

    event_types = [event.event_type for event in recorder.trace().events]
    assert previous.called is True
    assert AGENT_STEP_STARTED in event_types
    assert TOOL_STARTED in event_types
    assert TOOL_FINISHED in event_types
    assert CUSTOM_EVENT in event_types
    assert AGENT_STEP_FINISHED in event_types
    manager.detach(agent)
    assert agent.hooks is previous
    storage.close()


def test_instrument_registers_processor_with_mock_sdk(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registered: list[object] = []
    agents_module = types.ModuleType("agents")
    agents_module.__path__ = []
    agents_module.__spec__ = ModuleSpec("agents", loader=None, is_package=True)
    tracing_module = types.ModuleType("agents.tracing")
    tracing_module.__spec__ = ModuleSpec("agents.tracing", loader=None)
    dynamic_tracing_module = cast(Any, tracing_module)
    dynamic_tracing_module.add_trace_processor = registered.append
    monkeypatch.setitem(sys.modules, "agents", agents_module)
    monkeypatch.setitem(sys.modules, "agents.tracing", tracing_module)

    storage = SQLiteStorage(tmp_path / "instrument.sqlite")
    manager = instrument(storage=storage, recorder=Recorder(auto_start=False))

    assert manager.is_available() is True
    assert len(registered) == 1
    storage.close()


def test_real_openai_agents_sdk_import_smoke() -> None:
    pytest.importorskip("agents")

    assert AgentReplay(auto_instrument=False).is_available() is True


def test_cli_list_inspect_and_replay_latest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "latest.sqlite"
    storage = SQLiteStorage(db_path)
    recorder = Recorder(auto_start=False)
    run_id = recorder.start_run(name="latest")
    recorder.user_prompt("hello")
    recorder.end_run(run_id)
    recorder.save_to_storage(storage, run_id=run_id)
    storage.close()

    assert main(["list", "--db-path", str(db_path)]) == 0
    assert run_id in capsys.readouterr().out

    assert main(["inspect", "latest", "--db-path", str(db_path)]) == 0
    assert f"Run {run_id}" in capsys.readouterr().out

    assert main(["replay", "latest", "--db-path", str(db_path)]) == 0
    assert "Run Started" in capsys.readouterr().out


@dataclass(slots=True)
class _Trace:
    trace_id: str
    workflow_name: str
    group_id: str = "group"
    metadata: dict[str, str] | None = None


@dataclass(slots=True)
class _Span:
    span_id: str
    trace_id: str
    parent_id: str | None
    span_data: _SpanData


@dataclass(slots=True)
class _SpanData:
    type: str
    payload: dict[str, Any]

    def export(self) -> dict[str, Any]:
        return {"type": self.type, **self.payload}


class _PreviousHooks:
    def __init__(self) -> None:
        self.called = False

    async def on_start(self, _context: object, _agent: object) -> None:
        self.called = True


class _Agent:
    def __init__(self, name: str, hooks: Any | None) -> None:
        self.name = name
        self.hooks = hooks


class _Tool:
    def __init__(self, name: str) -> None:
        self.name = name


class _ToolContext:
    def __init__(self, tool_name: str, arguments: dict[str, str]) -> None:
        self.tool_name = tool_name
        self.tool_arguments = arguments
