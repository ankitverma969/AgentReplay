# AgentReplay Security and Redaction

AgentReplay includes an enterprise security subsystem that detects and redacts
sensitive data before traces are stored, exported, replayed, diffed, or shown by
the CLI.

The subsystem is local, dependency-free, and framework-agnostic. It does not
call external services and does not require an API key.

## What It Protects

The default rules detect common secrets and PII, including:

- OpenAI, Anthropic, Gemini, Azure, AWS, GitHub, GitLab, Slack, Discord, and
  Stripe tokens
- Bearer tokens, JWTs, OAuth tokens, cookies, and session IDs
- Database URLs and connection strings
- Private keys and SSH keys
- Email addresses and phone numbers
- Credit card numbers with Luhn validation
- PAN, Aadhaar, passport, vehicle, IP, and MAC values
- Date-of-birth strings when they appear with DOB context
- Sensitive field names such as `api_key`, `authorization`, `password`, and
  `private_key`
- Custom regex rules from Python or TOML configuration

## Recording Pipeline

Recorder payloads and metadata are sanitized at the serialization boundary. This
means sensitive values are redacted before events are retained in memory or
written to storage.

```python
from agentreplay import Recorder

with Recorder(name="secure-agent") as recorder:
    recorder.user_prompt("use sk-abcdefghijklmnopqrstuvwxyz123456")

trace = recorder.trace()
```

The trace will contain `[OPENAI KEY REDACTED]` instead of the original key.

## Export Safety

The export command sanitizes traces before rendering JSON, Markdown, or HTML.
This also protects older traces that may have been recorded before security
redaction was enabled.

```bash
agentreplay export RUN_ID --json
agentreplay export RUN_ID --markdown
agentreplay export RUN_ID --html --output run.html
```

Replay and diff rendering also sanitize loaded trace data before display.

## Python API

```python
from agentreplay import SecurityEngine

engine = SecurityEngine()
report = engine.scan(
    {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456",
        "email": "dev@example.com",
    },
)

print(report.summary())
print(report.redacted_preview)
```

Verify that no sensitive data remains:

```python
report = engine.verify({"prompt": "hello"})
assert report.verify()
```

Sanitize an arbitrary JSON-compatible object:

```python
safe_payload = engine.sanitize({"api_key": "sk-abcdefghijklmnopqrstuvwxyz123456"})
```

## Redaction Strategies

AgentReplay supports these strategies:

- `placeholder`: replace with a category-specific placeholder
- `mask`: replace the entire value with asterisks
- `partial_mask`: keep a small prefix and suffix
- `hash`: replace with a SHA256 digest
- `remove`: replace with an empty string
- `custom`: call a Python redaction function

```python
from agentreplay import SecurityConfig, SecurityEngine

engine = SecurityEngine(
    SecurityConfig(strategy="hash", hash_salt="deployment-specific-salt"),
)
```

## Configuration

Security can be configured through Python:

```python
from agentreplay import configure

configure(
    security_enabled=True,
    security_pii_enabled=True,
    security_strategy="placeholder",
    security_allowlist=("public_note",),
    security_denylist=("raw_secret",),
    security_ignore_rules=("ip_address",),
)
```

Environment variables:

```bash
AGENTREPLAY_SECURITY_ENABLED=true
AGENTREPLAY_SECURITY_PII_ENABLED=true
AGENTREPLAY_SECURITY_STRATEGY=placeholder
AGENTREPLAY_SECURITY_ALLOWLIST=public_note
AGENTREPLAY_SECURITY_DENYLIST=raw_secret
AGENTREPLAY_SECURITY_IGNORE_RULES=ip_address
AGENTREPLAY_SECURITY_HASH_SALT=local-salt
```

TOML:

```toml
[security]
enabled = true
pii_enabled = true
strategy = "placeholder"
allowlist = ["public_note"]
denylist = ["raw_secret"]
ignore_rules = ["ip_address"]
hash_salt = "local-salt"

[[security.custom_rules]]
name = "internal_ticket"
pattern = "INT-[0-9]{6}"
category = "ticket"
risk_level = "medium"
placeholder = "[TICKET REDACTED]"
```

## CLI

Scan a trace file, run ID, or `latest`:

```bash
agentreplay security scan exported-run.json
agentreplay security scan RUN_ID --db-path .agentreplay/agentreplay.sqlite
agentreplay security scan latest
```

Verify that a trace contains no detected secrets or PII:

```bash
agentreplay security verify exported-run.json
```

`verify` exits with:

- `0` when no findings are detected
- `2` when findings are detected
- `1` when the command cannot read or scan the trace

Render detailed reports:

```bash
agentreplay security report RUN_ID --markdown
agentreplay security report RUN_ID --html
agentreplay security report RUN_ID --json
```

List active rules:

```bash
agentreplay security rules
agentreplay security rules --json
```

## Plugin Support

Plugins can register security-related capabilities through `PluginApp`:

```python
from agentreplay.plugins import AgentReplayPlugin, PluginApp
from agentreplay.security import SecurityRule


class CompanySecurityPlugin(AgentReplayPlugin):
    name = "company-security"
    version = "1.0.0"

    def register(self, app: object) -> None:
        assert isinstance(app, PluginApp)
        app.register_redaction_rule(
            "internal-ticket",
            SecurityRule(
                name="internal_ticket",
                pattern="INT-[0-9]{6}",
                category="ticket",
                risk_level="medium",
            ),
        )
```

Plugins may also register secret detectors and PII detectors.

## Best Practices

- Keep security redaction enabled in development and CI.
- Use `security verify` before sharing exported traces.
- Prefer placeholders for debugging and hashes for correlation workflows.
- Use `allowlist` sparingly and only for fields known to be safe.
- Add organization-specific custom regex rules for internal token formats.
- Rotate any secret that appears in an unsanitized trace.
- Do not commit `.agentreplay` databases or exported traces containing private
  execution data.
- Treat traces as sensitive operational data even after redaction.

## Compliance Notes

AgentReplay provides configurable redaction and detection primitives, but it is
not by itself a compliance program. Teams using AgentReplay in regulated
environments should define data retention, access control, audit, review, and
incident response policies around stored traces and exports.

Recommended controls:

- store trace databases in restricted local or internal locations
- review custom rules for regional identifiers
- enforce export verification in CI or release workflows
- document retention periods
- restrict plugin installation to trusted packages
- periodically test false positives and false negatives against representative
  internal traces
