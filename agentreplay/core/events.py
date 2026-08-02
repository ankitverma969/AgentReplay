"""Event schema names for AgentReplay traces."""

from typing import Final, Literal, TypeAlias

EventType: TypeAlias = Literal[
    "run.started",
    "run.finished",
    "llm.request",
    "llm.response",
    "tool.call",
    "tool.result",
    "agent.step.started",
    "agent.step.finished",
    "exception.raised",
    "metadata.recorded",
    "token_usage.recorded",
]

RUN_STARTED: Final[EventType] = "run.started"
RUN_FINISHED: Final[EventType] = "run.finished"
LLM_REQUEST: Final[EventType] = "llm.request"
LLM_RESPONSE: Final[EventType] = "llm.response"
TOOL_CALL: Final[EventType] = "tool.call"
TOOL_RESULT: Final[EventType] = "tool.result"
AGENT_STEP_STARTED: Final[EventType] = "agent.step.started"
AGENT_STEP_FINISHED: Final[EventType] = "agent.step.finished"
EXCEPTION_RAISED: Final[EventType] = "exception.raised"
METADATA_RECORDED: Final[EventType] = "metadata.recorded"
TOKEN_USAGE_RECORDED: Final[EventType] = "token_usage.recorded"

__all__ = [
    "AGENT_STEP_FINISHED",
    "AGENT_STEP_STARTED",
    "EXCEPTION_RAISED",
    "EventType",
    "LLM_REQUEST",
    "LLM_RESPONSE",
    "METADATA_RECORDED",
    "RUN_FINISHED",
    "RUN_STARTED",
    "TOKEN_USAGE_RECORDED",
    "TOOL_CALL",
    "TOOL_RESULT",
]
