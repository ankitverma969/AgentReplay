from __future__ import annotations

import argparse
import json
import tempfile
import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.debugger import DebuggerSession
from agentreplay.diff import DiffEngine
from agentreplay.observability import ObservabilityEngine
from agentreplay.profiler import ProfilerEngine
from agentreplay.recording import Recorder
from agentreplay.regression import RegressionEngine
from agentreplay.replay import ReplayEngine
from agentreplay.security import SecurityEngine
from agentreplay.storage import SQLiteStorage
from agentreplay.types import JSONValue


@dataclass(frozen=True, slots=True)
class BenchmarkMeasurement:
    """Single benchmark measurement emitted by the benchmark suite."""

    name: str
    duration_ms: float
    peak_memory_bytes: int
    items: int

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-serializable benchmark payload."""
        return {
            "name": self.name,
            "duration_ms": self.duration_ms,
            "peak_memory_bytes": self.peak_memory_bytes,
            "items": self.items,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark AgentReplay modules.")
    parser.add_argument("--events", type=int, default=1_000)
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    if args.events <= 0:
        parser.error("--events must be greater than zero")

    baseline = _trace("baseline", args.events)
    target = _trace("target", args.events, slower=True)
    measurements = [
        _measure("recorder", lambda: _bench_recorder(args.events)),
        _measure("storage", lambda: _bench_storage(baseline)),
        _measure(
            "replay", lambda: len(ReplayEngine().load_trace(baseline).timeline.entries)
        ),
        _measure("diff", lambda: len(DiffEngine().compare(baseline, target).changes)),
        _measure("profiler", lambda: ProfilerEngine().profile(baseline).duration.count),
        _measure(
            "debugger",
            lambda: (
                DebuggerSession(ReplayEngine().load_trace(baseline))
                .statistics()
                .total_events
            ),
        ),
        _measure(
            "security",
            lambda: len(SecurityEngine().verify(baseline.to_dict()).findings),
        ),
        _measure(
            "opentelemetry",
            lambda: len(ObservabilityEngine().map_trace(baseline).spans),
        ),
        _measure(
            "regression",
            lambda: len(RegressionEngine().compare(baseline, target).findings),
        ),
    ]
    payload = {
        "events": args.events,
        "generated_at": datetime.now(UTC).isoformat(),
        "measurements": [measurement.to_dict() for measurement in measurements],
    }
    output = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_path:
        Path(args.json_path).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)
    return 0


def _measure(name: str, func: Callable[[], int]) -> BenchmarkMeasurement:
    tracemalloc.start()
    started = time.perf_counter()
    items = func()
    duration_ms = (time.perf_counter() - started) * 1_000.0
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return BenchmarkMeasurement(
        name=name,
        duration_ms=duration_ms,
        peak_memory_bytes=peak,
        items=items,
    )


def _bench_recorder(count: int) -> int:
    with Recorder(name="benchmark") as recorder:
        for index in range(count):
            recorder.custom_event("benchmark", payload={"index": index})
    return len(recorder.trace().events)


def _bench_storage(trace: TraceSnapshot) -> int:
    with tempfile.TemporaryDirectory(prefix="agentreplay-benchmark-") as directory:
        storage = SQLiteStorage(Path(directory) / "benchmark.sqlite")
        try:
            storage.save_run(trace.run)
            inserted = storage.bulk_insert_events(trace.events)
            return inserted + sum(
                1 for _event in storage.stream_events(trace.run.run_id)
            )
        finally:
            storage.close()


def _trace(run_id: str, count: int, *, slower: bool = False) -> TraceSnapshot:
    started = datetime(2026, 1, 1, tzinfo=UTC)
    run = RunRecord(
        run_id=run_id,
        name=f"benchmark-{run_id}",
        status="completed",
        started_at=started,
        ended_at=started + timedelta(milliseconds=count),
        duration_ms=float(count),
        metadata={"benchmark": True},
        tags=("benchmark",),
    )
    return TraceSnapshot(
        run=run,
        events=tuple(
            _event(run_id, sequence, slower=slower) for sequence in range(1, count + 1)
        ),
    )


def _event(run_id: str, sequence: int, *, slower: bool) -> EventRecord:
    duration = float(sequence % 25) + (10.0 if slower and sequence % 10 == 0 else 0.0)
    event_type = "llm.response" if sequence % 5 == 0 else "custom.event"
    return EventRecord(
        event_id=f"{run_id}-{sequence}",
        run_id=run_id,
        parent_event_id=None if sequence == 1 else f"{run_id}-{sequence - 1}",
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(milliseconds=sequence),
        duration_ms=duration,
        metadata={"bucket": sequence % 10},
        payload={
            "message": f"benchmark event {sequence}",
            "model_name": "benchmark-model" if event_type == "llm.response" else "",
            "total_tokens": sequence % 128,
            "cost": (sequence % 17) / 10_000,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
