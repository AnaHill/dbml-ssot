"""Unit tests for lineage.py's graph computation. Includes regression tests
for bugs found during this project's development."""
from pydbml import PyDBML

import lineage


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
    # more: an FK edge is a structural relation, not a flow.
    assert text.count("@-->") == len(lin.lineage_edges)
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
