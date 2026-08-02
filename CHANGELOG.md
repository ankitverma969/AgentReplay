# Changelog

All notable changes to AgentReplay will be documented in this file.

The project follows Semantic Versioning.

## 0.1.0 - Unreleased

- Added Phase 1 project foundation.
- Added packaging, CLI entrypoint, typed settings, logging, and documentation
  scaffold.
- Added in-memory recorder engine.
- Added SQLite storage engine with schema migrations, repositories, pagination,
  filtering, sorting, and event streaming.
- Added read-only replay engine with timeline rendering, JSON/file/database
  loading, playback controls, CLI support, and replay tests.
- Added read-only diff engine with structured changes, event alignment, console,
  JSON, Markdown, HTML, and summary reports.
- Added OpenAI Agents SDK adapter with tracing instrumentation, agent hooks,
  decorator/context/manual APIs, configuration, CLI latest helpers, docs, and
  tests.
- Added LangGraph adapter with Runnable callback instrumentation, sync/async
  graph execution tracing, streaming and checkpoint signals, DAG metadata,
  read-only export helpers, CLI export support, docs, examples, and tests.
- Added Plugin SDK with plugin metadata, validation, discovery, manager,
  registry, loader, dependency resolution, compatibility checks, lifecycle
  hooks, plugin configuration, CLI commands, docs, and tests.
- Added enterprise security and redaction engine with secret and PII detection,
  configurable redaction strategies, recorder/export/replay/diff sanitization,
  CLI scan/verify/report/rules commands, plugin security registrations,
  documentation, and tests.
- Added enterprise observability module with OpenTelemetry-compatible trace
  mapping, console/JSON/file/OTLP exporters, sampling, correlation context,
  metrics aggregation, telemetry CLI commands, plugin observability
  registrations, documentation, and tests.
- Added interactive time travel debugger with Textual-powered TUI, execution
  tree, event inspector, metadata and log panels, keyboard navigation, search,
  filters, statistics, selection export, current-event diffing, CLI command,
  documentation, and tests.
- Added AI agent profiler with duration percentiles, token/cost/model/tool/memory
  analysis, bottleneck detection, optimization recommendations, visualization
  data, console/JSON/Markdown/HTML/CSV reports, plugin extension points, CLI
  command, documentation, and tests.
- Added rich standalone HTML trace report generator with embedded offline
  assets, execution graph, timeline, trace tree, search/filter index, profiler
  results, security findings, optional diff report, JSON/Markdown/ZIP exports,
  plugin report extensions, CLI command, documentation, and tests.
- Added massive trace optimization and scalability engine with chunked/windowed
  loading, streaming JSON/JSONL exports, compression helpers, LRU cache, object
  pooling, SQLite optimization, FTS-backed search with streaming fallback,
  benchmark suite, performance reports, CLI commands, documentation, and tests.
- Added AI regression detection and root-cause analysis engine with deterministic
  regression, improvement, behavioral-change, trend, impact, recommendation,
  graph, CLI, plugin extension, documentation, and test coverage.
- Added public SDK and extension platform with stable extension protocols,
  typed event bus, hook manager, compatibility checks, deprecation helpers,
  extension registry, plugin bridge, dynamic CLI command registration, examples,
  documentation, and tests.
