"""Read-only AI agent profiling engine for AgentReplay traces."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Protocol, cast

from agentreplay.core.events import (
    COST_RECORDED,
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    TOOL_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    EventRecord,
)
from agentreplay.core.traces import TraceSnapshot
from agentreplay.exceptions import ProfilerError
from agentreplay.profiler.models import (
    Bottleneck,
    BottleneckSeverity,
    CostAnalysis,
    DurationAnalysis,
    HistogramBucket,
    MemoryAnalysis,
    ModelAnalysis,
    ModelProfile,
    OptimizationRecommendation,
    ProfilingReport,
    RecommendationCategory,
    TimelineSlice,
    TokenAnalysis,
    ToolAnalysis,
    ToolProfile,
    VisualizationData,
)
from agentreplay.replay.playback import EventTimeline
from agentreplay.storage import Pagination, SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue

ProfileInput = TraceSnapshot | str
CustomMetricFunction = Callable[[TraceSnapshot], JSONValue]
CustomRecommendationFunction = Callable[[ProfilingReport], Iterable[object]]

_TOOL_EVENTS = frozenset((TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED))
_LLM_EVENTS = frozenset((LLM_REQUEST, LLM_RESPONSE))
_MEMORY_EVENTS = frozenset((MEMORY_READ, MEMORY_WRITE))
_PROMPT_KEYS = frozenset(("prompt", "messages", "input", "instructions"))
_RESPONSE_KEYS = frozenset(("response", "output", "result", "content"))
_VISUALIZATION_LIMIT = 10_000


class CustomProfiler(Protocol):
    """Protocol for plugin-provided custom profilers."""

    def profile(self, trace: TraceSnapshot) -> Mapping[str, JSONValue]:
        """Return custom metrics for a trace snapshot."""


class CustomMetric(Protocol):
    """Protocol for plugin-provided custom profiler metrics."""

    def measure(self, trace: TraceSnapshot) -> JSONValue:
        """Return a custom metric value for a trace snapshot."""


class CustomRecommendation(Protocol):
    """Protocol for plugin-provided custom recommendations."""

    def recommend(self, report: ProfilingReport) -> Iterable[object]:
        """Return custom recommendation payloads for a profile report."""


class ProfilerEngine:
    """Analyze recorded AgentReplay runs for performance and cost bottlenecks."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        custom_profilers: Mapping[str, CustomProfiler] | None = None,
        custom_metrics: Mapping[str, CustomMetric | CustomMetricFunction] | None = None,
        custom_recommendations: (
            Mapping[str, CustomRecommendation | CustomRecommendationFunction] | None
        ) = None,
    ) -> None:
        """Create a profiler engine."""
        self._storage = storage
        self._custom_profilers = dict(custom_profilers or {})
        self._custom_metrics = dict(custom_metrics or {})
        self._custom_recommendations = dict(custom_recommendations or {})

    def profile(self, value: ProfileInput) -> ProfilingReport:
        """Profile a trace snapshot or storage-backed run id."""
        trace = value if isinstance(value, TraceSnapshot) else self.load(value)
        report = _ProfileBuilder(trace).build()
        custom_metrics = self._run_custom_metrics(trace)
        recommendations = (
            *report.recommendations,
            *self._run_custom_recommendations(report),
        )
        return ProfilingReport(
            run_id=report.run_id,
            run_name=report.run_name,
            duration=report.duration,
            tool_duration=report.tool_duration,
            llm_duration=report.llm_duration,
            memory_duration=report.memory_duration,
            replay_duration=report.replay_duration,
            diff_duration=report.diff_duration,
            token_analysis=report.token_analysis,
            cost_analysis=report.cost_analysis,
            model_analysis=report.model_analysis,
            tool_analysis=report.tool_analysis,
            memory_analysis=report.memory_analysis,
            bottlenecks=report.bottlenecks,
            recommendations=recommendations,
            visualizations=report.visualizations,
            custom_metrics=custom_metrics,
        )

    def load(self, run_id: str) -> TraceSnapshot:
        """Load a trace from configured storage for profiling."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        resolved_run_id = self.resolve_run_id(run_id)
        run = storage.load_run(resolved_run_id)
        if run is None:
            msg = f"Profile run not found: {resolved_run_id}"
            raise ProfilerError(msg)
        return TraceSnapshot(
            run=run,
            events=tuple(storage.stream_events(resolved_run_id, batch_size=5_000)),
        )

    def resolve_run_id(self, run_id: str) -> str:
        """Resolve the special ``latest`` run id."""
        if run_id != "latest":
            return run_id
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.list_runs(pagination=Pagination(limit=1))
        if not runs:
            msg = "No recorded runs found."
            raise ProfilerError(msg)
        return runs[0].run_id

    def close(self) -> None:
        """Release owned storage resources."""
        if self._storage is not None:
            self._storage.close()

    def _run_custom_metrics(self, trace: TraceSnapshot) -> dict[str, JSONValue]:
        """Run plugin-provided custom profiler and metric hooks."""
        metrics: dict[str, JSONValue] = {}
        for name, profiler in self._custom_profilers.items():
            try:
                metrics[name] = _json_value(profiler.profile(trace))
            except Exception as exc:
                metrics[name] = {"error": str(exc)}
        for name, metric in self._custom_metrics.items():
            try:
                if callable(metric):
                    metrics[name] = _json_value(metric(trace))
                else:
                    metrics[name] = _json_value(metric.measure(trace))
            except Exception as exc:
                metrics[name] = {"error": str(exc)}
        return metrics

    def _run_custom_recommendations(
        self,
        report: ProfilingReport,
    ) -> tuple[OptimizationRecommendation, ...]:
        """Run plugin-provided recommendation hooks."""
        recommendations: list[OptimizationRecommendation] = []
        for name, recommender in self._custom_recommendations.items():
            try:
                values = (
                    recommender(report)
                    if callable(recommender)
                    else recommender.recommend(report)
                )
            except Exception as exc:
                recommendations.append(
                    OptimizationRecommendation(
                        category="cost_reduction",
                        severity="low",
                        description=f"Custom recommendation {name} failed.",
                        rationale=str(exc),
                    )
                )
                continue
            for value in values:
                if isinstance(value, OptimizationRecommendation):
                    recommendations.append(value)
                else:
                    recommendations.append(
                        OptimizationRecommendation(
                            category="cost_reduction",
                            severity="info",
                            description=f"Custom recommendation from {name}.",
                            rationale=str(value),
                        )
                    )
        return tuple(recommendations)


@dataclass(slots=True)
class _NamedStats:
    """Mutable aggregate state for tool and model groups."""

    count: int = 0
    failures: int = 0
    retries: int = 0
    durations: list[tuple[str, float]] = field(default_factory=list)
    cost: float = 0.0
    tokens: int = 0
    providers: Counter[str] = field(default_factory=Counter)


class _ProfileBuilder:
    """Single-run profile builder."""

    def __init__(self, trace: TraceSnapshot) -> None:
        """Create profile builder state."""
        self.trace = trace
        self.events = tuple(
            sorted(trace.events, key=lambda event: (event.sequence, event.timestamp))
        )
        self.timeline = EventTimeline.from_trace(
            TraceSnapshot(run=trace.run, events=self.events)
        )
        self.duration_events: list[tuple[str, float]] = []
        self.tool_duration_events: list[tuple[str, float]] = []
        self.llm_duration_events: list[tuple[str, float]] = []
        self.memory_duration_events: list[tuple[str, float]] = []
        self.replay_duration_events: list[tuple[str, float]] = []
        self.diff_duration_events: list[tuple[str, float]] = []
        self.token_values: list[int] = []
        self.cost_values: list[tuple[str, float]] = []
        self.tokens_per_tool: Counter[str] = Counter()
        self.tokens_per_model: Counter[str] = Counter()
        self.cost_per_tool: defaultdict[str, float] = defaultdict(float)
        self.cost_per_model: defaultdict[str, float] = defaultdict(float)
        self.cost_per_request: defaultdict[str, float] = defaultdict(float)
        self.tool_stats: defaultdict[str, _NamedStats] = defaultdict(_NamedStats)
        self.model_stats: defaultdict[str, _NamedStats] = defaultdict(_NamedStats)
        self.provider_distribution: Counter[str] = Counter()
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.memory_reads = 0
        self.memory_writes = 0
        self.memory_size = 0
        self.retry_count = 0
        self.signatures: Counter[str] = Counter()
        self.memory_read_keys: Counter[str] = Counter()
        self.prompt_sizes: list[tuple[str, int]] = []
        self.response_sizes: list[tuple[str, int]] = []

    def build(self) -> ProfilingReport:
        """Build a complete profiling report."""
        for event in self.events:
            self._record_event(event)

        duration = _duration_analysis(self.duration_events)
        tool_duration = _duration_analysis(self.tool_duration_events)
        llm_duration = _duration_analysis(self.llm_duration_events)
        memory_duration = _duration_analysis(self.memory_duration_events)
        cost_analysis = self._cost_analysis()
        token_analysis = self._token_analysis()
        model_analysis = self._model_analysis()
        tool_analysis = self._tool_analysis()
        memory_analysis = self._memory_analysis()
        bottlenecks = self._bottlenecks(duration, cost_analysis)
        recommendations = self._recommendations(
            bottlenecks,
            token_analysis,
            cost_analysis,
            model_analysis,
            tool_analysis,
            memory_analysis,
        )
        visualizations = self._visualizations(token_analysis, cost_analysis)
        return ProfilingReport(
            run_id=self.trace.run.run_id,
            run_name=self.trace.run.name,
            duration=duration,
            tool_duration=tool_duration,
            llm_duration=llm_duration,
            memory_duration=memory_duration,
            replay_duration=_duration_analysis(self.replay_duration_events),
            diff_duration=_duration_analysis(self.diff_duration_events),
            token_analysis=token_analysis,
            cost_analysis=cost_analysis,
            model_analysis=model_analysis,
            tool_analysis=tool_analysis,
            memory_analysis=memory_analysis,
            bottlenecks=bottlenecks,
            recommendations=recommendations,
            visualizations=visualizations,
        )

    def _record_event(self, event: EventRecord) -> None:
        """Record metrics from one event."""
        duration_ms = _event_latency_ms(event)
        self.duration_events.append((event.event_id, duration_ms))
        event_cost = _event_cost(event)
        event_tokens = _event_total_tokens(event)
        self.signatures[_event_signature(event)] += 1

        if event_tokens:
            self.token_values.append(event_tokens)
            self.prompt_tokens += _int_value(
                _nested_value(event.payload, "prompt_tokens")
            )
            self.completion_tokens += _int_value(
                _nested_value(event.payload, "completion_tokens")
            )
            self.total_tokens += event_tokens
        if event_cost:
            self.cost_values.append((event.event_id, event_cost))
            self.cost_per_request[event.event_id] += event_cost

        tool_name = _tool_name(event)
        model_name = _model_name(event)
        provider_name = _provider_name(event)
        if tool_name is not None:
            self._record_tool(event, tool_name, duration_ms, event_cost, event_tokens)
        if model_name is not None:
            self._record_model(
                event,
                model_name,
                provider_name,
                duration_ms,
                event_cost,
                event_tokens,
            )
        if event.event_type in _MEMORY_EVENTS:
            self._record_memory(event, duration_ms)
        if event.event_type == RETRY_RECORDED:
            self.retry_count += 1
        if _is_replay_event(event):
            self.replay_duration_events.append((event.event_id, duration_ms))
        if _is_diff_event(event):
            self.diff_duration_events.append((event.event_id, duration_ms))

        prompt_size = _payload_text_size(event.payload, _PROMPT_KEYS)
        if prompt_size:
            self.prompt_sizes.append((event.event_id, prompt_size))
        response_size = _payload_text_size(event.payload, _RESPONSE_KEYS)
        if response_size:
            self.response_sizes.append((event.event_id, response_size))

    def _record_tool(
        self,
        event: EventRecord,
        tool_name: str,
        duration_ms: float,
        event_cost: float,
        event_tokens: int,
    ) -> None:
        """Record tool event metrics."""
        stats = self.tool_stats[tool_name]
        stats.count += 1
        stats.durations.append((event.event_id, duration_ms))
        stats.cost += event_cost
        stats.tokens += event_tokens
        if event.event_type == TOOL_FAILED:
            stats.failures += 1
        stats.retries += _retry_increment(event)
        self.tool_duration_events.append((event.event_id, duration_ms))
        self.cost_per_tool[tool_name] += event_cost
        self.tokens_per_tool[tool_name] += event_tokens

    def _record_model(
        self,
        event: EventRecord,
        model_name: str,
        provider_name: str | None,
        duration_ms: float,
        event_cost: float,
        event_tokens: int,
    ) -> None:
        """Record model event metrics."""
        stats = self.model_stats[model_name]
        stats.count += 1
        stats.durations.append((event.event_id, duration_ms))
        stats.cost += event_cost
        stats.tokens += event_tokens
        stats.retries += _retry_increment(event)
        if _event_failed(event):
            stats.failures += 1
        if provider_name is not None:
            stats.providers[provider_name] += 1
            self.provider_distribution[provider_name] += 1
        self.llm_duration_events.append((event.event_id, duration_ms))
        self.cost_per_model[model_name] += event_cost
        self.tokens_per_model[model_name] += event_tokens

    def _record_memory(self, event: EventRecord, duration_ms: float) -> None:
        """Record memory event metrics."""
        self.memory_duration_events.append((event.event_id, duration_ms))
        if event.event_type == MEMORY_READ:
            self.memory_reads += 1
            key = _memory_key(event)
            if key is not None:
                self.memory_read_keys[key] += 1
        else:
            self.memory_writes += 1
        self.memory_size += _memory_size(event)

    def _token_analysis(self) -> TokenAnalysis:
        """Build token analysis."""
        total = self.total_tokens or sum(self.token_values)
        return TokenAnalysis(
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=total,
            average_tokens=_average(self.token_values),
            maximum_tokens=max(self.token_values, default=0),
            minimum_tokens=min(self.token_values, default=0),
            tokens_per_tool=dict(self.tokens_per_tool),
            tokens_per_model=dict(self.tokens_per_model),
            distribution=tuple(sorted(self.token_values)),
        )

    def _cost_analysis(self) -> CostAnalysis:
        """Build cost analysis."""
        total_cost = sum(cost for _, cost in self.cost_values)
        non_zero = [(event_id, cost) for event_id, cost in self.cost_values if cost > 0]
        most = max(non_zero, key=lambda item: item[1], default=(None, 0.0))
        least = min(non_zero, key=lambda item: item[1], default=(None, 0.0))
        return CostAnalysis(
            total_cost=total_cost,
            average_cost=total_cost / len(non_zero) if non_zero else 0.0,
            cost_per_tool=dict(self.cost_per_tool),
            cost_per_model=dict(self.cost_per_model),
            cost_per_request=dict(self.cost_per_request),
            most_expensive_event_id=most[0],
            most_expensive_cost=most[1],
            least_expensive_event_id=least[0],
            least_expensive_cost=least[1],
            estimated_daily_cost=total_cost * 24.0,
            estimated_monthly_cost=total_cost * 24.0 * 30.0,
        )

    def _model_analysis(self) -> ModelAnalysis:
        """Build model/provider analysis."""
        profiles: list[ModelProfile] = []
        for model_name, stats in sorted(self.model_stats.items()):
            provider_name = (
                stats.providers.most_common(1)[0][0] if stats.providers else None
            )
            profiles.append(
                ModelProfile(
                    model_name=model_name,
                    provider_name=provider_name,
                    execution_count=stats.count,
                    average_latency_ms=_average_duration(stats.durations),
                    average_cost=stats.cost / stats.count if stats.count else 0.0,
                    average_tokens=stats.tokens / stats.count if stats.count else 0.0,
                    failure_rate=stats.failures / stats.count if stats.count else 0.0,
                    retry_rate=stats.retries / stats.count if stats.count else 0.0,
                )
            )
        return ModelAnalysis(
            models_used=tuple(profile.model_name for profile in profiles),
            provider_distribution=dict(self.provider_distribution),
            profiles=tuple(profiles),
        )

    def _tool_analysis(self) -> ToolAnalysis:
        """Build tool analysis."""
        profiles: list[ToolProfile] = []
        for tool_name, stats in sorted(self.tool_stats.items()):
            durations = [duration for _, duration in stats.durations]
            profiles.append(
                ToolProfile(
                    tool_name=tool_name,
                    execution_count=stats.count,
                    average_duration_ms=_average(durations),
                    fastest_ms=min(durations, default=0.0),
                    slowest_ms=max(durations, default=0.0),
                    failure_rate=stats.failures / stats.count if stats.count else 0.0,
                    retry_count=stats.retries,
                )
            )
        distribution = {
            profile.tool_name: profile.execution_count for profile in profiles
        }
        return ToolAnalysis(
            most_used_tool=_key_by_value(distribution, max),
            least_used_tool=_key_by_value(distribution, min),
            slowest_tool=_profile_by_value(profiles, "slowest_ms", max),
            fastest_tool=_profile_by_value(profiles, "fastest_ms", min),
            profiles=tuple(profiles),
            execution_distribution=distribution,
        )

    def _memory_analysis(self) -> MemoryAnalysis:
        """Build memory analysis."""
        count = self.memory_reads + self.memory_writes
        total_latency = sum(duration for _, duration in self.memory_duration_events)
        return MemoryAnalysis(
            reads=self.memory_reads,
            writes=self.memory_writes,
            total_latency_ms=total_latency,
            average_latency_ms=total_latency / count if count else 0.0,
            total_size_bytes=self.memory_size,
            average_size_bytes=self.memory_size / count if count else 0.0,
        )

    def _bottlenecks(
        self,
        duration: DurationAnalysis,
        cost_analysis: CostAnalysis,
    ) -> tuple[Bottleneck, ...]:
        """Detect bottlenecks from accumulated metrics."""
        bottlenecks: list[Bottleneck] = []
        slow_threshold = max(duration.average_ms * 2.0, 1_000.0)
        expensive_threshold = max(cost_analysis.average_cost, 1.0)

        for event in self.events:
            duration_ms = _event_latency_ms(event)
            event_cost = _event_cost(event)
            if event.event_type in _TOOL_EVENTS and duration_ms >= slow_threshold:
                bottlenecks.append(
                    _bottleneck(
                        "slow_tool_call",
                        "high",
                        event,
                        "Slow tool call detected.",
                        "duration_ms",
                        duration_ms,
                    )
                )
            if event.event_type in _LLM_EVENTS and duration_ms >= slow_threshold:
                bottlenecks.append(
                    _bottleneck(
                        "slow_model_call",
                        "high",
                        event,
                        "Slow model call detected.",
                        "duration_ms",
                        duration_ms,
                    )
                )
            if event_cost >= expensive_threshold:
                bottlenecks.append(
                    _bottleneck(
                        "expensive_operation",
                        "medium",
                        event,
                        "Expensive operation detected.",
                        "cost",
                        event_cost,
                    )
                )

        bottlenecks.extend(self._counter_bottlenecks())
        bottlenecks.extend(self._payload_size_bottlenecks())
        if self.retry_count >= 3:
            bottlenecks.append(
                Bottleneck(
                    category="excessive_retries",
                    severity="medium",
                    event_id=None,
                    description="Excessive retries detected.",
                    metric="retry_count",
                    value=self.retry_count,
                )
            )
        return tuple(bottlenecks)

    def _counter_bottlenecks(self) -> tuple[Bottleneck, ...]:
        """Detect repeated calls, duplicates, and redundant memory reads."""
        bottlenecks: list[Bottleneck] = []
        for signature, count in self.signatures.items():
            if count >= 2:
                bottlenecks.append(
                    Bottleneck(
                        category="duplicate_events",
                        severity="low",
                        event_id=None,
                        description="Duplicate event signatures detected.",
                        metric=signature[:80],
                        value=count,
                    )
                )
            if count >= 4:
                bottlenecks.append(
                    Bottleneck(
                        category="repeated_calls",
                        severity="medium",
                        event_id=None,
                        description="Repeated equivalent calls detected.",
                        metric=signature[:80],
                        value=count,
                    )
                )
        for key, count in self.memory_read_keys.items():
            if count >= 2:
                bottlenecks.append(
                    Bottleneck(
                        category="redundant_memory_reads",
                        severity="low",
                        event_id=None,
                        description="Repeated memory reads for the same key.",
                        metric=key,
                        value=count,
                    )
                )
        return tuple(bottlenecks)

    def _payload_size_bottlenecks(self) -> tuple[Bottleneck, ...]:
        """Detect large prompts and responses."""
        bottlenecks: list[Bottleneck] = []
        for event_id, size in self.prompt_sizes:
            if size >= 4_000:
                bottlenecks.append(
                    Bottleneck(
                        category="large_prompt",
                        severity="medium",
                        event_id=event_id,
                        description="Large prompt detected.",
                        metric="characters",
                        value=size,
                    )
                )
        for event_id, size in self.response_sizes:
            if size >= 8_000:
                bottlenecks.append(
                    Bottleneck(
                        category="large_response",
                        severity="medium",
                        event_id=event_id,
                        description="Large response detected.",
                        metric="characters",
                        value=size,
                    )
                )
        return tuple(bottlenecks)

    def _recommendations(
        self,
        bottlenecks: tuple[Bottleneck, ...],
        token_analysis: TokenAnalysis,
        cost_analysis: CostAnalysis,
        model_analysis: ModelAnalysis,
        tool_analysis: ToolAnalysis,
        memory_analysis: MemoryAnalysis,
    ) -> tuple[OptimizationRecommendation, ...]:
        """Generate optimization recommendations."""
        categories = {bottleneck.category for bottleneck in bottlenecks}
        recommendations: list[OptimizationRecommendation] = []
        if "large_prompt" in categories or token_analysis.average_tokens >= 4_000:
            recommendations.append(
                _recommendation(
                    "prompt_compression",
                    "medium",
                    "Compress repeated prompt context.",
                    "Large prompts and high token counts increase latency and cost.",
                )
            )
        if "repeated_calls" in categories and tool_analysis.profiles:
            recommendations.append(
                _recommendation(
                    "tool_caching",
                    "medium",
                    "Cache deterministic tool results.",
                    "Repeated equivalent calls were observed in this run.",
                )
            )
        if len(tool_analysis.profiles) >= 2 and tool_analysis.slowest_tool is not None:
            recommendations.append(
                _recommendation(
                    "parallel_execution",
                    "low",
                    "Evaluate parallelizing independent tools.",
                    "Multiple tools were used and one tool dominated latency.",
                )
            )
        if model_analysis.profiles:
            recommendations.append(
                _recommendation(
                    "model_selection",
                    "low",
                    "Review model selection for latency and cost balance.",
                    (
                        "Model-level latency, cost, token, and failure rates "
                        "are available."
                    ),
                )
            )
        if self.retry_count >= 3:
            recommendations.append(
                _recommendation(
                    "retry_optimization",
                    "medium",
                    "Tune retry policy and backoff.",
                    "Excessive retries were recorded.",
                )
            )
        if memory_analysis.reads >= 2:
            recommendations.append(
                _recommendation(
                    "memory_optimization",
                    "low",
                    "Batch or cache repeated memory reads.",
                    "Repeated memory access adds avoidable latency.",
                )
            )
        if self.llm_duration_events:
            recommendations.append(
                _recommendation(
                    "streaming",
                    "info",
                    "Consider streaming long model responses.",
                    "Streaming can improve perceived latency for long responses.",
                )
            )
        if len(self.model_stats) > 1 or len(self.tool_stats) > 1:
            recommendations.append(
                _recommendation(
                    "batching",
                    "info",
                    "Batch compatible requests where semantics allow it.",
                    "The run contains repeated provider or tool interaction patterns.",
                )
            )
        if cost_analysis.total_cost > 0:
            recommendations.append(
                _recommendation(
                    "cost_reduction",
                    "medium" if cost_analysis.total_cost >= 1.0 else "low",
                    "Reduce high-cost operations first.",
                    "Cost hotspots are isolated by model, tool, and request.",
                )
            )
        return tuple(recommendations)

    def _visualizations(
        self,
        token_analysis: TokenAnalysis,
        cost_analysis: CostAnalysis,
    ) -> VisualizationData:
        """Build visualization-ready data."""
        slices = tuple(
            TimelineSlice(
                event_id=entry.event.event_id,
                event_type=entry.event.event_type,
                label=entry.label,
                start_ms=_relative_start_ms(self.events[0], entry.event),
                duration_ms=_event_latency_ms(entry.event),
                depth=entry.depth,
            )
            for entry in self.timeline.entries[:_VISUALIZATION_LIMIT]
        )
        latency_values = [duration for _, duration in self.duration_events]
        provider_chart = {
            key: float(value) for key, value in self.provider_distribution.items()
        }
        tool_chart = {key: float(value) for key, value in self.tokens_per_tool.items()}
        return VisualizationData(
            execution_timeline=slices,
            latency_histogram=_histogram(latency_values, unit="ms"),
            token_histogram=_histogram(token_analysis.distribution, unit="tokens"),
            cost_breakdown=cost_analysis.cost_per_model or cost_analysis.cost_per_tool,
            pie_charts={"providers": provider_chart},
            bar_charts={"tokens_per_tool": tool_chart},
            flame_graph=slices,
            waterfall=slices,
        )


def _duration_analysis(values: list[tuple[str, float]]) -> DurationAnalysis:
    """Calculate duration statistics from event-duration tuples."""
    if not values:
        return DurationAnalysis()
    sorted_values = sorted(values, key=lambda item: item[1])
    durations = [duration for _, duration in sorted_values]
    total = sum(durations)
    fastest = sorted_values[0]
    slowest = sorted_values[-1]
    return DurationAnalysis(
        count=len(values),
        total_ms=total,
        average_ms=total / len(values),
        median_ms=_percentile(durations, 50),
        p50_ms=_percentile(durations, 50),
        p90_ms=_percentile(durations, 90),
        p95_ms=_percentile(durations, 95),
        p99_ms=_percentile(durations, 99),
        fastest_event_id=fastest[0],
        fastest_ms=fastest[1],
        slowest_event_id=slowest[0],
        slowest_ms=slowest[1],
    )


def _percentile(sorted_values: list[float], percentile: int) -> float:
    """Return nearest-rank percentile from sorted values."""
    if not sorted_values:
        return 0.0
    index = round((percentile / 100.0) * (len(sorted_values) - 1))
    return sorted_values[index]


def _histogram(
    values: Iterable[float | int], *, unit: str
) -> tuple[HistogramBucket, ...]:
    """Build a compact five-bucket histogram."""
    numeric = [float(value) for value in values]
    if not numeric:
        return ()
    minimum = min(numeric)
    maximum = max(numeric)
    if minimum == maximum:
        return (HistogramBucket(label=f"{minimum:.0f} {unit}", count=len(numeric)),)
    width = (maximum - minimum) / 5.0
    buckets = [0, 0, 0, 0, 0]
    for value in numeric:
        index = min(int((value - minimum) / width), 4)
        buckets[index] += 1
    return tuple(
        HistogramBucket(
            label=(
                f"{minimum + width * index:.0f}-"
                f"{minimum + width * (index + 1):.0f} {unit}"
            ),
            count=count,
        )
        for index, count in enumerate(buckets)
    )


def _event_latency_ms(event: EventRecord) -> float:
    """Return event duration or payload latency."""
    latency = _float_value(_nested_value(event.payload, "latency_ms"))
    duration = max(event.duration_ms, 0.0)
    return latency if latency > duration else duration


def _event_cost(event: EventRecord) -> float:
    """Return cost amount from a payload."""
    if event.event_type == COST_RECORDED:
        return _float_value(event.payload.get("amount"))
    cost = event.payload.get("cost")
    if isinstance(cost, Mapping):
        return _float_value(cost.get("amount"))
    return _float_value(cost) + _float_value(event.payload.get("cost_amount"))


def _event_total_tokens(event: EventRecord) -> int:
    """Return total token count from a payload."""
    total = _int_value(_nested_value(event.payload, "total_tokens"))
    if total:
        return total
    prompt = _int_value(_nested_value(event.payload, "prompt_tokens"))
    completion = _int_value(_nested_value(event.payload, "completion_tokens"))
    return prompt + completion


def _tool_name(event: EventRecord) -> str | None:
    """Return a normalized tool name for tool-like events."""
    if event.event_type not in _TOOL_EVENTS:
        return None
    return _first_str(event.payload, ("tool_name", "function_name", "name", "tool"))


def _model_name(event: EventRecord) -> str | None:
    """Return a normalized model name for model-like events."""
    if event.event_type not in _LLM_EVENTS:
        return None
    return _first_str(event.payload, ("model_name", "model"))


def _provider_name(event: EventRecord) -> str | None:
    """Return a normalized provider name for model-like events."""
    return _first_str(event.payload, ("provider_name", "provider"))


def _first_str(mapping: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    """Return the first string value under a known key."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _retry_increment(event: EventRecord) -> int:
    """Return retry contribution for an event."""
    if event.event_type == RETRY_RECORDED:
        return 1
    retry_count = _int_value(event.payload.get("retry_count"))
    if retry_count:
        return retry_count
    return 1 if event.payload.get("retry") is True else 0


