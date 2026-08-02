"""Dependency injection primitives for AgentReplay foundation services."""

from __future__ import annotations

from dataclasses import dataclass
from logging import Logger

from agentreplay.config import Settings, get_settings
from agentreplay.core.clocks import Clock, SystemClock
from agentreplay.core.ids import IdGenerator, UUIDGenerator
from agentreplay.logging import setup_logging


@dataclass(frozen=True, slots=True)
class Container:
    """Container for replaceable runtime dependencies.

    The container intentionally includes only foundation services in Phase 1.
    Future phases can add recorder, storage, replay, and diff services without
    changing the public configuration model.
    """

    settings: Settings
    clock: Clock
    id_generator: IdGenerator
    logger: Logger


def create_container(
    *,
    settings: Settings | None = None,
    clock: Clock | None = None,
    id_generator: IdGenerator | None = None,
    logger: Logger | None = None,
) -> Container:
    """Create a dependency container with explicit override points."""
    resolved_settings = get_settings() if settings is None else settings
    resolved_logger = setup_logging(resolved_settings) if logger is None else logger

    return Container(
        settings=resolved_settings,
        clock=SystemClock() if clock is None else clock,
        id_generator=UUIDGenerator() if id_generator is None else id_generator,
        logger=resolved_logger,
    )


__all__ = ["Container", "create_container"]
