"""Tests for sql_to_dbml.py. Unit tests for the pure helper functions
(sqlglot directly), integration tests for the CLI as a subprocess against
tests/fixtures/ files."""
import subprocess
import sys

import sqlglot
from sqlglot import exp

import sql_to_dbml as s2d


def test_full_table_name_with_schema():
    stmt = sqlglot.parse_one("SELECT 1 FROM silver.area AS a", dialect="databricks")
    table = stmt.find(exp.Table)
    assert s2d.full_table_name(table) == "silver.area"


def test_join_description_inner_and_left():
    stmt = sqlglot.parse_one(
        "SELECT 1 FROM a INNER JOIN b ON a.id = b.id LEFT JOIN c ON a.id = c.id",
        dialect="databricks",
    )
    joins = list(stmt.find_all(exp.Join))
    assert s2d.join_description(joins[0]) == "inner join"
    assert s2d.join_description(joins[1]) == "left join"


def test_extract_ctas_accepts_create_table_as_select():
    stmt = sqlglot.parse_one(
        "CREATE TABLE gold.x AS SELECT a.id FROM silver.a AS a", dialect="databricks"
    )
    result = s2d.extract_ctas(stmt)
    assert result is not None
    target, is_view, _select = result
    assert target == "gold.x"
    assert is_view is False


def test_extract_ctas_accepts_create_view_as_select():
    stmt = sqlglot.parse_one(
        "CREATE VIEW gold.x AS SELECT a.id FROM silver.a AS a", dialect="databricks"
    )
    result = s2d.extract_ctas(stmt)
    assert result is not None
    _target, is_view, _select = result
    assert is_view is True


def test_extract_ctas_rejects_plain_select():
    stmt = sqlglot.parse_one("SELECT * FROM silver.a", dialect="databricks")
    assert s2d.extract_ctas(stmt) is None


def test_extract_ctas_rejects_insert():
    stmt = sqlglot.parse_one(
        "INSERT INTO gold.x SELECT * FROM silver.a", dialect="databricks"
    )
    assert s2d.extract_ctas(stmt) is None


def test_source_description_lists_joins_with_type():
    stmt = sqlglot.parse_one(
        "CREATE TABLE gold.x AS SELECT 1 FROM a INNER JOIN b ON a.id = b.id "
        "LEFT JOIN c ON a.id = c.id",
        dialect="databricks",
    )
    _target, _is_view, select = s2d.extract_ctas(stmt)
    assert s2d.source_description(select) == "a + b + c (inner join b, left join c)"


def test_extract_raw_create_reads_columns_and_types():
    stmt = sqlglot.parse_one(
        "CREATE TABLE bronze.X (id INT PRIMARY KEY, name STRING, amount DECIMAL(10, 2))",
        dialect="databricks",
    )
    result = s2d.extract_raw_create(stmt)
    assert result is not None
    target, columns = result
    assert target == "bronze.X"
    assert columns == [
        ("id", "int", True),
        ("name", "string", False),
        ("amount", "decimal(10, 2)", False),
    ]


def test_extract_raw_create_reads_table_level_primary_key():
    stmt = sqlglot.parse_one(
        "CREATE TABLE bronze.X (a INT, b INT, PRIMARY KEY (a, b))", dialect="databricks"
    )
    _target, columns = s2d.extract_raw_create(stmt)
    assert [(name, is_pk) for name, _type, is_pk in columns] == [("a", True), ("b", True)]


def test_extract_raw_create_rejects_ctas():
    stmt = sqlglot.parse_one(
        "CREATE TABLE gold.x AS SELECT a.id FROM silver.a AS a", dialect="databricks"
    )
    assert s2d.extract_raw_create(stmt) is None


def test_extract_raw_create_rejects_plain_select():
    stmt = sqlglot.parse_one("SELECT * FROM silver.a", dialect="databricks")
    assert s2d.extract_raw_create(stmt) is None


def test_extract_foreign_keys_reads_inline_references():
    stmt = sqlglot.parse_one(
        "CREATE TABLE staging.orders (order_id INT PRIMARY KEY, "
        "customer_id INT REFERENCES staging.customer(customer_id))",
        dialect="postgres",
    )
    assert s2d.extract_foreign_keys(stmt) == [
        ("staging.orders", "customer_id", "staging.customer", "customer_id")
    ]


