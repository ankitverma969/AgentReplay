"""Configuration adapters for AgentReplay security settings."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast

from agentreplay.security.models import (
    FindingKind,
    RedactionStrategy,
    RiskLevel,
    RuleFlags,
    SecurityConfig,
    SecurityRule,
)

if TYPE_CHECKING:
    from agentreplay.config import Settings

_STRATEGIES = frozenset(
    {"mask", "remove", "hash", "partial_mask", "placeholder", "custom"},
)


def security_config_from_settings(settings: Settings) -> SecurityConfig:
    """Build a security engine configuration from global settings."""
    return SecurityConfig(
        enabled=settings.redaction_enabled and settings.security_enabled,
        pii_enabled=settings.security_pii_enabled,
        strategy=settings.security_strategy,
        allowlist=settings.security_allowlist,
        denylist=settings.security_denylist,
        ignore_rules=settings.security_ignore_rules,
        custom_rules=settings.security_custom_rules,
        per_field_strategies=settings.security_per_field_strategies,
        hash_salt=settings.security_hash_salt,
    )


def parse_security_strategy(
    value: object,
    *,
    key: str,
    source: str,
) -> RedactionStrategy:
    """Parse a redaction strategy setting."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _STRATEGIES:
            return cast(RedactionStrategy, normalized)
    msg = f"Configuration key {key!r} from {source} must be a redaction strategy."
    raise ValueError(msg)


def parse_security_rules(
    value: object,
    *,
    key: str,
    source: str,
) -> tuple[SecurityRule, ...]:
    """Parse custom security regex rules from configuration data."""
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        msg = f"Configuration key {key!r} from {source} must be a list of tables."
        raise ValueError(msg)
    rules: list[SecurityRule] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            msg = f"Security rule {index} from {source} must be a table."
            raise ValueError(msg)
        rule = _parse_security_rule(item, source=source, index=index)
        rules.append(rule)
    return tuple(rules)


def parse_per_field_strategies(
    value: object,
    *,
    key: str,
    source: str,
) -> Mapping[str, RedactionStrategy]:
    """Parse field-specific redaction strategy configuration."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"Configuration key {key!r} from {source} must be a table."
        raise ValueError(msg)
    parsed: dict[str, RedactionStrategy] = {}
    for field_name, strategy in value.items():
        if not isinstance(field_name, str) or not field_name.strip():
            msg = f"Configuration key {key!r} from {source} has an invalid field."
            raise ValueError(msg)
        parsed[field_name.strip()] = parse_security_strategy(
            strategy,
            key=f"{key}.{field_name}",
            source=source,
        )
    return parsed


def _parse_security_rule(
    value: Mapping[object, object],
    *,
    source: str,
    index: int,
) -> SecurityRule:
    required = ("name", "pattern", "category")
    missing = [key for key in required if not isinstance(value.get(key), str)]
    if missing:
        msg = f"Security rule {index} from {source} is missing {', '.join(missing)}."
        raise ValueError(msg)
    strategy = value.get("strategy")
    parsed_strategy = (
        None
        if strategy is None
        else parse_security_strategy(strategy, key="strategy", source=source)
    )
    kind = str(value.get("kind", "secret")).strip().lower()
    if kind not in {"secret", "pii"}:
        msg = f"Security rule {index} from {source} has invalid kind."
        raise ValueError(msg)
    parsed_kind = cast(FindingKind, kind)
    risk = str(value.get("risk_level", "high")).strip().lower()
    if risk not in {"low", "medium", "high", "critical"}:
        msg = f"Security rule {index} from {source} has invalid risk_level."
        raise ValueError(msg)
    parsed_risk = cast(RiskLevel, risk)
    flags = value.get("flags", ())
    if isinstance(flags, str):
        parsed_flags = tuple(item.strip().lower() for item in flags.split(",") if item)
    elif isinstance(flags, list | tuple):
        parsed_flags = tuple(str(item).strip().lower() for item in flags if str(item))
    else:
        parsed_flags = ()
    valid_flags = {"ignorecase", "multiline", "dotall"}
    normalized_flags = tuple(flag for flag in parsed_flags if flag in valid_flags)
    return SecurityRule(
        name=str(value["name"]).strip(),
        pattern=str(value["pattern"]),
        category=str(value["category"]).strip(),
        kind=parsed_kind,
        risk_level=parsed_risk,
        description=str(value.get("description", "")),
        placeholder=(
            None if value.get("placeholder") is None else str(value["placeholder"])
        ),
        strategy=parsed_strategy,
        enabled=bool(value.get("enabled", True)),
        flags=cast(RuleFlags, normalized_flags),
    )


__all__ = [
    "parse_per_field_strategies",
    "parse_security_rules",
    "parse_security_strategy",
    "security_config_from_settings",
]
