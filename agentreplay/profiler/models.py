"""Typed profile models for AgentReplay performance analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue

BottleneckSeverity: TypeAlias = Literal["info", "low", "medium", "high", "critical"]
RecommendationCategory: TypeAlias = Literal[
    "prompt_compression",
    "tool_caching",
    "parallel_execution",
    "model_selection",
    "retry_optimization",
    "memory_optimization",
    "streaming",
    "batching",
    "cost_reduction",
]


@dataclass(frozen=True, slots=True)
class DurationAnalysis:
    """Execution-duration statistics for a profile scope."""

    count: int = 0
    total_ms: float = 0.0
    average_ms: float = 0.0
    median_ms: float = 0.0
    p50_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    fastest_event_id: str | None = None
    fastest_ms: float = 0.0
    slowest_event_id: str | None = None
    slowest_ms: float = 0.0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "count": self.count,
            "total_ms": self.total_ms,
            "average_ms": self.average_ms,
            "median_ms": self.median_ms,
            "p50_ms": self.p50_ms,
            "p90_ms": self.p90_ms,
            "p95_ms": self.p95_ms,
            "p99_ms": self.p99_ms,
            "fastest_event_id": self.fastest_event_id,
            "fastest_ms": self.fastest_ms,
            "slowest_event_id": self.slowest_event_id,
            "slowest_ms": self.slowest_ms,
        }


@dataclass(frozen=True, slots=True)
class TokenAnalysis:
    """Token-usage statistics for recorded LLM-related events."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    average_tokens: float = 0.0
    maximum_tokens: int = 0
    minimum_tokens: int = 0
    tokens_per_tool: dict[str, int] = field(default_factory=dict)
    tokens_per_model: dict[str, int] = field(default_factory=dict)
    distribution: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "average_tokens": self.average_tokens,
            "maximum_tokens": self.maximum_tokens,
            "minimum_tokens": self.minimum_tokens,
            "tokens_per_tool": self.tokens_per_tool,
            "tokens_per_model": self.tokens_per_model,
            "distribution": list(self.distribution),
        }


