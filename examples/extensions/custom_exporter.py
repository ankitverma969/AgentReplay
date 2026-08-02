"""Example AgentReplay SDK custom exporter extension."""

from __future__ import annotations

from agentreplay.sdk import ExportResult, SDKExtensionMetadata, TraceSnapshot


class XMLTraceExporter:
    """Export a trace as a tiny XML document."""

    metadata = SDKExtensionMetadata(
        name="xml-trace-exporter",
        version="0.1.0",
        kind="exporter",
        summary="Exports recorded trace metadata as XML.",
    )

    def export(
        self, trace: TraceSnapshot, destination: str | None = None
    ) -> ExportResult:
        """Export trace metadata to XML bytes."""
        content = (
            f"<trace run_id='{trace.run.run_id}' events='{len(trace.events)}' />"
        ).encode()
        return ExportResult(
            exporter=self.metadata.name,
            content_type="application/xml",
            bytes_written=len(content),
            uri=destination,
        )
