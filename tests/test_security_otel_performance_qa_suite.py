from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from agentreplay import (
    BenchmarkCase,
    BenchmarkSuite,
    CorrelationContext,
    ObservabilityConfig,
    ObservabilityEngine,
    SecurityConfig,
    SecurityEngine,
    SecurityRule,
    SQLiteStorage,
    StreamingTraceExporter,
    TelemetryExportResult,
    TelemetryTrace,
    TraceWindowReader,
)
from agentreplay.core.events import (
    COST_RECORDED,
    CUSTOM_EVENT,
    LATENCY_RECORDED,
    LLM_REQUEST,
    LLM_RESPONSE,
    MEMORY_READ,
    MEMORY_WRITE,
    RETRY_RECORDED,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_FINISHED,
    EventRecord,
)
from agentreplay.core.runs import RunRecord
from agentreplay.core.traces import TraceSnapshot
from agentreplay.observability import TelemetrySampler, TraceMapper
from agentreplay.performance import compress_bytes, decompress_bytes
from agentreplay.performance.compression import (
    compression_result,
    iter_decompressed_lines,
)
from agentreplay.performance.models import ExportProgress
from agentreplay.types import JSONValue


@pytest.fixture
def trace() -> TraceSnapshot:
    """Return a representative trace for telemetry and performance tests."""
    return _trace("qa-run")


def test_01_detect_api_key() -> None:
    report = SecurityEngine().scan(
        {"prompt": "use sk-abcdefghijklmnopqrstuvwxyz123456"}
    )

    assert report.secrets_found == 1
    assert report.risk_level == "critical"
    assert report.findings[0].category == "openai_key"


def test_02_detect_jwt() -> None:
    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.signaturepart123"

    report = SecurityEngine().scan({"payload": token})

    assert report.secrets_found == 1
    assert report.findings[0].category == "jwt"
    assert token not in str(report.redacted_preview)


def test_03_detect_aws_key() -> None:
    report = SecurityEngine().scan({"payload": "aws AKIAABCDEFGHIJKLMNOP"})

    assert report.secrets_found == 1
    assert report.findings[0].category == "aws_access_key"
    assert "[AWS ACCESS KEY REDACTED]" in str(report.redacted_preview)


def test_04_detect_bearer_token() -> None:
    token = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    report = SecurityEngine().scan({"payload": token})

    assert report.secrets_found == 1
    assert report.findings[0].category == "bearer_token"
    assert token not in str(report.redacted_preview)


def test_05_redact_secret() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"

    sanitized = SecurityEngine().sanitize({"token": secret, "message": "safe"})

    assert isinstance(sanitized, dict)
    assert sanitized["token"] == "[SENSITIVE FIELD REDACTED]"
    assert sanitized["message"] == "safe"
    assert secret not in json.dumps(sanitized)


def test_06_custom_regex() -> None:
    rule = SecurityRule(
        name="internal_secret",
        pattern=r"INTSECRET-[0-9]{6}",
        category="internal_secret",
        placeholder="[INTERNAL SECRET REDACTED]",
    )

    report = SecurityEngine(SecurityConfig(custom_rules=(rule,))).scan(
        {"payload": "value INTSECRET-123456"}
    )

    assert report.secrets_found == 1
    assert report.findings[0].rule_name == "internal_secret"
    assert "[INTERNAL SECRET REDACTED]" in str(report.redacted_preview)


def test_07_ignore_rule() -> None:
    engine = SecurityEngine(SecurityConfig(ignore_rules=("openai_api_key",)))

    report = engine.scan({"payload": "sk-abcdefghijklmnopqrstuvwxyz123456"})

    assert report.verify()
    assert report.secrets_found == 0


def test_08_allow_list() -> None:
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    engine = SecurityEngine(SecurityConfig(allowlist=("safe_prompt",)))

    sanitized = engine.sanitize(
        {"safe_prompt": secret, "unsafe_prompt": secret},
    )

    assert isinstance(sanitized, dict)
    assert sanitized["safe_prompt"] == secret
    assert sanitized["unsafe_prompt"] == "[OPENAI KEY REDACTED]"


def test_09_export_safety() -> None:
    secret = "Bearer abcdefghijklmnopqrstuvwxyz123456"

    report_data = SecurityEngine().scan({"payload": secret}).to_dict()
    exported = json.dumps(report_data, sort_keys=True)

    assert secret not in exported
    assert "matched_text" not in exported
    assert "matched_preview" in exported


def test_10_security_report() -> None:
    report = SecurityEngine().scan(
        {
            "api_key": "sk-abcdefghijklmnopqrstuvwxyz123456",
            "email": "dev@example.com",
        },
        source="unit-test",
    )

    report_data = report.to_dict()

    assert report.summary() == "risk=critical secrets=1 pii=1 findings=2"
    assert report_data["source"] == "unit-test"
    assert report_data["secrets_found"] == 1
    assert report_data["pii_found"] == 1


