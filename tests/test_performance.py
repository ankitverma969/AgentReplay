from __future__ import annotations

import gzip
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentreplay import (
    BenchmarkCase,
    BenchmarkSuite,
    SearchQuery,
    SQLiteOptimizer,
    StreamingTraceExporter,
    TraceSearchEngine,
    TraceWindowReader,
)
from agentreplay.cli.main import build_parser, main
from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.performance import (
    LRUCache,
    ObjectPool,
    compress_bytes,
    decompress_bytes,
    partial_replay,
)
from agentreplay.performance.compression import iter_decompressed_lines
from agentreplay.performance.models import ExportProgress
from agentreplay.storage import SQLiteStorage


def test_window_reader_loads_first_next_previous_and_jumps(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=12)
    reader = TraceWindowReader(storage, default_limit=5)

    first = reader.first("run-1")
    second = reader.next(first)
    previous = reader.previous(second)
    by_event = reader.jump_to_event("run-1", "event-9")
    by_timestamp = reader.jump_to_timestamp(
        "run-1",
        datetime(2026, 1, 1, 12, 0, 8, tzinfo=UTC),
    )

    assert [event.sequence for event in first.events] == [1, 2, 3, 4, 5]
    assert [event.sequence for event in second.events] == [6, 7, 8, 9, 10]
    assert previous.events == first.events
    assert any(event.event_id == "event-9" for event in by_event.events)
    assert by_timestamp.events[0].sequence == 8
    assert [
        event.sequence for event in partial_replay(storage, "run-1", offset=10, limit=2)
    ] == [11, 12]
    storage.close()


def test_trace_search_supports_streaming_modes_and_index(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=8)
    engine = TraceSearchEngine(storage, batch_size=2)

    assert engine.index_run("run-1") == 8

    text = engine.search(SearchQuery(run_id="run-1", text="prompt 3"))
    regex = engine.search(SearchQuery(run_id="run-1", text=r"tool_\d", mode="regex"))
    metadata = engine.search(
        SearchQuery(
            run_id="run-1",
            mode="metadata",
            metadata_key="bucket",
            metadata_value="1",
        )
    )
    tool = engine.search(SearchQuery(run_id="run-1", text="tool_4", mode="tool"))
    model = engine.search(SearchQuery(run_id="run-1", text="gpt-test", mode="model"))

    assert text.matches
    assert text.used_index
    assert regex.matches
    assert not regex.used_index
    assert metadata.matches
    assert tool.matches[0].event.event_id == "event-4"
    assert model.matches
    storage.close()


def test_lru_cache_and_object_pool_are_bounded() -> None:
    cache: LRUCache[str, int] = LRUCache(max_size=2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)

    pool: ObjectPool[list[int]] = ObjectPool(list, max_size=1)
    item = pool.acquire()
    item.append(1)
    pool.release(item)
    pool.release([2])

    assert cache.get("b") is None
    assert len(cache) == 2
    assert len(pool) == 1


def test_compression_helpers_and_streaming_export(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=4)
    exporter = StreamingTraceExporter(storage, batch_size=2)
    output = tmp_path / "trace.jsonl.gz"
    progress: list[ExportProgress] = []

    exported = exporter.export_jsonl(
        "run-1",
        output,
        compression="gzip",
        progress=progress.append,
    )
    raw = b"agentreplay compression"
    compressed = compress_bytes(raw, compression_format="gzip")

    assert exported.events_written == 4
    assert progress[-1].events_written == 4
    with gzip.open(output, "rt", encoding="utf-8") as handle:
        assert handle.readline().startswith("{")
    assert next(iter_decompressed_lines(output, compression_format="gzip")).startswith(
        "{"
    )
    assert decompress_bytes(compressed, compression_format="gzip") == raw
    storage.close()


def test_streaming_export_json_supports_partial_windows(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=6)
    output = tmp_path / "trace.json"

    exported = StreamingTraceExporter(storage).export_json(
        "run-1",
        output,
        offset=2,
        limit=3,
    )
    data = json.loads(output.read_text(encoding="utf-8"))

    assert exported.events_written == 3
    assert [event["sequence"] for event in data["events"]] == [3, 4, 5]
    storage.close()


def test_sqlite_optimizer_reports_indexes_and_vacuum(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=3)
    optimizer = SQLiteOptimizer(storage)

    optimized = optimizer.optimize()
    vacuumed = optimizer.vacuum()

    assert optimized.event_count == 3
    assert "idx_events_run_type_sequence" in optimized.indexes
    assert vacuumed.vacuumed
    storage.close()


def test_benchmark_suite_runs_small_case(tmp_path: Path) -> None:
    result = BenchmarkSuite(db_path=tmp_path / "benchmark.sqlite").run(
        BenchmarkCase(event_count=20, chunk_size=5)
    )

    names = {measurement.name for measurement in result.measurements}
    assert "storage.batch_insert" in names
    assert "search.text" in names
    result_data = result.to_dict()
    case_data = result_data["case"]
    assert isinstance(case_data, dict)
    assert case_data["event_count"] == 20


def test_performance_cli_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    storage = _storage(tmp_path, event_count=2)
    db_path = storage.db_path
    storage.close()

    assert "benchmark" in build_parser().format_help()
    assert main(["analyze-db", "--db-path", str(db_path)]) == 0
    assert main(["optimize", "--db-path", str(db_path), "--json"]) == 0
    assert main(["vacuum", "--db-path", str(db_path)]) == 0
    assert (
        main(
            [
                "benchmark",
                "--events",
                "5",
                "--chunk-size",
                "2",
                "--db-path",
                str(tmp_path / "cli-bench.sqlite"),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert "AgentReplay SQLite Performance Report" in captured.out
    assert "AgentReplay benchmark" in captured.out


def test_benchmark_cli_rejects_invalid_size(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["benchmark", "--events", "0"]) == 1

    captured = capsys.readouterr()
    assert "agentreplay benchmark:" in captured.out


def _storage(tmp_path: Path, *, event_count: int) -> SQLiteStorage:
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    run = RunRecord(
        run_id="run-1",
        name="performance",
        status="completed",
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        ended_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
        duration_ms=60_000.0,
        metadata={"suite": "performance"},
        tags=("performance",),
    )
    storage.save_run(run)
    storage.bulk_insert_events(
        tuple(_event(sequence) for sequence in range(1, event_count + 1))
    )
    return storage


def _event(sequence: int) -> EventRecord:
    event_type = "llm.request" if sequence % 3 == 0 else "tool.finished"
    return EventRecord(
        event_id=f"event-{sequence}",
        run_id="run-1",
        parent_event_id=None if sequence == 1 else f"event-{sequence - 1}",
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC) + timedelta(seconds=sequence),
        duration_ms=float(sequence),
        metadata={"bucket": sequence % 2, "model_name": "gpt-test"},
        payload={
            "prompt": f"prompt {sequence}",
            "tool_name": f"tool_{sequence}",
            "model_name": "gpt-test",
            "provider_name": "openai",
            "message": f"trace message {sequence}",
        },
    )
