"""Built-in detection rules for AgentReplay security scanning."""

from __future__ import annotations

from agentreplay.security.models import FieldRule, SecurityRule

DEFAULT_SECRET_RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        name="anthropic_api_key",
        pattern=r"\bsk-ant-[A-Za-z0-9_-]{20,}\b",
        category="anthropic_key",
        risk_level="critical",
        placeholder="[ANTHROPIC KEY REDACTED]",
    ),
    SecurityRule(
        name="openai_api_key",
        pattern=r"\bsk-(?!ant-)[A-Za-z0-9_-]{20,}\b",
        category="openai_key",
        risk_level="critical",
        placeholder="[OPENAI KEY REDACTED]",
    ),
    SecurityRule(
        name="gemini_api_key",
        pattern=r"\bAIza[0-9A-Za-z_-]{20,}\b",
        category="gemini_key",
        risk_level="critical",
        placeholder="[GEMINI KEY REDACTED]",
    ),
    SecurityRule(
        name="azure_key",
        pattern=r"\b(?:azure|api)[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{20,}",
        category="azure_key",
        risk_level="critical",
        placeholder="[AZURE KEY REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="aws_access_key",
        pattern=r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
        category="aws_access_key",
        risk_level="critical",
        placeholder="[AWS ACCESS KEY REDACTED]",
    ),
    SecurityRule(
        name="aws_secret_key",
        pattern=(
            r"\baws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*"
            r"['\"]?[A-Za-z0-9/+=]{40}\b"
        ),
        category="aws_secret_key",
        risk_level="critical",
        placeholder="[AWS SECRET KEY REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="bearer_token",
        pattern=r"\bBearer\s+[A-Za-z0-9._~+/\-=]{16,}",
        category="bearer_token",
        risk_level="critical",
        placeholder="[BEARER TOKEN REDACTED]",
    ),
    SecurityRule(
        name="jwt_token",
        pattern=(
            r"\beyJ[A-Za-z0-9_-]{8,}\."
            r"[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
        ),
        category="jwt",
        risk_level="critical",
        placeholder="[JWT REDACTED]",
    ),
    SecurityRule(
        name="oauth_token",
        pattern=(
            r"\b(?:oauth|access[_-]?token|refresh[_-]?token)\s*[:=]\s*"
            r"['\"]?[A-Za-z0-9._~+/\-=]{16,}"
        ),
        category="oauth_token",
        risk_level="critical",
        placeholder="[OAUTH TOKEN REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="github_token",
        pattern=r"\b(?:gh[pousr]_[A-Za-z0-9_]{30,}|github_pat_[A-Za-z0-9_]{20,})\b",
        category="github_token",
        risk_level="critical",
        placeholder="[GITHUB TOKEN REDACTED]",
    ),
    SecurityRule(
        name="gitlab_token",
        pattern=r"\bglpat-[A-Za-z0-9_-]{20,}\b",
        category="gitlab_token",
        risk_level="critical",
        placeholder="[GITLAB TOKEN REDACTED]",
    ),
    SecurityRule(
        name="slack_token",
        pattern=r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b",
        category="slack_token",
        risk_level="critical",
        placeholder="[SLACK TOKEN REDACTED]",
    ),
    SecurityRule(
        name="discord_token",
        pattern=r"\b(?:mfa\.[A-Za-z0-9_-]{20,}|[A-Za-z0-9_-]{24}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27})\b",
        category="discord_token",
        risk_level="critical",
        placeholder="[DISCORD TOKEN REDACTED]",
    ),
    SecurityRule(
        name="stripe_key",
        pattern=r"\b(?:sk|pk|rk)_(?:live|test)_[A-Za-z0-9]{16,}\b",
        category="stripe_key",
        risk_level="critical",
        placeholder="[STRIPE KEY REDACTED]",
    ),
    SecurityRule(
        name="database_url",
        pattern=r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s'\"<>]+",
        category="database_url",
        risk_level="critical",
        placeholder="[DATABASE URL REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="connection_string",
        pattern=r"\b(?:Server|Data Source|Host)=([^;\n]+;){2,}[^;\n]+",
        category="connection_string",
        risk_level="critical",
        placeholder="[CONNECTION STRING REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="private_key",
        pattern=(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
            r"-----END [A-Z ]*PRIVATE KEY-----"
        ),
        category="private_key",
        risk_level="critical",
        placeholder="[PRIVATE KEY REDACTED]",
        flags=("dotall",),
    ),
    SecurityRule(
        name="ssh_public_key",
        pattern=r"\bssh-(?:rsa|ed25519)\s+[A-Za-z0-9+/=]{40,}",
        category="ssh_key",
        risk_level="high",
        placeholder="[SSH KEY REDACTED]",
    ),
    SecurityRule(
        name="cookie",
        pattern=r"\b(?:cookie|set-cookie)\s*[:=]\s*[^;\n]{8,}",
        category="cookie",
        risk_level="high",
        placeholder="[COOKIE REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="session_id",
        pattern=r"\b(?:sessionid|session_id|sid)\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}",
        category="session_id",
        risk_level="high",
        placeholder="[SESSION ID REDACTED]",
        flags=("ignorecase",),
    ),
)