def _event_failed(event: EventRecord) -> bool:
    """Return whether an event payload indicates failure."""
    return (
        event.event_type in {EXCEPTION_RAISED, TOOL_FAILED}
        or event.payload.get("failed") is True
        or event.payload.get("error") is not None
        or event.payload.get("exception") is not None
    )


def _memory_key(event: EventRecord) -> str | None:
    """Return memory key if available."""
    return _first_str(event.payload, ("key", "memory_key", "name"))


def _memory_size(event: EventRecord) -> int:
    """Return approximate memory payload size."""
    explicit = _int_value(event.payload.get("size_bytes"))
    if explicit:
        return explicit
    value = event.payload.get("value")
    if value is None:
        value = event.payload
    return len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))


def _payload_text_size(mapping: Mapping[str, object], keys: frozenset[str]) -> int:
    """Return largest text size under selected payload keys."""
    size = 0
    for key, value in mapping.items():
        normalized = key.lower()
        if normalized in keys or any(marker in normalized for marker in keys):
            size = max(size, len(_stringify(value)))
    return size


def _nested_value(mapping: Mapping[str, object], key: str) -> object:
    """Find a nested mapping value by key."""
    if key in mapping:
        return mapping[key]
    for value in mapping.values():
        if isinstance(value, Mapping):
            found = _nested_value(cast(Mapping[str, object], value), key)
            if found is not None:
                return found
    return None


