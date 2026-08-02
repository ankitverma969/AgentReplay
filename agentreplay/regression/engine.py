"""Regression detection and root-cause analysis engine for AgentReplay."""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol, cast

from agentreplay.core.events import (
    EXCEPTION_RAISED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    SYSTEM_PROMPT,
    TOOL_CALL,
    TOOL_FAILED,
    TOOL_FINISHED,
    TOOL_STARTED,
    USER_PROMPT,
    WARNING_RAISED,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.diff import DiffEngine
from agentreplay.diff.models import DiffChange, DiffResult
from agentreplay.exceptions import DiffError, ProfilerError, RegressionError
from agentreplay.profiler import ProfilerEngine
from agentreplay.profiler.models import ProfilingReport
from agentreplay.regression.models import (
    ImpactEstimate,
    MetricDelta,
    RegressionCategory,
    RegressionFinding,
    RegressionKind,
    RegressionReport,
    RegressionSeverity,
    RootCause,
    TrendAnalysis,
    TrendPoint,
    VisualComparison,
)
from agentreplay.storage import Pagination, RunQuery, SQLiteStorage, StorageBackend
from agentreplay.types import JSONValue

RegressionInput = TraceSnapshot | str
RegressionRuleFunction = Callable[[TraceSnapshot, TraceSnapshot], Iterable[object]]
RegressionAnalyzerFunction = Callable[[RegressionReport], JSONValue]
RegressionRecommendationFunction = Callable[[RegressionReport], Iterable[object]]

_TOOL_EVENTS = frozenset((TOOL_CALL, TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED))
_LLM_EVENTS = frozenset((LLM_REQUEST, LLM_RESPONSE))
_MEMORY_EVENTS = frozenset((MEMORY_READ, MEMORY_WRITE))
_PROMPT_EVENTS = frozenset((USER_PROMPT, SYSTEM_PROMPT))
_LATENCY_THRESHOLD = 0.20
_COST_THRESHOLD = 0.10
_TOKEN_THRESHOLD = 0.10


class CustomRegressionRule(Protocol):
    """Protocol for plugin-provided regression rules."""

    def analyze(
        self,
        baseline: TraceSnapshot,
        target: TraceSnapshot,
    ) -> Iterable[object]:
        """Return custom regression findings."""


class CustomRegressionAnalyzer(Protocol):
    """Protocol for plugin-provided regression analyzers."""

    def analyze(self, report: RegressionReport) -> JSONValue:
        """Return custom analyzer output."""


class CustomRegressionRecommendation(Protocol):
    """Protocol for plugin-provided regression recommendations."""

    def recommend(self, report: RegressionReport) -> Iterable[object]:
        """Return custom recommendation payloads."""


class RegressionEngine:
    """Detect regressions, improvements, and root causes from recorded traces."""

    def __init__(
        self,
        storage: StorageBackend | None = None,
        *,
        profiler_engine: ProfilerEngine | None = None,
        diff_engine: DiffEngine | None = None,
        custom_rules: Mapping[str, CustomRegressionRule | RegressionRuleFunction]
        | None = None,
        custom_analyzers: (
            Mapping[str, CustomRegressionAnalyzer | RegressionAnalyzerFunction] | None
        ) = None,
        custom_recommendations: (
            Mapping[
                str,
                CustomRegressionRecommendation | RegressionRecommendationFunction,
            ]
            | None
        ) = None,
    ) -> None:
        """Create a regression analysis engine."""
        self._storage = storage
        self._profiler = profiler_engine
        self._diff = diff_engine
        self._custom_rules = dict(custom_rules or {})
        self._custom_analyzers = dict(custom_analyzers or {})
        self._custom_recommendations = dict(custom_recommendations or {})

    def compare(
        self,
        baseline: RegressionInput,
        target: RegressionInput,
        *,
        history: Sequence[RegressionInput] = (),
    ) -> RegressionReport:
        """Compare two executions and return a regression report."""
        baseline_trace = self._resolve_trace(baseline)
        target_trace = self._resolve_trace(target)
        baseline_profile = self._profile(baseline_trace)
        target_profile = self._profile(target_trace)
        diff = self._diff_result(baseline_trace, target_trace)
        context = _AnalysisContext(
            baseline=baseline_trace,
            target=target_trace,
            baseline_profile=baseline_profile,
            target_profile=target_profile,
            diff=diff,
        )
        metric_deltas = _metric_deltas(
            baseline_profile,
            target_profile,
            baseline_trace,
            target_trace,
        )
        findings = [
            *_metric_findings(context, metric_deltas),
            *_behavior_findings(context),
            *self._custom_findings(baseline_trace, target_trace),
        ]
        trend = self.trends((*history, baseline_trace, target_trace))
        impact = _impact(metric_deltas, baseline_trace, target_trace)
        report = RegressionReport(
            baseline_run_id=baseline_trace.run.run_id,
            target_run_id=target_trace.run.run_id,
            generated_at=datetime.now(UTC),
            findings=tuple(_dedupe_findings(findings)),
            metric_deltas=metric_deltas,
            impact=impact,
            recommendations=(),
            trend=trend,
            visualizations=_visualizations(context, metric_deltas),
            plugin_results={},
            warnings=diff.warnings,
        )
        recommendations = _recommendations(report)
        plugin_results = self._custom_analysis(report)
        recommendations = (*recommendations, *self._custom_recommendations_for(report))
        return RegressionReport(
            baseline_run_id=report.baseline_run_id,
            target_run_id=report.target_run_id,
            generated_at=report.generated_at,
            findings=report.findings,
            metric_deltas=report.metric_deltas,
            impact=report.impact,
            recommendations=tuple(dict.fromkeys(recommendations)),
            trend=report.trend,
            visualizations=report.visualizations,
            plugin_results=plugin_results,
            warnings=report.warnings,
        )

    def compare_many(
        self,
        target: RegressionInput,
        baselines: Sequence[RegressionInput],
    ) -> tuple[RegressionReport, ...]:
        """Compare one target run against multiple historical baselines."""
        return tuple(
            self.compare(baseline, target, history=baselines) for baseline in baselines
        )

    def compare_to_latest(self, baseline: RegressionInput) -> RegressionReport:
        """Compare a baseline run to the latest stored run."""
        return self.compare(baseline, "latest")

    def compare_to_last_successful(self, target: RegressionInput) -> RegressionReport:
        """Compare a target run to the last successful stored run before it."""
        target_trace = self._resolve_trace(target)
        baseline = self._last_successful_before(target_trace.run)
        return self.compare(baseline.run_id, target_trace)

    def compare_named_baseline(
        self,
        baseline_name: str,
        target: RegressionInput,
    ) -> RegressionReport:
        """Compare a target run to the latest run with a baseline name."""
        baseline = self._named_baseline(baseline_name)
        return self.compare(baseline.run_id, target)

    def trends(self, values: Sequence[RegressionInput]) -> TrendAnalysis:
        """Analyze latency, cost, token, error, and retry trends across runs."""
        points = tuple(
            sorted(
                (_trend_point(self._resolve_trace(value)) for value in values),
                key=lambda point: point.started_at,
            )
        )
        return TrendAnalysis(
            points=points,
            latency_direction=_direction([point.latency_ms for point in points]),
            cost_direction=_direction([point.cost for point in points]),
            token_direction=_direction([point.tokens for point in points]),
            error_direction=_direction([point.errors for point in points]),
            retry_direction=_direction([point.retries for point in points]),
        )

    def load(self, run_id: str) -> TraceSnapshot:
        """Load a trace from configured storage."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        resolved_run_id = self.resolve_run_id(run_id)
        run = storage.load_run(resolved_run_id)
        if run is None:
            msg = f"Regression run not found: {resolved_run_id}"
            raise RegressionError(msg)
        return TraceSnapshot(
            run=run,
            events=tuple(storage.stream_events(resolved_run_id, batch_size=5_000)),
        )

    def resolve_run_id(self, run_id: str) -> str:
        """Resolve special run identifiers used by regression workflows."""
        if run_id == "latest":
            return self._latest_run().run_id
        if run_id == "last-successful":
            return self._last_successful().run_id
        if run_id.startswith("baseline:"):
            return self._named_baseline(run_id.removeprefix("baseline:")).run_id
        return run_id

    def close(self) -> None:
        """Release owned storage resources."""
        if self._storage is not None:
            self._storage.close()

    def _resolve_trace(self, value: RegressionInput) -> TraceSnapshot:
        """Resolve a trace input without executing anything."""
        return value if isinstance(value, TraceSnapshot) else self.load(value)

    def _profile(self, trace: TraceSnapshot) -> ProfilingReport:
        """Build a profile for a trace."""
        profiler = (
            ProfilerEngine(storage=self._storage)
            if self._profiler is None
            else self._profiler
        )
        try:
            return profiler.profile(trace)
        except ProfilerError as exc:
            msg = f"Regression profile failed for {trace.run.run_id}: {exc}"
            raise RegressionError(msg) from exc

    def _diff_result(
        self,
        baseline: TraceSnapshot,
        target: TraceSnapshot,
    ) -> DiffResult:
        """Build a diff result for two traces."""
        diff = DiffEngine(storage=self._storage) if self._diff is None else self._diff
        try:
            return diff.compare(baseline, target)
        except DiffError as exc:
            msg = f"Regression diff failed: {exc}"
            raise RegressionError(msg) from exc

    def _custom_findings(
        self,
        baseline: TraceSnapshot,
        target: TraceSnapshot,
    ) -> tuple[RegressionFinding, ...]:
        """Run plugin-provided custom rules safely."""
        findings: list[RegressionFinding] = []
        for name, rule in self._custom_rules.items():
            try:
                values = (
                    rule(baseline, target)
                    if callable(rule)
                    else rule.analyze(baseline, target)
                )
            except Exception as exc:
                findings.append(_custom_failure(name, str(exc)))
                continue
            findings.extend(
                value for value in values if isinstance(value, RegressionFinding)
            )
        return tuple(findings)

    def _custom_analysis(self, report: RegressionReport) -> dict[str, JSONValue]:
        """Run plugin-provided analyzers safely."""
        results: dict[str, JSONValue] = {}
        for name, analyzer in self._custom_analyzers.items():
            try:
                value = (
                    analyzer(report) if callable(analyzer) else analyzer.analyze(report)
                )
            except Exception as exc:
                results[name] = {"error": str(exc)}
            else:
                results[name] = _json_value(value)
        return results

    def _custom_recommendations_for(
        self,
        report: RegressionReport,
    ) -> tuple[str, ...]:
        """Run plugin-provided recommendation sources safely."""
        recommendations: list[str] = []
        for name, recommender in self._custom_recommendations.items():
            try:
                values = (
                    recommender(report)
                    if callable(recommender)
                    else recommender.recommend(report)
                )
            except Exception as exc:
                recommendations.append(f"Review custom recommender {name}: {exc}")
                continue
            recommendations.extend(str(value) for value in values)
        return tuple(recommendations)

    def _latest_run(self) -> RunRecord:
        """Return the latest stored run."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.list_runs(pagination=Pagination(limit=1))
        if not runs:
            msg = "No recorded runs found."
            raise RegressionError(msg)
        return runs[0]

    def _last_successful(self) -> RunRecord:
        """Return the latest completed stored run."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.search_runs(
            RunQuery(statuses=("completed",), pagination=Pagination(limit=1))
        )
        if not runs:
            msg = "No successful recorded runs found."
            raise RegressionError(msg)
        return runs[0]

    def _last_successful_before(self, run: RunRecord) -> RunRecord:
        """Return the latest completed run before a target run."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.search_runs(
            RunQuery(
                statuses=("completed",),
                started_before=run.started_at,
                pagination=Pagination(limit=1),
            )
        )
        if not runs:
            msg = f"No successful baseline found before {run.run_id}."
            raise RegressionError(msg)
        return runs[0]

    def _named_baseline(self, name: str) -> RunRecord:
        """Return the latest stored run matching a baseline name."""
        storage = SQLiteStorage() if self._storage is None else self._storage
        self._storage = storage
        runs = storage.search_runs(
            RunQuery(
                name_contains=name,
                tags=("baseline",),
                pagination=Pagination(limit=1),
            )
        )
        if not runs:
            msg = f"No named baseline found: {name}"
            raise RegressionError(msg)
        return runs[0]


