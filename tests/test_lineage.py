"""Unit tests for lineage.py's graph computation. Includes regression tests
for bugs found during this project's development."""
import json
import subprocess
import sys
from pathlib import Path

from pydbml import PyDBML

import lineage

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lineage.py"


def test_mermaid_id_sanitizes_special_chars():
    assert lineage.mermaid_id("silver.dim_area") == "silver_dim_area"
    assert lineage.mermaid_id("bronze.Area") == "bronze_Area"


def test_mermaid_id_prefixes_leading_digit():
    assert lineage.mermaid_id("1abc").startswith("n_")


def test_parse_note_extracts_source_and_notebook():
    note = "source table: bronze.Area\nnotebook: orchestration_notebooks/nb_dim_area"
    source, notebook, mechanism = lineage.parse_note(note)
    assert source == "bronze.Area"
    assert notebook == "orchestration_notebooks/nb_dim_area"
    assert mechanism is None


def test_parse_note_extracts_optional_mechanism():
    note = (
        "source table: bronze.Area\n"
        "notebook: adf_pipelines/pl_copy_bronze_area\n"
        "mechanism: pipeline"
    )
    source, notebook, mechanism = lineage.parse_note(note)
    assert source == "bronze.Area"
    assert notebook == "adf_pipelines/pl_copy_bronze_area"
    assert mechanism == "pipeline"


def test_is_missing_treats_todo_and_empty_as_missing():
    assert lineage.is_missing(None)
    assert lineage.is_missing("")
    assert lineage.is_missing("TODO")
    assert lineage.is_missing("todo")
    assert not lineage.is_missing("bronze.Area")


def test_join_source_splits_into_real_table_edges():
    """Regression: an 'A + B (join)' source must not create duplicate
    nodes when A and B are already tables in the model — a bug that made
    Mermaid's layout stack layers on top of each other before the fix."""
    src = """
    Table silver.dim_a {
      id integer [pk]
      Note: '''
        source table: bronze.A
        notebook: nb_a
      '''
    }
    Table silver.dim_b {
      id integer [pk]
      Note: '''
        source table: bronze.B
        notebook: nb_b
      '''
    }
    Table silver.dim_combined {
      id integer [pk]
      Note: '''
        source table: silver.dim_a + silver.dim_b (join)
        notebook: nb_combined
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)

    combined_nb_id = lineage.mermaid_id("nb_nb_combined")
    froms = {a for a, b in lin.lineage_edges if b == combined_nb_id}

    assert froms == {"silver_dim_a", "silver_dim_b"}
    assert not any(f.startswith("src_silver") for f in froms)


def test_union_all_source_splits_into_real_table_edges():
    """Regression: 'A union all B' (no +/, separator) must split into two
    sources the same way 'A + B' already did — the word 'union'/'union
    all' is recognized as a separator just like 'join'."""
    src = """
    Table silver.trips_2022 {
      id integer [pk]
      Note: '''
        source table: bronze.Trips2022
        notebook: nb_2022
      '''
    }
    Table silver.trips_2021 {
      id integer [pk]
      Note: '''
        source table: bronze.Trips2021
        notebook: nb_2021
      '''
    }
    Table gold.total_trips {
      id integer [pk]
      Note: '''
        source table: silver.trips_2022 union all silver.trips_2021
        notebook: nb_total_trips
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)

    total_nb_id = lineage.mermaid_id("nb_nb_total_trips")
    froms = {a for a, b in lin.lineage_edges if b == total_nb_id}

    assert froms == {"silver_trips_2022", "silver_trips_2021"}


def test_missing_note_becomes_todo_edge():
    src = """
    Table silver.dim_no_note {
      id integer [pk]
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)

    assert len(lin.todo_edges) == 1
    _src_id, _nb_id, tid = lin.todo_edges[0]
    assert tid == "silver_dim_no_note"


def test_orch_mechanism_defaults_to_notebook_when_missing():
    src = """
    Table silver.dim_a {
      id integer [pk]
      Note: '''
        source table: bronze.A
        notebook: nb_a
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)
    nb_id = lineage.mermaid_id("nb_nb_a")
    assert lin.orch_mechanism[nb_id] == "notebook"


def test_orch_mechanism_reads_explicit_pipeline_value():
    src = """
    Table bronze.X {
      id integer [pk]
      Note: '''
        source table: source_system.x
        notebook: adf_pipelines/pl_copy_x
        mechanism: pipeline
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)
    nb_id = lineage.mermaid_id("nb_adf_pipelines/pl_copy_x")
    assert lin.orch_mechanism[nb_id] == "pipeline"


def test_render_mermaid_uses_distinct_classdef_per_mechanism():
    src = """
    Table silver.dim_a {
      id integer [pk]
      Note: '''
        source table: bronze.A
        notebook: nb_a
      '''
    }
    Table gold.dim_b {
      id integer [pk]
      Note: '''
        source table: silver.dim_a
        notebook: stored_procedures/usp_load_b
        mechanism: stored_procedure
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)
    text = lineage.render_mermaid(lin)

    assert "classDef mech_notebook" in text
    assert "classDef mech_stored_procedure" in text
    fill, stroke = lineage.MECHANISM_STYLES["stored_procedure"]
    assert f"classDef mech_stored_procedure fill:{fill},stroke:{stroke}" in text


