# Migration Guide

## Version 0.1

AgentReplay is pre-1.0 but provides a stable public SDK surface through
`agentreplay.sdk`.

## Import Guidance

Application code may import from `agentreplay`.

Extension code should import from `agentreplay.sdk` and avoid internal modules.

## Optional Debugger Dependency

The interactive debugger uses Textual and is available through:

```bash
pip install "agentreplay[debugger]"
```

Core recording, storage, replay, diff, profiling, reporting, regression,
security, SDK, and CLI workflows do not require Textual.

## Deprecations

Stable SDK APIs use semantic versioning. Deprecated SDK APIs emit
`DeprecationWarning` for at least one minor release before removal.
