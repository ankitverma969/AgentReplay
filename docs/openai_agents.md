# OpenAI Agents SDK Integration

AgentReplay integrates with the OpenAI Agents SDK through optional adapter code.
The base `agentreplay` package does not require the SDK, an OpenAI API key, or
network access.

## Installation

Install AgentReplay only:

```bash
pip install agentreplay
```

Install AgentReplay with the optional OpenAI Agents SDK dependency:

```bash
pip install "agentreplay[openai-agents]"
```

## Quick Start

Use automatic tracing instrumentation:

```python
import agentreplay

agentreplay.instrument()
```

Use a context manager:

```python
from agentreplay import AgentReplay

with AgentReplay():
    ...
```

Attach hooks to one agent:

```python
from agentreplay import AgentReplay

replay = AgentReplay(auto_instrument=False)
replay.attach(agent)
```

Decorate a runner function:

```python
from agentreplay import record_agent

@record_agent
def run_agent(prompt: str) -> str:
    ...
```

## Configuration

Configure the adapter with `OpenAIAgentsConfig`:

```python
from agentreplay import OpenAIAgentsConfig, instrument

instrument(
    config=OpenAIAgentsConfig(
        enabled=True,
        record_prompts=True,
        hide_prompts=False,
        redact_api_keys=True,
        ignore_tools=("internal_lookup",),
        ignore_events=("debug",),
        sample_rate=1.0,
        metadata={"service": "support-agent"},
        run_name="support-agent",
    ),
)
```

Supported environment variables:

- `AGENTREPLAY_OPENAI_ENABLED`
- `AGENTREPLAY_OPENAI_RECORD_PROMPTS`
- `AGENTREPLAY_OPENAI_HIDE_PROMPTS`
- `AGENTREPLAY_OPENAI_REDACT_API_KEYS`
- `AGENTREPLAY_OPENAI_IGNORE_TOOLS`
- `AGENTREPLAY_OPENAI_IGNORE_EVENTS`
- `AGENTREPLAY_OPENAI_SAMPLE_RATE`
- `AGENTREPLAY_OPENAI_RUN_NAME`

## Examples

Example projects live in `examples/openai_agents`:

- `basic_agent.py`
- `multi_tool_agent.py`
- `streaming_responses.py`
- `handoffs.py`
- `error_handling.py`

## Best Practices

Use automatic instrumentation for broad local debugging and `attach(agent)` when
you only want to observe a specific agent. Keep `redact_api_keys=True` in shared
development environments. Use `hide_prompts=True` when prompt content may
contain private user data.

## Migration Guide

Existing OpenAI Agents SDK apps can start with:

```python
import agentreplay

agentreplay.instrument()
```

For more controlled migration, attach only one agent first:

```python
from agentreplay import AgentReplay

debugger = AgentReplay(auto_instrument=False)
debugger.attach(agent)
```

No SDK source files need to be modified.

## Troubleshooting

If `instrument()` reports that the OpenAI Agents SDK is not installed, install
the optional extra. If no runs appear, verify that recording is enabled and that
`sample_rate` is greater than `0.0`. If prompt content should not be stored, set
`hide_prompts=True`.
