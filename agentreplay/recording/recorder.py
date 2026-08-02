"""In-memory event recorder for AgentReplay."""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextvars import Token
from dataclasses import dataclass
from threading import RLock
from time import perf_counter
from typing import Literal, ParamSpec, TypeVar, cast, overload

from agentreplay.container import Container, create_container
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
    EventRecord,
    EventType,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import AgentReplayError
from agentreplay.recording.context import ActiveSession, SessionManager
from agentreplay.recording.event_manager import EventManager
from agentreplay.recording.metadata import MetadataCollector
from agentreplay.recording.run_manager import RunFinishStatus, RunManager
from agentreplay.recording.serializers import EventSerializer

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(slots=True)
class RunContext:
    """Context manager that records one run on an existing recorder."""

    recorder: Recorder
    name: str | None = None
    metadata: Mapping[str, object] | None = None
    tags: Sequence[str] = ()
    run_id: str | None = None

    def __enter__(self) -> Recorder:
        """Start a run and return the recorder."""
        self.run_id = self.recorder.start_run(
            name=self.name,
            metadata=self.metadata,
            tags=self.tags,
        )
        return self.recorder

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> Literal[False]:
        """Finish the run and preserve user exceptions."""
        if self.run_id is not None:
            if exc is not None:
                self.recorder.record_exception(exc)
            self.recorder.end_run(
                self.run_id,
                status="failed" if exc is not None else "completed",
            )
        return False

    async def __aenter__(self) -> Recorder:
        """Start a run in an async context and return the recorder."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        """Finish the run in an async context."""
        return self.__exit__(exc_type, exc, traceback)


@dataclass(slots=True)
class EventSpan:
    """Context manager that records the duration of one nested event."""

    recorder: Recorder
    event_type: EventType
    payload: Mapping[str, object] | None = None
    metadata: Mapping[str, object] | None = None
    event_id: str | None = None
    _started_at: float = 0.0
    _token: Token[ActiveSession | None] | None = None

    def __enter__(self) -> EventSpan:
        """Start recording the span event."""
        event = self.recorder.record_event(
            self.event_type,
            payload=self.payload,
            metadata=self.metadata,
            duration_ms=0.0,
        )
        self.event_id = event.event_id
        self._started_at = perf_counter()
        self._token = self.recorder._session_manager.push_event(event.event_id)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> Literal[False]:
        """Finish recording the span event and preserve user exceptions."""
        duration_ms = _elapsed_ms(self._started_at)
        if exc is not None:
            self.recorder.record_exception(exc)
        if self._token is not None:
            self.recorder._session_manager.pop_event(
                self._token,
            )
        if self.event_id is not None:
            self.recorder._event_manager.finish_event(
                self.event_id,
                duration_ms=duration_ms,
                metadata={"status": "failed" if exc is not None else "completed"},
            )
        return False

    async def __aenter__(self) -> EventSpan:
        """Start recording the span event in an async context."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        """Finish recording the span event in an async context."""
        return self.__exit__(exc_type, exc, traceback)


class Recorder:
    """Thread-safe in-memory recorder for AI agent execution events."""

    def __init__(
        self,
        *,
        name: str | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: Sequence[str] = (),
        auto_start: bool = True,
        container: Container | None = None,
        session_manager: SessionManager | None = None,
        serializer: EventSerializer | None = None,
        metadata_collector: MetadataCollector | None = None,
        run_manager: RunManager | None = None,
        event_manager: EventManager | None = None,
    ) -> None:
        """Create a recorder.

        Args:
            name: Optional run name used by context manager and decorator usage.
            metadata: Optional run metadata used by context manager usage.
            tags: Optional run tags.
            auto_start: Whether entering the context manager starts a run.
            container: Optional dependency container.
            session_manager: Optional session manager for tests or advanced use.
            serializer: Optional event serializer.
            metadata_collector: Optional metadata collector.
            run_manager: Optional run manager.
            event_manager: Optional event manager.
        """
        self._container = create_container() if container is None else container
        self._serializer = EventSerializer() if serializer is None else serializer
        self._metadata_collector = (
            MetadataCollector(self._serializer)
            if metadata_collector is None
            else metadata_collector
        )
        self._session_manager = (
            SessionManager() if session_manager is None else session_manager
        )
        self._run_manager = (
            RunManager(
                clock=self._container.clock,
                id_generator=self._container.id_generator,
                metadata_collector=self._metadata_collector,
            )
            if run_manager is None
            else run_manager
        )
        self._event_manager = (
            EventManager(
                clock=self._container.clock,
                id_generator=self._container.id_generator,
                serializer=self._serializer,
                metadata_collector=self._metadata_collector,
            )
            if event_manager is None
            else event_manager
        )
        self._context_name = name
        self._context_metadata = metadata
        self._context_tags = tuple(tags)
        self._auto_start = auto_start
        self._run_tokens: dict[str, Token[ActiveSession | None]] = {}
        self._last_run_id: str | None = None
        self._lock = RLock()

    def __enter__(self) -> Recorder:
        """Enter a recording context and start a run when configured."""
        if self._auto_start:
            self.start_run(
                name=self._context_name,
                metadata=self._context_metadata,
                tags=self._context_tags,
            )
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        exc: BaseException | None,
        _traceback: object,
    ) -> Literal[False]:
        """Exit a recording context, capturing exceptions without suppressing them."""
        active_run_id = self.current_run_id()
        if active_run_id is not None:
            if exc is not None:
                self.record_exception(exc)
            self.end_run(status="failed" if exc is not None else "completed")
        return False

    async def __aenter__(self) -> Recorder:
        """Enter an async recording context."""
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> Literal[False]:
        """Exit an async recording context."""
        return self.__exit__(exc_type, exc, traceback)

    def start_run(
        self,
        *,
        name: str | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: Sequence[str] = (),
    ) -> str:
        """Start a run and make it active in the current context."""
        run = self._run_manager.start_run(
            name=name,
            metadata=dict(metadata) if metadata is not None else None,
            tags=tuple(tags),
        )
        token = self._session_manager.enter_run(run.run_id)
        with self._lock:
            self._run_tokens[run.run_id] = token
            self._last_run_id = run.run_id
        self._event_manager.append_event(
            run_id=run.run_id,
            parent_event_id=None,
            event_type=RUN_STARTED,
            payload={"name": name, "tags": list(tags)},
            metadata=metadata,
        )
        return run.run_id

    def end_run(
        self,
        run_id: str | None = None,
        *,
        status: RunFinishStatus = "completed",
        metadata: Mapping[str, object] | None = None,
    ) -> RunRecord:
        """Finish a run and clear it from the active context when applicable."""
        resolved_run_id = self._resolve_active_run_id(run_id)
        self._event_manager.append_event(
            run_id=resolved_run_id,
            parent_event_id=None,
            event_type=RUN_FINISHED,
            payload={"status": status},
            metadata=metadata,
        )
        run = self._run_manager.finish_run(
            resolved_run_id,
            status=status,
            metadata=dict(metadata) if metadata is not None else None,
        )
        with self._lock:
            token = self._run_tokens.pop(resolved_run_id, None)
            self._last_run_id = resolved_run_id
        if token is not None and self.current_run_id() == resolved_run_id:
            self._session_manager.exit_run(token)
        return run

    def current_run_id(self) -> str | None:
        """Return the run id active in the current context."""
        return self._session_manager.active_run_id()

    def last_run_id(self) -> str | None:
        """Return the most recently started run id for this recorder."""
        with self._lock:
            return self._last_run_id

    def record_event(
        self,
        event_type: EventType,
        *,
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
        run_id: str | None = None,
        parent_event_id: str | None = None,
        duration_ms: float = 0.0,
    ) -> EventRecord:
        """Record a single event in the active run."""
        resolved_run_id = self._resolve_active_run_id(run_id)
        resolved_parent_event_id = (
            self._session_manager.active_parent_event_id()
            if parent_event_id is None
            else parent_event_id
        )
        return self._event_manager.append_event(
            run_id=resolved_run_id,
            event_type=event_type,
            parent_event_id=resolved_parent_event_id,
            payload=payload,
            metadata=metadata,
            duration_ms=duration_ms,
        )

    def span(
        self,
        event_type: EventType,
        *,
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventSpan:
        """Return a context manager that records one timed nested event."""
        return EventSpan(
            recorder=self,
            event_type=event_type,
            payload=payload,
            metadata=metadata,
        )

    def run(
        self,
        *,
        name: str | None = None,
        metadata: Mapping[str, object] | None = None,
        tags: Sequence[str] = (),
    ) -> RunContext:
        """Return a context manager for a run on this recorder."""
        return RunContext(
            recorder=self,
            name=name,
            metadata=metadata,
            tags=tags,
        )

    def user_prompt(
        self,
        prompt: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a user prompt."""
        return self.record_event(
            USER_PROMPT, payload={"prompt": prompt}, metadata=metadata
        )

    def system_prompt(
        self,
        prompt: str,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a system prompt."""
        return self.record_event(
            SYSTEM_PROMPT, payload={"prompt": prompt}, metadata=metadata
        )

    def assistant_response(
        self,
        response: object,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record an assistant response."""
        return self.record_event(
            ASSISTANT_RESPONSE,
            payload={"response": response},
            metadata=metadata,
        )

    def llm_request(
        self,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record an LLM request."""
        return self.record_event(
            LLM_REQUEST,
            payload=_merge_payload(
                payload,
                provider_name=provider_name,
                model_name=model_name,
            ),
            metadata=metadata,
        )

    def llm_response(
        self,
        *,
        provider_name: str | None = None,
        model_name: str | None = None,
        response: object | None = None,
        token_usage: Mapping[str, object] | None = None,
        cost: Mapping[str, object] | None = None,
        latency_ms: float | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record an LLM response with optional usage, cost, and latency."""
        payload: dict[str, object] = _merge_payload(
            None,
            provider_name=provider_name,
            model_name=model_name,
        )
        payload["response"] = response
        if token_usage is not None:
            payload["token_usage"] = token_usage
        if cost is not None:
            payload["cost"] = cost
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        return self.record_event(LLM_RESPONSE, payload=payload, metadata=metadata)

    def tool_started(
        self,
        tool_name: str,
        *,
        arguments: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record the start of a tool execution."""
        return self.record_event(
            TOOL_STARTED,
            payload={"tool_name": tool_name, "arguments": arguments or {}},
            metadata=metadata,
        )

    def tool_finished(
        self,
        tool_name: str,
        *,
        result: object | None = None,
        duration_ms: float = 0.0,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record successful completion of a tool execution."""
        return self.record_event(
            TOOL_FINISHED,
            payload={"tool_name": tool_name, "result": result},
            metadata=metadata,
            duration_ms=duration_ms,
        )

    def tool_failed(
        self,
        tool_name: str,
        exception: BaseException,
        *,
        duration_ms: float = 0.0,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record failed completion of a tool execution."""
        return self.record_event(
            TOOL_FAILED,
            payload={
                "tool_name": tool_name,
                "exception": self._serializer.serialize_exception(exception),
            },
            metadata=metadata,
            duration_ms=duration_ms,
        )

    def function_call(
        self,
        function_name: str,
        *,
        arguments: Mapping[str, object] | None = None,
        result: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a function call."""
        return self.record_event(
            FUNCTION_CALL,
            payload={
                "function_name": function_name,
                "arguments": arguments or {},
                "result": result,
            },
            metadata=metadata,
        )

    def memory_read(
        self,
        key: str,
        *,
        value: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a memory read."""
        return self.record_event(
            MEMORY_READ,
            payload={"key": key, "value": value},
            metadata=metadata,
        )

    def memory_write(
        self,
        key: str,
        *,
        value: object | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a memory write."""
        return self.record_event(
            MEMORY_WRITE,
            payload={"key": key, "value": value},
            metadata=metadata,
        )

    def custom_event(
        self,
        name: str,
        *,
        payload: Mapping[str, object] | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a custom event."""
        return self.record_event(
            CUSTOM_EVENT,
            payload=_merge_payload(payload, name=name),
            metadata=metadata,
        )

    def warning(
        self,
        message: str,
        *,
        category: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a warning event."""
        return self.record_event(
            WARNING_RAISED,
            payload={"message": message, "category": category},
            metadata=metadata,
        )

    def record_exception(
        self,
        exception: BaseException,
        *,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record an exception without suppressing or modifying it."""
        return self.record_event(
            EXCEPTION_RAISED,
            payload={"exception": self._serializer.serialize_exception(exception)},
            metadata=metadata,
        )

    def retry(
        self,
        *,
        attempt: int,
        reason: str | None = None,
        delay_ms: float | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record a retry decision."""
        return self.record_event(
            RETRY_RECORDED,
            payload={"attempt": attempt, "reason": reason, "delay_ms": delay_ms},
            metadata=metadata,
        )

    def token_usage(
        self,
        *,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        total_tokens: int | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record token usage when available."""
        return self.record_event(
            TOKEN_USAGE_RECORDED,
            payload={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
            },
            metadata=metadata,
        )

    def cost(
        self,
        *,
        amount: float,
        currency: str = "USD",
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record model or tool cost when provided by the caller."""
        return self.record_event(
            COST_RECORDED,
            payload={"amount": amount, "currency": currency},
            metadata=metadata,
        )

    def latency(
        self,
        *,
        latency_ms: float,
        operation: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> EventRecord:
        """Record an explicit latency measurement."""
        return self.record_event(
            LATENCY_RECORDED,
            payload={"latency_ms": latency_ms, "operation": operation},
            metadata=metadata,
            duration_ms=latency_ms,
        )

    def get_run(self, run_id: str) -> RunRecord:
        """Return a run record by id."""
        return self._run_manager.get_run(run_id)

    def list_runs(self) -> tuple[RunRecord, ...]:
        """Return all runs recorded by this recorder."""
        return self._run_manager.list_runs()

    def events(self, run_id: str | None = None) -> tuple[EventRecord, ...]:
        """Return recorded events for one run or all runs."""
        if run_id is None:
            return self._event_manager.all_events()
        return self._event_manager.events_for_run(run_id)

    def trace(self, run_id: str | None = None) -> TraceSnapshot:
        """Return an immutable trace snapshot for a run."""
        resolved_run_id = self._resolve_run_id(run_id)
        return TraceSnapshot(
            run=self._run_manager.get_run(resolved_run_id),
            events=self._event_manager.events_for_run(resolved_run_id),
        )

    def _resolve_active_run_id(self, run_id: str | None) -> str:
        """Resolve a run id for mutation and verify the run is still active."""
        if run_id is not None:
            self._run_manager.ensure_running(run_id)
            return run_id
        active_run_id = self.current_run_id()
        if active_run_id is None:
            msg = "No active AgentReplay run. Call start_run() before recording events."
            raise AgentReplayError(msg)
        self._run_manager.ensure_running(active_run_id)
        return active_run_id

    def _resolve_run_id(self, run_id: str | None) -> str:
        """Resolve an explicit run id or the active context-local run id."""
        if run_id is not None:
            return run_id
        active_run_id = self.current_run_id()
        if active_run_id is not None:
            return active_run_id
        last_run_id = self.last_run_id()
        if last_run_id is not None:
            return last_run_id
        msg = "No active AgentReplay run. Call start_run() before recording events."
        raise AgentReplayError(msg)


@overload
def record(func: Callable[P, R]) -> Callable[P, R]: ...


@overload
def record(
    func: None = None,
    *,
    name: str | None = None,
    metadata: Mapping[str, object] | None = None,
    tags: Sequence[str] = (),
    recorder: Recorder | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def record(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    metadata: Mapping[str, object] | None = None,
    tags: Sequence[str] = (),
    recorder: Recorder | None = None,
) -> Callable[P, R] | Callable[[Callable[P, R]], Callable[P, R]]:
    """Record a sync or async function execution with an in-memory recorder."""

    def decorate(target: Callable[P, R]) -> Callable[P, R]:
        run_name = name or target.__qualname__

        if inspect.iscoroutinefunction(target):

            @functools.wraps(target)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> object:
                active_recorder = (
                    Recorder(name=run_name, metadata=metadata, tags=tags)
                    if recorder is None
                    else recorder
                )
                async with active_recorder.run(
                    name=run_name,
                    metadata=metadata,
                    tags=tags,
                ):
                    result = target(*args, **kwargs)
                    return await cast(Awaitable[object], result)

            return cast(Callable[P, R], async_wrapper)

        @functools.wraps(target)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            active_recorder = (
                Recorder(name=run_name, metadata=metadata, tags=tags)
                if recorder is None
                else recorder
            )
            with active_recorder.run(
                name=run_name,
                metadata=metadata,
                tags=tags,
            ):
                return target(*args, **kwargs)

        return sync_wrapper

    if func is None:
        return decorate
    return decorate(func)


def _merge_payload(
    payload: Mapping[str, object] | None,
    **values: object,
) -> dict[str, object]:
    """Merge optional payload values into a new dictionary."""
    merged: dict[str, object] = dict(payload) if payload is not None else {}
    for key, value in values.items():
        if value is not None:
            merged[key] = value
    return merged


def _elapsed_ms(started_at: float) -> float:
    """Return elapsed milliseconds from a perf-counter timestamp."""
    return max((perf_counter() - started_at) * 1000.0, 0.0)


__all__ = ["EventSpan", "Recorder", "RunContext", "record"]