ANIMATION_FIXTURE = """
Table silver.dim_a {
  id integer [pk]
  Note: '''
    source table: bronze.A
    notebook: nb_a
  '''
}
Table gold.dim_b {
  id integer [pk, ref: > silver.dim_a.id]
  Note: '''
    source table: silver.dim_a
    notebook: nb_b
  '''
}
"""


def test_render_mermaid_animates_lineage_edges_only_when_interactive():
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    text = lineage.render_mermaid(lin, interactive=True)

    # One id'd arrow and one animate statement per lineage edge, and nothing
    # more: an FK edge is a structural relation, not a flow. Both arrow
    # forms count — thin into a process node, thick out of it.
    assert text.count("@-->") + text.count("@==>") == len(lin.lineage_edges)
    assert text.count("@{ animate: true }") == len(lin.lineage_edges)
    assert "e0@-->" in text
    assert "e0@{ animate: true }" in text
    assert "-.->|FK|" in text


def test_render_mermaid_keeps_plain_arrows_for_markdown_output():
    """The .md output must stay on the plain `-->` form: GitHub's and
    Obsidian's bundled Mermaid may predate the edge-id syntax (11.5+) and
    would render an error instead of the diagram."""
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    text = lineage.render_mermaid(lin)

    assert "@-->" not in text
    assert "animate" not in text
    assert " --> " in text


def test_render_mermaid_uses_thick_arrow_only_for_the_populating_hop():
    """A process reads the table on its input hop and populates the table on
    its output hop — the thick arrow marks the second. Both keep their
    arrowhead: in Mermaid's layout an edge often passes under an unrelated
    node, and the arrowhead is what separates "ends here" from "passes by"."""
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    text = lineage.render_mermaid(lin)

    for a, b in lin.lineage_edges:
        if a in lin.orch_nodes:
            assert f"  {a} ==> {b}" in text
        else:
            assert f"  {a} --> {b}" in text


def test_render_mermaid_keeps_edge_ids_on_thick_arrows_when_interactive():
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    text = lineage.render_mermaid(lin, interactive=True)

    assert "@==>" in text
    assert "@-->" in text
    assert text.count("@{ animate: true }") == len(lin.lineage_edges)


def test_legend_lists_only_what_the_diagram_shows():
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    html = lineage.legend_html(lin)

    assert "reads" in html and "writes" in html
    assert "notebook" in html
    # No stored procedure or pipeline is used by this model, and nothing is
    # missing, so neither may appear in the legend.
    assert "stored procedure" not in html
    assert "TODO" not in html


def test_legend_shows_todo_entry_when_lineage_is_missing():
    src = """
    Table silver.dim_no_note {
      id integer [pk]
    }
    """
    html = lineage.legend_html(lineage.Lineage(PyDBML(src)))

    assert "TODO" in html


def test_layer_list_includes_source_and_orchestration_layers():
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    ids = [layer["id"] for layer in lineage.layer_list(lin)]

    # The pseudo-layers come first, in diagram order, so their checkboxes
    # can be hidden/shown like any TableGroup.
    assert ids[:2] == ["sources", "orchestration"]
    for group in lin.groups:
        assert group["id"] in ids


def test_layer_list_and_graph_json_agree():
    """The checkboxes and the page's JSON are built from the same list —
    a layer with no checkbox could never be hidden, and a checkbox for a
    layer no node belongs to would do nothing."""
    lin = lineage.Lineage(PyDBML(ANIMATION_FIXTURE))
    from_json = [layer["id"] for layer in json.loads(lineage.graph_json(lin))["layers"]]

    assert from_json == [layer["id"] for layer in lineage.layer_list(lin)]


def test_html_output_has_layer_toggles_and_export_controls(tmp_path, fixtures_dir):
    out = tmp_path / "lineage.html"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(fixtures_dir / "valid.dbml"), "-o", str(out)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    html = out.read_text(encoding="utf-8")
    assert 'data-layer-toggle="sources"' in html
    assert 'data-layer-toggle="orchestration"' in html
    assert 'id="export-download"' in html
    assert 'id="export-copy"' in html


def test_render_mermaid_produces_flowchart_header():
    src = """
    Table silver.dim_a {
      id integer [pk]
      Note: '''
        source table: bronze.A
        notebook: nb_a
      '''
    }
    """
    db = PyDBML(src)
    lin = lineage.Lineage(db)
    text = lineage.render_mermaid(lin)

    assert text.startswith("flowchart LR")
    assert "silver_dim_a" in text
