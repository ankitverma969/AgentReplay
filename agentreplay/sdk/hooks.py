"""Public SDK hook system for extension lifecycle interception."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from threading import RLock

from agentreplay.sdk.models import SDKHookContext, SDKHookName, SDKHookResult
from agentreplay.types import Metadata

SDKHookHandler = Callable[[SDKHookContext], None]


class SDKHookManager:
    """Thread-safe hook manager for public extension lifecycle hooks."""

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        """Create an SDK hook manager."""
        self._handlers: defaultdict[
            SDKHookName,
            list[tuple[str, SDKHookHandler]],
        ] = defaultdict(list)
        self._lock = RLock()
        self._logger = (
            logging.getLogger("agentreplay.sdk.hooks") if logger is None else logger
        )

    def register(
        self,
        hook: SDKHookName,
        handler: SDKHookHandler,
        *,
        extension_name: str,
    ) -> None:
        """Register a hook handler for an extension."""
        with self._lock:
            self._handlers[hook].append((extension_name, handler))

    def emit(
        self,
        hook: SDKHookName,
        *,
        payload: Metadata | None = None,
    ) -> tuple[SDKHookResult, ...]:
        """Emit a hook and isolate extension failures."""
        with self._lock:
            handlers = tuple(self._handlers[hook])
        results: list[SDKHookResult] = []
        for extension_name, handler in handlers:
            context = SDKHookContext(
                hook=hook,
                payload=dict(payload or {}),
                extension_name=extension_name,
            )
            try:
                handler(context)
            except Exception as exc:
                self._logger.warning(
                    "AgentReplay SDK hook failed: %s.%s: %s",
                    extension_name,
                    hook,
                    exc,
                )
                results.append(
                    SDKHookResult(
                        hook=hook,
                        extension_name=extension_name,
                        succeeded=False,
                        error=str(exc),
                    )
                )
            else:
                results.append(
                    SDKHookResult(
                        hook=hook,
                        extension_name=extension_name,
                        succeeded=True,
                    )
                )
        return tuple(results)


__all__ = ["SDKHookHandler", "SDKHookManager"]
