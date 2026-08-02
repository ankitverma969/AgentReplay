"""Exception hierarchy for AgentReplay."""


class AgentReplayError(Exception):
    """Base class for all AgentReplay exceptions."""


class ConfigurationError(AgentReplayError):
    """Raised when configuration cannot be loaded or validated."""


class StorageError(AgentReplayError):
    """Raised when a storage backend fails."""


class SerializationError(AgentReplayError):
    """Raised when trace data cannot be serialized or deserialized."""


class ReplayError(AgentReplayError):
    """Raised when replay cannot proceed under the selected policy."""


class DiffError(AgentReplayError):
    """Raised when trace comparison cannot be completed."""


class AdapterError(AgentReplayError):
    """Raised when a framework adapter fails."""


class PluginError(AgentReplayError):
    """Raised when plugin discovery, validation, or execution fails."""


class InstrumentationError(AdapterError):
    """Raised when adapter instrumentation cannot be installed or removed."""


class RedactionError(AgentReplayError):
    """Raised when sensitive-data redaction fails."""


__all__ = [
    "AdapterError",
    "AgentReplayError",
    "ConfigurationError",
    "DiffError",
    "InstrumentationError",
    "PluginError",
    "RedactionError",
    "ReplayError",
    "SerializationError",
    "StorageError",
]
