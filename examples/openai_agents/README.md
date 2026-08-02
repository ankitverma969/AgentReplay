# OpenAI Agents SDK Examples

These examples show how AgentReplay can be added to OpenAI Agents SDK projects.
They require the optional SDK dependency:

```bash
pip install "agentreplay[openai-agents]"
```

The examples are intentionally small and keep AgentReplay setup to one or two
lines.

- `basic_agent.py`: automatic tracing instrumentation.
- `multi_tool_agent.py`: ignore selected tools.
- `streaming_responses.py`: context manager usage around streaming.
- `handoffs.py`: handoff recording.
- `error_handling.py`: exception recording.
