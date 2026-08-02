"""Security scanning, sanitization, and trace redaction engine."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace

from agentreplay.core.events import EventRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.security.models import (
    FieldRule,
    RedactionStrategy,
    SecurityConfig,
    SecurityFinding,
    SecurityReport,
    SecurityRule,
    finding_metadata,
)
from agentreplay.security.rules import DEFAULT_FIELD_RULES, default_rules
from agentreplay.types import JSONValue

_PLACEHOLDER = "[REDACTED]"


class SecurityEngine:
    """Detect and redact sensitive values in AgentReplay data."""

    def __init__(
        self,
        config: SecurityConfig | None = None,
        *,
        rules: Iterable[SecurityRule] | None = None,
        field_rules: Iterable[FieldRule] | None = None,
    ) -> None:
        """Create a security engine with compiled detection rules."""
        self.config = SecurityConfig() if config is None else config
        base_rules = default_rules(include_pii=self.config.pii_enabled)
        configured_rules = tuple(base_rules) + tuple(self.config.custom_rules)
        if rules is not None:
            configured_rules = tuple(rules)
        self._rules = tuple(
            _CompiledRule(rule)
            for rule in configured_rules
            if rule.enabled and not self._ignored(rule)
        )
        self._field_rules = tuple(
            rule
            for rule in (DEFAULT_FIELD_RULES if field_rules is None else field_rules)
            if rule.enabled and not self._ignored(rule)
        )
        self._allowlist = frozenset(self.config.allowlist)
        self._denylist = frozenset(
            _normalize_field(item) for item in self.config.denylist
        )

    def scan(
        self,
        value: JSONValue,
        *,
        source: str | None = None,
        include_preview: bool = True,
    ) -> SecurityReport:
        """Scan a JSON-compatible value and return detected findings."""
        if not self.config.enabled:
            return SecurityReport(findings=(), scanned_values=0, source=source)
        state = _ScanState()
        redacted = self.sanitize(value, findings=state.findings, state=state)
        return SecurityReport(
            findings=tuple(state.findings),
            scanned_values=state.scanned_values,
            redacted_preview=redacted if include_preview else None,
            source=source,
        )

    def verify(self, value: JSONValue, *, source: str | None = None) -> SecurityReport:
        """Scan a value without returning a redacted preview."""
        return self.scan(value, source=source, include_preview=False)

    def sanitize(
        self,
        value: JSONValue,
        *,
        findings: list[SecurityFinding] | None = None,
        state: _ScanState | None = None,
        path: str = "$",
    ) -> JSONValue:
        """Return a sanitized copy of a JSON-compatible value."""
        if not self.config.enabled:
            return value
        scan_state = _ScanState() if state is None else state
        if isinstance(value, Mapping):
            return {
                str(key): self._sanitize_mapping_value(
                    str(key),
                    item,
                    findings=findings,
                    state=scan_state,
                    path=f"{path}.{_escape_path(str(key))}",
                )
                for key, item in value.items()
            }
        if isinstance(value, Sequence) and not isinstance(
            value,
            str | bytes | bytearray,
        ):
            return [
                self.sanitize(
                    item,
                    findings=findings,
                    state=scan_state,
                    path=f"{path}[{index}]",
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, str):
            scan_state.scanned_values += 1
            return self._sanitize_string(
                value,
                findings=findings,
                state=scan_state,
                path=path,
            )
        scan_state.scanned_values += 1
        return value

    def sanitize_trace(self, trace: TraceSnapshot) -> TraceSnapshot:
        """Return a sanitized trace snapshot without mutating the input."""
        if not self.config.enabled:
            return trace
        run_findings: list[SecurityFinding] = []
        run_metadata = self.sanitize(
            dict(trace.run.metadata),
            findings=run_findings,
            path="$.run.metadata",
        )
        run = replace(
            trace.run,
            metadata={
                **_as_object_mapping(run_metadata),
                **finding_metadata(tuple(run_findings)),
            },
        )
        events = tuple(self.sanitize_event(event) for event in trace.events)
        return TraceSnapshot(run=run, events=events)

    def sanitize_event(self, event: EventRecord) -> EventRecord:
        """Return a sanitized event record without mutating the input."""
        if not self.config.enabled:
            return event
        findings: list[SecurityFinding] = []
        payload = self.sanitize(
            dict(event.payload),
            findings=findings,
            path=f"$.events[{event.sequence}].payload",
        )
        metadata = self.sanitize(
            dict(event.metadata),
            findings=findings,
            path=f"$.events[{event.sequence}].metadata",
        )
        return replace(
            event,
            payload=_as_object_mapping(payload),
            metadata={
                **_as_object_mapping(metadata),
                **finding_metadata(tuple(findings)),
            },
        )

    def rules(self) -> tuple[SecurityRule, ...]:
        """Return active regex detection rules."""
        return tuple(compiled.rule for compiled in self._rules)

    def field_rules(self) -> tuple[FieldRule, ...]:
        """Return active field-based redaction rules."""
        return self._field_rules

    def _sanitize_mapping_value(
        self,
        key: str,
        value: JSONValue,
        *,
        findings: list[SecurityFinding] | None,
        state: _ScanState,
        path: str,
    ) -> JSONValue:
        if self._is_allowed(path, key):
            return value
        field_rule = self._field_rule_for(path, key)
        if field_rule is None:
            return self.sanitize(value, findings=findings, state=state, path=path)
        state.scanned_values += 1
        text = _stringify(value)
        finding = self._field_finding(field_rule, text, path)
        _append_finding(finding, findings=findings, state=state)
        return self._redact_text(
            text,
            finding=finding,
            strategy=field_rule.strategy,
        )

    def _sanitize_string(
        self,
        value: str,
        *,
        findings: list[SecurityFinding] | None,
        state: _ScanState,
        path: str,
    ) -> str:
        if self._is_allowed(path, None):
            return value
        redacted = value
        matches: list[tuple[int, int, SecurityFinding, RedactionStrategy | None]] = []
        for rule in self._rules:
            for match in rule.finditer(value):
                if not self._valid_match(rule.rule, match.group(0)):
                    continue
                finding = self._regex_finding(rule.rule, match.group(0), path, match)
                matches.append(
                    (match.start(), match.end(), finding, rule.rule.strategy),
                )
        if not matches:
            return value
        matches.sort(key=lambda item: (item[0], item[1]))
        accepted: list[tuple[int, int, SecurityFinding, RedactionStrategy | None]] = []
        occupied_until = -1
        for start, end, finding, strategy in matches:
            if start < occupied_until:
                continue
            accepted.append((start, end, finding, strategy))
            occupied_until = end
        for start, end, finding, strategy in reversed(accepted):
            replacement = self._redact_text(
                value[start:end],
                finding=finding,
                strategy=strategy,
            )
            finding = replace(finding, redacted_text=replacement)
            _append_finding(finding, findings=findings, state=state)
            redacted = f"{redacted[:start]}{replacement}{redacted[end:]}"
        return redacted

    def _redact_text(
        self,
        value: str,
        *,
        finding: SecurityFinding,
        strategy: RedactionStrategy | None,
    ) -> str:
        selected = self._strategy_for(finding.path, finding.category, strategy)
        if selected == "remove":
            return ""
        if selected == "hash":
            digest = hashlib.sha256(
                f"{self.config.hash_salt}{value}".encode(),
            ).hexdigest()
            return f"sha256:{digest}"
        if selected == "partial_mask":
            return _partial_mask(value)
        if selected == "mask":
            return "*" * max(len(value), 8)
        if selected == "custom" and self.config.custom_redactor is not None:
            return self.config.custom_redactor(value, finding)
        return finding.redacted_text or _PLACEHOLDER

    def _strategy_for(
        self,
        path: str,
        category: str,
        override: RedactionStrategy | None,
    ) -> RedactionStrategy:
        for key in (path, _last_path_part(path), category):
            configured = self.config.per_field_strategies.get(key)
            if configured is not None:
                return configured
        if override is not None:
            return override
        return self.config.strategy

    def _field_rule_for(self, path: str, key: str) -> FieldRule | None:
        normalized_key = _normalize_field(key)
        if normalized_key in self._denylist:
            return FieldRule(
                name="denylist_field",
                fields=(key,),
                category="denylist",
                risk_level="critical",
                placeholder="[DENYLISTED FIELD REDACTED]",
            )
        for rule in self._field_rules:
            normalized_fields = {_normalize_field(field) for field in rule.fields}
            if normalized_key in normalized_fields or path in rule.fields:
                if rule.kind == "pii" and not self.config.pii_enabled:
                    return None
                return rule
        return None

    def _field_finding(
        self,
        rule: FieldRule,
        value: str,
        path: str,
    ) -> SecurityFinding:
        return SecurityFinding(
            rule_name=rule.name,
            category=rule.category,
            kind=rule.kind,
            risk_level=rule.risk_level,
            path=path,
            start=0,
            end=len(value),
            matched_text=value,
            redacted_text=rule.placeholder or _PLACEHOLDER,
            suggested_fix=_suggested_fix(rule.category),
        )

    def _regex_finding(
        self,
        rule: SecurityRule,
        value: str,
        path: str,
        match: re.Match[str],
    ) -> SecurityFinding:
        return SecurityFinding(
            rule_name=rule.name,
            category=rule.category,
            kind=rule.kind,
            risk_level=rule.risk_level,
            path=path,
            start=match.start(),
            end=match.end(),
            matched_text=value,
            redacted_text=rule.placeholder or _PLACEHOLDER,
            suggested_fix=_suggested_fix(rule.category),
        )

    def _is_allowed(self, path: str, key: str | None) -> bool:
        if path in self._allowlist:
            return True
        if key is not None and key in self._allowlist:
            return True
        return _last_path_part(path) in self._allowlist

    def _ignored(self, rule: SecurityRule | FieldRule) -> bool:
        ignored = set(self.config.ignore_rules)
        return rule.name in ignored or rule.category in ignored or rule.kind in ignored

    def _valid_match(self, rule: SecurityRule, value: str) -> bool:
        if rule.category == "credit_card":
            return _luhn_valid(value)
        if rule.category == "ip_address":
            return _valid_ip(value)
        return True


class _CompiledRule:
    """Compiled regular expression rule."""

    def __init__(self, rule: SecurityRule) -> None:
        self.rule = rule
        self.pattern = re.compile(rule.pattern, _regex_flags(rule))

    def finditer(self, value: str) -> Iterable[re.Match[str]]:
        """Return non-overlapping matches for the rule."""
        return self.pattern.finditer(value)


class _ScanState:
    """Mutable scan state shared during recursive traversal."""

    def __init__(self) -> None:
        self.findings: list[SecurityFinding] = []
        self.scanned_values = 0


def _append_finding(
    finding: SecurityFinding,
    *,
    findings: list[SecurityFinding] | None,
    state: _ScanState,
) -> None:
    if findings is not None and findings is not state.findings:
        findings.append(finding)
    state.findings.append(finding)


def _regex_flags(rule: SecurityRule) -> int:
    flags = 0
    if "ignorecase" in rule.flags:
        flags |= re.IGNORECASE
    if "multiline" in rule.flags:
        flags |= re.MULTILINE
    if "dotall" in rule.flags:
        flags |= re.DOTALL
    return flags


def _partial_mask(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(len(value) - 8, 4)}{value[-4:]}"


def _stringify(value: JSONValue) -> str:
    if isinstance(value, str):
        return value
    return repr(value)


def _escape_path(value: str) -> str:
    return value.replace("\\", "\\\\").replace(".", "\\.")


def _last_path_part(path: str) -> str:
    return _normalize_field(path.rsplit(".", 1)[-1].replace("\\.", "."))


def _normalize_field(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _suggested_fix(category: str) -> str:
    return f"Remove or rotate the exposed {category.replace('_', ' ')}."


def _valid_ip(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 4 and all(
        part.isdigit() and 0 <= int(part) <= 255 for part in parts
    )


def _luhn_valid(value: str) -> bool:
    digits = [int(char) for char in value if char.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def _as_object_mapping(value: JSONValue) -> dict[str, JSONValue]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


__all__ = ["SecurityEngine"]
