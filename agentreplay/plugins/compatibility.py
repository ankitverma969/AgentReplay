"""Version compatibility checks for AgentReplay plugins."""

from __future__ import annotations

from itertools import zip_longest

from agentreplay.exceptions import PluginError


def ensure_agentreplay_compatible(
    *,
    plugin_name: str,
    agentreplay_version: str,
    min_version: str | None,
    max_version: str | None,
) -> None:
    """Raise when a plugin does not support this AgentReplay version."""
    if (
        min_version is not None
        and _compare_versions(agentreplay_version, min_version) < 0
    ):
        msg = (
            f"Plugin {plugin_name!r} requires AgentReplay >= {min_version}; "
            f"current version is {agentreplay_version}."
        )
        raise PluginError(msg)
    if (
        max_version is not None
        and _compare_versions(agentreplay_version, max_version) > 0
    ):
        msg = (
            f"Plugin {plugin_name!r} requires AgentReplay <= {max_version}; "
            f"current version is {agentreplay_version}."
        )
        raise PluginError(msg)


def satisfies_version_constraint(version: str, constraint: str | None) -> bool:
    """Return whether a version satisfies a small dependency constraint syntax."""
    if constraint is None or not constraint.strip():
        return True
    for raw_part in constraint.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if part.startswith(">=") and _compare_versions(version, part[2:].strip()) < 0:
            return False
        if part.startswith("<=") and _compare_versions(version, part[2:].strip()) > 0:
            return False
        if part.startswith(">") and _compare_versions(version, part[1:].strip()) <= 0:
            return False
        if part.startswith("<") and _compare_versions(version, part[1:].strip()) >= 0:
            return False
        if part.startswith("==") and _compare_versions(version, part[2:].strip()) != 0:
            return False
        if part[0].isdigit() and _compare_versions(version, part) != 0:
            return False
    return True


def _compare_versions(left: str, right: str) -> int:
    """Compare two dotted numeric versions without external dependencies."""
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    for left_part, right_part in zip_longest(left_parts, right_parts, fillvalue=0):
        if left_part < right_part:
            return -1
        if left_part > right_part:
            return 1
    return 0


def _version_parts(version: str) -> tuple[int, ...]:
    """Return numeric version parts, ignoring suffixes such as ``rc1``."""
    parts: list[int] = []
    for raw_part in version.replace("-", ".").split("."):
        digits = ""
        for char in raw_part:
            if not char.isdigit():
                break
            digits += char
        if digits:
            parts.append(int(digits))
    return tuple(parts) or (0,)


__all__ = ["ensure_agentreplay_compatible", "satisfies_version_constraint"]