class _AnalysisContext:
    """Internal immutable-ish context for finding generation."""

    def __init__(
        self,
        *,
        baseline: TraceSnapshot,
        target: TraceSnapshot,
        baseline_profile: ProfilingReport,
        target_profile: ProfilingReport,
        diff: DiffResult,
    ) -> None:
        self.baseline = baseline
        self.target = target
        self.baseline_profile = baseline_profile
        self.target_profile = target_profile
        self.diff = diff
        self.target_by_id = {event.event_id: event for event in target.events}
        self.descendants = _descendant_index(target.events)

    def downstream(self, event_id: str | None, *, limit: int = 20) -> tuple[str, ...]:
        """Return downstream target events for an evidence event id."""
        if event_id is None:
            return ()
        return self.descendants.get(event_id, ())[:limit]


def _metric_deltas(
    baseline: ProfilingReport,
    target: ProfilingReport,
    baseline_trace: TraceSnapshot,
    target_trace: TraceSnapshot,
) -> tuple[MetricDelta, ...]:
    """Build metric deltas from profile reports."""
    values = (
        (
            "execution_time_ms",
            baseline.duration.total_ms,
            target.duration.total_ms,
        ),
        (
            "latency_average_ms",
            baseline.duration.average_ms,
            target.duration.average_ms,
        ),
        (
            "llm_latency_ms",
            baseline.llm_duration.total_ms,
            target.llm_duration.total_ms,
        ),
        (
            "tool_latency_ms",
            baseline.tool_duration.total_ms,
            target.tool_duration.total_ms,
        ),
        ("cost", baseline.cost_analysis.total_cost, target.cost_analysis.total_cost),
        (
            "tokens",
            float(baseline.token_analysis.total_tokens),
            float(target.token_analysis.total_tokens),
        ),
        (
            "retries",
            float(_retry_count(baseline, baseline_trace)),
            float(_retry_count(target, target_trace)),
        ),
        (
            "errors",
            float(_error_count(baseline, baseline_trace)),
            float(_error_count(target, target_trace)),
        ),
        (
            "failure_rate",
            _failure_rate(baseline_trace),
            _failure_rate(target_trace),
        ),
        (
            "warnings",
            float(_warning_count(baseline, baseline_trace)),
            float(_warning_count(target, target_trace)),
        ),
        (
            "memory_operations",
            float(baseline.memory_analysis.reads + baseline.memory_analysis.writes),
            float(target.memory_analysis.reads + target.memory_analysis.writes),
        ),
    )
    return tuple(_delta(name, old, new) for name, old, new in values)


