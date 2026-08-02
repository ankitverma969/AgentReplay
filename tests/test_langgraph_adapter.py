from __future__ import annotations

import asyncio
import json
import sys
import types
from collections.abc import AsyncIterator, Iterator, Mapping
from dataclasses import dataclass
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any, cast

import pytest
from agentreplay import Recorder
from agentreplay.cli.main import main
from agentreplay.core.events import (
    AGENT_STEP_FINISHED,
    AGENT_STEP_STARTED,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    RETRY_RECORDED,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
)
from agentreplay.langgraph import AgentReplay as LangGraphAgentReplay
from agentreplay.langgraph import LangGraphConfig, export_trace, instrument
from agentreplay.storage import SQLiteStorage


def test_langgraph_config_loads_environment_values() -> None:
    config = LangGraphConfig.from_env(
        {
            "AGENTREPLAY_LANGGRAPH_ENABLED": "true",
            "AGENTREPLAY_LANGGRAPH_RECORD_INPUTS": "false",
            "AGENTREPLAY_LANGGRAPH_RECORD_OUTPUTS": "true",
            "AGENTREPLAY_LANGGRAPH_HIDE_STATE": "true",
            "AGENTREPLAY_LANGGRAPH_REDACT_SECRETS": "false",
            "AGENTREPLAY_LANGGRAPH_IGNORE_NODES": "secret,internal",
            "AGENTREPLAY_LANGGRAPH_IGNORE_EVENTS": "on_debug,on_chain_stream",
            "AGENTREPLAY_LANGGRAPH_SAMPLE_RATE": "0.25",
            "AGENTREPLAY_LANGGRAPH_RUN_NAME": "graph-run",
            "AGENTREPLAY_LANGGRAPH_STREAM_MODES": "updates,debug",
        },
    )

    assert config.enabled is True
    assert config.record_inputs is False
    assert config.record_outputs is True
    assert config.hide_state is True
    assert config.redact_secrets is False
    assert config.ignore_nodes == ("secret", "internal")
    assert config.ignore_events == ("on_debug", "on_chain_stream")
    assert config.sample_rate == 0.25
    assert config.run_name == "graph-run"
    assert config.stream_modes == ("updates", "debug")


def test_instrument_records_sync_graph_execution(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "langgraph.sqlite")
    graph = instrument(
        _FakeGraph(),
        recorder=recorder,
        storage=storage,
        config=LangGraphConfig(metadata={"suite": "langgraph"}),
    )

    result = graph.invoke(input={"question": "hello sk-secret"})

    assert result == {"answer": "done", "router": {"route": "tool"}}
    trace = recorder.trace()
    assert trace.run.metadata["source"] == "langgraph"
    assert trace.run.metadata["dag"] == {
        "nodes": [
            {"id": "router", "label": "router"},
            {"id": "tool", "label": "tool"},
        ],
        "edges": [{"source": "router", "target": "tool"}],
    }
    event_types = [event.event_type for event in trace.events]
    assert AGENT_STEP_STARTED in event_types
    assert AGENT_STEP_FINISHED in event_types
    assert TOOL_STARTED in event_types
    assert TOOL_FINISHED in event_types
    assert LLM_REQUEST in event_types
    assert LLM_RESPONSE in event_types
    assert RETRY_RECORDED in event_types
    assert LATENCY_RECORDED in event_types
    assert storage.load_run(trace.run.run_id) is not None
    assert "sk-secret" not in json.dumps(trace.to_dict())
    storage.close()


def test_instrument_records_async_graph_execution(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "async.sqlite")
    graph = instrument(_FakeGraph(), recorder=recorder, storage=storage)

    result = asyncio.run(graph.ainvoke({"question": "hello"}))

    assert result == {"answer": "async", "model": "mock"}
    assert storage.load_run(recorder.trace().run.run_id) is not None
    storage.close()


