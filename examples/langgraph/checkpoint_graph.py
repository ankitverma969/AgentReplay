"""LangGraph checkpoint-aware recording example."""

from __future__ import annotations

try:
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover
    msg = 'Install LangGraph with: pip install "agentreplay[langgraph]"'
    raise SystemExit(msg) from exc

from agentreplay.langgraph import instrument


def answer(state: dict[str, str]) -> dict[str, str]:
    """Return a checkpointed response."""
    return {"answer": state["question"]}


builder = StateGraph(dict[str, str])
builder.add_node("answer", answer)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)

graph = instrument(builder.compile(checkpointer=InMemorySaver()))
config = {"configurable": {"thread_id": "example-thread"}}
print(graph.invoke({"question": "checkpoint me"}, config=config))
