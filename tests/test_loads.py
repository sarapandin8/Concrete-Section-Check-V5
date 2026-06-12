from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import kN_to_N, kNm_to_Nmm, tonf_to_N, tonfm_to_Nmm
from concrete_pmm_pro.ui.loads_page import (
    BEAM_SLS_LOAD_COLUMNS,
    BEAM_SLS_STAGE_EDITOR_COLUMNS,
    BEAM_ULS_LOAD_COLUMNS,
    COLUMN_SLS_LOAD_COLUMNS,
    COLUMN_ULS_LOAD_COLUMNS,
    _active_girder_service_basis_default,
    _axis_convention_rows,
    _beam_sls_stage_basis_warnings,
    _beam_sls_stage_input_specs,
    _beam_sls_stage_editor_rows,
    _beam_sls_table_after_stage_edit,
    _beam_uls_template_table,
    _column_workflow_tables_to_legacy_editor_table,
    _default_beam_sls_load_table,
    _default_beam_uls_load_table,
    BEAM_ULS_INPUT_MODE_ENVELOPE,
    BEAM_ULS_INPUT_MODE_FULL,
    BEAM_ULS_INPUT_MODE_MINIMUM,
    BEAM_ULS_INPUT_MODE_REVIEW,
    _excel_template_bytes,
    _normalize_editor_dataframe,
    prepare_imported_workflow_load_table,
    _normalize_beam_sls_load_table,
    _preview_dataframe,
    _split_mixed_editor_table_to_column_tables,
    _safe_excel_sheet_name,
    _workflow_table_result,
    _workflow_template_bytes,
    load_cases_from_dataframe,
    prepare_imported_load_table,
)


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


def test_loads_page_includes_member_workflow_notice_source() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")

    assert "Active member workflow" in source
    assert "Beam/Girder SLS rows can be selected in Analysis" in source
    assert "Pu/Mux/Muy PMM table" in source


def test_loads_workflow1a_axis_convention_uses_explicit_section_axes() -> None:
    rows = dict(_axis_convention_rows())

    assert "x-axis" in rows
    assert "y-axis" in rows
    assert "z-axis" in rows
    assert "main vertical bending" in rows["Mux"]
    assert "vertical shear" in rows["Vuy"]
    assert "major" not in " ".join(rows.keys()).lower()


def test_column_workflow_tables_map_back_to_existing_pmm_loadcase_contract() -> None:
    uls = pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-COL", "Pu": "1000", "Mux": "200", "Muy": "50", "Vux": "10", "Vuy": "20", "Tu": "5", "Note": "uls"},
        ],
        columns=COLUMN_ULS_LOAD_COLUMNS,
    )
    sls = pd.DataFrame(
        [
            {"Active": True, "Case Name": "SLS-COL", "P": "700", "Mx": "120", "My": "30", "Note": "sls"},
        ],
        columns=COLUMN_SLS_LOAD_COLUMNS,
    )

    legacy = _column_workflow_tables_to_legacy_editor_table(uls, sls)
    load_cases = load_cases_from_dataframe(legacy, "kN", "kN-m")

    assert list(legacy["Limit State"]) == ["ULS", "SLS"]
    assert load_cases[0].name == "ULS-COL"
    assert load_cases[0].Pu_N == pytest.approx(1_000_000)
    assert load_cases[0].Mux_Nmm == pytest.approx(200_000_000)
    assert load_cases[1].name == "SLS-COL"
    assert load_cases[1].load_type == "SLS"
    assert load_cases[1].Pu_N == pytest.approx(700_000)
    assert load_cases[1].Mux_Nmm == pytest.approx(120_000_000)


def test_split_mixed_load_table_to_column_uls_sls_tables() -> None:
    mixed = pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-1", "Limit State": "ULS", "Pu": "1", "Mux": "2", "Muy": "3", "Note": "strength"},
            {"Active": True, "Case Name": "SLS-1", "Limit State": "SLS", "Pu": "4", "Mux": "5", "Muy": "6", "Note": "service"},
        ]
    )

    uls, sls = _split_mixed_editor_table_to_column_tables(mixed)

    assert list(uls.columns) == COLUMN_ULS_LOAD_COLUMNS
    assert list(sls.columns) == COLUMN_SLS_LOAD_COLUMNS
    assert uls.loc[0, "Case Name"] == "ULS-1"
    assert sls.loc[0, "P"] == "4"
    assert sls.loc[0, "Mx"] == "5"
    assert sls.loc[0, "My"] == "6"


