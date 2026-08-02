"""Framework adapter package for AgentReplay."""

from agentreplay.adapters.base import AgentReplayAdapter
from agentreplay.adapters.langgraph import (
    AgentReplay as LangGraphAgentReplay,
)
from agentreplay.adapters.langgraph import (
    LangGraphCallbackHandler,
    LangGraphConfig,
    LangGraphInstrumentedGraph,
)
from agentreplay.adapters.langgraph import (
    instrument as instrument_langgraph,
)
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
    "LangGraphAgentReplay",
    "LangGraphCallbackHandler",
    "LangGraphConfig",
    "LangGraphInstrumentedGraph",
    "OpenAIAgentsConfig",
    "OpenAIAgentsHooks",
    "OpenAIAgentsTraceProcessor",
    "instrument",
    "instrument_langgraph",
    "record_agent",
]
