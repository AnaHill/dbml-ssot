"""Integration test for new_table.py."""
import subprocess
import sys


def test_new_table_scaffold(repo_root):
    result = subprocess.run(
        [
            sys.executable,
            "scripts/new_table.py",
            "--name",
            "dim_example",
            "--source",
            "bronze.Example",
            "--notebook",
            "orchestration_notebooks/nb_dim_example",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "Table dim_example {" in result.stdout
    assert "source table: bronze.Example" in result.stdout
    assert "notebook: orchestration_notebooks/nb_dim_example" in result.stdout
