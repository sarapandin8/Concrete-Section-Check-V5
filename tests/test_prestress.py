from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.data.prestress_tendon_products import apply_tendon_product_to_row, make_custom_tendon_product
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.ui.prestress_page import (
    AUTO_PERIMETER_PRESTRESS_LAYOUT_METHOD,
    INPUT_MODE_OPTIONS,
    INPUT_MODE_DISPLAY_LABELS,
    JACKING_LOSS_INPUT_MODE,
    MANUAL_PRESTRESS_LAYOUT_METHOD,
    PRESTRESS_COMPACT_EDITOR_COLUMNS,
    PLANNED_PRESTRESS_LAYOUT_METHODS,
    PRESTRESS_LAYOUT_METHOD_OPTIONS,
    PrestressParseResult,
    TENDON_PRODUCT_CREATION_MODES,
    _apply_force_input_method_to_active_rows,
    _build_prestress_status_rows,
    _build_prestress_summary_metrics,
    _default_auto_prestress_product_option,
    _engineering_notes_html,
    generate_auto_perimeter_prestress_layout,
    _is_planned_prestress_layout_method,
    _normalize_prestress_table_for_display,
    _planned_prestress_layout_message,
    _prestress_table_for_editor,
    _product_options_for_table,
    load_prestress_steel_database,
    normalize_prestress_table_for_effective_input_sync,
    prestress_elements_from_dataframe,
    prestress_summary_dataframe,
    prestress_valid_for_analysis,
    validate_prestress_against_geometry,
)
from concrete_pmm_pro.visualization import create_section_preview
from concrete_pmm_pro.visualization.section_plot import display_diameter_for_prestress_element, equivalent_diameter_from_area


def _row(**overrides):
    data = {
        "Active": True,
        "Label": "PS1",
        "Steel Type": "custom",
        "Product": "Custom",
        "x_mm": 0.0,
        "y_mm": 0.0,
        "Area_mm2": 100.0,
        "Diameter_mm": 12.0,
        "fpy_MPa": 1500.0,
        "fpu_MPa": 1860.0,
        "Ep_MPa": 195000.0,
        "Input Mode": "Passive",
        "Pe_eff_kN": 0.0,
        "fpe_MPa": 0.0,
        "fpj_ratio": 0.75,
        "loss_percent": 15.0,
        "Bonded": True,
        "Count": 1,
        "Note": "",
    }
    data.update(overrides)
    return data


def test_prestress_database_loads() -> None:
    prestress_db = load_prestress_steel_database()

    assert {"name", "type", "diameter_mm", "area_mm2", "grade", "fpy_MPa", "fpu_MPa", "Ep_MPa"}.issubset(prestress_db.columns)


def test_prestress_database_contains_strand_and_ps_bar_64() -> None:
    prestress_db = load_prestress_steel_database()
    names = set(prestress_db["name"])

    assert "15.2mm strand" in names
    assert "PS Bar 64 - 1080/1230" in names


def test_passive_mode_gives_zero_initial_state() -> None:
    result = prestress_elements_from_dataframe(pd.DataFrame([_row()]), load_prestress_steel_database())

    element = result.elements[0]
    assert not result.errors
    assert element.pe_eff_n == 0
    assert element.initial_stress_mpa == 0
    assert element.initial_strain == 0


def test_effective_force_pe_converts_kn_to_initial_stress() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": "Effective Force Pe", "Pe_eff_kN": 100.0})]),
        load_prestress_steel_database(),
    )

    element = result.elements[0]
    assert not result.errors
    assert element.pe_eff_n == pytest.approx(100_000.0)
    assert element.initial_stress_mpa == pytest.approx(1000.0)
    assert element.initial_strain == pytest.approx(1000.0 / 195000.0)


def test_effective_force_pe_rejects_stress_above_fpu() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": "Effective Force Pe", "Pe_eff_kN": 200.0, "fpy_MPa": 1200.0, "fpu_MPa": 1500.0})]),
        load_prestress_steel_database(),
    )

    assert result.elements == []
    assert any("Initial prestress stress from Pe_eff exceeds fpu_MPa" in error for error in result.errors)


def test_effective_force_pe_warns_when_stress_is_high_relative_to_fpu() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": "Effective Force Pe", "Pe_eff_kN": 90.0, "fpy_MPa": 800.0, "fpu_MPa": 1000.0})]),
        load_prestress_steel_database(),
    )

    assert not result.errors
    assert result.elements[0].initial_stress_mpa == pytest.approx(900.0)
    assert any("high relative to fpu_MPa" in warning for warning in result.warnings)


