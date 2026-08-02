"""Minimal typing surface for optional OpenAI Agents SDK examples."""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any, ParamSpec, TypeVar

_P = ParamSpec("_P")
_R = TypeVar("_R")

class Agent:
    """OpenAI Agents SDK agent constructor surface used by examples."""

    def __init__(
        self,
        *,
        name: str,
        instructions: str,
        tools: Sequence[Callable[..., object]] | None = ...,
        handoffs: Sequence[Agent] | None = ...,
        **kwargs: Any,
    ) -> None: ...

class RunResult:
    """Run result surface used by examples."""

    final_output: object

class StreamEvent:
    """Streaming event surface used by examples."""

    type: str

class StreamedRunResult:
    """Streamed result surface used by examples."""

    def stream_events(self) -> AsyncIterator[StreamEvent]: ...

class Runner:
    """OpenAI Agents SDK runner surface used by examples."""

    @staticmethod
    async def run(agent: Agent, user_input: str, **kwargs: Any) -> RunResult: ...
    @staticmethod
    def run_streamed(
        agent: Agent,
        user_input: str,
        **kwargs: Any,
    ) -> StreamedRunResult: ...

def function_tool(func: Callable[_P, _R]) -> Callable[_P, _R]: ...
