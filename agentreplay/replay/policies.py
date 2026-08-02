"""Replay policies, status values, and validation helpers."""

from __future__ import annotations

from typing import Final, Literal, TypeAlias

PlaybackSpeed: TypeAlias = float
ReplayStatus: TypeAlias = Literal[
    "idle",
    "loaded",
    "playing",
    "paused",
    "stopped",
    "completed",
]

ALLOWED_PLAYBACK_SPEEDS: Final[tuple[PlaybackSpeed, ...]] = (0.25, 0.5, 1.0, 2.0, 4.0)


def validate_playback_speed(speed: float) -> PlaybackSpeed:
    """Validate and normalize a replay playback speed."""
    for allowed_speed in ALLOWED_PLAYBACK_SPEEDS:
        if speed == allowed_speed:
            return allowed_speed
    allowed = ", ".join(f"{value:g}x" for value in ALLOWED_PLAYBACK_SPEEDS)
    msg = f"Unsupported replay speed {speed:g}x. Expected one of: {allowed}."
    raise ValueError(msg)


__all__ = [
    "ALLOWED_PLAYBACK_SPEEDS",
    "PlaybackSpeed",
    "ReplayStatus",
    "validate_playback_speed",
]
