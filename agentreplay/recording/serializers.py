"""Serialization helpers for recorded event payloads and metadata."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from uuid import UUID

from agentreplay.config import get_settings
from agentreplay.security.config import security_config_from_settings
from agentreplay.security.engine import SecurityEngine
from agentreplay.types import JSONValue, Metadata


class EventSerializer:
    """Convert arbitrary Python values into JSON-compatible snapshots."""

    def __init__(self, security_engine: SecurityEngine | None = None) -> None:
        """Create a serializer with optional security sanitization."""
        if security_engine is None:
            settings = get_settings()
            security_engine = SecurityEngine(
                security_config_from_settings(settings),
            )
        self._security_engine = security_engine

    def serialize_payload(
        self, payload: Mapping[str, object] | None
    ) -> dict[str, JSONValue]:
        """Serialize an event payload mapping."""
        return self.serialize_mapping(payload)

    def serialize_metadata(
        self,
        metadata: Mapping[str, object] | None,
    ) -> dict[str, JSONValue]:
        """Serialize an event or run metadata mapping."""
        return self.serialize_mapping(metadata)

    def serialize_mapping(
        self,
        value: Mapping[str, object] | None,
    ) -> dict[str, JSONValue]:
        """Serialize a string-keyed mapping into JSON-compatible values."""
        if value is None:
            return {}
        serialized = {
            str(key): self.serialize_value(item) for key, item in value.items()
        }
        sanitized = self._security_engine.sanitize(serialized)
        if isinstance(sanitized, Mapping):
            return {str(key): item for key, item in sanitized.items()}
        return {}

    def serialize_value(self, value: object) -> JSONValue:
        """Serialize a Python object into a JSON-compatible value."""
        if value is None or isinstance(value, str | int | float | bool):
            return value
        if isinstance(value, datetime | date):
            return value.isoformat()
        if isinstance(value, Decimal | UUID | Path):
            return str(value)
        if isinstance(value, Enum):
            return self.serialize_value(value.value)
        if isinstance(value, BaseException):
            return self.serialize_exception(value)
        if is_dataclass(value) and not isinstance(value, type):
            return self.serialize_value(asdict(value))
        if isinstance(value, Mapping | MappingProxyType):
            return {str(key): self.serialize_value(item) for key, item in value.items()}
        if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
            return [self.serialize_value(item) for item in value]
        if isinstance(value, bytes | bytearray):
            return value.hex()
        return repr(value)

    def serialize_exception(self, exception: BaseException) -> Metadata:
        """Serialize an exception without changing exception propagation."""
        return {
            "type": type(exception).__name__,
            "module": type(exception).__module__,
            "message": str(exception),
        }


__all__ = ["EventSerializer"]
