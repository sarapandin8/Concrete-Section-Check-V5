from __future__ import annotations

from pathlib import Path

from concrete_pmm_pro.core.models import Point2D, Rebar, SectionGeometry
from concrete_pmm_pro.geometry.generators import rectangular_hollow
from concrete_pmm_pro.ui import rebar_page


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_rebar_page_professional_layout_sections_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "Rebar Input" in source
    assert "Rebar Status" in source
    assert "Rebar Summary" in source
    assert "cpmm-rebar-strip" in source
    assert "st.sidebar" not in source


def test_rebar_summary_strip_helper_escapes_values() -> None:
    html = rebar_page._strip_html([rebar_page.RebarMetric("Total <As>", "400 > 300", "safe & quiet")])

    assert "Total &lt;As&gt;" in html
    assert "400 &gt; 300" in html
    assert "safe &amp; quiet" in html


def test_rebar_validation_source_is_compact() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "No validation errors" not in source
    assert "WARNING: none" not in source
    assert "_kv_panel_html" in source


def test_rebar_ratio_uses_existing_section_area() -> None:
    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-100.0, y=-100.0),
            Point2D(x=100.0, y=-100.0),
            Point2D(x=100.0, y=100.0),
            Point2D(x=-100.0, y=100.0),
        ]
    )

    assert rebar_page._reinforcement_ratio_label(400.0, geometry) == "1.000%"


def test_rebar_ratio_is_na_without_geometry() -> None:
    assert rebar_page._reinforcement_ratio_label(400.0, None) == "N/A"


def test_perimeter_rebar_layout_generates_uniform_rectangle_points() -> None:
    from concrete_pmm_pro.geometry.rebar_layout import generate_perimeter_rebar_layout

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-300.0, y=-300.0),
            Point2D(x=300.0, y=-300.0),
            Point2D(x=300.0, y=300.0),
            Point2D(x=-300.0, y=300.0),
        ]
    )

    result = generate_perimeter_rebar_layout(
        geometry,
        bar_size="DB20",
        diameter_mm=20.0,
        material="SD40",
        edge_offset_mm=75.0,
        target_spacing_mm=150.0,
        min_bars=4,
        label_prefix="B",
    )

    assert result.ok
    assert not result.table.empty
    assert len(result.table) == 12  # offset square side = 450 mm, perimeter = 1800 mm
    assert result.actual_spacing_mm == 150.0
    assert set(result.table["Bar Size"]) == {"DB20"}
    assert set(result.table["Material"]) == {"SD40"}
    assert result.table["Count"].tolist() == [1] * 12


def test_perimeter_rebar_layout_rejects_impossible_offset() -> None:
    from concrete_pmm_pro.geometry.rebar_layout import generate_perimeter_rebar_layout

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-100.0, y=-100.0),
            Point2D(x=100.0, y=-100.0),
            Point2D(x=100.0, y=100.0),
            Point2D(x=-100.0, y=100.0),
        ]
    )

    result = generate_perimeter_rebar_layout(
        geometry,
        bar_size="DB20",
        diameter_mm=20.0,
        material="SD40",
        edge_offset_mm=125.0,
        target_spacing_mm=150.0,
    )

    assert not result.ok
    assert "offset is too large" in result.errors[0]


def test_rebar_page_exposes_auto_perimeter_preview_apply_workflow() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "Auto perimeter layout" in source
    assert "Bar center offset (mm)" in source
    assert "Target spacing (mm)" in source
    assert "Apply generated perimeter layout to Rebar table" in source
    assert "does not silently overwrite manual bars" in source


def test_perimeter_rebar_layout_places_mandatory_corner_control_bars() -> None:
    from concrete_pmm_pro.geometry.rebar_layout import generate_perimeter_rebar_layout

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-300.0, y=-300.0),
            Point2D(x=300.0, y=-300.0),
            Point2D(x=300.0, y=300.0),
            Point2D(x=-300.0, y=300.0),
        ]
    )

    result = generate_perimeter_rebar_layout(
        geometry,
        bar_size="DB20",
        diameter_mm=20.0,
        material="SD40",
        edge_offset_mm=75.0,
        target_spacing_mm=150.0,
        min_bars=4,
        label_prefix="B",
    )

    generated_points = {(round(row.x_mm, 3), round(row.y_mm, 3)) for row in result.table.itertuples()}
    assert {(-225.0, -225.0), (225.0, -225.0), (225.0, 225.0), (-225.0, 225.0)} <= generated_points
    assert any("Corner-controlled layout" in info for info in result.info)


