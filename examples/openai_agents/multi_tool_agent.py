"""Multi-tool OpenAI Agents SDK example with tool filtering."""

from __future__ import annotations

import asyncio
import sys

from agentreplay import OpenAIAgentsConfig, instrument


async def main() -> None:
    """Run a tool-using agent while ignoring internal tools."""
    from agents import Agent, Runner, function_tool

    @function_tool
    def public_lookup(query: str) -> str:
        return f"public result for {query}"

    @function_tool
    def internal_lookup(query: str) -> str:
        return f"internal result for {query}"

    instrument(config=OpenAIAgentsConfig(ignore_tools=("internal_lookup",)))
    agent = Agent(
        name="Researcher",
        instructions="Use tools when useful.",
        tools=[public_lookup, internal_lookup],
    )
    result = await Runner.run(agent, "Find a public fact about AgentReplay.")
    sys.stdout.write(f"{result.final_output}\n")


if __name__ == "__main__":
    asyncio.run(main())
