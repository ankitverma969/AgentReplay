"""Basic LangGraph recording example."""

from __future__ import annotations

from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


class BasicState(TypedDict, total=False):
    """State carried through the basic example graph."""

    question: str
    answer: str


def answer(state: BasicState) -> BasicState:
    """Return a deterministic response for the example graph."""
    return {"answer": f"AgentReplay saw: {state['question']}"}


builder = StateGraph(BasicState)
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)

graph = instrument(builder.compile())
result = graph.invoke({"question": "hello"})
print(result)
