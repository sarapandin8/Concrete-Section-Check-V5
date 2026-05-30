"""Validation checks for Beam/Girder manual service-stage stress cases."""

from __future__ import annotations

from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.serviceability.girder_stage import (
    GirderServiceStageCase,
    default_girder_service_stage_templates,
    run_girder_service_stage_stress,
)
from concrete_pmm_pro.serviceability.girder_stress import make_girder_basis_from_gross_summary
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Girder service stage"


def validate_girder_service_stage_stress() -> list[ValidationResult]:
    """Return validation results for the manual service-stage stress kernel."""

    results: list[ValidationResult] = []
    basis = make_girder_basis_from_gross_summary(summarize_geometry(rectangle(1000.0, 500.0)))
    area = 1000.0 * 500.0
    ix = 1000.0 * 500.0**3 / 12.0

    service_only_case = GirderServiceStageCase(
        stage_id="SERVICE_ONLY",
        title="Service-only benchmark",
        basis_name="precast_gross",
        N_kN=1000.0,
        M_kNm=500.0,
        include_prestress=False,
    )
    service_only = run_girder_service_stage_stress(basis, service_only_case)
    expected_axial = -1000.0 * 1000.0 / area
    expected_top_service = expected_axial + 500.0 * 1_000_000.0 * (250.0 - 500.0) / ix
    expected_bottom_service = expected_axial + 500.0 * 1_000_000.0 * (250.0 - 0.0) / ix
    results.append(
        numeric_validation_result(
            case_id="GIRDER.STAGE.SERVICE.TOP",
            category=CATEGORY,
            title="Stage service-only top stress matches elastic kernel hand calculation",
            expected=expected_top_service,
            actual=service_only.top.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="GIRDER.STAGE.SERVICE.BOTTOM",
            category=CATEGORY,
            title="Stage service-only bottom stress matches elastic kernel hand calculation",
            expected=expected_bottom_service,
            actual=service_only.bottom.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )

    combined_case = GirderServiceStageCase(
        stage_id="COMBINED_PS",
        title="Combined service plus effective prestress benchmark",
        basis_name="precast_gross",
        N_kN=0.0,
        M_kNm=500.0,
        include_prestress=True,
        Pe_eff_kN=2000.0,
        tendon_y_from_bottom_mm=100.0,
    )
    combined = run_girder_service_stage_stress(basis, combined_case)
    service_top = 500.0 * 1_000_000.0 * (250.0 - 500.0) / ix
    service_bottom = 500.0 * 1_000_000.0 * (250.0 - 0.0) / ix
    ps_axial = -2000.0 * 1000.0 / area
    mps = 2000.0 * (100.0 - 250.0) / 1000.0
    ps_top = ps_axial + mps * 1_000_000.0 * (250.0 - 500.0) / ix
    ps_bottom = ps_axial + mps * 1_000_000.0 * (250.0 - 0.0) / ix
    results.append(
        numeric_validation_result(
            case_id="GIRDER.STAGE.COMBINED.TOP",
            category=CATEGORY,
            title="Combined stage top stress equals service plus prestress components",
            expected=service_top + ps_top,
            actual=combined.top.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="GIRDER.STAGE.COMBINED.BOTTOM",
            category=CATEGORY,
            title="Combined stage bottom stress equals service plus prestress components",
            expected=service_bottom + ps_bottom,
            actual=combined.bottom.total_stress_MPa,
            abs_tolerance=1.0e-9,
            units="MPa",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="GIRDER.STAGE.COMBINED.PS_INCLUDED",
            category=CATEGORY,
            title="Combined stage includes a prestress result when Pe_eff and yps are defined",
            passed=combined.prestress_result is not None and combined.prestress_result.Pe_eff_kN == 2000.0,
            expected="prestress result present",
            actual=combined.prestress_result.Pe_eff_kN if combined.prestress_result is not None else None,
        )
    )

    missing_ps_case = GirderServiceStageCase(
        stage_id="MISSING_PS",
        title="Missing prestress centroid warning case",
        basis_name="precast_gross",
        include_prestress=True,
        Pe_eff_kN=1000.0,
        tendon_y_from_bottom_mm=None,
    )
    missing_ps = run_girder_service_stage_stress(basis, missing_ps_case)
    results.append(
        boolean_validation_result(
            case_id="GIRDER.STAGE.MISSING_PS.WARNING",
            category=CATEGORY,
            title="Requested prestress without yps is reported as warning and does not crash",
            passed=missing_ps.prestress_result is None and any("tendon_y_from_bottom" in warning for warning in missing_ps.warnings),
            expected="warning and no prestress result",
            actual={"warnings": missing_ps.warnings, "prestress_result": missing_ps.prestress_result},
        )
    )

    templates = default_girder_service_stage_templates()
    results.append(
        boolean_validation_result(
            case_id="GIRDER.STAGE.TEMPLATES.BASIS",
            category=CATEGORY,
            title="Default stage templates provide precast and composite basis guidance only",
            passed={template.recommended_basis_name for template in templates} == {"precast_gross", "composite_transformed"},
            expected={"precast_gross", "composite_transformed"},
            actual={template.recommended_basis_name for template in templates},
            engineering_note="Templates do not auto-generate loads, losses, or stress limits.",
        )
    )

    return results
