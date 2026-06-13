from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import Rebar
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.ui.rebar_page import (
    COLUMN_PIER_TRANSVERSE_TABLE_KEY,
    DEFAULT_SHEAR_STIRRUP_FY_MPA,
    COLUMN_PIER_SEISMIC_DETAILING_OPTIONS,
    bar_size_defaults,
    default_material_for_bar_size,
    load_rebar_database,
    normalize_rebar_table_for_bar_size_sync,
    rebar_editor_tables_equal,
    rebars_from_dataframe,
    rebar_summary_dataframe,
    rebars_valid_for_analysis,
    validate_rebars_against_geometry,
    _aci_special_seismic_spacing_advisor,
    _column_pier_transverse_readiness_cards,
    _collapse_legacy_column_pier_transverse_template,
    _default_column_pier_transverse_reinforcement_table,
    _default_shear_reinforcement_table,
    _normalize_shear_reinforcement_table,
    _shear_reinforcement_preview_dataframe,
    SHEAR_STIRRUP_BAR_OPTIONS,
)


def test_rebar_database_loads() -> None:
    rebar_db = load_rebar_database()

    assert {"name", "type", "diameter_mm", "area_mm2", "fy_MPa", "Es_MPa"}.issubset(rebar_db.columns)
    assert "DB25" in set(rebar_db["name"])
    fy_by_size = {str(row["name"]): float(row["fy_MPa"]) for _, row in rebar_db.iterrows()}
    assert fy_by_size["DB20"] == pytest.approx(390.0)
    assert fy_by_size["DB32"] == pytest.approx(490.0)


def test_rebar_area_property_for_db25() -> None:
    rebar = Rebar(x_mm=0, y_mm=0, diameter_mm=25)

    assert rebar.area_mm2 == pytest.approx(490.9, rel=1e-3)


def test_rebars_from_dataframe_creates_rebar_objects() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 10, "y_mm": 20, "Bar Size": "DB25", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert len(result.rebars) == 1
    assert result.rebars[0].label == "B1"
    assert result.rebars[0].diameter_mm == 25


def test_selected_database_bar_size_preserves_manual_diameter_override() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": 99, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 99


def test_default_material_for_thai_rebar_sizes() -> None:
    assert default_material_for_bar_size("DB10") == "SD40"
    assert default_material_for_bar_size("DB28") == "SD40"
    assert default_material_for_bar_size("DB32") == "SD50"


def test_bar_size_defaults_resolve_database_diameter_and_material() -> None:
    rebar_db = load_rebar_database()

    assert bar_size_defaults("DB10", rebar_db) == (10.0, "SD40")
    assert bar_size_defaults("DB28", rebar_db) == (28.0, "SD40")
    assert bar_size_defaults("DB32", rebar_db) == (32.0, "SD50")


def test_bar_size_change_auto_syncs_diameter_and_material() -> None:
    rebar_db = load_rebar_database()
    previous = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB20", "Diameter_mm": 20, "Material": "SD40", "Count": 1, "Note": ""}]
    )
    edited = previous.copy()
    edited.loc[0, "Bar Size"] = "DB32"

    normalized = normalize_rebar_table_for_bar_size_sync(edited, previous, rebar_db)

    assert normalized.loc[0, "Diameter_mm"] == 32
    assert normalized.loc[0, "Material"] == "SD50"




def test_editor_table_equivalence_ignores_streamlit_numeric_dtype_roundtrip() -> None:
    left = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB32", "Diameter_mm": 32.0, "Material": "SD50", "Count": 1.0, "Note": ""}]
    )
    right = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0.0, "y_mm": 0.0, "Bar Size": "DB32", "Diameter_mm": 32, "Material": "SD50", "Count": 1, "Note": ""}]
    )

    assert rebar_editor_tables_equal(left, right) is True


def test_editor_table_equivalence_detects_auto_sync_difference() -> None:
    edited = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB32", "Diameter_mm": 20, "Material": "SD40", "Count": 1, "Note": ""}]
    )
    synced = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB32", "Diameter_mm": 32, "Material": "SD50", "Count": 1, "Note": ""}]
    )

    assert rebar_editor_tables_equal(synced, edited) is False