def test_old_pe_eff_column_still_converts_as_kn() -> None:
    row = _row(**{"Input Mode": "Effective Force Pe"})
    row.pop("Pe_eff_kN")
    row["Pe_eff"] = 100.0

    result = prestress_elements_from_dataframe(pd.DataFrame([row]), load_prestress_steel_database())

    assert not result.errors
    assert result.elements[0].pe_eff_n == pytest.approx(100_000.0)


def test_blank_bonded_defaults_to_true() -> None:
    result = prestress_elements_from_dataframe(pd.DataFrame([_row(Bonded=None)]), load_prestress_steel_database())

    assert not result.errors
    assert result.elements[0].bonded is True


def test_explicit_bonded_false_stays_false() -> None:
    result = prestress_elements_from_dataframe(pd.DataFrame([_row(Bonded=False)]), load_prestress_steel_database())

    assert not result.errors
    assert result.elements[0].bonded is False


def test_effective_stress_fpe_converts_to_force() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": "Effective Stress fpe", "fpe_MPa": 1000.0})]),
        load_prestress_steel_database(),
    )

    element = result.elements[0]
    assert not result.errors
    assert element.pe_eff_n == pytest.approx(100_000.0)
    assert element.initial_stress_mpa == pytest.approx(1000.0)


def test_jacking_stress_plus_losses() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": "Jacking Stress + Losses", "fpu_MPa": 1860.0, "fpj_ratio": 0.75, "loss_percent": 15.0})]),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    element = result.elements[0]
    assert not result.errors
    assert element.initial_stress_mpa == pytest.approx(expected_fpe)
    assert element.pe_eff_n == pytest.approx(100.0 * expected_fpe)


def test_jacking_total_loss_mode_converts_to_effective_prestress() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(**{"Input Mode": JACKING_LOSS_INPUT_MODE, "fpu_MPa": 1860.0, "fpj_ratio": 0.75, "loss_percent": 15.0})]),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    element = result.elements[0]
    assert not result.errors
    assert element.initial_stress_mpa == pytest.approx(expected_fpe)
    assert element.initial_strain == pytest.approx(expected_fpe / 195000.0)
    assert element.pe_eff_n == pytest.approx(100.0 * expected_fpe)


def test_fpy_greater_than_or_equal_to_fpu_is_rejected() -> None:
    with pytest.raises(ValueError, match="fpy_mpa"):
        PrestressElement(
            x_mm=0,
            y_mm=0,
            area_mm2=100,
            steel_type="custom",
            fpy_mpa=1860,
            fpu_mpa=1860,
        )


def test_unknown_product_without_area_gives_error() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(Product="UNKNOWN", Area_mm2=None)]),
        load_prestress_steel_database(),
    )

    assert any("not in the database" in error for error in result.errors)
    assert result.elements == []


def test_unknown_product_with_area_gives_custom_element_with_warning() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(Product="UNKNOWN", Area_mm2=120.0)]),
        load_prestress_steel_database(),
    )

    assert not result.errors
    assert result.elements[0].area_mm2 == 120.0
    assert any("not in the database" in warning for warning in result.warnings)


def test_standard_tendon_product_row_parses_as_tendon_group_area_without_pe_override() -> None:
    row = apply_tendon_product_to_row(_row(**{"Input Mode": "Effective Force Pe", "Pe_eff_kN": 500.0}), "6-12")
    result = prestress_elements_from_dataframe(pd.DataFrame([row]), load_prestress_steel_database())

    assert not result.errors
    element = result.elements[0]
    assert element.material_name == "Tendon 6-12"
    assert element.steel_type == "tendon_group"
    assert element.area_mm2 == pytest.approx(1680.0)
    assert element.diameter_mm is None
    assert element.fpy_mpa == pytest.approx(1580.0)
    assert element.fpu_mpa == pytest.approx(1860.0)
    assert element.pe_eff_n == pytest.approx(500_000.0)


def test_custom_tendon_product_row_parses_without_using_duct_as_diameter() -> None:
    product = make_custom_tendon_product(25, duct_id_mm=125.0)
    row = apply_tendon_product_to_row(_row(Product="Custom", Diameter_mm=125.0, Area_mm2=100.0), product)
    result = prestress_elements_from_dataframe(pd.DataFrame([row]), load_prestress_steel_database())

    assert not result.errors
    assert not result.warnings
    element = result.elements[0]
    assert element.material_name == "Tendon 6-25"
    assert element.steel_type == "tendon_group"
    assert element.area_mm2 == pytest.approx(3500.0)
    assert element.diameter_mm is None
    assert element.fpy_mpa == pytest.approx(1580.0)
    assert element.fpu_mpa == pytest.approx(1860.0)
    assert element.count == 1