def test_beam_girder_workflow_default_tables_use_three_stage_sls_model() -> None:
    uls = _default_beam_uls_load_table()
    sls = _default_beam_sls_load_table()

    assert list(uls.columns) == BEAM_ULS_LOAD_COLUMNS
    assert ["Mux", "Vuy", "Tu"] == list(uls.columns[3:6])
    assert "Station x (m)" in uls.columns
    assert uls.loc[0, "Active"] == False
    assert uls.loc[0, "Case Name"] == "Strength I"
    assert float(uls.loc[0, "Mux"]) == pytest.approx(0.0)
    assert list(sls.columns) == BEAM_SLS_LOAD_COLUMNS
    assert "Station x (m)" in sls.columns
    assert "Stage" in sls.columns
    assert "Load Component" in sls.columns  # internal/project metadata, hidden from default editor
    assert "Stage / Component" not in sls.columns
    assert list(sls["Stage"]) == ["Transfer stage", "Construction stage", "Service stage"]
    assert list(sls["Load Component"]) == ["Girder self-weight", "Girder self-weight + wet deck/topping", "Total SLS resultant"]
    assert list(sls["Section Basis"]) == ["Precast gross", "Precast gross", "Composite transformed"]
    assert "SDL and LL+IM" in sls.loc[2, "Note"]


def test_loads_template1_building_minimum_template_uses_aci19_uls2() -> None:
    template = _beam_uls_template_table("building", BEAM_ULS_INPUT_MODE_MINIMUM, span_length_m=20.0)

    assert set(template["Case Name"]) == {"ACI19-ULS-2"}
    assert set(template["Active"]) == {False}
    assert "1.2D + 1.6L" in str(template.iloc[0]["Note"])


def test_loads_template1_bridge_full_template_includes_strength_cases() -> None:
    template = _beam_uls_template_table("bridge", BEAM_ULS_INPUT_MODE_FULL, span_length_m=20.0, compact=True)

    assert "Strength I" in set(template["Case Name"])
    assert "Strength V" in set(template["Case Name"])
    assert set(template["Active"]) == {False}


def test_loads_template1_envelope_and_review_modes_are_safe_inactive() -> None:
    envelope = _beam_uls_template_table("bridge", BEAM_ULS_INPUT_MODE_ENVELOPE, span_length_m=20.0, compact=True)
    review = _beam_uls_template_table("building", BEAM_ULS_INPUT_MODE_REVIEW, span_length_m=20.0, compact=True)

    assert "ULS Envelope Mu+" in set(envelope["Case Name"])
    assert set(envelope["Active"]) == {False}
    assert set(review["Case Name"]) == {"ACI19-ULS-2"}
    assert set(review["Active"]) == {False}


def test_beam_girder_service_stage_basis_follows_selected_section_family() -> None:
    from concrete_pmm_pro.ui import loads_page

    original_state = dict(loads_page.st.session_state)
    try:
        loads_page.st.session_state.clear()
        loads_page.st.session_state["girder_section_family"] = "general_non_composite_girder"
        loads_page.st.session_state["girder_service_default_basis"] = "Precast gross"

        specs = _beam_sls_stage_input_specs()
        service_spec = next(spec for spec in specs if spec["stage"] == "Service stage")
        sls = _default_beam_sls_load_table()

        assert _active_girder_service_basis_default() == "Precast gross"
        assert service_spec["basis"] == "Precast gross"
        assert sls[sls["Stage"] == "Service stage"].iloc[0]["Section Basis"] == "Precast gross"
        assert "General / Non-composite Girder" in service_spec["note"]
    finally:
        loads_page.st.session_state.clear()
        loads_page.st.session_state.update(original_state)


def test_loads_workflow1b_migrates_old_stage_component_column() -> None:
    old = pd.DataFrame(
        [
            {
                "Active": True,
                "Case Name": "SLS-OLD",
                "Stage / Component": "Final service",
                "Section Basis": "Composite transformed",
                "N": "0",
                "Mx": "500",
                "My": "0",
                "Vy": "0",
                "Vx": "0",
                "T": "0",
                "Note": "legacy workflow1a row",
            }
        ]
    )

    migrated = _normalize_beam_sls_load_table(old)

    assert list(migrated.columns) == BEAM_SLS_LOAD_COLUMNS
    assert migrated.loc[0, "Stage"] == "Service stage"
    assert migrated.loc[0, "Load Component"] == "Total SLS resultant"
    assert "Stage / Component" not in migrated.columns


