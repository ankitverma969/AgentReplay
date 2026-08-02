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

The current implementation includes the in-memory recorder engine and local
SQLite storage. Replay, diff, and adapter implementations remain future work.
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