def _metric_findings(
    context: _AnalysisContext,
    deltas: tuple[MetricDelta, ...],
) -> tuple[RegressionFinding, ...]:
    """Detect numeric metric regressions and improvements."""
    findings: list[RegressionFinding] = []
    for metric in deltas:
        if metric.delta == 0:
            continue
        threshold = _threshold(metric.name)
        if abs(metric.percent_change) < threshold and abs(metric.delta) < 1:
            continue
        kind = _metric_kind(metric.name, metric.delta)
        title = _metric_title(metric.name, kind)
        severity = _metric_severity(metric)
        category = _metric_category(metric.name)
        findings.append(
            _finding(
                context,
                kind=kind,
                category=category,
                severity=severity,
                title=title,
                description=(
                    f"{metric.name.replace('_', ' ').title()} changed by "
                    f"{metric.delta:.3f} ({metric.percent_change:.1%})."
                ),
                location=f"metrics.{metric.name}",
                baseline_value=metric.baseline,
                target_value=metric.target,
                metric_delta=metric,
                likely_cause=_metric_cause(metric, context),
                recommendations=_metric_recommendations(metric),
            )
        )
    return tuple(findings)


def _behavior_findings(context: _AnalysisContext) -> tuple[RegressionFinding, ...]:
    """Detect behavioral changes from the execution diff."""
    findings: list[RegressionFinding] = []
    for change in context.diff.changes:
        category = _diff_category(change)
        severity = _diff_severity(change)
        kind = _diff_kind(change)
        findings.append(
            _finding(
                context,
                kind=kind,
                category=category,
                severity=severity,
                title=_diff_title(change),
                description=change.description,
                location=change.location,
                baseline_value=change.old_value,
                target_value=change.new_value,
                metric_delta=None,
                likely_cause=_diff_cause(change),
                recommendations=_diff_recommendations(change),
                evidence_event_ids=tuple(
                    event_id
                    for event_id in (change.old_event_id, change.new_event_id)
                    if event_id is not None
                ),
                event_id=change.new_event_id or change.old_event_id,
            )
        )
    return tuple(findings)


