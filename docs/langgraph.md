# LangGraph Integration

AgentReplay can observe LangGraph executions without calling models, tools, or
external services itself. The adapter records only events emitted by the graph
and by LangChain-compatible callbacks.

## Installation

```bash
pip install "agentreplay[langgraph]"
```

## Quick Start

```python
from agentreplay.langgraph import instrument

graph = build_graph().compile()
graph = instrument(graph)

result = graph.invoke({"question": "What changed?"})
```

The wrapped graph delegates unknown attributes to the original graph. Your graph
logic stays unchanged; the wrapper only injects an AgentReplay callback into
Runnable config for each execution.

## Context Manager

```python
from agentreplay.langgraph import AgentReplay

replay = AgentReplay()
graph = replay.attach(build_graph().compile())

with replay:
    graph.invoke({"question": "Trace this run"})
```

Use `attach()` when you want an object-oriented integration manager. Use
`instrument(graph)` when you want the one-line form.

## Configuration

```python
from agentreplay.langgraph import LangGraphConfig, instrument

graph = instrument(
    graph,
    config=LangGraphConfig(
        record_inputs=True,
        record_outputs=True,
        hide_state=False,
        redact_secrets=True,
        ignore_nodes=("internal_secret_node",),
        ignore_events=("on_debug",),
        sample_rate=1.0,
        run_name="support-routing-graph",
        metadata={"team": "support"},
    ),
)
```

Supported environment variables:

- `AGENTREPLAY_LANGGRAPH_ENABLED`
- `AGENTREPLAY_LANGGRAPH_RECORD_INPUTS`
- `AGENTREPLAY_LANGGRAPH_RECORD_OUTPUTS`
- `AGENTREPLAY_LANGGRAPH_HIDE_STATE`
- `AGENTREPLAY_LANGGRAPH_REDACT_SECRETS`
- `AGENTREPLAY_LANGGRAPH_IGNORE_NODES`
- `AGENTREPLAY_LANGGRAPH_IGNORE_EVENTS`
- `AGENTREPLAY_LANGGRAPH_SAMPLE_RATE`
- `AGENTREPLAY_LANGGRAPH_RUN_NAME`
- `AGENTREPLAY_LANGGRAPH_STREAM_MODES`

## Recorded Events

The adapter records graph start and finish events, node start and finish events,
tool nodes, LLM nodes, retries, errors, stream chunks, state updates, checkpoint
signals, interrupts, resume payloads, likely conditional branches, likely
parallel branches, timing, and best-effort DAG metadata from `get_graph()`.

## Streaming

```python
graph = instrument(graph)

for chunk in graph.stream({"topic": "debugging"}, stream_mode="updates"):
    print(chunk)
```

Async event streams are also supported:

```python
async for event in graph.astream_events({"topic": "debugging"}, version="v2"):
    print(event)
```

## Export

```python
markdown = graph.export_run(export_format="markdown")
html = graph.export_run(export_format="html")
```

CLI export works with the normal storage backend:

```bash
agentreplay export latest --markdown
agentreplay export RUN_ID --html --output run.html
```

## Best Practices

- Keep prompt and state recording disabled or hidden when traces may contain
  sensitive user data.
- Prefer `ignore_nodes` for deterministic internal nodes that add noise.
- Use `sample_rate` for high-volume production workloads.
- Persist traces to SQLite during local debugging, then export Markdown or HTML
  when sharing a run with maintainers.
- Keep AgentReplay callbacks in addition to any existing callbacks; the adapter
  appends its callback to the Runnable config.

## Performance Notes

AgentReplay performs best-effort serialization of event payloads. Large state
objects can increase memory use and SQLite write time. Use `hide_state=True`,
`record_inputs=False`, or `record_outputs=False` for large graphs when the
shape of execution matters more than full payload inspection.

## Troubleshooting

- If no node events appear, verify the graph honors LangChain Runnable
  callbacks through the `config={"callbacks": [...]}` mechanism.
- If streamed chunks are recorded but node events are absent, the graph may emit
  stream data without callback lifecycle events.
- If interrupts are missing, inspect the stream output shape and ensure the
  interrupt payload is visible to callers.
- If `instrument(graph)` cannot import LangGraph, install the optional extra.

## Migration Guide

Start by wrapping compiled graphs at the application boundary:

```python
graph = instrument(graph)
```

Then move repeated settings into `LangGraphConfig` or environment variables.
For service applications, pass an explicit `SQLiteStorage` so all workers write
to the intended local database path.