def test_product_options_include_standard_products_and_current_custom_labels() -> None:
    prestress_db = load_prestress_steel_database()
    table = pd.DataFrame(
        [
            _row(Product="6-25", **{"Steel Type": "tendon_group", "Strand Count": 25}),
            _row(Product="Custom high-strength bar"),
            _row(Product=""),
            _row(Product=None),
        ]
    )

    options = _product_options_for_table(prestress_db, table)

    assert options[:2] == ["", "Custom"]
    assert "Tendon 6-1" in options
    assert "Tendon 6-12" in options
    assert "Tendon 6-25" in options
    assert "Tendon 6-55" in options
    assert "6-25" not in options
    assert options.index("Tendon 6-1") < options.index("Tendon 6-55") < options.index("15.2mm strand")
    assert "PS Bar 32 - 1080/1230" in options
    assert "Custom high-strength bar" in options


def test_product_creation_modes_exclude_manual_custom_table() -> None:
    assert TENDON_PRODUCT_CREATION_MODES == ["Standard tendon product", "Custom tendon"]
    assert "Manual / custom table" not in TENDON_PRODUCT_CREATION_MODES


def test_effective_input_mode_options_are_user_facing_modes() -> None:
    assert INPUT_MODE_OPTIONS == ["Passive", "Pe_eff", "fpe", JACKING_LOSS_INPUT_MODE]


def test_prestress_layout_methods_keep_only_manual_as_implemented_workflow() -> None:
    assert PRESTRESS_LAYOUT_METHOD_OPTIONS == [
        MANUAL_PRESTRESS_LAYOUT_METHOD,
        AUTO_PERIMETER_PRESTRESS_LAYOUT_METHOD,
        "Linear layout",
        "Circular layout",
    ]
    assert PLANNED_PRESTRESS_LAYOUT_METHODS == ["Linear layout", "Circular layout"]
    assert not _is_planned_prestress_layout_method(MANUAL_PRESTRESS_LAYOUT_METHOD)
    assert not _is_planned_prestress_layout_method(AUTO_PERIMETER_PRESTRESS_LAYOUT_METHOD)
    assert _is_planned_prestress_layout_method("Linear layout")
    assert _is_planned_prestress_layout_method("Circular layout")


def test_planned_prestress_layout_message_routes_user_back_to_manual_table() -> None:
    message = _planned_prestress_layout_message("Linear layout")

    assert "Linear layout is planned" in message
    assert "Manual table remains the active prestress input workflow" in message
    assert "not used for analysis yet" in message


def test_default_auto_prestress_product_prefers_single_strand() -> None:
    options = ["", "Custom", "Tendon 6-12", "15.2mm strand", "PS Bar 32 - 1080/1230"]

    assert _default_auto_prestress_product_option(options) == options.index("15.2mm strand")


def test_auto_perimeter_prestress_layout_generates_jacking_rows() -> None:
    geometry = rectangle(width_mm=600.0, height_mm=600.0)
    db = load_prestress_steel_database()

    result = generate_auto_perimeter_prestress_layout(
        geometry,
        db,
        product="15.2mm strand",
        edge_offset_mm=75.0,
        target_spacing_mm=150.0,
        min_elements=4,
        label_prefix="PS-AUTO-",
        input_mode=JACKING_LOSS_INPUT_MODE,
    )

    assert result.ok
    assert len(result.table) == 12
    assert result.actual_spacing_mm == pytest.approx(150.0)
    assert result.table["Label"].iloc[0] == "PS-AUTO-01"
    assert set(result.table["Product"]) == {"15.2mm strand"}
    assert set(result.table["Input Mode"]) == {JACKING_LOSS_INPUT_MODE}
    assert result.table["Pe_eff_kN"].sum() > 0.0
    assert all("Auto perimeter prestress" in note for note in result.table["Note"])


