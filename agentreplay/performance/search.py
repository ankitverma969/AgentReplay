"""High-performance search for large AgentReplay traces."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator, Mapping

from agentreplay.core.events import EventRecord
from agentreplay.exceptions import PerformanceError
from agentreplay.performance.models import SearchQuery, SearchResult, SearchResults
from agentreplay.storage import SQLiteStorage, StorageBackend

_SEARCH_FIELDS = (
    "prompt",
    "messages",
    "input",
    "instructions",
    "response",
    "result",
    "tool_name",
    "function_name",
    "model_name",
    "provider_name",
    "provider",
    "error",
    "exception",
    "warning",
    "message",
)

_SEARCH_INDEX_SCHEMA = (
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS agentreplay_event_search
    USING fts5(
        event_id UNINDEXED,
        run_id UNINDEXED,
        event_type UNINDEXED,
        sequence UNINDEXED,
        content
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_event_search_run ON events(run_id, sequence)",
)


class TraceSearchEngine:
    """Search trace events using SQLite FTS when available, with streaming fallback."""

    def __init__(self, storage: StorageBackend, *, batch_size: int = 5_000) -> None:
        """Create a trace search engine."""
        if batch_size <= 0:
            msg = "Search batch size must be greater than zero."
            raise ValueError(msg)
        self._storage = storage
        self._batch_size = batch_size

    def index_run(self, run_id: str) -> int:
        """Build or refresh the SQLite full-text search index for one run."""
        connection = _sqlite_connection(self._storage)
        if connection is None:
            return 0
        try:
            for statement in _SEARCH_INDEX_SCHEMA:
                connection.execute(statement)
            connection.execute(
                "DELETE FROM agentreplay_event_search WHERE run_id = ?",
                (run_id,),
            )
            rows: list[tuple[str, str, str, int, str]] = []
            count = 0
            for event in self._storage.stream_events(
                run_id, batch_size=self._batch_size
            ):
                rows.append(_index_row(event))
                if len(rows) >= self._batch_size:
                    connection.executemany(_INSERT_SEARCH_SQL, rows)
                    count += len(rows)
                    rows.clear()
            if rows:
                connection.executemany(_INSERT_SEARCH_SQL, rows)
                count += len(rows)
            return count
        except sqlite3.Error as exc:
            msg = "Could not build AgentReplay event search index."
            raise PerformanceError(msg) from exc

    def search(self, query: SearchQuery) -> SearchResults:
        """Search a large trace with pagination."""
        if query.mode in {"regex", "metadata"}:
            return self._streaming_search(query)
        indexed = self._indexed_search(query)
        if indexed is not None:
            return indexed
        return self._streaming_search(query)

    def _indexed_search(self, query: SearchQuery) -> SearchResults | None:
        """Search the optional SQLite FTS index."""
        connection = _sqlite_connection(self._storage)
        if connection is None or not _has_search_index(connection):
            return None
        text = _query_text(query)
        if not text:
            return None
        try:
            rows = connection.execute(
                """
                SELECT event_id
                FROM agentreplay_event_search
                WHERE run_id = ? AND content MATCH ?
                ORDER BY rank
                LIMIT ? OFFSET ?
                """,
                (query.run_id, _fts_query(text), query.limit + 1, query.offset),
            ).fetchall()
        except sqlite3.Error:
            return None
        events = tuple(
            event
            for event_id in (str(row["event_id"]) for row in rows[: query.limit])
            for event in (_load_event(self._storage, query.run_id, event_id),)
            if event is not None and _matches_event_type(event, query)
        )
        matches = tuple(
            SearchResult(
                event=event,
                score=1.0,
                snippet=_snippet(event, text, query.case_sensitive),
                matched_fields=_matched_fields(event, text, query.case_sensitive),
            )
            for event in events
        )
        return SearchResults(
            query=query,
            matches=matches,
            scanned_events=len(rows),
            used_index=True,
            has_more=len(rows) > query.limit,
        )

    def _streaming_search(self, query: SearchQuery) -> SearchResults:
        """Search by streaming events and evaluating predicates incrementally."""
        matches: list[SearchResult] = []
        scanned = 0
        skipped = 0
        text = _query_text(query)
        regex = _compile_regex(text, query) if query.mode == "regex" else None
        has_more = False
        for event in self._storage.stream_events(
            query.run_id, batch_size=self._batch_size
        ):
            scanned += 1
            result = _match_event(event, query, text=text, regex=regex)
            if result is None:
                continue
            if skipped < query.offset:
                skipped += 1
                continue
            if len(matches) >= query.limit:
                has_more = True
                break
            matches.append(result)
        return SearchResults(
            query=query,
            matches=tuple(matches),
            scanned_events=scanned,
            used_index=False,
            has_more=has_more,
        )


class BackgroundIndexer:
    """Simple thread-backed background indexer for large traces."""

    def __init__(self, engine: TraceSearchEngine) -> None:
        """Create a background indexer."""
        self._engine = engine

    def submit(self, run_id: str) -> int:
        """Index a run synchronously through the configured engine.

        The method is intentionally deterministic for library users and tests. Callers
        that want background execution can pass it to ``ThreadPoolExecutor.submit``.
        """
        return self._engine.index_run(run_id)


def _sqlite_connection(storage: StorageBackend) -> sqlite3.Connection | None:
    """Return a SQLite connection when the backend is local SQLite."""
    if not isinstance(storage, SQLiteStorage):
        return None
    return storage._connection_manager.get_connection()


def _has_search_index(connection: sqlite3.Connection) -> bool:
    """Return whether the FTS search index exists."""
    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'agentreplay_event_search'
        """
    ).fetchone()
    return row is not None


