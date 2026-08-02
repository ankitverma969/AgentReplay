"""Public SDK extension registry."""

from __future__ import annotations

from collections import defaultdict

from agentreplay.exceptions import SDKError
from agentreplay.sdk.compat import ensure_sdk_compatible
from agentreplay.sdk.extensions import (
    SDKAnalyzer,
    SDKCLICommand,
    SDKExporter,
    SDKFrameworkAdapter,
    SDKReportExtension,
    SDKStorageFactory,
    SDKVisualization,
)
from agentreplay.sdk.models import SDKExtensionKind, SDKExtensionMetadata


class SDKExtensionRegistry:
    """Registry of stable SDK extensions by kind and name."""

    def __init__(self) -> None:
        """Create an SDK extension registry."""
        self._extensions: defaultdict[SDKExtensionKind, dict[str, object]] = (
            defaultdict(dict)
        )
        self._metadata: dict[str, SDKExtensionMetadata] = {}

    def register_analyzer(self, analyzer: SDKAnalyzer) -> None:
        """Register an analyzer extension."""
        self._register("analyzer", analyzer.metadata, analyzer)

    def register_exporter(self, exporter: SDKExporter) -> None:
        """Register an exporter extension."""
        self._register("exporter", exporter.metadata, exporter)

    def register_storage(self, storage: SDKStorageFactory) -> None:
        """Register a storage factory extension."""
        self._register("storage", storage.metadata, storage)

    def register_visualization(self, visualization: SDKVisualization) -> None:
        """Register a visualization extension."""
        self._register("visualization", visualization.metadata, visualization)

    def register_framework_adapter(self, adapter: SDKFrameworkAdapter) -> None:
        """Register a framework adapter extension."""
        self._register("framework_adapter", adapter.metadata, adapter)

    def register_report(self, report: SDKReportExtension) -> None:
        """Register a report extension."""
        self._register("report", report.metadata, report)

    def register_cli_command(self, command: SDKCLICommand) -> None:
        """Register a CLI command extension."""
        self._register("cli_command", command.metadata, command)

    def get(self, kind: SDKExtensionKind, name: str) -> object | None:
        """Return an extension by kind and name."""
        return self._extensions[kind].get(name)

    def require(self, kind: SDKExtensionKind, name: str) -> object:
        """Return an extension or raise."""
        extension = self.get(kind, name)
        if extension is None:
            msg = f"Unknown AgentReplay SDK extension: {kind}.{name}"
            raise SDKError(msg)
        return extension

    def list(
        self, kind: SDKExtensionKind | None = None
    ) -> tuple[SDKExtensionMetadata, ...]:
        """List extension metadata."""
        if kind is None:
            return tuple(self._metadata[name] for name in sorted(self._metadata))
        names = sorted(self._extensions[kind])
        return tuple(self._metadata[name] for name in names)

    def _register(
        self,
        kind: SDKExtensionKind,
        metadata: SDKExtensionMetadata,
        extension: object,
    ) -> None:
        """Register an extension after compatibility validation."""
        if metadata.kind != kind:
            msg = (
                f"SDK extension {metadata.name} declared "
                f"{metadata.kind}, expected {kind}."
            )
            raise SDKError(msg)
        ensure_sdk_compatible(metadata)
        if metadata.name in self._extensions[kind]:
            msg = (
                f"AgentReplay SDK extension already registered: {kind}.{metadata.name}"
            )
            raise SDKError(msg)
        self._extensions[kind][metadata.name] = extension
        self._metadata[metadata.name] = metadata


__all__ = ["SDKExtensionRegistry"]
