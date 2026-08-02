"""Renderers for AgentReplay performance and scalability reports."""

from __future__ import annotations

import json

from agentreplay.performance.models import (
    BenchmarkResult,
    PerformanceReport,
    SQLiteOptimizationReport,
)


def render_sqlite_report(report: SQLiteOptimizationReport) -> str:
    """Render a human-readable SQLite performance report."""
    lines = [
        "AgentReplay SQLite Performance Report",
        f"Database: {report.db_path}",
        f"Runs: {report.run_count}",
        f"Events: {report.event_count}",
        f"Estimated size: {report.estimated_size_bytes} bytes",
        f"Free pages: {report.freelist_count}",
        f"Indexes: {len(report.indexes)}",
        f"Analyzed: {report.analyzed}",
        f"Vacuumed: {report.vacuumed}",
    ]
    return "\n".join(lines)


def render_performance_json(report: PerformanceReport) -> str:
    """Render a performance report as JSON."""
    return json.dumps(report.to_dict(), sort_keys=True)


def render_benchmark_json(result: BenchmarkResult) -> str:
    """Render a benchmark result as JSON."""
    return json.dumps(result.to_dict(), sort_keys=True)


def render_benchmark_summary(result: BenchmarkResult) -> str:
    """Render a concise benchmark summary."""
    lines = [
        f"AgentReplay benchmark: {result.case.event_count} events",
        f"Chunk size: {result.case.chunk_size}",
    ]
    lines.extend(
        (
            f"{item.name}: {item.duration_ms:.2f} ms, "
            f"peak {item.peak_memory_bytes} bytes, "
            f"{item.items_processed} items"
        )
        for item in result.measurements
    )
    return "\n".join(lines)


__all__ = [
    "render_benchmark_json",
    "render_benchmark_summary",
    "render_performance_json",
    "render_sqlite_report",
]
