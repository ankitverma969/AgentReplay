"""Typed public SDK event bus."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock

from agentreplay.sdk.models import SDKEvent, SDKEventName
from agentreplay.types import Metadata

SDKEventHandler = Callable[[SDKEvent], None]


class SDKEventBus:
    """Thread-safe event bus used by AgentReplay SDK extensions."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        """Create an SDK event bus."""
        self._handlers: defaultdict[SDKEventName, list[SDKEventHandler]] = defaultdict(
            list
        )
        self._lock = RLock()
        self._logger = (
            logging.getLogger("agentreplay.sdk.events") if logger is None else logger
        )

    def subscribe(self, event_name: SDKEventName, handler: SDKEventHandler) -> None:
        """Subscribe a handler to an SDK event."""
        with self._lock:
            self._handlers[event_name].append(handler)

    def unsubscribe(self, event_name: SDKEventName, handler: SDKEventHandler) -> None:
        """Remove a previously registered handler."""
        with self._lock:
            self._handlers[event_name] = [
                registered
                for registered in self._handlers[event_name]
                if registered is not handler
            ]

    def publish(
        self,
        event_name: SDKEventName,
        *,
        payload: Metadata | None = None,
        source: str = "agentreplay",
    ) -> SDKEvent:
        """Publish an event and isolate subscriber failures."""
        event = SDKEvent(name=event_name, payload=dict(payload or {}), source=source)
        with self._lock:
            handlers = tuple(self._handlers[event_name])
        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                self._logger.warning(
                    "AgentReplay SDK event handler failed for %s: %s",
                    event_name,
                    exc,
                )
        return event

    def subscribers(self, event_name: SDKEventName) -> int:
        """Return subscriber count for one event."""
        with self._lock:
            return len(self._handlers[event_name])


__all__ = ["SDKEventBus", "SDKEventHandler"]
