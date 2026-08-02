"""Massive trace optimization and scalability tools for AgentReplay."""

from agentreplay.performance.benchmark import BenchmarkSuite
from agentreplay.performance.cache import LRUCache, ObjectPool
from agentreplay.performance.compression import (
    CompressedWriter,
    compress_bytes,
    decompress_bytes,
    iter_decompressed_lines,
)
from agentreplay.performance.export import StreamingTraceExporter
from agentreplay.performance.models import (
    BenchmarkCase,
    BenchmarkMeasurement,
    BenchmarkResult,
    CompressionFormat,
    CompressionResult,
    ExportProgress,
    PerformanceReport,
    SearchQuery,
    SearchResult,
    SearchResults,
    SQLiteOptimizationReport,
    TraceWindow,
)
from agentreplay.performance.parallel import parallel_map
from agentreplay.performance.search import BackgroundIndexer, TraceSearchEngine
from agentreplay.performance.sqlite import SQLiteOptimizer, optimize_sqlite
from agentreplay.performance.windows import TraceWindowReader, partial_replay

__all__ = [
    "BackgroundIndexer",
    "BenchmarkCase",
    "BenchmarkMeasurement",
    "BenchmarkResult",
    "BenchmarkSuite",
    "CompressedWriter",
    "CompressionFormat",
    "CompressionResult",
    "ExportProgress",
    "LRUCache",
    "ObjectPool",
    "PerformanceReport",
    "SQLiteOptimizationReport",
    "SQLiteOptimizer",
    "SearchQuery",
    "SearchResult",
    "SearchResults",
    "StreamingTraceExporter",
    "TraceSearchEngine",
    "TraceWindow",
    "TraceWindowReader",
    "compress_bytes",
    "decompress_bytes",
    "iter_decompressed_lines",
    "optimize_sqlite",
    "parallel_map",
    "partial_replay",
]