def _finding(
    context: _AnalysisContext,
    *,
    kind: str,
    category: RegressionCategory,
    severity: RegressionSeverity,
    title: str,
    description: str,
    location: str,
    baseline_value: JSONValue,
    target_value: JSONValue,
    metric_delta: MetricDelta | None,
    likely_cause: str,
    recommendations: tuple[str, ...] = (),
    evidence_event_ids: tuple[str, ...] = (),
    event_id: str | None = None,
) -> RegressionFinding:
    """Build one regression finding with root-cause details."""
    stable_id = f"{category}:{location}:{title}".replace(" ", "_").lower()
    return RegressionFinding(
        finding_id=stable_id[:180],
        kind=cast(RegressionKind, kind),
        category=category,
        severity=severity,
        title=title,
        description=description,
        location=location,
        baseline_value=baseline_value,
        target_value=target_value,
        metric_delta=metric_delta,
        root_cause=RootCause(
            what_changed=description,
            where_changed=location,
            when_changed=_when_changed(context, event_id),
            likely_cause=likely_cause,
            affected_downstream_events=context.downstream(event_id),
            confidence=_confidence(metric_delta, evidence_event_ids),
        ),
        recommendations=recommendations,
        evidence_event_ids=evidence_event_ids,
    )


def _delta(name: str, baseline: float, target: float) -> MetricDelta:
    """Return a numeric metric delta."""
    delta = target - baseline
    denominator = abs(baseline) if baseline != 0 else 1.0
    return MetricDelta(
        name=name,
        baseline=baseline,
        target=target,
        delta=delta,
        percent_change=delta / denominator,
    )


