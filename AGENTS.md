# AGENTS.md

This file is the project's canonical guide for all AI coding agents (Claude Code, Codex, Cursor, Copilot, Gemini CLI, etc.). Tool-specific files (e.g. `CLAUDE.md`) only import this content, they don't repeat it.

## Project

Lightweight, AI-assisted data architecture documentation as DBML. The format and the scripts are **generic** — not tied to a Lakehouse, Databricks, or any specific architecture (see README § Generality and [examples/generic_rdbms.dbml](examples/generic_rdbms.dbml), which proves the same thing works for a plain relational database with the exact same, unmodified scripts). This repo's own current model (`dbml/schema.dbml`) illustrates a Fabric/Databricks-style Lakehouse architecture (bronze/silver/gold) as an example — every reference below to bronze/silver/gold layers, notebooks, etc. concerns THIS current example model, not a general requirement of the tooling. The goal is **documentation, not a runnable system** — no production SQL is generated automatically from the model, and it isn't synced to any live database.

How the tools are used: [README.md](README.md). Why the repo is built this way, with the alternatives that were rejected: [DECISIONS.md](DECISIONS.md).

## Single source: dbml/

The data model is **plain DBML code** in the `dbml/` folder — no markdown wrapper, no other content. This is the only place tables, columns, and relations are written.

Every CLI script in `scripts/` that reads the DBML source accepts it as an optional list of positional arguments (no argument / a single file-or-folder / a list in the given order) — the exception is `sql_to_dbml.py`, which uses a `--dbml` flag instead, because its own positional argument is a SQL file. Default with no argument: `dbml/schema.dbml` if it exists, otherwise the whole `dbml/` folder. Full rules and an example: [README.md](README.md) § Tools.

Implementation: `scripts/_dbml_source.py`. This is the **one exception** to the "no cross-imports" principle (see Other files) — every script may import this one small shared helper, but not each other.