def _int_value(value: object) -> int:
    """Convert a JSON-like value to an integer."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _float_value(value: object) -> float:
    """Convert a JSON-like value to a float."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _event_signature(event: EventRecord) -> str:
    """Return a stable signature for duplicate/repeated detection."""
    payload = {
        key: value
        for key, value in event.payload.items()
        if key not in {"latency_ms", "duration_ms", "timestamp"}
    }
    return f"{event.event_type}:{json.dumps(payload, sort_keys=True, default=str)}"


def _is_replay_event(event: EventRecord) -> bool:
    """Return whether an event appears to represent replay work."""
    return "replay" in event.event_type or event.payload.get("operation") == "replay"


def _is_diff_event(event: EventRecord) -> bool:
    """Return whether an event appears to represent diff work."""
    return "diff" in event.event_type or event.payload.get("operation") == "diff"


def _relative_start_ms(first: EventRecord, event: EventRecord) -> float:
    """Return event start offset in milliseconds."""
    return max((event.timestamp - first.timestamp).total_seconds() * 1_000.0, 0.0)


def _average(values: Iterable[float | int]) -> float:
    """Return the arithmetic mean of values."""
    sequence = list(values)
    if not sequence:
        return 0.0
    return float(sum(sequence)) / len(sequence)


def _average_duration(values: list[tuple[str, float]]) -> float:
    """Return average duration from event-duration tuples."""
    return _average(duration for _, duration in values)


