"""Stable public SDK models for AgentReplay extensions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue, Metadata

SDKEventName: TypeAlias = Literal[
    "run.started",
    "run.finished",
    "event.created",
    "replay.started",
    "replay.finished",
    "export.started",
    "export.finished",
    "profiler.finished",
    "regression.finished",
]
SDKHookName: TypeAlias = Literal[
    "before_recording",
    "after_recording",
    "before_replay",
    "after_replay",
    "before_export",
    "after_export",
    "before_report",
    "after_report",
    "before_storage",
    "after_storage",
]
SDKExtensionKind: TypeAlias = Literal[
    "analyzer",
    "exporter",
    "storage",
    "visualization",
    "framework_adapter",
    "report",
    "cli_command",
]
SDKStability: TypeAlias = Literal["stable", "preview", "deprecated"]


@dataclass(frozen=True, slots=True)
class SDKVersion:
    """AgentReplay SDK semantic version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> SDKVersion:
        """Parse a semantic version string."""
        pieces = value.split(".")
        if len(pieces) != 3:
            msg = f"Invalid SDK semantic version: {value}"
            raise ValueError(msg)
        return cls(*(int(piece) for piece in pieces))

    def __str__(self) -> str:
        """Return semantic version text."""
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class SDKCompatibility:
    """Compatibility declaration for one extension."""

    min_sdk_version: str = "0.1.0"
    max_sdk_version: str | None = None
    python_requires: str = ">=3.11"


@dataclass(frozen=True, slots=True)
class SDKExtensionMetadata:
    """Metadata for one public SDK extension."""

    name: str
    version: str
    kind: SDKExtensionKind
    summary: str = ""
    compatibility: SDKCompatibility = SDKCompatibility()
    stability: SDKStability = "stable"
    config_schema: Metadata = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate extension metadata."""
        if not self.name.strip():
            msg = "SDK extension name must not be empty."
            raise ValueError(msg)
        SDKVersion.parse(self.version)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible metadata representation."""
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "summary": self.summary,
            "compatibility": {
                "min_sdk_version": self.compatibility.min_sdk_version,
                "max_sdk_version": self.compatibility.max_sdk_version,
                "python_requires": self.compatibility.python_requires,
            },
            "stability": self.stability,
            "config_schema": self.config_schema,
        }


@dataclass(frozen=True, slots=True)
class SDKEvent:
    """Typed event emitted through the public SDK event bus."""

    name: SDKEventName
    payload: Metadata = field(default_factory=dict)
    source: str = "agentreplay"
    emitted_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible event representation."""
        return {
            "name": self.name,
            "payload": self.payload,
            "source": self.source,
            "emitted_at": self.emitted_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class SDKHookContext:
    """Context passed to public SDK hooks."""

    hook: SDKHookName
    payload: Metadata = field(default_factory=dict)
    extension_name: str | None = None


@dataclass(frozen=True, slots=True)
class SDKHookResult:
    """Result of invoking one SDK hook handler."""

    hook: SDKHookName
    extension_name: str
    succeeded: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyzerResult:
    """Result returned by SDK analyzers."""

    analyzer: str
    findings: tuple[Metadata, ...] = ()
    metrics: Metadata = field(default_factory=dict)
    recommendations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible analyzer result."""
        return {
            "analyzer": self.analyzer,
            "findings": [dict(item) for item in self.findings],
            "metrics": self.metrics,
            "recommendations": list(self.recommendations),
        }


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Result returned by SDK exporters."""

    exporter: str
    content_type: str
    bytes_written: int
    uri: str | None = None
    metadata: Metadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible exporter result."""
        return {
            "exporter": self.exporter,
            "content_type": self.content_type,
            "bytes_written": self.bytes_written,
            "uri": self.uri,
            "metadata": self.metadata,
        }


@dataclass(frozen=True, slots=True)
class ReportSection:
    """Custom report section returned by SDK report extensions."""

    title: str
    html: str
    order: int = 100
    metadata: Metadata = field(default_factory=dict)


__all__ = [
    "AnalyzerResult",
    "ExportResult",
    "ReportSection",
    "SDKCompatibility",
    "SDKEvent",
    "SDKEventName",
    "SDKExtensionKind",
    "SDKExtensionMetadata",
    "SDKHookContext",
    "SDKHookName",
    "SDKHookResult",
    "SDKStability",
    "SDKVersion",
]
