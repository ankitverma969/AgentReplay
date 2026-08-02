"""Typed observability models for AgentReplay telemetry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue, Metadata

TelemetryExporterName: TypeAlias = Literal[
    "console",
    "json",
    "file",
    "otlp_grpc",
    "otlp_http",
]
SamplingStrategy: TypeAlias = Literal[
    "always_on",
    "always_off",
    "ratio",
    "parent_based",
    "custom",
]
SpanStatus: TypeAlias = Literal["unset", "ok", "error"]
Compression: TypeAlias = Literal["none", "gzip"]
AttributeEnricher: TypeAlias = Callable[[Metadata], Metadata]


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """Correlation identifiers attached to telemetry."""

    trace_id: str | None = None
    run_id: str | None = None
    request_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    custom_ids: Mapping[str, str] = field(default_factory=dict)
    baggage: Mapping[str, str] = field(default_factory=dict)

    def attributes(self) -> Metadata:
        """Return correlation identifiers as telemetry attributes."""
        attributes: dict[str, JSONValue] = {}
        for key, value in (
            ("agentreplay.trace_id", self.trace_id),
            ("agentreplay.run_id", self.run_id),
            ("agentreplay.request_id", self.request_id),
            ("agentreplay.session_id", self.session_id),
            ("enduser.id", self.user_id),
        ):
            if value is not None:
                attributes[key] = value
        for key, value in self.custom_ids.items():
            attributes[f"agentreplay.correlation.{key}"] = value
        for key, value in self.baggage.items():
            attributes[f"baggage.{key}"] = value
        return attributes


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    """Runtime configuration for AgentReplay observability."""

    enabled: bool = False
    exporter: TelemetryExporterName = "console"
    endpoint: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)
    service_name: str = "agentreplay"
    service_namespace: str | None = None
    deployment_environment: str | None = None
    sampling: SamplingStrategy = "always_on"
    sampling_ratio: float = 1.0
    timeout_ms: int = 10_000
    tls_enabled: bool = True
    compression: Compression = "none"
    file_path: str | None = None
    batch_size: int = 512
    queue_size: int = 2048
    graceful_shutdown_ms: int = 5_000
    auth_token: str | None = None


@dataclass(frozen=True, slots=True)
class TelemetryLink:
    """OpenTelemetry-compatible span link metadata."""

    trace_id: str
    span_id: str
    attributes: Metadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible link representation."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    """OpenTelemetry-compatible event attached to a span."""

    name: str
    timestamp: datetime
    attributes: Metadata = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible event representation."""
        return {
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "attributes": dict(self.attributes),
        }


@dataclass(frozen=True, slots=True)
class TelemetrySpan:
    """OpenTelemetry-compatible span derived from an AgentReplay event."""

    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    status: SpanStatus
    attributes: Metadata
    events: tuple[TelemetryEvent, ...] = ()
    links: tuple[TelemetryLink, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible span representation."""
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_ms": self.duration_ms,
            "status": self.status,
            "attributes": dict(self.attributes),
            "events": [event.to_dict() for event in self.events],
            "links": [link.to_dict() for link in self.links],
        }


@dataclass(frozen=True, slots=True)
class TelemetryTrace:
    """OpenTelemetry-compatible trace derived from one AgentReplay run."""

    trace_id: str
    run_id: str
    name: str
    start_time: datetime
    end_time: datetime | None
    attributes: Metadata
    resource: Metadata
    spans: tuple[TelemetrySpan, ...]
    correlation: CorrelationContext = field(default_factory=CorrelationContext)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible trace representation."""
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "attributes": dict(self.attributes),
            "resource": dict(self.resource),
            "correlation": self.correlation.attributes(),
            "spans": [span.to_dict() for span in self.spans],
        }


@dataclass(frozen=True, slots=True)
class TelemetryMetrics:
    """Aggregated observability metrics for AgentReplay traces."""

    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    retry_count: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    average_tokens: float = 0.0
    average_cost: float = 0.0
    tool_usage: Mapping[str, int] = field(default_factory=dict)
    model_usage: Mapping[str, int] = field(default_factory=dict)
    memory_reads: int = 0
    memory_writes: int = 0
    replay_count: int = 0
    diff_count: int = 0
    export_count: int = 0
    plugin_count: int = 0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible metrics representation."""
        return {
            "run_count": self.run_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "retry_count": self.retry_count,
            "average_latency_ms": self.average_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "average_tokens": self.average_tokens,
            "average_cost": self.average_cost,
            "tool_usage": dict(self.tool_usage),
            "model_usage": dict(self.model_usage),
            "memory_reads": self.memory_reads,
            "memory_writes": self.memory_writes,
            "replay_count": self.replay_count,
            "diff_count": self.diff_count,
            "export_count": self.export_count,
            "plugin_count": self.plugin_count,
        }


@dataclass(frozen=True, slots=True)
class TelemetryExportResult:
    """Result returned by telemetry exporters."""

    exporter: str
    succeeded: bool
    message: str
    exported_spans: int = 0
    output: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible export result."""
        return {
            "exporter": self.exporter,
            "succeeded": self.succeeded,
            "message": self.message,
            "exported_spans": self.exported_spans,
            "output": self.output,
        }


__all__ = [
    "AttributeEnricher",
    "Compression",
    "CorrelationContext",
    "ObservabilityConfig",
    "SamplingStrategy",
    "SpanStatus",
    "TelemetryEvent",
    "TelemetryExportResult",
    "TelemetryExporterName",
    "TelemetryLink",
    "TelemetryMetrics",
    "TelemetrySpan",
    "TelemetryTrace",
]
