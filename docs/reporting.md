# AgentReplay Reporting

AgentReplay can generate standalone offline HTML reports from recorded traces.
Reports are designed for debugging, auditing, sharing, and post-run review. They
consume existing trace data only and never execute agents, tools, replay logic,
diff logic, or LLM calls.

## Quick Start

```bash
agentreplay report RUN_ID --output report.html
agentreplay report latest --dark --compress --output report.html
agentreplay report RUN1 --compare RUN2 --light --output comparison.html
```

The generated HTML is self-contained: no CDN, no external CSS, no external
JavaScript, and no internet connection required.

## Python API

```python
from agentreplay import ReportingEngine, ReportOptions
from agentreplay.reporting.renderers import render_html, render_json_bundle

engine = ReportingEngine()
bundle = engine.generate("run-id", options=ReportOptions(theme="dark"))

html = render_html(bundle)
json_bundle = render_json_bundle(bundle)
```

## Report Sections

Reports include overview metrics, run summary, execution timeline, execution
graph, trace tree, statistics, latency analysis, token analysis, cost analysis,
tool usage, model usage, memory usage, errors, warnings, retries, metadata,
security findings, profiler results, and optimization suggestions.

## Execution Graph

The HTML report embeds an interactive DAG with zoom controls, path highlighting,
collapse/expand behavior, node details, keyboard focus, and search-driven
filtering. The graph is rendered from recorded parent-child event relationships
and sequence order.

## Timeline

The visual timeline shows recorded prompts, LLM calls, tools, memory events,
responses, durations, categories, and nesting depth. Search and filters update
the visible timeline without requiring external assets.

## Search And Filters

The report embeds a client-side search index covering prompt text, tool names,
model names, providers, errors, metadata, and regex-compatible queries. Filters
cover errors, warnings, tools, models, memory, slow events, expensive events,
and retries.

## Diff Reports

When `--compare RUN2` is provided, the report includes side-by-side comparison
data for added, removed, and modified events, execution path differences,
latency differences, cost differences, and token differences.

## Exports

The reporting renderer supports standalone HTML, PDF-ready HTML, Markdown
summary, JSON bundle, and ZIP package outputs. The CLI currently writes HTML,
while the Python API exposes the full renderer set.

## Themes And Accessibility

Reports support dark, light, print, and high-contrast presentation. The HTML
includes semantic sections, labels, keyboard-focusable controls, a skip link,
screen-reader labels, and responsive layout rules.

## Customization

Plugins can register custom report sections, charts, and widgets through
`PluginApp.register_report_section()`, `PluginApp.register_report_chart()`, and
`PluginApp.register_report_widget()`. Extension failures are isolated so a
broken plugin cannot prevent the base report from being generated.

## Performance Notes

Storage-backed report generation streams events from SQLite in batches. The
report keeps aggregate data for the whole run and caps visualization rows by
`ReportOptions.visualization_limit` to keep very large reports responsive.
