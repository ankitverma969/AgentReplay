"""LangGraph streaming recording example."""

from __future__ import annotations

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


def draft(state: dict[str, str]) -> dict[str, str]:
    """Create a draft value."""
    return {"draft": state["topic"]}


def finish(state: dict[str, str]) -> dict[str, str]:
    """Create the final value."""
    return {"answer": f"Finished: {state['draft']}"}


builder = StateGraph(dict[str, str])
builder.add_node("draft", draft)
builder.add_node("finish", finish)
builder.add_edge(START, "draft")
builder.add_edge("draft", "finish")
builder.add_edge("finish", END)

graph = instrument(builder.compile())
for chunk in graph.stream({"topic": "debugging"}, stream_mode="updates"):
    print(chunk)
