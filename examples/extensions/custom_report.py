"""Example AgentReplay SDK custom report extension."""

from __future__ import annotations

from collections.abc import Iterable

from agentreplay.sdk import ReportSection, SDKExtensionMetadata, TraceSnapshot


class RunTagReport:
    """Render run tags as a report section."""

    metadata = SDKExtensionMetadata(
        name="run-tag-report",
        version="0.1.0",
        kind="report",
        summary="Adds run tags to reports.",
    )

    def sections(self, trace: TraceSnapshot) -> Iterable[ReportSection]:
        """Return a run tag section."""
        tags = ", ".join(trace.run.tags) or "none"
        return (
            ReportSection(
                title="Run Tags",
                html=f"<p>{tags}</p>",
                order=20,
            ),
        )
