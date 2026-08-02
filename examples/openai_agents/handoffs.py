"""OpenAI Agents SDK handoff example with AgentReplay."""

from __future__ import annotations

import asyncio
import sys

import agentreplay


async def main() -> None:
    """Run an agent setup that may hand off to another agent."""
    from agents import Agent, Runner

    agentreplay.instrument()
    billing_agent = Agent(name="Billing", instructions="Handle billing questions.")
    triage_agent = Agent(
        name="Triage",
        instructions="Route billing questions to Billing.",
        handoffs=[billing_agent],
    )
    result = await Runner.run(triage_agent, "I need help with billing.")
    sys.stdout.write(f"{result.final_output}\n")


if __name__ == "__main__":
    asyncio.run(main())
