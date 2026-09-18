#!/usr/bin/env python3
"""Proposes a DBML Table block from SQL CREATE statements, compared against
the current DBML source (default: dbml/schema.dbml, or the whole dbml/
folder if schema.dbml is missing — same resolution as the other scripts,
see scripts/_dbml_source.py).

Accepts ONLY two statement shapes:
1. `CREATE TABLE ... AS SELECT ...` / `CREATE [OR REPLACE] VIEW ... AS
   SELECT ...` (CTAS/CTAV) — column types are inferred from the source
   tables.
2. A plain `CREATE TABLE name (column type, ...)` (no AS SELECT) — columns
   and types are read straight from the DDL. Intended for raw/ingested
   tables (e.g. the bronze layer) that have no SQL source.

Any other SQL (a plain SELECT, INSERT, MERGE, ALTER, etc.) is rejected with
an error and nothing is proposed — the whole file/run is left unapplied if
even one statement fails to match either shape.

Prints a complete Table block for every target table not yet in the DBML
source. DOES NOT WRITE DIRECTLY to the dbml file (same principle as
new_table.py) — review the proposal and paste it yourself into the right
file and TableGroup block. If the target table already exists, nothing is
proposed and hand-written Note text/columns are never overwritten.

--clipboard also copies the printed proposals to the Windows clipboard (via
PowerShell) in addition to printing them — makes it easier to paste into a
.dbml file or e.g. dbdiagram.io. Doesn't affect whether anything is written
directly to a file — it only copies the output, it never writes.

Known gaps that can't be inferred from SQL:
- notebook path: always TODO — orchestration info isn't in the SQL.
- source table: inferred from the source tables for CTAS/CTAV statements;
  always TODO for a plain CREATE TABLE (no SQL source).
- the type of computed/aggregated columns (SUM, DATE_TRUNC, etc.) in
  CTAS/CTAV statements: if the source column isn't found in the given DBML
  source, the type becomes `varchar` and the column is marked
  `[note: 'TODO: verify type']`. In a plain CREATE TABLE the type always
  comes straight from the DDL, so this gap doesn't apply.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import sqlglot
from pydbml import PyDBML
from sqlglot import exp

from _dbml_source import describe_paths, read_dbml_paths, resolve_dbml_paths

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")


def copy_to_clipboard(text: str) -> None:
    """Copies text to the Windows clipboard via PowerShell. Same
    implementation as copy_dbml.py's — not imported from there, because
    _dbml_source.py is the only shared helper allowed between scripts
    (see AGENTS.md)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", encoding="utf-8-sig", delete=False
    ) as f:
        f.write(text)
        temp_path = f.name
    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                f"Get-Content -Raw -Encoding UTF8 '{temp_path}' | Set-Clipboard",
            ],
            check=True,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


def full_table_name(t: exp.Table) -> str:
    return f"{t.db}.{t.name}" if t.db else t.name


def join_description(join: exp.Join) -> str:
    side = join.args.get("side")
    kind = join.args.get("kind")
    parts = [p for p in (side, kind) if p]
    parts.append("join")
    return " ".join(parts).lower()


def extract_ctas(stmt: exp.Expression):
    """Returns (target, is_view, select) if stmt is a valid
    CREATE TABLE/VIEW ... AS SELECT, otherwise None."""
    if not isinstance(stmt, exp.Create):
        return None
    kind = (stmt.args.get("kind") or "").upper()
    if kind not in ("TABLE", "VIEW"):
        return None
    select = stmt.args.get("expression")
    if not isinstance(select, exp.Select):
        return None
    target = stmt.this
    table_exp = target.this if isinstance(target, exp.Schema) else target
    if not isinstance(table_exp, exp.Table):
        return None
    return full_table_name(table_exp), kind == "VIEW", select


