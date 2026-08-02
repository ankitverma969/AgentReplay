"""Typed models for AgentReplay performance and scalability features."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, TypeAlias

from agentreplay.core.events import EventRecord, EventType
from agentreplay.types import JSONValue

CompressionFormat: TypeAlias = Literal["none", "gzip", "zstd", "lz4"]
SearchMode: TypeAlias = Literal[
    "text", "regex", "metadata", "tool", "prompt", "error", "provider", "model"
]
PoolKind: TypeAlias = Literal["thread", "process"]


@dataclass(frozen=True, slots=True)
class TraceWindow:
    """A bounded, ordered event window from a large trace."""

    run_id: str
    events: tuple[EventRecord, ...]
    offset: int
    limit: int
    total_estimate: int | None = None

    @property
    def next_offset(self) -> int:
        """Return the next offset after this window."""
        return self.offset + len(self.events)

    @property
    def previous_offset(self) -> int:
        """Return the previous offset for the same window size."""
        return max(0, self.offset - self.limit)

    @property
    def has_more(self) -> bool:
        """Return whether this window may have more events after it."""
        if self.total_estimate is None:
            return len(self.events) == self.limit
        return self.next_offset < self.total_estimate


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Search options for large recorded traces."""

    run_id: str
    text: str | None = None
    mode: SearchMode = "text"
    event_types: tuple[EventType, ...] = ()
    metadata_key: str | None = None
    metadata_value: str | None = None
    case_sensitive: bool = False
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        """Validate search bounds."""
        if self.limit <= 0:
            msg = "Search limit must be greater than zero."
            raise ValueError(msg)
        if self.offset < 0:
            msg = "Search offset must be zero or greater."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class SearchResult:
    """One high-performance trace search match."""

    event: EventRecord
    score: float
    snippet: str
    matched_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SearchResults:
    """A bounded set of search results with pagination metadata."""

    query: SearchQuery
    matches: tuple[SearchResult, ...]
    scanned_events: int
    used_index: bool
    has_more: bool


@dataclass(frozen=True, slots=True)
class CompressionResult:
    """Statistics for one compression operation."""

    format: CompressionFormat
    input_bytes: int
    output_bytes: int

    @property
    def ratio(self) -> float:
        """Return compressed/original size ratio."""
        if self.input_bytes == 0:
            return 1.0
        return self.output_bytes / self.input_bytes


@dataclass(frozen=True, slots=True)
class ExportProgress:
    """Progress notification emitted during large streaming exports."""

    run_id: str
    events_written: int
    bytes_written: int


@dataclass(frozen=True, slots=True)
class SQLiteOptimizationReport:
    """SQLite optimization and analysis results."""

    db_path: str
    page_count: int
    page_size: int
    freelist_count: int
    event_count: int
    run_count: int
    indexes: tuple[str, ...]
    analyzed: bool
    vacuumed: bool

    @property
    def estimated_size_bytes(self) -> int:
        """Return the SQLite file size estimate from page count and size."""
        return self.page_count * self.page_size

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible report dictionary."""
        return {
            "db_path": self.db_path,
            "page_count": self.page_count,
            "page_size": self.page_size,
            "freelist_count": self.freelist_count,
            "event_count": self.event_count,
            "run_count": self.run_count,
            "indexes": list(self.indexes),
            "analyzed": self.analyzed,
            "vacuumed": self.vacuumed,
            "estimated_size_bytes": self.estimated_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    """Aggregated memory, CPU, storage, compression, and index statistics."""

    generated_at: datetime
    storage: SQLiteOptimizationReport | None = None
    memory_bytes: int | None = None
    cpu_seconds: float | None = None
    compression: CompressionResult | None = None
    index_statistics: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible performance report."""
        return {
            "generated_at": self.generated_at.isoformat(),
            "storage": None if self.storage is None else self.storage.to_dict(),
            "memory_bytes": self.memory_bytes,
            "cpu_seconds": self.cpu_seconds,
            "compression": None
            if self.compression is None
            else {
                "format": self.compression.format,
                "input_bytes": self.compression.input_bytes,
                "output_bytes": self.compression.output_bytes,
                "ratio": self.compression.ratio,
            },
            "index_statistics": self.index_statistics,
        }


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """One benchmark workload definition."""

    event_count: int
    chunk_size: int = 5_000
    include_search: bool = True
    include_export: bool = True
    include_replay: bool = True
    include_diff: bool = True
    include_report: bool = True

    def __post_init__(self) -> None:
        """Validate benchmark sizes."""
        if self.event_count <= 0:
            msg = "Benchmark event count must be greater than zero."
            raise ValueError(msg)
        if self.chunk_size <= 0:
            msg = "Benchmark chunk size must be greater than zero."
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class BenchmarkMeasurement:
    """A measured benchmark operation."""

    name: str
    duration_ms: float
    peak_memory_bytes: int
    items_processed: int


@dataclass(frozen=True, slots=True)
class BenchmarkResult:
    """Benchmark result for a single synthetic large trace."""

    case: BenchmarkCase
    measurements: tuple[BenchmarkMeasurement, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a JSON-compatible benchmark result."""
        return {
            "case": {
                "event_count": self.case.event_count,
                "chunk_size": self.case.chunk_size,
            },
            "measurements": [
                {
                    "name": item.name,
                    "duration_ms": item.duration_ms,
                    "peak_memory_bytes": item.peak_memory_bytes,
                    "items_processed": item.items_processed,
                }
                for item in self.measurements
            ],
        }


__all__ = [
    "BenchmarkCase",
    "BenchmarkMeasurement",
    "BenchmarkResult",
    "CompressionFormat",
    "CompressionResult",
    "ExportProgress",
    "PerformanceReport",
    "PoolKind",
    "SQLiteOptimizationReport",
    "SearchMode",
    "SearchQuery",
    "SearchResult",
    "SearchResults",
    "TraceWindow",
]
