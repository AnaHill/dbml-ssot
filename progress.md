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

- **Distinguish an input edge from a populating edge in the lineage diagram.** Today every lineage edge is drawn identically ([lineage.py:236](scripts/lineage.py#L236)), so `bronze.Area --> nb_dim_area --> silver.area` reads as if data flowed the same way on both hops — when in reality the notebook only reads the first table and populates the second. Preferred fix: label the edges, `-->|reads|` into the process node and `-->|writes|` out of it. A lighter alternative if the labels clutter the picture: make the input hop an arrowless `---` line and keep the arrowhead only on the populating hop. Either way the split is easy to compute — in `lineage_edges` an input edge is one whose target is an `nb_*` node, an output edge one whose source is. Two things to handle at the same time: FK edges are already `-.->|FK|`, so a third meaning appears in a diagram that has no legend; and `tests/test_lineage.py` asserts on the current arrow form, so those assertions move with the change. Applies to both the `.md` and `.html` output, since they share `render_mermaid`.
- **An independent `/code-review` pass before bigger commits**, separating review from authoring — a working practice, not a repo change.

## How to use this file

- New session: read this + `AGENTS.md` before asking what's going on.
- After a decision: one line under "Decisions not recorded elsewhere" — but only if it isn't going into README/AGENTS.md anyway. If it is, link it instead.
- When an item is done: delete it.
