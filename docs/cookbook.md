# Cookbook

## Export a Report

```bash
agentreplay report latest --output trace.html
```

## Run a Regression Gate in CI

```bash
agentreplay regression baseline:prod latest --summary
```

## Optimize a SQLite Database

```bash
agentreplay optimize --db-path .agentreplay/agentreplay.sqlite
agentreplay vacuum --db-path .agentreplay/agentreplay.sqlite
```

## Build a Custom Analyzer

Use `agentreplay.sdk.SDKAnalyzer` or a simple class with compatible metadata and
an `analyze(trace)` method. See `examples/extensions/custom_analyzer.py`.

## Add a Custom CLI Command

Implement `register(subparsers)` and wrap it with an SDK plugin. See
`examples/extensions/custom_cli_command.py`.