def test_stream_records_chunks_parallel_branches_and_interrupts(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "stream.sqlite")
    graph = instrument(_FakeGraph(), recorder=recorder, storage=storage)

    chunks = list(graph.stream({"question": "hello"}))

    assert chunks == [
        {"left": {"value": 1}, "right": {"value": 2}},
        {"__interrupt__": {"reason": "approval"}},
    ]
    payload_names = [
        event.payload.get("name")
        for event in recorder.trace().events
        if event.event_type == CUSTOM_EVENT
    ]
    assert "langgraph.parallel" in payload_names
    assert "langgraph.interrupt" in payload_names
    assert "langgraph.stream.chunk" in payload_names
    storage.close()


def test_astream_events_records_checkpoints_and_branches(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "events.sqlite")
    graph = instrument(_FakeGraph(), recorder=recorder, storage=storage)

    events = asyncio.run(_collect_events(graph.astream_events({"question": "hello"})))

    assert [event["event"] for event in events] == [
        "on_chain_start",
        "on_checkpoint",
        "on_chain_stream",
    ]
    payload_names = [
        event.payload.get("name")
        for event in recorder.trace().events
        if event.event_type == CUSTOM_EVENT
    ]
    assert "langgraph.checkpoint" in payload_names
    assert "langgraph.branch" in payload_names
    storage.close()


def test_callback_records_tool_failure_and_node_exception(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "errors.sqlite")
    graph = instrument(_FailingGraph(), recorder=recorder, storage=storage)

    with pytest.raises(RuntimeError, match="boom"):
        graph.invoke({"question": "explode"})

    event_types = [event.event_type for event in recorder.trace().events]
    assert TOOL_FAILED in event_types
    assert EXCEPTION_RAISED in event_types
    storage.close()


def test_manager_attach_reuses_wrapper_and_context_persists(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "manager.sqlite")
    manager = LangGraphAgentReplay(
        recorder=Recorder(auto_start=False),
        storage=storage,
    )
    raw_graph = _FakeGraph()

    assert manager.attach(raw_graph) is manager.attach(raw_graph)
    with manager:
        manager.recorder.custom_event("manual.langgraph.marker")

    run_id = manager.last_run_id()
    assert run_id is not None
    assert storage.load_run(run_id) is not None
    storage.close()


def test_export_trace_renders_json_markdown_and_html(tmp_path: Path) -> None:
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(tmp_path / "export.sqlite")
    graph = instrument(_FakeGraph(), recorder=recorder, storage=storage)
    graph.invoke({"question": "hello"})
    trace = recorder.trace()

    assert json.loads(export_trace(trace))["run"]["run_id"] == trace.run.run_id
    assert "# AgentReplay LangGraph Run" in export_trace(
        trace,
        export_format="markdown",
    )
    assert "<html" in export_trace(trace, export_format="html")
    storage.close()


