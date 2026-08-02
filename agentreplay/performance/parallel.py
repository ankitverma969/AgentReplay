"""Parallel processing helpers for scalable trace workloads."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import TypeVar

from agentreplay.performance.models import PoolKind

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


def parallel_map(
    func: Callable[[InputT], OutputT],
    items: Iterable[InputT],
    *,
    workers: int | None = None,
    pool: PoolKind = "thread",
) -> tuple[OutputT, ...]:
    """Map a callable across items with a thread or process pool."""
    executor_type = ThreadPoolExecutor if pool == "thread" else ProcessPoolExecutor
    with executor_type(max_workers=workers) as executor:
        return tuple(executor.map(func, items))


__all__ = ["parallel_map"]
