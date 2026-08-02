"""Streaming OpenAI Agents SDK example with AgentReplay context management."""

from __future__ import annotations

import asyncio
import sys

from agentreplay import AgentReplay


async def main() -> None:
    """Run a streaming agent inside an AgentReplay context."""
    from agents import Agent, Runner

    agent = Agent(name="Streamer", instructions="Answer with short sentences.")
    with AgentReplay():
        stream = Runner.run_streamed(agent, "Explain replay debugging.")
        async for event in stream.stream_events():
            if event.type == "raw_response_event":
                sys.stdout.write(".")
        sys.stdout.write("\n")


if __name__ == "__main__":
    asyncio.run(main())
