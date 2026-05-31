"""Validation checks for Beam/Girder service-stress code-limit preview framework."""

from __future__ import annotations

import math

from concrete_pmm_pro.serviceability.girder_code_limits import (
    StressLimitInputRow,
    build_girder_sls_limit_profile,
    default_girder_sls_limit_profile,
    run_girder_service_stress_limit_check,
)
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Girder SLS code limits"


def validate_girder_code_limits() -> list[ValidationResult]:
    """Return validation cases for CODE.SLS.LIMIT1."""

    results: list[ValidationResult] = []
    fc = 45.0
    aashto_service = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Service / Final")
    aci_transfer = default_girder_sls_limit_profile("ACI 318", "Transfer")

    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT1.AASHTO.SERVICE.COMP",
            category=CATEGORY,
            title="AASHTO service compression preview limit",
            expected=0.45 * fc,
            actual=aashto_service.compression_limit_MPa(fc),
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="Preview profile value is centralized and editable; verify project-specific code clause before final design.",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT1.ACI.TRANSFER.TENSION",
            category=CATEGORY,
            title="ACI transfer tension preview limit",
            expected=0.25 * math.sqrt(fc),
            actual=aci_transfer.tension_allowable_MPa(fc),
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="Preview profile value is centralized and editable; verify project-specific code clause before final design.",
        )
    )

    no_tension = build_girder_sls_limit_profile(
        code="AASHTO LRFD Bridge",
        stage="User-defined",
        compression_limit_ratio=0.45,
        tension_limit_mode="No tension",
    )
    no_tension_result = run_girder_service_stress_limit_check(
        stresses=(StressLimitInputRow("Bottom", 0.20),),
        fc_MPa=fc,
        profile=no_tension,
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT1.NO_TENSION.FAILS_TENSION",
            category=CATEGORY,
            title="No-tension profile flags tensile stress",
            passed=no_tension_result.overall_status == "FAIL" and no_tension_result.points[0].status == "FAIL",
            expected="FAIL",
            actual=no_tension_result.overall_status,
            engineering_note="Tension-positive sign convention must be enforced by code-limit preview checks.",
        )
    )

    service_result = run_girder_service_stress_limit_check(
        stresses=(StressLimitInputRow("Top", -5.0), StressLimitInputRow("Bottom", 1.0)),
        fc_MPa=fc,
        profile=aashto_service,
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT1.SERVICE.PASSES_MODERATE_STRESS",
            category=CATEGORY,
            title="Moderate service stresses pass preview limits",
            passed=service_result.overall_status == "PASS" and service_result.failed_count == 0,
            expected="PASS",
            actual=service_result.overall_status,
            engineering_note="Framework check only; not a final code-certified SLS design check.",
        )
    )

    compression_fail = run_girder_service_stress_limit_check(
        stresses=(StressLimitInputRow("Top", -30.0),),
        fc_MPa=fc,
        profile=aashto_service,
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT1.COMPRESSION.FAILS_LIMIT",
            category=CATEGORY,
            title="Compression stress beyond profile limit fails",
            passed=compression_fail.overall_status == "FAIL" and compression_fail.points[0].stress_type == "compression",
            expected="FAIL",
            actual=compression_fail.overall_status,
            engineering_note="Compression stress is negative; utilization is based on absolute compression magnitude.",
        )
    )

    manual_profile = build_girder_sls_limit_profile(
        code="ACI 318",
        stage="User-defined",
        compression_limit_ratio=0.50,
        tension_limit_mode="User-defined",
        tension_limit_MPa=2.0,
    )
    manual_check = run_girder_service_stress_limit_check(
        stresses=(StressLimitInputRow("Bottom", 1.5),),
        fc_MPa=fc,
        profile=manual_profile,
    )
    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT1.MANUAL.TENSION_LIMIT",
            category=CATEGORY,
            title="Manual tension limit override is used",
            expected=1.5 / 2.0,
            actual=float(manual_check.points[0].utilization or 0.0),
            abs_tolerance=1.0e-12,
            units="D/C",
            engineering_note="User-defined profiles are needed until final code/clause calibration is locked by project requirements.",
        )
    )
    return results
