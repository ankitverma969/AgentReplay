"""Typed models for AgentReplay security scanning and redaction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

from agentreplay.types import JSONValue, Metadata

FindingKind: TypeAlias = Literal["secret", "pii"]
RiskLevel: TypeAlias = Literal["low", "medium", "high", "critical"]
RedactionStrategy: TypeAlias = Literal[
    "mask",
    "remove",
    "hash",
    "partial_mask",
    "placeholder",
    "custom",
]

RuleFlags: TypeAlias = tuple[Literal["ignorecase", "multiline", "dotall"], ...]
CustomRedactor: TypeAlias = Callable[[str, "SecurityFinding"], str]


@dataclass(frozen=True, slots=True)
class SecurityRule:
    """Declarative sensitive-data detection rule."""

    name: str
    pattern: str
    category: str
    kind: FindingKind = "secret"
    risk_level: RiskLevel = "high"
    description: str = ""
    placeholder: str | None = None
    strategy: RedactionStrategy | None = None
    enabled: bool = True
    flags: RuleFlags = ()


@dataclass(frozen=True, slots=True)
class FieldRule:
    """Rule that redacts a value based on a field name or path."""

    name: str
    fields: tuple[str, ...]
    category: str
    kind: FindingKind = "secret"
    risk_level: RiskLevel = "high"
    placeholder: str | None = None
    strategy: RedactionStrategy | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class SecurityConfig:
    """Runtime configuration for security scanning and redaction."""

    enabled: bool = True
    pii_enabled: bool = True
    strategy: RedactionStrategy = "placeholder"
    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()
    ignore_rules: tuple[str, ...] = ()
    custom_rules: tuple[SecurityRule, ...] = ()
    per_field_strategies: Mapping[str, RedactionStrategy] = field(
        default_factory=dict,
    )
    custom_redactor: CustomRedactor | None = None
    hash_salt: str = ""


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    """One detected secret or PII occurrence."""

    rule_name: str
    category: str
    kind: FindingKind
    risk_level: RiskLevel
    path: str
    start: int
    end: int
    matched_text: str
    redacted_text: str
    suggested_fix: str

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible finding representation."""
        return {
            "rule_name": self.rule_name,
            "category": self.category,
            "kind": self.kind,
            "risk_level": self.risk_level,
            "path": self.path,
            "start": self.start,
            "end": self.end,
            "matched_preview": preview_secret(self.matched_text),
            "redacted_preview": self.redacted_text,
            "suggested_fix": self.suggested_fix,
        }


@dataclass(frozen=True, slots=True)
class SecurityReport:
    """Aggregated result of scanning one trace or JSON-like object."""

    findings: tuple[SecurityFinding, ...]
    scanned_values: int
    redacted_preview: JSONValue | None = None
    source: str | None = None

    @property
    def secrets_found(self) -> int:
        """Return the number of secret findings."""
        return sum(1 for finding in self.findings if finding.kind == "secret")

    @property
    def pii_found(self) -> int:
        """Return the number of PII findings."""
        return sum(1 for finding in self.findings if finding.kind == "pii")

    @property
    def risk_level(self) -> RiskLevel:
        """Return the highest risk level present in the report."""
        order: Mapping[RiskLevel, int] = {
            "low": 0,
            "medium": 1,
            "high": 2,
            "critical": 3,
        }
        if not self.findings:
            return "low"
        return max(
            (finding.risk_level for finding in self.findings),
            key=lambda risk: order[risk],
        )

    def verify(self) -> bool:
        """Return whether no sensitive data was detected."""
        return not self.findings

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible report representation."""
        return {
            "source": self.source,
            "risk_level": self.risk_level,
            "secrets_found": self.secrets_found,
            "pii_found": self.pii_found,
            "scanned_values": self.scanned_values,
            "findings": [finding.to_dict() for finding in self.findings],
            "redacted_preview": self.redacted_preview,
        }

    def summary(self) -> str:
        """Return a compact human-readable summary."""
        return (
            f"risk={self.risk_level} "
            f"secrets={self.secrets_found} "
            f"pii={self.pii_found} "
            f"findings={len(self.findings)}"
        )


def preview_secret(value: str) -> str:
    """Return a safe preview of a sensitive matched value."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def finding_metadata(findings: tuple[SecurityFinding, ...]) -> Metadata:
    """Return compact metadata describing redaction findings."""
    if not findings:
        return {}
    categories = sorted({finding.category for finding in findings})
    return {
        "agentreplay.security.redacted": True,
        "agentreplay.security.findings": len(findings),
        "agentreplay.security.categories": categories,
    }


__all__ = [
    "CustomRedactor",
    "FieldRule",
    "FindingKind",
    "RedactionStrategy",
    "RiskLevel",
    "RuleFlags",
    "SecurityConfig",
    "SecurityFinding",
    "SecurityReport",
    "SecurityRule",
    "finding_metadata",
    "preview_secret",
]