def test_bar_size_sync_fills_blank_dependent_cells_when_size_unchanged() -> None:
    rebar_db = load_rebar_database()
    previous = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": None, "Material": "", "Count": 1, "Note": ""}]
    )
    edited = previous.copy()

    normalized = normalize_rebar_table_for_bar_size_sync(edited, previous, rebar_db)

    assert normalized.loc[0, "Diameter_mm"] == 25
    assert normalized.loc[0, "Material"] == "SD40"


def test_manual_overrides_are_preserved_when_bar_size_is_unchanged() -> None:
    rebar_db = load_rebar_database()
    previous = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": 25, "Material": "SD40", "Count": 1, "Note": ""}]
    )
    edited = previous.copy()
    edited.loc[0, "Diameter_mm"] = 23
    edited.loc[0, "Material"] = "ProjectSteel"

    normalized = normalize_rebar_table_for_bar_size_sync(edited, previous, rebar_db)

    assert normalized.loc[0, "Diameter_mm"] == 23
    assert normalized.loc[0, "Material"] == "ProjectSteel"


def test_blank_or_custom_bar_size_preserves_manual_input() -> None:
    rebar_db = load_rebar_database()
    previous = pd.DataFrame(
        [
            {"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "", "Diameter_mm": 21, "Material": "Manual", "Count": 1, "Note": ""},
            {"Active": True, "Label": "B2", "x_mm": 0, "y_mm": 0, "Bar Size": "Custom", "Diameter_mm": 22, "Material": "CustomMat", "Count": 1, "Note": ""},
        ]
    )

    normalized = normalize_rebar_table_for_bar_size_sync(previous, previous, rebar_db)

    assert normalized.loc[0, "Diameter_mm"] == 21
    assert normalized.loc[0, "Material"] == "Manual"
    assert normalized.loc[1, "Diameter_mm"] == 22
    assert normalized.loc[1, "Material"] == "CustomMat"


def test_rebar_summary_uses_normalized_diameter_and_material() -> None:
    rebar_db = load_rebar_database()
    previous = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB20", "Diameter_mm": 20, "Material": "SD40", "Count": 1, "Note": ""}]
    )
    edited = previous.copy()
    edited.loc[0, "Bar Size"] = "DB25"
    normalized = normalize_rebar_table_for_bar_size_sync(edited, previous, rebar_db)

    result = rebars_from_dataframe(normalized, rebar_db)
    summary = rebar_summary_dataframe(result.rebars)

    assert summary.loc[0, "diameter_mm"] == 25
    assert summary.loc[0, "material_name"] == "SD40"
    assert summary.loc[0, "area_mm2"] == pytest.approx(490.9, rel=1e-3)


def test_custom_bar_size_with_diameter_creates_rebar() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "C1", "x_mm": 0, "y_mm": 0, "Bar Size": "Custom", "Diameter_mm": 23, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 23
    assert any("Custom" in warning for warning in result.warnings)


def test_custom_bar_size_without_diameter_gives_error() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "C1", "x_mm": 0, "y_mm": 0, "Bar Size": "Custom", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("Custom" in error and "Diameter_mm" in error for error in result.errors)


def test_unknown_bar_size_with_diameter_creates_custom_rebar_with_warning() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "U1", "x_mm": 0, "y_mm": 0, "Bar Size": "UNKNOWN", "Diameter_mm": 21, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars[0].diameter_mm == 21
    assert any("not in the database" in warning for warning in result.warnings)


def test_unknown_bar_size_without_diameter_gives_error() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "U1", "x_mm": 0, "y_mm": 0, "Bar Size": "UNKNOWN", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("not in the database" in error for error in result.errors)


def test_inactive_rows_are_ignored() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": False, "Label": "B1", "x_mm": "bad", "y_mm": "bad", "Bar Size": "DB25", "Diameter_mm": -1, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert not result.errors
    assert result.rebars == []


def test_invalid_diameter_is_rejected() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "", "Diameter_mm": -20, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("Diameter_mm" in error for error in result.errors)
    assert result.rebars == []


def test_nonnumeric_coordinates_give_errors() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B1", "x_mm": "x", "y_mm": "y", "Bar Size": "DB20", "Diameter_mm": None, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert any("x_mm" in error for error in result.errors)
    assert any("y_mm" in error for error in result.errors)