def test_extract_foreign_keys_reads_table_level_constraint():
    stmt = sqlglot.parse_one(
        "CREATE TABLE staging.orders (order_id INT, customer_id INT, "
        "FOREIGN KEY (customer_id) REFERENCES staging.customer(customer_id))",
        dialect="postgres",
    )
    assert s2d.extract_foreign_keys(stmt) == [
        ("staging.orders", "customer_id", "staging.customer", "customer_id")
    ]


def test_extract_foreign_keys_reads_alter_table_constraint():
    """pg_dump writes every foreign key as a separate ALTER TABLE long after
    the CREATE TABLE — without this, a dump imports as unconnected tables."""
    stmt = sqlglot.parse_one(
        "ALTER TABLE staging.orders ADD CONSTRAINT fk_orders_customer "
        "FOREIGN KEY (customer_id) REFERENCES staging.customer(customer_id)",
        dialect="postgres",
    )
    assert s2d.extract_foreign_keys(stmt) == [
        ("staging.orders", "customer_id", "staging.customer", "customer_id")
    ]


def test_extract_foreign_keys_ignores_unrelated_statements():
    stmt = sqlglot.parse_one("SELECT * FROM staging.orders", dialect="postgres")
    assert s2d.extract_foreign_keys(stmt) == []


def test_render_columns_writes_reference_inline():
    lines = s2d.render_columns(
        [("customer_id", "int", False, True)],
        {"customer_id": ("staging.customer", "customer_id")},
    )
    assert "[ref: > staging.customer.customer_id]" in lines[0]


def run_tool(*args, repo_root):
    return subprocess.run(
        [sys.executable, "scripts/sql_to_dbml.py", *[str(a) for a in args]],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_new_table_is_proposed_with_inferred_types(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "ctas_new.sql",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 0
    assert "Table gold.widget_monthly {" in result.stdout
    assert "widget_id" in result.stdout
    assert "integer" in result.stdout
    assert "notebook: TODO" in result.stdout


def test_existing_table_is_not_proposed(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "ctas_existing.sql",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 0
    assert "is already in the DBML source" in result.stdout
    assert "Table silver.fact_widget_event {" not in result.stdout


def test_non_ctas_statement_is_rejected(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "ctas_invalid.sql",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 1
    assert "only accepts" in result.stderr


def test_new_raw_table_is_proposed_from_ddl(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "create_raw_new.sql",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 0
    assert "Table bronze.RawWidgetEvents {" in result.stdout
    assert "event_id             int   [pk]" in result.stdout
    assert "TODO: verify type" not in result.stdout
    assert "source table: TODO" in result.stdout


def test_schema_dump_fails_without_skip_flag(fixtures_dir, repo_root):
    """The default stays strict: a dump contains SET/CREATE INDEX/ALTER, and
    without the flag the run fails loudly rather than ignoring them."""
    result = run_tool(
        fixtures_dir / "pg_dump_excerpt.sql",
        "--dialect",
        "postgres",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 1
    assert "--skip-unsupported" in result.stderr


def test_schema_dump_imports_tables_and_relations_with_skip_flag(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "pg_dump_excerpt.sql",
        "--dialect",
        "postgres",
        "--skip-unsupported",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 0
    assert "Table staging.customer {" in result.stdout
    assert "Table staging.orders {" in result.stdout
    # The foreign key lives in a separate ALTER TABLE, and still lands inline.
    assert "[ref: > staging.customer.customer_id]" in result.stdout
    # Skipped statements are reported, never silently dropped.
    assert "Skipped 3 unsupported statement(s)" in result.stdout


def test_existing_raw_table_is_not_proposed(fixtures_dir, repo_root):
    result = run_tool(
        fixtures_dir / "create_raw_existing.sql",
        "--dbml",
        fixtures_dir / "valid.dbml",
        repo_root=repo_root,
    )
    assert result.returncode == 0
    assert "is already in the DBML source" in result.stdout
    assert "Table silver.dim_widget {" not in result.stdout