def test_loads_sls2c_stage_editor_hides_stage_and_component_but_preserves_backend_schema() -> None:
    table = _default_beam_sls_load_table()

    service_editor = _beam_sls_stage_editor_rows(table, "Service stage")

    assert list(service_editor.columns) == BEAM_SLS_STAGE_EDITOR_COLUMNS
    assert "Stage" not in service_editor.columns
    assert "Load Component" not in service_editor.columns
    assert service_editor.loc[0, "Case Name"] == "SLS-SERV"

    edited_service = service_editor.copy()
    edited_service.loc[0, "Mx"] = "1234.5"
    merged = _beam_sls_table_after_stage_edit(table, "Service stage", edited_service)

    assert list(merged.columns) == BEAM_SLS_LOAD_COLUMNS
    service_row = merged[merged["Stage"] == "Service stage"].iloc[0]
    assert service_row["Load Component"] == "Total SLS resultant"
    assert service_row["Section Basis"] == "Composite transformed"
    assert service_row["Mx"] == "1234.5"
    assert set(merged["Stage"]) == {"Transfer stage", "Construction stage", "Service stage"}


def test_loads_import1_beam_sls_station_rows_preserve_stage_metadata() -> None:
    imported = pd.DataFrame(
        [
            {"Active": True, "Station": 0.0, "Case Name": "SLS-SERV", "Mx": "0", "N": "0"},
            {"Active": True, "Station": 10.0, "Case Name": "SLS-SERV", "Mx": "500", "N": "0"},
        ]
    )

    prepared = prepare_imported_workflow_load_table(
        imported,
        BEAM_SLS_STAGE_EDITOR_COLUMNS,
        default_values={"Section Basis": "Composite transformed"},
    )
    merged = _beam_sls_table_after_stage_edit(_default_beam_sls_load_table(), "Service stage", prepared)

    service_rows = merged[merged["Stage"] == "Service stage"].reset_index(drop=True)
    assert list(service_rows["Station x (m)"]) == ["0.0", "10.0"]
    assert set(service_rows["Load Component"]) == {"Total SLS resultant"}
    assert set(service_rows["Section Basis"]) == {"Composite transformed"}


