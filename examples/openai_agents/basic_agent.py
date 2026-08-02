"""Basic OpenAI Agents SDK integration with AgentReplay."""

from __future__ import annotations

import asyncio
import sys

import agentreplay


async def main() -> None:
    """Run a basic OpenAI Agents SDK agent with AgentReplay enabled."""
    from agents import Agent, Runner

    agentreplay.instrument()
    agent = Agent(name="Assistant", instructions="Answer concisely.")
    result = await Runner.run(agent, "What is AgentReplay?")
    sys.stdout.write(f"{result.final_output}\n")


if __name__ == "__main__":
    asyncio.run(main())