@dataclass(frozen=True, slots=True)
class CostAnalysis:
    """Cost statistics for recorded model and tool operations."""

    total_cost: float = 0.0
    average_cost: float = 0.0
    cost_per_tool: dict[str, float] = field(default_factory=dict)
    cost_per_model: dict[str, float] = field(default_factory=dict)
    cost_per_request: dict[str, float] = field(default_factory=dict)
    most_expensive_event_id: str | None = None
    most_expensive_cost: float = 0.0
    least_expensive_event_id: str | None = None
    least_expensive_cost: float = 0.0
    estimated_daily_cost: float = 0.0
    estimated_monthly_cost: float = 0.0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "total_cost": self.total_cost,
            "average_cost": self.average_cost,
            "cost_per_tool": self.cost_per_tool,
            "cost_per_model": self.cost_per_model,
            "cost_per_request": self.cost_per_request,
            "most_expensive_event_id": self.most_expensive_event_id,
            "most_expensive_cost": self.most_expensive_cost,
            "least_expensive_event_id": self.least_expensive_event_id,
            "least_expensive_cost": self.least_expensive_cost,
            "estimated_daily_cost": self.estimated_daily_cost,
            "estimated_monthly_cost": self.estimated_monthly_cost,
        }


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Aggregated profile for one model name."""

    model_name: str
    provider_name: str | None
    execution_count: int
    average_latency_ms: float
    average_cost: float
    average_tokens: float
    failure_rate: float
    retry_rate: float

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "model_name": self.model_name,
            "provider_name": self.provider_name,
            "execution_count": self.execution_count,
            "average_latency_ms": self.average_latency_ms,
            "average_cost": self.average_cost,
            "average_tokens": self.average_tokens,
            "failure_rate": self.failure_rate,
            "retry_rate": self.retry_rate,
        }


@dataclass(frozen=True, slots=True)
class ModelAnalysis:
    """Model and provider distribution profile."""

    models_used: tuple[str, ...] = ()
    provider_distribution: dict[str, int] = field(default_factory=dict)
    profiles: tuple[ModelProfile, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "models_used": list(self.models_used),
            "provider_distribution": self.provider_distribution,
            "profiles": [profile.to_dict() for profile in self.profiles],
        }


@dataclass(frozen=True, slots=True)
class ToolProfile:
    """Aggregated profile for one tool name."""

    tool_name: str
    execution_count: int
    average_duration_ms: float
    fastest_ms: float
    slowest_ms: float
    failure_rate: float
    retry_count: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "tool_name": self.tool_name,
            "execution_count": self.execution_count,
            "average_duration_ms": self.average_duration_ms,
            "fastest_ms": self.fastest_ms,
            "slowest_ms": self.slowest_ms,
            "failure_rate": self.failure_rate,
            "retry_count": self.retry_count,
        }


@dataclass(frozen=True, slots=True)
class ToolAnalysis:
    """Tool execution distribution and efficiency analysis."""

    most_used_tool: str | None = None
    least_used_tool: str | None = None
    slowest_tool: str | None = None
    fastest_tool: str | None = None
    profiles: tuple[ToolProfile, ...] = ()
    execution_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "most_used_tool": self.most_used_tool,
            "least_used_tool": self.least_used_tool,
            "slowest_tool": self.slowest_tool,
            "fastest_tool": self.fastest_tool,
            "profiles": [profile.to_dict() for profile in self.profiles],
            "execution_distribution": self.execution_distribution,
        }


@dataclass(frozen=True, slots=True)
class MemoryAnalysis:
    """Memory read/write performance profile."""

    reads: int = 0
    writes: int = 0
    total_latency_ms: float = 0.0
    average_latency_ms: float = 0.0
    total_size_bytes: int = 0
    average_size_bytes: float = 0.0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "reads": self.reads,
            "writes": self.writes,
            "total_latency_ms": self.total_latency_ms,
            "average_latency_ms": self.average_latency_ms,
            "total_size_bytes": self.total_size_bytes,
            "average_size_bytes": self.average_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class Bottleneck:
    """Detected profile bottleneck or inefficiency."""

    category: str
    severity: BottleneckSeverity
    event_id: str | None
    description: str
    metric: str
    value: float | int | str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "category": self.category,
            "severity": self.severity,
            "event_id": self.event_id,
            "description": self.description,
            "metric": self.metric,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class OptimizationRecommendation:
    """Optimization recommendation generated from profile evidence."""

    category: RecommendationCategory
    severity: BottleneckSeverity
    description: str
    rationale: str
    event_id: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "rationale": self.rationale,
            "event_id": self.event_id,
        }


@dataclass(frozen=True, slots=True)
class HistogramBucket:
    """One histogram bucket used by visualization data."""

    label: str
    count: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {"label": self.label, "count": self.count}


@dataclass(frozen=True, slots=True)
class TimelineSlice:
    """One timeline, flame graph, or waterfall visualization row."""

    event_id: str
    event_type: str
    label: str
    start_ms: float
    duration_ms: float
    depth: int = 0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "label": self.label,
            "start_ms": self.start_ms,
            "duration_ms": self.duration_ms,
            "depth": self.depth,
        }


@dataclass(frozen=True, slots=True)
class VisualizationData:
    """Data payloads for timeline, histograms, charts, and flame graphs."""

    execution_timeline: tuple[TimelineSlice, ...] = ()
    latency_histogram: tuple[HistogramBucket, ...] = ()
    token_histogram: tuple[HistogramBucket, ...] = ()
    cost_breakdown: dict[str, float] = field(default_factory=dict)
    pie_charts: dict[str, dict[str, float]] = field(default_factory=dict)
    bar_charts: dict[str, dict[str, float]] = field(default_factory=dict)
    flame_graph: tuple[TimelineSlice, ...] = ()
    waterfall: tuple[TimelineSlice, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "execution_timeline": [
                timeline_slice.to_dict() for timeline_slice in self.execution_timeline
            ],
            "latency_histogram": [
                bucket.to_dict() for bucket in self.latency_histogram
            ],
            "token_histogram": [bucket.to_dict() for bucket in self.token_histogram],
            "cost_breakdown": self.cost_breakdown,
            "pie_charts": self.pie_charts,
            "bar_charts": self.bar_charts,
            "flame_graph": [item.to_dict() for item in self.flame_graph],
            "waterfall": [item.to_dict() for item in self.waterfall],
        }


@dataclass(frozen=True, slots=True)
class ProfilingReport:
    """Complete read-only profile report for one AgentReplay run."""

    run_id: str
    run_name: str | None
    duration: DurationAnalysis
    tool_duration: DurationAnalysis
    llm_duration: DurationAnalysis
    memory_duration: DurationAnalysis
    replay_duration: DurationAnalysis
    diff_duration: DurationAnalysis
    token_analysis: TokenAnalysis
    cost_analysis: CostAnalysis
    model_analysis: ModelAnalysis
    tool_analysis: ToolAnalysis
    memory_analysis: MemoryAnalysis
    bottlenecks: tuple[Bottleneck, ...]
    recommendations: tuple[OptimizationRecommendation, ...]
    visualizations: VisualizationData
    custom_metrics: dict[str, JSONValue] = field(default_factory=dict)

    def summary(self) -> str:
        """Return a concise human-readable summary."""
        return (
            f"Profile for {self.run_id}: {self.duration.count} events, "
            f"{self.duration.total_ms:.3f} ms total, "
            f"{self.token_analysis.total_tokens} tokens, "
            f"{self.cost_analysis.total_cost:.6f} cost, "
            f"{len(self.bottlenecks)} bottlenecks."
        )

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "run_id": self.run_id,
            "run_name": self.run_name,
            "summary": self.summary(),
            "duration": self.duration.to_dict(),
            "tool_duration": self.tool_duration.to_dict(),
            "llm_duration": self.llm_duration.to_dict(),
            "memory_duration": self.memory_duration.to_dict(),
            "replay_duration": self.replay_duration.to_dict(),
            "diff_duration": self.diff_duration.to_dict(),
            "token_analysis": self.token_analysis.to_dict(),
            "cost_analysis": self.cost_analysis.to_dict(),
            "model_analysis": self.model_analysis.to_dict(),
            "tool_analysis": self.tool_analysis.to_dict(),
            "memory_analysis": self.memory_analysis.to_dict(),
            "bottlenecks": [bottleneck.to_dict() for bottleneck in self.bottlenecks],
            "recommendations": [
                recommendation.to_dict() for recommendation in self.recommendations
            ],
            "visualizations": self.visualizations.to_dict(),
            "custom_metrics": self.custom_metrics,
        }


__all__ = [
    "Bottleneck",
    "BottleneckSeverity",
    "CostAnalysis",
    "DurationAnalysis",
    "HistogramBucket",
    "MemoryAnalysis",
    "ModelAnalysis",
    "ModelProfile",
    "OptimizationRecommendation",
    "ProfilingReport",
    "RecommendationCategory",
    "TimelineSlice",
    "TokenAnalysis",
    "ToolAnalysis",
    "ToolProfile",
    "VisualizationData",
]
