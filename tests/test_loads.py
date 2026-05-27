from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import kN_to_N, kNm_to_Nmm, tonf_to_N, tonfm_to_Nmm
from concrete_pmm_pro.ui.loads_page import _excel_template_bytes, _normalize_editor_dataframe, _preview_dataframe, load_cases_from_dataframe, prepare_imported_load_table


def test_force_unit_conversions() -> None:
    assert kN_to_N(1) == 1000
    assert tonf_to_N(1) == pytest.approx(9806.65)


def test_moment_unit_conversions() -> None:
    assert kNm_to_Nmm(1) == 1_000_000
    assert tonfm_to_Nmm(1) == pytest.approx(9_806_650)


def test_load_case_stores_internal_actions() -> None:
    load_case = LoadCase(name="ULS-01", Pu_N=1000, Mux_Nmm=2_000_000, Muy_Nmm=3_000_000)

    assert load_case.Pu_N == 1000
    assert load_case.Mux_Nmm == 2_000_000
    assert load_case.Muy_Nmm == 3_000_000
    assert load_case.Mx_Nmm == 2_000_000
    assert load_case.My_Nmm == 3_000_000


def test_load_case_accepts_old_titlecase_moment_names() -> None:
    load_case = LoadCase(name="OLD", Pu_N=1000, Mx_Nmm=2000, My_Nmm=3000)

    assert load_case.Mux_Nmm == 2000
    assert load_case.Muy_Nmm == 3000


def test_load_case_accepts_legacy_action_names() -> None:
    load_case = LoadCase(name="LEGACY", axial_n=1000, mx_nmm=2000, my_nmm=3000)

    assert load_case.Pu_N == 1000
    assert load_case.Mux_Nmm == 2000
    assert load_case.Muy_Nmm == 3000
    assert load_case.axial_n == 1000


def test_blank_load_case_name_is_rejected() -> None:
    with pytest.raises(ValueError, match="name"):
        LoadCase(name=" ", Pu_N=1000, Mux_Nmm=0, Muy_Nmm=0)


def test_load_cases_from_dataframe_converts_pu_mux_muy_kn_and_knm() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Combo Name": "ULS-01", "Pu": 1000, "Mux": 500, "Muy": 300, "Load Type": "ULS", "Note": "ok"},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "kN", "kN-m")

    assert len(load_cases) == 1
    assert load_cases[0].Pu_N == pytest.approx(1_000_000)
    assert load_cases[0].Mux_Nmm == pytest.approx(500_000_000)
    assert load_cases[0].Muy_Nmm == pytest.approx(300_000_000)


def test_load_cases_from_dataframe_accepts_legacy_mx_my_columns() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Combo Name": "ULS-OLD", "Pu": 10, "Mx": 2, "My": 3, "Load Type": "ULS", "Note": "legacy"},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "kN", "kN-m")

    assert len(load_cases) == 1
    assert load_cases[0].Mux_Nmm == pytest.approx(2_000_000)
    assert load_cases[0].Muy_Nmm == pytest.approx(3_000_000)


def test_load_cases_from_dataframe_converts_tonf_and_tonfm() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Combo Name": "EXT-01", "Pu": 1, "Mux": 2, "Muy": 3, "Load Type": "Extreme", "Note": ""},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "tonf", "tonf-m")

    assert load_cases[0].Pu_N == pytest.approx(9806.65)
    assert load_cases[0].Mux_Nmm == pytest.approx(19_613_300)
    assert load_cases[0].Muy_Nmm == pytest.approx(29_419_950)


