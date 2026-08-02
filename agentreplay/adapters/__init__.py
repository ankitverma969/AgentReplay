"""Framework adapter package for AgentReplay."""

from agentreplay.adapters.base import AgentReplayAdapter
from agentreplay.adapters.openai_agents import (
    AgentReplay,
    OpenAIAgentsConfig,
    OpenAIAgentsHooks,
    OpenAIAgentsTraceProcessor,
    instrument,
    record_agent,
)
from agentreplay.adapters.registry import AdapterRegistry

__all__ = [
    "AdapterRegistry",
    "AgentReplay",
    "AgentReplayAdapter",
    "OpenAIAgentsConfig",
    "OpenAIAgentsHooks",
    "OpenAIAgentsTraceProcessor",
    "instrument",
    "record_agent",
]
