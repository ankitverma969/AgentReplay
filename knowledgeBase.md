# AgentReplay Knowledge Base

AgentReplay is a framework-agnostic Python library for recording, inspecting,
replaying, comparing, and exporting AI agent executions. It is designed to run
locally, require no API key, and observe agent behavior without calling LLMs,
executing tools, or changing the target agent's behavior.

This document summarizes what is currently implemented, how the pieces fit
together, and how developers can use the project today.

## Project Status

Implemented components:

- Project foundation and packaging
- Typed configuration system
- Logging setup
- Exception hierarchy
- Dependency injection container
- CLI entrypoint
- In-memory recorder engine
- SQLite storage engine
- Read-only replay engine
- Read-only diff engine
- OpenAI Agents SDK adapter
- LangGraph adapter
- Plugin SDK
- Examples and developer documentation
- CI workflow for linting, typing, and tests

The library targets Python 3.11 and newer.

## Core Principles

- AgentReplay observes and records only.
- AgentReplay does not require an API key.
- AgentReplay does not call LLMs.
- AgentReplay does not execute tools during replay or diff.
- Recorder, storage, replay, diff, adapters, and plugins are separated by
  package boundaries.
- Optional framework integrations remain optional dependencies.
- SQLite is the default local persistence backend.
- The storage abstraction is designed for future backends.

## Package Overview

Important packages:

- `agentreplay.recording`: recorder engine, context handling, event and run
  management, serialization, redaction helpers, and recording hooks.
- `agentreplay.storage`: storage interface, SQLite implementation, repositories,
  schema migration support, connection handling, and transactions.
- `agentreplay.replay`: replay engine, replay sessions, timeline model,
  iterator, controller, and playback state.
- `agentreplay.diff`: run comparison engine, event matching, diff models, and
  console/JSON/Markdown/HTML renderers.
- `agentreplay.adapters`: framework adapter implementations and adapter
  registry placeholders.
- `agentreplay.plugins`: plugin base class, discovery, validation, lifecycle
  management, registry, dependency resolution, and plugin app surface.
- `agentreplay.cli`: command-line interface and command handlers.
- `agentreplay.core`: shared event, run, trace, clock, ID, and metadata models.
- `agentreplay.testing`: helper utilities for tests and examples.

## Main Features

### Recording

The recorder captures agent execution data in memory:

- run started
- run finished
- user prompt
- system prompt
- assistant response
- LLM request
- LLM response
- tool started
- tool finished
- tool failed
- function call
- memory read
- memory write
- custom event
- warning
- exception
- retry
- token usage
- cost
- latency
- model name
- provider name
- metadata
- timestamps
- durations
- nested parent-child event relationships

Supported API styles:

- context manager
- decorator
- manual start/end API
- synchronous functions
- asynchronous functions
- automatic exception recording
- automatic timing

### Storage

The default storage backend is SQLite.

Storage supports:

- create run
- update run
- delete run
- get run
- list runs
- search runs
- save event
- load events
- delete events
- bulk insert
- pagination
- filtering
- sorting
- schema versioning
- migrations

The storage layer is abstracted behind `StorageBackend` so future backends such
as PostgreSQL, DuckDB, MongoDB, S3, or other systems can implement the same
contract.

### Replay

Replay reconstructs recorded executions from stored or exported data.

Replay supports:

- load run by ID
- load from JSON
- load from file
- sequential replay
- nested event timeline rendering
- pause
- resume
- stop
- seek by event ID
- jump to timestamp
- step forward
- step backward
- playback speeds of `0.25x`, `0.5x`, `1x`, `2x`, and `4x`

Replay is read-only. It does not call an LLM, execute tools, or mutate stored
runs.

### Diff

The diff engine compares two recorded executions without running the agent.

Diff compares:

- run metadata
- execution time
- latency
- model
- provider
- prompts
- system prompts
- assistant responses
- tool calls
- tool outputs
- memory events
- function calls
- retries
- errors
- warnings
- token usage
- cost
- execution graph metadata
- timeline
- custom metadata

Diff outputs:

- added events
- removed events
- modified events
- unchanged events
- old values
- new values
- change locations
- severity levels
- console reports
- JSON reports
- Markdown reports
- HTML reports
- summary reports

### OpenAI Agents SDK Adapter

