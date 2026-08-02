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

The current implementation includes the in-memory recorder engine. Replay, diff,
adapter, and storage implementations remain future work. Future phases should
extend existing package boundaries instead of moving responsibilities across
layers.

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

The recorder does not persist data. Future storage work should consume immutable
`RunRecord`, `EventRecord`, and `TraceSnapshot` objects without changing agent
execution behavior.
