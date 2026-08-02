"""Entry point naming conventions for AgentReplay plugins."""

from typing import Final

ADAPTER_ENTRY_POINT_GROUP: Final[str] = "agentreplay.adapters"
PLUGIN_ENTRY_POINT_GROUP: Final[str] = "agentreplay.plugins"

__all__ = ["ADAPTER_ENTRY_POINT_GROUP", "PLUGIN_ENTRY_POINT_GROUP"]
