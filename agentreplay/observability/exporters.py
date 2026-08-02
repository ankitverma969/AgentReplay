"""Telemetry exporters for AgentReplay observability."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Protocol

from agentreplay.exceptions import ObservabilityError
from agentreplay.observability.models import (
    ObservabilityConfig,
    TelemetryExportResult,
    TelemetryTrace,
)


class TelemetryExporter(Protocol):
    """Protocol implemented by telemetry exporters."""

    name: str

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Export one telemetry trace."""

    def shutdown(self) -> None:
        """Flush and close exporter resources."""


class ConsoleTelemetryExporter:
    """Human-readable telemetry exporter for local debugging."""

    name = "console"

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Render a telemetry trace as text."""
        lines = [
            f"Trace {trace.trace_id} ({trace.name})",
            f"Run: {trace.run_id}",
            f"Spans: {len(trace.spans)}",
        ]
        for span in trace.spans:
            parent = f" parent={span.parent_span_id}" if span.parent_span_id else ""
            lines.append(
                f"- {span.name} status={span.status} "
                f"duration_ms={span.duration_ms:.3f}{parent}"
            )
        output = "\n".join(lines)
        return TelemetryExportResult(
            exporter=self.name,
            succeeded=True,
            message="console telemetry rendered",
            exported_spans=len(trace.spans),
            output=output,
        )

    def shutdown(self) -> None:
        """No resources are held by the console exporter."""


class JSONTelemetryExporter:
    """JSON telemetry exporter."""

    name = "json"

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Render a telemetry trace as JSON."""
        output = json.dumps(trace.to_dict(), sort_keys=True)
        return TelemetryExportResult(
            exporter=self.name,
            succeeded=True,
            message="json telemetry rendered",
            exported_spans=len(trace.spans),
            output=output,
        )

    def shutdown(self) -> None:
        """No resources are held by the JSON exporter."""


class FileTelemetryExporter:
    """File telemetry exporter that writes JSON lines."""

    name = "file"

    def __init__(self, path: str | Path) -> None:
        """Create a file exporter."""
        self._path = Path(path).expanduser()

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Append one telemetry trace as a JSON line."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        output = json.dumps(trace.to_dict(), sort_keys=True)
        with self._path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(output)
            file_obj.write("\n")
        return TelemetryExportResult(
            exporter=self.name,
            succeeded=True,
            message=f"telemetry written to {self._path}",
            exported_spans=len(trace.spans),
            output=str(self._path),
        )

    def shutdown(self) -> None:
        """No long-lived file handle is held."""