def _key_by_value(
    values: Mapping[str, int],
    chooser: Callable[[Iterable[int]], int],
) -> str | None:
    """Return key whose value matches a chooser such as ``max`` or ``min``."""
    if not values:
        return None
    target = chooser(values.values())
    for key, value in values.items():
        if value == target:
            return key
    return None


def _profile_by_value(
    profiles: list[ToolProfile],
    field_name: str,
    chooser: Callable[[Iterable[float]], float],
) -> str | None:
    """Return profile name whose selected field matches a chooser."""
    if not profiles:
        return None
    values = [float(getattr(profile, field_name)) for profile in profiles]
    target = chooser(values)
    for profile in profiles:
        if float(getattr(profile, field_name)) == target:
            return profile.tool_name
    return None


def _bottleneck(
    category: str,
    severity: BottleneckSeverity,
    event: EventRecord,
    description: str,
    metric: str,
    value: float | int | str,
) -> Bottleneck:
    """Build a bottleneck from an event."""
    return Bottleneck(
        category=category,
        severity=severity,
        event_id=event.event_id,
        description=description,
        metric=metric,
        value=value,
    )


def _recommendation(
    category: str,
    severity: BottleneckSeverity,
    description: str,
    rationale: str,
) -> OptimizationRecommendation:
    """Build a typed recommendation."""
    return OptimizationRecommendation(
        category=cast(RecommendationCategory, category),
        severity=severity,
        description=description,
        rationale=rationale,
    )


def _json_value(value: object) -> JSONValue:
    """Convert plugin outputs into a JSON-compatible value."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return str(value)


def _stringify(value: object) -> str:
    """Return a deterministic string representation."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, default=str)


__all__ = [
    "CustomMetric",
    "CustomMetricFunction",
    "CustomProfiler",
    "CustomRecommendation",
    "CustomRecommendationFunction",
    "ProfileInput",
    "ProfilerEngine",
]
