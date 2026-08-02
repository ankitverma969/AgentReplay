# AgentReplay Architecture

AgentReplay is organized as a framework-agnostic core with optional adapters and
extension surfaces around it. The core records, stores, replays, compares,
profiles, secures, reports, and exports recorded traces without calling LLMs or
executing tools during offline analysis.

## Package Boundaries

- `agentreplay.core`: immutable domain models, event and run types, clocks,
  identifiers, metadata helpers, and trace snapshots.
- `agentreplay.recording`: in-memory recording engine, run/session/event
  managers, decorators, context managers, nested spans, metadata collection,
  serialization, and automatic timing.
- `agentreplay.storage`: storage protocol, SQLite backend, migrations,
  repositories, transaction handling, pagination, filtering, sorting, bulk
  inserts, and streaming reads.
- `agentreplay.replay`: read-only replay engine, sessions, iterators, event
  timelines, playback controller, seeking, stepping, and speed control.
- `agentreplay.diff`: deterministic run comparison, event alignment, severity
  classification, summary data, and console/JSON/Markdown/HTML renderers.
- `agentreplay.security`: secret and PII detection, redaction policies, trace
  sanitization, verification, report rendering, and CLI scanning.
- `agentreplay.observability`: OpenTelemetry-compatible trace mapping,
  exporters, sampling, correlation context, and metrics aggregation.
- `agentreplay.debugger`: offline debugger sessions, search, filters, stats,
  export helpers, and optional Textual TUI.
- `agentreplay.profiler`: latency, token, cost, model, tool, memory, retry, and
  bottleneck analysis with recommendation and visualization data.
- `agentreplay.reporting`: self-contained offline report bundles and renderers
  for trace, graph, timeline, profiler, security, and diff output.
- `agentreplay.performance`: chunked and windowed loading, streaming exports,
  compression, cache, pooling, SQLite optimization, search, and benchmark data.
- `agentreplay.regression`: deterministic regression detection, root-cause
  analysis, impact estimation, trend analysis, recommendations, and reports.
- `agentreplay.adapters`: optional framework integrations such as OpenAI Agents
  SDK and LangGraph.
- `agentreplay.plugins`: plugin discovery, validation, lifecycle handling,
  dependency checks, registry, and plugin CLI management.
- `agentreplay.sdk`: stable long-term extension interface for analyzers,
  exporters, storage engines, visualizations, framework adapters, custom
  reports, CLI commands, event bus subscriptions, hooks, compatibility checks,
  and deprecation helpers.
- `agentreplay.cli`: command registration and command handlers.

## Dependency Rules

Core modules use the Python standard library unless a dependency is explicitly
optional. Framework adapters, OpenTelemetry exporters, and the interactive
debugger live behind extras so `pip install agentreplay` stays small and does
not require API keys, cloud services, or framework packages.

## Runtime Flow

Recording creates a `TraceSnapshot` made of a `RunRecord` and ordered
`EventRecord` objects. Storage persists snapshots through the storage protocol.
Replay, diff, profiler, debugger, security, reporting, performance, and
regression modules consume snapshots read-only.

## Extension Flow

Plugins and third-party packages should depend on `agentreplay.sdk`. The SDK
exposes typed context objects, event bus subscriptions, lifecycle hooks,
extension metadata, compatibility checks, and registration protocols without
requiring imports from internal modules.

## Release Engineering

The repository is prepared for multi-platform CI, security scanning, dead-code
detection, coverage enforcement, package build validation, benchmark reporting,
MkDocs Material documentation, semantic release automation, PyPI publishing, and
GitHub Releases.
