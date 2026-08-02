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

Phase 1 intentionally avoids recorder, replay, diff, adapter, and storage
implementations. Future phases should extend existing package boundaries instead
of moving responsibilities across layers.