def test_11_otel_span_creation(trace: TraceSnapshot) -> None:
    telemetry = TraceMapper().map_trace(trace)

    span = telemetry.spans[2]

    assert span.name == "agentreplay.llm.request"
    assert span.span_id == "qa-run-3"
    assert span.attributes["gen_ai.request.model"] == "gpt-test"
    assert span.events[0].name == LLM_REQUEST


def test_12_otel_trace_mapping(trace: TraceSnapshot) -> None:
    telemetry = TraceMapper(
        ObservabilityConfig(service_name="agentreplay-enterprise"),
    ).map_trace(
        trace,
        correlation=CorrelationContext(
            trace_id="trace-123",
            request_id="request-456",
            custom_ids={"tenant": "acme"},
        ),
    )

    assert telemetry.trace_id == "trace-123"
    assert telemetry.resource["service.name"] == "agentreplay-enterprise"
    assert telemetry.attributes["agentreplay.request_id"] == "request-456"
    assert telemetry.attributes["agentreplay.correlation.tenant"] == "acme"


def test_13_metrics_export(trace: TraceSnapshot) -> None:
    exporter = CollectingTelemetryExporter()
    engine = ObservabilityEngine(
        ObservabilityConfig(enabled=True, exporter="json"),
        exporter=exporter,
    )

    result = engine.export_trace(trace)
    metrics = engine.metrics([trace], replay_count=2, diff_count=1)

    assert result.succeeded
    assert result.exported_spans == len(trace.events)
    assert metrics.export_count == 1
    assert metrics.average_tokens == 42
    assert metrics.average_cost == 0.25


def test_14_sampling(trace: TraceSnapshot) -> None:
    telemetry = TraceMapper().map_trace(trace)
    parent_sampled = TraceMapper().map_trace(
        trace,
        correlation=CorrelationContext(custom_ids={"parent_sampled": "true"}),
    )

    assert TelemetrySampler(ObservabilityConfig(sampling="always_on")).should_sample(
        telemetry
    )
    assert not TelemetrySampler(
        ObservabilityConfig(sampling="always_off")
    ).should_sample(telemetry)
    assert TelemetrySampler(
        ObservabilityConfig(sampling="parent_based", sampling_ratio=0.0)
    ).should_sample(parent_sampled)


def test_15_async_exporter(trace: TraceSnapshot) -> None:
    exporter = CollectingTelemetryExporter()
    engine = ObservabilityEngine(
        ObservabilityConfig(enabled=True, exporter="json"),
        exporter=exporter,
    )

    result = asyncio.run(_export_async(engine, trace))

    assert result.succeeded
    assert len(exporter.traces) == 1
    assert exporter.traces[0].run_id == trace.run.run_id


def test_16_batch_exporter(trace: TraceSnapshot) -> None:
    exporter = CollectingTelemetryExporter()
    engine = ObservabilityEngine(
        ObservabilityConfig(enabled=True, exporter="json", batch_size=2),
        exporter=exporter,
    )

    first = engine.export_trace(trace)
    second = engine.export_trace(_trace("qa-run-2"))
    metrics = engine.metrics([trace])

    assert first.succeeded
    assert second.succeeded
    assert [item.run_id for item in exporter.traces] == ["qa-run", "qa-run-2"]
    assert metrics.export_count == 2


def test_17_compression() -> None:
    raw = b"agentreplay-compression-" * 128

    compressed = compress_bytes(raw, compression_format="gzip")
    result = compression_result(len(raw), len(compressed), compression_format="gzip")

    assert decompress_bytes(compressed, compression_format="gzip") == raw
    assert result.format == "gzip"
    assert 0 < result.ratio < 1


def test_18_lazy_loading(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=25)
    try:
        reader = TraceWindowReader(storage, default_limit=5)

        first = reader.first("perf-run")
        cached_first = reader.window("perf-run", offset=0, limit=5)
        second = reader.next(first)

        assert first is cached_first
        assert [event.sequence for event in first.events] == [1, 2, 3, 4, 5]
        assert [event.sequence for event in second.events] == [6, 7, 8, 9, 10]
    finally:
        storage.close()


def test_19_streaming(tmp_path: Path) -> None:
    storage = _storage(tmp_path, event_count=12)
    output = tmp_path / "stream.jsonl.gz"
    progress: list[ExportProgress] = []
    try:
        exported = StreamingTraceExporter(storage, batch_size=4).export_jsonl(
            "perf-run",
            output,
            compression="gzip",
            offset=2,
            limit=6,
            progress=progress.append,
        )
        lines = list(iter_decompressed_lines(output, compression_format="gzip"))

        assert exported.events_written == 6
        assert [item.events_written for item in progress] == [4, 6]
        assert len(lines) == 6
        assert json.loads(lines[0])["sequence"] == 3
    finally:
        storage.close()