def _threshold(name: str) -> float:
    """Return detection threshold for a metric."""
    if "cost" in name:
        return _COST_THRESHOLD
    if "token" in name:
        return _TOKEN_THRESHOLD
    if "latency" in name or "time" in name:
        return _LATENCY_THRESHOLD
    return 0.0


def _metric_kind(name: str, delta: float) -> str:
    """Classify a metric delta as regression or improvement."""
    if name in {"errors", "warnings", "retries", "failure_rate"}:
        return "regression" if delta > 0 else "improvement"
    if name == "memory_operations":
        return "behavior_change"
    return "regression" if delta > 0 else "improvement"


def _metric_category(name: str) -> RegressionCategory:
    """Map a metric to a regression category."""
    if "latency" in name or "time" in name:
        return "performance"
    if "cost" in name:
        return "cost"
    if "token" in name:
        return "cost"
    if "retry" in name or "error" in name or "warning" in name or "failure" in name:
        return "infrastructure"
    if "memory" in name:
        return "memory"
    return "custom"


def _metric_title(metric: str, kind: str) -> str:
    """Return a human-readable metric finding title."""
    direction = "Decreased" if kind == "improvement" else "Increased"
    return f"{metric.replace('_', ' ').title()} {direction}"


def _metric_severity(metric: MetricDelta) -> RegressionSeverity:
    """Assign severity for a metric delta."""
    magnitude = abs(metric.percent_change)
    if metric.name in {"errors", "retries"} and metric.delta > 0:
        return "critical" if metric.delta >= 3 else "high"
    if magnitude >= 1.0:
        return "high"
    if magnitude >= 0.5:
        return "medium"
    if magnitude >= 0.1:
        return "low"
    return "informational"


def _metric_cause(metric: MetricDelta, context: _AnalysisContext) -> str:
    """Infer likely cause for a metric change from profile and diff evidence."""
    changed_categories = {change.category for change in context.diff.changes}
    if (
        metric.name.startswith("llm")
        and {"model", "provider", "llm"} & changed_categories
    ):
        return "Model or provider request behavior changed upstream of latency."
    if "tool" in metric.name and "tool_calls" in changed_categories:
        return "Tool selection, order, or output changed."
    if "token" in metric.name and {"prompt", "system_prompt"} & changed_categories:
        return "Prompt content or context size changed."
    if (
        "cost" in metric.name
        and {"model", "provider", "token_usage"} & changed_categories
    ):
        return "Model/provider selection or token usage changed."
    if metric.name in {"errors", "retries", "warnings"}:
        return "Failure, warning, or retry behavior changed in the target run."
    return "Recorded metrics changed without a more specific upstream diff signal."


def _metric_recommendations(metric: MetricDelta) -> tuple[str, ...]:
    """Return recommendations for a metric finding."""
    if metric.name in {"tokens", "cost"} and metric.delta > 0:
        return ("Reduce prompt size.", "Switch model if quality permits.")
    if "latency" in metric.name or "time" in metric.name:
        if metric.delta > 0:
            return (
                "Cache tool results.",
                "Parallelize independent tool execution.",
                "Review slowest model and tool spans.",
            )
        return ("Preserve the change that reduced latency.",)
    if metric.name == "retries" and metric.delta > 0:
        return ("Reduce retries.", "Tune retry policy and backoff.")
    if metric.name == "memory_operations":
        return ("Optimize memory usage.", "Cache repeated memory reads.")
    return ()


def _diff_kind(change: DiffChange) -> str:
    """Classify a diff change."""
    if change.change_type in {"added", "removed", "modified"}:
        return "behavior_change"
    return "improvement"


