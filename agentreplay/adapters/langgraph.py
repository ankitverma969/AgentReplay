"""LangGraph integration for AgentReplay."""

from __future__ import annotations

import importlib.util
import os
import random
from collections.abc import AsyncIterator, Callable, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal, cast

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
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import AdapterError
from agentreplay.recording import Recorder
from agentreplay.recording.serializers import EventSerializer
from agentreplay.storage import SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue, Metadata

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_HIDDEN = "[hidden]"
_REDACTED = "[redacted]"
_SECRET_MARKERS = ("api_key", "apikey", "authorization", "bearer", "token", "secret")


@dataclass(frozen=True, slots=True)
class LangGraphConfig:
    """Configuration for the LangGraph adapter."""

    enabled: bool = True
    record_inputs: bool = True
    record_outputs: bool = True
    hide_state: bool = False
    redact_secrets: bool = True
    ignore_nodes: tuple[str, ...] = ()
    ignore_events: tuple[str, ...] = ()
    sample_rate: float = 1.0
    metadata: Metadata = field(default_factory=dict)
    run_name: str | None = None
    stream_modes: tuple[str, ...] = (
        "updates",
        "values",
        "messages",
        "custom",
        "checkpoints",
        "tasks",
        "debug",
    )

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.sample_rate <= 1.0:
            msg = "LangGraph sampling rate must be between 0.0 and 1.0."
            raise ValueError(msg)
        object.__setattr__(self, "ignore_nodes", tuple(self.ignore_nodes))
        object.__setattr__(self, "ignore_events", tuple(self.ignore_events))
        object.__setattr__(self, "stream_modes", tuple(self.stream_modes))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        overrides: Mapping[str, object] | None = None,
    ) -> LangGraphConfig:
        """Load adapter settings from environment variables."""
        env = os.environ if environ is None else environ
        values: dict[str, object] = {}
        _put_env_bool(values, env, "AGENTREPLAY_LANGGRAPH_ENABLED", "enabled")
        _put_env_bool(
            values,
            env,
            "AGENTREPLAY_LANGGRAPH_RECORD_INPUTS",
            "record_inputs",
        )
        _put_env_bool(
            values,
            env,
            "AGENTREPLAY_LANGGRAPH_RECORD_OUTPUTS",
            "record_outputs",
        )
        _put_env_bool(values, env, "AGENTREPLAY_LANGGRAPH_HIDE_STATE", "hide_state")
        _put_env_bool(
            values,
            env,
            "AGENTREPLAY_LANGGRAPH_REDACT_SECRETS",
            "redact_secrets",
        )
        if "AGENTREPLAY_LANGGRAPH_IGNORE_NODES" in env:
            values["ignore_nodes"] = _split_csv(
                env["AGENTREPLAY_LANGGRAPH_IGNORE_NODES"],
            )
        if "AGENTREPLAY_LANGGRAPH_IGNORE_EVENTS" in env:
            values["ignore_events"] = _split_csv(
                env["AGENTREPLAY_LANGGRAPH_IGNORE_EVENTS"],
            )
        if "AGENTREPLAY_LANGGRAPH_SAMPLE_RATE" in env:
            values["sample_rate"] = float(env["AGENTREPLAY_LANGGRAPH_SAMPLE_RATE"])
        if "AGENTREPLAY_LANGGRAPH_RUN_NAME" in env:
            values["run_name"] = env["AGENTREPLAY_LANGGRAPH_RUN_NAME"]
        if "AGENTREPLAY_LANGGRAPH_STREAM_MODES" in env:
            values["stream_modes"] = _split_csv(
                env["AGENTREPLAY_LANGGRAPH_STREAM_MODES"],
            )
        if overrides is not None:
            values.update(overrides)
        return cls(**cast(Any, values))


