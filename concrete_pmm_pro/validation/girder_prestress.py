"""Validation checks for Beam/Girder effective-prestress stress effects."""

from __future__ import annotations

from concrete_pmm_pro.core.models import PrestressElement
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_prestress import (
    run_girder_prestress_stress_effect,
    summarize_girder_prestress_elements,
)
from concrete_pmm_pro.serviceability.girder_stress import make_girder_basis_from_gross_summary
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Girder prestress stress"


def validate_girder_prestress_stress() -> list[ValidationResult]:
    """Return validation results for the prestress stress-effect kernel."""

    results: list[ValidationResult] = []
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))
    area = 1000.0 * 500.0
    ix = 1000.0 * 500.0**3 / 12.0

    low_tendon = run_girder_prestress_stress_effect(basis, Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=100.0)
    axial = -2000.0 * 1000.0 / area
    e = 100.0 - 250.0
    mps = 2000.0 * e / 1000.0
    expected_top = axial + mps * 1_000_000.0 * (250.0 - 500.0) / ix
    expected_bottom = axial + mps * 1_000_000.0 * (250.0 - 0.0) / ix
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.LOW.TOP",
            category=CATEGORY,
            title="Low tendon produces top stress from Pe/A and eccentricity",
            expected=expected_top,
            actual=low_tendon.top.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="Compression is negative and tension is positive; low tendon may create top tension.",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.LOW.BOTTOM",
            category=CATEGORY,
            title="Low tendon increases bottom compression",
            expected=expected_bottom,
            actual=low_tendon.bottom.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="GIRDER.PS.LOW.SIGN",
            category=CATEGORY,
            title="Low tendon has bottom compression larger than top compression",
            passed=low_tendon.bottom.total_stress_MPa < low_tendon.top.total_stress_MPa,
            expected="bottom stress more compressive than top",
            actual=(low_tendon.top.total_stress_MPa, low_tendon.bottom.total_stress_MPa),
        )
    )

    centroid_tendon = run_girder_prestress_stress_effect(basis, Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=250.0)
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.CENTROID.TOP",
            category=CATEGORY,
            title="Centroidal prestress has axial stress only at top",
            expected=axial,
            actual=centroid_tendon.top.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.CENTROID.BOTTOM",
            category=CATEGORY,
            title="Centroidal prestress has axial stress only at bottom",
            expected=axial,
            actual=centroid_tendon.bottom.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )

    high_tendon = run_girder_prestress_stress_effect(basis, Pe_eff_kN=2000.0, tendon_y_from_bottom_mm=400.0)
    results.append(
        boolean_validation_result(
            case_id="GIRDER.PS.HIGH.SIGN",
            category=CATEGORY,
            title="High tendon increases top compression",
            passed=high_tendon.top.total_stress_MPa < high_tendon.bottom.total_stress_MPa,
            expected="top stress more compressive than bottom",
            actual=(high_tendon.top.total_stress_MPa, high_tendon.bottom.total_stress_MPa),
        )
    )

    elements = [
        PrestressElement(x_mm=0.0, y_mm=-150.0, area_mm2=140.0, pe_eff_n=100_000.0, count=2, label="PS1"),
        PrestressElement(x_mm=0.0, y_mm=-50.0, area_mm2=140.0, pe_eff_n=200_000.0, count=1, label="PS2"),
        PrestressElement(x_mm=0.0, y_mm=0.0, area_mm2=140.0, pe_eff_n=0.0, count=1, label="Passive"),
    ]
    summary = summarize_girder_prestress_elements(elements, section_bottom_y_mm=-250.0)
    expected_y = ((100_000.0 * 2) * 100.0 + 200_000.0 * 200.0) / 400_000.0
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.ELEMENTS.PE",
            category=CATEGORY,
            title="Prestress element summary uses pe_eff_n times count",
            expected=400.0,
            actual=summary.total_pe_eff_kN,
            abs_tolerance=1.0e-9,
            units="kN",
            engineering_note="Breaking load, strand count metadata, and duct diameter are not used as Pe_eff.",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="GIRDER.PS.ELEMENTS.Y",
            category=CATEGORY,
            title="Prestress element summary reports Pe-weighted y from bottom",
            expected=expected_y,
            actual=summary.tendon_y_from_bottom_mm or 0.0,
            abs_tolerance=1.0e-9,
            units="mm",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="GIRDER.PS.ZERO.IGNORED",
            category=CATEGORY,
            title="Zero Pe_eff element is ignored in girder prestress summary",
            passed=summary.ignored_element_count == 1 and any("no positive Pe_eff" in warning for warning in summary.warnings),
            expected="one zero-Pe element ignored with warning",
            actual={"ignored": summary.ignored_element_count, "warnings": summary.warnings},
        )
    )

    return results
