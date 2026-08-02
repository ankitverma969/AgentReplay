"""OpenAI Agents SDK integration for AgentReplay."""

from __future__ import annotations

import functools
import importlib.util
import os
import random
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, ParamSpec, TypeVar, cast, overload

from agentreplay.core.events import (
    AGENT_STEP_FINISHED,
    AGENT_STEP_STARTED,
    ASSISTANT_RESPONSE,
    CUSTOM_EVENT,
    EXCEPTION_RAISED,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    RETRY_RECORDED,
    SYSTEM_PROMPT,
    TOKEN_USAGE_RECORDED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    EventRecord,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import AdapterError
from agentreplay.recording import Recorder
from agentreplay.recording.serializers import EventSerializer
from agentreplay.storage import SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue, Metadata

P = ParamSpec("P")
R = TypeVar("R")

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_SAMPLER = random.SystemRandom()
_HIDDEN = "[hidden]"
_REDACTED = "[redacted]"
_API_KEY_MARKERS = ("api_key", "apikey", "authorization", "bearer", "token")


@dataclass(frozen=True, slots=True)
class OpenAIAgentsConfig:
    """Configuration for the OpenAI Agents SDK adapter."""

    enabled: bool = True
    record_prompts: bool = True
    hide_prompts: bool = False
    redact_api_keys: bool = True
    ignore_tools: tuple[str, ...] = ()
    ignore_events: tuple[str, ...] = ()
    sample_rate: float = 1.0
    metadata: Metadata = field(default_factory=dict)
    run_name: str | None = None

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if not 0.0 <= self.sample_rate <= 1.0:
            msg = "OpenAI Agents sampling rate must be between 0.0 and 1.0."
            raise ValueError(msg)
        object.__setattr__(self, "ignore_tools", tuple(self.ignore_tools))
        object.__setattr__(self, "ignore_events", tuple(self.ignore_events))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
        *,
        overrides: Mapping[str, object] | None = None,
    ) -> OpenAIAgentsConfig:
        """Load OpenAI adapter settings from environment variables."""
        env = os.environ if environ is None else environ
        values: dict[str, object] = {}
        _put_env_bool(values, env, "AGENTREPLAY_OPENAI_ENABLED", "enabled")
        _put_env_bool(
            values,
            env,
            "AGENTREPLAY_OPENAI_RECORD_PROMPTS",
            "record_prompts",
        )
        _put_env_bool(values, env, "AGENTREPLAY_OPENAI_HIDE_PROMPTS", "hide_prompts")
        _put_env_bool(
            values,
            env,
            "AGENTREPLAY_OPENAI_REDACT_API_KEYS",
            "redact_api_keys",
        )
        if "AGENTREPLAY_OPENAI_IGNORE_TOOLS" in env:
            values["ignore_tools"] = _split_csv(env["AGENTREPLAY_OPENAI_IGNORE_TOOLS"])
        if "AGENTREPLAY_OPENAI_IGNORE_EVENTS" in env:
            values["ignore_events"] = _split_csv(
                env["AGENTREPLAY_OPENAI_IGNORE_EVENTS"],
            )
        if "AGENTREPLAY_OPENAI_SAMPLE_RATE" in env:
            values["sample_rate"] = float(env["AGENTREPLAY_OPENAI_SAMPLE_RATE"])
        if "AGENTREPLAY_OPENAI_RUN_NAME" in env:
            values["run_name"] = env["AGENTREPLAY_OPENAI_RUN_NAME"]
        if overrides is not None:
            values.update(overrides)
        return cls(**cast(Any, values))


