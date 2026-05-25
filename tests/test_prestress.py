from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.data.prestress_tendon_products import apply_tendon_product_to_row, make_custom_tendon_product
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.ui.prestress_page import (
    PrestressParseResult,
    load_prestress_steel_database,
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
    assert element.material_name == "6-12"
    assert element.steel_type == "tendon_group"
    assert element.area_mm2 == pytest.approx(1680.0)
    assert element.diameter_mm is None
    assert element.fpu_mpa == pytest.approx(1860.0)
    assert element.pe_eff_n == pytest.approx(500_000.0)


def test_custom_tendon_product_row_parses_without_using_duct_as_diameter() -> None:
    product = make_custom_tendon_product(25, duct_id_mm=125.0)
    row = apply_tendon_product_to_row(_row(Product="Custom", Diameter_mm=125.0, Area_mm2=100.0), product)
    result = prestress_elements_from_dataframe(pd.DataFrame([row]), load_prestress_steel_database())

    assert not result.errors
    assert not result.warnings
    element = result.elements[0]
    assert element.material_name == "6-25"
    assert element.steel_type == "tendon_group"
    assert element.area_mm2 == pytest.approx(3500.0)
    assert element.diameter_mm is None


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
