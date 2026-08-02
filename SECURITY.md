# Security Policy

AgentReplay processes execution traces that may contain prompts, responses,
metadata, errors, and tool payloads. Treat traces as sensitive by default.

## Reporting Vulnerabilities

Please report vulnerabilities privately through GitHub Security Advisories:

https://github.com/ankitverma969/AgentReplay/security/advisories/new

Do not open public issues for suspected vulnerabilities.

## Supported Versions

Security fixes are provided for the latest released minor version.

## Security Expectations

- Do not commit real secrets, customer traces, API keys, or credentials.
- Prefer local storage and explicit exports.
- Redact sensitive payloads before sharing reports.
- Avoid unsafe deserialization in extensions.
- Validate filesystem paths before reading or writing user-provided paths.
