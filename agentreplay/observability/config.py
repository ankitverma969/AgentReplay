"""Configuration helpers for AgentReplay observability."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from agentreplay.observability.models import (
    Compression,
    ObservabilityConfig,
    SamplingStrategy,
    TelemetryExporterName,
)

if TYPE_CHECKING:
    from agentreplay.config import Settings

_EXPORTERS = frozenset({"console", "json", "file", "otlp_grpc", "otlp_http"})
_SAMPLING = frozenset({"always_on", "always_off", "ratio", "parent_based", "custom"})
_COMPRESSION = frozenset({"none", "gzip"})


def observability_config_from_settings(settings: Settings) -> ObservabilityConfig:
    """Build observability config from resolved global settings."""
    return ObservabilityConfig(
        enabled=settings.observability_enabled,
        exporter=settings.observability_exporter,
        endpoint=settings.observability_endpoint,
        headers=settings.observability_headers,
        service_name=settings.observability_service_name,
        service_namespace=settings.observability_service_namespace,
        deployment_environment=settings.observability_environment,
        sampling=settings.observability_sampling,
        sampling_ratio=settings.observability_sampling_ratio,
        timeout_ms=settings.observability_timeout_ms,
        tls_enabled=settings.observability_tls_enabled,
        compression=settings.observability_compression,
        file_path=settings.observability_file_path,
        batch_size=settings.observability_batch_size,
        queue_size=settings.observability_queue_size,
        graceful_shutdown_ms=settings.observability_graceful_shutdown_ms,
        auth_token=settings.observability_auth_token,
    )


def parse_exporter(value: object, *, key: str, source: str) -> TelemetryExporterName:
    """Parse telemetry exporter selection."""
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        if normalized in _EXPORTERS:
            return cast(TelemetryExporterName, normalized)
    msg = f"Configuration key {key!r} from {source} must be a telemetry exporter."
    raise ValueError(msg)


def parse_sampling(value: object, *, key: str, source: str) -> SamplingStrategy:
    """Parse telemetry sampling strategy."""
    if isinstance(value, str):
        normalized = value.strip().lower().replace("-", "_")
        if normalized in _SAMPLING:
            return cast(SamplingStrategy, normalized)
    msg = f"Configuration key {key!r} from {source} must be a sampling strategy."
    raise ValueError(msg)


def parse_compression(value: object, *, key: str, source: str) -> Compression:
    """Parse telemetry compression mode."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _COMPRESSION:
            return cast(Compression, normalized)
    msg = f"Configuration key {key!r} from {source} must be a compression mode."
    raise ValueError(msg)


def parse_headers(value: object, *, key: str, source: str) -> Mapping[str, str]:
    """Parse telemetry headers from TOML or environment values."""
    if value is None:
        return {}
    if isinstance(value, str):
        headers: dict[str, str] = {}
        for item in value.split(","):
            if not item.strip():
                continue
            if "=" not in item:
                msg = f"Header {item!r} from {source} must use key=value format."
                raise ValueError(msg)
            header_key, header_value = item.split("=", 1)
            headers[header_key.strip()] = header_value.strip()
        return headers
    if isinstance(value, Mapping):
        return {
            str(header_key): str(header_value)
            for header_key, header_value in value.items()
        }
    msg = f"Configuration key {key!r} from {source} must be a header mapping."
    raise ValueError(msg)


__all__ = [
    "observability_config_from_settings",
    "parse_compression",
    "parse_exporter",
    "parse_headers",
    "parse_sampling",
]
