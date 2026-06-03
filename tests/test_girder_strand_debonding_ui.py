from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESTRESS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "prestress_page.py").read_text(encoding="utf-8")
PROJECT_IO_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "io" / "project_io.py").read_text(encoding="utf-8")


def test_prestress_page_contains_strand_layout_debonding_workflow() -> None:
    assert "Simple-Supported Girder Strand Layout & Debonding" in PRESTRESS_SOURCE
    assert "girder_strand_layout_table" in PRESTRESS_SOURCE
    assert "Left debond m" in PRESTRESS_SOURCE
    assert "Right debond m" in PRESTRESS_SOURCE
    assert "Effective prestress preview" in PRESTRESS_SOURCE
    assert "12.7 mm low-relaxation strand" in PRESTRESS_SOURCE
    assert "15.2 mm low-relaxation strand" in PRESTRESS_SOURCE
    assert "PS6A supports optional individual bonded/unbonded strand selection within a row" in PRESTRESS_SOURCE
    assert "Computed spacing_mm" in PRESTRESS_SOURCE
    assert "3db minimum spacing" in PRESTRESS_SOURCE
    assert "reduce the number of strands in this row" in PRESTRESS_SOURCE
    assert "Transfer/development length transition is not modeled" in PRESTRESS_SOURCE
    assert "does not change current Analysis results" in PRESTRESS_SOURCE
    assert "Rebuild default strand layout from current section" in PRESTRESS_SOURCE
    assert "2 rows at y=50/100 mm" in PRESTRESS_SOURCE
    assert 'line={"color": section_line_color, "width": 2.0, "dash": "solid"}' in PRESTRESS_SOURCE
    assert 'name="Bonded"' in PRESTRESS_SOURCE
    assert 'name="Debonded"' in PRESTRESS_SOURCE
    assert "diamond-open" in PRESTRESS_SOURCE
    assert 'xanchor="left"' in PRESTRESS_SOURCE
    assert "label_gap = max(340.0" in PRESTRESS_SOURCE
    assert "on_change=_sync_girder_strand_layout_editor_to_table" in PRESTRESS_SOURCE
    assert "Row 1 at the bottom" in PRESTRESS_SOURCE
    assert "_girder_debonding_schedule_dataframe" in PRESTRESS_SOURCE
    assert "Debonding QA" in PRESTRESS_SOURCE
    assert "_render_girder_debonding_rule_dashboard" in PRESTRESS_SOURCE
    assert "Debonding rule audit — individual preview" in PRESTRESS_SOURCE
    assert "Critical transfer station audit" in PRESTRESS_SOURCE


def test_project_io_preserves_girder_strand_layout_metadata_source() -> None:
    assert "girder_strand_layout_table" in PROJECT_IO_SOURCE
    assert "girder_prestress_system_settings" in PROJECT_IO_SOURCE
    assert "_girder_strand_layout_metadata_from_session" in PROJECT_IO_SOURCE