def test_auto_perimeter_prestress_layout_handles_hollow_section_outer_boundary() -> None:
    geometry = rectangular_hollow(
        width_mm=1000.0,
        height_mm=800.0,
        t_top_mm=120.0,
        t_bottom_mm=140.0,
        t_left_mm=110.0,
        t_right_mm=130.0,
    )
    db = load_prestress_steel_database()

    result = generate_auto_perimeter_prestress_layout(
        geometry,
        db,
        product="15.2mm strand",
        edge_offset_mm=75.0,
        target_spacing_mm=150.0,
        min_elements=4,
        label_prefix="PS-AUTO-",
        input_mode=JACKING_LOSS_INPUT_MODE,
    )

    assert result.ok
    generated_points = {(round(row.x_mm, 3), round(row.y_mm, 3)) for row in result.table.itertuples()}
    assert {(-425.0, -325.0), (425.0, -325.0), (425.0, 325.0), (-425.0, 325.0)} <= generated_points
    parsed = prestress_elements_from_dataframe(result.table, db)
    assert parsed.errors == []
    assert validate_prestress_against_geometry(parsed.elements, geometry) == []


def test_auto_perimeter_prestress_layout_rejects_impossible_offset() -> None:
    geometry = rectangle(width_mm=200.0, height_mm=200.0)

    result = generate_auto_perimeter_prestress_layout(
        geometry,
        load_prestress_steel_database(),
        product="15.2mm strand",
        edge_offset_mm=125.0,
        target_spacing_mm=150.0,
        min_elements=4,
    )

    assert not result.ok
    assert "offset is too large" in result.errors[0]


def test_auto_perimeter_prestress_layout_requires_catalog_product() -> None:
    result = generate_auto_perimeter_prestress_layout(
        rectangle(width_mm=600.0, height_mm=600.0),
        load_prestress_steel_database(),
        product="Custom",
    )

    assert not result.ok
    assert "Select a catalog prestress product" in result.errors[0]


def test_apply_force_input_method_updates_active_rows_only() -> None:
    table = pd.DataFrame(
        [
            _row(Label="PS1", Active=True, **{"Input Mode": "Passive"}),
            _row(Label="PS2", Active=False, **{"Input Mode": "Passive"}),
        ]
    )

    applied = _apply_force_input_method_to_active_rows(table, INPUT_MODE_DISPLAY_LABELS["Pe_eff"])

    assert applied.loc[0, "Input Mode"] == "Pe_eff"
    assert applied.loc[1, "Input Mode"] == "Passive"


def test_apply_force_input_method_jacking_defaults_blank_loss_inputs_for_active_rows() -> None:
    table = pd.DataFrame(
        [
            _row(Label="PS1", Active=True, fpj_ratio=None, loss_percent=None, **{"Input Mode": "Passive"}),
            _row(Label="PS2", Active=False, fpj_ratio=None, loss_percent=None, **{"Input Mode": "Passive"}),
        ]
    )

    applied = _apply_force_input_method_to_active_rows(table, JACKING_LOSS_INPUT_MODE)

    assert applied.loc[0, "Input Mode"] == JACKING_LOSS_INPUT_MODE
    assert applied.loc[0, "fpj_ratio"] == pytest.approx(0.75)
    assert applied.loc[0, "loss_percent"] == pytest.approx(15.0)
    assert applied.loc[1, "Input Mode"] == "Passive"
    assert pd.isna(applied.loc[1, "fpj_ratio"])
    assert pd.isna(applied.loc[1, "loss_percent"])


def test_apply_force_input_method_jacking_syncs_effective_force_after_normalization() -> None:
    table = pd.DataFrame([_row(Active=True, Area_mm2=1680.0, fpu_MPa=1860.0, fpj_ratio=None, loss_percent=None)])

    applied = _apply_force_input_method_to_active_rows(table, JACKING_LOSS_INPUT_MODE)
    normalized = normalize_prestress_table_for_effective_input_sync(applied, load_prestress_steel_database())

    expected_fpe = 1860.0 * 0.75 * 0.85
    assert normalized.loc[0, "Input Mode"] == JACKING_LOSS_INPUT_MODE
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(expected_fpe)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0 * expected_fpe / 1000.0)




def test_prestress_table_defaults_count_and_note_for_new_rows() -> None:
    table = pd.DataFrame(
        [
            _row(
                Product="6-25",
                **{
                    "Steel Type": "tendon_group",
                    "Count": None,
                    "Note": None,
                    "Input Mode": "fpe",
                    "fpe_MPa": 600.0,
                },
            )
        ]
    )

    normalized = normalize_prestress_table_for_effective_input_sync(table, load_prestress_steel_database())

    assert normalized.loc[0, "Count"] == 1
    assert normalized.loc[0, "Note"] == ""
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(2100.0)


def test_input_mode_editor_labels_are_user_facing_but_normalize_to_canonical_values() -> None:
    editor_table = _prestress_table_for_editor(pd.DataFrame([_row(**{"Input Mode": "Pe_eff"})]))

    assert editor_table.loc[0, "Input Mode"] == "Pe_eff"

    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": INPUT_MODE_DISPLAY_LABELS["fpe"], "Area_mm2": 1680.0, "fpe_MPa": 1000.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Input Mode"] == "fpe"
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0)