@pytest.mark.performance
def test_20_benchmark_accuracy(tmp_path: Path) -> None:
    case = BenchmarkCase(event_count=30, chunk_size=10)

    result = BenchmarkSuite(db_path=tmp_path / "benchmark.sqlite").run(case)
    measurements = {item.name: item for item in result.measurements}

    assert measurements["storage.batch_insert"].items_processed == 30
    assert measurements["trace.load_first_chunk"].items_processed == 10
    assert measurements["export.jsonl"].items_processed == 30
    assert all(item.duration_ms >= 0 for item in result.measurements)
    assert all(item.peak_memory_bytes >= 0 for item in result.measurements)


class CollectingTelemetryExporter:
    """Telemetry exporter used to verify engine/exporter contracts."""

    name = "collecting"

    def __init__(self) -> None:
        """Create an in-memory telemetry collector."""
        self.traces: list[TelemetryTrace] = []
        self.closed = False

    def export(self, trace: TelemetryTrace) -> TelemetryExportResult:
        """Collect a telemetry trace and return a successful export result."""
        self.traces.append(trace)
        return TelemetryExportResult(
            exporter=self.name,
            succeeded=True,
            message="collected",
            exported_spans=len(trace.spans),
        )

    def shutdown(self) -> None:
        """Mark the exporter as closed."""
        self.closed = True


async def _export_async(
    engine: ObservabilityEngine,
    trace: TraceSnapshot,
) -> TelemetryExportResult:
    """Export telemetry from an async caller without blocking the event loop."""
    return await asyncio.to_thread(engine.export_trace, trace)


def _trace(run_id: str) -> TraceSnapshot:
    """Build a deterministic trace with security, telemetry, and metric data."""
    run = _run(run_id)
    events = (
        _event(f"{run_id}-1", run_id, 1, RUN_STARTED, {"name": "agent"}),
        _event(f"{run_id}-2", run_id, 2, CUSTOM_EVENT, {"message": "prepare"}),
        _event(
            f"{run_id}-3",
            run_id,
            3,
            LLM_REQUEST,
            {"provider_name": "openai", "model_name": "gpt-test", "prompt": "hello"},
            parent_event_id=f"{run_id}-2",
            duration_ms=12.0,
        ),
        _event(
            f"{run_id}-4",
            run_id,
            4,
            LLM_RESPONSE,
            {
                "response": "hi",
                "model_name": "gpt-test",
                "token_usage": {
                    "input_tokens": 20,
                    "output_tokens": 22,
                    "total_tokens": 42,
                },
                "cost": {"amount": 0.25, "currency": "USD"},
            },
            parent_event_id=f"{run_id}-3",
            duration_ms=18.0,
        ),
        _event(
            f"{run_id}-5",
            run_id,
            5,
            TOOL_FINISHED,
            {"tool_name": "search", "result": "ok"},
            duration_ms=7.0,
        ),
        _event(f"{run_id}-6", run_id, 6, MEMORY_READ, {"key": "state"}),
        _event(f"{run_id}-7", run_id, 7, MEMORY_WRITE, {"key": "state"}),
        _event(f"{run_id}-8", run_id, 8, RETRY_RECORDED, {"attempt": 1}),
        _event(f"{run_id}-9", run_id, 9, COST_RECORDED, {"amount": 0.25}),
        _event(f"{run_id}-10", run_id, 10, LATENCY_RECORDED, {"latency_ms": 18.0}),
        _event(f"{run_id}-11", run_id, 11, RUN_FINISHED, {"status": "completed"}),
    )
    return TraceSnapshot(run=run, events=events)


def _storage(tmp_path: Path, *, event_count: int) -> SQLiteStorage:
    """Create a SQLite database with a deterministic performance trace."""
    storage = SQLiteStorage(tmp_path / "agentreplay.sqlite")
    storage.save_run(_run("perf-run"))
    storage.bulk_insert_events(
        tuple(
            _event(f"perf-{index}", "perf-run", index, CUSTOM_EVENT, {"i": index})
            for index in range(1, event_count + 1)
        )
    )
    return storage


def _run(run_id: str) -> RunRecord:
    """Create a deterministic run record."""
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return RunRecord(
        run_id=run_id,
        name=run_id,
        status="completed",
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        duration_ms=1_000.0,
        metadata={"suite": "qa"},
        tags=("qa",),
    )


def _event(
    event_id: str,
    run_id: str,
    sequence: int,
    event_type: str,
    payload: dict[str, JSONValue],
    *,
    parent_event_id: str | None = None,
    duration_ms: float = 0.0,
) -> EventRecord:
    """Create a deterministic event record."""
    return EventRecord(
        event_id=event_id,
        run_id=run_id,
        parent_event_id=parent_event_id,
        sequence=sequence,
        event_type=event_type,
        timestamp=datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        + timedelta(milliseconds=sequence),
        duration_ms=duration_ms,
        metadata={"suite": "qa"},
        payload=payload,
    )