class AgentReplay:
    """LangGraph integration manager."""

    name = "langgraph"
    framework = "langgraph"
    version_support = "LangGraph compiled graphs and Runnable-compatible graphs"

    def __init__(
        self,
        *,
        recorder: Recorder | None = None,
        storage: StorageBackend | None = None,
        config: LangGraphConfig | None = None,
    ) -> None:
        """Create a LangGraph integration manager."""
        self.config = LangGraphConfig.from_env() if config is None else config
        self.recorder = Recorder(auto_start=False) if recorder is None else recorder
        self.storage = SQLiteStorage() if storage is None else storage
        self._serializer = EventSerializer()
        self._attached: dict[int, LangGraphInstrumentedGraph] = {}
        self._entered_run_id: str | None = None

    def __enter__(self) -> AgentReplay:
        """Enter a coarse LangGraph recording context."""
        if self.config.enabled and self._entered_run_id is None:
            self._entered_run_id = self.recorder.start_run(
                name=self.config.run_name or "langgraph",
                metadata=self._metadata({"source": "langgraph.context"}),
            )
            self._record_custom(
                self._entered_run_id,
                "langgraph.context.started",
                {"message": "LangGraph context entered."},
            )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> None:
        """Leave a LangGraph recording context."""
        if self._entered_run_id is None:
            return
        if exc is not None:
            self.recorder.record_event(
                EXCEPTION_RAISED,
                run_id=self._entered_run_id,
                parent_event_id=None,
                payload={"exception": self._serializer.serialize_exception(exc)},
                metadata=self._metadata({"source": "langgraph.context"}),
            )
        self._record_custom(
            self._entered_run_id,
            "langgraph.context.finished",
            {"status": "failed" if exc is not None else "completed"},
        )
        self.recorder.end_run(
            self._entered_run_id,
            status="failed" if exc is not None else "completed",
        )
        self.recorder.save_to_storage(self.storage, run_id=self._entered_run_id)
        self._entered_run_id = None

    def is_available(self) -> bool:
        """Return whether LangGraph is importable."""
        return importlib.util.find_spec("langgraph") is not None

    def attach(self, graph: object) -> LangGraphInstrumentedGraph:
        """Return an instrumented wrapper for a LangGraph graph."""
        graph_id = id(graph)
        attached = self._attached.get(graph_id)
        if attached is not None:
            return attached
        wrapped = LangGraphInstrumentedGraph(
            graph,
            recorder=self.recorder,
            storage=self.storage,
            config=self.config,
            serializer=self._serializer,
        )
        self._attached[graph_id] = wrapped
        return wrapped

    def trace(self, run_id: str | None = None) -> TraceSnapshot:
        """Return a recorded trace from the underlying recorder."""
        return self.recorder.trace(run_id)

    def last_run_id(self) -> str | None:
        """Return the most recent run id."""
        return self.recorder.last_run_id()

    def _record_custom(
        self,
        run_id: str,
        name: str,
        payload: Mapping[str, object],
    ) -> None:
        """Record a LangGraph custom event."""
        self.recorder.record_event(
            CUSTOM_EVENT,
            run_id=run_id,
            parent_event_id=None,
            payload={"name": name, **dict(payload)},
            metadata=self._metadata(),
        )

    def _metadata(self, values: Mapping[str, object] | None = None) -> Metadata:
        """Return merged adapter metadata."""
        merged: dict[str, object] = dict(self.config.metadata)
        if values is not None:
            merged.update(values)
        return _clean_mapping(merged, config=self.config)


