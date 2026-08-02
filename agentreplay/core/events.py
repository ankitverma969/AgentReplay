"""Event records and event schema names for AgentReplay traces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Final

from agentreplay.types import JSONValue, Metadata

EventType = str

RUN_STARTED: Final[EventType] = "run.started"
RUN_FINISHED: Final[EventType] = "run.finished"
USER_PROMPT: Final[EventType] = "prompt.user"
SYSTEM_PROMPT: Final[EventType] = "prompt.system"
ASSISTANT_RESPONSE: Final[EventType] = "response.assistant"
LLM_REQUEST: Final[EventType] = "llm.request"
LLM_RESPONSE: Final[EventType] = "llm.response"
TOOL_CALL: Final[EventType] = "tool.call"
TOOL_RESULT: Final[EventType] = "tool.result"
TOOL_STARTED: Final[EventType] = "tool.started"
TOOL_FINISHED: Final[EventType] = "tool.finished"
TOOL_FAILED: Final[EventType] = "tool.failed"
FUNCTION_CALL: Final[EventType] = "function.call"
MEMORY_READ: Final[EventType] = "memory.read"
MEMORY_WRITE: Final[EventType] = "memory.write"
CUSTOM_EVENT: Final[EventType] = "custom.event"
WARNING_RAISED: Final[EventType] = "warning.raised"
AGENT_STEP_STARTED: Final[EventType] = "agent.step.started"
AGENT_STEP_FINISHED: Final[EventType] = "agent.step.finished"
EXCEPTION_RAISED: Final[EventType] = "exception.raised"
RETRY_RECORDED: Final[EventType] = "retry.recorded"
METADATA_RECORDED: Final[EventType] = "metadata.recorded"
TOKEN_USAGE_RECORDED: Final[EventType] = "token_usage.recorded"
COST_RECORDED: Final[EventType] = "cost.recorded"
LATENCY_RECORDED: Final[EventType] = "latency.recorded"

KNOWN_EVENT_TYPES: Final[tuple[EventType, ...]] = (
    RUN_STARTED,
    RUN_FINISHED,
    USER_PROMPT,
    SYSTEM_PROMPT,
    ASSISTANT_RESPONSE,
    LLM_REQUEST,
    LLM_RESPONSE,
    TOOL_CALL,
    TOOL_RESULT,
    TOOL_STARTED,
    TOOL_FINISHED,
    TOOL_FAILED,
    FUNCTION_CALL,
    MEMORY_READ,
    MEMORY_WRITE,
    CUSTOM_EVENT,
    WARNING_RAISED,
    AGENT_STEP_STARTED,
    AGENT_STEP_FINISHED,
    EXCEPTION_RAISED,
    RETRY_RECORDED,
    METADATA_RECORDED,
    TOKEN_USAGE_RECORDED,
    COST_RECORDED,
    LATENCY_RECORDED,
)


@dataclass(frozen=True, slots=True)
class EventRecord:
    """Immutable in-memory record of one observed execution event."""

    event_id: str
    run_id: str
    parent_event_id: str | None
    sequence: int
    event_type: EventType
    timestamp: datetime
    duration_ms: float
    metadata: Metadata
    payload: Metadata

    def __post_init__(self) -> None:
        """Make payload and metadata mappings immutable after construction."""
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible dictionary representation."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "parent_event_id": self.parent_event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "metadata": dict(self.metadata),
            "payload": dict(self.payload),
        }


__all__ = [
    "AGENT_STEP_FINISHED",
    "AGENT_STEP_STARTED",
    "ASSISTANT_RESPONSE",
    "COST_RECORDED",
    "CUSTOM_EVENT",
    "EXCEPTION_RAISED",
    "EventRecord",
    "EventType",
    "FUNCTION_CALL",
    "KNOWN_EVENT_TYPES",
    "LATENCY_RECORDED",
    "LLM_REQUEST",
    "LLM_RESPONSE",
    "MEMORY_READ",
    "MEMORY_WRITE",
    "METADATA_RECORDED",
    "RETRY_RECORDED",
    "RUN_FINISHED",
    "RUN_STARTED",
    "SYSTEM_PROMPT",
    "TOKEN_USAGE_RECORDED",
    "TOOL_CALL",
    "TOOL_FAILED",
    "TOOL_FINISHED",
    "TOOL_RESULT",
    "TOOL_STARTED",
    "USER_PROMPT",
    "WARNING_RAISED",
]