def test_cli_export_supports_latest_and_formats(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "cli-export.sqlite"
    recorder = Recorder(auto_start=False)
    storage = SQLiteStorage(db_path)
    graph = instrument(_FakeGraph(), recorder=recorder, storage=storage)
    graph.invoke({"question": "hello"})
    storage.close()

    assert main(["export", "latest", "--db-path", str(db_path), "--json"]) == 0
    assert "langgraph.graph.started" in capsys.readouterr().out

    assert main(["export", "latest", "--db-path", str(db_path), "--markdown"]) == 0
    assert "# AgentReplay LangGraph Run" in capsys.readouterr().out

    output_path = tmp_path / "run.html"
    assert (
        main(
            [
                "export",
                "latest",
                "--db-path",
                str(db_path),
                "--html",
                "--output",
                str(output_path),
            ],
        )
        == 0
    )
    assert output_path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_real_langgraph_import_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    langgraph_module = types.ModuleType("langgraph")
    langgraph_module.__spec__ = ModuleSpec("langgraph", loader=None)
    monkeypatch.setitem(sys.modules, "langgraph", langgraph_module)

    assert LangGraphAgentReplay().is_available() is True


async def _collect_events(source: AsyncIterator[object]) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async for event in source:
        events.append(cast(dict[str, object], event))
    return events


def _callback(config: Mapping[str, object] | None) -> object:
    callbacks = cast(Mapping[str, list[object]], config or {}).get("callbacks", [])
    return callbacks[-1]


class _FakeGraph:
    name = "fake-langgraph"
    checkpointer = "memory"

    def get_graph(self) -> _DrawableGraph:
        return _DrawableGraph()

    def invoke(
        self,
        input_value: object,
        *,
        config: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> dict[str, object]:
        callback = _callback(config)
        _emit_success_callbacks(callback, input_value)
        return {"answer": "done", "router": {"route": "tool"}}

    async def ainvoke(
        self,
        input_value: object,
        *,
        config: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> dict[str, object]:
        await asyncio.sleep(0)
        callback = _callback(config)
        _emit_success_callbacks(callback, input_value)
        return {"answer": "async", "model": "mock"}

    def stream(
        self,
        input_value: object,
        *,
        config: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> Iterator[dict[str, object]]:
        callback = _callback(config)
        _emit_success_callbacks(callback, input_value)
        yield {"left": {"value": 1}, "right": {"value": 2}}
        yield {"__interrupt__": {"reason": "approval"}}

    async def astream_events(
        self,
        input_value: object,
        *,
        config: Mapping[str, object] | None = None,
        version: str = "v2",
        **_kwargs: object,
    ) -> AsyncIterator[dict[str, object]]:
        callback = _callback(config)
        _emit_success_callbacks(callback, input_value)
        yield {"event": "on_chain_start", "name": "branch:router", "version": version}
        yield {"event": "on_checkpoint", "name": "checkpoint"}
        yield {"event": "on_chain_stream", "name": "router", "data": {"chunk": 1}}


class _FailingGraph:
    name = "failing-langgraph"

    def invoke(
        self,
        input_value: object,
        *,
        config: Mapping[str, object] | None = None,
        **_kwargs: object,
    ) -> None:
        callback = _callback(config)
        dynamic_callback = cast(Any, callback)
        dynamic_callback.on_chain_start(
            {"name": "explode"},
            input_value,
            run_id="node-error",
            name="explode",
        )
        dynamic_callback.on_tool_start(
            {"name": "bad_tool"},
            "payload",
            run_id="tool-error",
            parent_run_id="node-error",
        )
        dynamic_callback.on_tool_error(
            RuntimeError("tool failed"),
            run_id="tool-error",
        )
        dynamic_callback.on_chain_error(RuntimeError("boom"), run_id="node-error")
        raise RuntimeError("boom")


@dataclass(frozen=True, slots=True)
class _DrawableNode:
    name: str


@dataclass(frozen=True, slots=True)
class _DrawableEdge:
    source: str
    target: str


class _DrawableGraph:
    nodes = {
        "router": _DrawableNode("router"),
        "tool": _DrawableNode("tool"),
    }
    edges = [_DrawableEdge("router", "tool")]


@dataclass(frozen=True, slots=True)
class _RetryState:
    attempt_number: int = 2
    outcome: str = "rate-limit"
    idle_for: float = 0.5


@dataclass(frozen=True, slots=True)
class _LLMResponse:
    usage: dict[str, int]


def _emit_success_callbacks(callback: object, input_value: object) -> None:
    dynamic_callback = cast(Any, callback)
    dynamic_callback.on_chain_start(
        {"name": "router"},
        input_value,
        run_id="node-router",
        name="router",
    )
    dynamic_callback.on_llm_start(
        {"model": "mock-model"},
        ["System: answer briefly", "User: hello"],
        run_id="llm-router",
        parent_run_id="node-router",
    )
    dynamic_callback.on_llm_end(
        _LLMResponse({"input_tokens": 4, "output_tokens": 2, "total_tokens": 6}),
        run_id="llm-router",
    )
    dynamic_callback.on_retry(_RetryState(), run_id="node-router")
    dynamic_callback.on_tool_start(
        {"name": "lookup"},
        "hello",
        run_id="tool-lookup",
        parent_run_id="node-router",
    )
    dynamic_callback.on_tool_end("lookup result", run_id="tool-lookup")
    dynamic_callback.on_chain_end(
        {"router": {"route": "tool"}},
        run_id="node-router",
    )
