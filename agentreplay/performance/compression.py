"""Streaming compression helpers for large AgentReplay exports."""

from __future__ import annotations

import gzip
import importlib
from collections.abc import Iterator
from pathlib import Path
from typing import IO, BinaryIO, NoReturn, cast

from agentreplay.exceptions import PerformanceError
from agentreplay.performance.models import CompressionFormat, CompressionResult


def compress_bytes(
    data: bytes,
    *,
    compression_format: str = "gzip",
) -> bytes:
    """Compress bytes using a supported compression format."""
    normalized = _normalize_format(compression_format)
    if normalized == "none":
        return data
    if normalized == "gzip":
        return gzip.compress(data)
    if normalized == "zstd":
        zstandard = importlib.import_module("zstandard")
        compressor = zstandard.ZstdCompressor()
        return bytes(compressor.compress(data))
    if normalized == "lz4":
        lz4_frame = importlib.import_module("lz4.frame")
        return bytes(lz4_frame.compress(data))
    return _raise_unknown(normalized)


def decompress_bytes(
    data: bytes,
    *,
    compression_format: str = "gzip",
) -> bytes:
    """Decompress bytes using a supported compression format."""
    normalized = _normalize_format(compression_format)
    if normalized == "none":
        return data
    if normalized == "gzip":
        return gzip.decompress(data)
    if normalized == "zstd":
        zstandard = importlib.import_module("zstandard")
        decompressor = zstandard.ZstdDecompressor()
        return bytes(decompressor.decompress(data))
    if normalized == "lz4":
        lz4_frame = importlib.import_module("lz4.frame")
        return bytes(lz4_frame.decompress(data))
    return _raise_unknown(normalized)


def compression_result(
    input_bytes: int,
    output_bytes: int,
    *,
    compression_format: str,
) -> CompressionResult:
    """Build compression statistics."""
    return CompressionResult(
        format=cast(CompressionFormat, _normalize_format(compression_format)),
        input_bytes=input_bytes,
        output_bytes=output_bytes,
    )


class CompressedWriter:
    """Streaming binary writer with transparent optional compression."""

    def __init__(
        self,
        path: str | Path,
        *,
        compression_format: str = "none",
    ) -> None:
        """Open a compressed writer for a filesystem path."""
        self._path = Path(path).expanduser()
        self._format = _normalize_format(compression_format)
        self._input_bytes = 0
        self._output_bytes = 0
        self._raw: BinaryIO | None = None
        self._writer: IO[bytes] | None = None

    @property
    def result(self) -> CompressionResult:
        """Return current compression statistics."""
        return compression_result(
            self._input_bytes,
            self._output_bytes,
            compression_format=self._format,
        )

    def write(self, data: bytes) -> int:
        """Write bytes to the compressed stream."""
        writer = self._require_writer()
        self._input_bytes += len(data)
        written = writer.write(data)
        return int(written)

    def __enter__(self) -> CompressedWriter:
        """Open the writer."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        raw = self._path.open("wb")
        self._raw = raw
        if self._format == "none":
            self._writer = raw
        elif self._format == "gzip":
            self._writer = cast(IO[bytes], gzip.GzipFile(fileobj=raw, mode="wb"))
        elif self._format == "zstd":
            zstandard = importlib.import_module("zstandard")
            compressor = zstandard.ZstdCompressor()
            self._writer = cast(IO[bytes], compressor.stream_writer(raw))
        else:
            lz4_frame = importlib.import_module("lz4.frame")
            self._writer = cast(IO[bytes], lz4_frame.open(raw, mode="wb"))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        """Close the compressed stream and capture output size."""
        if self._writer is not None:
            self._writer.close()
        if self._raw is not None and not self._raw.closed:
            self._raw.close()
        if self._path.exists():
            self._output_bytes = self._path.stat().st_size

    def _require_writer(self) -> IO[bytes]:
        """Return the active writer."""
        if self._writer is None:
            msg = "CompressedWriter must be used as a context manager."
            raise PerformanceError(msg)
        return self._writer


def iter_decompressed_lines(
    path: str | Path,
    *,
    compression_format: str = "none",
) -> Iterator[str]:
    """Iterate decompressed UTF-8 lines from a compressed export."""
    resolved = Path(path).expanduser()
    normalized = _normalize_format(compression_format)
    if normalized == "none":
        with resolved.open("rt", encoding="utf-8") as handle:
            yield from handle
        return
    if normalized == "gzip":
        with gzip.open(resolved, "rt", encoding="utf-8") as handle:
            yield from handle
        return
    if normalized == "zstd":
        zstandard = importlib.import_module("zstandard")
        with resolved.open("rb") as raw:
            reader = zstandard.ZstdDecompressor().stream_reader(raw)
            yield from reader.read().decode("utf-8").splitlines(keepends=True)
        return
    if normalized == "lz4":
        lz4_frame = importlib.import_module("lz4.frame")
        with lz4_frame.open(resolved, "rt", encoding="utf-8") as handle:
            yield from handle
        return
    _raise_unknown(normalized)


def _normalize_format(value: str) -> str:
    """Validate and normalize a compression format string."""
    if value in {"none", "gzip", "zstd", "lz4"}:
        return value
    return _raise_unknown(value)


def _raise_unknown(compression_format: str) -> NoReturn:
    """Raise for an unsupported compression format."""
    msg = f"Unsupported AgentReplay compression format: {compression_format}"
    raise PerformanceError(msg)


__all__ = [
    "CompressedWriter",
    "compress_bytes",
    "compression_result",
    "decompress_bytes",
    "iter_decompressed_lines",
]
