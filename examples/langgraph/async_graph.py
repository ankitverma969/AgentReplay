"""Async LangGraph recording example."""

from __future__ import annotations

import asyncio
from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


class AsyncState(TypedDict, total=False):
    """State carried through the async example graph."""

    question: str
    answer: str


async def answer(state: AsyncState) -> AsyncState:
    """Return a deterministic async response for the example graph."""
    await asyncio.sleep(0)
    return {"answer": state["question"].upper()}


async def main() -> None:
    """Run the async example graph."""
    builder = StateGraph(AsyncState)
    builder.add_node("answer", answer)
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)

    graph = instrument(builder.compile())
    result = await graph.ainvoke({"question": "hello"})
    print(result)


asyncio.run(main())
