"""Memory-efficient streaming exporters for massive AgentReplay traces."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

from agentreplay.core.events import EventRecord
from agentreplay.core.runs import RunRecord
from agentreplay.exceptions import PerformanceError
from agentreplay.performance.compression import CompressedWriter
from agentreplay.performance.models import CompressionFormat, ExportProgress
from agentreplay.storage import EventQuery, Pagination, StorageBackend

ProgressCallback = Callable[[ExportProgress], None]


class StreamingTraceExporter:
    """Export large traces directly to disk without building full JSON in memory."""

    def __init__(self, storage: StorageBackend, *, batch_size: int = 5_000) -> None:
        """Create a streaming exporter."""
        if batch_size <= 0:
            msg = "Export batch size must be greater than zero."
            raise ValueError(msg)
        self._storage = storage
        self._batch_size = batch_size

    def export_json(
        self,
        run_id: str,
        path: str | Path,
        *,
        compression: CompressionFormat = "none",
        offset: int = 0,
        limit: int | None = None,
        progress: ProgressCallback | None = None,
    ) -> ExportProgress:
        """Stream a JSON trace object to disk."""
        run = self._require_run(run_id)
        events_written = 0
        with CompressedWriter(path, compression_format=compression) as writer:
            self._write(writer, b'{"run":')
            self._write(writer, _json_bytes(run.to_dict()))
            self._write(writer, b',"events":[')
            first = True
            for event in self._events(run_id, offset=offset, limit=limit):
                if not first:
                    self._write(writer, b",")
                self._write(writer, _json_bytes(event.to_dict()))
                first = False
                events_written += 1
                if progress is not None and events_written % self._batch_size == 0:
                    progress(
                        ExportProgress(
                            run_id=run_id,
                            events_written=events_written,
                            bytes_written=writer.result.input_bytes,
                        )
                    )
            self._write(writer, b"]}")
            final = ExportProgress(
                run_id=run_id,
                events_written=events_written,
                bytes_written=writer.result.input_bytes,
            )
        if progress is not None:
            progress(final)
        return final

    def export_jsonl(
        self,
        run_id: str,
        path: str | Path,
        *,
        compression: CompressionFormat = "none",
        offset: int = 0,
        limit: int | None = None,
        progress: ProgressCallback | None = None,
    ) -> ExportProgress:
        """Stream newline-delimited JSON events to disk."""
        self._require_run(run_id)
        events_written = 0
        with CompressedWriter(path, compression_format=compression) as writer:
            for event in self._events(run_id, offset=offset, limit=limit):
                self._write(writer, _json_bytes(event.to_dict()) + b"\n")
                events_written += 1
                if progress is not None and events_written % self._batch_size == 0:
                    progress(
                        ExportProgress(
                            run_id=run_id,
                            events_written=events_written,
                            bytes_written=writer.result.input_bytes,
                        )
                    )
            final = ExportProgress(
                run_id=run_id,
                events_written=events_written,
                bytes_written=writer.result.input_bytes,
            )
        if progress is not None:
            progress(final)
        return final

    def _events(
        self,
        run_id: str,
        *,
        offset: int,
        limit: int | None,
    ) -> Iterator[EventRecord]:
        """Iterate export events without loading the full trace."""
        if offset < 0:
            msg = "Export offset must be zero or greater."
            raise ValueError(msg)
        query = EventQuery(
            run_id=run_id,
            pagination=Pagination(limit=limit, offset=offset),
        )
        yield from self._storage.stream_events(
            run_id,
            query=query,
            batch_size=self._batch_size,
        )

    def _require_run(self, run_id: str) -> RunRecord:
        """Load a run or raise a performance error."""
        run = self._storage.load_run(run_id)
        if run is None:
            msg = f"Export run not found: {run_id}"
            raise PerformanceError(msg)
        return run

    @staticmethod
    def _write(writer: CompressedWriter, data: bytes) -> None:
        """Write bytes through a compressed writer."""
        writer.write(data)


def _json_bytes(value: object) -> bytes:
    """Serialize compact JSON bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


__all__ = ["ProgressCallback", "StreamingTraceExporter"]
