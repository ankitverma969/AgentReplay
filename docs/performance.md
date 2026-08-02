# AgentReplay Performance Guide

AgentReplay includes `agentreplay.performance` for massive trace workloads where a
single run can contain hundreds of thousands or millions of events.

The package is intentionally additive. Existing recorder, storage, replay, diff,
reporting, security, profiler, and adapter APIs keep their current behavior.
Performance APIs provide memory-safe alternatives when callers need partial access.

## Core Capabilities

- Windowed trace reads with `TraceWindowReader`
- First, next, previous, jump-to-event, and jump-to-timestamp loading
- Partial replay helpers that return only visible events
- Streaming JSON and JSONL exports directly to disk
- gzip compression built in, with zstd and LZ4 supported when their optional
  Python packages are installed
- LRU cache and object pool utilities for reusable windows and buffers
- SQLite optimization with additional indexes, `PRAGMA optimize`, `ANALYZE`, and
  optional `VACUUM`
- Full-text search indexing on SQLite FTS5 when available
- Streaming regex and metadata search fallback
- Deterministic benchmark suite for large trace workloads
- Thread and process pool helper for parallel workloads

## Windowed Reading

Use `TraceWindowReader` when a UI, replay view, or report only needs the visible
slice of a run.

```python
from agentreplay import SQLiteStorage, TraceWindowReader

storage = SQLiteStorage()
reader = TraceWindowReader(storage, default_limit=100)

window = reader.first("run-id")
next_window = reader.next(window)
focused = reader.jump_to_event("run-id", "event-id")
```

## Search

Use `TraceSearchEngine` for prompt, tool, model, provider, error, metadata, text,
and regex search. `index_run()` builds a SQLite FTS index when available. Regex and
metadata queries always stream safely.

```python
from agentreplay import SearchQuery, SQLiteStorage, TraceSearchEngine

storage = SQLiteStorage()
search = TraceSearchEngine(storage)
search.index_run("run-id")

results = search.search(SearchQuery(run_id="run-id", text="failed", mode="error"))
```

## Streaming Exports

Large exports should write directly to disk. `StreamingTraceExporter` supports
full or partial exports and progress callbacks.

```python
from agentreplay import SQLiteStorage, StreamingTraceExporter

storage = SQLiteStorage()
exporter = StreamingTraceExporter(storage)
exporter.export_jsonl("run-id", "trace.jsonl.gz", compression="gzip")
```

## SQLite Optimization

The optimizer adds performance indexes, runs SQLite optimizer hints, performs
analysis, and can vacuum when explicitly requested.

```python
from agentreplay import SQLiteOptimizer, SQLiteStorage

storage = SQLiteStorage()
report = SQLiteOptimizer(storage).optimize()
```

## CLI

```bash
agentreplay benchmark --events 10000
agentreplay optimize
agentreplay analyze-db --json
agentreplay vacuum
```

## Scaling Notes

- Prefer `stream_events()` and `TraceWindowReader` over `load_events()` for large
  traces.
- Use `StreamingTraceExporter` for exports over a few thousand events.
- Build search indexes after recording completes.
- Use `VACUUM` during maintenance windows only.
- Keep report visualization limits bounded and rely on lazy client rendering for
  large traces.
- Use diff implementations that align events in linear or near-linear passes.

## Compression

gzip is available without extra dependencies. zstd and LZ4 are loaded lazily, so
the core package remains minimal. Install optional packages in deployments that
need those formats.

## Benchmarks

The benchmark suite is deterministic and can be run with smaller event counts in
CI. For release validation, run 10k, 100k, 500k, and 1M event workloads on
representative machines and capture memory, CPU, search, replay, diff, export,
and report timings.
