"""High-level observability engine for AgentReplay telemetry."""

from __future__ import annotations

from collections.abc import Iterable
from threading import RLock

from agentreplay.core.traces import TraceSnapshot
from agentreplay.observability.exporters import TelemetryExporter, build_exporter
from agentreplay.observability.mapping import MetricsAggregator, TraceMapper
from agentreplay.observability.models import (
    AttributeEnricher,
    CorrelationContext,
    ObservabilityConfig,
    TelemetryExportResult,
    TelemetryMetrics,
    TelemetryTrace,
)
from agentreplay.observability.sampling import CustomSampler, TelemetrySampler


class ObservabilityEngine:
    """Map AgentReplay traces to telemetry and export them."""

    def __init__(
        self,
        config: ObservabilityConfig | None = None,
        *,
        exporter: TelemetryExporter | None = None,
        custom_sampler: CustomSampler | None = None,
        enrichers: Iterable[AttributeEnricher] = (),
    ) -> None:
        """Create an observability engine."""
        self.config = ObservabilityConfig() if config is None else config
        self._mapper = TraceMapper(self.config, enrichers=enrichers)
        self._metrics = MetricsAggregator()
        self._sampler = TelemetrySampler(self.config, custom_sampler=custom_sampler)
        self._exporter = exporter
        self._lock = RLock()
        self._export_count = 0

    def map_trace(
        self,
        trace: TraceSnapshot,
        *,
        correlation: CorrelationContext | None = None,
    ) -> TelemetryTrace:
        """Map a trace without exporting it."""
        return self._mapper.map_trace(trace, correlation=correlation)

    def export_trace(
        self,
        trace: TraceSnapshot,
        *,
        correlation: CorrelationContext | None = None,
    ) -> TelemetryExportResult:
        """Export one AgentReplay trace as telemetry."""
        telemetry_trace = self.map_trace(trace, correlation=correlation)
        if not self.config.enabled:
            return TelemetryExportResult(
                exporter=self.config.exporter,
                succeeded=True,
                message="telemetry disabled",
                exported_spans=0,
            )
        if not self._sampler.should_sample(telemetry_trace):
            return TelemetryExportResult(
                exporter=self.config.exporter,
                succeeded=True,
                message="trace not sampled",
                exported_spans=0,
            )
        exporter = self._require_exporter()
        result = exporter.export(telemetry_trace)
        with self._lock:
            self._export_count += 1
        return result

    def metrics(
        self,
        traces: Iterable[TraceSnapshot],
        *,
        replay_count: int = 0,
        diff_count: int = 0,
        plugin_count: int = 0,
    ) -> TelemetryMetrics:
        """Aggregate metrics for traces."""
        with self._lock:
            export_count = self._export_count
        return self._metrics.summarize(
            traces,
            replay_count=replay_count,
            diff_count=diff_count,
            export_count=export_count,
            plugin_count=plugin_count,
        )

    def shutdown(self) -> None:
        """Gracefully shut down exporter resources."""
        exporter = self._exporter
        if exporter is not None:
            exporter.shutdown()

    def _require_exporter(self) -> TelemetryExporter:
        with self._lock:
            if self._exporter is None:
                self._exporter = build_exporter(self.config)
            return self._exporter


__all__ = ["ObservabilityEngine"]