def test_jacking_total_loss_editor_label_normalizes_to_canonical_mode() -> None:
    editor_table = _prestress_table_for_editor(pd.DataFrame([_row(**{"Input Mode": JACKING_LOSS_INPUT_MODE})]))

    assert editor_table.loc[0, "Input Mode"] == "Jacking + Total Loss %"

    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame(
            [
                _row(
                    **{
                        "Input Mode": INPUT_MODE_DISPLAY_LABELS[JACKING_LOSS_INPUT_MODE],
                        "Area_mm2": 1680.0,
                        "fpu_MPa": 1860.0,
                    }
                )
            ]
        ),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    assert normalized.loc[0, "Input Mode"] == JACKING_LOSS_INPUT_MODE
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(expected_fpe)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0 * expected_fpe / 1000.0)


def test_legacy_verbose_input_mode_labels_still_normalize() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame(
            [
                _row(
                    **{
                        "Input Mode": "Jacking + Total Loss % - compute Pe_eff from fpj and total loss",
                        "Area_mm2": 1680.0,
                        "fpu_MPa": 1860.0,
                    }
                )
            ]
        ),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    assert normalized.loc[0, "Input Mode"] == JACKING_LOSS_INPUT_MODE
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(expected_fpe)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0 * expected_fpe / 1000.0)


def test_note_is_not_shown_in_compact_prestress_editor_columns() -> None:
    assert "Count" in PRESTRESS_COMPACT_EDITOR_COLUMNS
    assert "Note" not in PRESTRESS_COMPACT_EDITOR_COLUMNS


def test_effective_input_sync_passive_sets_zero_force_and_stress() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "Passive", "Pe_eff_kN": 1848.0, "fpe_MPa": 1100.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(0.0)
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(0.0)


def test_effective_input_sync_pe_eff_mode_computes_fpe() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "Pe_eff", "Area_mm2": 1680.0, "Pe_eff_kN": 1848.0, "fpe_MPa": 0.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1848.0)
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(1100.0)


def test_effective_input_sync_fpe_mode_computes_pe_eff() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "fpe", "Area_mm2": 1680.0, "Pe_eff_kN": 0.0, "fpe_MPa": 1100.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(1100.0)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1848.0)


def test_effective_input_sync_jacking_total_loss_mode_computes_pe_eff() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame(
            [
                _row(
                    **{
                        "Input Mode": JACKING_LOSS_INPUT_MODE,
                        "Area_mm2": 1680.0,
                        "fpu_MPa": 1860.0,
                        "Pe_eff_kN": 0.0,
                        "fpe_MPa": 0.0,
                    }
                )
            ]
        ),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    assert normalized.loc[0, "Input Mode"] == JACKING_LOSS_INPUT_MODE
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(expected_fpe)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0 * expected_fpe / 1000.0)


def test_effective_input_sync_tendon_group_jacking_mode_uses_area_and_fpu_not_breaking_load() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(Product="6-25", **{"Steel Type": "tendon_group", "Input Mode": JACKING_LOSS_INPUT_MODE, "Pe_eff_kN": 1.0, "fpe_MPa": 1.0})]),
        load_prestress_steel_database(),
    )

    expected_fpe = 1860.0 * 0.75 * 0.85
    assert normalized.loc[0, "Area_mm2"] == pytest.approx(3500.0)
    assert normalized.loc[0, "Breaking Load_kN"] == pytest.approx(6500.0)
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(expected_fpe)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(3500.0 * expected_fpe / 1000.0)
    assert normalized.loc[0, "Pe_eff_kN"] != pytest.approx(normalized.loc[0, "Breaking Load_kN"])