The OpenAI Agents SDK adapter is optional and is installed with:

```bash
pip install "agentreplay[openai-agents]"
```

Supported usage styles:

- `agentreplay.instrument()`
- `@record_agent`
- `with AgentReplay():`
- `AgentReplay().attach(agent)`

The adapter records SDK tracing and agent lifecycle information when available:

- agent start and end
- user messages
- assistant messages
- tool calls
- tool outputs
- handoffs
- guardrails
- model requests
- model responses
- exceptions
- retries
- token usage
- latency
- metadata

See `docs/openai_agents.md` and `examples/openai_agents`.

### LangGraph Adapter

The LangGraph adapter is optional and is installed with:

```bash
pip install "agentreplay[langgraph]"
```

Basic usage:

```python
from agentreplay.langgraph import instrument

graph = instrument(graph)
result = graph.invoke({"question": "What happened?"})
```

The adapter records graph execution information when available:

- graph start and end
- node execution
- node inputs
- node outputs
- conditional branches
- parallel branches
- state updates
- checkpoints
- tool nodes
- LLM nodes
- errors
- retries
- interrupts
- resume events
- streaming events
- metadata
- timing
- execution DAG metadata

See `docs/langgraph.md` and `examples/langgraph`.

### Plugin SDK

AgentReplay includes a plugin architecture so external packages can extend the
library without modifying core code.

Supported plugin types:

- agent frameworks
- LLM providers
- storage backends
- exporters
- CLI commands
- event processors
- metadata collectors
- future authentication providers

Plugins are discovered through the `agentreplay.plugins` Python entry-point
group. A package such as `agentreplay-crewai` can become available after normal
installation if it exposes a compatible entry point.

Plugin lifecycle hooks:

- before run
- after run
- before event
- after event
- before replay
- after replay
- before export
- after export
- plugin loaded
- plugin unloaded

See `docs/plugins.md`.

## Installation

Install the base package:

```bash
pip install agentreplay
```

Install for local development:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install optional integrations:

```bash
pip install "agentreplay[openai-agents]"
pip install "agentreplay[langgraph]"
pip install "agentreplay[all]"
```

## Common Usage

### Record With Context Manager

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

### Record With Manual Control

```python
from agentreplay import Recorder

recorder = Recorder(auto_start=False)
run_id = recorder.start_run(name="manual")
recorder.custom_event("checkpoint", payload={"step": 1})
recorder.end_run(run_id)
```

### Record With Decorator

```python
from agentreplay import record

@record
def my_agent() -> str:
    return "done"
```

### Persist To SQLite

```python
from agentreplay import Recorder, SQLiteStorage

with Recorder(name="agent") as recorder:
    recorder.user_prompt("Hello")
    recorder.assistant_response("Hi")

with SQLiteStorage(".agentreplay/agentreplay.sqlite") as storage:
    recorder.save_to_storage(storage)
```

### Replay A Run

```python
from agentreplay import ReplayEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
engine = ReplayEngine(storage=storage)
session = engine.load("run-id")

print(session.timeline.render())
engine.play()
```

### Compare Two Runs

```python
from agentreplay import DiffEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
diff = DiffEngine(storage=storage)
result = diff.compare("baseline-run-id", "candidate-run-id")

print(result.summary())
```

## CLI Usage

Show help:

```bash
agentreplay --help
```

Show version:

```bash
agentreplay version
```

List stored runs:

```bash
agentreplay list --db-path .agentreplay/agentreplay.sqlite
```

Replay a run:

```bash
agentreplay replay RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay replay RUN_ID --speed 2 --step
agentreplay replay --file exported-run.json --timeline
```

Diff two runs:

```bash
agentreplay diff RUN1 RUN2 --db-path .agentreplay/agentreplay.sqlite
agentreplay diff RUN1 RUN2 --summary
agentreplay diff RUN1 RUN2 --json
agentreplay diff RUN1 RUN2 --markdown
agentreplay diff RUN1 RUN2 --html
```

Export a run:

```bash
agentreplay export RUN_ID --json
agentreplay export RUN_ID --markdown
agentreplay export RUN_ID --html --output run.html
```

Inspect runs:

```bash
agentreplay inspect latest
agentreplay inspect RUN_ID
```

Manage plugins:

