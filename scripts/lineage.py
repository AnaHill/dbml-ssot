#!/usr/bin/env python3
"""Generates a data lineage diagram (Mermaid flowchart) from the DBML source
(default: dbml/schema.dbml, or the whole dbml/ folder if schema.dbml is
missing).

You can pass a single file, a folder, or a list of names/files/folders in
the GIVEN order (see scripts/_dbml_source.py).

Reads each table's `source table:` and `notebook:` lines from its Note
field and draws a path from upstream source -> notebook -> table, grouped
into blocks matching the TableGroups (Lakehouse layers). If a source
matches a table already in the model (including in joins/unions —
separated by "+", "," or the word "join"/"union"/"union all", e.g.
"A + B (join)" or "A union all B"), an edge is drawn straight to that
table instead of creating a duplicate node — this keeps bronze->silver->
gold as one continuous path instead of Mermaid's layout stacking layers on
top of each other. FK relations (Ref) between tables are shown as dotted
lines. Tables missing source/notebook info (or where it's still TODO) are
marked with their own warning style instead of being drawn incorrectly or
left out.

Doesn't modify the DBML source — this is a purely generated view, not
another source of truth. Re-run whenever the DBML source changes.

-o file.md   -> a Mermaid code block to paste into/view in Obsidian,
                GitHub, etc. via native mermaid support.
-o file.html -> a standalone, interactive HTML file (mermaid.js from a
                CDN) — opens directly in the browser with a double-click,
                no dependency on VS Code, Obsidian, or any cloud service.
                Click a table (or several) to see its upstream/downstream
                path highlighted — each selected table gets its own color
                in selection order, and shared path segments are colored
                by the first-selected table. Click again to deselect a
                table, show/hide layers with the checkboxes.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from pydbml import PyDBML

from _dbml_source import describe_paths, read_dbml_paths, resolve_dbml_paths

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

SPLIT_SOURCE_RE = re.compile(r"\s*(?:\+|,|\bjoin\b|\bunion(?:\s+all)?\b)\s*", re.IGNORECASE)
TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def mermaid_id(text: str) -> str:
    ident = re.sub(r"[^A-Za-z0-9_]", "_", text)
    if not ident or ident[0].isdigit():
        ident = f"n_{ident}"
    return ident


def full_name(table) -> str:
    return f"{table.schema}.{table.name}" if table.schema else table.name


def parse_note(note_text: str) -> tuple[str | None, str | None, str | None]:
    source = notebook = mechanism = None
    for line in note_text.splitlines():
        line = line.strip()
        if line.lower().startswith("source table:"):
            source = line.split(":", 1)[1].strip()
        elif line.lower().startswith("notebook:"):
            notebook = line.split(":", 1)[1].strip()
        elif line.lower().startswith("mechanism:"):
            mechanism = line.split(":", 1)[1].strip()
    return source, notebook, mechanism


def is_missing(value: str | None) -> bool:
    return not value or value.strip().upper() == "TODO"


SOURCES_COLOR = "#D7A86E"  # bronze/tan tone for the Sources block

# Orchestration node coloring follows the optional `mechanism:` Note line
# (see AGENTS.md). An unrecognized/missing value -> "notebook" (default,
# keeps backward compatibility for existing tables that don't have this
# line). Deliberately does NOT infer the mechanism from the notebook/
# pipeline name's text (e.g. a path prefix) — different files already use
# different naming conventions for the same mechanism (see
# examples/generic_rdbms.dbml's "dbo.usp_..." vs. this model's
# "stored_procedures/usp_...", both stored-procedure-style but structurally
# different) — guessing would get it wrong.
MECHANISM_STYLES: dict[str, tuple[str, str]] = {
    "notebook": ("#B39DDB", "#6b5b95"),  # lavender
    "pipeline": ("#7FB3D5", "#2E6DA4"),  # blue
    "stored_procedure": ("#F5B971", "#B96A1E"),  # orange
}
DEFAULT_MECHANISM_STYLE = ("#B0B0B0", "#6b6b6b")  # unrecognized mechanism value (gray)


class Lineage:
    """The graph computed once from the DBML source. Both the text renderer
    (render_mermaid) and the JSON renderer (graph_json, for the interactive
    HTML) read this same structure, so the source/notebook interpretation
    logic lives in exactly one place."""

    def __init__(self, db):
        self.table_labels: dict[str, str] = {}
        self.node_layer: dict[str, str] = {}
        self.source_nodes: dict[str, str] = {}
        self.orch_nodes: dict[str, str] = {}
        self.orch_mechanism: dict[str, str] = {}
        self.lineage_edges: list[tuple[str, str]] = []
        self.todo_edges: list[tuple[str, str, str]] = []
        self.fk_edges: list[tuple[str, str]] = []
        self.groups: list[dict] = []

        table_ids = {full_name(t): mermaid_id(full_name(t)) for t in db.tables}
        grouped_ids: set[str] = set()

        for table in db.tables:
            tid = mermaid_id(full_name(table))
            self.table_labels[tid] = full_name(table)

            source = notebook = mechanism = None
            if table.note and getattr(table.note, "text", None):
                source, notebook, mechanism = parse_note(table.note.text)

            if is_missing(source) or is_missing(notebook):
                src_id = mermaid_id(f"todo_src_{tid}")
                nb_id = mermaid_id(f"todo_nb_{tid}")
                self.todo_edges.append((src_id, nb_id, tid))
                self.node_layer.setdefault(src_id, "sources")
                self.node_layer.setdefault(nb_id, "orchestration")
                continue

            nb_id = mermaid_id(f"nb_{notebook}")
            self.orch_nodes[nb_id] = notebook
            self.orch_mechanism[nb_id] = (mechanism or "notebook").strip().lower()

            source_clean = TRAILING_PAREN_RE.sub("", source).strip()
            parts = [p.strip() for p in SPLIT_SOURCE_RE.split(source_clean)]
            for part in (p for p in parts if p):
                if part in table_ids:
                    self.lineage_edges.append((table_ids[part], nb_id))
                else:
                    src_id = mermaid_id(f"src_{part}")
                    self.source_nodes[src_id] = part
                    self.lineage_edges.append((src_id, nb_id))

            self.lineage_edges.append((nb_id, tid))

        for group in db.table_groups:
            gid = mermaid_id(group.name)
            table_ids_in_group = []
            for table in group.items:
                tid = mermaid_id(full_name(table))
                table_ids_in_group.append(tid)
                grouped_ids.add(tid)
                self.node_layer[tid] = gid
            self.groups.append(
                {
                    "id": gid,
                    "name": group.name,
                    "color": group.color,
                    "tables": table_ids_in_group,
                }
            )

        self.ungrouped_ids = [
            mermaid_id(full_name(t))
            for t in db.tables
            if mermaid_id(full_name(t)) not in grouped_ids
        ]

        for ref in db.refs:
            t_from = mermaid_id(full_name(ref.col1[0].table))
            t_to = mermaid_id(full_name(ref.col2[0].table))
            self.fk_edges.append((t_from, t_to))

        for sid in self.source_nodes:
            self.node_layer.setdefault(sid, "sources")
        for nid in self.orch_nodes:
            self.node_layer.setdefault(nid, "orchestration")

    def all_node_ids(self):
        ids = set(self.table_labels) | set(self.source_nodes) | set(self.orch_nodes)
        for src_id, nb_id, _tid in self.todo_edges:
            ids.add(src_id)
            ids.add(nb_id)
        return ids


def render_mermaid(lin: Lineage, interactive: bool = False) -> str:
    lines = ["flowchart LR"]

    if lin.source_nodes:
        lines.append('  subgraph sources["Sources (external system or previous layer)"]')
        for nid, label in lin.source_nodes.items():
            lines.append(f'    {nid}["{label}"]')
        lines.append("  end")
        lines.append(f"  style sources fill:{SOURCES_COLOR}33,stroke:#8a6a3d")

    if lin.orch_nodes:
        # Not wrapped in a subgraph (unlike sources) — notebooks get their
        # own shape (hexagon) and per-node color via classDef, and settle
        # naturally in Mermaid's layout following their own edges (e.g. a
        # bronze->silver notebook lands between those two blocks) instead
        # of forcing every notebook from every transition into one visual
        # box regardless of its actual place in the pipeline.
        for nid, label in lin.orch_nodes.items():
            lines.append(f'  {nid}{{{{"{label}"}}}}')

        used_mechanisms = {lin.orch_mechanism.get(nid, "notebook") for nid in lin.orch_nodes}
        for mechanism in sorted(used_mechanisms):
            fill, stroke = MECHANISM_STYLES.get(mechanism, DEFAULT_MECHANISM_STYLE)
            class_name = f"mech_{mermaid_id(mechanism)}"
            lines.append(f"  classDef {class_name} fill:{fill},stroke:{stroke},color:#2d2140")
        for nid in lin.orch_nodes:
            mechanism = lin.orch_mechanism.get(nid, "notebook")
            lines.append(f"  class {nid} mech_{mermaid_id(mechanism)}")

    for group in lin.groups:
        lines.append(f'  subgraph {group["id"]}["{group["name"]}"]')
        for tid in group["tables"]:
            lines.append(f'    {tid}["{lin.table_labels[tid]}"]')
        lines.append("  end")
        if group["color"]:
            lines.append(f"  style {group['id']} fill:{group['color']}33,stroke:#666")

    for tid in lin.ungrouped_ids:
        lines.append(f'  {tid}["{lin.table_labels[tid]}"]')

    for idx, (a, b) in enumerate(lin.lineage_edges):
        # Interactive output only: an edge id (`e0@-->`) so the edge can be
        # animated below. The .md output stays on the plain `-->` form,
        # because GitHub's and Obsidian's bundled Mermaid may predate the
        # edge-id syntax (Mermaid 11.5+) and would render the diagram as an
        # error instead of a flowchart.
        arrow = f"e{idx}@-->" if interactive else "-->"
        lines.append(f"  {a} {arrow} {b}")

    for src_id, nb_id, tid in lin.todo_edges:
        lines.append(
            f'  {src_id}["TODO"]:::todo --> {nb_id}{{{{"TODO"}}}}:::todo --> {tid}'
        )

    for a, b in lin.fk_edges:
        lines.append(f"  {a} -.->|FK| {b}")

    lines.append("  classDef todo fill:#fff3cd,stroke:#e0a800,color:#7a5b00")

    if interactive:
        # Animate the direction of data movement (Mermaid 11.5+). Only
        # lineage edges get this — an FK edge is a structural relation, not
        # a flow, and a TODO edge is a warning about missing information.
        for idx in range(len(lin.lineage_edges)):
            lines.append(f"  e{idx}@{{ animate: true }}")

        # Mark every node with its own class name (= the node's own id),
        # known to us. This way the JS doesn't need to guess Mermaid's
        # internal, undocumented SVG id format to identify nodes — it's
        # enough to look for a name in classList that's found in graph.nodes.
        for node_id in sorted(lin.all_node_ids()):
            lines.append(f"  class {node_id} {node_id}")

    return "\n".join(lines)


def graph_json(lin: Lineage) -> str:
    nodes = {}
    for tid, label in lin.table_labels.items():
        nodes[tid] = {"label": label, "layer": lin.node_layer.get(tid)}
    for nid, label in lin.source_nodes.items():
        nodes[nid] = {"label": label, "layer": "sources"}
    for nid, label in lin.orch_nodes.items():
        nodes[nid] = {"label": label, "layer": "orchestration"}
    for src_id, nb_id, _tid in lin.todo_edges:
        nodes.setdefault(src_id, {"label": "TODO", "layer": "sources"})
        nodes.setdefault(nb_id, {"label": "TODO", "layer": "orchestration"})

    edges = [{"from": a, "to": b, "kind": "lineage"} for a, b in lin.lineage_edges]
    for src_id, nb_id, tid in lin.todo_edges:
        edges.append({"from": src_id, "to": nb_id, "kind": "todo"})
        edges.append({"from": nb_id, "to": tid, "kind": "todo"})
    edges += [{"from": a, "to": b, "kind": "fk"} for a, b in lin.fk_edges]

    layers = [{"id": "sources", "name": "Sources"}, {"id": "orchestration", "name": "Orchestration"}]
    layers += [{"id": g["id"], "name": g["name"]} for g in lin.groups]

    return json.dumps({"nodes": nodes, "edges": edges, "layers": layers}, ensure_ascii=False)


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Data lineage</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  :root {{
    /* Categorical color palette (validated, fixed order) — one color per
       selected table, in selection order. */
    --sel-1: #2a78d6; --sel-2: #eb6834; --sel-3: #1baf7a; --sel-4: #eda100;
    --sel-5: #e87ba4; --sel-6: #008300; --sel-7: #4a3aa7; --sel-8: #e34948;
  }}
  body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 2rem; }}
  h1 {{ font-size: 1.1rem; }}
  p.meta {{ color: #666; font-size: 0.85rem; }}
  .toolbar {{
    display: flex; flex-wrap: wrap; gap: 1.25rem; align-items: center;
    border: 1px solid #ddd; border-radius: 8px; padding: 0.75rem 1rem;
    margin: 1rem 0; font-size: 0.9rem; background: #fafafa;
  }}
  .toolbar fieldset {{ border: none; padding: 0; margin: 0; display: flex; gap: 0.75rem; }}
  .toolbar legend {{ font-size: 0.75rem; color: #666; padding: 0 0 0.2rem; }}
  .toolbar label {{ display: flex; align-items: center; gap: 0.3rem; cursor: pointer; }}
  .toolbar button {{
    cursor: pointer; border: 1px solid #ccc; background: #fff; border-radius: 6px;
    padding: 0.2rem 0.6rem; font-size: 0.95rem; line-height: 1.4;
  }}
  .zoom-controls {{ display: flex; align-items: center; gap: 0.4rem; }}
  #zoom-level {{ min-width: 3.5em; text-align: center; color: #666; }}
  .diagram-scroll {{
    border: 1px solid #ddd; border-radius: 8px;
    height: 75vh; min-height: 420px; overflow: auto; background: #fff;
    cursor: grab; user-select: none;
  }}
  .diagram-zoom {{ display: inline-block; transform-origin: 0 0; padding: 1rem; }}
  .node.dimmed {{ opacity: 0.12; }}
  .edge-dimmed {{ opacity: 0.08; }}
  /* Mermaid animates an edge by putting its own edge-animation-* class on
     the path. Switching the animation off is done by overriding that here
     rather than by removing the class, so nothing depends on Mermaid's
     internal class names surviving a version bump — if they change, the
     animation simply stays on and the checkbox stops biting. */
  .diagram-zoom.animation-off path[class*="edge-animation"] {{
    animation: none !important; stroke-dasharray: none !important;
  }}
  .node.sel-1 rect, .node.sel-1 polygon {{ stroke: var(--sel-1) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-1)); }}
  .node.sel-2 rect, .node.sel-2 polygon {{ stroke: var(--sel-2) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-2)); }}
  .node.sel-3 rect, .node.sel-3 polygon {{ stroke: var(--sel-3) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-3)); }}
  .node.sel-4 rect, .node.sel-4 polygon {{ stroke: var(--sel-4) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-4)); }}
  .node.sel-5 rect, .node.sel-5 polygon {{ stroke: var(--sel-5) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-5)); }}
  .node.sel-6 rect, .node.sel-6 polygon {{ stroke: var(--sel-6) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-6)); }}
  .node.sel-7 rect, .node.sel-7 polygon {{ stroke: var(--sel-7) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-7)); }}
  .node.sel-8 rect, .node.sel-8 polygon {{ stroke: var(--sel-8) !important; stroke-width: 5px !important; filter: drop-shadow(0 0 3px var(--sel-8)); }}
  path.edge-sel-1 {{ stroke: var(--sel-1) !important; stroke-width: 3px !important; }}
  path.edge-sel-2 {{ stroke: var(--sel-2) !important; stroke-width: 3px !important; }}
  path.edge-sel-3 {{ stroke: var(--sel-3) !important; stroke-width: 3px !important; }}
  path.edge-sel-4 {{ stroke: var(--sel-4) !important; stroke-width: 3px !important; }}
  path.edge-sel-5 {{ stroke: var(--sel-5) !important; stroke-width: 3px !important; }}
  path.edge-sel-6 {{ stroke: var(--sel-6) !important; stroke-width: 3px !important; }}
  path.edge-sel-7 {{ stroke: var(--sel-7) !important; stroke-width: 3px !important; }}
  path.edge-sel-8 {{ stroke: var(--sel-8) !important; stroke-width: 3px !important; }}
</style>
</head>
<body>
<h1>Data lineage — {source_file}</h1>
<p class="meta">Generated: python scripts/lineage.py {source_file} -o {output_file} — do not edit by hand, re-run when {source_file} changes. Pan with the scrollbars/trackpad, zoom with the +/- buttons or Ctrl+mouse wheel.</p>

<div class="toolbar">
  <fieldset>
    <legend>Show layers</legend>
    {layer_checkboxes}
  </fieldset>
  <div class="zoom-controls">
    <button id="zoom-out" type="button">−</button>
    <span id="zoom-level">100%</span>
    <button id="zoom-in" type="button">+</button>
    <button id="zoom-reset" type="button">Reset</button>
  </div>
  <label><input type="checkbox" id="animation-toggle" checked> Animate flow</label>
  <button id="clear-selection" type="button">Clear selection</button>
</div>

<div class="diagram-scroll">
<div class="diagram-zoom">
<pre class="mermaid">
{mermaid}
</pre>
</div>
</div>

<script id="graph-data" type="application/json">{graph_json}</script>
<script>
(async () => {{
  mermaid.initialize({{
    startOnLoad: false,
    securityLevel: "loose",
    flowchart: {{ useMaxWidth: false }},
  }});

  const graph = JSON.parse(document.getElementById("graph-data").textContent);
  const adjOut = {{}}, adjIn = {{}};
  for (const e of graph.edges) {{
    (adjOut[e.from] ??= []).push(e.to);
    (adjIn[e.to] ??= []).push(e.from);
  }}

  function reachable(startId, adj) {{
    const seen = new Set([startId]);
    const stack = [startId];
    while (stack.length) {{
      const cur = stack.pop();
      for (const next of (adj[cur] || [])) {{
        if (!seen.has(next)) {{ seen.add(next); stack.push(next); }}
      }}
    }}
    return seen;
  }}

  try {{
    await mermaid.run({{ querySelector: ".mermaid" }});
  }} catch (err) {{
    console.error("lineage: mermaid.run() failed", err);
    return;
  }}

  const svg = document.querySelector(".mermaid svg");
  if (!svg) {{
    console.error("lineage: no SVG found after rendering");
    return;
  }}
  svg.style.removeProperty("max-width");

  // Every node is tagged with a Mermaid "class" directive carrying its own
  // id (see lineage.py: `class <id> <id>`), so identification is done via
  // classList rather than Mermaid's internal (undocumented) id format.
  const nodeEls = new Map();
  svg.querySelectorAll(".node").forEach((el) => {{
    for (const cls of el.classList) {{
      if (Object.prototype.hasOwnProperty.call(graph.nodes, cls)) {{
        nodeEls.set(cls, el);
        break;
      }}
    }}
  }});
  if (nodeEls.size === 0) {{
    console.error("lineage: no nodes were recognized — class identifiers don't match");
  }}

  // Edges don't have our own class hook (Mermaid has no equivalent
  // directive for a single edge), so they're identified by render order:
  // graph.edges is produced in exactly the same order as the arrows in the
  // mermaid source. Best effort — if Mermaid ever reorders the edgePaths
  // nodes, the length comparison below will reveal it.
  const edgeEls = Array.from(svg.querySelectorAll("g.edgePaths path, path.flowchart-link"));
  console.info(`lineage: found ${{edgeEls.length}} edge element(s) in the SVG, data contains ${{graph.edges.length}} edge(s).`);
  if (edgeEls.length !== graph.edges.length) {{
    console.warn(
      "lineage: counts don't match — edge highlighting/hiding may be inaccurate. " +
      "Check svg.querySelectorAll('g.edgePaths path, path.flowchart-link') in the browser console."
    );
  }}

  // Mermaid draws its own label element for every edge in the
  // "edgeLabels" group (not part of the path element) — including ones
  // with no text (e.g. "FK") -> it's just empty. Same order/count as
  // edgeEls, so wired up by the same index.
  let labelEls = Array.from(svg.querySelectorAll("g.edgeLabels > g"));
  if (labelEls.length === 0) {{
    labelEls = Array.from(svg.querySelectorAll(".edgeLabel"));
  }}
  console.info(`lineage: found ${{labelEls.length}} edge label(s) (${{graph.edges.length}} edge(s) total).`);

  // Multi-select: selected is a SET of clicked nodes (insertion order is
  // preserved in a JS Set). Every selected node gets its own color from a
  // fixed palette (idToSlot), and its whole upstream/downstream path is
  // colored the same way. If two selections share the same node/edge, the
  // first-selected one (lowest slot index) "owns" that shared part — a
  // simple, deterministic rule instead of trying to color the same
  // element with several colors at once.
  const PALETTE_SIZE = 8;
  const SEL_CLASSES = Array.from({{ length: PALETTE_SIZE }}, (_, i) => `sel-${{i + 1}}`);
  const EDGE_SEL_CLASSES = Array.from({{ length: PALETTE_SIZE }}, (_, i) => `edge-sel-${{i + 1}}`);

  const selected = new Set();
  const idToSlot = new Map();

  function nextFreeSlot() {{
    const used = new Set(idToSlot.values());
    for (let i = 0; i < PALETTE_SIZE; i++) {{
      if (!used.has(i)) return i;
    }}
    return 0; // more than 8 simultaneous selections: recycle slot 0
  }}

  function updateHighlight() {{
    nodeEls.forEach((el) => el.classList.remove("dimmed", ...SEL_CLASSES));
    edgeEls.forEach((el) => el.classList.remove("edge-dimmed", ...EDGE_SEL_CLASSES));
    labelEls.forEach((el) => el.classList.remove("edge-dimmed", ...EDGE_SEL_CLASSES));

    if (selected.size === 0) return;

    const orderedSelected = [...selected];
    const reachBySelection = orderedSelected.map(
      (id) => new Set([...reachable(id, adjIn), ...reachable(id, adjOut)])
    );

    const keepAll = new Set();
    const nodeOwnerSlot = new Map();
    reachBySelection.forEach((reach, idx) => {{
      const slot = idToSlot.get(orderedSelected[idx]);
      reach.forEach((n) => {{
        keepAll.add(n);
        if (!nodeOwnerSlot.has(n)) nodeOwnerSlot.set(n, slot);
      }});
    }});

    function edgeOwnerSlot(edge) {{
      for (let idx = 0; idx < orderedSelected.length; idx++) {{
        if (reachBySelection[idx].has(edge.from) && reachBySelection[idx].has(edge.to)) {{
          return idToSlot.get(orderedSelected[idx]);
        }}
      }}
      return undefined;
    }}

    nodeEls.forEach((el, nid) => {{
      el.classList.toggle("dimmed", !keepAll.has(nid));
      const slot = selected.has(nid) ? idToSlot.get(nid) : nodeOwnerSlot.get(nid);
      if (slot !== undefined) el.classList.add(`sel-${{slot + 1}}`);
    }});

    edgeEls.forEach((el, i) => {{
      const edge = graph.edges[i];
      if (!edge) return;
      const slot = edgeOwnerSlot(edge);
      el.classList.toggle("edge-dimmed", slot === undefined);
      if (slot !== undefined) el.classList.add(`edge-sel-${{slot + 1}}`);
    }});

    labelEls.forEach((el, i) => {{
      const edge = graph.edges[i];
      if (!edge) return;
      el.classList.toggle("edge-dimmed", edgeOwnerSlot(edge) === undefined);
    }});
  }}

  function toggleSelect(id) {{
    if (selected.has(id)) {{
      selected.delete(id);
      idToSlot.delete(id);
    }} else {{
      selected.add(id);
      idToSlot.set(id, nextFreeSlot());
    }}
    updateHighlight();
  }}

  nodeEls.forEach((el, id) => {{
    el.style.cursor = "pointer";
    el.addEventListener("click", () => toggleSelect(id));
  }});

  document.getElementById("clear-selection").addEventListener("click", () => {{
    selected.clear();
    idToSlot.clear();
    updateHighlight();
  }});

  function currentHiddenLayers() {{
    const hidden = new Set();
    document.querySelectorAll("[data-layer-toggle]").forEach((cb) => {{
      if (!cb.checked) hidden.add(cb.dataset.layerToggle);
    }});
    return hidden;
  }}

  function applyLayerVisibility() {{
    const hidden = currentHiddenLayers();

    nodeEls.forEach((el, id) => {{
      el.style.display = hidden.has(graph.nodes[id].layer) ? "none" : "";
    }});

    edgeEls.forEach((el, i) => {{
      const edge = graph.edges[i];
      if (!edge) return;
      const fromLayer = graph.nodes[edge.from]?.layer;
      const toLayer = graph.nodes[edge.to]?.layer;
      el.style.display = (hidden.has(fromLayer) || hidden.has(toLayer)) ? "none" : "";
    }});

    labelEls.forEach((el, i) => {{
      const edge = graph.edges[i];
      if (!edge) return;
      const fromLayer = graph.nodes[edge.from]?.layer;
      const toLayer = graph.nodes[edge.to]?.layer;
      el.style.display = (hidden.has(fromLayer) || hidden.has(toLayer)) ? "none" : "";
    }});

    svg.querySelectorAll(".cluster").forEach((el) => {{
      const isHidden = [...hidden].some((layer) => el.id === layer || el.id.includes(layer));
      el.style.display = isHidden ? "none" : "";
    }});
  }}

  document.querySelectorAll("[data-layer-toggle]").forEach((cb) => {{
    cb.addEventListener("change", applyLayerVisibility);
  }});

  // Zoom via a simple CSS transform: scale(), plus the browser's own
  // scrollbars for panning. Doesn't touch the SVG's own size/viewBox at
  // all, so there's no conflict with Mermaid's internal measurement.
  let scale = 1;
  const zoomEl = document.querySelector(".diagram-zoom");
  const zoomLevelEl = document.getElementById("zoom-level");

  function setScale(next) {{
    scale = Math.min(Math.max(next, 0.2), 4);
    zoomEl.style.transform = `scale(${{scale}})`;
    zoomLevelEl.textContent = Math.round(scale * 100) + "%";
  }}

  const animationToggle = document.getElementById("animation-toggle");
  animationToggle.addEventListener("change", () => {{
    zoomEl.classList.toggle("animation-off", !animationToggle.checked);
  }});

  document.getElementById("zoom-in").addEventListener("click", () => setScale(scale * 1.2));
  document.getElementById("zoom-out").addEventListener("click", () => setScale(scale / 1.2));
  document.getElementById("zoom-reset").addEventListener("click", () => setScale(1));

  const scrollEl = document.querySelector(".diagram-scroll");

  scrollEl.addEventListener(
    "wheel",
    (e) => {{
      if (!e.ctrlKey) return;
      e.preventDefault();
      setScale(scale * (e.deltaY < 0 ? 1.1 : 0.9));
    }},
    {{ passive: false }}
  );

  // Drag with the left mouse button to pan. A click (no movement) still
  // goes through to node highlighting — only an actual drag is suppressed,
  // via a capture-phase click listener before it reaches the node.
  let isDragging = false;
  let dragMoved = false;
  let dragStartX = 0, dragStartY = 0, startScrollLeft = 0, startScrollTop = 0;

  scrollEl.addEventListener("mousedown", (e) => {{
    if (e.button !== 0) return;
    isDragging = true;
    dragMoved = false;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    startScrollLeft = scrollEl.scrollLeft;
    startScrollTop = scrollEl.scrollTop;
    scrollEl.style.cursor = "grabbing";
  }});

  window.addEventListener("mousemove", (e) => {{
    if (!isDragging) return;
    const dx = e.clientX - dragStartX;
    const dy = e.clientY - dragStartY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) dragMoved = true;
    if (dragMoved) {{
      scrollEl.scrollLeft = startScrollLeft - dx;
      scrollEl.scrollTop = startScrollTop - dy;
    }}
  }});

  window.addEventListener("mouseup", () => {{
    isDragging = false;
    scrollEl.style.cursor = "";
  }});

  scrollEl.addEventListener(
    "click",
    (e) => {{
      if (dragMoved) {{
        e.stopPropagation();
        e.preventDefault();
        dragMoved = false;
      }}
    }},
    true
  );

  setScale(1);
}})();
</script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dbml_files",
        nargs="*",
        help="file(s)/folder, default: dbml/schema.dbml or the whole dbml/ folder",
    )
    parser.add_argument(
        "-o", "--output", type=Path, help="file to write the diagram to (default: stdout)"
    )
    args = parser.parse_args()

    try:
        paths = resolve_dbml_paths(args.dbml_files)
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    source_desc = describe_paths(paths)

    try:
        db = PyDBML(read_dbml_paths(paths))
    except Exception as e:
        print(f"ERROR ({source_desc}): {e}", file=sys.stderr)
        return 1

    lin = Lineage(db)
    is_html = bool(args.output) and args.output.suffix.lower() == ".html"
    mermaid = render_mermaid(lin, interactive=is_html)

    if is_html:
        layer_checkboxes = "\n    ".join(
            f'<label><input type="checkbox" data-layer-toggle="{g["id"]}" checked> {g["name"]}</label>'
            for g in lin.groups
        )
        output = HTML_TEMPLATE.format(
            source_file=source_desc,
            output_file=args.output,
            mermaid=mermaid,
            graph_json=graph_json(lin),
            layer_checkboxes=layer_checkboxes,
        )
    else:
        output = (
            f"<!-- Generated: python scripts/lineage.py — do not edit by hand, "
            f"source is {source_desc} -->\n\n"
            "```mermaid\n" + mermaid + "\n```\n"
        )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"Written: {args.output}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