def test_total_as_calculation_with_count() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": True, "Label": "B", "x_mm": 0, "y_mm": 0, "Bar Size": "DB25", "Diameter_mm": None, "Material": "SD40", "Count": 3, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)
    total_as = sum(rebar.area_mm2 for rebar in result.rebars)

    assert len(result.rebars) == 3
    assert total_as == pytest.approx(3 * 490.9, rel=1e-3)
    assert [rebar.label for rebar in result.rebars] == ["B-1", "B-2", "B-3"]


def test_rebar_outside_section_is_detected() -> None:
    geometry = rectangle(width_mm=400, height_mm=400)
    rebars = [Rebar(x_mm=300, y_mm=0, diameter_mm=20, label="OUT")]

    errors = validate_rebars_against_geometry(rebars, geometry)

    assert any("outside concrete" in error for error in errors)
    assert rebars_valid_for_analysis(RebarParseResultForTest(rebars), errors) is False


def test_rebar_inside_hole_is_detected() -> None:
    geometry = rectangular_hollow(width_mm=1000, height_mm=800, t_top_mm=100, t_bottom_mm=100, t_left_mm=100, t_right_mm=100)
    rebars = [Rebar(x_mm=0, y_mm=0, diameter_mm=20, label="VOID")]

    errors = validate_rebars_against_geometry(rebars, geometry)

    assert any("inside a void" in error for error in errors)
    assert rebars_valid_for_analysis(RebarParseResultForTest(rebars), errors) is False


def RebarParseResultForTest(rebars: list[Rebar]):
    from concrete_pmm_pro.ui.rebar_page import RebarParseResult

    return RebarParseResult(rebars=rebars, errors=[], warnings=[], info=[])


def test_rebars_from_dataframe_empty_active_rows_does_not_emit_presence_warning() -> None:
    rebar_db = load_rebar_database()
    df = pd.DataFrame(
        [{"Active": False, "Label": "B1", "x_mm": 0, "y_mm": 0, "Bar Size": "DB20", "Diameter_mm": 20, "Material": "SD40", "Count": 1, "Note": ""}]
    )

    result = rebars_from_dataframe(df, rebar_db)

    assert result.rebars == []
    assert not any("No active" in warning for warning in result.warnings)



def test_shear_reinforcement_default_template_uses_db12_and_allowed_dropdown_sizes() -> None:
    table = _default_shear_reinforcement_table(20.0)

    assert not table.empty
    assert set(table["Bar Size"]) == {"DB12"}
    assert set(table["fy_MPa"]) == {DEFAULT_SHEAR_STIRRUP_FY_MPA}
    assert DEFAULT_SHEAR_STIRRUP_FY_MPA == pytest.approx(390.0)
    assert table["Active"].eq(False).all()
    assert SHEAR_STIRRUP_BAR_OPTIONS == ["DB10", "DB12", "DB16", "DB20", "DB25"]


def test_column_pier_transverse_default_template_is_separate_from_beam_girder_key() -> None:
    table = _default_column_pier_transverse_reinforcement_table()

    assert COLUMN_PIER_TRANSVERSE_TABLE_KEY == "column_pier_transverse_reinforcement_table"
    assert len(table) == 1
    assert table.iloc[0]["Zone"] == "Control section"
    assert table["Active"].eq(False).all()
    assert set(table["Bar Size"]) == {"DB12"}
    assert "control section" in str(table.iloc[0]["Note"]).lower()


def test_column_pier_legacy_three_region_template_collapses_to_control_section() -> None:
    legacy = pd.DataFrame(
        [
            {"Active": True, "Zone": "End confinement A", "x_start_m": 0.0, "x_end_m": 1.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 100.0, "fy_MPa": 390.0, "Note": "legacy"},
            {"Active": True, "Zone": "Typical shaft/core", "x_start_m": 1.0, "x_end_m": 5.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 150.0, "fy_MPa": 390.0, "Note": "legacy"},
            {"Active": True, "Zone": "End confinement B", "x_start_m": 5.0, "x_end_m": 6.0, "Bar Size": "DB12", "Diameter_mm": 12.0, "Legs": 2, "Spacing_mm": 100.0, "fy_MPa": 390.0, "Note": "legacy"},
        ]
    )

    collapsed = _collapse_legacy_column_pier_transverse_template(legacy)

    assert len(collapsed) == 1
    assert collapsed.iloc[0]["Zone"] == "Control section"
    assert bool(collapsed.iloc[0]["Active"]) is True
    assert collapsed.iloc[0]["Spacing_mm"] == pytest.approx(150.0)
    assert "legacy three-region template" in str(collapsed.iloc[0]["Note"])