**Never:**
- create a parallel SQL file or duplicate the schema anywhere else as a hand-maintained copy
- wrap DBML code back into a markdown file as a hand-maintained copy — if a markdown preview is needed, use `scripts/preview_md.py` (it generates a view, it doesn't create a new source of truth)
- generate/run SQL DDL as part of normal editing (`scripts/export_sql.py` is a separate, on-request tool — not an automatic step)
- commit the contents of `generated/` as a source of truth — it's gitignored, a purely derived view

## When adding or editing tables

1. Add/edit the table directly in `dbml/schema.dbml` (or the right domain file, if the model is split across several `.dbml` files), using DBML syntax. Reference: <https://dbml.dbdiagram.io/docs/>. If you're unsure of the syntax, don't guess — check the docs or validate (see below) and fix any errors.
2. Every table **must have** a `Note` field with two lines:
   ```
   Note: '''
     source table: <upstream source table or system, e.g. bronze.Area (Lakehouse) or RAW.CUSTOMERS (Snowflake)>
     notebook: <orchestrating mechanism: notebook path, pipeline name, stored procedure name, etc.>
   '''
   ```
   **Never invent source table or notebook values.** If you don't know them for certain, ask the user or write the value as exactly `TODO` (not e.g. `TODO: unknown` or other extra text) — `scripts/lineage.py` only recognizes missing information from this exact string (case-insensitive) and marks it in the diagram with its own warning style. Wrong source info is worse than missing info.

   An optional third line, `mechanism: <notebook|pipeline|stored_procedure>`, controls the color of the orchestration node in `scripts/lineage.py`'s diagram (if missing, the default is `notebook` — never guessed). An unrecognized value gets its own default gray color instead of being forced into the wrong category.
3. Naming convention: `snake_case`, primary key shaped like `<table>_id integer [pk, increment]`. **This model's own convention** (not a general DBML rule): the `dim_`/`fact_` prefixes are reserved for the gold layer only (e.g. `gold.dim_area`, `gold.fact_production_monthly`, or `fact_..._view` for SQL views) — the silver layer uses bare entity names with no prefix (e.g. `silver.area`, `silver.production_events`), so the layers aren't mixed up. If your model isn't Lakehouse-style, apply an equally consistent naming convention that fits your context.
4. Relations preferably inline at the column (`column integer [ref: > other_table.column]`). Use a separate `Ref:` line only when a relation doesn't naturally attach to one column (e.g. many-to-many). Relations work across file boundaries with no extra setup — DBML/PyDBML doesn't require the target table to be defined before the referencing `Ref` line.
5. Group tables into logical units with `TableGroup` blocks, with consistent colors — in this model, by Lakehouse layer (`bronze_layer`, `silver_layer`, `gold_layer`); in another context, by domain or schema, say.
6. A new table's skeleton can be generated with: `python scripts/new_table.py --name dim_x --source bronze.X --notebook <path>` — fill in the `Note` fields yourself and don't leave placeholder values in the final file. (The script only scaffolds `source table` and `notebook` — add the optional `mechanism` line yourself if you need it, see point 2.)
7. If a table is derived from SQL (`CREATE TABLE/VIEW ... AS SELECT`), `python scripts/sql_to_dbml.py <sql-file>` can propose a ready-made skeleton (see SQL-to-DBML proposal below) — still always review the proposal before pasting it in, never paste it in as-is.

## Validation (always run after editing)

```bash
# Once
pip install -r requirements.txt

python scripts/validate_dbml.py
```

An edit isn't done until validation passes with no errors. If validation fails, fix the DBML syntax — don't skip or remove the validation step.

## SQL DDL when needed (rare, not automatic)

```bash
# SQL DDL to the terminal
python scripts/export_sql.py

# SQL DDL to a file
python scripts/export_sql.py -o file.sql
```

The generated SQL is PyDBML's generic dialect — not guaranteed to be the target platform's (Fabric/Databricks) dialect as-is. Use only when real SQL is genuinely needed, don't add this to the normal editing workflow.

## Editing scripts

If you edit any file in `scripts/`, run the pytest suite in `tests/` before considering the change done:

```bash
# Once
pip install -r requirements-dev.txt

pytest
```

If you add new pure logic to a script (a function that doesn't do file I/O or call external processes), add a unit test for it in `tests/` at the same time. See [README.md § Testing](README.md#testing) for a more detailed description of the test structure.

If you add an entirely new script meant to be run directly as `python scripts/new.py` (not a helper like `_dbml_source.py`), add its own line to `.claude/settings.json`'s `permissions.allow` list: `"Bash(python scripts/new.py*)"`. Do this **only** if the script doesn't run external commands built from user-supplied arguments (no `subprocess`/`os.system`/`eval` call that feeds a CLI argument straight into a command string) — this repo is public, and this file affects any Claude Code session that opens the repo, not just your own machine. If you're unsure, leave the line out and let the command prompt for permission normally.

## Visual review

Changes are made directly to the DBML source (see When adding or editing tables) — dbdiagram.io is no longer the primary route; the model is now mostly just viewed visually: directly reviewing the `.dbml` file's ERD structure with a VS Code extension (see [README.md](README.md) § Tools), or reviewing the lineage diagram with `python scripts/lineage.py -o generated/lineage.html` (see Data lineage diagram).

`python scripts/copy_dbml.py` is still available in case you occasionally want to do an interactive, click-based edit in [dbdiagram.io](https://dbdiagram.io) (renaming with its references, changing a relation's cardinality) — it copies the DBML source's content (default `dbml/schema.dbml`) to the clipboard. If you paste updated DBML back from there, replace the source file's entire content with it as-is.

## Data lineage diagram

`python scripts/lineage.py -o generated/lineage.md` (or `-o generated/lineage.html` for a standalone, interactive mermaid.js page, if the `.md` preview doesn't render reliably in your editor) generates a Mermaid flowchart from the DBML source's `Note` fields (upstream source → process/notebook/pipeline → table — generic, doesn't depend on Lakehouse vocabulary, see README § Generality) and `Ref` relations, grouped into `TableGroup` blocks. This is a **generated view, not a source of truth** — never edit files in `generated/` by hand, re-run the script whenever the DBML source changes. Missing/`TODO` lineage is shown in the diagram with its own warning style; don't fix this by inventing source table or notebook values — fill them in in `dbml/schema.dbml` once the real information is known.

## Markdown preview when needed

`python scripts/preview_md.py` generates `generated/preview.md`, wrapping the DBML source's content in a ` ```dbml ` code block (e.g. for the Obsidian DBML Visualizer plugin). A purely generated view — never hand-maintained, never a source of truth.

## SQL-to-DBML proposal (experimental)

`python scripts/sql_to_dbml.py <sql-file> [--dbml <dbml-source>]` proposes a DBML `Table` block from two kinds of SQL statements: `CREATE TABLE ... AS SELECT` / `CREATE [OR REPLACE] VIEW ... AS SELECT` (CTAS/CTAV, column types inferred from the source tables) and a plain `CREATE TABLE name (column type, ...)` (no `AS SELECT`, columns read straight from the DDL — intended for raw/ingested source tables that have no SQL source, e.g. the bronze layer in a Lakehouse or a staging/raw table in any other architecture). Accepts only these two statement shapes — any other SQL is rejected with an error and nothing is updated. Never writes directly to the `.dbml` file and never overwrites an existing table (it only reports that it's already in the model). Full description: [README.md](README.md) § Tools. Why the input is restricted to these two shapes: [DECISIONS.md](DECISIONS.md).

If you use/paste this output into a `.dbml` file: the `notebook` field is always `TODO`, and for plain `CREATE TABLE` tables so is `source table` (there's no SQL source to infer it from) — fill these in yourself, don't invent values (see When adding or editing tables, point 2). Check every column marked `[note: 'TODO: verify type']` (only possible on CTAS/CTAV proposals) and fix the actual type before considering the table done — these are gaps that can't be inferred from SQL, not bugs in the script.

## Other files

The repo structure (`dbml/`, `scripts/`, `generated/`, `examples/`, `tests/`, dependency files) is described in more detail in [README.md](README.md)'s Structure section — not repeated here.

One rule especially relevant to an agent: don't edit [DECISIONS.md](DECISIONS.md) without the user asking for it; it's decision history, not editable documentation. Add to it only when a new decision is actually made.
