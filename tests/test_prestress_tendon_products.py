from __future__ import annotations

import pytest

from concrete_pmm_pro.data.prestress_tendon_products import (
    apply_tendon_product_to_row,
    equivalent_steel_diameter_mm,
    get_tendon_product,
    list_tendon_products,
    make_custom_tendon_product,
    tendon_product_options,
)
from concrete_pmm_pro.visualization.section_plot import display_diameter_for_prestress_element, equivalent_diameter_from_area
from concrete_pmm_pro.core.models import PrestressElement


STANDARD_LABELS = {f"Tendon 6-{strand_count}" for strand_count in range(1, 56)}


def test_standard_tendon_product_records_exist() -> None:
    assert set(tendon_product_options()) == STANDARD_LABELS


def test_standard_tendon_products_compute_area_and_breaking_load_from_strand_count() -> None:
    for product in list_tendon_products():
        assert product.tendon_area_mm2 == pytest.approx(product.strand_count * 140.0)
        assert product.breaking_load_kN == pytest.approx(product.strand_count * 260.0)
        assert product.strand_diameter_mm == pytest.approx(15.2)
        assert product.fpy_MPa == pytest.approx(1580.0)
        assert product.fpu_MPa == pytest.approx(1860.0)
        assert product.Ep_MPa == pytest.approx(195000.0)


def test_get_tendon_product_6_12_returns_expected_reference_data() -> None:
    product = get_tendon_product("6-12")

    assert product is not None
    assert product.strand_count == 12
    assert product.tendon_area_mm2 == pytest.approx(1680.0)
    assert product.breaking_load_kN == pytest.approx(3120.0)
    assert product.duct_id_mm == pytest.approx(80.0)




def test_legacy_tendon_label_6_12_is_accepted_and_migrates_to_display_label() -> None:
    legacy = get_tendon_product("6-12")
    current = get_tendon_product("Tendon 6-12")

    assert legacy is not None
    assert current is not None
    assert legacy == current
    assert legacy.label == "Tendon 6-12"

def test_get_tendon_product_6_55_returns_expected_reference_data() -> None:
    product = get_tendon_product("6-55")

    assert product is not None
    assert product.strand_count == 55
    assert product.tendon_area_mm2 == pytest.approx(7700.0)
    assert product.breaking_load_kN == pytest.approx(14300.0)
    assert product.duct_id_mm == pytest.approx(160.0)


def test_make_custom_tendon_product_6_25_computes_nominal_values() -> None:
    product = make_custom_tendon_product(25)

    assert product.label == "Tendon 6-25"
    assert product.strand_count == 25
    assert product.tendon_area_mm2 == pytest.approx(3500.0)
    assert product.breaking_load_kN == pytest.approx(6500.0)
    assert product.fpy_MPa == pytest.approx(1580.0)
    assert product.fpu_MPa == pytest.approx(1860.0)
    assert product.Ep_MPa == pytest.approx(195000.0)


def test_make_custom_tendon_product_6_28_computes_equivalent_display_diameter() -> None:
    product = make_custom_tendon_product(28)

    assert product.label == "Tendon 6-28"
    assert product.tendon_area_mm2 == pytest.approx(3920.0)
    assert product.fpy_MPa == pytest.approx(1580.0)
    assert equivalent_steel_diameter_mm(product.tendon_area_mm2) == pytest.approx(70.65, abs=0.05)


def test_custom_tendon_preview_diameter_uses_steel_area_not_duct_id() -> None:
    product = make_custom_tendon_product(25, duct_id_mm=120.0)
    element = PrestressElement(
        x_mm=0.0,
        y_mm=0.0,
        area_mm2=product.tendon_area_mm2,
        diameter_mm=product.duct_id_mm,
        steel_type="tendon_group",
    )

    assert equivalent_diameter_from_area(3500.0) == pytest.approx(66.8, abs=0.05)
    assert equivalent_steel_diameter_mm(1680.0) == pytest.approx(46.27, abs=0.03)
    assert equivalent_steel_diameter_mm(3500.0) == pytest.approx(66.8, abs=0.05)
    assert display_diameter_for_prestress_element(element) == pytest.approx(66.8, abs=0.05)


def test_apply_standard_tendon_product_to_row_updates_area_and_reference_fields() -> None:
    row = {"Pe_eff_kN": 123.0, "Diameter_mm": 999.0, "Note": "keep user note"}
    updated = apply_tendon_product_to_row(row, "6-12")

    assert updated["Product"] == "Tendon 6-12"
    assert updated["Steel Type"] == "tendon_group"
    assert updated["Area_mm2"] == pytest.approx(1680.0)
    assert updated["Eq Steel Dia_mm"] == pytest.approx(46.27, abs=0.03)
    assert updated["fpy_MPa"] == pytest.approx(1580.0)
    assert updated["fpu_MPa"] == pytest.approx(1860.0)
    assert updated["Ep_MPa"] == pytest.approx(195000.0)
    assert updated["Breaking Load_kN"] == pytest.approx(3120.0)
    assert updated["Duct ID_mm"] == pytest.approx(80.0)
    assert updated["Diameter_mm"] is None
    assert updated["Count"] == 1
    assert updated["Strand Count"] == 12
    assert updated["Pe_eff_kN"] == pytest.approx(123.0)
    assert updated["Pe_eff_kN"] != pytest.approx(updated["Breaking Load_kN"])


def test_apply_custom_tendon_product_to_row_updates_area_without_pe_overwrite() -> None:
    product = make_custom_tendon_product(25, duct_id_mm=125.0, duct_type="Round duct")
    row = {"Pe_eff_kN": 0.0, "fpe_MPa": 900.0}
    updated = apply_tendon_product_to_row(row, product)

    assert updated["Product"] == "Tendon 6-25"
    assert updated["Area_mm2"] == pytest.approx(3500.0)
    assert updated["Eq Steel Dia_mm"] == pytest.approx(66.8, abs=0.05)
    assert updated["fpy_MPa"] == pytest.approx(1580.0)
    assert updated["fpu_MPa"] == pytest.approx(1860.0)
    assert updated["Ep_MPa"] == pytest.approx(195000.0)
    assert updated["Breaking Load_kN"] == pytest.approx(6500.0)
    assert updated["Duct Type"] == "Round duct"
    assert updated["Duct ID_mm"] == pytest.approx(125.0)
    assert updated["Diameter_mm"] is None
    assert updated["Count"] == 1
    assert updated["Strand Count"] == 25
    assert updated["Pe_eff_kN"] == pytest.approx(0.0)
    assert updated["fpe_MPa"] == pytest.approx(900.0)
    assert updated["Pe_eff_kN"] != pytest.approx(updated["Breaking Load_kN"])
