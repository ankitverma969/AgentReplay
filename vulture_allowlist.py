"""Vulture allowlist for public extension and packaging entry points.

AgentReplay intentionally exposes many symbols through public APIs, plugin
protocols, CLI discovery, and documentation examples. Static dead-code checks
cannot always see those dynamic call paths, so this file references stable
entry points that must remain available for users and third-party extensions.
"""

from agentreplay import (
    AgentReplay,
    DiffEngine,
    ProfilerEngine,
    Recorder,
    ReplayEngine,
    ReportingEngine,
    ReportOptions,
    SQLiteStorage,
    record,
)
from agentreplay.sdk import (
    AgentReplaySDK,
    AnalyzerResult,
    ExportResult,
    SDKContext,
    SDKExtensionMetadata,
    create_sdk,
)

PUBLIC_API = (
    AgentReplay,
    DiffEngine,
    ProfilerEngine,
    Recorder,
    ReplayEngine,
    ReportOptions,
    ReportingEngine,
    SQLiteStorage,
    record,
    AgentReplaySDK,
    AnalyzerResult,
    ExportResult,
    SDKContext,
    SDKExtensionMetadata,
    create_sdk,
)
