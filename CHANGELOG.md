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