def _diff_category(change: DiffChange) -> RegressionCategory:
    """Map diff categories into regression categories."""
    category = change.category
    if category in {"latency", "execution_time"}:
        return "performance"
    if category in {"cost", "token_usage"}:
        return "cost"
    if category in {"prompt", "system_prompt", "assistant_response"}:
        return "quality"
    if category in {"tool_calls", "tool_outputs", "function_calls"}:
        return "tooling"
    if category in {"model", "provider", "llm"}:
        return "model"
    if category == "memory":
        return "memory"
    if category in {"errors", "warnings", "retries"}:
        return "infrastructure"
    if "security" in category:
        return "security"
    if category in {"custom_metadata", "metadata", "run_metadata"}:
        return "configuration"
    return "custom"


def _diff_severity(change: DiffChange) -> RegressionSeverity:
    """Map diff severity into regression severity."""
    if change.severity == "critical":
        return "critical"
    if change.severity == "high":
        return "high"
    if change.severity == "medium":
        return "medium"
    if change.severity == "low":
        return "low"
    return "informational"


def _diff_title(change: DiffChange) -> str:
    """Return a recognizable behavior-change title."""
    if change.category in {"prompt", "system_prompt"}:
        return "Prompt changed"
    if change.category == "assistant_response":
        return "Response changed"
    if change.category == "model":
        return "Different model"
    if change.category == "provider":
        return "Different provider"
    if change.category == "tool_calls":
        if change.change_type == "added":
            return "Additional tool call"
        if change.change_type == "removed":
            return "Missing tool call"
        return "Tool changed"
    if change.category == "execution_graph":
        return "Execution graph changed"
    return change.description.rstrip(".")


def _diff_cause(change: DiffChange) -> str:
    """Infer likely cause from one diff change."""
    if change.category in {"prompt", "system_prompt"}:
        return "Input instructions or context changed before model execution."
    if change.category in {"model", "provider", "llm"}:
        return "Model/provider configuration changed."
    if change.category in {"tool_calls", "tool_outputs", "function_calls"}:
        return "Tool routing, arguments, or tool behavior changed."
    if change.category == "execution_graph":
        return "Parent-child event relationships changed the execution path."
    if change.category in {"errors", "warnings", "retries"}:
        return "Runtime reliability signals changed."
    if change.category == "memory":
        return "Memory read/write state changed."
    return "Recorded event data changed."


def _diff_recommendations(change: DiffChange) -> tuple[str, ...]:
    """Return recommendations for one behavioral diff."""
    if change.category in {"prompt", "system_prompt"}:
        return ("Reduce prompt size.", "Review prompt template changes.")
    if change.category == "tool_calls":
        return ("Cache tool results.", "Remove duplicate calls.")
    if change.category == "execution_graph":
        return ("Review conditional branches and handoff routing.",)
    if change.category in {"model", "provider"}:
        return ("Switch model if regression is not intentional.",)
    if change.category in {"errors", "retries"}:
        return ("Reduce retries.", "Inspect failing upstream dependency.")
    if change.category == "memory":
        return ("Optimize memory usage.",)
    return ()


def _when_changed(context: _AnalysisContext, event_id: str | None) -> str:
    """Return when a finding changed in target execution time."""
    if event_id is None:
        return context.target.run.started_at.isoformat()
    event = context.target_by_id.get(event_id)
    if event is None:
        return context.target.run.started_at.isoformat()
    return event.timestamp.isoformat()


def _confidence(
    metric_delta: MetricDelta | None,
    evidence_event_ids: tuple[str, ...],
) -> float:
    """Estimate confidence for a root-cause explanation."""
    score = 0.55
    if metric_delta is not None:
        score += min(abs(metric_delta.percent_change), 1.0) * 0.25
    if evidence_event_ids:
        score += 0.20
    return min(score, 0.98)


def _impact(
    deltas: tuple[MetricDelta, ...],
    baseline: TraceSnapshot,
    target: TraceSnapshot,
) -> ImpactEstimate:
    """Build impact estimate from metric deltas."""
    by_name = {metric.name: metric for metric in deltas}
    errors_delta = int(by_name["errors"].delta)
    baseline_errors = max(_event_count(baseline.events, EXCEPTION_RAISED), 1)
    target_errors = _event_count(target.events, EXCEPTION_RAISED)
    failure_rate = target_errors / max(len(target.events), 1)
    baseline_failure_rate = baseline_errors / max(len(baseline.events), 1)
    return ImpactEstimate(
        execution_time_ms=by_name["execution_time_ms"].delta,
        cost=by_name["cost"].delta,
        tokens=int(by_name["tokens"].delta),
        failure_rate=failure_rate - baseline_failure_rate,
        reliability=float(-errors_delta),
        tool_usage=_tool_count(target.events) - _tool_count(baseline.events),
        memory_usage=int(by_name["memory_operations"].delta),
    )


