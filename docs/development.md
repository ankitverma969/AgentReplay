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
make test-performance
make coverage
make security
make dead-code
make docs
make benchmark
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

The current implementation includes the recorder, SQLite storage, replay, diff,
debugger, profiler, reporting, performance, regression, security,
observability, plugin, public SDK, OpenAI Agents SDK adapter, and LangGraph
adapter modules. Future work should extend existing package boundaries instead
of moving responsibilities across layers.

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

## LangGraph Adapter

The LangGraph adapter lives behind `agentreplay.langgraph` and
`agentreplay.adapters.langgraph`.

The adapter should remain optional and must not make LangGraph a required core
dependency. Tests should prefer fake Runnable-compatible graphs unless a test is
explicitly marked as an optional import smoke test.

The adapter records by appending an AgentReplay callback to LangGraph Runnable
config. It must not modify LangGraph source code, call LLMs, execute tools
directly, or change graph state outside normal graph execution.

## Plugin SDK

The Plugin SDK lives in `agentreplay.plugins`.

Plugin support should remain framework-agnostic and optional. Core code should
not import third-party framework packages to discover plugins. External packages
must register through entry points in `agentreplay.plugins`.

Plugin manager behavior should fail open by default. A plugin crash must not
break recording, replay, diff, storage, or CLI fundamentals unless a caller
explicitly opts into fail-closed behavior.
