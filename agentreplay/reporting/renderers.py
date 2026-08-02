"""Render AgentReplay report bundles into offline artifacts."""

from __future__ import annotations

import html
import io
import json
import re
import zipfile

from agentreplay.reporting.models import ReportBundle


def render_html(bundle: ReportBundle, *, compress: bool | None = None) -> str:
    """Render a standalone offline HTML report."""
    compressed = bundle.assets_compressed if compress is None else compress
    payload = _json_script(bundle.to_dict())
    html_text = _html_document(bundle, payload)
    if compressed:
        return compress_html(html_text)
    return html_text


def render_markdown_summary(bundle: ReportBundle) -> str:
    """Render a Markdown report summary."""
    lines = [
        "# AgentReplay Trace Report",
        "",
        f"**Run:** `{bundle.run_id}`",
        f"**Name:** {bundle.run_name or '-'}",
        f"**Generated:** `{bundle.generated_at}`",
        "",
        "## Overview",
    ]
    lines.extend(f"- **{metric.label}:** {metric.value}" for metric in bundle.metrics)
    lines.extend(["", "## Profiler Results"])
    profiler = bundle.profiler
    lines.append(str(profiler.get("summary", "No profiler summary.")))
    lines.extend(["", "## Optimization Suggestions"])
    recommendations = profiler.get("recommendations", [])
    if isinstance(recommendations, list) and recommendations:
        for recommendation in recommendations:
            if isinstance(recommendation, dict):
                lines.append(
                    "- "
                    f"{recommendation.get('category', 'recommendation')}: "
                    f"{recommendation.get('description', '')}"
                )
    else:
        lines.append("No optimization suggestions generated.")
    if bundle.diff is not None:
        lines.extend(["", "## Diff Summary", str(bundle.diff.get("summary", ""))])
    return "\n".join(lines)


def render_json_bundle(bundle: ReportBundle, *, compress: bool = False) -> str:
    """Render a report bundle as JSON."""
    if compress:
        return json.dumps(bundle.to_dict(), sort_keys=True, separators=(",", ":"))
    return json.dumps(bundle.to_dict(), sort_keys=True, indent=2)


def render_zip_package(bundle: ReportBundle, *, compress: bool = True) -> bytes:
    """Render a ZIP package containing HTML, Markdown, and JSON artifacts."""
    html_report = render_html(bundle, compress=compress)
    markdown = render_markdown_summary(bundle)
    json_bundle = render_json_bundle(bundle, compress=compress)
    buffer = io.BytesIO()
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    with zipfile.ZipFile(buffer, mode="w", compression=compression) as archive:
        archive.writestr("report.html", html_report)
        archive.writestr("summary.md", markdown)
        archive.writestr("bundle.json", json_bundle)
    return buffer.getvalue()