class AgentReplay:
    """OpenAI Agents SDK integration manager."""

    name = "openai-agents"
    framework = "openai-agents-sdk"
    version_support = "OpenAI Agents SDK with tracing processors or agent hooks"

    def __init__(
        self,
        *,
        recorder: Recorder | None = None,
        storage: StorageBackend | None = None,
        config: OpenAIAgentsConfig | None = None,
        auto_instrument: bool = True,
    ) -> None:
        """Create an OpenAI Agents SDK integration manager."""
        self.config = OpenAIAgentsConfig.from_env() if config is None else config
        self.recorder = Recorder(auto_start=False) if recorder is None else recorder
        self.storage = SQLiteStorage() if storage is None else storage
        self._serializer = EventSerializer()
        self._processor = OpenAIAgentsTraceProcessor(
            recorder=self.recorder,
            storage=self.storage,
            config=self.config,
            serializer=self._serializer,
        )
        self._attached_agents: list[object] = []
        self._entered_run_id: str | None = None
        self._instrumented = False
        if auto_instrument and self.config.enabled:
            self.instrument()

    def __enter__(self) -> AgentReplay:
        """Enter a recording context."""
        if self.config.enabled and self._entered_run_id is None:
            self._entered_run_id = self.recorder.start_run(
                name=self.config.run_name or "openai-agents",
                metadata=self._metadata({"source": "context"}),
            )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> None:
        """Leave a recording context and persist the run when available."""
        if self._entered_run_id is None:
            return
        if exc is not None:
            self.recorder.record_exception(exc)
        self.recorder.end_run(
            self._entered_run_id,
            status="failed" if exc is not None else "completed",
        )
        self._persist(self._entered_run_id)
        self._entered_run_id = None

    def is_available(self) -> bool:
        """Return whether the OpenAI Agents SDK package is importable."""
        return importlib.util.find_spec("agents") is not None

    def instrument(self) -> AgentReplay:
        """Register an AgentReplay tracing processor with the SDK."""
        if self._instrumented or not self.config.enabled:
            return self
        try:
            tracing = _import_agents_tracing()
        except ImportError as exc:
            msg = "OpenAI Agents SDK is not installed. Install the optional SDK extra."
            raise AdapterError(msg) from exc
        register_processor = getattr(tracing, "add_trace_processor", None)
        if register_processor is None:
            register_processor = getattr(tracing, "add_tracing_processor", None)
        if register_processor is None:
            register_processor = getattr(tracing, "register_processor", None)
        if register_processor is None:
            msg = "OpenAI Agents SDK tracing processor registration was not found."
            raise AdapterError(msg)
        register_processor(self._processor)
        self._instrumented = True
        return self

    def attach(self, agent: object) -> object:
        """Attach AgentReplay hooks to one OpenAI Agents SDK agent."""
        if not self.config.enabled:
            return agent
        hooks = OpenAIAgentsHooks(
            recorder=self.recorder,
            storage=self.storage,
            config=self.config,
            serializer=self._serializer,
        )
        existing_hooks = getattr(agent, "hooks", None)
        agent_object = cast(Any, agent)
        agent_object.hooks = _HookChain(existing_hooks, hooks)
        self._attached_agents.append(agent)
        return agent

    def detach(self, agent: object) -> None:
        """Remove AgentReplay hooks previously installed by ``attach``."""
        hooks = getattr(agent, "hooks", None)
        if isinstance(hooks, _HookChain):
            agent_object = cast(Any, agent)
            agent_object.hooks = hooks.previous
        if agent in self._attached_agents:
            self._attached_agents.remove(agent)

    def trace(self, run_id: str | None = None) -> TraceSnapshot:
        """Return a recorded trace from the underlying recorder."""
        return self.recorder.trace(run_id)

    def last_run_id(self) -> str | None:
        """Return the most recently recorded run id."""
        return self.recorder.last_run_id()

    def _metadata(self, values: Mapping[str, object] | None = None) -> Metadata:
        """Merge adapter metadata with event-specific metadata."""
        merged: dict[str, object] = dict(self.config.metadata)
        if values is not None:
            merged.update(values)
        return _clean_mapping(
            merged,
            redact_api_keys=self.config.redact_api_keys,
        )

    def _persist(self, run_id: str) -> None:
        """Persist a completed run without altering recorder state."""
        self.recorder.save_to_storage(self.storage, run_id=run_id)


