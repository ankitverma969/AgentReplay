"""Report renderers for AgentReplay profiling output."""

from __future__ import annotations

import csv
import html
import io
import json

from agentreplay.profiler.models import ProfilingReport


def render_summary(report: ProfilingReport) -> str:
    """Render a compact profiling summary."""
    return "\n".join(
        (
            report.summary(),
            f"Slowest Event: {report.duration.slowest_event_id or '-'} "
            f"({report.duration.slowest_ms:.3f} ms)",
            f"Slowest Tool: {report.tool_analysis.slowest_tool or '-'}",
            f"Slowest Model Call: {report.llm_duration.slowest_event_id or '-'}",
            f"Total Tokens: {report.token_analysis.total_tokens}",
            f"Total Cost: {report.cost_analysis.total_cost:.6f}",
            f"Recommendations: {len(report.recommendations)}",
        )
    )


def render_console(report: ProfilingReport) -> str:
    """Render a human-readable console profile report."""
    sections = [
        "# AgentReplay Profile",
        "",
        render_summary(report),
        "",
        "## Duration",
        _duration_lines(report),
        "",
        "## Tokens",
        _token_lines(report),
        "",
        "## Cost",
        _cost_lines(report),
        "",
        "## Models",
        _model_lines(report),
        "",
        "## Tools",
        _tool_lines(report),
        "",
        "## Memory",
        _memory_lines(report),
        "",
        "## Bottlenecks",
        _bottleneck_lines(report),
        "",
        "## Recommendations",
        _recommendation_lines(report),
    ]
    return "\n".join(sections)


def render_timeline(report: ProfilingReport) -> str:
    """Render execution timeline profile rows."""
    if not report.visualizations.execution_timeline:
        return "No timeline data."
    lines = ["Execution Timeline"]
    for item in report.visualizations.execution_timeline:
        indent = "  " * item.depth
        lines.append(
            f"{indent}{item.label} {item.event_id} "
            f"start={item.start_ms:.3f}ms duration={item.duration_ms:.3f}ms"
        )
    return "\n".join(lines)


def render_json(report: ProfilingReport) -> str:
    """Render profile report as JSON."""
    return json.dumps(report.to_dict(), sort_keys=True)


def render_markdown(report: ProfilingReport) -> str:
    """Render profile report as Markdown."""
    return render_console(report)


def render_html(report: ProfilingReport) -> str:
    """Render profile report as standalone HTML."""
    title = html.escape(f"AgentReplay Profile {report.run_id}")
    body = html.escape(render_console(report))
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><pre>{body}</pre></body></html>"
    )


