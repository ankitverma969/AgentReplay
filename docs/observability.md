# AgentReplay Observability

AgentReplay includes an optional enterprise observability module for exporting
recorded runs into OpenTelemetry-compatible telemetry. The module is local and
modular by default, and OTLP export becomes available when the optional
OpenTelemetry dependencies are installed.

## Architecture

The observability package is isolated under `agentreplay.observability`.

Core parts:

- `ObservabilityEngine`: maps and exports AgentReplay traces
- `TraceMapper`: converts AgentReplay runs and events into telemetry traces and
  spans
- `MetricsAggregator`: computes run, latency, token, cost, tool, model, replay,
  diff, export, and plugin metrics
- `TelemetrySampler`: implements always-on, always-off, ratio, parent-based, and
  custom sampling
- Exporters: console, JSON, file, OTLP HTTP, and OTLP gRPC
- `CorrelationContext`: carries trace, run, request, session, user, custom, and
  baggage identifiers

AgentReplay mapping:

- every AgentReplay run maps to an OpenTelemetry-compatible trace
- every AgentReplay event maps to an OpenTelemetry-compatible span
- parent event IDs are preserved as parent span IDs and links
- event payloads are attached as span events
- semantic attributes are emitted for LLMs, tools, latency, tokens, cost,
  errors, warnings, framework metadata, service metadata, and correlations

## Installation

Base observability works without additional dependencies:

```bash
pip install agentreplay
```

Install OpenTelemetry exporters:

```bash
pip install "agentreplay[otel]"
```

Install all optional integrations:

```bash
pip install "agentreplay[all]"
```

## Quick Start

```python
from agentreplay import ObservabilityConfig, ObservabilityEngine, Recorder

with Recorder(name="agent") as recorder:
    recorder.user_prompt("Hello")
    recorder.assistant_response("Hi")

engine = ObservabilityEngine(
    ObservabilityConfig(enabled=True, exporter="json"),
)

result = engine.export_trace(recorder.trace())
print(result.output)
```

## Configuration

Python:

```python
from agentreplay import configure

configure(
    observability_enabled=True,
    observability_exporter="otlp_http",
    observability_endpoint="http://localhost:4318/v1/traces",
    observability_service_name="agent-service",
    observability_environment="development",
    observability_sampling="ratio",
    observability_sampling_ratio=0.25,
)
```

TOML:

```toml
[observability]
enabled = true
exporter = "otlp_http"
endpoint = "http://localhost:4318/v1/traces"
service_name = "agent-service"
service_namespace = "agents"
environment = "development"
sampling = "ratio"
sampling_ratio = 0.25
timeout_ms = 10000
tls_enabled = true
compression = "gzip"
batch_size = 512
queue_size = 2048
graceful_shutdown_ms = 5000

[observability.headers]
x-tenant = "acme"
```

Environment variables:

```bash
AGENTREPLAY_OBSERVABILITY_ENABLED=true
AGENTREPLAY_OBSERVABILITY_EXPORTER=otlp_http
AGENTREPLAY_OBSERVABILITY_ENDPOINT=http://localhost:4318/v1/traces
AGENTREPLAY_OBSERVABILITY_SERVICE_NAME=agent-service
AGENTREPLAY_OBSERVABILITY_ENVIRONMENT=development
AGENTREPLAY_OBSERVABILITY_SAMPLING=ratio
AGENTREPLAY_OBSERVABILITY_SAMPLING_RATIO=0.25
AGENTREPLAY_OBSERVABILITY_HEADERS=x-tenant=acme
```

## Exporter Guide

Supported exporters:

- `console`: human-readable local output
- `json`: JSON string output
- `file`: append telemetry traces to JSONL
- `otlp_http`: export through OpenTelemetry OTLP HTTP
- `otlp_grpc`: export through OpenTelemetry OTLP gRPC

File exporter:

```python
from agentreplay import ObservabilityConfig, ObservabilityEngine

engine = ObservabilityEngine(
    ObservabilityConfig(
        enabled=True,
        exporter="file",
        file_path=".agentreplay/telemetry.jsonl",
    ),
)
```

## Jaeger Setup

Run Jaeger with OTLP enabled, then configure AgentReplay:

```bash
docker run --rm -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one
AGENTREPLAY_OBSERVABILITY_ENABLED=true
AGENTREPLAY_OBSERVABILITY_EXPORTER=otlp_grpc
AGENTREPLAY_OBSERVABILITY_ENDPOINT=http://localhost:4317
```

Open Jaeger at `http://localhost:16686` and select the configured service name.

## Grafana Tempo Setup

Use Tempo's OTLP endpoint:

```bash
AGENTREPLAY_OBSERVABILITY_ENABLED=true
AGENTREPLAY_OBSERVABILITY_EXPORTER=otlp_http
AGENTREPLAY_OBSERVABILITY_ENDPOINT=http://localhost:4318/v1/traces
```

Tempo can then be explored from Grafana through its Tempo data source.

## OTLP Guide

Prefer OTLP when integrating with:

- Jaeger
- Grafana Tempo
- SigNoz
- Honeycomb
- Datadog
- New Relic
- Elastic APM
- Lightstep
- OpenObserve

AgentReplay uses OpenTelemetry standards and avoids vendor-specific APIs. For
vendor-hosted endpoints, configure `endpoint`, `headers`, `auth_token`, TLS, and
compression according to the provider's OTLP instructions.

## Metrics

`MetricsAggregator` exposes:

- run count
- success count
- failure count
- retry count
- average latency
- P95 and P99 latency
- average tokens
- average cost
- tool usage
- model usage
- memory reads and writes
- replay count
- diff count
- export count
- plugin count

```python
from agentreplay import ObservabilityEngine

metrics = ObservabilityEngine().metrics([trace], plugin_count=3)
print(metrics.to_dict())
```

## CLI

```bash
agentreplay telemetry status
agentreplay telemetry config
agentreplay telemetry config --json
agentreplay telemetry test
agentreplay telemetry test --json
agentreplay telemetry export RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay telemetry export latest --json
```

## Plugin Support

Plugins can register:

- custom telemetry exporters
- custom metrics
- custom span processors
- custom attribute enrichers

```python
from agentreplay.plugins import AgentReplayPlugin, PluginApp


class ObservabilityPlugin(AgentReplayPlugin):
    name = "company-observability"
    version = "1.0.0"

    def register(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        app.register_telemetry_exporter("company", object())
```

## Best Practices

- Keep telemetry disabled by default in libraries and enable it in applications.
- Use sampling for high-volume systems.
- Prefer batch exporters for production OTLP endpoints.
- Configure service names and environments consistently.
- Use correlation IDs to connect AgentReplay traces with request logs.
- Export through OTLP standards instead of vendor-specific APIs.
- Call `shutdown()` during application termination to flush exporters.
- Keep security redaction enabled before exporting traces.

## Performance Notes

The mapper and metrics aggregator process events in linear time. Built-in file,
JSON, and console exporters avoid network calls. OTLP exporters use the
OpenTelemetry SDK batch span processor, with queue size, batch size, timeout, and
shutdown behavior controlled through configuration.

For traces with 100,000 or more events:

- use sampling where possible
- prefer file or batch OTLP exporters
- avoid console output
- keep payload sizes small
- tune queue and batch sizes for the deployment target

## Troubleshooting

If OTLP export fails:

- confirm `agentreplay[otel]` is installed
- verify the endpoint and protocol match the exporter
- confirm authentication headers or tokens are configured
- check TLS and compression settings
- run `agentreplay telemetry test --json`
- start with the `json` exporter to validate mapping before network export
