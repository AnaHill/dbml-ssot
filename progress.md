# Progress

A working note on where the project stands and what's still open — a fast way into the project for a new session, without reading the whole chat history. `README.md` holds the rationale and `AGENTS.md` the rules: anything already written there is linked from here, never restated, so no list has to be maintained in two places. Free-form, allowed to be incomplete, not a source of truth.

## Where things stand

Repo layout and the script list: README § Structure. What each script does and how to run it: README § Tools and § Getting started. The rules the agent works under: `AGENTS.md`. The model's current size (tables, relations, groups): `python scripts/validate_dbml.py` prints it, so it isn't copied here.

The one thing worth repeating, because every other decision follows from it: **documentation, not a runnable system** — the model never writes itself back anywhere, and the agent never invents missing metadata (`TODO` as an exact string instead of a guess).

## Decisions not recorded elsewhere

README § Why we ended up here already covers the plain `.dbml` file, the mandatory `Note` field, the `mechanism:` line, and `sql_to_dbml.py`'s two accepted statement shapes — not repeated here. What's left:

1. **Bronze was modeled as real `Table` blocks**, not as text references inside the silver layer's Notes, so a lineage path starts from a node that actually exists in the model. Their `source table:` values are generic `source_system.*` names — this model is an illustration, not a real system.
2. **`lineage.html`'s "Orchestration" subgraph was removed** — orchestration nodes are free-standing (own shape + color via a per-node `classDef`), because the forced wrapper competed with the natural flow layout and added no identity that shape + color didn't already give.
3. **The competitive landscape was checked deliberately**, not skipped: DBML's native `Dep` syntax (2026-08), Databricks' Vibe Data Modeling, Microsoft Fabric's Rayfin SDK. Conclusion in README § "Documentation vs. a runnable system: where this repo sits" — this repo sits at the lightest, non-runnable end on purpose.
4. **Arrowheads are never dropped from a lineage edge.** A thin arrow marks the hop into an orchestration node (a read) and a thick one the hop out of it (a write), but both keep their head — in Mermaid's layout an edge often passes under an unrelated node, and the arrowhead at the target is the only cue separating "ends here" from "passes by". An arrowless `---` input hop was considered and rejected for exactly that reason.
5. **`AGENTS.md` is written against a context-engineering test**: every line has to earn its place — "would a strong model behave worse without this?" That's why it carries rules rather than a script list that would need manual upkeep.

## Open items

- **An independent `/code-review` pass before bigger commits**, separating review from authoring — a working practice, not a repo change.
- **Bigger arrowheads** in `lineage.html`, if they ever feel too small. Mermaid draws them as `<marker>` elements, whose size is an attribute rather than a style, so it means scaling `markerWidth`/`markerHeight` (and `refX` with them, or the tip drifts off the node edge) in JS after `mermaid.run()`. Low value for the fiddliness, and it would depend on Mermaid's rendered SVG internals — left undone on purpose.
- **Per-edge `reads`/`writes` labels** were considered and left undone: the thin/thick arrows plus the legend already carry the meaning, and 45 labels in a picture that currently labels only FK edges would land at edge midpoints, sometimes on top of an unrelated node. Only worth revisiting if the weight difference turns out to be too subtle in practice.

## How to use this file

- New session: read this + `AGENTS.md` before asking what's going on.
- After a decision: one line under "Decisions not recorded elsewhere" — but only if it isn't going into README/AGENTS.md anyway. If it is, link it instead.
- When an item is done: delete it.
