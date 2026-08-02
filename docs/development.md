# Developer Guide

## Setup

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install
```

## Common Commands

```bash
make format
make lint
make typecheck
make test
make check
```

## CLI Smoke Test

```bash
agentreplay --help
agentreplay version
agentreplay list
```

## Configuration

AgentReplay supports `agentreplay.toml`, `.agentreplay.toml`, and
`AGENTREPLAY_*` environment variables. Environment variables override file
configuration, and explicit Python API values override both.

## Maintainer Notes

The current implementation includes the in-memory recorder engine, local SQLite
storage, read-only replay engine, read-only diff engine, and the OpenAI Agents
SDK adapter. Additional adapter implementations remain future work.
Future phases should extend existing package boundaries instead of moving
responsibilities across layers.

## Recorder Engine

The in-memory recorder is now available through `agentreplay.Recorder` and
`agentreplay.record`.

The recorder supports:

- sync and async context managers
- sync and async decorators
- manual `start_run()` and `end_run()`
- nested timed spans
- automatic timestamps, UUIDs, metadata, duration, and exception events
- thread-safe in-memory run and event managers

The recorder keeps active data in memory. Persistence is handled by storage
backends that consume immutable `RunRecord`, `EventRecord`, and `TraceSnapshot`
objects without changing agent execution behavior.

## Storage Engine

The default persistence backend is `SQLiteStorage`.

The storage layer includes:

- backend-neutral `StorageBackend` protocol
- `RunQuery`, `EventQuery`, and `Pagination` query models
- SQLite connection and transaction managers
- run, event, and metadata repositories
- schema migrations and version tracking
- normalized run, event, metadata, run tag, and attachment tables

Storage should remain a persistence concern only. Replay and diff behavior
belong to their dedicated packages.

## Replay Engine

Replay is read-only. It must never call an LLM, execute tools, or mutate stored
runs.

The replay layer includes:

- `ReplayEngine` for loading runs from storage, JSON strings, and JSON files
- `ReplaySession` for a loaded trace and timeline
- `ReplayController` for play, pause, resume, stop, seek, timestamp jumps, and
  step navigation
- `ReplayIterator` for timeline iteration
- `EventTimeline` for nested and concurrent event visualization

Playback speed is limited to `0.25x`, `0.5x`, `1x`, `2x`, and `4x`.

## Diff Engine

Diff is read-only. It must never execute agents, call an LLM, execute tools, or
mutate stored runs.

The diff layer includes:

- `DiffEngine` for comparing two `TraceSnapshot` objects or storage-backed run
  ids
- `EventMatcher` for aligning thousands of recorded events efficiently
- immutable `DiffResult`, `DiffChange`, and `DiffStats` models
- report renderers for console, JSON, Markdown, HTML, and summary output

Diff reports include added, removed, and modified changes with old value, new
value, location, category, severity, and related event ids when available.