def test_loads_import1_beam_station_validation_allows_same_case_at_different_stations() -> None:
    table = pd.DataFrame(
        [
            {"Active": True, "Station x (m)": "0", "Case Name": "ULS-G1", "Mux": "0", "Vuy": "10", "Tu": "0", "Muy": "0", "Vux": "0", "Nu": "0", "Note": ""},
            {"Active": True, "Station x (m)": "5", "Case Name": "ULS-G1", "Mux": "100", "Vuy": "0", "Tu": "0", "Muy": "0", "Vux": "0", "Nu": "0", "Note": ""},
        ],
        columns=BEAM_ULS_LOAD_COLUMNS,
    )

    result = _workflow_table_result(
        table,
        table_name="Beam/Girder ULS",
        numeric_columns=["Station x (m)", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu"],
        unique_key_columns=["Case Name", "Station x (m)"],
    )

    assert result.errors == []
    assert len(result.load_cases) == 2




def test_loads_import1_workflow_template_sanitizes_excel_sheet_names() -> None:
    template = pd.DataFrame([{"Active": True, "Station x (m)": 0.0, "Case Name": "ULS-G1"}])

    workbook_bytes = _workflow_template_bytes(
        template,
        sheet_name="Beam/Girder ULS station-load import",
        instructions=[{"Field": "Case Name", "Instruction": "Required."}],
    )

    assert workbook_bytes.startswith(b"PK")
    assert _safe_excel_sheet_name("Beam/Girder ULS station-load import") == "Beam Girder ULS station-load"
    assert _safe_excel_sheet_name("/:*?[]") == "Load Template"


def test_beam_girder_workflow_table_validation_rejects_non_numeric_actions() -> None:
    table = pd.DataFrame(
        [{"Active": True, "Case Name": "BG-1", "Mux": "bad", "Vuy": "10", "Tu": "0", "Muy": "0", "Vux": "0", "Nu": "0", "Note": ""}],
        columns=BEAM_ULS_LOAD_COLUMNS,
    )

    result = _workflow_table_result(table, table_name="Beam/Girder ULS", numeric_columns=["Mux", "Vuy", "Tu", "Muy", "Vux", "Nu"])

    assert result.errors
    assert "Mux must be numeric" in result.errors[0]


def test_loads_page_source_contains_workflow_based_uls_sls_tables_and_double_count_warning() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")

    assert "ULS PMM / Shear Loads" in source
    assert "SLS Stress Loads" in source
    assert "ULS Bridge Beam/Girder Design Loads" in source
    assert "ULS Building Beam/Girder Design Loads" in source
    assert "SLS Girder Service Loads" in source
    assert "LOADS.COMPACT1" in source
    assert "LOADS.TEMPLATE1" in source
    assert "Minimum design input — primary gravity combo" in source
    assert "Strength I" in source
    assert "ACI19-ULS-2" in source
    assert "factored station resultants" in source
    assert 'st.tabs(["ULS Loads", "SLS Loads"])' in source
    assert 'st.expander("Axis convention for load input", expanded=False)' in source
    assert 'st.expander("Load input status", expanded=validation_has_issues)' in source
    assert "Do not include prestress in the Loads resultant" in source
    assert "Load Component" in source
    assert "enter service actions by stage" in source
    assert "Mux is main vertical bending" in source
    assert "Vuy is vertical shear" in source


def test_beam_sls_stage_tab_edits_are_persisted_with_single_rerun_guard() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")

    assert "LOADS.SLS2C" in source
    assert "_store_editor_table_and_rerun_on_change" in source
    assert "st.rerun()" in source
    assert "stage_tabs = st.tabs" in source
    assert "beam_sls_{stage_key}_loads_editor" in source
    assert 'SelectboxColumn("Check Stage"' not in source
    assert 'SelectboxColumn("Load Component"' not in source
    assert 'SelectboxColumn(' in source and '"Section Basis"' in source
    assert "Combined SLS backend table used by Analysis" in source


def test_column_pier_load_table_edits_are_persisted_with_single_rerun_guard() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")

    assert '"column_uls_loads_table",' in source
    assert '"column_sls_loads_table",' in source
    assert "COLUMN_ULS_LOAD_COLUMNS" in source
    assert "COLUMN_SLS_LOAD_COLUMNS" in source
    assert source.count("_store_editor_table_and_rerun_on_change(") >= 3


def test_beam_sls_stage_basis_warnings_accept_service_total_but_flag_mismatched_basis() -> None:
    table = pd.DataFrame(
        [
            {
                "Active": True,
                "Case Name": "SLS-TOTAL",
                "Stage": "Final service",
                "Load Component": "Total SLS resultant",
                "Section Basis": "Composite transformed",
                "N": "0",
                "Mx": "500",
                "My": "0",
                "Vy": "0",
                "Vx": "0",
                "T": "0",
                "Note": "quick preview only",
            },
            {
                "Active": True,
                "Case Name": "TRANSFER-BAD",
                "Stage": "Transfer / release",
                "Load Component": "Prestress / release",
                "Section Basis": "Composite transformed",
                "N": "0",
                "Mx": "100",
                "My": "0",
                "Vy": "0",
                "Vx": "0",
                "T": "0",
                "Note": "wrong basis",
            },
            {
                "Active": True,
                "Case Name": "LL-BAD",
                "Stage": "Post-composite service action",
                "Load Component": "LL+IM",
                "Section Basis": "Precast gross",
                "N": "0",
                "Mx": "200",
                "My": "0",
                "Vy": "0",
                "Vx": "0",
                "T": "0",
                "Note": "wrong basis",
            },
        ],
        columns=BEAM_SLS_LOAD_COLUMNS,
    )

    warnings = _beam_sls_stage_basis_warnings(table)

    joined = "\n".join(warnings)
    assert "Total SLS resultant is suitable for quick preview only" not in joined
    assert "Precast gross section basis" in joined
    assert "Composite transformed section basis" in joined


def test_loads_workflow1c_source_reflects_sls_preview_connection_and_basis_guidance() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "loads_page.py").read_text(encoding="utf-8")

    assert "SLS rows can be selected in Analysis for quick preview checks" in source
    assert "SLS stage / section-basis guidance" in source
    assert "detailed load-component dropdown" in source
    assert "Combined SLS backend table used by Analysis" in source
    assert "station-based" in source
    assert "Import Bridge Beam/Girder ULS station loads" in source or "Import Bridge Beam/Girder ULS station" in source
    assert "full staged summation" in source