def _recommendations(report: RegressionReport) -> tuple[str, ...]:
    """Generate report-level recommendations."""
    recommendations: list[str] = []
    for finding in report.findings:
        recommendations.extend(finding.recommendations)
    if report.impact.cost > 0:
        recommendations.append("Reduce high-cost operations first.")
    if report.impact.execution_time_ms > 0:
        recommendations.append(
            "Profile the slowest target events before changing code."
        )
    if report.impact.tokens > 0:
        recommendations.append("Reduce prompt size.")
    if report.impact.tool_usage > 0:
        recommendations.append("Remove duplicate calls.")
    if report.impact.memory_usage > 0:
        recommendations.append("Optimize memory usage.")
    return tuple(dict.fromkeys(recommendations))


def _visualizations(
    context: _AnalysisContext,
    deltas: tuple[MetricDelta, ...],
) -> VisualComparison:
    """Build visualization-ready regression comparison data."""
    graph_changes: list[dict[str, JSONValue]] = [
        {
            "change_type": change.change_type,
            "location": change.location,
            "old_event_id": change.old_event_id,
            "new_event_id": change.new_event_id,
        }
        for change in context.diff.changes
        if change.category == "execution_graph"
    ]
    timeline: list[dict[str, JSONValue]] = [
        {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "timestamp": event.timestamp.isoformat(),
            "duration_ms": event.duration_ms,
        }
        for event in context.target.events[:10_000]
    ]
    tools = _name_comparison(
        _tool_sequence(context.baseline.events),
        _tool_sequence(context.target.events),
        "tool",
    )
    models = _name_comparison(
        _model_sequence(context.baseline.events),
        _model_sequence(context.target.events),
        "model",
    )
    return VisualComparison(
        regression_timeline=tuple(timeline),
        execution_graph_diff=tuple(graph_changes),
        latency_comparison=tuple(
            metric
            for metric in deltas
            if "latency" in metric.name or "time" in metric.name
        ),
        cost_comparison=tuple(metric for metric in deltas if "cost" in metric.name),
        token_comparison=tuple(metric for metric in deltas if "token" in metric.name),
        tool_comparison=tools,
        model_comparison=models,
    )


def _trend_point(trace: TraceSnapshot) -> TrendPoint:
    """Build one trend point from a trace."""
    return TrendPoint(
        run_id=trace.run.run_id,
        started_at=trace.run.started_at,
        latency_ms=sum(_event_latency(event) for event in trace.events),
        cost=sum(_event_cost(event) for event in trace.events),
        tokens=sum(_event_tokens(event) for event in trace.events),
        errors=_event_count(trace.events, EXCEPTION_RAISED),
        retries=_event_count(trace.events, RETRY_RECORDED),
    )


def _direction(values: Sequence[float | int]) -> str:
    """Return trend direction."""
    if len(values) < 2:
        return "stable"
    first = float(values[0])
    last = float(values[-1])
    if abs(last - first) <= max(abs(first), 1.0) * 0.05:
        return "stable"
    return "up" if last > first else "down"


def _dedupe_findings(
    findings: Iterable[RegressionFinding],
) -> tuple[RegressionFinding, ...]:
    """Deduplicate findings by stable id."""
    by_id: dict[str, RegressionFinding] = {}
    for finding in findings:
        by_id.setdefault(finding.finding_id, finding)
    return tuple(by_id.values())


def _descendant_index(events: Sequence[EventRecord]) -> dict[str, tuple[str, ...]]:
    """Build downstream descendant lookups from parent-event links."""
    children: defaultdict[str, list[str]] = defaultdict(list)
    for event in events:
        if event.parent_event_id is not None:
            children[event.parent_event_id].append(event.event_id)
    descendants: dict[str, tuple[str, ...]] = {}
    for event in events:
        seen: list[str] = []
        queue = deque(children.get(event.event_id, ()))
        while queue:
            child = queue.popleft()
            seen.append(child)
            queue.extend(children.get(child, ()))
        descendants[event.event_id] = tuple(seen)
    return descendants


def _retry_count(profile: ProfilingReport, trace: TraceSnapshot) -> int:
    """Return retry count from model and tool profile evidence."""
    return int(
        _event_count(trace.events, RETRY_RECORDED)
        + sum(tool.retry_count for tool in profile.tool_analysis.profiles)
        + sum(
            model.retry_rate * model.execution_count
            for model in profile.model_analysis.profiles
        )
    )