def extract_raw_create(stmt: exp.Expression):
    """Returns (target, columns) if stmt is a valid plain
    `CREATE TABLE name (column type, ...)` statement (no AS SELECT),
    otherwise None. columns is a list of (name, type, is_pk) read straight
    from the DDL."""
    if not isinstance(stmt, exp.Create):
        return None
    kind = (stmt.args.get("kind") or "").upper()
    if kind != "TABLE" or stmt.args.get("expression") is not None:
        return None
    schema = stmt.this
    if not isinstance(schema, exp.Schema):
        return None
    table_exp = schema.this
    if not isinstance(table_exp, exp.Table):
        return None

    column_defs = [e for e in schema.expressions if isinstance(e, exp.ColumnDef)]
    if not column_defs:
        return None

    pk_names = set()
    for e in schema.expressions:
        if isinstance(e, exp.PrimaryKey):
            pk_names.update(c.name for c in e.expressions)
    for c in column_defs:
        if any(isinstance(con.kind, exp.PrimaryKeyColumnConstraint) for con in c.constraints):
            pk_names.add(c.this.name)

    columns = [
        (c.this.name, c.args.get("kind").sql(dialect="databricks").lower(), c.this.name in pk_names)
        for c in column_defs
    ]
    return full_table_name(table_exp), columns


def source_description(select: exp.Select) -> str:
    from_node = select.find(exp.From)
    base = from_node.this
    tables = [full_table_name(base)]
    join_notes = []
    for j in select.args.get("joins") or []:
        jt = j.this
        tables.append(full_table_name(jt))
        join_notes.append(f"{join_description(j)} {jt.name}")
    tables_part = " + ".join(tables)
    if join_notes:
        return f"{tables_part} ({', '.join(join_notes)})"
    return tables_part


def build_alias_map(select: exp.Select) -> dict[str, str]:
    from_node = select.find(exp.From)
    tables = [from_node.this] + [j.this for j in (select.args.get("joins") or [])]
    return {t.alias_or_name: full_table_name(t) for t in tables}


def build_columns(select: exp.Select, alias_map: dict[str, str], columns_by_table: dict[str, dict[str, str]]):
    group = select.args.get("group")
    group_sqls = {g.sql(dialect="databricks") for g in (group.expressions if group else [])}

    columns = []
    for proj in select.expressions:
        expr = proj.this if isinstance(proj, exp.Alias) else proj
        name = proj.alias_or_name
        is_pk = expr.sql(dialect="databricks") in group_sqls

        col_type, sure = "varchar", False
        if isinstance(expr, exp.Column):
            real_table = alias_map.get(expr.table)
            source_cols = columns_by_table.get(real_table, {})
            if expr.name in source_cols:
                col_type, sure = source_cols[expr.name], True

        columns.append((name, col_type, is_pk, sure))
    return columns


def render_columns(columns) -> list[str]:
    """columns: a list of (name, type, is_pk, sure) — 'sure' controls
    whether '[note: TODO: verify type]' is added; for plain CREATE TABLE
    columns sure=True always, since the type comes straight from the DDL
    and isn't an inference."""
    lines = []
    for col_name, col_type, is_pk, sure in columns:
        settings = []
        if is_pk:
            settings.append("pk")
        if not sure:
            settings.append("note: 'TODO: verify type'")
        setting_str = f"   [{', '.join(settings)}]" if settings else ""
        lines.append(f"  {col_name:<20} {col_type}{setting_str}")
    return lines


def render_table_block(target: str, is_view: bool, columns, source_desc: str) -> str:
    schema, _, _name = target.partition(".")
    lines = [f"Table {target} {{"]
    lines.extend(render_columns(columns))
    lines.append("")
    note_lines = ["  Note: '''", f"    source table: {source_desc}", "    notebook: TODO"]
    if is_view:
        note_lines.append("    remark: SQL view, not a physical table")
    note_lines.append("  '''")
    lines.extend(note_lines)
    lines.append("}")
    lines.append(f"# Remember to add {target} to the correct TableGroup block (schema '{schema}' -> *_layer).")
    return "\n".join(lines)


