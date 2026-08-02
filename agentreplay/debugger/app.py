"""Textual terminal UI for AgentReplay time travel debugging."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, cast

from textual.app import App, ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, RichLog, Static, Tree

from agentreplay.debugger.models import DebuggerTheme, SearchQuery
from agentreplay.debugger.renderers import (
    render_event_export,
    render_event_inspection,
    render_metadata,
    render_stats,
)
from agentreplay.debugger.session import DebuggerSession
from agentreplay.diff import DiffEngine
from agentreplay.exceptions import DebuggerError, DiffError
from agentreplay.replay.playback import TimelineEntry
from agentreplay.storage import StorageBackend


class PromptScreen(ModalScreen[str | None]):
    """Small modal input screen for jump, timestamp, and search commands."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, prompt: str) -> None:
        """Create a prompt screen."""
        super().__init__()
        self._prompt = prompt

    def compose(self) -> ComposeResult:
        """Compose prompt widgets."""
        yield Vertical(
            Label(self._prompt),
            Input(),
            id="debugger-prompt",
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Dismiss the modal with the submitted value."""
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        """Dismiss the modal without a value."""
        self.dismiss(None)


class DebuggerApp(App[None]):
    """Full-screen Textual debugger for recorded AgentReplay runs."""

    CSS = """
    Screen {
        background: $surface;
        color: $text;
    }

    #main-layout {
        height: 1fr;
    }

    #left-panel {
        width: 30%;
        min-width: 24;
        border: solid $primary;
    }

    #center-panel {
        width: 45%;
        min-width: 32;
        border: solid $accent;
    }

    #right-panel {
        width: 25%;
        min-width: 24;
        border: solid $secondary;
    }

    #logs {
        height: 8;
        border: solid $panel-lighten-2;
    }

    .panel-title {
        padding: 0 1;
        text-style: bold;
    }

    #current-event,
    #metadata {
        padding: 1;
        overflow-y: auto;
    }

    #debugger-prompt {
        width: 70%;
        height: auto;
        margin: 2 4;
        padding: 1 2;
        border: solid $primary;
        background: $panel;
    }
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("n", "next_event", "Next"),
        Binding("p", "previous_event", "Previous"),
        Binding("j", "jump_to_event", "Jump"),
        Binding("g", "go_to_timestamp", "Timestamp"),
        Binding("f", "search", "Search"),
        Binding("t", "timeline", "Timeline"),
        Binding("e", "expand", "Expand"),
        Binding("c", "collapse", "Collapse"),
        Binding("i", "inspect", "Inspect"),
        Binding("m", "metadata", "Metadata"),
        Binding("l", "logs", "Logs"),
        Binding("d", "diff_current_event", "Diff"),
        Binding("s", "statistics", "Stats"),
        Binding("r", "replay_from_current", "Replay"),
        Binding("q", "quit", "Quit"),
        Binding("question_mark", "help", "Help"),
    ]

    def __init__(
        self,
        *,
        session: DebuggerSession,
        theme: DebuggerTheme = "dark",
        storage: StorageBackend | None = None,
        diff_run_id: str | None = None,
    ) -> None:
        """Create the debugger application."""
        super().__init__()
        self.session = session
        self._debugger_theme = theme
        self.storage = storage
        self.diff_run_id = diff_run_id

    def compose(self) -> ComposeResult:
        """Compose the debugger panels."""
        yield Header(show_clock=True)
        with Horizontal(id="main-layout"):
            with Vertical(id="left-panel"):
                yield Static("Execution Tree", classes="panel-title")
                yield Tree(f"Run {self.session.run_id}", id="execution-tree")
            with Vertical(id="center-panel"):
                yield Static("Current Event", classes="panel-title")
                yield Static("", id="current-event")
            with Vertical(id="right-panel"):
                yield Static("Metadata", classes="panel-title")
                yield Static("", id="metadata")
        yield RichLog(id="logs", wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        """Initialize theme and panel content."""
        self.dark = self._debugger_theme == "dark"
        self.session.log(f"Debugger loaded run {self.session.run_id}.")
        self._refresh_all()

    def action_next_event(self) -> None:
        """Move to the next event."""
        self.session.next_event()
        self._refresh_all()

    def action_previous_event(self) -> None:
        """Move to the previous event."""
        self.session.previous_event()
        self._refresh_all()

    def action_jump_to_event(self) -> None:
        """Prompt for an event id and jump to it."""
        self.push_screen(PromptScreen("Jump to event id"), self._jump_to_event)

    def action_go_to_timestamp(self) -> None:
        """Prompt for an ISO timestamp and jump to it."""
        self.push_screen(PromptScreen("Go to ISO timestamp"), self._go_to_timestamp)

    def action_search(self) -> None:
        """Prompt for a search query and navigate to the first match."""
        self.push_screen(PromptScreen("Search events"), self._search)

    def action_timeline(self) -> None:
        """Log the current virtualized timeline window."""
        lines = [
            _entry_line(entry, selected=entry.index == self.session.index)
            for entry in self.session.event_window(size=80)
        ]
        self._write_logs("Timeline", lines)

    def action_expand(self) -> None:
        """Expand the current event subtree."""
        self.session.expand_current()
        self._refresh_all()

    def action_collapse(self) -> None:
        """Collapse the current event subtree."""
        self.session.collapse_current()
        self._refresh_all()

    def action_inspect(self) -> None:
        """Focus and refresh the current event panel."""
        self.query_one("#current-event", Static).focus()
        self._refresh_event()

    def action_metadata(self) -> None:
        """Focus and refresh the metadata panel."""
        self.query_one("#metadata", Static).focus()
        self._refresh_metadata()

    def action_logs(self) -> None:
        """Focus the logs panel."""
        self.query_one("#logs", RichLog).focus()

    def action_diff_current_event(self) -> None:
        """Compare the current event with a configured comparison run."""
        entry = self.session.current_entry()
        if entry is None:
            self.session.log("No current event to diff.")
            self._refresh_logs()
            return
        if self.diff_run_id is None:
            self.session.log("Start with --diff-run to enable current event diffing.")
            self._refresh_logs()
            return
        if self.storage is None:
            self.session.log("Current event diff requires storage-backed debugging.")
            self._refresh_logs()
            return
        try:
            result = DiffEngine(storage=self.storage).compare(
                self.session.run_id,
                self.diff_run_id,
            )
        except DiffError as exc:
            self.session.log(f"Diff failed: {exc}")
            self._refresh_logs()
            return
        event_id = entry.event.event_id
        changes = [
            change
            for change in result.changes
            if change.old_event_id == event_id or change.new_event_id == event_id
        ]
        if not changes:
            self.session.log(f"No differences found for {event_id}.")
        for change in changes[:20]:
            self.session.log(
                f"{change.severity.upper()} {change.location}: {change.description}"
            )
        self._refresh_logs()

    def action_statistics(self) -> None:
        """Display execution statistics."""
        self._write_logs(
            "Statistics",
            render_stats(self.session.statistics()).splitlines(),
        )

    def action_replay_from_current(self) -> None:
        """Log a read-only replay window from the current position."""
        entries = self.session.replay_session.timeline.entries[self.session.index :]
        lines = [_entry_line(entry, selected=False) for entry in entries[:80]]
        self._write_logs("Replay From Current Position", lines)

    def action_help(self) -> None:
        """Display debugger keyboard shortcuts."""
        self._write_logs(
            "Keyboard Shortcuts",
            [
                "N next event",
                "P previous event",
                "J jump to event",
                "G go to timestamp",
                "F search",
                "T timeline",
                "E expand",
                "C collapse",
                "I inspect",
                "M metadata",
                "L logs",
                "D diff current event",
                "S statistics",
                "R replay from current position",
                "Q quit",
                "? help",
            ],
        )

    def export_current_to_clipboard(self) -> bool:
        """Copy the current event JSON to the terminal clipboard."""
        entry = self.session.current_entry()
        if entry is None:
            return False
        self.copy_to_clipboard(render_event_export(entry, "clipboard"))
        self.session.log(f"Copied event {entry.event.event_id} to clipboard.")
        self._refresh_logs()
        return True

    def _jump_to_event(self, value: str | None) -> None:
        """Handle jump prompt results."""
        if value is None or not value.strip():
            return
        try:
            self.session.jump_to_event(value.strip())
        except DebuggerError as exc:
            self.session.log(str(exc))
        self._refresh_all()

    def _go_to_timestamp(self, value: str | None) -> None:
        """Handle timestamp prompt results."""
        if value is None or not value.strip():
            return
        try:
            self.session.go_to_timestamp(datetime.fromisoformat(value.strip()))
        except (DebuggerError, ValueError) as exc:
            self.session.log(str(exc))
        self._refresh_all()

    def _search(self, value: str | None) -> None:
        """Handle search prompt results."""
        if value is None or not value.strip():
            return
        try:
            matches = self.session.search(SearchQuery(value.strip()))
        except ValueError as exc:
            self.session.log(str(exc))
            matches = ()
        self._refresh_all()
        if matches:
            self._write_logs(
                "Search Results",
                [
                    f"{match.event_id} [{match.field}] {match.excerpt}"
                    for match in matches[:80]
                ],
            )

    def _refresh_all(self) -> None:
        """Refresh every debugger panel."""
        self._refresh_tree()
        self._refresh_event()
        self._refresh_metadata()
        self._refresh_logs()

    def _refresh_tree(self) -> None:
        """Refresh the execution tree panel."""
        tree = cast(Tree[str], self.query_one("#execution-tree", Tree))
        tree.clear()
        root = tree.root
        for entry in self.session.event_window(size=400):
            line = _entry_line(entry, selected=entry.index == self.session.index)
            root.add(line)
        root.expand()

    def _refresh_event(self) -> None:
        """Refresh the current event panel."""
        inspection = self.session.inspect_current()
        panel = self.query_one("#current-event", Static)
        if inspection is None:
            panel.update("No events recorded.")
            return
        panel.update(render_event_inspection(inspection))

    def _refresh_metadata(self) -> None:
        """Refresh the metadata panel."""
        inspection = self.session.inspect_current()
        panel = self.query_one("#metadata", Static)
        if inspection is None:
            panel.update("No metadata recorded.")
            return
        panel.update(render_metadata(inspection.metadata))

    def _refresh_logs(self) -> None:
        """Refresh the logs panel."""
        log = self.query_one("#logs", RichLog)
        log.clear()
        for message in self.session.logs[-200:]:
            log.write(message)
        entry = self.session.current_entry()
        if entry is not None:
            log.write(
                f"Status: run={self.session.run_id} "
                f"event={entry.index + 1}/"
                f"{len(self.session.replay_session.timeline.entries)} "
                f"id={entry.event.event_id}"
            )

    def _write_logs(self, title: str, lines: list[str]) -> None:
        """Replace logs with a titled message set."""
        self.session.log(f"{title}:")
        for line in lines:
            self.session.log(line)
        self._refresh_logs()


def _entry_line(entry: TimelineEntry, *, selected: bool) -> str:
    """Return one line for a timeline entry."""
    marker = ">" if selected else " "
    indent = "  " * entry.depth
    parallel = " [parallel]" if entry.is_concurrent else ""
    return f"{marker} {indent}{entry.label}{parallel} {entry.event.event_id}"


__all__ = ["DebuggerApp", "PromptScreen"]