def test_perimeter_rebar_layout_uses_outer_boundary_for_hollow_section() -> None:
    from concrete_pmm_pro.geometry.rebar_layout import generate_perimeter_rebar_layout

    geometry = rectangular_hollow(
        width_mm=1000.0,
        height_mm=800.0,
        t_top_mm=120.0,
        t_bottom_mm=140.0,
        t_left_mm=110.0,
        t_right_mm=130.0,
    )

    result = generate_perimeter_rebar_layout(
        geometry,
        bar_size="DB20",
        diameter_mm=20.0,
        material="SD40",
        edge_offset_mm=75.0,
        target_spacing_mm=150.0,
        min_bars=4,
        label_prefix="B",
    )

    assert result.ok
    generated_points = {(round(row.x_mm, 3), round(row.y_mm, 3)) for row in result.table.itertuples()}
    assert {(-425.0, -325.0), (425.0, -325.0), (425.0, 325.0), (-425.0, 325.0)} <= generated_points
    rebars = [
        Rebar(x_mm=float(row.x_mm), y_mm=float(row.y_mm), diameter_mm=20.0, material_name="SD40", label=str(row.Label))
        for row in result.table.itertuples()
    ]
    assert rebar_page.validate_rebars_against_geometry(rebars, geometry) == []


def test_rebar_preview_is_rendered_inside_status_column_before_summary() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    status_column_index = source.index("with status_col:")
    preview_index = source.index("Section Preview with Rebar")
    summary_index = source.index("Rebar Summary")

    assert status_column_index < preview_index < summary_index


def test_rebar_section_preview_draws_true_scale_bar_circles() -> None:
    from concrete_pmm_pro.core.models import Rebar
    from concrete_pmm_pro.visualization import create_section_preview

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-200.0, y=-300.0),
            Point2D(x=200.0, y=-300.0),
            Point2D(x=200.0, y=300.0),
            Point2D(x=-200.0, y=300.0),
        ]
    )
    rebar = Rebar(x_mm=75.0, y_mm=-125.0, diameter_mm=20.0, material_name="SD40", label="B1")

    fig = create_section_preview(geometry, rebars=[rebar])

    circle_shapes = [shape for shape in fig.layout.shapes if shape.type == "circle"]
    assert len(circle_shapes) == 1
    shape = circle_shapes[0]
    assert shape.xref == "x"
    assert shape.yref == "y"
    assert (shape.x1 - shape.x0) == 20.0
    assert (shape.y1 - shape.y0) == 20.0
    assert shape.x0 == 65.0
    assert shape.x1 == 85.0
    assert shape.y0 == -135.0
    assert shape.y1 == -115.0


def test_rebar_true_scale_preview_keeps_hover_marker_small() -> None:
    from concrete_pmm_pro.core.models import Rebar
    from concrete_pmm_pro.visualization import create_section_preview

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-200.0, y=-300.0),
            Point2D(x=200.0, y=-300.0),
            Point2D(x=200.0, y=300.0),
            Point2D(x=-200.0, y=300.0),
        ]
    )
    rebar = Rebar(x_mm=0.0, y_mm=0.0, diameter_mm=32.0, material_name="SD50", label="B1")

    fig = create_section_preview(geometry, rebars=[rebar])
    traces = {trace.name: trace for trace in fig.data}

    assert traces["Rebar"].marker.size == 4
    assert "display=true-scale diameter" in traces["Rebar"].text[0]


def test_rebar_page_groups_longitudinal_and_transverse_inputs_in_subtabs() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert 'st.tabs(["Longitudinal Rebar", "Transverse Rebar"])' in source
    assert "_render_longitudinal_rebar_tab" in source
    assert "_render_transverse_rebar_tab" in source
    assert "Beam/Girder torsion reads active ordinary bars" in source
    assert "Active stirrup zones are the provided layout" in source


def test_rebar_page_contains_column_pier_transverse_workflow_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "Column/Pier Shear and Torsion Reinforcement" in source
    assert "COLUMN_PIER_TRANSVERSE_TABLE_KEY" in source
    assert "column_pier_transverse_reinforcement_table" in source
    assert "future checks must not count prestress as longitudinal torsion Al" in source
    assert "Prestress strands, tendons, and PT bars are not counted as Al" in source