class OpenAIAgentsTraceProcessor:
    """OpenAI Agents SDK tracing processor that records completed spans."""

    def __init__(
        self,
        *,
        recorder: Recorder,
        storage: StorageBackend,
        config: OpenAIAgentsConfig,
        serializer: EventSerializer,
    ) -> None:
        """Create a trace processor."""
        self._recorder = recorder
        self._storage = storage
        self._config = config
        self._serializer = serializer
        self._run_by_trace_id: dict[str, str] = {}
        self._sampled_traces: set[str] = set()
        self._event_by_span_id: dict[str, str] = {}
        self._started_at_by_span_id: dict[str, float] = {}

    def on_trace_start(self, trace: object) -> None:
        """Record an OpenAI Agents trace start."""
        if not self._config.enabled or not self._is_sampled():
            return
        trace_id = _object_id(trace, "trace_id")
        metadata = self._metadata(
            {
                "source": "openai_agents.trace",
                "trace_id": trace_id,
                "group_id": _optional_attr(trace, "group_id"),
                "workflow_name": _optional_attr(trace, "workflow_name"),
                "sdk_metadata": _optional_attr(trace, "metadata"),
            },
        )
        run_id = self._recorder.start_run(
            name=self._config.run_name or _optional_str_attr(trace, "workflow_name"),
            metadata=metadata,
        )
        self._run_by_trace_id[trace_id] = run_id
        self._sampled_traces.add(trace_id)

    def on_trace_end(self, trace: object) -> None:
        """Record an OpenAI Agents trace end."""
        trace_id = _object_id(trace, "trace_id")
        run_id = self._run_by_trace_id.pop(trace_id, None)
        self._sampled_traces.discard(trace_id)
        if run_id is None:
            return
        self._recorder.end_run(run_id, status="completed")
        self._recorder.save_to_storage(self._storage, run_id=run_id)

    def on_span_start(self, span: object) -> None:
        """Record the beginning of an OpenAI Agents span."""
        if not self._config.enabled or self._ignored_span(span):
            return
        run_id = self._resolve_run_id(span)
        if run_id is None:
            return
        span_id = _object_id(span, "span_id")
        self._started_at_by_span_id[span_id] = perf_counter()
        event = self._record_span_start(span, run_id=run_id)
        if event is not None:
            self._event_by_span_id[span_id] = event.event_id

    def on_span_end(self, span: object) -> None:
        """Record the completion of an OpenAI Agents span."""
        if not self._config.enabled or self._ignored_span(span):
            return
        run_id = self._resolve_run_id(span)
        if run_id is None:
            return
        span_id = _object_id(span, "span_id")
        parent_event_id = self._event_by_span_id.pop(span_id, None)
        started_at = self._started_at_by_span_id.pop(span_id, None)
        duration_ms = (
            0.0 if started_at is None else (perf_counter() - started_at) * 1000
        )
        self._record_span_end(
            span,
            run_id=run_id,
            parent_event_id=parent_event_id,
            duration_ms=max(duration_ms, 0.0),
        )

    def shutdown(self) -> None:
        """Clear in-memory adapter state."""
        self.force_flush()

    def force_flush(self) -> None:
        """Clear completed processor bookkeeping."""
        self._event_by_span_id.clear()
        self._started_at_by_span_id.clear()

    def _resolve_run_id(self, span: object) -> str | None:
        """Resolve the AgentReplay run id associated with a span."""
        trace_id = _optional_str_attr(span, "trace_id")
        if trace_id is not None and trace_id in self._sampled_traces:
            return self._run_by_trace_id.get(trace_id)
        active_run_id = self._recorder.current_run_id()
        if active_run_id is not None:
            return active_run_id
        if trace_id is None and self._config.sample_rate > 0.0:
            return self._recorder.start_run(
                name=self._config.run_name or "openai-agents",
                metadata=self._metadata({"source": "openai_agents.span"}),
            )
        return None

    def _record_span_start(self, span: object, *, run_id: str) -> EventRecord | None:
        """Record a start event for one SDK span."""
        data = _span_data(span)
        span_type = _span_type(data)
        payload = _span_payload(data, serializer=self._serializer)
        metadata = self._metadata(_span_metadata(span, data))
        parent_span_id = _optional_str_attr(span, "parent_id")
        parent_event_id = (
            None
            if parent_span_id is None
            else self._event_by_span_id.get(parent_span_id)
        )
        if span_type in {"agent", "runner"}:
            return self._recorder.record_event(
                AGENT_STEP_STARTED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload=payload,
                metadata=metadata,
            )
        if span_type in {"generation", "response"}:
            self._record_prompt_payload(payload, run_id=run_id)
            return self._recorder.record_event(
                LLM_REQUEST,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload=payload,
                metadata=metadata,
            )
        if span_type == "function":
            tool_name = _tool_name(payload)
            if self._ignored_tool(tool_name):
                return None
            return self._recorder.record_event(
                TOOL_STARTED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={
                    "tool_name": tool_name,
                    "arguments": dict(_mapping_or_empty(payload.get("input"))),
                },
                metadata=metadata,
            )
        if span_type == "handoff":
            return self._recorder.custom_event(
                "openai_agents.handoff.started",
                payload=payload,
                metadata=metadata,
            )
        if span_type == "guardrail":
            return self._recorder.custom_event(
                "openai_agents.guardrail.started",
                payload=payload,
                metadata=metadata,
            )
        if span_type == "retry":
            return self._recorder.record_event(
                RETRY_RECORDED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={
                    "attempt": _int_or_none(payload.get("attempt")),
                    "reason": _optional_string(payload.get("reason")),
                    "delay_ms": _float_or_none(payload.get("delay_ms")),
                },
                metadata=metadata,
            )
        return self._recorder.record_event(
            CUSTOM_EVENT,
            run_id=run_id,
            parent_event_id=parent_event_id,
            payload={"name": f"openai_agents.{span_type}.started", **payload},
            metadata=metadata,
        )

    def _record_span_end(
        self,
        span: object,
        *,
        run_id: str,
        parent_event_id: str | None,
        duration_ms: float,
    ) -> None:
        """Record a completion event for one SDK span."""
        data = _span_data(span)
        span_type = _span_type(data)
        payload = _span_payload(data, serializer=self._serializer)
        metadata = self._metadata(_span_metadata(span, data))
        if span_type in {"agent", "runner"}:
            self._recorder.record_event(
                AGENT_STEP_FINISHED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload=payload,
                metadata=metadata,
                duration_ms=duration_ms,
            )
        elif span_type in {"generation", "response"}:
            self._recorder.record_event(
                LLM_RESPONSE,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={
                    "provider_name": "openai",
                    "model_name": _optional_string(payload.get("model")),
                    "response": payload.get("output") or payload.get("response_id"),
                    "token_usage": _mapping_or_none(payload.get("usage")),
                    "latency_ms": duration_ms,
                },
                metadata=metadata,
                duration_ms=duration_ms,
            )
        elif span_type == "function":
            tool_name = _tool_name(payload)
            if not self._ignored_tool(tool_name):
                self._recorder.record_event(
                    TOOL_FINISHED,
                    run_id=run_id,
                    parent_event_id=parent_event_id,
                    payload={"tool_name": tool_name, "result": payload.get("output")},
                    duration_ms=duration_ms,
                    metadata=metadata,
                )
        elif span_type == "handoff":
            self._recorder.custom_event(
                "openai_agents.handoff.finished",
                payload=payload,
                metadata=metadata,
            )
        elif span_type == "guardrail":
            self._recorder.custom_event(
                "openai_agents.guardrail.finished",
                payload=payload,
                metadata=metadata,
            )
        else:
            self._recorder.record_event(
                CUSTOM_EVENT,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={"name": f"openai_agents.{span_type}.finished", **payload},
                metadata=metadata,
                duration_ms=duration_ms,
            )
        if duration_ms > 0.0:
            self._recorder.record_event(
                LATENCY_RECORDED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={
                    "latency_ms": duration_ms,
                    "operation": f"openai_agents.{span_type}",
                },
                metadata=metadata,
                duration_ms=duration_ms,
            )
        usage = _mapping_or_none(payload.get("usage"))
        if usage is not None:
            self._record_usage(usage, metadata, run_id=run_id)
        error = payload.get("error") or payload.get("exception")
        if error is not None:
            self._recorder.record_event(
                EXCEPTION_RAISED,
                run_id=run_id,
                parent_event_id=parent_event_id,
                payload={"exception": error},
                metadata=metadata,
            )

    def _record_prompt_payload(
        self,
        payload: Mapping[str, JSONValue],
        *,
        run_id: str,
    ) -> None:
        """Record prompt messages from SDK generation inputs when enabled."""
        if not self._config.record_prompts:
            return
        input_value = payload.get("input")
        if isinstance(input_value, str):
            self._record_prompt(run_id, USER_PROMPT, input_value)
            return
        if not isinstance(input_value, Sequence):
            return
        for item in input_value:
            if not isinstance(item, Mapping):
                continue
            role = item.get("role")
            content = _message_content(item)
            if content is None:
                continue
            prompt = _prompt_value(content, self._config)
            if role == "system":
                self._record_prompt(run_id, SYSTEM_PROMPT, prompt)
            elif role == "assistant":
                self._record_prompt(run_id, ASSISTANT_RESPONSE, prompt)
            else:
                self._record_prompt(run_id, USER_PROMPT, prompt)

    def _record_usage(
        self,
        usage: Mapping[str, object],
        metadata: Metadata,
        *,
        run_id: str,
    ) -> None:
        """Record token usage from a model span payload."""
        self._recorder.record_event(
            TOKEN_USAGE_RECORDED,
            run_id=run_id,
            parent_event_id=None,
            payload={
                "input_tokens": _int_or_none(
                    usage.get("input_tokens", usage.get("prompt_tokens")),
                ),
                "output_tokens": _int_or_none(
                    usage.get("output_tokens", usage.get("completion_tokens")),
                ),
                "total_tokens": _int_or_none(usage.get("total_tokens")),
            },
            metadata=metadata,
        )

    def _record_prompt(self, run_id: str, event_type: str, prompt: str) -> None:
        """Record a prompt-like event with an explicit run id."""
        key = "response" if event_type == ASSISTANT_RESPONSE else "prompt"
        self._recorder.record_event(
            event_type,
            run_id=run_id,
            parent_event_id=None,
            payload={key: _prompt_value(prompt, self._config)},
        )

    def _ignored_span(self, span: object) -> bool:
        """Return whether a span type is configured to be ignored."""
        span_type = _span_type(_span_data(span))
        return span_type in self._config.ignore_events

    def _ignored_tool(self, tool_name: str) -> bool:
        """Return whether a tool is configured to be ignored."""
        return tool_name in self._config.ignore_tools

    def _is_sampled(self) -> bool:
        """Return whether the next trace should be sampled."""
        return (
            self._config.sample_rate >= 1.0
            or _SAMPLER.random() < self._config.sample_rate
        )

    def _metadata(self, values: Mapping[str, object] | None = None) -> Metadata:
        """Return redacted adapter metadata."""
        merged: dict[str, object] = dict(self._config.metadata)
        if values is not None:
            merged.update(values)
        return _clean_mapping(merged, redact_api_keys=self._config.redact_api_keys)


