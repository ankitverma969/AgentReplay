# AgentReplay Profiler

AgentReplay includes a read-only profiler for recorded AI agent executions. It
analyzes existing traces from SQLite or in-memory snapshots and never executes
agents, tools, replay logic, diff logic, or LLM calls.

## Quick Start

```bash
agentreplay profile RUN_ID
agentreplay profile latest --summary
agentreplay profile RUN_ID --timeline
agentreplay profile RUN_ID --json
agentreplay profile RUN_ID --html
agentreplay profile RUN_ID --markdown
agentreplay profile RUN_ID --csv
```

Use `--db-path` to profile a run stored outside the default local database.

## Python API

```python
from agentreplay import ProfilerEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
report = ProfilerEngine(storage=storage).profile("run-id")

print(report.summary())
print(report.duration.p95_ms)
print(report.cost_analysis.total_cost)
```

## What It Analyzes

- Total execution time, average event duration, median, P50, P90, P95, and P99.
- Slowest and fastest events, tools, and model calls.
- Tool, LLM, memory, replay, and diff duration distributions.
- Prompt, completion, and total tokens.
- Tokens per tool, per model, and token distribution.
- Total, average, daily, and monthly estimated cost.
- Cost per tool, model, and request.
- Models used, provider distribution, latency, cost, token averages, failures,
  and retries.
- Tool usage, average duration, fastest and slowest tools, failures, and retry
  counts.
- Memory reads, writes, latency, and approximate payload size.

## Bottleneck Detection

The profiler detects slow tools, slow model calls, repeated calls, duplicate
event signatures, redundant memory reads, large prompts, large responses,
excessive retries, and expensive operations.

## Recommendations

Recommendations are generated from profile evidence and can include prompt
compression, tool caching, parallel execution, model selection, retry tuning,
memory optimization, streaming, batching, and cost reduction.

## Visualizations

Reports include visualization-ready data for execution timelines, latency
histograms, token histograms, cost breakdowns, pie charts, bar charts, flame
graphs, and waterfall charts. AgentReplay emits the data; external tools can
render it however they prefer.

## Plugin Extension Points

Plugins can register custom profilers, custom metrics, and custom
recommendations through `PluginApp.register_custom_profiler()`,
`PluginApp.register_custom_metric()`, and
`PluginApp.register_custom_recommendation()`.

## Performance Notes

The storage-backed profiler streams events from SQLite in batches before
building aggregate metrics. Visualization rows are capped to keep reports
bounded for very large runs, while aggregate duration, token, cost, model, tool,
memory, and bottleneck analysis still considers the full trace.
