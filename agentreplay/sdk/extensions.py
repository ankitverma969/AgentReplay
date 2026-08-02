"""Stable extension protocols and base classes for the public SDK."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping
from typing import Protocol

from agentreplay.core.traces import TraceSnapshot
from agentreplay.sdk.models import (
    AnalyzerResult,
    ExportResult,
    ReportSection,
    SDKExtensionMetadata,
)
from agentreplay.storage import StorageBackend
from agentreplay.types import JSONValue


class SDKAnalyzer(Protocol):
    """Protocol for custom analyzers.

    Analyzer extensions cover latency, security, compliance, prompt, cost, tool,
    memory, and domain-specific analysis.
    """

    metadata: SDKExtensionMetadata

    def analyze(self, trace: TraceSnapshot) -> AnalyzerResult:
        """Analyze a recorded trace without executing agents, LLMs, or tools."""


class SDKExporter(Protocol):
    """Protocol for XML, YAML, CSV, Parquet, SQL, Elastic, Kafka, and API exporters."""

    metadata: SDKExtensionMetadata

    def export(
        self, trace: TraceSnapshot, destination: str | None = None
    ) -> ExportResult:
        """Export a recorded trace."""


class SDKStorageFactory(Protocol):
    """Protocol for custom storage backend factories."""

    metadata: SDKExtensionMetadata

    def create(self, config: Mapping[str, JSONValue] | None = None) -> StorageBackend:
        """Create a storage backend."""


class SDKVisualization(Protocol):
    """Protocol for custom visualization providers."""

    metadata: SDKExtensionMetadata

    def render(self, trace: TraceSnapshot) -> ReportSection:
        """Render visualization content for a trace."""


class SDKFrameworkAdapter(Protocol):
    """Protocol for custom framework adapter extensions."""

    metadata: SDKExtensionMetadata

    def instrument(
        self, target: object, config: Mapping[str, JSONValue] | None = None
    ) -> object:
        """Instrument a framework object and return the instrumented target."""


class SDKReportExtension(Protocol):
    """Protocol for custom report sections.

    Report extensions can add charts, widgets, tables, statistics, and
    recommendations.
    """

    metadata: SDKExtensionMetadata

    def sections(self, trace: TraceSnapshot) -> Iterable[ReportSection]:
        """Return report sections for a trace."""


class SDKCLICommand(Protocol):
    """Protocol for plugin-provided CLI command registrations."""

    metadata: SDKExtensionMetadata

    def register(
        self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None:
        """Register CLI commands."""


class BaseAnalyzer:
    """Convenience base class for SDK analyzers."""

    metadata: SDKExtensionMetadata

    def analyze(self, _trace: TraceSnapshot) -> AnalyzerResult:
        """Analyze a trace using the default no-finding implementation."""
        return AnalyzerResult(analyzer=self.metadata.name)


class BaseExporter:
    """Convenience base class for SDK exporters."""

    metadata: SDKExtensionMetadata

    def export(
        self, trace: TraceSnapshot, destination: str | None = None
    ) -> ExportResult:
        """Export a trace using the default JSON-byte estimate implementation."""
        content = str(trace.to_dict()).encode("utf-8")
        return ExportResult(
            exporter=self.metadata.name,
            content_type="application/octet-stream",
            bytes_written=len(content),
            uri=destination,
        )


class BaseReportExtension:
    """Convenience base class for custom report sections."""

    metadata: SDKExtensionMetadata

    def sections(self, _trace: TraceSnapshot) -> Iterable[ReportSection]:
        """Return no custom sections by default."""
        return ()


class BaseCLICommand:
    """Convenience base class for SDK CLI commands."""

    metadata: SDKExtensionMetadata

    def register(
        self, subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    ) -> None:
        """Register no commands by default."""


def analyzer_metadata(name: str, *, summary: str = "") -> SDKExtensionMetadata:
    """Build stable analyzer metadata."""
    return SDKExtensionMetadata(
        name=name, version="0.1.0", kind="analyzer", summary=summary
    )


def exporter_metadata(name: str, *, summary: str = "") -> SDKExtensionMetadata:
    """Build stable exporter metadata."""
    return SDKExtensionMetadata(
        name=name, version="0.1.0", kind="exporter", summary=summary
    )


__all__ = [
    "BaseAnalyzer",
    "BaseCLICommand",
    "BaseExporter",
    "BaseReportExtension",
    "SDKAnalyzer",
    "SDKCLICommand",
    "SDKExporter",
    "SDKFrameworkAdapter",
    "SDKReportExtension",
    "SDKStorageFactory",
    "SDKVisualization",
    "analyzer_metadata",
    "exporter_metadata",
]
