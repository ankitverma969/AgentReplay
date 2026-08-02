from __future__ import annotations

import json
from pathlib import Path

import pytest
from agentreplay import (
    CorrelationContext,
    ObservabilityConfig,
    ObservabilityEngine,
    Recorder,
)
from agentreplay.cli.main import main
from agentreplay.config import load_settings
from agentreplay.core.traces import TraceSnapshot
from agentreplay.observability import (
    ConsoleTelemetryExporter,
    FileTelemetryExporter,
    JSONTelemetryExporter,
    MetricsAggregator,
    TelemetrySampler,
    TraceMapper,
)
from agentreplay.plugins import AgentReplayPlugin, PluginApp
from agentreplay.storage import SQLiteStorage
from agentreplay.types import Metadata


def _recorded_trace() -> TraceSnapshot:
    with Recorder(name="observed") as recorder:
        recorder.user_prompt("hello")
        recorder.llm_response(
            provider_name="openai",
            model_name="gpt-test",
            response="hi",
            token_usage={"input_tokens": 2, "output_tokens": 3, "total_tokens": 5},
            cost={"amount": 0.01, "currency": "USD"},
            latency_ms=25.0,
        )
        recorder.tool_finished("search", result={"ok": True}, duration_ms=10.0)
        recorder.retry(attempt=1, reason="rate limit")
        recorder.memory_read("profile", value="x")
        recorder.memory_write("profile", value="y")
    return recorder.trace()


def test_trace_mapper_maps_run_and_events_to_telemetry_spans() -> None:
    trace = _recorded_trace()
    telemetry = TraceMapper(
        ObservabilityConfig(service_name="agent-service"),
    ).map_trace(
        trace,
        correlation=CorrelationContext(
            request_id="req-1",
            session_id="sess-1",
            custom_ids={"tenant": "acme"},
            baggage={"region": "us"},
        ),
    )

    assert telemetry.run_id == trace.run.run_id
    assert telemetry.resource["service.name"] == "agent-service"
    assert len(telemetry.spans) == len(trace.events)
    assert telemetry.spans[0].attributes["agentreplay.run.id"] == trace.run.run_id
    assert telemetry.spans[0].attributes["agentreplay.request_id"] == "req-1"
    assert telemetry.spans[0].attributes["baggage.region"] == "us"


def test_metrics_aggregator_summarizes_trace_data() -> None:
    metrics = MetricsAggregator().summarize([_recorded_trace()], plugin_count=2)

    assert metrics.run_count == 1
    assert metrics.success_count == 1
    assert metrics.retry_count == 1
    assert metrics.average_tokens == 5
    assert metrics.average_cost == 0.01
    assert metrics.tool_usage["search"] == 1
    assert metrics.model_usage["gpt-test"] == 1
    assert metrics.memory_reads == 1
    assert metrics.memory_writes == 1
    assert metrics.plugin_count == 2


def test_sampling_modes_are_respected() -> None:
    trace = TraceMapper().map_trace(_recorded_trace())

    assert TelemetrySampler(ObservabilityConfig(sampling="always_on")).should_sample(
        trace,
    )
    assert not TelemetrySampler(
        ObservabilityConfig(sampling="always_off"),
    ).should_sample(trace)
    assert not TelemetrySampler(
        ObservabilityConfig(sampling="ratio", sampling_ratio=0.0),
    ).should_sample(trace)


def test_json_console_and_file_exporters(tmp_path: Path) -> None:
    telemetry = TraceMapper().map_trace(_recorded_trace())
    json_result = JSONTelemetryExporter().export(telemetry)
    console_result = ConsoleTelemetryExporter().export(telemetry)
    file_path = tmp_path / "telemetry.jsonl"
    file_result = FileTelemetryExporter(file_path).export(telemetry)

    assert json.loads(json_result.output or "{}")["run_id"] == telemetry.run_id
    assert "Trace" in (console_result.output or "")
    assert file_result.succeeded
    assert telemetry.run_id in file_path.read_text(encoding="utf-8")


def test_observability_engine_exports_when_enabled() -> None:
    engine = ObservabilityEngine(ObservabilityConfig(enabled=True, exporter="json"))

    result = engine.export_trace(_recorded_trace())

    assert result.succeeded
    assert result.exported_spans > 0


def test_observability_engine_respects_disabled_config() -> None:
    engine = ObservabilityEngine(ObservabilityConfig(enabled=False, exporter="json"))

    result = engine.export_trace(_recorded_trace())

    assert result.succeeded
    assert result.exported_spans == 0
    assert result.message == "telemetry disabled"


