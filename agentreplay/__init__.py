"""Public package interface for AgentReplay."""

from agentreplay.adapters.openai_agents import (
    AgentReplay,
    OpenAIAgentsConfig,
    instrument,
    record_agent,
)
from agentreplay.api import configure, create_container, get_settings, reset_settings
from agentreplay.debugger import DebuggerEngine, DebuggerSession
from agentreplay.diff import DiffEngine
from agentreplay.exceptions import (
    AdapterError,
    AgentReplayError,
    ConfigurationError,
    DebuggerError,
    DiffError,
    InstrumentationError,
    ObservabilityError,
    PluginError,
    ProfilerError,
    RedactionError,
    ReplayError,
    SerializationError,
    StorageError,
)
from agentreplay.observability import (
    CorrelationContext,
    ObservabilityConfig,
    ObservabilityEngine,
    TelemetryExportResult,
    TelemetryMetrics,
    TelemetryTrace,
)
from agentreplay.plugins import AgentReplayPlugin, PluginApp, PluginManager
from agentreplay.profiler import ProfilerEngine, ProfilingReport
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
    "DebuggerEngine",
    "DebuggerError",
    "DebuggerSession",
    "DiffEngine",
    "DiffError",
    "EventQuery",
    "InstrumentationError",
    "ObservabilityConfig",
    "ObservabilityEngine",
    "ObservabilityError",
    "OpenAIAgentsConfig",
    "Pagination",
    "PluginApp",
    "PluginError",
    "PluginManager",
    "ProfilerEngine",
    "ProfilerError",
    "ProfilingReport",
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
    "TelemetryExportResult",
    "TelemetryMetrics",
    "TelemetryTrace",
    "AgentReplayPlugin",
    "CorrelationContext",
    "configure",
    "create_container",
    "get_settings",
    "instrument",
    "record",
    "record_agent",
    "reset_settings",
]
