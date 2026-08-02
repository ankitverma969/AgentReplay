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

## Status

AgentReplay is feature complete for its initial open-source release candidate.
The repository contains:

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
- SQLite storage engine
- read-only replay engine
- read-only diff engine
- interactive time travel debugger
- AI agent profiler
- rich standalone HTML trace report generator
- massive trace optimization and scalability engine
- AI regression detection and root-cause analysis engine
- public SDK and extension platform
- OpenAI Agents SDK adapter
- LangGraph adapter
- Plugin SDK
- Enterprise security and redaction engine
- Enterprise observability module with OpenTelemetry-compatible exports
- release engineering for PyPI, GitHub Releases, CI, security scanning,
  documentation publishing, packaging validation, and benchmarks

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

Run the full release-readiness suite before publishing:

```bash
make coverage
make security
make dead-code
make docs
make benchmark
make build
python -m twine check dist/*
```

Use the CLI:

```bash
agentreplay --help
agentreplay version
agentreplay benchmark --events 10000
agentreplay optimize
agentreplay analyze-db --json
agentreplay vacuum
agentreplay regression BASELINE_RUN TARGET_RUN --summary
```

## Public SDK

Build third-party extensions with the stable SDK surface:

```python
from agentreplay.sdk import AnalyzerResult, SDKExtensionMetadata, create_sdk


class MyAnalyzer:
    metadata = SDKExtensionMetadata(
        name="my-analyzer",
        version="0.1.0",
        kind="analyzer",
    )

    def analyze(self, trace):
        return AnalyzerResult(analyzer=self.metadata.name)


sdk = create_sdk()
sdk.register(MyAnalyzer())
```

See `docs/sdk.md` for analyzers, exporters, storage engines, reports,
visualizations, framework adapters, CLI commands, event bus usage, hooks,
versioning, and compatibility guidance.

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

The recorder is local and in-memory by default. It does not require an LLM, API
key, cloud service, or storage backend.

## SQLite Storage

Persist recorded runs locally with the default SQLite backend:

```python
from agentreplay import Recorder, SQLiteStorage

with Recorder(name="agent") as recorder:
    recorder.user_prompt("Hello")
    recorder.assistant_response("Hi")

with SQLiteStorage(".agentreplay/agentreplay.sqlite") as storage:
    recorder.save_to_storage(storage)
    run_id = recorder.last_run_id()
    if run_id is not None:
        saved_run = storage.load_run(run_id)
```

The storage layer is abstracted behind `StorageBackend`, so future database
backends can implement the same API.

## Replay

Replay reconstructs recorded runs without calling an LLM or executing tools:

```python
from agentreplay import ReplayEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
engine = ReplayEngine(storage=storage)

session = engine.load("run-id")
print(session.timeline.render())

engine.play()
engine.pause()
engine.seek(session.timeline.entries[0].event.event_id)
engine.resume()
engine.stop()
```

Use the CLI:

```bash
agentreplay replay RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay replay --file exported-run.json --timeline
agentreplay replay RUN_ID --speed 2 --step
```

## Interactive Debugger

Open a full-screen terminal debugger for recorded runs. The debugger is offline
and read-only: it loads traces from SQLite or exported JSON and never calls LLMs
or executes tools.

```bash
pip install "agentreplay[debugger]"
agentreplay debug RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay debug latest
agentreplay debug --file exported-run.json
```

The debugger includes an execution tree, current event inspector, metadata
panel, logs, search, filters, timeline navigation, statistics, event export, and
current-event diffing with `--diff-run`.

## Profiler

Profile recorded runs to find latency bottlenecks, token hotspots, expensive
operations, inefficient tools, memory overhead, retries, and optimization
opportunities. Profiling is read-only and never calls an LLM or executes tools.

```bash
agentreplay profile RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay profile latest --summary
agentreplay profile RUN_ID --json
agentreplay profile RUN_ID --html
agentreplay profile RUN_ID --markdown
agentreplay profile RUN_ID --csv
```

Python API:

```python
from agentreplay import ProfilerEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
report = ProfilerEngine(storage=storage).profile("run-id")

print(report.summary())
```

## HTML Reports

Generate a self-contained offline HTML report for debugging, auditing, and
sharing recorded traces. Reports embed all CSS, JavaScript, report data,
timeline views, graph views, profiler results, security findings, and optional
diff data into one file.

```bash
agentreplay report RUN_ID --output report.html
agentreplay report latest --dark --compress --output report.html
agentreplay report RUN1 --compare RUN2 --light --output comparison.html
```

