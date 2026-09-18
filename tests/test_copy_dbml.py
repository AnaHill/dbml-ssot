"""Unit tests for copy_dbml.py's strip_colors(). Actual clipboard writing
(copy_to_clipboard, calls PowerShell) isn't tested automatically — it's a
Windows-specific side effect, not meaningful to run in CI."""
import copy_dbml


def test_strip_colors_removes_table_color():
    src = "Table foo [headercolor: #3498DB] {\n  id integer\n}"
    result, removed = copy_dbml.strip_colors(src)
    assert removed == 1
    assert "headercolor" not in result
    assert "Table foo {" in result


def test_strip_colors_removes_tablegroup_color():
    src = "TableGroup silver_layer [color: #C6E2FF] {\n  dim_a\n}"
    result, removed = copy_dbml.strip_colors(src)
    assert removed == 1
    assert "color" not in result
    assert "TableGroup silver_layer {" in result


def test_strip_colors_keeps_other_settings():
    src = "Table foo [headercolor: #3498DB, note: 'hello'] {\n  id integer\n}"
    result, removed = copy_dbml.strip_colors(src)
    assert removed == 1
    assert "headercolor" not in result
    assert "note: 'hello'" in result


def test_strip_colors_noop_when_no_colors():
    src = "Table foo {\n  id integer\n}"
    result, removed = copy_dbml.strip_colors(src)
    assert removed == 0
    assert result == src