def test_effective_input_sync_product_area_change_preserves_pe_eff_and_recomputes_fpe() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(Product="6-25", **{"Steel Type": "tendon_group", "Input Mode": "Pe_eff", "Area_mm2": 1680.0, "Pe_eff_kN": 1848.0, "fpe_MPa": 1100.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Area_mm2"] == pytest.approx(3500.0)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1848.0)
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(528.0)
    assert normalized.loc[0, "Breaking Load_kN"] == pytest.approx(6500.0)
    assert normalized.loc[0, "Pe_eff_kN"] != pytest.approx(normalized.loc[0, "Breaking Load_kN"])


def test_effective_input_sync_product_area_change_preserves_fpe_and_recomputes_pe_eff() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(Product="6-25", **{"Steel Type": "tendon_group", "Input Mode": "fpe", "Area_mm2": 1680.0, "Pe_eff_kN": 1680.0, "fpe_MPa": 1000.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Area_mm2"] == pytest.approx(3500.0)
    assert normalized.loc[0, "fpe_MPa"] == pytest.approx(1000.0)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(3500.0)
    assert normalized.loc[0, "Pe_eff_kN"] != pytest.approx(normalized.loc[0, "Breaking Load_kN"])


def test_effective_input_sync_standard_tendon_fields_remain_intact() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(Product="6-12", **{"Steel Type": "tendon_group", "Input Mode": "Pe_eff", "Pe_eff_kN": 1848.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Product"] == "Tendon 6-12"
    assert normalized.loc[0, "Area_mm2"] == pytest.approx(1680.0)
    assert normalized.loc[0, "fpy_MPa"] == pytest.approx(1580.0)
    assert normalized.loc[0, "fpu_MPa"] == pytest.approx(1860.0)
    assert normalized.loc[0, "Ep_MPa"] == pytest.approx(195000.0)
    assert normalized.loc[0, "Strand Count"] == 12
    assert normalized.loc[0, "Diameter_mm"] is None
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1848.0)


def test_effective_input_sync_ps_bar_database_product_fields_remain_intact() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(Product="PS Bar 32 - 1080/1230", **{"Input Mode": "Pe_eff", "Pe_eff_kN": 100.0})]),
        load_prestress_steel_database(),
    )

    assert normalized.loc[0, "Steel Type"] == "prestressing_bar"
    assert normalized.loc[0, "Diameter_mm"] == pytest.approx(32.0)
    assert normalized.loc[0, "Area_mm2"] == pytest.approx(804.2)
    assert normalized.loc[0, "fpy_MPa"] == pytest.approx(1080.0)
    assert normalized.loc[0, "fpu_MPa"] == pytest.approx(1230.0)
    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(100.0)


def test_effective_input_sync_is_idempotent_after_dependent_field_update() -> None:
    prestress_db = load_prestress_steel_database()
    first = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "fpe", "Area_mm2": 1680.0, "Pe_eff_kN": 0.0, "fpe_MPa": 1000.0})]),
        prestress_db,
    )
    second = normalize_prestress_table_for_effective_input_sync(first, prestress_db)

    pd.testing.assert_frame_equal(first, second)


def test_total_pe_summary_uses_normalized_effective_force() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "fpe", "Area_mm2": 1680.0, "fpe_MPa": 1000.0, "Count": 2})]),
        load_prestress_steel_database(),
    )
    result = prestress_elements_from_dataframe(normalized, load_prestress_steel_database())

    metrics = {metric.title: metric for metric in _build_prestress_summary_metrics(result, [], True)}

    assert normalized.loc[0, "Pe_eff_kN"] == pytest.approx(1680.0)
    assert metrics["Total Pe_eff"].value == "3,360.0 kN"


def test_effective_input_validation_warns_for_zero_pe_eff_mode() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "Pe_eff", "Area_mm2": 1680.0, "Pe_eff_kN": 0.0})]),
        load_prestress_steel_database(),
    )
    result = prestress_elements_from_dataframe(normalized, load_prestress_steel_database())

    assert not result.errors
    assert any("zero Pe_eff_kN" in warning for warning in result.warnings)


def test_effective_input_validation_warns_above_seventy_five_percent_fpu() -> None:
    normalized = normalize_prestress_table_for_effective_input_sync(
        pd.DataFrame([_row(**{"Input Mode": "fpe", "Area_mm2": 1680.0, "fpe_MPa": 1400.0, "fpu_MPa": 1860.0})]),
        load_prestress_steel_database(),
    )
    result = prestress_elements_from_dataframe(normalized, load_prestress_steel_database())

    assert not result.errors
    assert any("0.75 x fpu_MPa" in warning for warning in result.warnings)


def test_tendon_group_table_display_normalizes_diameter_and_equivalent_diameter() -> None:
    table = pd.DataFrame(
        [
            _row(
                Product="6-25",
                **{
                    "Steel Type": "tendon_group",
                    "Area_mm2": 3500.0,
                    "Diameter_mm": 125.0,
                    "Strand Count": 25,
                    "fpy_MPa": None,
                    "fpu_MPa": 1860.0,
                },
            )
        ]
    )

    normalized = _normalize_prestress_table_for_display(table)

    assert normalized.loc[0, "Diameter_mm"] is None
    assert normalized.loc[0, "Eq Steel Dia_mm"] == pytest.approx(66.8, abs=0.05)
    assert normalized.loc[0, "fpy_MPa"] == pytest.approx(1580.0)
    assert normalized.loc[0, "Count"] == 1


