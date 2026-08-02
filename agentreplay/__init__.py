"""Public package interface for AgentReplay."""

from agentreplay.adapters.openai_agents import (
    AgentReplay,
    OpenAIAgentsConfig,
    instrument,
    record_agent,
)
from agentreplay.api import configure, create_container, get_settings, reset_settings
from agentreplay.diff import DiffEngine
from agentreplay.exceptions import (
    AdapterError,
    AgentReplayError,
    ConfigurationError,
    DiffError,
    InstrumentationError,
    PluginError,
    RedactionError,
    ReplayError,
    SerializationError,
    StorageError,
)
from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginManager
from agentreplay.recording import Recorder, record
from agentreplay.replay import ReplayEngine
from agentreplay.security import (
    RedactionStrategy,
    SecurityConfig,
    SecurityEngine,
    SecurityFinding,
    SecurityReport,
    SecurityRule,
)
from agentreplay.storage import (
    EventQuery,
    Pagination,
    RunQuery,
    SQLiteStorage,
    StorageBackend,
)
from agentreplay.version import __version__

__all__ = [
    "__version__",
    "AdapterError",
    "AgentReplay",
    "AgentReplayError",
    "ConfigurationError",
    "DiffEngine",
    "DiffError",
    "EventQuery",
    "InstrumentationError",
    "OpenAIAgentsConfig",
    "Pagination",
    "PluginApp",
    "PluginError",
    "PluginManager",
    "RedactionError",
    "RedactionStrategy",
    "ReplayError",
    "ReplayEngine",
    "Recorder",
    "RunQuery",
    "SecurityConfig",
    "SecurityEngine",
    "SecurityFinding",
    "SecurityReport",
    "SecurityRule",
    "SerializationError",
    "SQLiteStorage",
    "StorageError",
    "StorageBackend",
    "AgentReplayPlugin",
    "configure",
    "create_container",
    "get_settings",
    "instrument",
    "record",
    "record_agent",
    "reset_settings",
]