def render_raw_table_block(target: str, columns) -> str:
    """columns: a list of (name, type, is_pk) straight from the DDL — no
    type inference."""
    schema, _, _name = target.partition(".")
    lines = [f"Table {target} {{"]
    lines.extend(render_columns([(n, t, pk, True) for n, t, pk in columns]))
    lines.append("")
    lines.extend(
        [
            "  Note: '''",
            "    source table: TODO",
            "    notebook: TODO",
            "    remark: created from a plain CREATE TABLE statement (no AS SELECT) — columns/types come from the DDL, but the source system isn't in the SQL",
            "  '''",
        ]
    )
    lines.append("}")
    lines.append(f"# Remember to add {target} to the correct TableGroup block (schema '{schema}' -> *_layer).")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sql_files",
        nargs="+",
        type=Path,
        help="SQL file(s) to read CTAS/CTAV or plain CREATE TABLE statements from",
    )
    parser.add_argument(
        "--dbml",
        dest="dbml_files",
        nargs="*",
        default=None,
        help="DBML source to check against (default: dbml/schema.dbml or the dbml/ folder)",
    )
    parser.add_argument("--dialect", default="databricks", help="SQL dialect for sqlglot (default: databricks)")
    parser.add_argument(
        "--clipboard",
        action="store_true",
        help="also copy the proposals to the clipboard (Windows, PowerShell) in addition to printing",
    )
    args = parser.parse_args()

    try:
        dbml_paths = resolve_dbml_paths(args.dbml_files)
        db = PyDBML(read_dbml_paths(dbml_paths))
    except Exception as e:
        print(f"ERROR (DBML source): {e}", file=sys.stderr)
        return 1

    existing_names = {(f"{t.schema}.{t.name}" if t.schema else t.name) for t in db.tables}
    columns_by_table: dict[str, dict[str, str]] = {}
    for t in db.tables:
        full = f"{t.schema}.{t.name}" if t.schema else t.name
        columns_by_table[full] = {c.name: c.type for c in t.columns}

    had_error = False
    proposals = []

    for sql_file in args.sql_files:
        try:
            sql_text = sql_file.read_text(encoding="utf-8")
        except OSError as e:
            print(f"ERROR ({sql_file}): {e}", file=sys.stderr)
            had_error = True
            continue

        try:
            statements = sqlglot.parse(sql_text, dialect=args.dialect)
        except Exception as e:
            print(f"ERROR ({sql_file}): could not parse SQL: {e}", file=sys.stderr)
            had_error = True
            continue

        for i, stmt in enumerate(s for s in statements if s is not None):
            ctas = extract_ctas(stmt)
            raw = extract_raw_create(stmt) if ctas is None else None
            if ctas is None and raw is None:
                print(
                    f"ERROR ({sql_file}, statement {i + 1}): only accepts "
                    "'CREATE TABLE ... AS SELECT', 'CREATE [OR REPLACE] VIEW "
                    "... AS SELECT', or a plain 'CREATE TABLE name (column "
                    "type, ...)' statement.",
                    file=sys.stderr,
                )
                had_error = True
                continue

            if ctas is not None:
                target, is_view, select = ctas
                if target in existing_names:
                    print(f"OK ({sql_file}): {target} is already in the DBML source ({describe_paths(dbml_paths)}) — no change proposed.")
                    continue
                proposals.append(("ctas", sql_file, target, is_view, select))
            else:
                target, columns = raw
                if target in existing_names:
                    print(f"OK ({sql_file}): {target} is already in the DBML source ({describe_paths(dbml_paths)}) — no change proposed.")
                    continue
                proposals.append(("raw", sql_file, target, columns))

    if had_error:
        print("\nERROR: one or more statements were invalid — nothing proposed.", file=sys.stderr)
        return 1

    if not proposals:
        print("No new tables to propose.")
        return 0

    blocks = []
    for proposal in proposals:
        kind = proposal[0]
        if kind == "ctas":
            _, sql_file, target, is_view, select = proposal
            alias_map = build_alias_map(select)
            columns = build_columns(select, alias_map, columns_by_table)
            source_desc = source_description(select)
            block = render_table_block(target, is_view, columns, source_desc)
        else:
            _, sql_file, target, columns = proposal
            block = render_raw_table_block(target, columns)
        print(f"\n# Proposal ({sql_file}):")
        print(block)
        blocks.append(f"# Proposal ({sql_file}):\n{block}")

    if args.clipboard:
        clipboard_text = "\n\n".join(blocks) + "\n"
        try:
            copy_to_clipboard(clipboard_text)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"\nERROR: failed to copy to clipboard: {e}", file=sys.stderr)
            return 1
        print(f"\nCopied to clipboard ({len(proposals)} proposal(s), {len(clipboard_text)} characters).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
