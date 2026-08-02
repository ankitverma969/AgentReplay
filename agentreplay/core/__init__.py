"""Core domain records for AgentReplay traces and run metadata."""

from agentreplay.core.events import EventRecord, EventType
from agentreplay.core.runs import RunRecord, RunStatus
from agentreplay.core.traces import TraceSnapshot

__all__ = ["EventRecord", "EventType", "RunRecord", "RunStatus", "TraceSnapshot"]