Python API:

```python
from agentreplay import ReportingEngine, ReportOptions
from agentreplay.reporting.renderers import render_html

bundle = ReportingEngine().generate("run-id", options=ReportOptions(theme="dark"))
html = render_html(bundle)
```

## Diff

Compare two recorded runs without executing the agent, tools, or LLM calls:

```python
from agentreplay import DiffEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
diff = DiffEngine(storage=storage)

result = diff.compare("baseline-run-id", "candidate-run-id")
print(result.summary())
```

Use the CLI:

```bash
agentreplay diff RUN1 RUN2 --db-path .agentreplay/agentreplay.sqlite
agentreplay diff RUN1 RUN2 --json
agentreplay diff RUN1 RUN2 --markdown --verbose
agentreplay diff RUN1 RUN2 --html
agentreplay diff RUN1 RUN2 --summary
```

Export stored runs as JSON, Markdown, or HTML:

```bash
agentreplay export RUN_ID --json
agentreplay export RUN_ID --markdown
agentreplay export RUN_ID --html --output run.html
```

## OpenAI Agents SDK

AgentReplay can observe OpenAI Agents SDK runs through optional adapter support:

```python
import agentreplay

agentreplay.instrument()
```

The integration uses SDK extension points and keeps `openai-agents` optional:

```bash
pip install "agentreplay[openai-agents]"
```

See `docs/openai_agents.md` and `examples/openai_agents` for configuration,
quick-start examples, best practices, migration notes, and troubleshooting.

## LangGraph

AgentReplay can observe LangGraph compiled graphs and Runnable-compatible graph
executions through optional adapter support:

```python
from agentreplay.langgraph import instrument

graph = instrument(graph)
result = graph.invoke({"question": "What happened?"})
```

Use an integration manager when you prefer attach-style setup:

```python
from agentreplay.langgraph import AgentReplay

replay = AgentReplay()
graph = replay.attach(graph)
```

The adapter appends an AgentReplay callback to Runnable config and records graph
start/end, node lifecycle events, tools, LLM nodes, retries, errors, streaming
chunks, checkpoints, interrupts, state updates, timing, and DAG metadata when
available. It does not call LLMs or execute tools.

```bash
pip install "agentreplay[langgraph]"
```

See `docs/langgraph.md` and `examples/langgraph` for configuration, examples,
performance notes, troubleshooting, and migration guidance.

## Plugins

AgentReplay includes a Plugin SDK for third-party integrations:

```python
from agentreplay.plugins import AgentReplayPlugin


class CrewAIPlugin(AgentReplayPlugin):
    name = "crewai"
    version = "1.0.0"
    plugin_type = "agent_framework"

    def register(self, app):
        app.register_agent_framework("crewai", object())
```

External packages expose plugins through the `agentreplay.plugins` entry-point
group and become available after installation.

## Security

AgentReplay redacts common secrets and PII before traces are stored, exported,
replayed, diffed, or displayed:

```bash
agentreplay security scan RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay security verify exported-run.json
agentreplay security rules
```

See `docs/security.md` for configuration, examples, best practices, compliance
notes, and plugin extension points.

## Observability

AgentReplay can map recorded runs to OpenTelemetry-compatible telemetry:

```bash
agentreplay telemetry status
agentreplay telemetry test --json
agentreplay telemetry export RUN_ID --db-path .agentreplay/agentreplay.sqlite
```

Install OTLP exporter support with:

```bash
pip install "agentreplay[otel]"
```

See `docs/observability.md` for architecture, configuration, exporter guides,
OTLP setup, metrics, performance notes, and troubleshooting.

```bash
agentreplay plugins
agentreplay plugins list
agentreplay plugins info crewai
agentreplay plugins install agentreplay-crewai
agentreplay plugins disable crewai
```

See `docs/plugins.md` for the full API, lifecycle hooks, configuration,
best practices, and migration guide.

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
- `AGENTREPLAY_PLUGINS_ENABLED`
- `AGENTREPLAY_PLUGIN_AUTO_DISCOVER`
- `AGENTREPLAY_DISABLED_PLUGINS`
- `AGENTREPLAY_PLUGIN_CONFIG_<PLUGIN>__<KEY>`

Example:

```toml
enabled = true
db_path = ".agentreplay/agentreplay.sqlite"
redaction_enabled = true
log_level = "INFO"
storage_backend = "sqlite"
fail_mode = "fail_open"

[plugins]
enabled = true
auto_discover = true
disabled = []
```

## License

AgentReplay is released under the MIT License.
