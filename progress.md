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
4. **`AGENTS.md` is written against a context-engineering test**: every line has to earn its place — "would a strong model behave worse without this?" That's why it carries rules rather than a script list that would need manual upkeep.

## Open items

- **Distinguish an input edge from a populating edge in the lineage diagram.** Today every lineage edge is drawn identically ([lineage.py:236](scripts/lineage.py#L236)), so `bronze.Area --> nb_dim_area --> silver.area` reads as if data flowed the same way on both hops — when in reality the notebook only reads the first table and populates the second. **The constraint that rules out the obvious fix:** in Mermaid's layout an edge often passes under or beside an unrelated node on its way to its own target, and the only thing separating "this edge ends here" from "this edge merely passes by" is the arrowhead at the target. So making the input hop an arrowless `---` line — the first idea — would remove exactly that cue and make lineage *harder* to follow than it is today. Dropped for that reason.

Options that keep every arrowhead, in the order worth trying: (1) a legend in the page, explaining that an edge into a process node is a read and an edge out of it is a write — no change to the edges at all; (2) a visual difference in weight or shade, e.g. a thin input hop and a thick (`==>`) populating hop; (3) `-->|reads|` / `-->|writes|` labels, which are unambiguous but add 45 texts to a picture that currently labels only FK edges, and Mermaid puts each label at the edge's midpoint, which may land on top of an unrelated node. Also worth weighing before doing anything: the edge animation added since already conveys direction, and a notebook reading a table is arguably data movement too — the problem may be smaller in the rendered picture than it looked in text.

If a change is made: in `lineage_edges` an input edge is one whose target is an `nb_*` node and an output edge one whose source is, `tests/test_lineage.py` asserts on the current arrow form, and the `.md` and `.html` outputs share `render_mermaid` — so decide deliberately whether both should change.
- **An independent `/code-review` pass before bigger commits**, separating review from authoring — a working practice, not a repo change.

## How to use this file

- New session: read this + `AGENTS.md` before asking what's going on.
- After a decision: one line under "Decisions not recorded elsewhere" — but only if it isn't going into README/AGENTS.md anyway. If it is, link it instead.
- When an item is done: delete it.
