"""Benchmark suite for AgentReplay massive trace workloads."""

from __future__ import annotations

import json
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.performance.export import StreamingTraceExporter
from agentreplay.performance.models import (
    BenchmarkCase,
    BenchmarkMeasurement,
    BenchmarkResult,
    SearchQuery,
)
from agentreplay.performance.search import TraceSearchEngine
from agentreplay.performance.windows import TraceWindowReader
from agentreplay.storage import SQLiteStorage

MeasuredCall = Callable[[], int]


class BenchmarkSuite:
    """Run deterministic scalability benchmarks against synthetic traces."""

    def __init__(self, *, db_path: str | Path | None = None) -> None:
        """Create a benchmark suite."""
        self._db_path = db_path

    def run(self, case: BenchmarkCase) -> BenchmarkResult:
        """Run a benchmark case and return measurements."""
        if self._db_path is None:
            with tempfile.TemporaryDirectory(prefix="agentreplay-bench-") as directory:
                return self._run_with_storage(
                    Path(directory) / "benchmark.sqlite", case
                )
        return self._run_with_storage(Path(self._db_path), case)

    def _run_with_storage(self, db_path: Path, case: BenchmarkCase) -> BenchmarkResult:
        """Run a case against one SQLite database path."""
        storage = SQLiteStorage(db_path)
        try:
            run = synthetic_run("benchmark-run")
            storage.save_run(run)
            measurements: list[BenchmarkMeasurement] = [
                _measure(
                    "storage.batch_insert",
                    lambda: _insert_synthetic_events(storage, run.run_id, case),
                )
            ]
            reader = TraceWindowReader(storage, default_limit=case.chunk_size)
            measurements.append(
                _measure(
                    "trace.load_first_chunk",
                    lambda: len(reader.first(run.run_id).events),
                )
            )
            if case.include_search:
                search = TraceSearchEngine(storage)
                measurements.append(
                    _measure("search.index", lambda: search.index_run(run.run_id))
                )
                measurements.append(
                    _measure(
                        "search.text",
                        lambda: len(
                            search.search(
                                SearchQuery(run_id=run.run_id, text="benchmark")
                            ).matches
                        ),
                    )
                )
            if case.include_export:
                output = db_path.with_suffix(".jsonl")
                exporter = StreamingTraceExporter(storage, batch_size=case.chunk_size)
                measurements.append(
                    _measure(
                        "export.jsonl",
                        lambda: (
                            exporter.export_jsonl(run.run_id, output).events_written
                        ),
                    )
                )
            if case.include_replay:
                measurements.append(
                    _measure(
                        "replay.windowed",
                        lambda: len(
                            reader.window(run.run_id, limit=case.chunk_size).events
                        ),
                    )
                )
            if case.include_diff:
                measurements.append(
                    _measure(
                        "diff.linear_scan_baseline",
                        lambda: _linear_scan(storage, run.run_id),
                    )
                )
            if case.include_report:
                measurements.append(
                    _measure(
                        "report.chunk_metadata",
                        lambda: len(reader.stream_chunks(run.run_id)),
                    )
                )
            return BenchmarkResult(case=case, measurements=tuple(measurements))
        finally:
            storage.close()


def synthetic_run(run_id: str) -> RunRecord:
    """Build a synthetic run for benchmark workloads."""
    started = datetime(2026, 1, 1, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name="AgentReplay massive trace benchmark",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        duration_ms=1_000.0,
        metadata={"benchmark": True},
        tags=("benchmark", "performance"),
    )


def synthetic_events(
    run_id: str,
    count: int,
    *,
    start_sequence: int = 1,
) -> tuple[EventRecord, ...]:
    """Build synthetic benchmark events."""
    started = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        EventRecord(
            event_id=f"{run_id}-event-{sequence}",
            run_id=run_id,
            parent_event_id=None if sequence == 1 else f"{run_id}-event-{sequence - 1}",
            sequence=sequence,
            event_type="custom.event" if sequence % 5 else "llm.response",
            timestamp=started + timedelta(milliseconds=sequence),
            duration_ms=float(sequence % 37),
            metadata={
                "benchmark": True,
                "bucket": sequence % 10,
                "model_name": "benchmark-model" if sequence % 5 == 0 else "none",
            },
            payload={
                "message": f"benchmark event {sequence}",
                "tool_name": "benchmark_tool" if sequence % 7 == 0 else "",
                "tokens": sequence % 128,
            },
        )
        for sequence in range(start_sequence, start_sequence + count)
    )


def _insert_synthetic_events(
    storage: SQLiteStorage,
    run_id: str,
    case: BenchmarkCase,
) -> int:
    """Insert synthetic events in chunks."""
    inserted = 0
    while inserted < case.event_count:
        count = min(case.chunk_size, case.event_count - inserted)
        events = synthetic_events(run_id, count, start_sequence=inserted + 1)
        inserted += storage.bulk_insert_events(events)
    return inserted


def _linear_scan(storage: SQLiteStorage, run_id: str) -> int:
    """Run a memory-safe linear scan used as a diff/replay baseline."""
    count = 0
    for _event in storage.stream_events(run_id, batch_size=5_000):
        count += 1
    return count


def _measure(name: str, call: MeasuredCall) -> BenchmarkMeasurement:
    """Measure runtime and peak memory for one operation."""
    tracemalloc.start()
    start = time.perf_counter()
    items = call()
    duration_ms = (time.perf_counter() - start) * 1_000.0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return BenchmarkMeasurement(
        name=name,
        duration_ms=duration_ms,
        peak_memory_bytes=peak,
        items_processed=items,
    )


def benchmark_result_json(result: BenchmarkResult) -> str:
    """Return benchmark JSON."""
    return json.dumps(result.to_dict(), sort_keys=True)


__all__ = [
    "BenchmarkSuite",
    "benchmark_result_json",
    "synthetic_events",
    "synthetic_run",
]