def test_observability_settings_load_from_environment() -> None:
    settings = load_settings(
        environ={
            "AGENTREPLAY_OBSERVABILITY_ENABLED": "true",
            "AGENTREPLAY_OBSERVABILITY_EXPORTER": "file",
            "AGENTREPLAY_OBSERVABILITY_ENDPOINT": "http://localhost:4318",
            "AGENTREPLAY_OBSERVABILITY_HEADERS": "x-api-key=value",
            "AGENTREPLAY_OBSERVABILITY_SERVICE_NAME": "agent-service",
            "AGENTREPLAY_OBSERVABILITY_SERVICE_NAMESPACE": "agents",
            "AGENTREPLAY_OBSERVABILITY_ENVIRONMENT": "test",
            "AGENTREPLAY_OBSERVABILITY_SAMPLING": "ratio",
            "AGENTREPLAY_OBSERVABILITY_SAMPLING_RATIO": "0.5",
            "AGENTREPLAY_OBSERVABILITY_TIMEOUT_MS": "1234",
            "AGENTREPLAY_OBSERVABILITY_TLS_ENABLED": "false",
            "AGENTREPLAY_OBSERVABILITY_COMPRESSION": "gzip",
            "AGENTREPLAY_OBSERVABILITY_FILE_PATH": "telemetry.jsonl",
            "AGENTREPLAY_OBSERVABILITY_BATCH_SIZE": "64",
            "AGENTREPLAY_OBSERVABILITY_QUEUE_SIZE": "128",
            "AGENTREPLAY_OBSERVABILITY_GRACEFUL_SHUTDOWN_MS": "2000",
            "AGENTREPLAY_OBSERVABILITY_AUTH_TOKEN": "secret",
        },
    )

    assert settings.observability_enabled is True
    assert settings.observability_exporter == "file"
    assert settings.observability_endpoint == "http://localhost:4318"
    assert settings.observability_headers == {"x-api-key": "value"}
    assert settings.observability_service_name == "agent-service"
    assert settings.observability_service_namespace == "agents"
    assert settings.observability_environment == "test"
    assert settings.observability_sampling == "ratio"
    assert settings.observability_sampling_ratio == 0.5
    assert settings.observability_timeout_ms == 1234
    assert settings.observability_tls_enabled is False
    assert settings.observability_compression == "gzip"
    assert settings.observability_file_path == "telemetry.jsonl"
    assert settings.observability_batch_size == 64
    assert settings.observability_queue_size == 128
    assert settings.observability_graceful_shutdown_ms == 2000
    assert settings.observability_auth_token == "secret"


def test_observability_settings_load_from_toml(tmp_path: Path) -> None:
    config_file = tmp_path / "agentreplay.toml"
    config_file.write_text(
        "\n".join(
            [
                "[observability]",
                "enabled = true",
                'exporter = "json"',
                'service_name = "agent-service"',
                'sampling = "parent_based"',
                "sampling_ratio = 0.25",
                "timeout_ms = 3000",
                "tls_enabled = true",
                "",
                "[observability.headers]",
                'x-tenant = "acme"',
            ],
        ),
        encoding="utf-8",
    )

    settings = load_settings(config_path=config_file, environ={})

    assert settings.observability_enabled is True
    assert settings.observability_exporter == "json"
    assert settings.observability_headers == {"x-tenant": "acme"}
    assert settings.observability_sampling == "parent_based"
    assert settings.observability_sampling_ratio == 0.25


def test_telemetry_cli_commands(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_path = tmp_path / "runs.sqlite"
    storage = SQLiteStorage(db_path)
    recorder = Recorder(name="cli-telemetry")
    with recorder:
        recorder.user_prompt("hello")
    recorder.save_to_storage(storage)
    storage.close()

    assert main(["telemetry", "status"]) == 0
    assert "AgentReplay Telemetry" in capsys.readouterr().out

    assert main(["telemetry", "config", "--json"]) == 0
    assert "service_name" in capsys.readouterr().out

    assert main(["telemetry", "test", "--json"]) == 0
    assert "exported_spans" in capsys.readouterr().out

    assert (
        main(
            [
                "telemetry",
                "export",
                "latest",
                "--db-path",
                str(db_path),
                "--json",
            ],
        )
        == 0
    )
    assert "telemetry disabled" in capsys.readouterr().out


def test_plugin_app_accepts_telemetry_registrations() -> None:
    class Enricher:
        def enrich(self, _attributes: Metadata) -> Metadata:
            return {"extra": True}

    class TelemetryPlugin(AgentReplayPlugin):
        name = "telemetry-plugin"
        version = "1.0.0"

        def register(self, app: object) -> None:
            plugin_app = app
            assert isinstance(plugin_app, PluginApp)
            plugin_app.register_telemetry_exporter("exporter", object())
            plugin_app.register_telemetry_metric("metric", object())
            plugin_app.register_telemetry_span_processor("processor", object())
            plugin_app.register_telemetry_attribute_enricher("enricher", Enricher())

    app = PluginApp()
    app.activate("telemetry-plugin", {})
    TelemetryPlugin().register(app)
    app.deactivate()

    kinds = {registration.kind for registration in app.registrations()}
    assert kinds == {
        "telemetry_exporter",
        "telemetry_metric",
        "telemetry_span_processor",
        "telemetry_attribute_enricher",
    }


def test_trace_mapper_handles_large_event_sets() -> None:
    with Recorder(name="large-observability") as recorder:
        for index in range(100_000):
            recorder.custom_event("step", payload={"index": index})

    telemetry = TraceMapper().map_trace(recorder.trace())

    assert len(telemetry.spans) == 100_002
