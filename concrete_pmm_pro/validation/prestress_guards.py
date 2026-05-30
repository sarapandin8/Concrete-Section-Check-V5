"""Read-only validation guards for prestress product semantics."""

from __future__ import annotations

from concrete_pmm_pro.data.prestress_tendon_products import (
    apply_tendon_product_to_row,
    equivalent_steel_diameter_mm,
    get_tendon_product,
    make_custom_tendon_product,
)
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Prestress Guards"


def validate_pe_eff_fpe_relationship() -> list[ValidationResult]:
    area_mm2 = 1680.0
    fpe_mpa = 1100.0
    pe_eff_kn = 1848.0
    return [
        numeric_validation_result(
            case_id="PS.GUARD.PE_FROM_FPE",
            category=CATEGORY,
            title="Pe_eff = Aps * fpe / 1000",
            expected=pe_eff_kn,
            actual=area_mm2 * fpe_mpa / 1000.0,
            abs_tolerance=1.0e-9,
            units="kN",
        ),
        numeric_validation_result(
            case_id="PS.GUARD.FPE_FROM_PE",
            category=CATEGORY,
            title="fpe = Pe_eff * 1000 / Aps",
            expected=fpe_mpa,
            actual=pe_eff_kn * 1000.0 / area_mm2,
            abs_tolerance=1.0e-9,
            units="MPa",
        ),
    ]


def validate_breaking_load_is_reference_only() -> list[ValidationResult]:
    row = {"Pe_eff_kN": 123.0, "fpe_MPa": 900.0, "Diameter_mm": 999.0}
    updated = apply_tendon_product_to_row(row, "6-12")
    return [
        boolean_validation_result(
            case_id="PS.GUARD.BREAKING_LOAD_NOT_PE",
            category=CATEGORY,
            title="Breaking load does not populate Pe_eff",
            passed=updated["Pe_eff_kN"] == row["Pe_eff_kN"] and updated["Pe_eff_kN"] != updated["Breaking Load_kN"],
            expected="Pe_eff_kN preserved; Breaking Load_kN reference only",
            actual={"Pe_eff_kN": updated["Pe_eff_kN"], "Breaking Load_kN": updated["Breaking Load_kN"]},
        ),
        boolean_validation_result(
            case_id="PS.GUARD.FPE_PRESERVED",
            category=CATEGORY,
            title="Product application does not overwrite fpe",
            passed=updated["fpe_MPa"] == row["fpe_MPa"],
            expected=row["fpe_MPa"],
            actual=updated["fpe_MPa"],
        ),
    ]


def validate_duct_and_strand_count_guards() -> list[ValidationResult]:
    product = get_tendon_product("6-12")
    custom = make_custom_tendon_product(25, duct_id_mm=125.0)
    assert product is not None
    eq_diameter = equivalent_steel_diameter_mm(product.tendon_area_mm2)
    custom_row = apply_tendon_product_to_row({"Diameter_mm": 125.0, "Pe_eff_kN": 0.0}, custom)
    return [
        boolean_validation_result(
            case_id="PS.GUARD.DUCT_NOT_DIAMETER",
            category=CATEGORY,
            title="Duct ID is not steel display diameter",
            passed=product.duct_id_mm != eq_diameter,
            expected="duct_id_mm is separate from equivalent steel diameter",
            actual={"duct_id_mm": product.duct_id_mm, "eq_steel_dia_mm": eq_diameter},
        ),
        boolean_validation_result(
            case_id="PS.GUARD.CUSTOM_DUCT_NOT_DIAMETER",
            category=CATEGORY,
            title="Custom tendon duct ID is not Diameter_mm",
            passed=custom_row["Diameter_mm"] is None and custom_row["Duct ID_mm"] == custom.duct_id_mm,
            expected={"Diameter_mm": None, "Duct ID_mm": custom.duct_id_mm},
            actual={"Diameter_mm": custom_row["Diameter_mm"], "Duct ID_mm": custom_row["Duct ID_mm"]},
        ),
        numeric_validation_result(
            case_id="PS.GUARD.TENDON_AREA_FROM_STRAND_COUNT",
            category=CATEGORY,
            title="Tendon area equals strand count times strand area",
            expected=product.strand_count * product.strand_area_mm2,
            actual=product.tendon_area_mm2,
            abs_tolerance=1.0e-9,
            units="mm^2",
        ),
        boolean_validation_result(
            case_id="PS.GUARD.NO_DOUBLE_MULTIPLY_STRAND_COUNT",
            category=CATEGORY,
            title="Strand Count remains metadata after product application",
            passed=custom_row["Area_mm2"] == custom.tendon_area_mm2 and custom_row["Count"] == 1,
            expected="Area_mm2 is total tendon area and Count is element count",
            actual={"Area_mm2": custom_row["Area_mm2"], "Strand Count": custom_row["Strand Count"], "Count": custom_row["Count"]},
        ),
    ]


def validate_prestress_guards() -> list[ValidationResult]:
    return [
        *validate_pe_eff_fpe_relationship(),
        *validate_breaking_load_is_reference_only(),
        *validate_duct_and_strand_count_guards(),
    ]
