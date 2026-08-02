"""Context-local session management for active AgentReplay runs."""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace

from agentreplay.exceptions import AgentReplayError


@dataclass(frozen=True, slots=True)
class ActiveSession:
    """Context-local active run and nested event stack."""

    run_id: str
    event_stack: tuple[str, ...] = ()


class SessionManager:
    """Manage active run and parent-event state for sync and async contexts."""

    def __init__(self) -> None:
        """Create an isolated session manager."""
        self._active_session: ContextVar[ActiveSession | None] = ContextVar(
            "agentreplay_active_session",
            default=None,
        )

    def active_run_id(self) -> str | None:
        """Return the run id active in the current context."""
        session = self._active_session.get()
        return None if session is None else session.run_id

    def active_parent_event_id(self) -> str | None:
        """Return the current parent event id for nested event recording."""
        session = self._active_session.get()
        if session is None or not session.event_stack:
            return None
        return session.event_stack[-1]

    def enter_run(self, run_id: str) -> Token[ActiveSession | None]:
        """Set the active run for the current context."""
        return self._active_session.set(ActiveSession(run_id=run_id))

    def exit_run(self, token: Token[ActiveSession | None]) -> None:
        """Restore the previous active run context."""
        self._active_session.reset(token)

    def push_event(self, event_id: str) -> Token[ActiveSession | None]:
        """Push a nested parent event for the current context."""
        session = self._active_session.get()
        if session is None:
            msg = "Cannot push an AgentReplay event without an active run."
            raise AgentReplayError(msg)
        next_session = replace(session, event_stack=(*session.event_stack, event_id))
        return self._active_session.set(next_session)

    def pop_event(self, token: Token[ActiveSession | None]) -> None:
        """Restore the previous nested event stack for the current context."""
        self._active_session.reset(token)


__all__ = ["ActiveSession", "SessionManager"]
