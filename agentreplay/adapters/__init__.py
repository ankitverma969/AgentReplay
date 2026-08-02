"""Framework adapter package for AgentReplay."""

from agentreplay.adapters.base import AgentReplayAdapter
from agentreplay.adapters.registry import AdapterRegistry

__all__ = ["AdapterRegistry", "AgentReplayAdapter"]