class OpenTelemetryExporter:
    """OpenTelemetry SDK exporter for OTLP HTTP or gRPC backends."""

    def __init__(self, config: ObservabilityConfig) -> None:
        """Create an OTLP exporter from observability configuration."""
        self._config = config
        self.name = str(config.exporter)
        self._provider: Any | None = None
        self._tracer: Any | None = None
        self._configure()

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Export a telemetry trace through OpenTelemetry spans."""
        tracer = self._tracer
        if tracer is None:
            msg = "OpenTelemetry tracer is not configured."
            raise ObservabilityError(msg)
        with tracer.start_as_current_span(
            trace.name,
            attributes=dict(trace.attributes),
        ) as root_span:
            root_span.add_event(
                "agentreplay.run",
                attributes={"agentreplay.run.id": trace.run_id},
            )
            for span in trace.spans:
                with tracer.start_as_current_span(
                    span.name,
                    attributes=dict(span.attributes),
                ) as otel_span:
                    for event in span.events:
                        otel_span.add_event(
                            event.name,
                            attributes=dict(event.attributes),
                        )
                    if span.status == "error":
                        _set_error_status(otel_span)
        return TelemetryExportResult(
            exporter=self.name,
            succeeded=True,
            message="telemetry exported through OpenTelemetry",
            exported_spans=len(trace.spans),
        )

    def shutdown(self) -> None:
        """Flush OpenTelemetry provider resources."""
        provider = self._provider
        if provider is not None:
            shutdown = getattr(provider, "shutdown", None)
            if callable(shutdown):
                shutdown()

    def _configure(self) -> None:
        if not opentelemetry_available():
            msg = (
                "OpenTelemetry packages are not installed. "
                "Install agentreplay[otel] to use OTLP exporters."
            )
            raise ObservabilityError(msg)
        sdk_trace = _import("opentelemetry.sdk.trace")
        sdk_resources = _import("opentelemetry.sdk.resources")
        sdk_export = _import("opentelemetry.sdk.trace.export")
        otel_trace = _import("opentelemetry.trace")
        resource = sdk_resources.Resource.create(_otel_resource(self._config))
        provider = sdk_trace.TracerProvider(resource=resource)
        exporter = _otlp_exporter(self._config)
        processor = sdk_export.BatchSpanProcessor(
            exporter,
            max_queue_size=self._config.queue_size,
            max_export_batch_size=self._config.batch_size,
            schedule_delay_millis=min(self._config.timeout_ms, 5_000),
        )
        provider.add_span_processor(processor)
        otel_trace.set_tracer_provider(provider)
        self._provider = provider
        self._tracer = otel_trace.get_tracer("agentreplay")


def build_exporter(config: ObservabilityConfig) -> TelemetryExporter:
    """Build a telemetry exporter from configuration."""
    if config.exporter == "console":
        return ConsoleTelemetryExporter()
    if config.exporter == "json":
        return JSONTelemetryExporter()
    if config.exporter == "file":
        return FileTelemetryExporter(config.file_path or ".agentreplay/telemetry.jsonl")
    if config.exporter in {"otlp_grpc", "otlp_http"}:
        return OpenTelemetryExporter(config)
    msg = f"Unsupported telemetry exporter: {config.exporter}"
    raise ObservabilityError(msg)


def opentelemetry_available() -> bool:
    """Return whether required OpenTelemetry packages are importable."""
    return (
        importlib.util.find_spec("opentelemetry") is not None
        and importlib.util.find_spec("opentelemetry.sdk.trace") is not None
    )


def _otlp_exporter(config: ObservabilityConfig) -> Any:
    if config.exporter == "otlp_http":
        module = _import("opentelemetry.exporter.otlp.proto.http.trace_exporter")
        cls = module.OTLPSpanExporter
    else:
        module = _import("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
        cls = module.OTLPSpanExporter
    headers = dict(config.headers)
    if config.auth_token is not None:
        headers.setdefault("authorization", f"Bearer {config.auth_token}")
    kwargs: dict[str, Any] = {
        "endpoint": config.endpoint,
        "headers": headers or None,
        "timeout": config.timeout_ms / 1000,
    }
    if config.exporter == "otlp_grpc":
        kwargs["insecure"] = not config.tls_enabled
    if config.compression != "none":
        kwargs["compression"] = config.compression
    return cls(**{key: value for key, value in kwargs.items() if value is not None})


def _otel_resource(config: ObservabilityConfig) -> dict[str, str]:
    resource = {
        "service.name": config.service_name,
        "telemetry.sdk.name": "agentreplay",
        "telemetry.sdk.language": "python",
    }
    if config.service_namespace is not None:
        resource["service.namespace"] = config.service_namespace
    if config.deployment_environment is not None:
        resource["deployment.environment"] = config.deployment_environment
    return resource


def _set_error_status(span: Any) -> None:
    try:
        status_module = _import("opentelemetry.trace.status")
        span.set_status(status_module.Status(status_module.StatusCode.ERROR))
    except Exception:
        return


def _import(module_name: str) -> Any:
    return __import__(module_name, fromlist=["*"])


__all__ = [
    "ConsoleTelemetryExporter",
    "FileTelemetryExporter",
    "JSONTelemetryExporter",
    "OpenTelemetryExporter",
    "TelemetryExporter",
    "build_exporter",
    "opentelemetry_available",
]