def compress_html(value: str) -> str:
    """Compress HTML without changing embedded report semantics."""
    value = re.sub(r"\s*\n\s*", "", value)
    value = re.sub(r">\s+<", "><", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def _html_document(bundle: ReportBundle, payload: str) -> str:
    """Build the complete standalone HTML document."""
    title = html.escape(f"AgentReplay Report {bundle.run_id}")
    theme_class = f"theme-{html.escape(bundle.theme)}"
    extension_html = "\n".join(
        (
            '<section class="panel extension" data-extension-kind="'
            f'{html.escape(extension.kind)}">'
            f"<h2>{html.escape(extension.name)}</h2>"
            f"{extension.html}</section>"
        )
        for extension in bundle.extensions
    )
    diff_section = (
        '<section class="panel" id="diff-section">'
        "<h2>Diff Report - Side-by-side comparison</h2>"
        "<p>Added Events, Removed Events, Modified Events, Execution Path "
        "Differences, Latency Differences, Cost Differences, Token Differences</p>"
        '<div id="diff-summary"></div>'
        '<div class="diff-grid" id="diff-grid"></div></section>'
        if bundle.diff is not None
        else ""
    )
    return "\n".join(
        (
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            f"<title>{title}</title>",
            f"<style>{_css()}</style>",
            "</head>",
            f'<body class="{theme_class}">',
            '<a class="skip-link" href="#main">Skip to report content</a>',
            '<header class="hero" role="banner">',
            "<div>",
            "<p>AgentReplay Trace Report</p>",
            f"<h1>{html.escape(bundle.run_name or bundle.run_id)}</h1>",
            f"<span>Generated {html.escape(bundle.generated_at)}</span>",
            "</div>",
            '<div class="toolbar" role="toolbar" aria-label="Report controls">',
            '<button type="button" data-action="theme">Theme</button>',
            '<button type="button" data-action="contrast">High Contrast</button>',
            '<button type="button" data-action="print">Print</button>',
            "</div>",
            "</header>",
            '<main id="main" class="layout" tabindex="-1">',
            '<section class="panel overview" aria-labelledby="overview-title">',
            '<h2 id="overview-title">Overview</h2>',
            '<div class="metrics" id="metrics"></div>',
            "</section>",
            '<section class="panel controls" aria-labelledby="controls-title">',
            '<h2 id="controls-title">Search and Filters</h2>',
            '<label for="search-input">Search trace</label>',
            (
                '<input id="search-input" type="search" '
                'placeholder="Prompt, tool, model, provider, error, metadata, regex">'
            ),
            '<div class="filters" id="filters"></div>',
            "</section>",
            '<section class="panel" aria-labelledby="timeline-title">',
            '<h2 id="timeline-title">Execution Timeline</h2>',
            '<div class="timeline-toolbar">',
            '<button type="button" data-action="timeline-zoom-in">Zoom</button>',
            '<button type="button" data-action="timeline-reset">Reset</button>',
            "</div>",
            '<div id="timeline" class="timeline" role="list"></div>',
            "</section>",
            '<section class="panel graph-panel" aria-labelledby="graph-title">',
            '<h2 id="graph-title">Execution Graph</h2>',
            '<div class="graph-toolbar">',
            '<button type="button" data-action="graph-zoom-in">Zoom In</button>',
            '<button type="button" data-action="graph-zoom-out">Zoom Out</button>',
            '<button type="button" data-action="collapse">Collapse</button>',
            '<button type="button" data-action="expand">Expand</button>',
            '<button type="button" data-action="highlight">Highlight Path</button>',
            "</div>",
            '<svg id="graph" role="img" aria-label="Interactive execution DAG"></svg>',
            '<aside id="node-details" aria-live="polite"></aside>',
            "</section>",
            '<section class="panel" aria-labelledby="tree-title">',
            '<h2 id="tree-title">Trace Tree</h2>',
            '<div id="trace-tree"></div>',
            "</section>",
            '<section class="panel charts" aria-labelledby="charts-title">',
            '<h2 id="charts-title">Statistics and Visualizations</h2>',
            '<div id="chart-grid" class="chart-grid"></div>',
            "</section>",
            '<section class="panel" aria-labelledby="analysis-title">',
            '<h2 id="analysis-title">Profiler Results</h2>',
            '<div id="analysis-grid" class="analysis-grid"></div>',
            "</section>",
            '<section class="panel" aria-labelledby="security-title">',
            '<h2 id="security-title">Security Findings</h2>',
            '<div id="security-findings"></div>',
            "</section>",
            diff_section,
            '<section class="panel" aria-labelledby="metadata-title">',
            '<h2 id="metadata-title">Metadata</h2>',
            '<pre id="metadata"></pre>',
            "</section>",
            extension_html,
            "</main>",
            f'<script type="application/json" id="agentreplay-report-data">{payload}</script>',
            f"<script>{_js()}</script>",
            "</body>",
            "</html>",
        )
    )


def _json_script(value: object) -> str:
    """Serialize JSON safely inside a script tag."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _css() -> str:
    """Return embedded report CSS."""
    return r"""
:root{color-scheme:dark;--bg:#0f172a;--panel:#111827;--text:#e5e7eb;--muted:#94a3b8;--accent:#38bdf8;--good:#22c55e;--warn:#f59e0b;--bad:#ef4444;--line:#334155}
.theme-light{color-scheme:light;--bg:#f8fafc;--panel:#ffffff;--text:#0f172a;--muted:#475569;--accent:#0369a1;--good:#15803d;--warn:#b45309;--bad:#b91c1c;--line:#cbd5e1}
.theme-print{color-scheme:light;--bg:#fff;--panel:#fff;--text:#111;--muted:#444;--accent:#000;--good:#000;--warn:#000;--bad:#000;--line:#bbb}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
button,input{font:inherit}button{border:1px solid var(--line);background:var(--panel);color:var(--text);padding:.45rem .7rem;border-radius:6px;cursor:pointer}button:focus,input:focus,.node:focus{outline:3px solid var(--accent);outline-offset:2px}
.skip-link{position:absolute;left:-999px;top:auto}.skip-link:focus{left:1rem;top:1rem;background:var(--panel);padding:.5rem;z-index:10}
.hero{display:flex;justify-content:space-between;gap:1rem;align-items:center;padding:1.5rem 2rem;border-bottom:1px solid var(--line);background:linear-gradient(135deg,var(--panel),var(--bg))}
.hero h1{margin:.2rem 0;font-size:clamp(1.6rem,4vw,3rem)}.hero p,.hero span{margin:0;color:var(--muted)}.toolbar,.graph-toolbar,.timeline-toolbar,.filters{display:flex;flex-wrap:wrap;gap:.5rem}
.layout{width:min(1480px,calc(100% - 2rem));margin:1rem auto 3rem;display:grid;grid-template-columns:repeat(12,1fr);gap:1rem}.panel{grid-column:span 12;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:1rem;box-shadow:0 20px 60px #0002}
.overview,.controls{grid-column:span 6}.graph-panel{grid-column:span 8}.charts{grid-column:span 4}.metrics,.analysis-grid,.chart-grid,.diff-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem}.metric,.card{border:1px solid var(--line);border-radius:6px;padding:.75rem;background:color-mix(in srgb,var(--panel) 84%,var(--accent))}
.metric strong{display:block;font-size:1.35rem}.muted{color:var(--muted)}#search-input{width:100%;box-sizing:border-box;border:1px solid var(--line);background:var(--bg);color:var(--text);border-radius:6px;padding:.65rem;margin:.35rem 0 .75rem}
.timeline{height:420px;overflow:auto;border:1px solid var(--line);border-radius:6px}.timeline-row{display:grid;grid-template-columns:120px 1fr 90px;gap:.75rem;align-items:center;padding:.45rem .7rem;border-bottom:1px solid var(--line)}.timeline-bar{height:10px;border-radius:99px;background:var(--accent);min-width:6px}.timeline-row[data-category=errors]{color:var(--bad)}.timeline-row[data-category=warnings]{color:var(--warn)}
#graph{width:100%;height:560px;border:1px solid var(--line);border-radius:6px;background:var(--bg);touch-action:none}.edge{stroke:var(--line);stroke-width:2}.node circle{fill:var(--panel);stroke:var(--accent);stroke-width:2}.node.error circle{stroke:var(--bad)}.node.warning circle{stroke:var(--warn)}.node.slow circle{stroke:var(--warn)}.node text{fill:var(--text);font-size:12px}.node.selected circle{fill:var(--accent);stroke:var(--text)}
#node-details{margin-top:.75rem;color:var(--muted)}#trace-tree{max-height:520px;overflow:auto}.tree-row{padding:.3rem .5rem;border-bottom:1px solid var(--line)}pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);border:1px solid var(--line);padding:.75rem;border-radius:6px}
.high-contrast{--bg:#000;--panel:#000;--text:#fff;--muted:#fff;--accent:#ff0;--line:#fff}.hidden{display:none!important}
@media(max-width:900px){.overview,.controls,.graph-panel,.charts{grid-column:span 12}.hero{align-items:flex-start;flex-direction:column}.timeline-row{grid-template-columns:1fr}}
@media print{body{background:#fff;color:#000}.toolbar,.controls,.graph-toolbar,.timeline-toolbar{display:none}.panel{break-inside:avoid;box-shadow:none}}
"""


def _js() -> str:
    """Return embedded report JavaScript."""
    return r"""
(() => {
  const data = JSON.parse(document.getElementById("agentreplay-report-data").textContent);
  let activeFilter = "all";
  let searchText = "";
  let graphScale = 1;
  let graphOffset = {x: 40, y: 40};
  const $ = (id) => document.getElementById(id);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const metricTone = (tone) => tone === "success" ? "good" : tone === "warning" ? "warn" : "neutral";
  function renderMetrics(){
    $("metrics").innerHTML = data.metrics.map(metric => `<article class="metric ${metricTone(metric.tone)}"><span>${escapeHtml(metric.label)}</span><strong>${escapeHtml(metric.value)}</strong></article>`).join("");
  }
  function matches(item){
    const categoryOk = activeFilter === "all" || item.category === activeFilter || (activeFilter === "slow" && item.duration_ms >= 1000) || (activeFilter === "expensive" && (data.profiler.cost_analysis?.cost_per_request?.[item.event_id] || 0) > 0);
    if(!categoryOk) return false;
    if(!searchText) return true;
    const doc = data.search_index.find(entry => entry.event_id === item.event_id);
    try { return new RegExp(searchText, "i").test(doc ? doc.text : ""); }
    catch { return (doc ? doc.text : "").toLowerCase().includes(searchText.toLowerCase()); }
  }
  function renderFilters(){
    const filters = ["all","errors","warnings","tools","models","memory","slow","expensive","retries"];
    $("filters").innerHTML = filters.map(name => `<button type="button" data-filter="${name}" aria-pressed="${activeFilter === name}">${name} (${name === "all" ? data.timeline.length : (data.filter_counts[name] || 0)})</button>`).join("");
  }
  function renderTimeline(){
    const rows = data.timeline.filter(matches);
    $("timeline").innerHTML = rows.map(item => `<div class="timeline-row" data-category="${item.category}" role="listitem" tabindex="0" title="${escapeHtml(item.event_type)}"><span>${escapeHtml(item.label)}</span><div class="timeline-bar" style="width:${Math.max(6, Math.min(100, item.duration_ms / 20))}%"></div><span>${Number(item.duration_ms).toFixed(2)} ms</span></div>`).join("");
  }
  function renderTree(){
    $("trace-tree").innerHTML = data.trace_tree.filter(matches).map(item => `<div class="tree-row" style="padding-left:${item.depth * 18 + 8}px"><strong>${escapeHtml(item.label)}</strong> <span class="muted">${escapeHtml(item.event_id)}</span></div>`).join("");
  }
  function renderGraph(){
    const svg = $("graph");
    const width = svg.clientWidth || 900;
    const nodes = data.nodes.filter(node => {
      const timeline = data.timeline.find(item => item.event_id === node.event_id);
      return timeline ? matches(timeline) : true;
    });
    const positions = new Map(nodes.map((node, index) => [node.event_id, {x: graphOffset.x + (index % 5) * 180 * graphScale, y: graphOffset.y + Math.floor(index / 5) * 95 * graphScale}]));
    const edges = data.edges.filter(edge => positions.has(edge.source_event_id) && positions.has(edge.target_event_id)).map(edge => {
      const source = positions.get(edge.source_event_id); const target = positions.get(edge.target_event_id);
      return `<line class="edge" x1="${source.x}" y1="${source.y}" x2="${target.x}" y2="${target.y}"></line>`;
    }).join("");
    const nodeMarkup = nodes.map(node => {
      const position = positions.get(node.event_id);
      return `<g class="node ${node.severity}" tabindex="0" data-node="${escapeHtml(node.event_id)}" transform="translate(${position.x},${position.y})"><circle r="${22 * graphScale}"></circle><text x="${30 * graphScale}" y="4">${escapeHtml(node.label)}</text></g>`;
    }).join("");
    svg.setAttribute("viewBox", `0 0 ${width} 620`);
    svg.innerHTML = edges + nodeMarkup;
  }
  function renderCharts(){
    const p = data.profiler;
    const cards = [
      ["Latency Histogram", p.visualizations?.latency_histogram],
      ["Token Histogram", p.visualizations?.token_histogram],
      ["Cost Breakdown", Object.entries(p.visualizations?.cost_breakdown || {}).map(([label,count]) => ({label,count}))],
      ["Provider Pie", Object.entries(p.visualizations?.pie_charts?.providers || {}).map(([label,count]) => ({label,count}))]
    ];
    $("chart-grid").innerHTML = cards.map(([title, rows]) => `<article class="card"><h3>${escapeHtml(title)}</h3>${barRows(rows || [])}</article>`).join("");
  }
  function barRows(rows){
    const max = Math.max(1, ...rows.map(row => Number(row.count || row[1] || 0)));
    return rows.map(row => {
      const label = row.label ?? row[0]; const count = Number(row.count ?? row[1] ?? 0);
      return `<div><span>${escapeHtml(label)}</span><div class="timeline-bar" style="width:${Math.max(4, count / max * 100)}%"></div><small>${count}</small></div>`;
    }).join("") || '<p class="muted">No chart data.</p>';
  }
  function renderAnalysis(){
    const profiler = data.profiler;
    const recommendations = profiler.recommendations || [];
    $("analysis-grid").innerHTML = [
      card("Latency Analysis", `P95 ${profiler.duration?.p95_ms ?? 0} ms<br>P99 ${profiler.duration?.p99_ms ?? 0} ms`),
      card("Token Analysis", `Total ${profiler.token_analysis?.total_tokens ?? 0}<br>Average ${Number(profiler.token_analysis?.average_tokens ?? 0).toFixed(2)}`),
      card("Cost Analysis", `Total ${Number(profiler.cost_analysis?.total_cost ?? 0).toFixed(6)}<br>Monthly ${Number(profiler.cost_analysis?.estimated_monthly_cost ?? 0).toFixed(6)}`),
      card("Tool Usage", JSON.stringify(profiler.tool_analysis?.execution_distribution || {})),
      card("Model Usage", (profiler.model_analysis?.models_used || []).join(", ") || "No models"),
      card("Memory Usage", `Reads ${profiler.memory_analysis?.reads ?? 0}<br>Writes ${profiler.memory_analysis?.writes ?? 0}`),
      card("Errors / Warnings / Retries", `${data.filter_counts.errors || 0} errors<br>${data.filter_counts.warnings || 0} warnings<br>${data.filter_counts.retries || 0} retries`),
      card("Optimization Suggestions", recommendations.map(r => `${escapeHtml(r.category)}: ${escapeHtml(r.description)}`).join("<br>") || "No suggestions")
    ].join("");
  }
  function card(title, body){ return `<article class="card"><h3>${escapeHtml(title)}</h3><p>${body}</p></article>`; }
  function renderSecurity(){
    const findings = data.security.findings || [];
    $("security-findings").innerHTML = findings.length ? findings.map(f => `<div class="card"><strong>${escapeHtml(f.risk_level)} ${escapeHtml(f.category)}</strong><p>${escapeHtml(f.path)} ${escapeHtml(f.suggested_fix)}</p></div>`).join("") : '<p>No security findings.</p>';
  }
  function renderDiff(){
    if(!data.diff) return;
    $("diff-summary").textContent = data.diff.summary || "";
    const changes = data.diff.changes || [];
    $("diff-grid").innerHTML = changes.slice(0, 300).map(change => `<article class="card"><strong>${escapeHtml(change.change_type)} ${escapeHtml(change.category)}</strong><p>${escapeHtml(change.description)}</p><small>${escapeHtml(change.location)}</small></article>`).join("") || "<p>No differences found.</p>";
  }
  function renderMetadata(){ $("metadata").textContent = JSON.stringify(data.trace.run.metadata || {}, null, 2); }
  function renderAll(){ renderMetrics(); renderFilters(); renderTimeline(); renderTree(); renderGraph(); renderCharts(); renderAnalysis(); renderSecurity(); renderDiff(); renderMetadata(); }
  document.addEventListener("click", event => {
    const action = event.target?.dataset?.action; const filter = event.target?.dataset?.filter; const node = event.target?.closest?.(".node");
    if(filter){ activeFilter = filter; renderAll(); }
    if(action === "theme"){ document.body.classList.toggle("theme-light"); document.body.classList.toggle("theme-dark"); }
    if(action === "contrast"){ document.body.classList.toggle("high-contrast"); }
    if(action === "print"){ window.print(); }
    if(action === "graph-zoom-in"){ graphScale = Math.min(2, graphScale + .15); renderGraph(); }
    if(action === "graph-zoom-out"){ graphScale = Math.max(.5, graphScale - .15); renderGraph(); }
    if(action === "timeline-zoom-in"){ $("timeline").style.fontSize = "1.08rem"; }
    if(action === "timeline-reset"){ $("timeline").style.fontSize = ""; }
    if(action === "collapse"){ $("trace-tree").classList.add("hidden"); }
    if(action === "expand"){ $("trace-tree").classList.remove("hidden"); }
    if(action === "highlight"){ document.querySelectorAll(".node").forEach(item => item.classList.add("selected")); }
    if(node){ const id = node.dataset.node; const detail = data.nodes.find(item => item.event_id === id); $("node-details").textContent = detail ? `${detail.label} ${detail.event_type} ${detail.duration_ms} ms` : ""; }
  });
  $("search-input").addEventListener("input", event => { searchText = event.target.value; renderTimeline(); renderTree(); renderGraph(); });
  document.addEventListener("keydown", event => { if(event.key === "/"){ event.preventDefault(); $("search-input").focus(); } });
  renderAll();
})();
"""


__all__ = [
    "compress_html",
    "render_html",
    "render_json_bundle",
    "render_markdown_summary",
    "render_zip_package",
]
