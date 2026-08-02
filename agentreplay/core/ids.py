"""Identifier generation abstractions for AgentReplay."""

from __future__ import annotations

from typing import Protocol
from uuid import uuid4


class IdGenerator(Protocol):
    """Protocol for replaceable identifier generators."""

    def new_id(self) -> str:
        """Return a new opaque identifier."""


class UUIDGenerator:
    """Identifier generator backed by random UUID4 values."""

    def new_id(self) -> str:
        """Return a UUID4 string."""
        return str(uuid4())


__all__ = ["IdGenerator", "UUIDGenerator"]