def _index_row(event: EventRecord) -> tuple[str, str, str, int, str]:
    """Build one FTS row."""
    return (
        event.event_id,
        event.run_id,
        event.event_type,
        event.sequence,
        _event_text(event),
    )


_INSERT_SEARCH_SQL = """
    INSERT INTO agentreplay_event_search(
        event_id, run_id, event_type, sequence, content
    )
    VALUES (?, ?, ?, ?, ?)
"""


def _load_event(
    storage: StorageBackend,
    run_id: str,
    event_id: str,
) -> EventRecord | None:
    """Load one event by id using a streaming-compatible fallback."""
    for event in storage.stream_events(run_id, batch_size=5_000):
        if event.event_id == event_id:
            return event
    return None


def _query_text(query: SearchQuery) -> str:
    """Return the query text used for text-like modes."""
    if query.mode == "tool":
        return "" if query.text is None else query.text
    if query.mode == "prompt":
        return "" if query.text is None else query.text
    if query.mode == "error":
        return "" if query.text is None else query.text
    if query.mode == "provider":
        return "" if query.text is None else query.text
    if query.mode == "model":
        return "" if query.text is None else query.text
    return "" if query.text is None else query.text


def _fts_query(value: str) -> str:
    """Return a conservative FTS query."""
    tokens = [token for token in re.split(r"\W+", value) if token]
    if not tokens:
        return '""'
    return " AND ".join(f'"{token}"' for token in tokens)


def _compile_regex(text: str, query: SearchQuery) -> re.Pattern[str]:
    """Compile a user regex with configured case sensitivity."""
    flags = 0 if query.case_sensitive else re.IGNORECASE
    try:
        return re.compile(text, flags)
    except re.error as exc:
        msg = f"Invalid AgentReplay search regex: {exc}"
        raise PerformanceError(msg) from exc


def _match_event(
    event: EventRecord,
    query: SearchQuery,
    *,
    text: str,
    regex: re.Pattern[str] | None,
) -> SearchResult | None:
    """Return a search result when an event matches a query."""
    if not _matches_event_type(event, query):
        return None
    if query.mode == "metadata":
        return _metadata_result(event, query)
    searchable = _mode_text(event, query.mode)
    matched = (
        bool(regex.search(searchable))
        if regex
        else _contains(searchable, text, query.case_sensitive)
    )
    if not matched:
        return None
    return SearchResult(
        event=event,
        score=1.0,
        snippet=_snippet(event, text, query.case_sensitive),
        matched_fields=_matched_fields(event, text, query.case_sensitive),
    )


