"""LangGraph streaming recording example."""

from __future__ import annotations

from typing import TypedDict

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


class StreamingState(TypedDict, total=False):
    """State carried through the streaming example graph."""

    topic: str
    draft: str
    answer: str


def draft(state: StreamingState) -> StreamingState:
    """Create a draft value."""
    return {"draft": state["topic"]}


def finish(state: StreamingState) -> StreamingState:
    """Create the final value."""
    return {"answer": f"Finished: {state['draft']}"}


builder = StateGraph(StreamingState)
builder.add_node("draft", draft)
builder.add_node("finish", finish)
builder.add_edge(START, "draft")
builder.add_edge("draft", "finish")
builder.add_edge("finish", END)

graph = instrument(builder.compile())
for chunk in graph.stream({"topic": "debugging"}, stream_mode="updates"):
    print(chunk)
