"""LangGraph parallel branch recording example."""

from __future__ import annotations

from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


class ParallelState(TypedDict, total=False):
    """State carried through the parallel branch example graph."""

    topic: str
    left: str
    right: str
    answer: str


def left(state: ParallelState) -> ParallelState:
    """Return the left branch output."""
    return {"left": state["topic"]}


def right(state: ParallelState) -> ParallelState:
    """Return the right branch output."""
    return {"right": state["topic"]}


def join(state: ParallelState) -> ParallelState:
    """Join branch state."""
    return {"answer": f"{state.get('left', '')} {state.get('right', '')}".strip()}


builder = StateGraph(ParallelState)
builder.add_node("left", left)
builder.add_node("right", right)
builder.add_node("join", join)
builder.add_edge(START, "left")
builder.add_edge(START, "right")
builder.add_edge("left", "join")
builder.add_edge("right", "join")
builder.add_edge("join", END)

graph = instrument(builder.compile())
print(graph.invoke({"topic": "parallel"}))
