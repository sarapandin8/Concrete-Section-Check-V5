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
    assert "Individual strands" in PRESTRESS_SOURCE
    assert "Computed spacing_mm" in PRESTRESS_SOURCE
    assert "3db minimum spacing" in PRESTRESS_SOURCE
    assert "reduce the number of strands in this row" in PRESTRESS_SOURCE
    assert "Transfer/development length transition is not modeled" in PRESTRESS_SOURCE
    assert "does not change current Analysis results" in PRESTRESS_SOURCE


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
    assert table.loc[0, "Total Aps_mm2"] == 12 * 98.7
    assert table.loc[0, "Edge CL_mm"] == 45.0
    assert table.loc[0, "Min spacing_mm"] == 50.0


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
