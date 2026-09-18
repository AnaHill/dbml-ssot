"""Unit tests for scripts/_dbml_source.py: file/folder/list input resolution
and preserving order (see AGENTS.md "Other files")."""
import pytest

import _dbml_source as dbml_source


def test_resolve_directory_returns_sorted_files(fixtures_dir):
    paths = dbml_source.resolve_dbml_paths([str(fixtures_dir / "dbml_dir")])
    assert [p.name for p in paths] == ["10_a.dbml", "20_b.dbml"]


def test_resolve_explicit_file_list_preserves_given_order(fixtures_dir):
    d = fixtures_dir / "dbml_dir"
    paths = dbml_source.resolve_dbml_paths([str(d / "20_b.dbml"), str(d / "10_a.dbml")])
    assert [p.name for p in paths] == ["20_b.dbml", "10_a.dbml"]


def test_load_dbml_source_concatenates_in_given_order(fixtures_dir):
    d = fixtures_dir / "dbml_dir"
    paths = dbml_source.resolve_dbml_paths([str(d / "20_b.dbml"), str(d / "10_a.dbml")])
    text = dbml_source.read_dbml_paths(paths)
    assert text.index("Table b") < text.index("Table a")


def test_resolve_missing_token_raises(fixtures_dir):
    with pytest.raises(FileNotFoundError):
        dbml_source.resolve_dbml_paths(["does_not_exist"])


def test_resolve_empty_directory_raises(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        dbml_source.resolve_dbml_paths([str(empty)])
