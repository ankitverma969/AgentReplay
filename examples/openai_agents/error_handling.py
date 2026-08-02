"""OpenAI Agents SDK error handling example with AgentReplay."""

from __future__ import annotations

import asyncio
import sys

from agentreplay import record_agent


@record_agent
async def run_with_recording(prompt: str) -> str:
    """Run an agent and let AgentReplay capture exceptions."""
    from agents import Agent, Runner

    agent = Agent(name="ErrorDemo", instructions="Answer normally.")
    result = await Runner.run(agent, prompt)
    return str(result.final_output)


async def main() -> None:
    """Run the error-handling example."""
    try:
        output = await run_with_recording("Say hello.")
    except Exception as exc:
        sys.stdout.write(f"Agent failed: {exc}\n")
    else:
        sys.stdout.write(f"{output}\n")


if __name__ == "__main__":
    asyncio.run(main())
