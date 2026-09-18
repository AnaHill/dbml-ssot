"""Integration test for export_sql.py."""
import subprocess
import sys


def test_export_sql_produces_create_table(fixtures_dir, repo_root):
    result = subprocess.run(
        [sys.executable, "scripts/export_sql.py", str(fixtures_dir / "valid.dbml")],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "CREATE TABLE" in result.stdout
    assert "dim_widget" in result.stdout