def test_strand_layout_normalization_and_station_preview_with_streamlit_stub(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_effective_prestress_preview_dataframe,
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 140.0,
                "y_mm_from_bottom": 100.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 140.0,
                "y_mm_from_bottom": 200.0,
                "Pe_transfer/strand_kN": 150.0,
                "Pe_construction/strand_kN": 140.0,
                "Pe_eff_final/strand_kN": 120.0,
                "Left debond m": 3.0,
                "Right debond m": 3.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    assert table.loc[0, "Total Aps_mm2"] == 280.0
    assert table.loc[1, "Total Aps_mm2"] == 280.0

    preview = _girder_effective_prestress_preview_dataframe(table, 10.0).set_index("x_m")
    assert preview.loc[0.0, "Effective strands"] == 2
    assert preview.loc[5.0, "Effective strands"] == 4
    assert preview.loc[5.0, "Pe_transfer_eff_kN"] == 600.0
    assert preview.loc[5.0, "yps_eff_mm_from_bottom"] == 150.0

    points = _girder_strand_point_layout_dataframe(table, None)
    assert len(points) == 4
    assert set(points["Group ID"]) == {"Row 1", "Row 2"}


def test_longitudinal_debonding_plot_shows_sleeve_symbols_with_streamlit_stub(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_longitudinal_debonding_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Debonded row",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "Area/Strand_mm2": 98.7,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 2.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_longitudinal_debonding_layout(table, span_length_m=10.0)
    trace_names = [trace.name for trace in fig.data]
    marker_symbols = [getattr(getattr(trace, "marker", None), "symbol", None) for trace in fig.data]

    assert "Debonded" in trace_names
    assert "Bonded" in trace_names
    assert "diamond-open" in marker_symbols
    assert any(annotation.text == "L=1.00 m" for annotation in fig.layout.annotations)
    assert any(annotation.text == "R=2.00 m" for annotation in fig.layout.annotations)
    bonded_traces = [trace for trace in fig.data if trace.name == "Bonded"]
    assert bonded_traces
    assert all(trace.line.color == "#1f77b4" for trace in bonded_traces)


def test_cross_section_plot_and_debond_schedule_show_row_debond_status(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_debonding_schedule_dataframe,
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 2.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_strand_cross_section_layout(table, None)
    trace_names = [trace.name for trace in fig.data]
    assert "Bonded" in trace_names or "Debonded" in trace_names
    label_texts = [annotation.text for annotation in fig.layout.annotations]
    assert any(getattr(annotation, "xanchor", None) == "left" for annotation in fig.layout.annotations)
    assert all("<br>" not in label for label in label_texts)
    assert any("Row 1 · total 2 · B=0 · U=2 · Debonded both ends · L=1.00 m · R=1.00 m" == label for label in label_texts)

    schedule = _girder_debonding_schedule_dataframe(table, span_length_m=10.0)
    assert schedule.loc[0, "Debond status"] == "Debonded both ends"
    assert schedule.loc[0, "Left debond m"] == 1.0
    assert schedule.loc[0, "Right debond m"] == 1.0
    assert schedule.loc[1, "Debond status"] == "Right debonded"
    assert schedule.loc[1, "Bonded zone m"] == "0.000 → 8.000"




def test_cross_section_plot_shows_individual_bonded_and_debonded_points(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_debonding_schedule_dataframe,
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
        _plot_girder_strand_cross_section_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 6,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
                "Debonded strand nos": "1,6",
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    points = _girder_strand_point_layout_dataframe(table, None)
    assert points["Debonded selected"].tolist().count(True) == 2
    assert points["Debonded selected"].tolist().count(False) == 4

    fig = _plot_girder_strand_cross_section_layout(table, None)
    trace_names = [trace.name for trace in fig.data]
    assert "Bonded" in trace_names
    assert "Debonded" in trace_names
    assert any("B=4 · U=2" in annotation.text for annotation in fig.layout.annotations)

    schedule = _girder_debonding_schedule_dataframe(table, 10.0)
    assert schedule.loc[0, "Bonded strands"] == 4
    assert schedule.loc[0, "Debonded strands"] == 2
    assert schedule.loc[0, "Debonded strand nos"] == "1, 6"
    assert schedule.loc[0, "Selection mode"] == "Individual"

def test_data_editor_patch_payload_persists_first_edit_without_dataframe_value_error(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    _data_editor_payload_to_dataframe = prestress_page._data_editor_payload_to_dataframe
    _normalize_girder_strand_layout_table = prestress_page._normalize_girder_strand_layout_table
    _sync_girder_strand_layout_editor_to_table = prestress_page._sync_girder_strand_layout_editor_to_table

    base = _normalize_girder_strand_layout_table(
        pd.DataFrame(
            [
                {
                    "Active": True,
                    "Group ID": "Row 1",
                    "Strand Size": "12.7 mm low-relaxation strand",
                    "No. Strands": 19,
                    "y_mm_from_bottom": 50.0,
                    "Left debond m": 0.0,
                    "Right debond m": 0.0,
                }
            ]
        ),
        span_length_m=30.0,
    )
    prestress_page.st.session_state.clear()
    prestress_page.st.session_state["girder_strand_layout_table"] = base
    prestress_page.st.session_state["girder_strand_layout_editor"] = {
        "edited_rows": {0: {"Left debond m": 1.5, "Right debond m": 1.0}},
        "added_rows": [],
        "deleted_rows": [],
    }

    patched = _data_editor_payload_to_dataframe(prestress_page.st.session_state["girder_strand_layout_editor"], base)
    assert patched.loc[0, "Left debond m"] == 1.5
    assert patched.loc[0, "Right debond m"] == 1.0

    _sync_girder_strand_layout_editor_to_table(30.0, "Left/right independent", None)
    saved = prestress_page.st.session_state["girder_strand_layout_table"]
    assert saved.loc[0, "Left debond m"] == 1.5
    assert saved.loc[0, "Right debond m"] == 1.0



def test_longitudinal_plot_orders_row_1_at_bottom_and_hides_termination_text(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _plot_girder_longitudinal_debonding_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 50.0,
                "Left debond m": 1.0,
                "Right debond m": 1.0,
            },
            {
                "Active": True,
                "Group ID": "Row 2",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            },
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=10.0)
    fig = _plot_girder_longitudinal_debonding_layout(table, span_length_m=10.0)
    assert list(fig.layout.yaxis.tickvals) == [1, 2]
    assert fig.layout.yaxis.ticktext[0].startswith("Row 1")
    assert all("termination" not in str(getattr(trace, "text", "")).lower() for trace in fig.data)



def test_girder_strand_default_size_is_12_7_mm_with_auto_area(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        DEFAULT_GIRDER_STRAND_SIZE,
        _normalize_girder_strand_layout_table,
    )

    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0)
    assert DEFAULT_GIRDER_STRAND_SIZE == "12.7 mm low-relaxation strand"
    assert set(table["Strand Size"]) == {"12.7 mm low-relaxation strand"}
    assert table.loc[0, "Area/Strand_mm2"] == 98.7
    assert len(table.index) == 2
    assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0]
    assert table["No. Strands"].tolist() == [8, 6]
    assert table.loc[0, "Total Aps_mm2"] == 8 * 98.7
    assert table.loc[0, "Edge CL_mm"] == 45.0
    assert table.loc[0, "Min spacing_mm"] == 50.0



def test_section_based_default_strand_layout_uses_current_section_width(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.core.models import Point2D, SectionGeometry  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import _normalize_girder_strand_layout_table  # noqa: PLC0415

    geometry = SectionGeometry(
        outer_polygon=[
            Point2D(x=-300.0, y=-300.0),
            Point2D(x=300.0, y=-300.0),
            Point2D(x=300.0, y=300.0),
            Point2D(x=-300.0, y=300.0),
        ]
    )

    table = _normalize_girder_strand_layout_table(None, span_length_m=30.0, geometry=geometry)

    assert len(table.index) == 2
    assert table["No. Strands"].tolist() == [11, 11]
    assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0]
    assert set(table["Strand Size"]) == {"12.7 mm low-relaxation strand"}

def test_girder_strand_size_controls_spacing_and_edge_clearance(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "15.2 row",
                "Strand Size": "15.2 mm low-relaxation strand",
                "No. Strands": 8,
                "Edge CL_mm": 50.0,
                "Min spacing_mm": 50.0,
                "y_mm_from_bottom": 100.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=20.0)
    assert table.loc[0, "Edge CL_mm"] == 45.0
    assert table.loc[0, "Min spacing_mm"] == 55.0

    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=None)
    assert errors == []
    assert all("less than minimum" not in warning for warning in warnings)


def test_girder_strand_layout_ui_is_gated_to_beam_girder_preset(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.core.models import PrestressElement  # noqa: PLC0415
    import concrete_pmm_pro.ui.prestress_page as prestress_page  # noqa: PLC0415

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "column_pier_pmm"}, "section_preset_key": "parametric_i_girder"}
    assert not prestress_page._is_girder_prestress_layout_workflow_active()

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "beam_girder"}, "section_preset_key": "rectangle"}
    assert not prestress_page._is_girder_prestress_layout_workflow_active()

    prestress_page.st.session_state = {"analysis_mode_settings": {"member_type": "beam_girder"}, "section_preset_key": "parametric_i_girder"}
    assert prestress_page._is_girder_prestress_layout_workflow_active()

    passive = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=0, initial_stress_mpa=0, initial_strain=0)
    active = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=1000, initial_stress_mpa=10, initial_strain=10 / 195000)
    assert not prestress_page._has_active_prestress_force([passive])
    assert prestress_page._has_active_prestress_force([active])


