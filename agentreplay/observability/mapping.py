"""Map AgentReplay traces to OpenTelemetry-compatible telemetry data."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import timedelta

from agentreplay.core.events import (
    COST_RECORDED,
    EXCEPTION_RAISED,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    TOOL_FAILED,
    TOOL_FINISHED,
    EventRecord,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.observability.models import (
    AttributeEnricher,
    CorrelationContext,
    ObservabilityConfig,
    SpanStatus,
    TelemetryEvent,
    TelemetryLink,
    TelemetryMetrics,
    TelemetrySpan,
    TelemetryTrace,
)
from agentreplay.types import JSONValue, Metadata
from agentreplay.version import __version__


class TraceMapper:
    """Convert AgentReplay trace snapshots into telemetry traces."""

    def __init__(
        self,
        config: ObservabilityConfig | None = None,
        *,
        enrichers: Iterable[AttributeEnricher] = (),
    ) -> None:
        """Create a trace mapper."""
        self._config = ObservabilityConfig() if config is None else config
        self._enrichers = tuple(enrichers)

    def map_trace(
        self,
        trace: TraceSnapshot,
        *,
        correlation: CorrelationContext | None = None,
    ) -> TelemetryTrace:
        """Map one AgentReplay trace into an OpenTelemetry-compatible trace."""
        resolved_correlation = (
            CorrelationContext(run_id=trace.run.run_id)
            if correlation is None
            else replace(correlation, run_id=correlation.run_id or trace.run.run_id)
        )
        trace_id = resolved_correlation.trace_id or trace.run.run_id
        resource = _resource_attributes(self._config)
        attributes = self._enrich(
            {
                "agentreplay.run.id": trace.run.run_id,
                "agentreplay.run.name": trace.run.name,
                "agentreplay.run.status": trace.run.status,
                "agentreplay.version": __version__,
                "deployment.environment": self._config.deployment_environment,
                **resolved_correlation.attributes(),
                **_flatten_metadata("agentreplay.run.metadata", trace.run.metadata),
            },
        )
        spans = tuple(
            self._map_event(event, trace_id=trace_id, correlation=resolved_correlation)
            for event in trace.events
        )
        return TelemetryTrace(
            trace_id=trace_id,
            run_id=trace.run.run_id,
            name=trace.run.name or "agentreplay.run",
            start_time=trace.run.started_at,
            end_time=trace.run.ended_at,
            attributes=_clean_attributes(attributes),
            resource=resource,
            spans=spans,
            correlation=resolved_correlation,
        )

    def _map_event(
        self,
        event: EventRecord,
        *,
        trace_id: str,
        correlation: CorrelationContext,
    ) -> TelemetrySpan:
        end_time = event.timestamp + timedelta(milliseconds=event.duration_ms)
        attributes = self._enrich(
            {
                "agentreplay.run.id": event.run_id,
                "agentreplay.event.id": event.event_id,
                "agentreplay.event.type": event.event_type,
                "agentreplay.event.sequence": event.sequence,
                "agentreplay.parent_event.id": event.parent_event_id,
                "agentreplay.duration_ms": event.duration_ms,
                **correlation.attributes(),
                **_event_attributes(event),
                **_flatten_metadata("agentreplay.event.metadata", event.metadata),
            },
        )
        span_event = TelemetryEvent(
            name=event.event_type,
            timestamp=event.timestamp,
            attributes=_clean_attributes(_flatten_metadata("payload", event.payload)),
        )
        links = (
            ()
            if event.parent_event_id is None
            else (
                TelemetryLink(
                    trace_id=trace_id,
                    span_id=event.parent_event_id,
                    attributes={"agentreplay.link.type": "parent_event"},
                ),
            )
        )
        return TelemetrySpan(
            span_id=event.event_id,
            trace_id=trace_id,
            parent_span_id=event.parent_event_id,
            name=_span_name(event),
            start_time=event.timestamp,
            end_time=end_time,
            duration_ms=event.duration_ms,
            status=_span_status(event),
            attributes=_clean_attributes(attributes),
            events=(span_event,),
            links=links,
        )

    def _enrich(self, attributes: Metadata) -> Metadata:
        enriched = dict(attributes)
        for enricher in self._enrichers:
            enriched.update(enricher(enriched))
        return enriched


class MetricsAggregator:
    """Aggregate AgentReplay trace data into telemetry metrics."""

    def summarize(
        self,
        traces: Iterable[TraceSnapshot],
        *,
        replay_count: int = 0,
        diff_count: int = 0,
        export_count: int = 0,
        plugin_count: int = 0,
    ) -> TelemetryMetrics:
        """Return aggregate metrics for trace snapshots."""
        trace_list = tuple(traces)
        latencies: list[float] = []
        token_totals: list[float] = []
        costs: list[float] = []
        tool_usage: dict[str, int] = {}
        model_usage: dict[str, int] = {}
        retry_count = 0
        memory_reads = 0
        memory_writes = 0
        for trace in trace_list:
            for event in trace.events:
                if event.duration_ms > 0:
                    latencies.append(event.duration_ms)
                if event.event_type == RETRY_RECORDED:
                    retry_count += 1
                if event.event_type == MEMORY_READ:
                    memory_reads += 1
                if event.event_type == MEMORY_WRITE:
                    memory_writes += 1
                _increment_if_present(tool_usage, _tool_name(event))
                _increment_if_present(model_usage, _model_name(event))
                tokens = _token_total(event)
                if tokens is not None:
                    token_totals.append(float(tokens))
                cost = _cost_amount(event)
                if cost is not None:
                    costs.append(float(cost))
        return TelemetryMetrics(
            run_count=len(trace_list),
            success_count=sum(
                1 for trace in trace_list if trace.run.status == "completed"
            ),
            failure_count=sum(
                1 for trace in trace_list if trace.run.status == "failed"
            ),
            retry_count=retry_count,
            average_latency_ms=_average(latencies),
            p95_latency_ms=_percentile(latencies, 0.95),
            p99_latency_ms=_percentile(latencies, 0.99),
            average_tokens=_average(token_totals),
            average_cost=_average(costs),
            tool_usage=tool_usage,
            model_usage=model_usage,
            memory_reads=memory_reads,
            memory_writes=memory_writes,
            replay_count=replay_count,
            diff_count=diff_count,
            export_count=export_count,
            plugin_count=plugin_count,
        )


def _span_name(event: EventRecord) -> str:
    return f"agentreplay.{event.event_type}"


def _span_status(event: EventRecord) -> SpanStatus:
    if event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}:
        return "error"
    return "ok"


def _event_attributes(event: EventRecord) -> Metadata:
    payload = event.payload
    attrs: dict[str, JSONValue] = {}
    provider = payload.get("provider_name") or payload.get("provider")
    model = payload.get("model_name") or payload.get("model")
    tool = _tool_name(event)
    if provider is not None:
        attrs["gen_ai.system"] = str(provider)
        attrs["agentreplay.provider"] = str(provider)
    if model is not None:
        attrs["gen_ai.request.model"] = str(model)
        attrs["agentreplay.model"] = str(model)
    if tool is not None:
        attrs["agentreplay.tool.name"] = tool
    if event.event_type == TOOL_FINISHED:
        attrs["agentreplay.tool.duration_ms"] = event.duration_ms
    if event.event_type == LATENCY_RECORDED:
        attrs["agentreplay.latency_ms"] = _number(payload.get("latency_ms"))
    if event.event_type in {LLM_REQUEST, LLM_RESPONSE}:
        attrs.update(_llm_sizes(payload))
    if event.event_type == COST_RECORDED:
        amount = _cost_amount(event)
        if amount is not None:
            attrs["agentreplay.cost.amount"] = amount
    tokens = _token_total(event)
    if tokens is not None:
        attrs["gen_ai.usage.total_tokens"] = tokens
    return attrs


def _llm_sizes(payload: Mapping[str, JSONValue]) -> Metadata:
    attrs: dict[str, JSONValue] = {}
    prompt = payload.get("prompt") or payload.get("prompts")
    response = payload.get("response") or payload.get("completion")
    if prompt is not None:
        attrs["agentreplay.prompt.size"] = len(str(prompt))
    if response is not None:
        attrs["agentreplay.completion.size"] = len(str(response))
    usage = payload.get("token_usage")
    if isinstance(usage, Mapping):
        input_tokens = _number(usage.get("input_tokens"))
        output_tokens = _number(usage.get("output_tokens"))
        if input_tokens is not None:
            attrs["gen_ai.usage.input_tokens"] = input_tokens
        if output_tokens is not None:
            attrs["gen_ai.usage.output_tokens"] = output_tokens
    return attrs


def _resource_attributes(config: ObservabilityConfig) -> Metadata:
    attributes: dict[str, JSONValue] = {
        "service.name": config.service_name,
        "telemetry.sdk.name": "agentreplay",
        "telemetry.sdk.language": "python",
        "agentreplay.version": __version__,
    }
    if config.service_namespace is not None:
        attributes["service.namespace"] = config.service_namespace
    if config.deployment_environment is not None:
        attributes["deployment.environment"] = config.deployment_environment
    return attributes


def _flatten_metadata(prefix: str, metadata: Mapping[str, JSONValue]) -> Metadata:
    flattened: dict[str, JSONValue] = {}
    for key, value in metadata.items():
        attr_key = f"{prefix}.{key}"
        if isinstance(value, Mapping):
            flattened.update(_flatten_metadata(attr_key, value))
        elif isinstance(value, list | tuple):
            flattened[attr_key] = str(value)
        else:
            flattened[attr_key] = value
    return flattened


def _clean_attributes(attributes: Mapping[str, JSONValue]) -> Metadata:
    return {
        key: value
        for key, value in attributes.items()
        if value is not None and isinstance(value, str | int | float | bool)
    }


def _increment_if_present(values: dict[str, int], key: str | None) -> None:
    if key is not None:
        values[key] = values.get(key, 0) + 1


def _tool_name(event: EventRecord) -> str | None:
    value = event.payload.get("tool_name")
    return None if value is None else str(value)


def _model_name(event: EventRecord) -> str | None:
    value = event.payload.get("model_name") or event.payload.get("model")
    return None if value is None else str(value)


def _token_total(event: EventRecord) -> float | None:
    usage = event.payload.get("token_usage")
    if isinstance(usage, Mapping):
        total = _number(usage.get("total_tokens"))
        if total is not None:
            return total
        input_tokens = _number(usage.get("input_tokens")) or 0.0
        output_tokens = _number(usage.get("output_tokens")) or 0.0
        return input_tokens + output_tokens if input_tokens or output_tokens else None
    return _number(event.payload.get("total_tokens"))


def _cost_amount(event: EventRecord) -> float | None:
    cost = event.payload.get("cost")
    if isinstance(cost, Mapping):
        return _number(cost.get("amount"))
    return _number(event.payload.get("amount"))


def _number(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(
        int(round((len(sorted_values) - 1) * percentile)),
        len(sorted_values) - 1,
    )
    return sorted_values[index]


__all__ = ["MetricsAggregator", "TraceMapper"]
