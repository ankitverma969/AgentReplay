# AgentReplay Debugger

AgentReplay includes an offline interactive time travel debugger for recorded
agent executions. It never calls an LLM, never executes tools, and never mutates
stored runs. The debugger reads an existing trace from SQLite or an exported JSON
file and presents it in a full-screen terminal interface.

## Quick Start

```bash
agentreplay debug RUN_ID
agentreplay debug latest
agentreplay debug --file trace.json
```

Use `--db-path` to point at a specific SQLite database and `--theme light` to
switch out of the default dark theme.

## Layout

- Left panel: execution tree with event nesting and concurrent markers.
- Center panel: current event inspector.
- Right panel: metadata for the selected event.
- Bottom panel: debugger logs, timeline output, search results, statistics, and
  current position status.

## Keyboard Shortcuts

- `N`: next event.
- `P`: previous event.
- `J`: jump to an event id.
- `G`: go to an ISO timestamp.
- `F`: search visible events.
- `T`: show the current timeline window.
- `E`: expand the current event subtree.
- `C`: collapse the current event subtree.
- `I`: inspect current event.
- `M`: focus metadata.
- `L`: focus logs.
- `D`: diff the current event against `--diff-run`.
- `S`: show statistics.
- `R`: render replay output from the current position.
- `Q`: quit.
- `?`: show help.

## Search

Debugger search covers prompt text, model names, tool names, providers, event
types, metadata, errors, and warnings. The Python API also supports regular
expression search via `SearchQuery(regex=True)`.

## Filters

The session API supports filters for errors, warnings, tool events, LLM events,
memory events, slow events, expensive events, and retries. Filters are applied
before navigation and search, which keeps large traces responsive.

## Exports

The selected event can be rendered as JSON, Markdown, HTML, or clipboard-ready
JSON through the debugger renderer API. The Textual UI copies the selected event
to the terminal clipboard when integrated into higher-level keymaps or commands.

## Troubleshooting

If `agentreplay debug latest` reports that no runs exist, record a run or pass
the database path that contains the run with `--db-path`. If timestamp jumps do
not find a match, use an ISO timestamp at or before the desired event time.
