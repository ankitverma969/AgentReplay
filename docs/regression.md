# AgentReplay Regression Guide

`agentreplay.regression` compares recorded executions and detects regressions,
improvements, and behavioral changes without calling LLMs or executing tools.

The engine consumes existing AgentReplay trace data, Diff results, and Profiler
metrics. It is designed as the primary production debugging workflow after a
release, prompt change, model change, tool change, or infrastructure change.

## Quick Start

```python
from agentreplay import RegressionEngine, SQLiteStorage

storage = SQLiteStorage(".agentreplay/agentreplay.sqlite")
engine = RegressionEngine(storage=storage)

report = engine.compare("baseline-run", "target-run")
print(report.summary())
```

CLI:

```bash
agentreplay regression BASELINE_RUN TARGET_RUN
agentreplay regression BASELINE_RUN TARGET_RUN --summary
agentreplay regression BASELINE_RUN TARGET_RUN --json
agentreplay regression BASELINE_RUN TARGET_RUN --html
agentreplay regression BASELINE_RUN TARGET_RUN --markdown
agentreplay regression BASELINE_RUN TARGET_RUN --csv
agentreplay regression BASELINE_RUN TARGET_RUN --graph
```

Special run aliases:

- `latest`: latest stored run
- `last-successful`: latest completed run
- `baseline:NAME`: latest completed baseline-tagged run whose name contains
  `NAME`

## What It Detects

- Latency increases and decreases
- Cost increases and decreases
- Token increases and decreases
- Tool selection and tool order changes
- Missing or additional tool calls
- Model and provider changes
- Prompt and system prompt changes
- Assistant response changes
- Retry, error, warning, and failure-rate changes
- Memory read/write changes
- Metadata and configuration changes
- Execution graph changes

## Root Cause Analysis

Every finding includes:

- What changed
- Where it changed
- When it changed
- Severity
- Likely cause
- Affected downstream events
- Confidence score

The root-cause explanation is deterministic and based only on recorded traces.
For example, if tokens and cost increase after a prompt diff, the likely cause is
reported as prompt or context growth.

## Classification

Findings are classified into:

- Performance
- Cost
- Quality
- Tooling
- Model
- Memory
- Infrastructure
- Configuration
- Security
- Custom

Severity levels are:

- Critical
- High
- Medium
- Low
- Informational

## Trend Analysis

The engine can compare a target against many historical runs and compute
latency, cost, token, error, and retry trends:

```python
trend = engine.trends(["run-1", "run-2", "run-3"])
```

## Plugin Support

Plugins can register custom regression rules, analyzers, and recommendations via
the Plugin SDK:

```python
app.register_regression_rule("domain-rule", rule)
app.register_regression_analyzer("domain-analyzer", analyzer)
app.register_regression_recommendation("domain-recommendation", recommender)
```

Custom plugin failures are isolated and reported as low-severity custom findings
or plugin result errors.

## Best Practices

- Keep stable baseline runs tagged with `baseline`.
- Compare prompt, model, provider, and tool changes before production release.
- Use `--summary` in CI and `--json` for automated gates.
- Use `--html` for release review and incident analysis.
- Review high and critical findings before shipping agent changes.
- Treat improvements as evidence to preserve useful optimizations.