def test_inactive_rows_are_ignored() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(Active=False, x_mm="bad", y_mm="bad", Area_mm2=None)]),
        load_prestress_steel_database(),
    )

    assert not result.errors
    assert result.elements == []


def test_count_greater_than_one_is_handled_by_element_count() -> None:
    result = prestress_elements_from_dataframe(
        pd.DataFrame([_row(Count=3, Area_mm2=100.0)]),
        load_prestress_steel_database(),
    )

    assert not result.errors
    assert len(result.elements) == 1
    assert result.elements[0].count == 3
    assert result.elements[0].total_area_mm2 == pytest.approx(300.0)


def test_prestress_outside_section_is_detected() -> None:
    geometry = rectangle(width_mm=400, height_mm=400)
    element = PrestressElement(x_mm=300, y_mm=0, area_mm2=100, steel_type="custom", label="OUT")

    errors = validate_prestress_against_geometry([element], geometry)

    assert any("outside concrete" in error for error in errors)


def test_prestress_inside_hole_is_detected() -> None:
    geometry = rectangular_hollow(width_mm=1000, height_mm=800, t_top_mm=100, t_bottom_mm=100, t_left_mm=100, t_right_mm=100)
    element = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, steel_type="custom", label="VOID")

    errors = validate_prestress_against_geometry([element], geometry)

    assert any("inside a void" in error for error in errors)


def test_prestress_valid_for_analysis_false_if_outside_section() -> None:
    element = PrestressElement(x_mm=300, y_mm=0, area_mm2=100, steel_type="custom", label="OUT")
    result = PrestressParseResult(elements=[element], errors=[], warnings=[], info=[])
    errors = validate_prestress_against_geometry([element], rectangle(width_mm=400, height_mm=400))

    assert prestress_valid_for_analysis(result, errors) is False


def test_preview_accepts_prestress_elements_without_crashing() -> None:
    element = PrestressElement(x_mm=0, y_mm=0, area_mm2=100, steel_type="strand", label="PS")
    fig = create_section_preview(rectangle(width_mm=400, height_mm=400), prestress_elements=[element])

    assert fig.data
    assert any(trace.name == "Prestressing strand/tendon" for trace in fig.data)


def test_equivalent_diameter_from_area_matches_circular_area() -> None:
    assert equivalent_diameter_from_area(140.0) == pytest.approx(13.35, abs=0.01)
    assert equivalent_diameter_from_area(1680.0) == pytest.approx(46.27, abs=0.03)


def test_tendon_group_display_diameter_uses_total_steel_area_not_diameter() -> None:
    element = PrestressElement(
        x_mm=0,
        y_mm=0,
        area_mm2=140.0,
        diameter_mm=120.0,
        steel_type="tendon_group",
        count=12,
        label="12 strand tendon",
    )

    assert display_diameter_for_prestress_element(element) == pytest.approx(46.27, abs=0.03)


def test_tendon_group_preview_circle_uses_true_scale_total_steel_area() -> None:
    element = PrestressElement(
        x_mm=100.0,
        y_mm=-50.0,
        area_mm2=140.0,
        diameter_mm=120.0,
        steel_type="tendon_group",
        count=12,
        label="12 strand tendon",
    )
    fig = create_section_preview(rectangle(width_mm=400, height_mm=400), prestress_elements=[element])

    shape = fig.layout.shapes[0]
    assert shape.type == "circle"
    assert shape.xref == "x"
    assert shape.yref == "y"
    assert (shape.x1 - shape.x0) / 2.0 == pytest.approx(23.13, abs=0.03)
    assert (shape.y1 - shape.y0) / 2.0 == pytest.approx(23.13, abs=0.03)
    assert shape.x0 == pytest.approx(100.0 - 23.13, abs=0.03)
    assert shape.x1 == pytest.approx(100.0 + 23.13, abs=0.03)
    assert shape.y0 == pytest.approx(-50.0 - 23.13, abs=0.03)
    assert shape.y1 == pytest.approx(-50.0 + 23.13, abs=0.03)


