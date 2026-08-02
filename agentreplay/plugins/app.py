"""Registration facade exposed to AgentReplay plugins."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from agentreplay.plugins.models import (
    HookName,
    PluginHookContext,
    PluginHookResult,
    PluginRegistration,
    PluginType,
)
from agentreplay.types import Metadata

PluginHookHandler = Callable[[PluginHookContext], None]
CLICommandRegistrar = Callable[[Any], None]


class Exporter(Protocol):
    """Protocol implemented by plugin-provided exporters."""

    def export(self, trace: object) -> str:
        """Export a trace-like object."""


class EventProcessor(Protocol):
    """Protocol implemented by plugin-provided event processors."""

    def process_event(self, event: object) -> object | None:
        """Process an event and return a replacement or ``None``."""


class MetadataCollector(Protocol):
    """Protocol implemented by plugin-provided metadata collectors."""

    def collect(self) -> Metadata:
        """Return metadata to attach to an execution."""


class SecurityDetector(Protocol):
    """Protocol implemented by plugin-provided security detectors."""

    def scan(self, value: object) -> object:
        """Scan a value and return detector-specific findings."""


class TelemetryAttributeEnricher(Protocol):
    """Protocol implemented by telemetry attribute enrichers."""

    def enrich(self, attributes: Metadata) -> Metadata:
        """Return extra telemetry attributes."""


class CustomProfiler(Protocol):
    """Protocol implemented by plugin-provided profiler extensions."""

    def profile(self, trace: object) -> object:
        """Return plugin-specific profile output for a trace-like object."""


class CustomMetric(Protocol):
    """Protocol implemented by plugin-provided profiler metrics."""

    def measure(self, trace: object) -> object:
        """Return plugin-specific metric output for a trace-like object."""


class CustomRecommendation(Protocol):
    """Protocol implemented by plugin-provided profiler recommendations."""

    def recommend(self, profile: object) -> object:
        """Return plugin-specific recommendations for a profile-like object."""


class ReportExtension(Protocol):
    """Protocol implemented by plugin-provided report extensions."""

    def render(self, report: object) -> str:
        """Render extension output for a report-like object."""


class RegressionRule(Protocol):
    """Protocol implemented by plugin-provided regression rules."""

    def analyze(self, baseline: object, target: object) -> object:
        """Return regression findings from two trace-like objects."""


class RegressionAnalyzer(Protocol):
    """Protocol implemented by plugin-provided regression analyzers."""

    def analyze(self, report: object) -> object:
        """Return analyzer-specific regression output."""


class RegressionRecommendation(Protocol):
    """Protocol implemented by plugin-provided regression recommenders."""

    def recommend(self, report: object) -> object:
        """Return additional recommendations for a regression report."""


@dataclass(slots=True)
class PluginApp:
    """Mutable registration facade passed to plugin ``register()`` methods."""

    logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("agentreplay.plugins"),
    )
    _active_plugin: str | None = None
    _config_by_plugin: Mapping[str, Metadata] = field(default_factory=dict)
    _registrations: list[PluginRegistration] = field(default_factory=list)
    _hooks: dict[HookName, list[tuple[str, PluginHookHandler]]] = field(
        default_factory=dict,
    )

    def activate(self, plugin_name: str, config: Metadata) -> None:
        """Set the plugin currently allowed to register capabilities."""
        self._active_plugin = plugin_name
        merged = dict(self._config_by_plugin)
        merged[plugin_name] = dict(config)
        self._config_by_plugin = merged

    def deactivate(self) -> None:
        """Clear the active plugin registration context."""
        self._active_plugin = None

    def config(self, plugin_name: str | None = None) -> Metadata:
        """Return plugin-specific configuration."""
        resolved_name = self._require_active_plugin(plugin_name)
        return dict(self._config_by_plugin.get(resolved_name, {}))

    def register_agent_framework(self, name: str, value: object) -> None:
        """Register an agent-framework integration."""
        self._register("agent_framework", name, value)

    def register_llm_provider(self, name: str, value: object) -> None:
        """Register an LLM-provider integration."""
        self._register("llm_provider", name, value)

    def register_storage_backend(self, name: str, value: object) -> None:
        """Register a storage backend factory or implementation."""
        self._register("storage_backend", name, value)

    def register_exporter(
        self,
        name: str,
        value: Exporter | Callable[..., str],
    ) -> None:
        """Register an exporter implementation."""
        self._register("exporter", name, value)

    def register_cli_command(self, name: str, registrar: CLICommandRegistrar) -> None:
        """Register a plugin-provided CLI command registrar."""
        self._register("cli_command", name, registrar)

    def register_event_processor(self, name: str, processor: EventProcessor) -> None:
        """Register an event processor."""
        self._register("event_processor", name, processor)

    def register_metadata_collector(
        self,
        name: str,
        collector: MetadataCollector,
    ) -> None:
        """Register a metadata collector."""
        self._register("metadata_collector", name, collector)

    def register_secret_detector(self, name: str, detector: SecurityDetector) -> None:
        """Register a plugin-provided secret detector."""
        self._register("secret_detector", name, detector)

    def register_pii_detector(self, name: str, detector: SecurityDetector) -> None:
        """Register a plugin-provided PII detector."""
        self._register("pii_detector", name, detector)

    def register_redaction_rule(self, name: str, rule: object) -> None:
        """Register a plugin-provided redaction rule."""
        self._register("redaction_rule", name, rule)

    def register_telemetry_exporter(self, name: str, exporter: object) -> None:
        """Register a plugin-provided telemetry exporter."""
        self._register("telemetry_exporter", name, exporter)

    def register_telemetry_metric(self, name: str, metric: object) -> None:
        """Register a plugin-provided telemetry metric."""
        self._register("telemetry_metric", name, metric)

    def register_telemetry_span_processor(self, name: str, processor: object) -> None:
        """Register a plugin-provided telemetry span processor."""
        self._register("telemetry_span_processor", name, processor)

    def register_telemetry_attribute_enricher(
        self,
        name: str,
        enricher: TelemetryAttributeEnricher,
    ) -> None:
        """Register a plugin-provided telemetry attribute enricher."""
        self._register("telemetry_attribute_enricher", name, enricher)

    def register_custom_profiler(self, name: str, profiler: CustomProfiler) -> None:
        """Register a plugin-provided profiler extension."""
        self._register("custom_profiler", name, profiler)

    def register_custom_metric(self, name: str, metric: CustomMetric) -> None:
        """Register a plugin-provided profiler metric."""
        self._register("custom_metric", name, metric)

    def register_custom_recommendation(
        self,
        name: str,
        recommendation: CustomRecommendation,
    ) -> None:
        """Register a plugin-provided profiler recommendation."""
        self._register("custom_recommendation", name, recommendation)

    def register_report_section(self, name: str, section: ReportExtension) -> None:
        """Register a plugin-provided trace report section."""
        self._register("report_section", name, section)

    def register_report_chart(self, name: str, chart: ReportExtension) -> None:
        """Register a plugin-provided trace report chart."""
        self._register("report_chart", name, chart)

    def register_report_widget(self, name: str, widget: ReportExtension) -> None:
        """Register a plugin-provided trace report widget."""
        self._register("report_widget", name, widget)

    def register_regression_rule(self, name: str, rule: RegressionRule) -> None:
        """Register a plugin-provided regression detection rule."""
        self._register("regression_rule", name, rule)

    def register_regression_analyzer(
        self,
        name: str,
        analyzer: RegressionAnalyzer,
    ) -> None:
        """Register a plugin-provided regression analyzer."""
        self._register("regression_analyzer", name, analyzer)

    def register_regression_recommendation(
        self,
        name: str,
        recommendation: RegressionRecommendation,
    ) -> None:
        """Register a plugin-provided regression recommendation source."""
        self._register("regression_recommendation", name, recommendation)

    def register_sdk_analyzer(self, name: str, analyzer: object) -> None:
        """Register a public SDK analyzer extension."""
        self._register("sdk_analyzer", name, analyzer)

    def register_sdk_exporter(self, name: str, exporter: object) -> None:
        """Register a public SDK exporter extension."""
        self._register("sdk_exporter", name, exporter)

    def register_sdk_storage(self, name: str, storage: object) -> None:
        """Register a public SDK storage extension."""
        self._register("sdk_storage", name, storage)

    def register_sdk_visualization(self, name: str, visualization: object) -> None:
        """Register a public SDK visualization extension."""
        self._register("sdk_visualization", name, visualization)

    def register_sdk_report(self, name: str, report: object) -> None:
        """Register a public SDK report extension."""
        self._register("sdk_report", name, report)

    def register_auth_provider(self, name: str, provider: object) -> None:
        """Register a future authentication provider."""
        self._register("auth_provider", name, provider)

    def register_hook(self, hook: HookName, handler: PluginHookHandler) -> None:
        """Register a lifecycle hook handler for the active plugin."""
        plugin_name = self._require_active_plugin()
        self._hooks.setdefault(hook, []).append((plugin_name, handler))

    def registrations(
        self,
        *,
        plugin_name: str | None = None,
        kind: PluginType | None = None,
    ) -> tuple[PluginRegistration, ...]:
        """Return registered capabilities, optionally filtered."""
        registrations = self._registrations
        if plugin_name is not None:
            registrations = [
                registration
                for registration in registrations
                if registration.plugin_name == plugin_name
            ]
        if kind is not None:
            registrations = [
                registration
                for registration in registrations
                if registration.kind == kind
            ]
        return tuple(registrations)

    def remove_plugin(self, plugin_name: str) -> None:
        """Remove registrations and hooks owned by a plugin."""
        self._registrations = [
            registration
            for registration in self._registrations
            if registration.plugin_name != plugin_name
        ]
        self._hooks = {
            hook: [
                (owner, handler) for owner, handler in handlers if owner != plugin_name
            ]
            for hook, handlers in self._hooks.items()
        }

    def emit_hook(
        self,
        hook: HookName,
        *,
        payload: Metadata | None = None,
    ) -> tuple[PluginHookResult, ...]:
        """Invoke hook handlers and isolate plugin failures."""
        context = PluginHookContext(hook=hook, payload=dict(payload or {}))
        results: list[PluginHookResult] = []
        for plugin_name, handler in tuple(self._hooks.get(hook, ())):
            try:
                handler(context)
            except Exception as exc:
                self.logger.warning(
                    "AgentReplay plugin hook failed: %s.%s: %s",
                    plugin_name,
                    hook,
                    exc,
                )
                results.append(
                    PluginHookResult(
                        hook=hook,
                        plugin_name=plugin_name,
                        succeeded=False,
                        error=str(exc),
                    ),
                )
            else:
                results.append(
                    PluginHookResult(
                        hook=hook,
                        plugin_name=plugin_name,
                        succeeded=True,
                    ),
                )
        return tuple(results)

    def _register(self, kind: PluginType, name: str, value: object) -> None:
        """Register one capability for the active plugin."""
        plugin_name = self._require_active_plugin()
        if not name.strip():
            msg = "Plugin registrations must have a non-empty name."
            raise ValueError(msg)
        self._registrations.append(
            PluginRegistration(
                plugin_name=plugin_name,
                kind=kind,
                name=name.strip(),
                value=value,
            ),
        )

    def _require_active_plugin(self, plugin_name: str | None = None) -> str:
        """Return an explicit or currently active plugin name."""
        resolved_name = plugin_name or self._active_plugin
        if resolved_name is None:
            msg = "Plugin registrations require an active plugin context."
            raise RuntimeError(msg)
        return resolved_name


__all__ = [
    "CLICommandRegistrar",
    "CustomMetric",
    "CustomProfiler",
    "CustomRecommendation",
    "EventProcessor",
    "Exporter",
    "MetadataCollector",
    "PluginApp",
    "PluginHookHandler",
    "ReportExtension",
    "RegressionAnalyzer",
    "RegressionRecommendation",
    "RegressionRule",
    "SecurityDetector",
    "TelemetryAttributeEnricher",
]
