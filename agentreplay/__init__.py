"""Public package interface for AgentReplay."""

from agentreplay.api import configure, create_container, get_settings, reset_settings
from agentreplay.exceptions import (
    AdapterError,
    AgentReplayError,
    ConfigurationError,
    DiffError,
    InstrumentationError,
    RedactionError,
    ReplayError,
    SerializationError,
    StorageError,
)
from agentreplay.recording import Recorder, record
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
    "AgentReplayError",
    "ConfigurationError",
    "DiffError",
    "EventQuery",
    "InstrumentationError",
    "Pagination",
    "RedactionError",
    "ReplayError",
    "Recorder",
    "RunQuery",
    "SerializationError",
    "SQLiteStorage",
    "StorageError",
    "StorageBackend",
    "configure",
    "create_container",
    "get_settings",
    "record",
    "reset_settings",
]