def _error_count(profile: ProfilingReport, trace: TraceSnapshot) -> int:
    """Return approximate failure count from model and tool profile evidence."""
    return int(
        _event_count(trace.events, EXCEPTION_RAISED)
        + sum(
            tool.failure_rate * tool.execution_count
            for tool in profile.tool_analysis.profiles
        )
        + sum(
            model.failure_rate * model.execution_count
            for model in profile.model_analysis.profiles
        )
    )


def _failure_rate(trace: TraceSnapshot) -> float:
    """Return run failure rate from recorded exception events."""
    return _event_count(trace.events, EXCEPTION_RAISED) / max(len(trace.events), 1)


def _warning_count(profile: ProfilingReport, trace: TraceSnapshot) -> int:
    """Return warning count when present in custom profile metrics."""
    value = profile.custom_metrics.get("warnings", 0)
    custom_count = int(value) if isinstance(value, int | float) else 0
    return custom_count + _event_count(trace.events, WARNING_RAISED)


def _event_count(events: Sequence[EventRecord], event_type: str) -> int:
    """Count events of one type."""
    return sum(1 for event in events if event.event_type == event_type)


def _tool_count(events: Sequence[EventRecord]) -> int:
    """Count tool-like events."""
    return sum(1 for event in events if event.event_type in _TOOL_EVENTS)


def _event_latency(event: EventRecord) -> float:
    """Return event latency from duration or payload."""
    value = event.payload.get("latency_ms")
    if isinstance(value, int | float):
        return float(value)
    return max(event.duration_ms, 0.0)


def _event_cost(event: EventRecord) -> float:
    """Return event cost."""
    value = event.payload.get("cost")
    if isinstance(value, Mapping):
        amount = value.get("amount")
        return float(amount) if isinstance(amount, int | float) else 0.0
    return float(value) if isinstance(value, int | float) else 0.0


def _event_tokens(event: EventRecord) -> int:
    """Return event token usage."""
    for key in ("total_tokens", "tokens"):
        value = event.payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, Mapping):
            total = value.get("total_tokens")
            if isinstance(total, int):
                return total
    return 0


def _tool_sequence(events: Sequence[EventRecord]) -> tuple[str, ...]:
    """Return ordered tool names."""
    return tuple(
        name
        for event in events
        if event.event_type in _TOOL_EVENTS
        for name in (_first_str(event.payload, ("tool_name", "function_name", "name")),)
        if name is not None
    )


def _model_sequence(events: Sequence[EventRecord]) -> tuple[str, ...]:
    """Return ordered model names."""
    return tuple(
        name
        for event in events
        if event.event_type in _LLM_EVENTS
        for name in (_first_str(event.payload, ("model_name", "model")),)
        if name is not None
    )


def _name_comparison(
    baseline: tuple[str, ...],
    target: tuple[str, ...],
    name: str,
) -> tuple[dict[str, JSONValue], ...]:
    """Return name-count comparison rows."""
    left = Counter(baseline)
    right = Counter(target)
    return tuple(
        {
            name: item,
            "baseline": left[item],
            "target": right[item],
            "delta": right[item] - left[item],
        }
        for item in sorted(set(left) | set(right))
    )


def _first_str(mapping: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    """Return first non-empty string value under keys."""
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _custom_failure(name: str, error: str) -> RegressionFinding:
    """Return a finding for a failed custom rule."""
    return RegressionFinding(
        finding_id=f"custom:{name}:failed",
        kind="behavior_change",
        category="custom",
        severity="low",
        title=f"Custom regression rule {name} failed",
        description=f"Custom regression rule {name} failed: {error}",
        location=f"plugins.{name}",
        baseline_value=None,
        target_value=error,
        metric_delta=None,
        root_cause=RootCause(
            what_changed="Custom regression rule failed.",
            where_changed=f"plugins.{name}",
            when_changed=datetime.now(UTC).isoformat(),
            likely_cause=error,
            affected_downstream_events=(),
            confidence=0.5,
        ),
        recommendations=(f"Review custom regression rule {name}.",),
    )


def _json_value(value: object) -> JSONValue:
    """Convert extension output to JSON-compatible data."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, str | bytes | bytearray):
        return [_json_value(item) for item in value]
    return str(value)


__all__ = [
    "CustomRegressionAnalyzer",
    "CustomRegressionRecommendation",
    "CustomRegressionRule",
    "RegressionAnalyzerFunction",
    "RegressionEngine",
    "RegressionInput",
    "RegressionRecommendationFunction",
    "RegressionRuleFunction",
]
