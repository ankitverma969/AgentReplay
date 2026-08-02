from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentreplay import Recorder, SecurityConfig, SecurityEngine
from agentreplay.cli.main import main
from agentreplay.config import load_settings
from agentreplay.plugins import AgentReplayPlugin, PluginApp
from agentreplay.security.models import SecurityRule


def test_security_engine_redacts_common_secrets_and_pii() -> None:
    engine = SecurityEngine()
    payload = {
        "prompt": (
            "key sk-abcdefghijklmnopqrstuvwxyz123456 "
            "email dev@example.com "
            "auth Bearer abcdefghijklmnopqrstuvwxyz123456"
        ),
    }

    report = engine.scan(payload)

    assert report.secrets_found == 2
    assert report.pii_found == 1
    assert report.risk_level == "critical"
    redacted = report.redacted_preview
    assert isinstance(redacted, dict)
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in str(redacted)
    assert "dev@example.com" not in str(redacted)
    assert "Bearer abcdefghijklmnopqrstuvwxyz123456" not in str(redacted)


def test_security_engine_supports_redaction_strategies() -> None:
    engine = SecurityEngine(SecurityConfig(strategy="hash", hash_salt="salt"))

    sanitized = engine.sanitize({"token": "sk-abcdefghijklmnopqrstuvwxyz123456"})

    assert isinstance(sanitized, dict)
    assert str(sanitized["token"]).startswith("sha256:")


def test_security_engine_supports_custom_rules_and_allowlist() -> None:
    rule = SecurityRule(
        name="internal_ticket",
        pattern=r"INT-[0-9]{6}",
        category="ticket",
        risk_level="medium",
        placeholder="[TICKET REDACTED]",
    )
    engine = SecurityEngine(
        SecurityConfig(
            custom_rules=(rule,),
            allowlist=("public_note",),
        ),
    )

    sanitized = engine.sanitize(
        {
            "private_note": "case INT-123456",
            "public_note": "case INT-654321",
        },
    )

    assert isinstance(sanitized, dict)
    assert sanitized["private_note"] == "case [TICKET REDACTED]"
    assert sanitized["public_note"] == "case INT-654321"


def test_security_engine_can_disable_pii_detection() -> None:
    engine = SecurityEngine(SecurityConfig(pii_enabled=False))

    report = engine.scan({"email": "dev@example.com"})

    assert report.pii_found == 0


def test_credit_card_detection_uses_luhn_to_reduce_false_positives() -> None:
    engine = SecurityEngine()

    report = engine.scan({"text": "reference 1234 5678 9012 3456"})

    assert not any(finding.category == "credit_card" for finding in report.findings)


def test_recorder_sanitizes_before_events_are_kept_in_memory() -> None:
    with Recorder(name="security") as recorder:
        recorder.user_prompt("use sk-abcdefghijklmnopqrstuvwxyz123456")
        recorder.tool_started(
            "lookup",
            arguments={"authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
        )

    trace = recorder.trace()
    rendered = json.dumps(trace.to_dict(), sort_keys=True)

    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in rendered
    assert "Bearer abcdefghijklmnopqrstuvwxyz123456" not in rendered
    assert "[OPENAI KEY REDACTED]" in rendered
    assert "[SENSITIVE FIELD REDACTED]" in rendered


def test_security_settings_load_from_environment() -> None:
    settings = load_settings(
        environ={
            "AGENTREPLAY_SECURITY_ENABLED": "false",
            "AGENTREPLAY_SECURITY_PII_ENABLED": "false",
            "AGENTREPLAY_SECURITY_STRATEGY": "partial_mask",
            "AGENTREPLAY_SECURITY_ALLOWLIST": "safe",
            "AGENTREPLAY_SECURITY_DENYLIST": "unsafe",
            "AGENTREPLAY_SECURITY_IGNORE_RULES": "email_address",
            "AGENTREPLAY_SECURITY_HASH_SALT": "pepper",
        },
    )

    assert settings.security_enabled is False
    assert settings.security_pii_enabled is False
    assert settings.security_strategy == "partial_mask"
    assert settings.security_allowlist == ("safe",)
    assert settings.security_denylist == ("unsafe",)
    assert settings.security_ignore_rules == ("email_address",)
    assert settings.security_hash_salt == "pepper"


def test_security_settings_load_from_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text(
        "\n".join(
            [
                "[security]",
                "enabled = true",
                "pii_enabled = false",
                'strategy = "mask"',
                'allowlist = ["public"]',
                'denylist = ["private"]',
                "",
                "[[security.custom_rules]]",
                'name = "ticket"',
                'pattern = "TICKET-[0-9]+"',
                'category = "ticket"',
            ],
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_file, environ={})

    assert settings.security_enabled is True
    assert settings.security_pii_enabled is False
    assert settings.security_strategy == "mask"
    assert settings.security_allowlist == ("public",)
    assert settings.security_denylist == ("private",)
    assert settings.security_custom_rules[0].name == "ticket"


def test_security_cli_scans_json_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(
        json.dumps({"payload": "sk-abcdefghijklmnopqrstuvwxyz123456"}),
        encoding="utf-8",
    )

    exit_code = main(["security", "scan", str(trace_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "secrets=1" in captured.out
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in captured.out


def test_security_cli_verify_fails_when_findings_exist(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace_file = tmp_path / "trace.json"
    trace_file.write_text(
        json.dumps({"payload": "Bearer abcdefghijklmnopqrstuvwxyz123456"}),
        encoding="utf-8",
    )

    exit_code = main(["security", "verify", str(trace_file)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "failed" in captured.out


def test_security_cli_scans_text_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trace_file = tmp_path / "trace.md"
    trace_file.write_text(
        "token sk-abcdefghijklmnopqrstuvwxyz123456",
        encoding="utf-8",
    )

    exit_code = main(["security", "scan", str(trace_file)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "secrets=1" in captured.out


def test_plugin_app_accepts_security_registrations() -> None:
    class Detector:
        def scan(self, value: object) -> object:
            return value

    class SecurityPlugin(AgentReplayPlugin):
        name = "security-plugin"
        version = "1.0.0"

        def register(self, app: object) -> None:
            plugin_app = app
            assert isinstance(plugin_app, PluginApp)
            plugin_app.register_secret_detector("secret", Detector())
            plugin_app.register_pii_detector("pii", Detector())
            plugin_app.register_redaction_rule(
                "rule",
                SecurityRule(
                    name="custom",
                    pattern="CUSTOM",
                    category="custom",
                ),
            )

    app = PluginApp()
    app.activate("security-plugin", {})
    SecurityPlugin().register(app)
    app.deactivate()

    kinds = {registration.kind for registration in app.registrations()}
    assert kinds == {"secret_detector", "pii_detector", "redaction_rule"}


def test_security_engine_scans_large_event_sets() -> None:
    engine = SecurityEngine()
    payload = {
        "events": [{"payload": f"event {index}"} for index in range(100_000)],
    }

    report = engine.verify(payload)

    assert report.verify()
    assert report.scanned_values == 100_000
