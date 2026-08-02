"""Shared typing aliases used across AgentReplay."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | Sequence["JSONValue"] | Mapping[str, "JSONValue"]
Metadata: TypeAlias = Mapping[str, JSONValue]

__all__ = ["JSONScalar", "JSONValue", "Metadata"]
