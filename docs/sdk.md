# AgentReplay Public SDK

`agentreplay.sdk` is the stable extension interface for AgentReplay. Future
plugins should depend on this package instead of importing AgentReplay internals.

The SDK supports:

- Custom analyzers
- Custom exporters
- Custom storage factories
- Custom visualizations
- Custom framework adapters
- Custom report sections
- Custom CLI commands
- Typed event bus subscriptions
- Lifecycle hooks
- Semantic-version compatibility checks
- Deprecation helpers

## Architecture

The SDK has four primary parts:

- `SDKContext`: stable access to recorder, replay, diff, profiler, security,
  regression, storage, reporting, and observability APIs.
- `SDKExtensionRegistry`: typed registry for analyzers, exporters, storage,
  visualizations, framework adapters, reports, and CLI commands.
- `SDKEventBus`: typed publish/subscribe bus for execution lifecycle events.
- `SDKHookManager`: typed lifecycle hook system for before/after extension work.

## Events

Extensions can subscribe to:

- `run.started`
- `run.finished`
- `event.created`
- `replay.started`
- `replay.finished`
- `export.started`
- `export.finished`
- `profiler.finished`
- `regression.finished`

```python
from agentreplay.sdk import create_sdk

sdk = create_sdk()
sdk.events.subscribe("run.started", lambda event: print(event.payload))
sdk.events.publish("run.started", payload={"run_id": "run-1"})
```

## Hooks

Supported hooks:

- `before_recording`
- `after_recording`
- `before_replay`
- `after_replay`
- `before_export`
- `after_export`
- `before_report`
- `after_report`
- `before_storage`
- `after_storage`

```python
sdk.hooks.register(
    "before_export",
    lambda context: print(context.payload),
    extension_name="my-extension",
)
sdk.hooks.emit("before_export", payload={"run_id": "run-1"})
```

## Analyzer Guide

```python
from agentreplay.sdk import AnalyzerResult, SDKExtensionMetadata


class PromptAnalyzer:
    metadata = SDKExtensionMetadata(
        name="prompt-analyzer",
        version="0.1.0",
        kind="analyzer",
    )

    def analyze(self, trace):
        prompts = [
            event for event in trace.events if event.event_type.startswith("prompt.")
        ]
        return AnalyzerResult(
            analyzer=self.metadata.name,
            metrics={"prompt_events": len(prompts)},
        )
```

## Exporter Guide

```python
from agentreplay.sdk import ExportResult, SDKExtensionMetadata


class XMLExporter:
    metadata = SDKExtensionMetadata(
        name="xml-exporter",
        version="0.1.0",
        kind="exporter",
    )

    def export(self, trace, destination=None):
        content = f"<trace run='{trace.run.run_id}' />".encode()
        return ExportResult(
            exporter=self.metadata.name,
            content_type="application/xml",
            bytes_written=len(content),
            uri=destination,
        )
```

## CLI Command Guide

```python
from agentreplay.sdk import SDKExtensionMetadata


class MyCommand:
    metadata = SDKExtensionMetadata(
        name="myplugin",
        version="0.1.0",
        kind="cli_command",
    )

    def register(self, subparsers):
        parser = subparsers.add_parser("myplugin")
        parser.set_defaults(handler=lambda args: 0)
```

Plugin packages can expose these commands through `AgentReplaySDKPlugin`, so
users can run commands such as:

```bash
agentreplay myplugin analyze
```

## Versioning

The SDK follows semantic versioning. Extensions declare compatibility with:

```python
from agentreplay.sdk import compatible

compatibility = compatible(min_sdk_version="0.1.0")
```

The current SDK API version is exported as `SDK_API_VERSION`.

## Deprecation Policy

Stable SDK APIs emit `DeprecationWarning` for at least one minor release before
removal. The policy text is exported as `DEPRECATION_POLICY`.

## Best Practices

- Import from `agentreplay.sdk`, not private AgentReplay modules.
- Never call LLMs or execute tools inside analyzers or regression rules.
- Keep exporters streaming-friendly for large traces.
- Validate extension metadata and compatibility at registration time.
- Fail open where possible so core AgentReplay workflows continue.
- Keep CLI commands namespaced to avoid collisions with built-ins.
