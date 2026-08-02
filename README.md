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
- in-memory recorder engine

Replay, diff, storage, and framework adapter behavior will be added in later
phases.

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

## In-Memory Recording

Use `Recorder` as a context manager:

```python
from agentreplay import Recorder

with Recorder(name="agent") as recorder:
    recorder.system_prompt("Answer briefly.")
    recorder.user_prompt("What is AgentReplay?")
    recorder.llm_request(provider_name="example", model_name="demo-model")
    recorder.llm_response(response="A local recorder.", latency_ms=12.0)
    recorder.assistant_response("A local recorder.")

trace = recorder.trace()
```

Use manual run control:

```python
from agentreplay import Recorder

recorder = Recorder(auto_start=False)
run_id = recorder.start_run(name="manual")
recorder.custom_event("checkpoint", payload={"step": 1})
recorder.end_run(run_id)
```

Use the decorator form:

```python
from agentreplay import record

@record
def my_agent() -> str:
    return "done"
```

The recorder is local and in-memory in this phase. It does not require an LLM,
API key, cloud service, or storage backend.

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