DEFAULT_PII_RULES: tuple[SecurityRule, ...] = (
    SecurityRule(
        name="email_address",
        pattern=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        category="email",
        kind="pii",
        risk_level="medium",
        placeholder="[EMAIL REDACTED]",
    ),
    SecurityRule(
        name="phone_number",
        pattern=r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b",
        category="phone",
        kind="pii",
        risk_level="medium",
        placeholder="[PHONE REDACTED]",
    ),
    SecurityRule(
        name="credit_card_number",
        pattern=r"\b(?:\d[ -]*?){13,19}\b",
        category="credit_card",
        kind="pii",
        risk_level="critical",
        placeholder="[CREDIT CARD REDACTED]",
    ),
    SecurityRule(
        name="pan_number",
        pattern=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
        category="pan",
        kind="pii",
        risk_level="high",
        placeholder="[PAN REDACTED]",
    ),
    SecurityRule(
        name="aadhaar_number",
        pattern=r"\b[2-9][0-9]{3}\s?[0-9]{4}\s?[0-9]{4}\b",
        category="aadhaar",
        kind="pii",
        risk_level="high",
        placeholder="[AADHAAR REDACTED]",
    ),
    SecurityRule(
        name="passport_number",
        pattern=r"\b[A-Z][0-9]{7}\b",
        category="passport",
        kind="pii",
        risk_level="high",
        placeholder="[PASSPORT REDACTED]",
    ),
    SecurityRule(
        name="ip_address",
        pattern=r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        category="ip_address",
        kind="pii",
        risk_level="low",
        placeholder="[IP REDACTED]",
    ),
    SecurityRule(
        name="mac_address",
        pattern=r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b",
        category="mac_address",
        kind="pii",
        risk_level="low",
        placeholder="[MAC REDACTED]",
    ),
    SecurityRule(
        name="date_of_birth",
        pattern=r"\b(?:dob|date of birth)\s*[:=]\s*\d{4}-\d{2}-\d{2}\b",
        category="date_of_birth",
        kind="pii",
        risk_level="medium",
        placeholder="[DATE OF BIRTH REDACTED]",
        flags=("ignorecase",),
    ),
    SecurityRule(
        name="vehicle_number",
        pattern=r"\b[A-Z]{2}[ -]?[0-9]{1,2}[ -]?[A-Z]{1,3}[ -]?[0-9]{4}\b",
        category="vehicle_number",
        kind="pii",
        risk_level="medium",
        placeholder="[VEHICLE NUMBER REDACTED]",
    ),
)

DEFAULT_FIELD_RULES: tuple[FieldRule, ...] = (
    FieldRule(
        name="secret_field",
        fields=(
            "api_key",
            "apikey",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "authorization",
            "password",
            "private_key",
            "connection_string",
            "database_url",
            "cookie",
            "session",
            "session_id",
        ),
        category="sensitive_field",
        risk_level="critical",
        placeholder="[SENSITIVE FIELD REDACTED]",
    ),
    FieldRule(
        name="pii_field",
        fields=(
            "email",
            "phone",
            "dob",
            "date_of_birth",
            "address",
            "national_id",
            "passport",
            "aadhaar",
            "pan",
            "vehicle_number",
        ),
        category="pii_field",
        kind="pii",
        risk_level="medium",
        placeholder="[PII FIELD REDACTED]",
    ),
)


def default_rules(*, include_pii: bool = True) -> tuple[SecurityRule, ...]:
    """Return enabled built-in regex rules."""
    if include_pii:
        return DEFAULT_SECRET_RULES + DEFAULT_PII_RULES
    return DEFAULT_SECRET_RULES


__all__ = [
    "DEFAULT_FIELD_RULES",
    "DEFAULT_PII_RULES",
    "DEFAULT_SECRET_RULES",
    "default_rules",
]
