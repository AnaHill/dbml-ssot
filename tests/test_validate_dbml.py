"""Integration tests for validate_dbml.py — run as a real CLI command,
since the script has no separate pure logic outside argparse handling."""
import subprocess
import sys


def run_validate(*dbml_args, repo_root):
    return subprocess.run(
        [sys.executable, "scripts/validate_dbml.py", *[str(a) for a in dbml_args]],
        cwd=repo_root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_valid_dbml_passes(fixtures_dir, repo_root):
    result = run_validate(fixtures_dir / "valid.dbml", repo_root=repo_root)
    assert result.returncode == 0
    assert "OK (" in result.stdout


def test_invalid_alias_fails(fixtures_dir, repo_root):
    """Regression: 'AS' in uppercase isn't valid DBML syntax (found during
    this project's development — lowercase 'as' works)."""
    result = run_validate(fixtures_dir / "invalid_alias.dbml", repo_root=repo_root)
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_directory_input_reads_all_files(fixtures_dir, repo_root):
    result = run_validate(fixtures_dir / "dbml_dir", repo_root=repo_root)
    assert result.returncode == 0
    assert "2 tables" in result.stdout


def test_explicit_file_list_in_given_order(fixtures_dir, repo_root):
    """Regression: several files can be given as a list, used in the given
    order (the dbml/ folder split-per-domain scenario)."""
    d = fixtures_dir / "dbml_dir"
    result = run_validate(d / "20_b.dbml", d / "10_a.dbml", repo_root=repo_root)
    assert result.returncode == 0
    assert "2 tables" in result.stdout


def test_missing_path_fails_cleanly(repo_root):
    result = run_validate("does_not_exist", repo_root=repo_root)
    assert result.returncode == 1
    assert "ERROR" in result.stderr


def test_generic_rdbms_example_validates(repo_root):
    """Regression: examples/generic_rdbms.dbml proves that the same Note
    convention and the same scripts (no changes to scripts/) also work
    without Lakehouse/Databricks vocabulary — keep this example always
    valid."""
    result = run_validate(repo_root / "examples" / "generic_rdbms.dbml", repo_root=repo_root)
    assert result.returncode == 0
    assert "3 tables" in result.stdout