def render_csv(report: ProfilingReport) -> str:
    """Render key profile metrics as CSV."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(("section", "metric", "value"))
    writer.writerow(("duration", "total_ms", f"{report.duration.total_ms:.6f}"))
    writer.writerow(("duration", "average_ms", f"{report.duration.average_ms:.6f}"))
    writer.writerow(("duration", "p95_ms", f"{report.duration.p95_ms:.6f}"))
    writer.writerow(("tokens", "total_tokens", report.token_analysis.total_tokens))
    writer.writerow(("cost", "total_cost", f"{report.cost_analysis.total_cost:.6f}"))
    writer.writerow(("memory", "reads", report.memory_analysis.reads))
    writer.writerow(("memory", "writes", report.memory_analysis.writes))
    for profile in report.model_analysis.profiles:
        writer.writerow(
            ("model", f"{profile.model_name}.count", profile.execution_count)
        )
        writer.writerow(
            (
                "model",
                f"{profile.model_name}.average_latency_ms",
                f"{profile.average_latency_ms:.6f}",
            )
        )
    for tool_profile in report.tool_analysis.profiles:
        writer.writerow(
            ("tool", f"{tool_profile.tool_name}.count", tool_profile.execution_count)
        )
        writer.writerow(
            (
                "tool",
                f"{tool_profile.tool_name}.average_duration_ms",
                f"{tool_profile.average_duration_ms:.6f}",
            )
        )
    return output.getvalue()


def _duration_lines(report: ProfilingReport) -> str:
    """Render duration lines."""
    duration = report.duration
    return "\n".join(
        (
            f"Total Execution Time: {duration.total_ms:.3f} ms",
            f"Average Event Duration: {duration.average_ms:.3f} ms",
            f"Median Duration: {duration.median_ms:.3f} ms",
            f"P50: {duration.p50_ms:.3f} ms",
            f"P90: {duration.p90_ms:.3f} ms",
            f"P95: {duration.p95_ms:.3f} ms",
            f"P99: {duration.p99_ms:.3f} ms",
            f"Fastest Event: {duration.fastest_event_id or '-'}",
            f"Slowest Event: {duration.slowest_event_id or '-'}",
            f"Memory Access Time: {report.memory_duration.total_ms:.3f} ms",
            f"Replay Time: {report.replay_duration.total_ms:.3f} ms",
            f"Diff Time: {report.diff_duration.total_ms:.3f} ms",
        )
    )


def _token_lines(report: ProfilingReport) -> str:
    """Render token lines."""
    tokens = report.token_analysis
    return "\n".join(
        (
            f"Prompt Tokens: {tokens.prompt_tokens}",
            f"Completion Tokens: {tokens.completion_tokens}",
            f"Total Tokens: {tokens.total_tokens}",
            f"Average Tokens: {tokens.average_tokens:.3f}",
            f"Maximum Tokens: {tokens.maximum_tokens}",
            f"Minimum Tokens: {tokens.minimum_tokens}",
            f"Tokens Per Tool: {tokens.tokens_per_tool}",
            f"Tokens Per Model: {tokens.tokens_per_model}",
        )
    )


def _cost_lines(report: ProfilingReport) -> str:
    """Render cost lines."""
    cost = report.cost_analysis
    return "\n".join(
        (
            f"Total Cost: {cost.total_cost:.6f}",
            f"Average Cost: {cost.average_cost:.6f}",
            f"Cost Per Tool: {cost.cost_per_tool}",
            f"Cost Per Model: {cost.cost_per_model}",
            f"Most Expensive Event: {cost.most_expensive_event_id or '-'}",
            f"Least Expensive Event: {cost.least_expensive_event_id or '-'}",
            f"Estimated Daily Cost: {cost.estimated_daily_cost:.6f}",
            f"Estimated Monthly Cost: {cost.estimated_monthly_cost:.6f}",
        )
    )


def _model_lines(report: ProfilingReport) -> str:
    """Render model lines."""
    if not report.model_analysis.profiles:
        return "No model events recorded."
    return "\n".join(
        f"{profile.model_name}: count={profile.execution_count}, "
        f"provider={profile.provider_name or '-'}, "
        f"avg_latency={profile.average_latency_ms:.3f} ms, "
        f"avg_cost={profile.average_cost:.6f}, "
        f"avg_tokens={profile.average_tokens:.3f}, "
        f"failure_rate={profile.failure_rate:.3f}, "
        f"retry_rate={profile.retry_rate:.3f}"
        for profile in report.model_analysis.profiles
    )


def _tool_lines(report: ProfilingReport) -> str:
    """Render tool lines."""
    if not report.tool_analysis.profiles:
        return "No tool events recorded."
    return "\n".join(
        f"{profile.tool_name}: count={profile.execution_count}, "
        f"avg_duration={profile.average_duration_ms:.3f} ms, "
        f"fastest={profile.fastest_ms:.3f} ms, "
        f"slowest={profile.slowest_ms:.3f} ms, "
        f"failure_rate={profile.failure_rate:.3f}, "
        f"retry_count={profile.retry_count}"
        for profile in report.tool_analysis.profiles
    )


def _memory_lines(report: ProfilingReport) -> str:
    """Render memory lines."""
    memory = report.memory_analysis
    return "\n".join(
        (
            f"Memory Reads: {memory.reads}",
            f"Memory Writes: {memory.writes}",
            f"Memory Latency: {memory.total_latency_ms:.3f} ms",
            f"Memory Size: {memory.total_size_bytes} bytes",
        )
    )


def _bottleneck_lines(report: ProfilingReport) -> str:
    """Render bottlenecks."""
    if not report.bottlenecks:
        return "No bottlenecks detected."
    return "\n".join(
        f"- [{bottleneck.severity}] {bottleneck.category}: "
        f"{bottleneck.description} ({bottleneck.metric}={bottleneck.value})"
        for bottleneck in report.bottlenecks
    )


def _recommendation_lines(report: ProfilingReport) -> str:
    """Render recommendations."""
    if not report.recommendations:
        return "No recommendations generated."
    return "\n".join(
        f"- [{recommendation.severity}] {recommendation.category}: "
        f"{recommendation.description} {recommendation.rationale}"
        for recommendation in report.recommendations
    )


__all__ = [
    "render_console",
    "render_csv",
    "render_html",
    "render_json",
    "render_markdown",
    "render_summary",
    "render_timeline",
]