class LangGraphInstrumentedGraph:
    """Proxy object that records LangGraph Runnable execution."""

    def __init__(
        self,
        graph: object,
        *,
        recorder: Recorder,
        storage: StorageBackend,
        config: LangGraphConfig,
        serializer: EventSerializer,
    ) -> None:
        """Create an instrumented graph proxy."""
        self._graph = graph
        self._recorder = recorder
        self._storage = storage
        self._config = config
        self._serializer = serializer

    @property
    def graph(self) -> object:
        """Return the wrapped graph."""
        return self._graph

    def __getattr__(self, name: str) -> object:
        """Delegate unknown attributes to the wrapped graph."""
        return getattr(self._graph, name)

    def invoke(
        self,
        input_value: object = None,
        config: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> object:
        """Invoke a synchronous graph execution while recording it."""
        resolved_input = _resolve_input(input_value, kwargs)
        with self._run("invoke", resolved_input, config, kwargs) as state:
            try:
                result = cast(Any, self._graph).invoke(
                    resolved_input,
                    config=_merge_config(config, state.callback),
                    **kwargs,
                )
            except BaseException as exc:
                state.record_exception(exc)
                raise
            state.record_output(result)
            return result

    async def ainvoke(
        self,
        input_value: object = None,
        config: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> object:
        """Invoke an asynchronous graph execution while recording it."""
        resolved_input = _resolve_input(input_value, kwargs)
        async with self._arun("ainvoke", resolved_input, config, kwargs) as state:
            try:
                result = await cast(Any, self._graph).ainvoke(
                    resolved_input,
                    config=_merge_config(config, state.callback),
                    **kwargs,
                )
            except BaseException as exc:
                state.record_exception(exc)
                raise
            state.record_output(result)
            return result

    def stream(
        self,
        input_value: object = None,
        config: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> Iterator[object]:
        """Stream a synchronous graph execution while recording chunks."""
        resolved_input = _resolve_input(input_value, kwargs)
        with self._run("stream", resolved_input, config, kwargs) as state:
            try:
                for chunk in cast(Any, self._graph).stream(
                    resolved_input,
                    config=_merge_config(config, state.callback),
                    **kwargs,
                ):
                    state.record_stream_chunk(chunk)
                    yield chunk
            except BaseException as exc:
                state.record_exception(exc)
                raise

    async def astream(
        self,
        input_value: object = None,
        config: Mapping[str, object] | None = None,
        **kwargs: object,
    ) -> AsyncIterator[object]:
        """Stream an asynchronous graph execution while recording chunks."""
        resolved_input = _resolve_input(input_value, kwargs)
        async with self._arun("astream", resolved_input, config, kwargs) as state:
            try:
                async for chunk in cast(Any, self._graph).astream(
                    resolved_input,
                    config=_merge_config(config, state.callback),
                    **kwargs,
                ):
                    state.record_stream_chunk(chunk)
                    yield chunk
            except BaseException as exc:
                state.record_exception(exc)
                raise

    async def astream_events(
        self,
        input_value: object = None,
        config: Mapping[str, object] | None = None,
        *,
        version: str = "v2",
        **kwargs: object,
    ) -> AsyncIterator[object]:
        """Stream LangChain/LangGraph events while recording them."""
        resolved_input = _resolve_input(input_value, kwargs)
        async with self._arun(
            "astream_events",
            resolved_input,
            config,
            kwargs,
        ) as state:
            try:
                async for event in cast(Any, self._graph).astream_events(
                    resolved_input,
                    config=_merge_config(config, state.callback),
                    version=version,
                    **kwargs,
                ):
                    state.record_stream_event(event)
                    yield event
            except BaseException as exc:
                state.record_exception(exc)
                raise

    def export_run(
        self,
        run_id: str | None = None,
        *,
        export_format: str = "json",
    ) -> str:
        """Export a recorded LangGraph execution."""
        trace = self._recorder.trace(run_id)
        return export_trace(trace, export_format=export_format)

    def _run(
        self,
        mode: str,
        input_value: object,
        config: Mapping[str, object] | None,
        kwargs: Mapping[str, object],
    ) -> _RunState:
        """Create a synchronous run state context."""
        return _RunState(
            graph=self._graph,
            recorder=self._recorder,
            storage=self._storage,
            config=self._config,
            serializer=self._serializer,
            mode=mode,
            input_value=input_value,
            runnable_config=config,
            kwargs=kwargs,
        )

    def _arun(
        self,
        mode: str,
        input_value: object,
        config: Mapping[str, object] | None,
        kwargs: Mapping[str, object],
    ) -> _AsyncRunState:
        """Create an asynchronous run state context."""
        return _AsyncRunState(self._run(mode, input_value, config, kwargs))


class _RunState(AbstractContextManager["_RunState"]):
    """Run-scoped state for one instrumented graph execution."""

    def __init__(
        self,
        *,
        graph: object,
        recorder: Recorder,
        storage: StorageBackend,
        config: LangGraphConfig,
        serializer: EventSerializer,
        mode: str,
        input_value: object,
        runnable_config: Mapping[str, object] | None,
        kwargs: Mapping[str, object],
    ) -> None:
        """Create graph execution state."""
        self.graph = graph
        self.recorder = recorder
        self.storage = storage
        self.config = config
        self.serializer = serializer
        self.mode = mode
        self.input_value = input_value
        self.runnable_config = runnable_config
        self.kwargs = kwargs
        self.run_id: str | None = None
        self.callback = LangGraphCallbackHandler(
            recorder=recorder,
            config=config,
            serializer=serializer,
            run_id_provider=lambda: self.run_id,
        )
        self._started_at = 0.0

    def __enter__(self) -> _RunState:
        """Start a graph run."""
        if not self.config.enabled or not _is_sampled(self.config):
            return self
        self._started_at = perf_counter()
        self.run_id = self.recorder.start_run(
            name=self.config.run_name or _graph_name(self.graph),
            metadata=_metadata(
                self.config,
                {
                    "source": "langgraph",
                    "mode": self.mode,
                    "dag": _graph_dag(self.graph),
                    "configurable": _configurable(self.runnable_config),
                    "kwargs": _clean_value(dict(self.kwargs), config=self.config),
                },
            ),
        )
        self.record_custom(
            "langgraph.graph.started",
            {
                "mode": self.mode,
                "input": (
                    _clean_value(self.input_value, config=self.config)
                    if self.config.record_inputs
                    else _HIDDEN
                ),
                "checkpointer": _checkpointer_metadata(self.graph),
                "resume": _resume_payload(self.input_value),
            },
        )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> None:
        """Finish a graph run."""
        if self.run_id is None:
            return
        duration_ms = max((perf_counter() - self._started_at) * 1000.0, 0.0)
        status: LiteralRunStatus = "failed" if exc is not None else "completed"
        self.record_custom(
            "langgraph.graph.finished",
            {"mode": self.mode, "status": status},
            duration_ms=duration_ms,
        )
        self.recorder.record_event(
            LATENCY_RECORDED,
            run_id=self.run_id,
            parent_event_id=None,
            payload={"latency_ms": duration_ms, "operation": "langgraph.graph"},
            metadata=_metadata(self.config),
            duration_ms=duration_ms,
        )
        self.recorder.end_run(self.run_id, status=status)
        self.recorder.save_to_storage(self.storage, run_id=self.run_id)

    def record_output(self, output: object) -> None:
        """Record a graph output state."""
        if self.run_id is None or not self.config.record_outputs:
            return
        self.record_custom(
            "langgraph.graph.output",
            {"output": _clean_value(output, config=self.config)},
        )
        self._record_state_updates(output)

    def record_stream_chunk(self, chunk: object) -> None:
        """Record one stream chunk."""
        if self.run_id is None:
            return
        payload = _stream_payload(chunk, config=self.config)
        self.record_custom("langgraph.stream.chunk", payload)
        self._record_state_updates(chunk)
        self._record_parallel(chunk)
        self._record_interrupt(chunk)

    def record_stream_event(self, event: object) -> None:
        """Record one Runnable stream event."""
        if self.run_id is None:
            return
        event_mapping = _as_mapping(event)
        event_type = str(event_mapping.get("event", "stream_event"))
        if event_type in self.config.ignore_events:
            return
        name = str(event_mapping.get("name", "langgraph"))
        payload = _clean_value(event_mapping, config=self.config)
        self.record_custom(f"langgraph.event.{event_type}", {"event": payload})
        if "checkpoint" in event_type or "checkpoint" in name.lower():
            self.record_custom("langgraph.checkpoint", {"event": payload})
        if "interrupt" in event_type or _contains_key(event_mapping, "__interrupt__"):
            self.record_custom("langgraph.interrupt", {"event": payload})
        if "branch" in name.lower():
            self.record_custom("langgraph.branch", {"event": payload})

    def record_exception(self, exc: BaseException) -> None:
        """Record a graph execution exception."""
        if self.run_id is None:
            return
        self.recorder.record_event(
            EXCEPTION_RAISED,
            run_id=self.run_id,
            parent_event_id=None,
            payload={"exception": self.serializer.serialize_exception(exc)},
            metadata=_metadata(self.config, {"source": "langgraph"}),
        )

    def record_custom(
        self,
        name: str,
        payload: Mapping[str, object],
        *,
        duration_ms: float = 0.0,
        parent_event_id: str | None = None,
    ) -> None:
        """Record a LangGraph custom event."""
        if self.run_id is None:
            return
        self.recorder.record_event(
            CUSTOM_EVENT,
            run_id=self.run_id,
            parent_event_id=parent_event_id,
            payload={"name": name, **dict(payload)},
            metadata=_metadata(self.config),
            duration_ms=duration_ms,
        )

    def _record_state_updates(self, value: object) -> None:
        """Record state updates from graph output or stream chunks."""
        if self.run_id is None:
            return
        updates = _state_updates(value)
        for node, update in updates:
            if node in self.config.ignore_nodes:
                continue
            self.record_custom(
                "langgraph.state.update",
                {"node": node, "update": _clean_value(update, config=self.config)},
            )

    def _record_parallel(self, value: object) -> None:
        """Record likely parallel branch output."""
        branches = _parallel_branches(value)
        if branches:
            self.record_custom("langgraph.parallel", {"branches": list(branches)})

    def _record_interrupt(self, value: object) -> None:
        """Record interrupt and resume signals when visible in payloads."""
        interrupt = _interrupt_payload(value)
        if interrupt is not None:
            self.record_custom("langgraph.interrupt", {"interrupt": interrupt})


class _AsyncRunState(AbstractAsyncContextManager[_RunState]):
    """Async wrapper around a synchronous run state."""

    def __init__(self, state: _RunState) -> None:
        """Create an async run state."""
        self._state = state

    async def __aenter__(self) -> _RunState:
        """Enter the wrapped run state."""
        return self._state.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Exit the wrapped run state."""
        self._state.__exit__(exc_type, exc, traceback)


class LangGraphCallbackHandler:
    """LangChain-compatible callback handler for LangGraph graph execution."""

    def __init__(
        self,
        *,
        recorder: Recorder,
        config: LangGraphConfig,
        serializer: EventSerializer,
        run_id_provider: CallableRunIdProvider,
    ) -> None:
        """Create a callback handler."""
        self._recorder = recorder
        self._config = config
        self._serializer = serializer
        self._run_id_provider = run_id_provider
        self._event_by_run_id: dict[str, str] = {}
        self._started_at_by_run_id: dict[str, float] = {}

    def on_chain_start(
        self,
        serialized: Mapping[str, object] | None,
        inputs: object,
        *,
        run_id: object,
        parent_run_id: object | None = None,
        tags: Sequence[str] | None = None,
        metadata: Mapping[str, object] | None = None,
        name: str | None = None,
        **_kwargs: object,
    ) -> None:
        """Record a graph or node start callback."""
        self._record_node_start(
            "chain",
            _callback_name(serialized, name),
            inputs,
            run_id=run_id,
            parent_run_id=parent_run_id,
            tags=tags,
            metadata=metadata,
        )

    def on_chain_end(
        self,
        outputs: object,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a graph or node end callback."""
        self._record_node_end("chain", outputs, run_id=run_id)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a graph or node error callback."""
        self._record_error(error, run_id=run_id)

    def on_tool_start(
        self,
        serialized: Mapping[str, object] | None,
        input_str: str,
        *,
        run_id: object,
        parent_run_id: object | None = None,
        name: str | None = None,
        **_kwargs: object,
    ) -> None:
        """Record a tool node start callback."""
        run = self._current_run_id()
        if run is None:
            return
        tool_name = _callback_name(serialized, name)
        if tool_name in self._config.ignore_nodes:
            return
        event = self._recorder.record_event(
            TOOL_STARTED,
            run_id=run,
            parent_event_id=self._parent_event_id(parent_run_id),
            payload={
                "tool_name": tool_name,
                "arguments": (
                    _clean_value(input_str, config=self._config)
                    if self._config.record_inputs
                    else _HIDDEN
                ),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
        )
        self._remember(run_id, event.event_id)

    def on_tool_end(
        self,
        output: object,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a tool node end callback."""
        run = self._current_run_id()
        if run is None:
            return
        parent = self._event_by_run_id.pop(str(run_id), None)
        duration_ms = self._duration(run_id)
        self._recorder.record_event(
            TOOL_FINISHED,
            run_id=run,
            parent_event_id=parent,
            payload={
                "tool_name": "langgraph_tool",
                "result": (
                    _clean_value(output, config=self._config)
                    if self._config.record_outputs
                    else _HIDDEN
                ),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
            duration_ms=duration_ms,
        )

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a tool node error callback."""
        run = self._current_run_id()
        if run is None:
            return
        parent = self._event_by_run_id.pop(str(run_id), None)
        self._recorder.record_event(
            TOOL_FAILED,
            run_id=run,
            parent_event_id=parent,
            payload={
                "tool_name": "langgraph_tool",
                "exception": self._serializer.serialize_exception(error),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
            duration_ms=self._duration(run_id),
        )

    def on_llm_start(
        self,
        serialized: Mapping[str, object] | None,
        prompts: list[str],
        *,
        run_id: object,
        parent_run_id: object | None = None,
        **_kwargs: object,
    ) -> None:
        """Record an LLM node start callback."""
        run = self._current_run_id()
        if run is None:
            return
        event = self._recorder.record_event(
            LLM_REQUEST,
            run_id=run,
            parent_event_id=self._parent_event_id(parent_run_id),
            payload={
                "provider_name": "langgraph",
                "model_name": _model_name(serialized),
                "prompts": (
                    _clean_value(prompts, config=self._config)
                    if self._config.record_inputs
                    else _HIDDEN
                ),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
        )
        self._remember(run_id, event.event_id)

    def on_llm_end(
        self,
        response: object,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record an LLM node end callback."""
        run = self._current_run_id()
        if run is None:
            return
        parent = self._event_by_run_id.pop(str(run_id), None)
        self._recorder.record_event(
            LLM_RESPONSE,
            run_id=run,
            parent_event_id=parent,
            payload={
                "provider_name": "langgraph",
                "response": _clean_value(response, config=self._config),
                "token_usage": _usage_from_response(response),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
            duration_ms=self._duration(run_id),
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record an LLM node error callback."""
        self._record_error(error, run_id=run_id)

    def on_retry(
        self,
        retry_state: object,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a retry callback."""
        run = self._current_run_id()
        if run is None:
            return
        self._recorder.record_event(
            RETRY_RECORDED,
            run_id=run,
            parent_event_id=self._parent_event_id(run_id),
            payload=_retry_payload(retry_state),
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
        )

    def on_custom_event(
        self,
        name: str,
        data: object,
        *,
        run_id: object,
        **_kwargs: object,
    ) -> None:
        """Record a custom callback event."""
        run = self._current_run_id()
        if run is None:
            return
        self._recorder.record_event(
            CUSTOM_EVENT,
            run_id=run,
            parent_event_id=self._parent_event_id(run_id),
            payload={
                "name": f"langgraph.custom.{name}",
                "data": _clean_value(data, config=self._config),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
        )

    def _record_node_start(
        self,
        node_kind: str,
        node_name: str,
        inputs: object,
        *,
        run_id: object,
        parent_run_id: object | None,
        tags: Sequence[str] | None,
        metadata: Mapping[str, object] | None,
    ) -> None:
        """Record a LangGraph node start callback."""
        run = self._current_run_id()
        if run is None or node_name in self._config.ignore_nodes:
            return
        payload = {
            "name": "langgraph.node.started",
            "node": node_name,
            "node_kind": node_kind,
            "tags": list(tags or ()),
            "input": (
                _clean_value(inputs, config=self._config)
                if self._config.record_inputs
                else _HIDDEN
            ),
        }
        event = self._recorder.record_event(
            AGENT_STEP_STARTED,
            run_id=run,
            parent_event_id=self._parent_event_id(parent_run_id),
            payload=payload,
            metadata=_metadata(
                self._config,
                {"source": "langgraph.callback", "callback_metadata": metadata or {}},
            ),
        )
        self._remember(run_id, event.event_id)
        if _is_branch_node(node_name):
            self._recorder.record_event(
                CUSTOM_EVENT,
                run_id=run,
                parent_event_id=event.event_id,
                payload={"name": "langgraph.branch", "node": node_name},
                metadata=_metadata(self._config),
            )

    def _record_node_end(
        self,
        node_kind: str,
        outputs: object,
        *,
        run_id: object,
    ) -> None:
        """Record a LangGraph node end callback."""
        run = self._current_run_id()
        if run is None:
            return
        parent = self._event_by_run_id.pop(str(run_id), None)
        duration_ms = self._duration(run_id)
        self._recorder.record_event(
            AGENT_STEP_FINISHED,
            run_id=run,
            parent_event_id=parent,
            payload={
                "name": "langgraph.node.finished",
                "node_kind": node_kind,
                "output": (
                    _clean_value(outputs, config=self._config)
                    if self._config.record_outputs
                    else _HIDDEN
                ),
            },
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
            duration_ms=duration_ms,
        )

    def _record_error(self, error: BaseException, *, run_id: object) -> None:
        """Record a callback error."""
        run = self._current_run_id()
        if run is None:
            return
        parent = self._event_by_run_id.pop(str(run_id), None)
        self._recorder.record_event(
            EXCEPTION_RAISED,
            run_id=run,
            parent_event_id=parent,
            payload={"exception": self._serializer.serialize_exception(error)},
            metadata=_metadata(self._config, {"source": "langgraph.callback"}),
            duration_ms=self._duration(run_id),
        )

    def _current_run_id(self) -> str | None:
        """Return the current AgentReplay run id."""
        return self._run_id_provider()

    def _parent_event_id(self, parent_run_id: object | None) -> str | None:
        """Return an AgentReplay parent event id for a callback parent run id."""
        if parent_run_id is None:
            return None
        return self._event_by_run_id.get(str(parent_run_id))

    def _remember(self, run_id: object, event_id: str) -> None:
        """Remember callback-to-event mapping."""
        self._event_by_run_id[str(run_id)] = event_id
        self._started_at_by_run_id[str(run_id)] = perf_counter()

    def _duration(self, run_id: object) -> float:
        """Return elapsed callback duration."""
        started_at = self._started_at_by_run_id.pop(str(run_id), None)
        if started_at is None:
            return 0.0
        return max((perf_counter() - started_at) * 1000.0, 0.0)


LiteralRunStatus = Literal["completed", "failed", "cancelled"]
CallableRunIdProvider = Callable[[], str | None]


def instrument(
    graph: object,
    *,
    recorder: Recorder | None = None,
    storage: StorageBackend | None = None,
    config: LangGraphConfig | None = None,
) -> LangGraphInstrumentedGraph:
    """Return an instrumented LangGraph graph wrapper."""
    return AgentReplay(recorder=recorder, storage=storage, config=config).attach(graph)


def export_trace(trace: TraceSnapshot, *, export_format: str = "json") -> str:
    """Export a LangGraph execution trace as JSON, Markdown, or HTML."""
    normalized = export_format.lower()
    if normalized == "json":
        import json

        return json.dumps(trace.to_dict(), sort_keys=True)
    if normalized == "markdown":
        return _trace_markdown(trace)
    if normalized == "html":
        return _trace_html(trace)
    msg = f"Unsupported LangGraph export format: {export_format}"
    raise AdapterError(msg)


def _merge_config(
    config: Mapping[str, object] | None,
    callback: LangGraphCallbackHandler,
) -> dict[str, object]:
    """Return Runnable config with AgentReplay callback appended."""
    merged: dict[str, object] = dict(config or {})
    callbacks = merged.get("callbacks")
    if callbacks is None:
        merged["callbacks"] = [callback]
    elif isinstance(callbacks, list):
        merged["callbacks"] = [*callbacks, callback]
    else:
        merged["callbacks"] = [callbacks, callback]
    return merged


def _resolve_input(input_value: object, kwargs: dict[str, object]) -> object:
    """Support LangGraph's common ``input=`` keyword without shadowing builtins."""
    if input_value is None and "input" in kwargs:
        return kwargs.pop("input")
    return input_value


def _metadata(
    config: LangGraphConfig,
    values: Mapping[str, object] | None = None,
) -> Metadata:
    """Return merged and cleaned metadata."""
    merged: dict[str, object] = dict(config.metadata)
    if values is not None:
        merged.update(values)
    return _clean_mapping(merged, config=config)


def _graph_name(graph: object) -> str:
    """Return a readable graph name."""
    for attribute in ("name", "__name__"):
        value = getattr(graph, attribute, None)
        if isinstance(value, str) and value:
            return value
    return type(graph).__name__


def _graph_dag(graph: object) -> dict[str, JSONValue]:
    """Extract best-effort DAG metadata from a graph."""
    get_graph = getattr(graph, "get_graph", None)
    if not callable(get_graph):
        return {}
    try:
        graph_obj = get_graph()
    except Exception:
        return {}
    nodes = _graph_items(getattr(graph_obj, "nodes", ()))
    edges = _graph_edges(getattr(graph_obj, "edges", ()))
    return {"nodes": nodes, "edges": edges}


def _graph_items(value: object) -> list[JSONValue]:
    """Serialize graph node metadata."""
    if isinstance(value, Mapping):
        return [
            {"id": str(key), "label": _safe_name(item)} for key, item in value.items()
        ]
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_safe_name(item) for item in value]
    return []


def _graph_edges(value: object) -> list[JSONValue]:
    """Serialize graph edge metadata."""
    if not isinstance(value, Sequence) or isinstance(value, str | bytes | bytearray):
        return []
    edges: list[JSONValue] = []
    for edge in value:
        if isinstance(edge, Mapping):
            edges.append({str(key): _json_value(item) for key, item in edge.items()})
        else:
            source = getattr(edge, "source", None)
            target = getattr(edge, "target", None)
            edges.append({"source": _json_value(source), "target": _json_value(target)})
    return edges


def _checkpointer_metadata(graph: object) -> JSONValue:
    """Return best-effort checkpointer metadata."""
    checkpointer = getattr(graph, "checkpointer", None)
    if checkpointer is None:
        return None
    return {"type": type(checkpointer).__name__, "repr": _safe_repr(checkpointer)}


def _configurable(config: Mapping[str, object] | None) -> JSONValue:
    """Return runnable configurable metadata."""
    if config is None:
        return {}
    configurable = config.get("configurable")
    return _json_value(configurable)


def _resume_payload(value: object) -> JSONValue:
    """Return resume metadata when input appears to resume an interrupted graph."""
    resume = getattr(value, "resume", None)
    if resume is not None:
        return _json_value(resume)
    if isinstance(value, Mapping) and "resume" in value:
        return _json_value(value["resume"])
    return None


def _state_updates(value: object) -> tuple[tuple[str, object], ...]:
    """Extract likely state updates from graph outputs or update stream chunks."""
    if not isinstance(value, Mapping):
        return ()
    updates: list[tuple[str, object]] = []
    for key, item in value.items():
        if isinstance(key, str):
            updates.append((key, item))
    return tuple(updates)


def _parallel_branches(value: object) -> tuple[str, ...]:
    """Return likely parallel branch names."""
    if not isinstance(value, Mapping):
        return ()
    keys = tuple(str(key) for key in value)
    return keys if len(keys) > 1 else ()


def _interrupt_payload(value: object) -> JSONValue:
    """Return interrupt payload when visible."""
    if isinstance(value, Mapping) and "__interrupt__" in value:
        return _json_value(value["__interrupt__"])
    interrupt = getattr(value, "__interrupt__", None)
    return _json_value(interrupt) if interrupt is not None else None


def _stream_payload(value: object, *, config: LangGraphConfig) -> dict[str, JSONValue]:
    """Return a cleaned stream chunk payload."""
    return {
        "chunk": _json_value(_clean_value(value, config=config)),
        "parallel_branches": list(_parallel_branches(value)),
        "interrupt": _interrupt_payload(value),
    }


def _as_mapping(value: object) -> Mapping[str, object]:
    """Return mapping data for stream events."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {"value": value}


def _contains_key(value: object, key: str) -> bool:
    """Return whether a nested mapping contains a key."""
    if isinstance(value, Mapping):
        if key in value:
            return True
        return any(_contains_key(item, key) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return any(_contains_key(item, key) for item in value)
    return False


def _callback_name(serialized: Mapping[str, object] | None, name: str | None) -> str:
    """Return a callback name from callback inputs."""
    if name:
        return name
    if serialized:
        explicit = serialized.get("name")
        if isinstance(explicit, str) and explicit:
            return explicit
        identifier = serialized.get("id")
        if isinstance(identifier, Sequence) and not isinstance(
            identifier,
            str | bytes | bytearray,
        ):
            return ".".join(str(part) for part in identifier)
    return "langgraph_node"


def _model_name(serialized: Mapping[str, object] | None) -> str | None:
    """Return a model name from callback metadata when present."""
    if not serialized:
        return None
    for key in ("model", "model_name", "name"):
        value = serialized.get(key)
        if isinstance(value, str):
            return value
    return None


def _usage_from_response(response: object) -> Mapping[str, object] | None:
    """Extract token usage from an LLM response."""
    usage = getattr(response, "usage", None)
    if isinstance(usage, Mapping):
        return cast(Mapping[str, object], usage)
    if isinstance(response, Mapping):
        response_usage = response.get("usage") or response.get("token_usage")
        if isinstance(response_usage, Mapping):
            return cast(Mapping[str, object], response_usage)
    return None


def _retry_payload(retry_state: object) -> dict[str, JSONValue]:
    """Return retry event payload."""
    return {
        "attempt": _json_value(getattr(retry_state, "attempt_number", None)),
        "reason": _json_value(getattr(retry_state, "outcome", None)),
        "delay_ms": _json_value(getattr(retry_state, "idle_for", None)),
    }


def _is_branch_node(name: str) -> bool:
    """Return whether a callback name looks like a branch router."""
    normalized = name.lower()
    return "branch" in normalized or "condition" in normalized or "route" in normalized


def _is_sampled(config: LangGraphConfig) -> bool:
    """Return whether a run should be sampled."""
    return config.sample_rate >= 1.0 or random.random() < config.sample_rate


def _clean_value(value: object, *, config: LangGraphConfig) -> object:
    """Clean state values according to adapter configuration."""
    if config.hide_state:
        return _HIDDEN
    if config.redact_secrets:
        return _redact_value(value)
    return value


def _clean_mapping(value: Mapping[Any, object], *, config: LangGraphConfig) -> Metadata:
    """Return a JSON-compatible and optionally redacted mapping."""
    serializer = EventSerializer()
    cleaned: dict[str, JSONValue] = {}
    for key, item in value.items():
        key_text = str(key)
        if config.redact_secrets and _sensitive_key(key_text):
            cleaned[key_text] = _REDACTED
        else:
            cleaned[key_text] = serializer.serialize_value(
                _redact_value(item) if config.redact_secrets else item,
            )
    return cleaned


def _redact_value(value: object) -> object:
    """Redact sensitive values recursively."""
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, Mapping):
        return {
            str(key): _REDACTED if _sensitive_key(str(key)) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_redact_value(item) for item in value]
    return value


def _redact_string(value: str) -> str:
    """Redact common token-like secret strings."""
    return " ".join(
        _REDACTED if word.startswith(("sk-", "Bearer", "token-")) else word
        for word in value.split()
    )


def _sensitive_key(key: str) -> bool:
    """Return whether a key name likely contains a secret."""
    normalized = key.replace("-", "_").lower()
    return any(marker in normalized for marker in _SECRET_MARKERS)


def _json_value(value: object) -> JSONValue:
    """Return a JSON-compatible value."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return _safe_repr(value)


def _safe_name(value: object) -> JSONValue:
    """Return a safe display name for graph components."""
    name = getattr(value, "name", None)
    if isinstance(name, str):
        return name
    return _json_value(value)


def _safe_repr(value: object) -> str:
    """Return bounded repr text."""
    text = repr(value)
    return text if len(text) <= 500 else f"{text[:497]}..."


def _put_env_bool(
    values: dict[str, object],
    env: Mapping[str, str],
    env_name: str,
    key: str,
) -> None:
    """Parse one optional boolean environment value."""
    if env_name not in env:
        return
    normalized = env[env_name].strip().lower()
    if normalized in _TRUE_VALUES:
        values[key] = True
    elif normalized in _FALSE_VALUES:
        values[key] = False
    else:
        msg = f"{env_name} must be a boolean value."
        raise ValueError(msg)


def _split_csv(value: str) -> tuple[str, ...]:
    """Split comma-separated configuration values."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _trace_markdown(trace: TraceSnapshot) -> str:
    """Render a Markdown export for a trace."""
    lines = [
        f"# AgentReplay LangGraph Run {trace.run.run_id}",
        "",
        f"- Status: `{trace.run.status}`",
        f"- Name: `{trace.run.name or ''}`",
        f"- Duration ms: `{trace.run.duration_ms}`",
        f"- Events: `{len(trace.events)}`",
        "",
        "## Events",
    ]
    for event in trace.events:
        lines.append(
            f"- `{event.sequence}` `{event.event_type}` "
            f"`{event.event_id}` parent=`{event.parent_event_id or ''}`"
        )
    return "\n".join(lines)


def _trace_html(trace: TraceSnapshot) -> str:
    """Render an HTML export for a trace."""
    import html

    items = "\n".join(
        (
            "<li>"
            f"{event.sequence} "
            f"<code>{html.escape(event.event_type)}</code> "
            f"<code>{html.escape(event.event_id)}</code>"
            "</li>"
        )
        for event in trace.events
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            (
                '<head><meta charset="utf-8">'
                "<title>AgentReplay LangGraph Export</title></head>"
            ),
            "<body>",
            f"<h1>Run {html.escape(trace.run.run_id)}</h1>",
            f"<p>Status: {html.escape(trace.run.status)}</p>",
            f"<p>Events: {len(trace.events)}</p>",
            f"<ul>{items}</ul>",
            "</body>",
            "</html>",
        ]
    )


__all__ = [
    "AgentReplay",
    "LangGraphCallbackHandler",
    "LangGraphConfig",
    "LangGraphInstrumentedGraph",
    "export_trace",
    "instrument",
]