class OpenAIAgentsHooks:
    """Agent hook implementation for explicit ``attach(agent)`` integration."""

    def __init__(
        self,
        *,
        recorder: Recorder,
        storage: StorageBackend,
        config: OpenAIAgentsConfig,
        serializer: EventSerializer,
    ) -> None:
        """Create OpenAI Agents SDK hooks."""
        self._recorder = recorder
        self._storage = storage
        self._config = config
        self._serializer = serializer
        self._active_run_ids: set[str] = set()
        self._run_id_by_agent_id: dict[int, str] = {}

    async def on_start(self, context: object, agent: object) -> None:
        """Record agent start from the SDK agent hook."""
        if not self._config.enabled:
            return
        run_id = self._ensure_run(context, agent)
        self._recorder.record_event(
            AGENT_STEP_STARTED,
            run_id=run_id,
            payload={"agent": _agent_name(agent)},
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    async def on_end(self, context: object, agent: object, output: object) -> None:
        """Record agent end from the SDK agent hook."""
        if not self._config.enabled:
            return
        run_id = self._ensure_run(context, agent)
        self._recorder.record_event(
            ASSISTANT_RESPONSE,
            run_id=run_id,
            parent_event_id=None,
            payload={"response": _clean_value(output, config=self._config)},
        )
        self._recorder.record_event(
            AGENT_STEP_FINISHED,
            run_id=run_id,
            payload={"agent": _agent_name(agent), "output": output},
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )
        self._finish_run(run_id)

    async def on_handoff(self, context: object, agent: object, source: object) -> None:
        """Record a handoff into this agent."""
        run_id = self._ensure_run(context, agent)
        self._recorder.record_event(
            CUSTOM_EVENT,
            run_id=run_id,
            parent_event_id=None,
            payload={
                "name": "openai_agents.handoff",
                "from_agent": _agent_name(source),
                "to_agent": _agent_name(agent),
            },
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    async def on_tool_start(self, context: object, agent: object, tool: object) -> None:
        """Record tool start from the SDK agent hook."""
        tool_name = _tool_object_name(tool, context)
        if self._ignored_tool(tool_name):
            return
        run_id = self._ensure_run(context, agent)
        self._recorder.record_event(
            TOOL_STARTED,
            run_id=run_id,
            parent_event_id=None,
            payload={
                "tool_name": tool_name,
                "arguments": dict(
                    _mapping_or_empty(_optional_attr(context, "tool_arguments")),
                ),
            },
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    async def on_tool_end(
        self,
        context: object,
        agent: object,
        tool: object,
        result: object,
    ) -> None:
        """Record tool end from the SDK agent hook."""
        tool_name = _tool_object_name(tool, context)
        if self._ignored_tool(tool_name):
            return
        run_id = self._ensure_run(context, agent)
        self._recorder.record_event(
            TOOL_FINISHED,
            run_id=run_id,
            parent_event_id=None,
            payload={
                "tool_name": tool_name,
                "result": _clean_value(result, config=self._config),
            },
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    async def on_llm_start(
        self,
        context: object,
        agent: object,
        system_prompt: str | None,
        input_items: list[object],
    ) -> None:
        """Record model request from the SDK agent hook."""
        run_id = self._ensure_run(context, agent)
        if self._config.record_prompts and system_prompt is not None:
            self._recorder.record_event(
                SYSTEM_PROMPT,
                run_id=run_id,
                parent_event_id=None,
                payload={"prompt": _prompt_value(system_prompt, self._config)},
            )
        for item in input_items:
            if self._config.record_prompts:
                self._record_input_item(item, run_id=run_id)
        self._recorder.record_event(
            LLM_REQUEST,
            run_id=run_id,
            parent_event_id=None,
            payload={"agent": _agent_name(agent), "input_items": input_items},
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    async def on_llm_end(
        self,
        context: object,
        agent: object,
        response: object,
    ) -> None:
        """Record model response from the SDK agent hook."""
        run_id = self._ensure_run(context, agent)
        payload = self._serializer.serialize_value(response)
        response_mapping = (
            payload if isinstance(payload, Mapping) else {"response": payload}
        )
        self._recorder.record_event(
            LLM_RESPONSE,
            run_id=run_id,
            parent_event_id=None,
            payload={
                "provider_name": "openai",
                "model_name": _optional_string(response_mapping.get("model")),
                "response": response_mapping,
                "token_usage": _mapping_or_none(response_mapping.get("usage")),
            },
            metadata=self._metadata({"source": "openai_agents.hooks"}),
        )

    def _record_input_item(self, item: object, *, run_id: str) -> None:
        """Record one model input item as a prompt event when possible."""
        serialized = self._serializer.serialize_value(item)
        if not isinstance(serialized, Mapping):
            return
        content = _message_content(serialized)
        if content is None:
            return
        role = serialized.get("role")
        event_type = SYSTEM_PROMPT if role == "system" else USER_PROMPT
        if role == "system":
            event_type = SYSTEM_PROMPT
        self._recorder.record_event(
            event_type,
            run_id=run_id,
            parent_event_id=None,
            payload={"prompt": _prompt_value(content, self._config)},
        )

    def _ensure_run(self, context: object, agent: object) -> str:
        """Ensure a run exists for hook callbacks."""
        active = self._recorder.current_run_id()
        if active is not None:
            return active
        agent_id = id(agent)
        existing = self._run_id_by_agent_id.get(agent_id)
        if existing is not None:
            return existing
        run_id = self._recorder.start_run(
            name=self._config.run_name or _agent_name(agent),
            metadata=self._metadata(
                {
                    "source": "openai_agents.hooks",
                    "context": _safe_repr(context),
                },
            ),
        )
        self._active_run_ids.add(run_id)
        self._run_id_by_agent_id[agent_id] = run_id
        return run_id

    def _finish_run(self, run_id: str) -> None:
        """Finish and persist runs created by this hook object."""
        if run_id not in self._active_run_ids:
            return
        self._recorder.end_run(run_id, status="completed")
        self._recorder.save_to_storage(self._storage, run_id=run_id)
        self._active_run_ids.remove(run_id)
        for agent_id, mapped_run_id in tuple(self._run_id_by_agent_id.items()):
            if mapped_run_id == run_id:
                del self._run_id_by_agent_id[agent_id]

    def _ignored_tool(self, tool_name: str) -> bool:
        """Return whether a tool is configured to be ignored."""
        return tool_name in self._config.ignore_tools

    def _metadata(self, values: Mapping[str, object] | None = None) -> Metadata:
        """Return merged hook metadata."""
        merged: dict[str, object] = dict(self._config.metadata)
        if values is not None:
            merged.update(values)
        return _clean_mapping(merged, redact_api_keys=self._config.redact_api_keys)


class _HookChain:
    """Composable hook object that preserves any existing agent hooks."""

    def __init__(self, previous: object | None, current: OpenAIAgentsHooks) -> None:
        """Create a hook chain."""
        self.previous = previous
        self.current = current

    async def on_start(self, context: object, agent: object) -> None:
        """Invoke start hooks in order."""
        await _maybe_await(self.previous, "on_start", context, agent)
        await self.current.on_start(context, agent)

    async def on_end(self, context: object, agent: object, output: object) -> None:
        """Invoke end hooks in order."""
        await _maybe_await(self.previous, "on_end", context, agent, output)
        await self.current.on_end(context, agent, output)

    async def on_handoff(self, context: object, agent: object, source: object) -> None:
        """Invoke handoff hooks in order."""
        await _maybe_await(self.previous, "on_handoff", context, agent, source)
        await self.current.on_handoff(context, agent, source)

    async def on_tool_start(
        self,
        context: object,
        agent: object,
        tool: object,
    ) -> None:
        """Invoke tool start hooks in order."""
        await _maybe_await(self.previous, "on_tool_start", context, agent, tool)
        await self.current.on_tool_start(context, agent, tool)

    async def on_tool_end(
        self,
        context: object,
        agent: object,
        tool: object,
        result: object,
    ) -> None:
        """Invoke tool end hooks in order."""
        await _maybe_await(self.previous, "on_tool_end", context, agent, tool, result)
        await self.current.on_tool_end(context, agent, tool, result)

    async def on_llm_start(
        self,
        context: object,
        agent: object,
        system_prompt: str | None,
        input_items: list[object],
    ) -> None:
        """Invoke LLM start hooks in order."""
        await _maybe_await(
            self.previous,
            "on_llm_start",
            context,
            agent,
            system_prompt,
            input_items,
        )
        await self.current.on_llm_start(context, agent, system_prompt, input_items)

    async def on_llm_end(
        self,
        context: object,
        agent: object,
        response: object,
    ) -> None:
        """Invoke LLM end hooks in order."""
        await _maybe_await(self.previous, "on_llm_end", context, agent, response)
        await self.current.on_llm_end(context, agent, response)


@overload
def record_agent(func: Callable[P, R]) -> Callable[P, R]: ...


@overload
def record_agent(
    func: None = None,
    *,
    name: str | None = None,
    config: OpenAIAgentsConfig | None = None,
    recorder: Recorder | None = None,
    storage: StorageBackend | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def record_agent(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    config: OpenAIAgentsConfig | None = None,
    recorder: Recorder | None = None,
    storage: StorageBackend | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Record an OpenAI Agents SDK invocation with a decorator."""
    resolved_config = OpenAIAgentsConfig.from_env() if config is None else config

    def decorate(target: Callable[P, R]) -> Callable[P, R]:
        run_name = name or target.__qualname__
        target_config = _config_with_run_name(resolved_config, run_name)

        if _is_coroutine_callable(target):

            @functools.wraps(target)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                if not target_config.enabled:
                    result = target(*args, **kwargs)
                    return await cast(Awaitable[object], result)
                manager = AgentReplay(
                    recorder=recorder,
                    storage=storage,
                    config=target_config,
                    auto_instrument=False,
                )
                with manager:
                    _record_call_inputs(manager.recorder, target_config, args, kwargs)
                    result = target(*args, **kwargs)
                    output = await cast(Awaitable[object], result)
                    manager.recorder.assistant_response(
                        _clean_value(output, config=target_config),
                    )
                    return output

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(target)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if not target_config.enabled:
                return target(*args, **kwargs)
            manager = AgentReplay(
                recorder=recorder,
                storage=storage,
                config=target_config,
                auto_instrument=False,
            )
            with manager:
                _record_call_inputs(manager.recorder, target_config, args, kwargs)
                output = target(*args, **kwargs)
                manager.recorder.assistant_response(
                    _clean_value(output, config=target_config),
                )
                return output

        return sync_wrapper

    if func is None:
        return decorate
    return decorate(func)


def instrument(
    *,
    config: OpenAIAgentsConfig | None = None,
    recorder: Recorder | None = None,
    storage: StorageBackend | None = None,
) -> AgentReplay:
    """Enable automatic OpenAI Agents SDK tracing instrumentation."""
    return AgentReplay(recorder=recorder, storage=storage, config=config)


def _import_agents_tracing() -> object:
    """Import the SDK tracing module lazily."""
    try:
        import importlib

        tracing = importlib.import_module("agents.tracing")
    except ImportError as exc:
        raise ImportError from exc
    return tracing


def _record_call_inputs(
    recorder: Recorder,
    config: OpenAIAgentsConfig,
    args: tuple[object, ...],
    kwargs: Mapping[str, object],
) -> None:
    """Record decorator inputs as metadata and user prompts when possible."""
    if not config.record_prompts:
        return
    prompt = _first_prompt(args, kwargs)
    if prompt is not None:
        recorder.user_prompt(_prompt_value(prompt, config))


def _config_with_run_name(
    config: OpenAIAgentsConfig,
    run_name: str,
) -> OpenAIAgentsConfig:
    """Return config with a decorator run name when one is not already set."""
    if config.run_name is not None:
        return config
    return replace(config, run_name=run_name)


def _first_prompt(args: tuple[object, ...], kwargs: Mapping[str, object]) -> str | None:
    """Find a likely prompt value from decorator inputs."""
    for key in ("input", "prompt", "message", "messages"):
        value = kwargs.get(key)
        if isinstance(value, str):
            return value
    for value in args:
        if isinstance(value, str):
            return value
    return None


def _span_data(span: object) -> object:
    """Return SDK span data from common span shapes."""
    data = _optional_attr(span, "span_data")
    if data is not None:
        return data
    data = _optional_attr(span, "data")
    if data is not None:
        return data
    return span


def _span_type(data: object) -> str:
    """Return a normalized SDK span type."""
    value = _optional_attr(data, "type")
    if isinstance(value, str):
        return value
    exported = _export_object(data)
    value = exported.get("type")
    if isinstance(value, str):
        return value
    return type(data).__name__.replace("SpanData", "").lower() or "custom"


def _span_payload(data: object, *, serializer: EventSerializer) -> dict[str, JSONValue]:
    """Serialize SDK span data into a JSON-compatible payload."""
    exported = _export_object(data)
    if exported:
        return _clean_mapping(exported, redact_api_keys=True)
    value = serializer.serialize_value(data)
    if isinstance(value, Mapping):
        return _clean_mapping(value, redact_api_keys=True)
    return {"value": value}


def _span_metadata(span: object, data: object) -> dict[str, object]:
    """Collect stable metadata for a span."""
    return {
        "source": "openai_agents.tracing",
        "span_id": _optional_attr(span, "span_id"),
        "trace_id": _optional_attr(span, "trace_id"),
        "parent_id": _optional_attr(span, "parent_id"),
        "span_type": _span_type(data),
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def _export_object(value: object) -> dict[str, object]:
    """Call an SDK object's export method when available."""
    export = getattr(value, "export", None)
    if not callable(export):
        return {}
    exported = export()
    if isinstance(exported, Mapping):
        return dict(exported)
    return {}


def _object_id(value: object, attribute: str) -> str:
    """Return a stable object id from an SDK object attribute."""
    attr_value = _optional_attr(value, attribute)
    if isinstance(attr_value, str) and attr_value:
        return attr_value
    return f"agentreplay-{id(value)}"


def _optional_attr(value: object, attribute: str) -> object | None:
    """Read an optional attribute without raising."""
    return getattr(value, attribute, None)


def _optional_str_attr(value: object, attribute: str) -> str | None:
    """Read an optional string attribute."""
    attr_value = _optional_attr(value, attribute)
    return attr_value if isinstance(attr_value, str) else None


def _optional_string(value: object) -> str | None:
    """Return a value as a string when it is present."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _tool_name(payload: Mapping[str, JSONValue]) -> str:
    """Extract a tool name from a span payload."""
    value = payload.get("name") or payload.get("tool_name")
    return value if isinstance(value, str) and value else "openai_tool"


def _tool_object_name(tool: object, context: object) -> str:
    """Extract a tool name from SDK hook arguments."""
    for candidate in (
        _optional_attr(context, "tool_name"),
        _optional_attr(tool, "name"),
        _optional_attr(tool, "__name__"),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate
    return type(tool).__name__


def _agent_name(agent: object) -> str:
    """Extract a readable agent name."""
    name = _optional_attr(agent, "name")
    if isinstance(name, str) and name:
        return name
    return type(agent).__name__


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    """Return a mapping or an empty mapping."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return {}


def _mapping_or_none(value: object) -> Mapping[str, object] | None:
    """Return a mapping when value has mapping shape."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, object], value)
    return None


def _int_or_none(value: object) -> int | None:
    """Parse an optional integer value."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return None


def _float_or_none(value: object) -> float | None:
    """Parse an optional float value."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _message_content(item: Mapping[Any, object]) -> str | None:
    """Extract text content from a model input item."""
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(
        content,
        str | bytes | bytearray,
    ):
        parts: list[str] = []
        for part in content:
            if isinstance(part, Mapping):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else None
    return None


def _prompt_value(value: str, config: OpenAIAgentsConfig) -> str:
    """Return a prompt value honoring prompt visibility settings."""
    if config.hide_prompts:
        return _HIDDEN
    if config.redact_api_keys:
        return _redact_string(value)
    return value


def _clean_value(value: object, *, config: OpenAIAgentsConfig) -> object:
    """Clean a user-provided value according to adapter configuration."""
    if config.hide_prompts and isinstance(value, str):
        return _HIDDEN
    if config.redact_api_keys:
        return _redact_value(value)
    return value


def _clean_mapping(
    value: Mapping[Any, object],
    *,
    redact_api_keys: bool,
) -> dict[str, JSONValue]:
    """Return a JSON-compatible mapping with optional key redaction."""
    cleaned: dict[str, JSONValue] = {}
    serializer = EventSerializer()
    for key, item in value.items():
        key_text = str(key)
        if redact_api_keys and _sensitive_key(key_text):
            cleaned[key_text] = _REDACTED
        else:
            cleaned[key_text] = serializer.serialize_value(
                _redact_value(item) if redact_api_keys else item,
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
    """Redact common OpenAI-style API key tokens from strings."""
    words = value.split()
    redacted = [
        _REDACTED if word.startswith(("sk-", "sess-", "Bearer ")) else word
        for word in words
    ]
    return " ".join(redacted)


def _sensitive_key(key: str) -> bool:
    """Return whether a key name likely contains credentials."""
    normalized = key.replace("-", "_").lower()
    return any(marker in normalized for marker in _API_KEY_MARKERS)


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
    """Split a comma-separated environment value."""
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _is_coroutine_callable(value: Callable[..., object]) -> bool:
    """Return whether a callable is an async function."""
    import inspect

    return inspect.iscoroutinefunction(value)


async def _maybe_await(target: object, method: str, *args: object) -> None:
    """Invoke an optional hook method and await it when needed."""
    if target is None:
        return
    callback = getattr(target, method, None)
    if not callable(callback):
        return
    result = callback(*args)
    if isinstance(result, Awaitable):
        await result


def _safe_repr(value: object) -> str:
    """Return a bounded representation for metadata."""
    text = repr(value)
    return text if len(text) <= 500 else f"{text[:497]}..."


__all__ = [
    "AgentReplay",
    "OpenAIAgentsConfig",
    "OpenAIAgentsHooks",
    "OpenAIAgentsTraceProcessor",
    "instrument",
    "record_agent",
]
