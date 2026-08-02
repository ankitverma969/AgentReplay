"""Structured diff result models for AgentReplay executions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue

ChangeType: TypeAlias = Literal["added", "removed", "modified", "unchanged"]
DiffSeverity: TypeAlias = Literal["info", "low", "medium", "high", "critical"]


@dataclass(frozen=True, slots=True)
class DiffChange:
    """One observed difference between two recorded executions."""

    change_type: ChangeType
    category: str
    location: str
    severity: DiffSeverity
    description: str
    old_value: JSONValue
    new_value: JSONValue
    old_event_id: str | None = None
    new_event_id: str | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of this change."""
        return {
            "change_type": self.change_type,
            "category": self.category,
            "location": self.location,
            "severity": self.severity,
            "description": self.description,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "old_event_id": self.old_event_id,
            "new_event_id": self.new_event_id,
        }


@dataclass(frozen=True, slots=True)
class DiffStats:
    """Summary counts for a diff result."""

    added: int = 0
    removed: int = 0
    modified: int = 0
    unchanged: int = 0

    @property
    def changed(self) -> int:
        """Return the total number of non-unchanged items."""
        return self.added + self.removed + self.modified

    def to_dict(self) -> dict[str, int]:
        """Return summary counts as a dictionary."""
        return {
            "added": self.added,
            "removed": self.removed,
            "modified": self.modified,
            "unchanged": self.unchanged,
            "changed": self.changed,
        }


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Complete comparison result for two AgentReplay traces."""

    left_run_id: str
    right_run_id: str
    changes: tuple[DiffChange, ...]
    unchanged: int = 0
    warnings: tuple[str, ...] = ()

    @property
    def stats(self) -> DiffStats:
        """Return aggregate change counts."""
        counts = Counter(change.change_type for change in self.changes)
        return DiffStats(
            added=counts["added"],
            removed=counts["removed"],
            modified=counts["modified"],
            unchanged=self.unchanged,
        )

    @property
    def has_changes(self) -> bool:
        """Return whether the diff contains any changed item."""
        return self.stats.changed > 0

    def changes_by_severity(self, severity: DiffSeverity) -> tuple[DiffChange, ...]:
        """Return changes for one severity level."""
        return tuple(change for change in self.changes if change.severity == severity)

    def summary(self) -> str:
        """Return a compact human-readable summary."""
        stats = self.stats
        if stats.changed == 0:
            return (
                f"No differences found between {self.left_run_id} "
                f"and {self.right_run_id}."
            )
        return (
            f"{stats.changed} differences between {self.left_run_id} "
            f"and {self.right_run_id}: {stats.added} added, "
            f"{stats.removed} removed, {stats.modified} modified, "
            f"{stats.unchanged} unchanged."
        )

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible representation of this result."""
        return {
            "left_run_id": self.left_run_id,
            "right_run_id": self.right_run_id,
            "summary": self.summary(),
            "stats": self.stats.to_dict(),
            "warnings": list(self.warnings),
            "changes": [change.to_dict() for change in self.changes],
        }


def build_result(
    *,
    left_run_id: str,
    right_run_id: str,
    changes: Iterable[DiffChange],
    unchanged: int,
    warnings: Iterable[str] = (),
) -> DiffResult:
    """Build an immutable diff result from iterable inputs."""
    return DiffResult(
        left_run_id=left_run_id,
        right_run_id=right_run_id,
        changes=tuple(changes),
        unchanged=unchanged,
        warnings=tuple(warnings),
    )


__all__ = [
    "ChangeType",
    "DiffChange",
    "DiffResult",
    "DiffSeverity",
    "DiffStats",
    "build_result",
]
