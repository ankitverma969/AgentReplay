"""Typed models for AgentReplay regression and root-cause analysis."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue

RegressionKind: TypeAlias = Literal["regression", "improvement", "behavior_change"]
RegressionCategory: TypeAlias = Literal[
    "performance",
    "cost",
    "quality",
    "tooling",
    "model",
    "memory",
    "infrastructure",
    "configuration",
    "security",
    "custom",
]
RegressionSeverity: TypeAlias = Literal[
    "critical",
    "high",
    "medium",
    "low",
    "informational",
]


@dataclass(frozen=True, slots=True)
class MetricDelta:
    """One numeric metric comparison between baseline and target."""

    name: str
    baseline: float
    target: float
    delta: float
    percent_change: float

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "name": self.name,
            "baseline": self.baseline,
            "target": self.target,
            "delta": self.delta,
            "percent_change": self.percent_change,
        }


@dataclass(frozen=True, slots=True)
class ImpactEstimate:
    """Estimated production impact of detected changes."""

    execution_time_ms: float = 0.0
    cost: float = 0.0
    tokens: int = 0
    failure_rate: float = 0.0
    reliability: float = 0.0
    tool_usage: int = 0
    memory_usage: int = 0

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "execution_time_ms": self.execution_time_ms,
            "cost": self.cost,
            "tokens": self.tokens,
            "failure_rate": self.failure_rate,
            "reliability": self.reliability,
            "tool_usage": self.tool_usage,
            "memory_usage": self.memory_usage,
        }


@dataclass(frozen=True, slots=True)
class RootCause:
    """Root-cause explanation for one regression finding."""

    what_changed: str
    where_changed: str
    when_changed: str
    likely_cause: str
    affected_downstream_events: tuple[str, ...]
    confidence: float

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "what_changed": self.what_changed,
            "where_changed": self.where_changed,
            "when_changed": self.when_changed,
            "likely_cause": self.likely_cause,
            "affected_downstream_events": list(self.affected_downstream_events),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class RegressionFinding:
    """One detected regression, improvement, or behavioral change."""

    finding_id: str
    kind: RegressionKind
    category: RegressionCategory
    severity: RegressionSeverity
    title: str
    description: str
    location: str
    baseline_value: JSONValue
    target_value: JSONValue
    metric_delta: MetricDelta | None
    root_cause: RootCause
    recommendations: tuple[str, ...] = ()
    evidence_event_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "finding_id": self.finding_id,
            "kind": self.kind,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "baseline_value": self.baseline_value,
            "target_value": self.target_value,
            "metric_delta": (
                None if self.metric_delta is None else self.metric_delta.to_dict()
            ),
            "root_cause": self.root_cause.to_dict(),
            "recommendations": list(self.recommendations),
            "evidence_event_ids": list(self.evidence_event_ids),
        }


@dataclass(frozen=True, slots=True)
class TrendPoint:
    """One run-level trend point across historical executions."""

    run_id: str
    started_at: datetime
    latency_ms: float
    cost: float
    tokens: int
    errors: int
    retries: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "latency_ms": self.latency_ms,
            "cost": self.cost,
            "tokens": self.tokens,
            "errors": self.errors,
            "retries": self.retries,
        }


@dataclass(frozen=True, slots=True)
class TrendAnalysis:
    """Trend analysis across many historical runs."""

    points: tuple[TrendPoint, ...] = ()
    latency_direction: str = "stable"
    cost_direction: str = "stable"
    token_direction: str = "stable"
    error_direction: str = "stable"
    retry_direction: str = "stable"

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "points": [point.to_dict() for point in self.points],
            "latency_direction": self.latency_direction,
            "cost_direction": self.cost_direction,
            "token_direction": self.token_direction,
            "error_direction": self.error_direction,
            "retry_direction": self.retry_direction,
        }


@dataclass(frozen=True, slots=True)
class VisualComparison:
    """Visualization-ready regression report data."""

    regression_timeline: tuple[dict[str, JSONValue], ...] = ()
    execution_graph_diff: tuple[dict[str, JSONValue], ...] = ()
    latency_comparison: tuple[MetricDelta, ...] = ()
    cost_comparison: tuple[MetricDelta, ...] = ()
    token_comparison: tuple[MetricDelta, ...] = ()
    tool_comparison: tuple[dict[str, JSONValue], ...] = ()
    model_comparison: tuple[dict[str, JSONValue], ...] = ()

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "regression_timeline": [dict(item) for item in self.regression_timeline],
            "execution_graph_diff": [dict(item) for item in self.execution_graph_diff],
            "latency_comparison": [
                metric.to_dict() for metric in self.latency_comparison
            ],
            "cost_comparison": [metric.to_dict() for metric in self.cost_comparison],
            "token_comparison": [metric.to_dict() for metric in self.token_comparison],
            "tool_comparison": [dict(item) for item in self.tool_comparison],
            "model_comparison": [dict(item) for item in self.model_comparison],
        }


@dataclass(frozen=True, slots=True)
class RegressionSummary:
    """Aggregate finding counts for a regression report."""

    regressions: int = 0
    improvements: int = 0
    behavior_changes: int = 0
    by_severity: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_findings(
        cls,
        findings: tuple[RegressionFinding, ...],
    ) -> RegressionSummary:
        """Build summary counts from findings."""
        kinds = Counter(finding.kind for finding in findings)
        severities = Counter(finding.severity for finding in findings)
        categories = Counter(finding.category for finding in findings)
        return cls(
            regressions=kinds["regression"],
            improvements=kinds["improvement"],
            behavior_changes=kinds["behavior_change"],
            by_severity={str(key): value for key, value in severities.items()},
            by_category={str(key): value for key, value in categories.items()},
        )

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "regressions": self.regressions,
            "improvements": self.improvements,
            "behavior_changes": self.behavior_changes,
            "by_severity": self.by_severity,
            "by_category": self.by_category,
        }


@dataclass(frozen=True, slots=True)
class RegressionReport:
    """Complete regression analysis report."""

    baseline_run_id: str
    target_run_id: str
    generated_at: datetime
    findings: tuple[RegressionFinding, ...]
    metric_deltas: tuple[MetricDelta, ...]
    impact: ImpactEstimate
    recommendations: tuple[str, ...]
    trend: TrendAnalysis
    visualizations: VisualComparison
    plugin_results: dict[str, JSONValue] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def summary_counts(self) -> RegressionSummary:
        """Return aggregate summary counts."""
        return RegressionSummary.from_findings(self.findings)

    def summary(self) -> str:
        """Return a concise human-readable summary."""
        counts = self.summary_counts
        return (
            f"Regression analysis {self.baseline_run_id} -> {self.target_run_id}: "
            f"{counts.regressions} regressions, {counts.improvements} improvements, "
            f"{counts.behavior_changes} behavioral changes."
        )

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation."""
        return {
            "baseline_run_id": self.baseline_run_id,
            "target_run_id": self.target_run_id,
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary(),
            "summary_counts": self.summary_counts.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "metric_deltas": [metric.to_dict() for metric in self.metric_deltas],
            "impact": self.impact.to_dict(),
            "recommendations": list(self.recommendations),
            "trend": self.trend.to_dict(),
            "visualizations": self.visualizations.to_dict(),
            "plugin_results": self.plugin_results,
            "warnings": list(self.warnings),
        }


__all__ = [
    "ImpactEstimate",
    "MetricDelta",
    "RegressionCategory",
    "RegressionFinding",
    "RegressionKind",
    "RegressionReport",
    "RegressionSeverity",
    "RegressionSummary",
    "RootCause",
    "TrendAnalysis",
    "TrendPoint",
    "VisualComparison",
]
