# AgentReplay

AgentReplay is a framework-agnostic debugging and replay library for AI agent
executions.

The project goal is to let developers install one package:

```bash
pip install agentreplay
```

and integrate it into agent frameworks with minimal code. AgentReplay observes
and records execution events so runs can later be inspected, replayed, compared,
and exported.

## Phase 1 Status

This repository currently contains the project foundation only:

- Python package scaffold
- CLI entrypoint
- typed settings management
- configuration file loading
- environment variable loading
- logging setup
- exception hierarchy
- dependency injection primitives
- documented package boundaries

Recorder, replay, diff, storage, and framework adapter behavior will be added in
later phases.

## Requirements

- Python 3.11 or newer
- No API key required
- No network service required

## Development

Create a virtual environment, then install the project with development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Run the quality checks:

```bash
make check
```

Use the CLI:

```bash
agentreplay --help
agentreplay version
```

## Configuration

AgentReplay reads configuration from these sources, in priority order:

1. explicit Python API overrides
2. environment variables
3. project configuration files
4. defaults

Supported configuration files:

- `agentreplay.toml`
- `.agentreplay.toml`

Supported environment variables:

- `AGENTREPLAY_ENABLED`
- `AGENTREPLAY_DB_PATH`
- `AGENTREPLAY_REDACTION`
- `AGENTREPLAY_LOG_LEVEL`
- `AGENTREPLAY_STORAGE_BACKEND`
- `AGENTREPLAY_FAIL_MODE`
- `AGENTREPLAY_CONFIG`

Example:

```toml
enabled = true
db_path = ".agentreplay/agentreplay.sqlite"
redaction_enabled = true
log_level = "INFO"
storage_backend = "sqlite"
fail_mode = "fail_open"
```

## License

AgentReplay is released under the MIT License.