def test_prestress_preview_uses_circle_markers_and_type_colors() -> None:
    strand = PrestressElement(x_mm=-50, y_mm=0, area_mm2=140.0, diameter_mm=15.2, steel_type="strand", label="Strand")
    pt_bar = PrestressElement(x_mm=50, y_mm=0, area_mm2=804.2, diameter_mm=32.0, steel_type="prestressing_bar", label="PT Bar")
    fig = create_section_preview(rectangle(width_mm=400, height_mm=400), prestress_elements=[strand, pt_bar])
    traces = {trace.name: trace for trace in fig.data}

    assert traces["Prestressing strand/tendon"].marker.symbol == "circle"
    assert traces["PT bar"].marker.symbol == "circle"
    assert traces["Prestressing strand/tendon"].marker.color != traces["PT bar"].marker.color
    assert len(fig.layout.shapes) == 2


def test_prestress_summary_includes_total_area_and_total_force() -> None:
    element = PrestressElement(
        x_mm=0,
        y_mm=0,
        area_mm2=100,
        steel_type="strand",
        pe_eff_n=50_000,
        count=3,
        label="PS",
    )

    summary = prestress_summary_dataframe([element])

    assert "material_name" in summary.columns
    assert "total_area_mm2" in summary.columns
    assert "total_pe_eff_n" in summary.columns
    assert summary.loc[0, "total_area_mm2"] == pytest.approx(300.0)
    assert summary.loc[0, "total_pe_eff_n"] == pytest.approx(150_000.0)


def test_prestress_summary_metrics_count_active_types_and_force() -> None:
    result = PrestressParseResult(
        elements=[
            PrestressElement(x_mm=0, y_mm=0, area_mm2=100.0, steel_type="tendon_group", pe_eff_n=50_000.0, count=2, bonded=True),
            PrestressElement(x_mm=0, y_mm=0, area_mm2=140.0, steel_type="strand", pe_eff_n=10_000.0, count=1, bonded=False),
        ],
        errors=[],
        warnings=[],
        info=[],
    )

    metrics = {metric.title: metric for metric in _build_prestress_summary_metrics(result, [], True)}

    assert metrics["Valid elements"].value == "2"
    assert metrics["Total Aps"].value == "340.0 mm2"
    assert metrics["Total Pe_eff"].value == "110.0 kN"
    assert metrics["Analysis readiness"].value == "Yes"
    assert metrics["Tendon groups"].value == "1"
    assert metrics["Tendon groups"].detail == "Strand/PT bars: 1"
    assert metrics["Bonded state"].value == "1 / 1"


def test_prestress_status_rows_include_geometry_warning_without_validation_logic_change() -> None:
    result = PrestressParseResult(elements=[], errors=[], warnings=[], info=[])

    rows = {row.title: row for row in _build_prestress_status_rows(result, [], False, True, active_rebar_count=1)}

    assert rows["Overall readiness"].value == "Ready"
    assert rows["Warnings"].value == "1"
    assert rows["Warnings"].status == "warning"


def test_engineering_notes_preserve_prestress_safeguards() -> None:
    html = _engineering_notes_html()

    assert "Product breaking load is reference data only" in html
    assert "Choose Pe_eff to enter effective force directly" in html
    assert "Choose fpe to enter effective stress" in html
    assert "Duct ID is duct reference information and is not steel diameter" in html
    assert "Area_mm2 controls steel area" in html
    assert "not external Pu demand" in html


def test_prestress_elements_from_dataframe_empty_active_rows_does_not_emit_presence_warning() -> None:
    prestress_db = load_prestress_steel_database()
    row = apply_tendon_product_to_row(_row(Active=False), "Tendon 6-12")

    result = prestress_elements_from_dataframe(pd.DataFrame([row]), prestress_db)

    assert result.elements == []
    assert not any("No active" in warning for warning in result.warnings)

def test_prestress_summary_labels_active_and_passive_analysis_roles() -> None:
    elements = [
        PrestressElement(
            x_mm=0,
            y_mm=-100,
            area_mm2=100,
            steel_type="strand",
            pe_eff_n=50_000,
            initial_stress_mpa=500,
            initial_strain=500 / 195000,
            bonded=True,
            label="PS-active",
        ),
        PrestressElement(
            x_mm=0,
            y_mm=100,
            area_mm2=100,
            steel_type="prestressing_bar",
            pe_eff_n=0,
            initial_stress_mpa=0,
            initial_strain=0,
            bonded=True,
            label="PS-passive",
        ),
    ]

    summary = prestress_summary_dataframe(elements)

    assert "Analysis role" in summary.columns
    assert summary.loc[summary["Label"] == "PS-active", "Analysis role"].iloc[0] == "Active bonded prestress"
    assert summary.loc[summary["Label"] == "PS-passive", "Analysis role"].iloc[0] == "Passive bonded high-strength steel"