def _metadata_result(event: EventRecord, query: SearchQuery) -> SearchResult | None:
    """Return a search result for metadata predicates."""
    if query.metadata_key is None:
        return None
    value = event.metadata.get(query.metadata_key)
    if value is None:
        return None
    value_text = _json_text(value)
    if query.metadata_value is not None and not _contains(
        value_text,
        query.metadata_value,
        query.case_sensitive,
    ):
        return None
    return SearchResult(
        event=event,
        score=1.0,
        snippet=f"{query.metadata_key}={value_text[:160]}",
        matched_fields=(f"metadata.{query.metadata_key}",),
    )


def _matches_event_type(event: EventRecord, query: SearchQuery) -> bool:
    """Return whether an event type passes the query filter."""
    return not query.event_types or event.event_type in query.event_types


def _mode_text(event: EventRecord, mode: str) -> str:
    """Return searchable text scoped to a mode."""
    if mode == "tool":
        return _selected_text(
            event.payload, ("tool_name", "function_name", "arguments", "result")
        )
    if mode == "prompt":
        return _selected_text(
            event.payload, ("prompt", "messages", "input", "instructions")
        )
    if mode == "error":
        return _selected_text(
            event.payload, ("error", "exception", "warning", "message")
        )
    if mode == "provider":
        return _selected_text(event.payload, ("provider", "provider_name"))
    if mode == "model":
        return _selected_text(event.payload, ("model", "model_name"))
    return _event_text(event)


def _selected_text(mapping: Mapping[str, object], keys: tuple[str, ...]) -> str:
    """Return JSON text for selected payload keys."""
    values = [mapping[key] for key in keys if key in mapping]
    return " ".join(_json_text(value) for value in values)


def _event_text(event: EventRecord) -> str:
    """Return indexed text for one event."""
    parts: list[str] = [event.event_id, event.event_type]
    parts.extend(_field_values(event.payload, _SEARCH_FIELDS))
    parts.extend(_field_values(event.metadata, _SEARCH_FIELDS))
    return " ".join(parts)


def _field_values(
    mapping: Mapping[str, object], keys: tuple[str, ...]
) -> Iterator[str]:
    """Yield textual values for interesting keys."""
    for key in keys:
        if key in mapping:
            yield _json_text(mapping[key])


def _json_text(value: object) -> str:
    """Return stable JSON-ish text for a recorded value."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return repr(value)


def _contains(value: str, needle: str, case_sensitive: bool) -> bool:
    """Return whether text contains a needle."""
    if not needle:
        return True
    if case_sensitive:
        return needle in value
    return needle.casefold() in value.casefold()


def _matched_fields(
    event: EventRecord,
    text: str,
    case_sensitive: bool,
) -> tuple[str, ...]:
    """Return payload/metadata fields containing a search term."""
    fields: list[str] = []
    for owner, mapping in (("payload", event.payload), ("metadata", event.metadata)):
        for key, value in mapping.items():
            if _contains(_json_text(value), text, case_sensitive):
                fields.append(f"{owner}.{key}")
    return tuple(fields or ("event",))


def _snippet(event: EventRecord, text: str, case_sensitive: bool) -> str:
    """Return a short search snippet."""
    body = _event_text(event)
    if not text:
        return body[:180]
    haystack = body if case_sensitive else body.casefold()
    needle = text if case_sensitive else text.casefold()
    index = haystack.find(needle)
    if index < 0:
        return body[:180]
    start = max(0, index - 60)
    end = min(len(body), index + len(text) + 60)
    return body[start:end]


__all__ = ["BackgroundIndexer", "TraceSearchEngine"]
