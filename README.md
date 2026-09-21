# AI-assisted data architecture and visualization

A data architecture described as code in one place — readable by a human, safe for an AI agent to maintain.

- **One source of truth: plain `.dbml` code.** Every diagram, SQL export and preview is generated from it, never kept in sync by hand.
- **Human-friendly both ways.** Edit the text directly in your editor, or view it as an ERD or an interactive lineage diagram.
- **Built for an agent to maintain.** DBML is compact text an LLM reads well, and [AGENTS.md](AGENTS.md) sets the guardrails it works under.

## Decision

The data model is described **in the `dbml/` folder**, as plain DBML code — no markdown wrapper, no parallel SQL file that a human or an agent would have to keep in sync by hand. `dbml/schema.dbml` is the model's single source of truth — one file for as long as it stays a manageable size, but every script also supports splitting it across several files in the same folder (see Tools below).

- **Visual/low-code editing** (renaming a table along with its references, changing a relation's cardinality by clicking, colors): [dbdiagram.io](https://dbdiagram.io). `python scripts/copy_dbml.py` copies the code to the clipboard for pasting in; after editing, the updated DBML is copied back into `dbml/schema.dbml`.
- **Local graphical preview** (optional, view-only — editing always happens directly in the `dbml/` files): primarily the VS Code extension [DBML ERD Visualizer](https://marketplace.visualstudio.com/items?itemName=bocovo.dbml-erd-visualizer) (reads the `.dbml` file directly in the editor, no script needed). Alternatives: [dbdiagram.io's official VS Code extension](https://docs.dbdiagram.io/vs-code-extension/) (basic use — syntax highlighting + ERD preview — is local), or Obsidian + the [DBML Visualizer](https://community.obsidian.md/plugins/dbml-visualizer) plugin. If a tool specifically needs a markdown-wrapped code block (like the Obsidian plugin), `python scripts/preview_md.py` generates one (`generated/preview.md`) — not versioned as a separate source of truth, just a generated view.
- **SQL DDL** is generated only when needed (`scripts/export_sql.py`), not automatically. The goal right now isn't to run a live system from this model.
- **Syntax validation**, a **data lineage diagram**, and a **new-table scaffold** are handled by Python scripts in `scripts/`, without needing an agent for every change.
- **Agent guardrails** live in [AGENTS.md](AGENTS.md): never invent a source table or an orchestrating job — write the exact string `TODO`, which the lineage diagram then flags in its own warning style; propose rather than write straight into the model; and let validation and the test suite decide when a change is done.

## Tools

Every CLI script in `scripts/` that reads the DBML source (`validate_dbml.py`, `export_sql.py`, `copy_dbml.py`, `preview_md.py`, `lineage.py`, and `sql_to_dbml.py` via its `--dbml` flag) accepts it as an optional list of positional arguments, in three ways:

1. **No argument** — default: `dbml/schema.dbml` if it exists, otherwise the whole `dbml/` folder (all `.dbml` files in alphabetical order).
2. **A single file or folder** — a folder expands to all its `.dbml` files in alphabetical order.
3. **A list of names/files/folders** — used in the GIVEN order. A bare filename with no path/extension (e.g. `10_silver`) is looked up inside the `dbml/` folder. This way, for example if the `dbml/` folder has both `schema.dbml` and separate per-domain scratch versions at the same time, you can pick exactly the files you want without disturbing the default behavior (plain `schema.dbml`):
   ```
   python scripts/validate_dbml.py 10_silver 30_snowflake
   ```
   Implementation: [scripts/_dbml_source.py](scripts/_dbml_source.py) — the one shared helper every script may import (see Structure).

Commands:

- **Syntax validation**: `python scripts/validate_dbml.py`
- **Editing in dbdiagram.io**: `python scripts/copy_dbml.py` copies the DBML source's content to the clipboard (removes `color`/`headercolor` settings by default, since dbdiagram.io's free tier doesn't support them — `--keep-colors` preserves them).
- **Graphical ERD preview (VS Code)**: install the [DBML ERD Visualizer](https://marketplace.visualstudio.com/items?itemName=bocovo.dbml-erd-visualizer) extension and open `dbml/schema.dbml` — the preview opens in a side panel with a click, no script needed (see Decision for other options).
- **Local markdown preview**: `python scripts/preview_md.py` generates `generated/preview.md` (a ` ```dbml ` wrapper), e.g. for Obsidian.
- **SQL DDL when needed**: `python scripts/export_sql.py [-o file.sql]`
- **New table skeleton**: `python scripts/new_table.py --name dim_x --source bronze.X --notebook <path>`
- **SQL-to-DBML proposal** (experimental): `python scripts/sql_to_dbml.py <sql-file> [--dbml <dbml-source>]` reads two kinds of `CREATE` statements from a SQL file and proposes a DBML `Table` block for every target table not yet in the DBML source — if it's already there, it reports that and proposes nothing, and never overwrites:
  1. `CREATE TABLE ... AS SELECT` / `CREATE [OR REPLACE] VIEW ... AS SELECT` (CTAS/CTAV) — column types are inferred from the source tables in the given DBML source.
  2. A plain `CREATE TABLE name (column type, ...)` (no `AS SELECT`) — columns and types are read straight from the DDL. Intended for raw/ingested tables (e.g. the bronze layer) that have no SQL source.

  Any other SQL is rejected with an error and nothing is updated. The tool never writes into the `.dbml` file — it prints a proposal for you to review and paste in, and `--clipboard` also copies it. What SQL cannot tell it is marked `TODO` rather than guessed: always the `notebook` field, `source table` for a plain `CREATE TABLE`, and a computed column's type when the source column isn't in the model. Check every `TODO` by hand before considering the table done. Why the input is restricted to two shapes: [DECISIONS.md](DECISIONS.md).
- **Data lineage diagram**: `python scripts/lineage.py -o generated/lineage.md` builds a Mermaid flowchart from the `Note` fields and `Ref` relations — upstream source → process → table, plus the foreign keys, grouped by `TableGroup`. Nothing in it assumes Lakehouse vocabulary (see Generality below). A thin arrow runs into a process node (it reads that table) and a thick one out of it (it populates that table); missing or `TODO` lineage shows up in its own warning color rather than disappearing.

  `-o generated/lineage.html` instead produces a standalone **interactive** page (mermaid.js from a CDN) that opens with a double-click:

  - Click a table to light up its whole upstream/downstream path. Several selections at once, each in its own color.
  - Edges animate in the direction data moves; "Animate flow" turns that off.
  - Show/hide any layer, including the source and process nodes.
  - "Download PNG" / "Copy PNG" export exactly what's on screen at 2× — selection highlighted, hidden layers gone. That's how the image below was made.
  - A legend generated from the model itself, listing only the mechanisms that model actually uses.

  The animation is deliberately absent from the `.md` output: GitHub's and Obsidian's bundled Mermaid may predate the edge-id syntax it needs.

![A lineage diagram: source systems on the left, orchestration nodes between them, and the bronze, silver and gold layers as grouped blocks; two selected tables highlight their own upstream/downstream paths in different colors](docs/img/lineage-example.png)

A static snapshot of this repo's own `dbml/schema.dbml` with two tables selected — the live, clickable version is one command away: `python scripts/lineage.py -o generated/lineage.html`.

Everything in `generated/` is a **derived view, not a source of truth** — not versioned in git, never edited by hand, re-run whenever the DBML source changes.

## Generality: not tied to Lakehouse/Databricks/Fabric

This repo's own model (`dbml/schema.dbml`) describes a Fabric/Databricks-style Lakehouse, but the **scheme itself is generic**: the `Note` field's two lines (`source table:` and `notebook:`) are just free text, and the scripts (`validate_dbml.py`, `lineage.py`, etc.) know nothing about bronze/silver/gold layers or Databricks — they just read those two lines and the `TableGroup` grouping. The `notebook:` line can just as well be a stored procedure's name, a dbt model's name, an Airflow task id, or any other schema-to-schema transformation.

An optional third line, `mechanism: <notebook|pipeline|stored_procedure>`, controls `lineage.py`'s orchestration node color in the diagram — not guessed from the text's shape (e.g. a path prefix), since different files in this repo already use different naming conventions for the same mechanism (compare `examples/generic_rdbms.dbml`'s `dbo.usp_...` with this model's `stored_procedures/usp_...`). If missing, the default is `notebook`, and an unrecognized value gets its own default gray color instead of being forced into the wrong category.

[`examples/generic_rdbms.dbml`](examples/generic_rdbms.dbml) proves this concretely: a plain relational database (no bronze/silver/gold vocabulary at all), where the `notebook:` line holds a SQL Server-style stored procedure's name instead of an ingestion script. It's run with **the exact same, unmodified scripts**:

```bash
python scripts/validate_dbml.py examples/generic_rdbms.dbml
python scripts/lineage.py examples/generic_rdbms.dbml -o generated/lineage_example.md
```

## Why it looks like this

Every structural choice here — plain `.dbml` over a markdown fence or Mermaid `erDiagram`, why `sql_to_dbml.py` accepts only two statement shapes, why the repo stops short of dbt, Databricks' Vibe Data Modeling or Fabric's Rayfin — is written down with its alternatives in [DECISIONS.md](DECISIONS.md). You don't need it to use the repo; it's there so a settled decision isn't quietly reopened.

## Structure

- `dbml/` — the data model as DBML, the single source of truth
  - `schema.dbml` — the whole model as one file (current state)
- `scripts/` — helper scripts:
  - `_dbml_source.py` — shared helper for resolving the DBML source (file/folder/list). The one exception to the "no cross-imports" principle.
  - `validate_dbml.py` — checks the DBML syntax
  - `export_sql.py` — generates SQL DDL when needed (PyDBML, a generic dialect — not guaranteed to be the target platform's, e.g. Fabric/Databricks, dialect as-is)
  - `new_table.py` — prints a ready-made table skeleton with `Note` metadata (source table + notebook path) to paste into the DBML source
  - `copy_dbml.py` — copies the DBML source's content to the clipboard (Windows) to paste into dbdiagram.io
  - `preview_md.py` — wraps the DBML source in a ` ```dbml ` code block (`generated/preview.md`), e.g. for an Obsidian preview
  - `lineage.py` — generates a Mermaid lineage diagram (upstream source → notebook/pipeline/stored procedure → table, FK relations, `TableGroup` layers — generic, not tied to Lakehouse vocabulary) from the `Note` fields; not a parallel source of truth, just a generated view
  - `sql_to_dbml.py` — proposes a DBML table from SQL `CREATE TABLE/VIEW ... AS SELECT` or plain `CREATE TABLE` statements (see Tools); doesn't write directly, only prints a proposal
- `generated/` — every view the scripts produce (`lineage.md`, `lineage.html`, `preview.md`). The contents are gitignored and are not a source of truth; only an empty `.gitkeep` is versioned, to keep the output location visible in the repo.
- `examples/` — standalone example models, not part of the `dbml/` folder's source of truth. `generic_rdbms.dbml` proves the model/scripts generalize beyond a Lakehouse context (see Generality above).
- `docs/img/` — static images used by this README. Refreshed by hand, unlike `generated/`.
- `tests/` — pytest tests for the scripts (see Testing below)
- [DECISIONS.md](DECISIONS.md) — why the repo is built this way, and the alternatives that were rejected
- [requirements.txt](requirements.txt) — runtime dependencies (`pydbml`, `sqlglot`)
- [requirements-dev.txt](requirements-dev.txt): dev/test dependencies (`pytest`), kept separate from the above
- [LICENSE](LICENSE): MIT

## Getting started

Every line below is either a `#` comment or a command you can run as-is.

```bash
# Once: a virtual environment, so packages land in .venv and not in your global Python
python -m venv .venv
source .venv/Scripts/activate      # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Check the model parses
python scripts/validate_dbml.py

# Lineage diagram: a Mermaid block for GitHub/Obsidian, or an interactive page
python scripts/lineage.py -o generated/lineage.md
python scripts/lineage.py -o generated/lineage.html

# Scaffold a new table (prints a skeleton — you paste it in yourself)
python scripts/new_table.py --name dim_example --source bronze.Example --notebook orchestration_notebooks/nb_dim_example

# Propose a table from SQL (prints a proposal, writes nothing; --clipboard also copies it)
python scripts/sql_to_dbml.py path/to/file.sql

# Copy the DBML to the clipboard, e.g. for the dbdiagram.io editor
python scripts/copy_dbml.py

# Markdown preview (a dbml code fence), e.g. for Obsidian
python scripts/preview_md.py

# SQL DDL, only when you actually need it
python scripts/export_sql.py -o generated/schema.sql
```

Every one of these takes an optional DBML source — a file, a folder, or a list — and defaults to `dbml/schema.dbml` (see Tools).

## Testing

The scripts in `scripts/` have pytest tests in `tests/`:

```
# Once
pip install -r requirements.txt -r requirements-dev.txt

# Whenever scripts/ changes
pytest
```

The tests fall into two types:
- **Unit tests** for pure logic that already exists as separate functions (`lineage.py`'s `Lineage` class and helper functions, `copy_dbml.py`'s `strip_colors()`, `_dbml_source.py`'s path resolution) — imported directly via the `sys.path` entry `tests/conftest.py` adds, no changes to the scripts needed.
- **Integration tests** for the CLI scripts (`validate_dbml.py`, `export_sql.py`, `new_table.py`, `preview_md.py`) — run as a real CLI command via `subprocess` against DBML files in `tests/fixtures/`, checking the exit code + the output content. Includes regression tests for the file/folder/list input resolution (see `tests/fixtures/dbml_dir/`).

`sql_to_dbml.py` gets both kinds in one file (`tests/test_sql_to_dbml.py`): unit tests for its pure helper functions (calling `sqlglot` directly), plus integration tests for the CLI as a subprocess — it's the one script substantial enough to warrant its own combined test file rather than fitting neatly into either bullet above.

**Deliberately left out:** `copy_dbml.py`'s and `sql_to_dbml.py --clipboard`'s actual clipboard writing (calls PowerShell — a Windows-specific side effect) and `lineage.py`'s interactive HTML working in a real browser (needs an actual browser, not something pytest could substitute).

Run the tests whenever you change anything in `scripts/`, before considering the change done.

## For later (not done yet, not critical now)

- **CI**: once more than one person starts editing the model/scripts at the same time, it's worth running tests and validation automatically on PRs. Example GitHub Actions workflow (`.github/workflows/test.yml`) — not in use yet, add it as a file once it's genuinely needed:

  ```yaml
  name: test
  on: [push, pull_request]
  jobs:
    test:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: "3.12"
        - run: pip install -r requirements.txt -r requirements-dev.txt
        - run: python scripts/validate_dbml.py
        - run: pytest
  ```

  Note: the scripts and tests were developed/run on Windows (including `copy_dbml.py`'s PowerShell call), but the validation/test suite itself is platform-independent — `ubuntu-latest` would work fine in CI regardless, since `copy_dbml.py` isn't tested automatically (see Testing).
- A pre-commit hook (`validate_dbml.py` + `pytest` before every commit) is a lighter alternative to CI if GitHub Actions feels like overkill.
