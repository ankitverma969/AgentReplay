# AgentReplay

AgentReplay is a local, framework-agnostic debugging and replay library for AI
agent executions.

It records important execution events, stores runs locally by default, and lets
developers inspect, replay, compare, profile, report on, and analyze regressions
without calling LLMs or executing tools during analysis.

## Install

```bash
pip install agentreplay
```

Optional extras:

```bash
pip install "agentreplay[debugger]"
pip install "agentreplay[otel]"
pip install "agentreplay[openai-agents]"
pip install "agentreplay[langgraph]"
```

## Core Workflows

- Record agent executions with `Recorder`
- Persist runs with `SQLiteStorage`
- Replay traces with `ReplayEngine`
- Compare traces with `DiffEngine`
- Profile traces with `ProfilerEngine`
- Generate reports with `ReportingEngine`
- Detect regressions with `RegressionEngine`
- Build extensions with `agentreplay.sdk`

## Design Promise

AgentReplay observes recorded data only. It does not require API keys, cloud
services, LLM calls, or tool execution for replay, diff, profiling, reporting, or
regression analysis.