def test_default_prestress_rows_are_inactive_examples() -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    sys.modules.setdefault("streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import _default_prestress_table, load_prestress_steel_database  # noqa: PLC0415

    table = _default_prestress_table(load_prestress_steel_database())
    assert table["Active"].tolist() == [False, False]


def test_girder_strand_points_are_center_out_not_edge_spread(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _girder_strand_point_layout_dataframe,
        _normalize_girder_strand_layout_table,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Two center strands",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 2,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 100.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(raw, span_length_m=20.0)
    points = _girder_strand_point_layout_dataframe(table, geometry=None).sort_values("x_mm")

    assert points["x_mm"].round(6).tolist() == [-25.0, 25.0]
    assert points["Computed spacing_mm"].tolist() == [50.0, 50.0]


def test_prestress_source_contains_compact_strand_editor_and_rerun_guard() -> None:
    assert "GIRDER_STRAND_LAYOUT_EDITOR_COLUMNS" in PRESTRESS_SOURCE
    assert "Left debond m" in PRESTRESS_SOURCE
    assert "Right debond m" in PRESTRESS_SOURCE
    assert "_store_girder_strand_layout_and_rerun_on_change" in PRESTRESS_SOURCE
    assert "centerline outward" in PRESTRESS_SOURCE
    assert "🟨" in PRESTRESS_SOURCE


def test_box_beam_default_strand_layout_passes_void_aware_validation(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import box_section_fillet, precast_box_beam_exterior  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    geometries = [
        box_section_fillet(
            width_mm=990,
            height_mm=700,
            h1_mm=180,
            h3_mm=160,
            h4_mm=80,
            h5_mm=200,
            h6_mm=300,
            h7_mm=400,
            h8_mm=70,
            b2_mm=100,
            b3_mm=290,
            b4_mm=70,
        ),
        precast_box_beam_exterior(
            width_mm=990,
            height_mm=700,
            h1_mm=180,
            h3_mm=160,
            h4_mm=80,
            h5_mm=200,
            h6_mm=300,
            h7_mm=400,
            h8_mm=70,
            b2_mm=100,
            b3_mm=360,
            b4_mm=70,
        ),
    ]
    for geometry in geometries:
        table = _normalize_girder_strand_layout_table(None, span_length_m=20.0, geometry=geometry)
        errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
        assert errors == []
        assert warnings == []
        assert table["y_mm_from_bottom"].tolist() == [50.0, 100.0]
        assert table["No. Strands"].tolist() == [19, 19]


def test_box_beam_strand_layout_warns_when_strands_enter_void_or_cover_is_low(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.geometry.generators import box_section_fillet  # noqa: PLC0415
    from concrete_pmm_pro.ui.prestress_page import (  # noqa: PLC0415
        _normalize_girder_strand_layout_table,
        _validate_girder_strand_layout,
    )

    geometry = box_section_fillet(
        width_mm=990,
        height_mm=700,
        h1_mm=180,
        h3_mm=160,
        h4_mm=80,
        h5_mm=200,
        h6_mm=300,
        h7_mm=400,
        h8_mm=70,
        b2_mm=100,
        b3_mm=290,
        b4_mm=70,
    )
    void_row = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Void row",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 3,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 200.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(void_row, span_length_m=20.0, geometry=geometry)
    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
    assert errors == []
    assert any("inside a void/chamfer" in warning for warning in warnings)

    low_cover_row = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Low cover",
                "Strand Size": "12.7 mm low-relaxation strand",
                "No. Strands": 1,
                "Row center x_mm": 0.0,
                "y_mm_from_bottom": 20.0,
                "Left debond m": 0.0,
                "Right debond m": 0.0,
            }
        ]
    )
    table = _normalize_girder_strand_layout_table(low_cover_row, span_length_m=20.0, geometry=geometry)
    errors, warnings = _validate_girder_strand_layout(table, span_length_m=20.0, geometry=geometry)
    assert errors == []
    assert any("minimum strand centerline clearance" in warning for warning in warnings)


def test_girder_strand_editor_first_edit_callback_persists_table(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as page  # noqa: PLC0415

    monkeypatch.setattr(page, "st", st)
    edited = page._normalize_girder_strand_layout_table(None, span_length_m=30.0)
    edited.loc[0, "Left debond m"] = 1.25
    edited.loc[0, "Right debond m"] = 0.75
    st.session_state["girder_strand_layout_editor"] = edited

    page._sync_girder_strand_layout_editor_to_table(30.0, "Left/right independent", None)

    stored = st.session_state["girder_strand_layout_table"]
    assert float(stored.loc[0, "Left debond m"]) == 1.25
    assert float(stored.loc[0, "Right debond m"]) == 0.75



def test_girder_strand_editor_store_does_not_force_rerun_during_numeric_edit(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {}

    def _raise_rerun() -> None:
        raise AssertionError("strand editor store must not force rerun while numeric cells are edited")

    st.rerun = _raise_rerun
    st.experimental_rerun = _raise_rerun
    st.column_config = types.SimpleNamespace(
        CheckboxColumn=lambda *args, **kwargs: None,
        TextColumn=lambda *args, **kwargs: None,
        NumberColumn=lambda *args, **kwargs: None,
        SelectboxColumn=lambda *args, **kwargs: None,
    )
    monkeypatch.setitem(sys.modules, "streamlit", st)

    import concrete_pmm_pro.ui.prestress_page as page  # noqa: PLC0415

    monkeypatch.setattr(page, "st", st)
    previous = page._normalize_girder_strand_layout_table(None, span_length_m=30.0)
    edited = previous.copy()
    edited.loc[0, "Left debond m"] = 1.5
    edited.loc[0, "Right debond m"] = 1.0

    page._store_girder_strand_layout_and_rerun_on_change(previous, edited)

    stored = st.session_state["girder_strand_layout_table"]
    assert float(stored.loc[0, "Left debond m"]) == 1.5
    assert float(stored.loc[0, "Right debond m"]) == 1.0