```bash
agentreplay plugins
agentreplay plugins list
agentreplay plugins info PLUGIN_NAME
agentreplay plugins install PACKAGE_NAME
agentreplay plugins disable PLUGIN_NAME
```

## Configuration

AgentReplay supports configuration from:

- explicit Python settings
- TOML configuration files
- environment variables

Configuration covers:

- storage path
- logging level
- plugin discovery
- disabled plugins
- plugin-specific configuration
- adapter settings
- prompt recording controls
- redaction controls
- sampling
- ignored tools
- ignored events
- custom metadata
- run naming

Typical environment variable style:

```bash
AGENTREPLAY_LOG_LEVEL=INFO
AGENTREPLAY_STORAGE_PATH=.agentreplay/agentreplay.sqlite
AGENTREPLAY_PLUGIN_AUTO_DISCOVER=true
```

Adapter-specific environment variables are available for OpenAI Agents SDK and
LangGraph configuration.

## Development Workflow

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run all checks:

```bash
make check
```

Run individual checks:

```bash
python -m ruff check agentreplay tests
python -m ruff format --check agentreplay tests
python -m mypy
python -m pytest
```

Build package artifacts:

```bash
python -m build
python -m twine check dist/*
```

## Testing

The test suite currently covers:

- CLI behavior
- configuration loading
- dependency injection container
- recorder behavior
- SQLite storage behavior
- replay behavior
- diff behavior
- OpenAI adapter behavior with mocks
- LangGraph adapter behavior with mocks
- plugin SDK behavior

The CI workflow runs on:

- Ubuntu
- macOS
- Windows
- Python 3.11
- Python 3.12
- Python 3.13

## Documentation Map

Primary documentation files:

- `README.md`: project overview and quick starts
- `docs/architecture.md`: architecture and package boundaries
- `docs/development.md`: development workflow
- `docs/openai_agents.md`: OpenAI Agents SDK adapter guide
- `docs/langgraph.md`: LangGraph adapter guide
- `docs/plugins.md`: Plugin SDK guide
- `CONTRIBUTING.md`: contribution process
- `CHANGELOG.md`: release history

Example directories:

- `examples/manual_recording.py`
- `examples/sqlite_storage.py`
- `examples/replay_recording.py`
- `examples/diff_recordings.py`
- `examples/openai_agents`
- `examples/langgraph`

## Current Limitations

The following are important to know before production release:

- Recorder events are stored in memory before persistence.
- Replay and diff currently load full runs into memory.
- Only SQLite storage is implemented.
- OpenAI Agents SDK and LangGraph are the only first-class adapters.
- Other framework adapter modules are placeholders for future integration work.
- Optional SDK integration tests depend on optional third-party packages.
- The project has not yet reached a stable `1.0` API contract.

## Release Readiness Checklist

Before a public production release, verify:

- public API stability
- adapter lifecycle cleanup
- concurrency behavior for streaming and parallel execution
- redaction coverage for secrets
- large-run storage performance
- replay and diff memory behavior
- plugin safety boundaries
- wheel and source distribution builds
- `twine check`
- coverage thresholds
- optional dependency compatibility
- security policy
- issue templates
- pull request template
- release notes

## Contribution Notes

Contributors should:

- follow the existing package boundaries
- avoid adding required dependencies unless necessary
- keep optional framework support behind extras
- add type hints for public and internal APIs
- add docstrings for modules, classes, and public methods
- add tests for new behavior
- avoid changing stored data formats without migration support
- keep replay and diff read-only
- keep adapters observational
- preserve backward compatibility where possible

## Safety Model

AgentReplay is intended to be a local debugging and replay tool. It should never
require cloud services or API credentials to operate. Because it may record
prompts, responses, tool outputs, metadata, and errors, users should treat
recorded runs as potentially sensitive data.

Recommended practices:

- enable redaction when recording sensitive systems
- avoid committing `.agentreplay` databases
- review exported JSON, Markdown, and HTML before sharing
- configure prompt hiding when traces may contain private data
- keep plugin usage limited to trusted packages

## Maintainer Notes

For long-term maintainability:

- keep the core framework-agnostic
- keep integrations optional
- maintain clear compatibility notes for third-party SDK versions
- document migration steps for data format changes
- prefer small, focused abstractions
- keep test fixtures realistic
- add regression tests for reported adapter bugs
- benchmark storage, replay, and diff with large traces
