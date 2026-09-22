# Decisions

Why this repo is built the way it is — the alternatives that were considered and the reasons each one was or wasn't chosen. This is decision history, not documentation of how to use the tools: for that, see [README.md](README.md). Nothing here needs to be read to use the repo; it exists so that a decision already made isn't quietly reopened, and so the reasoning survives the people who had it.

## Original idea

The original idea was three parallel representations (SQL `schema.md`, DBML `description.md`, an Obsidian visual) that an agent/script would keep in sync with each other. This was rejected: several parallel "truths" drift out of sync over time. One source is safer.

## Alternatives considered

Alternatives considered for DBML:

- **Mermaid `erDiagram`** — renders natively in more places (GitHub, Obsidian's core, VS Code) without a third-party plugin, which would have reduced a dependency.
  - Rejected as the main choice anyway, because it doesn't support per-table `Note` metadata as well as DBML — exactly the feature that lets every table document its bronze source and orchestrating notebook directly in the model.
- **The Obsidian DBML Visualizer plugin as an interactive editor** — offers low-code editing (rename, changing cardinality by clicking) directly in Obsidian, but is a small, new project (v1.0.2, about 2 months old at the time) → abandonment risk. The same risk applies to comparable Mermaid editors (e.g. Mermaid NG for VS Code, still unpublished to the marketplace). None of these are as mature as **dbdiagram.io**, where exactly the same feature set has been in production for years.
  - So dbdiagram.io is the primary editor, and the Obsidian plugin is just an optional extra.
- **VS Code extensions for graphical ERD preview** — since editing is now always done directly on the `.dbml` files (not via dbdiagram.io, see above), the need is just for a local visual preview in the same editor where the model is edited. Three options checked: [`bocovo.dbml-erd-visualizer`](https://marketplace.visualstudio.com/items?itemName=bocovo.dbml-erd-visualizer) (open source, no login, preview opens in a side panel with a click — the marketplace listing doesn't separately confirm network traffic, but being open source makes it checkable if needed), [dbdiagram.io's official extension](https://docs.dbdiagram.io/vs-code-extension/) (documented: basic use is local, network only for paid sync/publish features), and Obsidian + the DBML Visualizer plugin (see above — needs a separate app and `preview_md.py`'s markdown wrapper).
  - `bocovo.dbml-erd-visualizer` was chosen as the primary option because it works directly in the same editor where the model is edited, with no context switch or extra step.
- **dbt (`sources.yml`/`schema.yml`)** — would make sense if a real pipeline were run from the model, but overkill when the goal is lightweight documentation with no live execution.

## DBML in a markdown fence vs. its own .dbml file

At first DBML was written inside `description.md` in a single ` ```dbml ` code block, and `description.md` also held the tool instructions. This was changed to a plain `.dbml` file, because:

- Four scripts had to repeat the same "extract the dbml block from markdown" logic — this disappears entirely once the file is already plain DBML.
- A separate `.dbml` file can get real DBML syntax highlighting in an editor; inside a markdown fence it can't.
- `description.md` no longer had a reason to be separate from `readme.md` once it held no model — its content was merged into the README.

If a markdown preview is ever needed (e.g. the Obsidian plugin), it isn't maintained by hand as a parallel copy — `scripts/preview_md.py` generates it from the DBML source when needed.

## schema.dbml at the repo root vs. in a dbml/ folder

`schema.dbml` was moved from the repo root into its own `dbml/` folder right at the start (before anything was committed), for two reasons:

- Keeps the repo root clean — the data model separate from documentation, scripts, and tests.
- Allows growth in two directions later without a second disruptive move: either the model is split across several files per domain (`10_silver.dbml`, `20_gold.dbml`, ...) in the same folder, or — if genuinely needed — several independent projects could each live in their own subfolder (`dbml/<project>/`). The latter hasn't been implemented and there's no known need for it; the structure simply doesn't rule it out if that ever changes.

The three-part input model the scripts support (no argument / a single file-or-folder / a list in the given order, see README § Tools) is already sufficient for both the per-domain split and the multi-project case — neither needed a separate "list of projects" mechanism or the like to be built. The one thing that would change with more projects: the default (`dbml/schema.dbml`) would stop being unambiguous, and a path would always have to be given explicitly.

## SQL → DBML import: only CREATE TABLE/VIEW ... AS SELECT or a plain CREATE TABLE

`sql_to_dbml.py` accepts only two statement shapes as input — `CREATE TABLE ... AS SELECT` / `CREATE [OR REPLACE] VIEW ... AS SELECT` (CTAS/CTAV) and a plain `CREATE TABLE name (column type, ...)` (no `AS SELECT`) — not arbitrary SQL (`INSERT`, `MERGE`, `ALTER`, multi-statement transactions, etc.). The restriction was chosen deliberately, for two reasons:

- **A narrow, predictable grammar.** Both accepted forms are each one well-known statement shape: CTAS/CTAV (`CREATE ... AS SELECT ... FROM ... [JOIN ...]* [GROUP BY ...]`), whose parsing (`sqlglot`) is limited to walking a single `SELECT` tree — the target table, source tables, join types, and `GROUP BY` columns are all directly extractable from the tree's structure; and a plain `CREATE TABLE`, where columns and types are read straight from the DDL's column list, needing no inference at all. Supporting other statements (e.g. an `INSERT INTO` an existing table, or complex CTE chains) would bring significantly more ambiguous cases with no matching benefit at this stage.
- **Fail clearly, don't guess.** If the given SQL doesn't match either shape, the tool prints an error and proposes nothing — the same principle as in `validate_dbml.py`. No partial or uncertain updates.

Plain `CREATE TABLE` support was added alongside CTAS/CTAV because some tables in the model (e.g. the bronze layer) are raw, ingested data with no SQL source at all — the CTAS/CTAV restriction would have left them completely outside this tool's reach even though their structure is directly readable from their own DDL.

**Gaps the restriction doesn't solve, because they aren't a SQL problem but a missing-information problem:**

- A `notebook` path can never be derived from SQL — it's orchestration metadata that neither statement shape contains in any form. The tool always marks it `TODO`, never guesses.
- `source table` is inferred from the source tables for CTAS/CTAV statements, but for a plain `CREATE TABLE` there's nothing to infer it from (no `SELECT` source) — always `TODO`.
- The type of computed/aggregated columns (`SUM(...)`, `DATE_TRUNC(...)`, etc.) isn't explicit in a CTAS/CTAV's `SELECT` list — the tool infers the type from the source column if it's found in the given DBML source, otherwise marks it `varchar` + `[note: 'TODO: verify type']`. Plain `CREATE TABLE` columns don't have this gap, since the type always comes straight from the DDL.

Because of all these gaps, the tool never writes directly to the `.dbml` file — a proposal always has to be reviewed before pasting it in.

## Documentation vs. a runnable system: where this repo sits

Describing a data model as text/code spans many maturity levels, and this repo deliberately sits at the lightest end:

- **Hand-maintained static documentation** (markdown tables, wiki pages) — no validation, drifts from the truth over time.
- **This repo (DBML + guardrails)** — code-shaped, validatable, but deliberately **not runnable**: the scripts only read the model and generate views (validation, lineage), never write it back or sync it to any live system. The agent instructions (`AGENTS.md`) explicitly forbid inventing metadata (`TODO` as an exact string instead of guessing).
- **dbt / SQLMesh** — the documentation (`sources.yml`/lineage graph) is wired into a real, runnable transformation pipeline; the model AND the pipeline are the same code.
- **Rayfin** ([Microsoft Fabric Apps SDK](https://learn.microsoft.com/en-us/javascript/api/fabric-apps-sdk-javascript/rayfin-overview)) and Databricks' [Vibe Data Modeling](https://www.databricks.com/blog/reimagining-data-modeling-lakehouse-introducing-vibe-data-modeling) — the schema is defined as code (TypeScript decorators, or a `model.json` generated from a prompt), and the tool **provisions a live database, an API, and permission policies** straight from it. The model no longer describes the system — the model *is* the system.

The further along this spectrum you go, the more tightly the model and the live system are coupled — useful when the goal is genuinely to run something, but it brings deploy risk, an infrastructure dependency, and a bigger blast radius for "wrong info is now in production." This repo's need was different: document and visualize a (possibly still just planned) Lakehouse model lightly, without the documentation itself ever being able to accidentally change anything real — that's why the lighter, deliberately decoupled end of the spectrum was chosen, not because the heavier options were unknown.

A second, orthogonal axis is **one-off vs. deterministic generation**. [Archify](https://tt-a1i.github.io/archify/) (an agent skill for Claude Code/Cursor/Codex, among other things generating ETL/lineage diagrams in its "data-flow" mode) generates a diagram fresh from a natural-language prompt, by the agent's own interpretation, every time — fast, but with no structured, versioned source of truth and no guardrails stopping the agent from filling gaps with guesses. This repo deliberately does the same thing differently: the diagram (`lineage.py`) is always generated the same way from the same, validatable `dbml/schema.dbml` file, and `AGENTS.md` explicitly forbids the agent from guessing missing metadata (`TODO` instead of a guess) — reproducibility and guardrails were chosen over free-form speed.

## ERD Studio: the closest neighbour, and why this still exists

[ERD Studio](https://github.com/liam-machine/erd-studio) ([VS Code extension](https://marketplace.visualstudio.com/items?itemName=liamwynne.erd-studio)) is the nearest thing to this repo found so far: a visual ERD designer that keeps the model in your repository as plain files, explicitly so an AI assistant can read it. It is worth knowing about before reaching for anything here, and for some projects it is the better choice.

**Where it is genuinely ahead:** it edits on a canvas with two-way sync back to the files, which this repo does not do at all — click-based editing here is delegated to dbdiagram.io through a copy-paste round trip. It also compares the logical design against what dbt actually built (`manifest.json`, `catalog.json`) and reports the drift, which is a kind of verification this repo deliberately does not attempt.

**Why it doesn't replace this:**

- **It is built around dbt.** Its core value needs a `dbt_project.yml`; without one it drops to a logical-only mode. This repo's `notebook:` line is free text precisely so an ADF pipeline, a Fabric notebook or a stored procedure counts as an orchestrating mechanism.
- **"Lineage" means a different thing in each.** There it means design-vs-built drift. Here it means upstream source → process → table, across platform boundaries. They are not two solutions to one problem.
- **Format portability.** DBML is read by dbdiagram.io, `sql2dbml` and several viewers; ERD Studio's YAML/JSON schema lives in ERD Studio.
- **Licence.** ERD Studio is PolyForm Shield 1.0.0 — free to use, including commercially, but it forbids building a competing product. That is source-available, not open source. This repo is MIT, so it can be forked and built on without that question arising.

Summary: on a dbt project that wants visual modeling, ERD Studio probably does more. This repo earns its place when the stack isn't dbt, when the format and licence need to stay open, or when what needs documenting is where the data came from rather than how the tables are shaped.

## Arrowheads are never dropped from a lineage edge

A thin arrow marks the hop into an orchestration node (the process reads that table) and a thick one the hop out of it (the process populates that table), but both keep their arrowhead. In Mermaid's layout an edge often passes under an unrelated node on its way to its own target, and the arrowhead is the only cue separating "this edge ends here" from "this edge just passes by". An arrowless `---` input hop was considered and rejected for exactly that reason: it would have made lineage harder to follow, not easier.

Per-edge `reads`/`writes` labels were considered too. They are unambiguous, but they would add a label to every lineage edge in a picture that currently labels only foreign keys, and Mermaid places each label at the edge's midpoint — sometimes on top of an unrelated node. The weight difference plus a legend carries the same meaning without the clutter.
