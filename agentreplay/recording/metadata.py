"""Metadata collection helpers for recorded runs and events."""

from __future__ import annotations

import os
import platform
import sys
import threading
from collections.abc import Mapping

from agentreplay.recording.serializers import EventSerializer
from agentreplay.types import Metadata


class MetadataCollector:
    """Collect stable runtime metadata for runs and events."""

    def __init__(self, serializer: EventSerializer | None = None) -> None:
        """Create a metadata collector."""
        self._serializer = EventSerializer() if serializer is None else serializer

    def collect_run_metadata(
        self,
        metadata: Mapping[str, object] | None = None,
    ) -> Metadata:
        """Collect process-level metadata for a run."""
        automatic: dict[str, object] = {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "process_id": os.getpid(),
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
        }
        return self._merge(automatic, metadata)

    def collect_event_metadata(
        self,
        metadata: Mapping[str, object] | None = None,
    ) -> Metadata:
        """Collect lightweight context metadata for an event."""
        automatic: dict[str, object] = {
            "thread_id": threading.get_ident(),
            "thread_name": threading.current_thread().name,
        }
        return self._merge(automatic, metadata)

    def _merge(
        self,
        automatic: Mapping[str, object],
        user_metadata: Mapping[str, object] | None,
    ) -> Metadata:
        """Merge automatic metadata with user-provided metadata."""
        merged: dict[str, object] = dict(automatic)
        if user_metadata is not None:
            merged.update(user_metadata)
        return self._serializer.serialize_metadata(merged)


__all__ = ["MetadataCollector"]
