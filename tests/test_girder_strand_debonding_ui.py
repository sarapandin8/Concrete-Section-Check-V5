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
        _normalize_girder_strand_layout_table,
    )

    raw = pd.DataFrame(
        [
            {
                "Active": True,
                "Group ID": "Row 1",
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