def test_load_cases_from_dataframe_preserves_active_flag_and_load_type() -> None:
    df = pd.DataFrame(
        [
            {"Active": False, "Combo Name": "SLS-01", "Pu": 5, "Mux": 1, "Muy": 1, "Load Type": "SLS", "Note": "service"},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "kN", "kN-m")

    assert load_cases[0].active is False
    assert load_cases[0].load_type == "SLS"
    assert load_cases[0].note == "service"


def test_internal_units_preview_uses_mux_muy_column_names() -> None:
    preview = _preview_dataframe([LoadCase(name="ULS-01", Pu_N=1000, Mux_Nmm=2000, Muy_Nmm=3000)])

    assert "Pu_N" in preview.columns
    assert "Mux_Nmm" in preview.columns
    assert "Muy_Nmm" in preview.columns
    assert "Mx_Nmm" not in preview.columns
    assert "My_Nmm" not in preview.columns


def test_load_cases_from_dataframe_accepts_current_case_and_limit_state_columns() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-NEW", "Limit State": "ULS", "Pu": "1,250", "Mux": "500.5", "Muy": "-300", "Note": "excel paste"},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "kN", "kN-m")

    assert len(load_cases) == 1
    assert load_cases[0].name == "ULS-NEW"
    assert load_cases[0].load_type == "ULS"
    assert load_cases[0].Pu_N == pytest.approx(1_250_000)
    assert load_cases[0].Mux_Nmm == pytest.approx(500_500_000)
    assert load_cases[0].Muy_Nmm == pytest.approx(-300_000_000)


def test_load_cases_from_dataframe_accepts_limit_state_aliases_and_blank_active_defaults_true() -> None:
    df = pd.DataFrame(
        [
            {"Case Name": "SERVICE-01", "Limit State": "service", "Pu": 10, "Mux": 2, "Muy": 3, "Note": ""},
        ]
    )

    load_cases = load_cases_from_dataframe(df, "kN", "kN-m")

    assert load_cases[0].active is True
    assert load_cases[0].load_type == "SLS"


def test_load_cases_from_dataframe_rejects_duplicate_case_names() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-01", "Limit State": "ULS", "Pu": 10, "Mux": 2, "Muy": 3},
            {"Active": True, "Case Name": "uls-01", "Limit State": "ULS", "Pu": 11, "Mux": 2, "Muy": 3},
        ]
    )

    with pytest.raises(ValueError, match="Duplicate Case Name"):
        load_cases_from_dataframe(df, "kN", "kN-m")


def test_internal_units_preview_uses_case_and_limit_state_column_names() -> None:
    preview = _preview_dataframe([LoadCase(name="ULS-01", Pu_N=1000, Mux_Nmm=2000, Muy_Nmm=3000)])

    assert "Case Name" in preview.columns
    assert "Limit State" in preview.columns
    assert "Pu_N" in preview.columns
    assert "Mux_Nmm" in preview.columns
    assert "Muy_Nmm" in preview.columns
    assert "Mx_Nmm" not in preview.columns
    assert "My_Nmm" not in preview.columns


def test_load_editor_normalization_casts_numeric_text_columns_for_streamlit() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-01", "Limit State": "ULS", "Pu": 1250.0, "Mux": 500.0, "Muy": -300.0, "Note": None},
        ]
    )

    normalized = _normalize_editor_dataframe(df)

    assert normalized["Active"].dtype == bool
    assert normalized.loc[0, "Pu"] == "1250.0"
    assert normalized.loc[0, "Mux"] == "500.0"
    assert normalized.loc[0, "Muy"] == "-300.0"
    assert normalized.loc[0, "Note"] == ""


def test_prepare_imported_load_table_accepts_legacy_headers_and_drops_blank_rows() -> None:
    df = pd.DataFrame(
        [
            {"Active": True, "Combo Name": "ULS-01", "Load Type": "Strength", "Pu": "1,250", "Mx": "500", "My": "-300", "Description": "from export"},
            {"Active": None, "Combo Name": "", "Load Type": "", "Pu": "", "Mx": "", "My": "", "Description": ""},
        ]
    )

    imported = prepare_imported_load_table(df)

    assert list(imported.columns) == ["Active", "Case Name", "Limit State", "Pu", "Mux", "Muy", "Note"]
    assert len(imported) == 1
    assert imported.loc[0, "Case Name"] == "ULS-01"
    assert imported.loc[0, "Limit State"] == "ULS"
    assert imported.loc[0, "Pu"] == "1,250"
    assert imported.loc[0, "Mux"] == "500"
    assert imported.loc[0, "Muy"] == "-300"
    assert imported.loc[0, "Note"] == "from export"


def test_excel_template_bytes_can_be_generated() -> None:
    data = _excel_template_bytes()

    assert data.startswith(b"PK")
    assert len(data) > 1000