def test_column_pier_control_section_allows_zero_length_reference() -> None:
    rebar_db = load_rebar_database()
    table = _default_column_pier_transverse_reinforcement_table()
    table.loc[0, "Active"] = True

    preview, errors, warnings = _shear_reinforcement_preview_dataframe(
        table,
        rebar_db,
        allow_zero_length_reference=True,
    )

    assert errors == []
    assert warnings == []
    assert len(preview) == 1
    assert preview.iloc[0]["x start (m)"] == pytest.approx(0.0)
    assert preview.iloc[0]["x end (m)"] == pytest.approx(0.0)
    avs_column = next(column for column in preview.columns if str(column).startswith("Av/s") and "/mm)" in str(column))
    assert preview.iloc[0][avs_column] != "-"


def test_aci_special_seismic_spacing_advisor_recommends_governing_control_spacing() -> None:
    result = _aci_special_seismic_spacing_advisor(
        section_min_dimension_mm=400.0,
        min_longitudinal_bar_diameter_mm=20.0,
        hx_mm=300.0,
    )

    assert result.status == "Advisor ready"
    assert result.s_max_mm == pytest.approx(100.0)
    assert result.suggested_spacing_mm == pytest.approx(100.0)
    assert result.governing_limit == "0.25 x minimum outside section dimension"
    assert len(result.criteria) == 3


def test_aci_special_seismic_spacing_advisor_remains_review_when_inputs_are_missing() -> None:
    result = _aci_special_seismic_spacing_advisor(
        section_min_dimension_mm=None,
        min_longitudinal_bar_diameter_mm=None,
        hx_mm=None,
    )

    assert result.status == "REVIEW"
    assert result.s_max_mm is None
    assert result.suggested_spacing_mm is None
    assert result.warnings


def test_column_pier_seismic_options_keep_aashto_as_manual_review_route() -> None:
    assert "ACI 318 special seismic confinement advisor" in COLUMN_PIER_SEISMIC_DETAILING_OPTIONS
    assert "AASHTO LRFD seismic bridge column - manual review" in COLUMN_PIER_SEISMIC_DETAILING_OPTIONS


def test_column_pier_preview_keeps_seismic_advisor_row_display_only() -> None:
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text(encoding="utf-8")

    assert "Recommended seismic spacing (ACI advisor)" in source
    assert "Advisor only / REVIEW" in source
    assert "Shear and torsion calculations use the Control section row only" in source


def test_column_pier_transverse_readiness_excludes_prestress_from_longitudinal_al() -> None:
    table = _default_column_pier_transverse_reinforcement_table()
    table["Active"] = True
    settings = {
        "closed_tie_layout": "Closed ties / hoops",
        "torsion_core_basis": "Auto from section and tie offset",
    }

    cards = _column_pier_transverse_readiness_cards(table, settings, rebar_count=4, preview_errors=[])
    by_title = {card.title: card for card in cards}

    assert by_title["Longitudinal torsion bars"].value == "Available"
    assert "prestress is not counted as Al" in by_title["Longitudinal torsion bars"].detail
    assert by_title["Torsion input"].value == "Ready"
    assert "Analysis issues scoped ACI RC shear/torsion/V+T status" in by_title["Capability"].detail


def test_shear_reinforcement_preview_calculates_avs_for_active_zone() -> None:
    rebar_db = load_rebar_database()
    table = _default_shear_reinforcement_table(20.0).head(1).copy()
    table.loc[0, "Active"] = True
    table.loc[0, "Bar Size"] = "DB12"
    table.loc[0, "Legs"] = 2
    table.loc[0, "Spacing_mm"] = 100.0

    normalized = _normalize_shear_reinforcement_table(table, table, rebar_db)
    preview, errors, warnings = _shear_reinforcement_preview_dataframe(normalized, rebar_db)

    assert not errors
    assert not warnings
    assert preview.iloc[0]["Av/s (mm²/mm)"] == pytest.approx(2 * 113.1 / 100.0, rel=1e-3)
    assert preview.iloc[0]["Av/s (mm²/m)"] == pytest.approx(2 * 113.1 / 100.0 * 1000.0, rel=1e-3)
