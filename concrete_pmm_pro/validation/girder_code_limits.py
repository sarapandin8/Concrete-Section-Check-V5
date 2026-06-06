"""Validation checks for Beam/Girder service-stress code-limit preview framework."""

from __future__ import annotations

import math

from concrete_pmm_pro.serviceability.girder_code_limits import (
    StressLimitInputRow,
    build_girder_sls_limit_profile,
    default_girder_sls_limit_profile,
    girder_sls_limit_formula_summary,
    girder_sls_limit_profile_options,
    girder_sls_stage_basis_consistency_warnings,
    run_girder_service_stress_limit_check,
)
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Girder SLS code limits"


def validate_girder_code_limits() -> list[ValidationResult]:
    """Return validation cases for CODE.SLS.LIMIT1."""

    results: list[ValidationResult] = []
    fc = 45.0
    aashto_service = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Final service / Composite")
    aci_transfer = default_girder_sls_limit_profile("ACI 318", "Transfer / Release")

    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT1.AASHTO.SERVICE.COMP",
            category=CATEGORY,
            title="AASHTO full-service compression preview limit",
            expected=0.60 * fc,
            actual=aashto_service.compression_limit_MPa(fc),
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="ACI transfer general/interior profile uses 0.25√f'ci; end-zone higher limit is a separate verified profile.",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT1.ACI.TRANSFER.TENSION",
            category=CATEGORY,
            title="ACI transfer general/interior tension preview limit",
            expected=0.25 * math.sqrt(fc),
            actual=aci_transfer.tension_allowable_MPa(fc),
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="Preview profile value is centralized and editable; verify project-specific code clause before final design.",
        )
    )


    aci_final = default_girder_sls_limit_profile("ACI 318", "Final service / Composite")
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT2.CODE_PROFILES.DISTINCT_FINAL_TENSION",
            category=CATEGORY,
            title="AASHTO and ACI final-service preview profiles are visibly distinct",
            passed=aashto_service.tension_allowable_MPa(fc) < aci_final.tension_allowable_MPa(fc),
            expected="AASHTO final-service tension preview < ACI final-service tension preview",
            actual={
                "AASHTO tension MPa": aashto_service.tension_allowable_MPa(fc),
                "ACI tension MPa": aci_final.tension_allowable_MPa(fc),
            },
            engineering_note="Profiles remain editable previews, but they should not look identical when switching code families.",
        )
    )

    formula = girder_sls_limit_formula_summary(profile=aci_transfer, fc_MPa=fc)
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT3.FORMULA_DISPLAY",
            category=CATEGORY,
            title="Limit formula summary exposes formula and substitution text",
            passed="0.600" in formula.compression_formula and "27.000 MPa" in formula.compression_substitution and "0.250" in formula.tension_formula,
            expected="compression and tension formula text",
            actual={
                "compression": formula.compression_formula,
                "compression substitution": formula.compression_substitution,
                "tension": formula.tension_formula,
                "tension substitution": formula.tension_substitution,
            },
            engineering_note="Commercial-grade SLS checks must show how preview limits were calculated, not just the resulting number.",
        )
    )
    consistency_warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Transfer / Release",
        section_basis_label="Composite transformed section",
        load_stage="Final service",
        load_component="Total SLS resultant",
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT3.STAGE_BASIS_GUARD",
            category=CATEGORY,
            title="Stage/load/basis consistency guard flags misleading transfer check",
            passed=len(consistency_warnings) >= 3,
            expected="stage mismatch, composite-basis, and total-resultant warnings",
            actual=list(consistency_warnings),
            engineering_note="A PASS/FAIL preview is not meaningful if a final-service total resultant is checked as a transfer-stage composite result.",
        )
    )

    transfer_no_ps_warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Transfer / Release",
        section_basis_label="Precast gross section",
        load_stage="Transfer / Release",
        load_component="Girder self-weight",
        stress_includes_prestress=False,
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT3.TRANSFER.PRESTRESS_REQUIRED",
            category=CATEGORY,
            title="Transfer/release preview requires transfer prestress effect",
            passed=any("Pe_transfer" in warning and "does not include transfer prestress" in warning for warning in transfer_no_ps_warnings),
            expected="warning requiring Pe_transfer / initial prestress effect",
            actual=list(transfer_no_ps_warnings),
            engineering_note="A release-stage prestressed girder check without transfer prestress is an engineering-review condition, not a clean PASS/FAIL case.",
        )
    )


    aashto_options = girder_sls_limit_profile_options("AASHTO LRFD Bridge", "Final service / Composite")
    aci_options = girder_sls_limit_profile_options("ACI 318", "Final service / Composite")
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT3.PROFILE_OPTIONS.VISIBLE",
            category=CATEGORY,
            title="Code-specific limit profile options are available",
            passed=(
                any("moderate" in option.label.lower() and option.tension_sqrt_fc_ratio == 0.50 for option in aashto_options)
                and any("Class U" in option.label and option.tension_sqrt_fc_ratio == 0.62 for option in aci_options)
                and any(option.tension_limit_mode == "No tension" for option in aashto_options)
            ),
            expected="AASHTO moderate/severe/no-tension and ACI Class U/T style profiles",
            actual={
                "AASHTO options": [option.label for option in aashto_options],
                "ACI options": [option.label for option in aci_options],
            },
            engineering_note="Commercial-grade preview checks must expose code/stage profile choices instead of one hidden generic ratio.",
        )
    )
    aashto_transfer = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Transfer / Release")
    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT3.AASHTO.TRANSFER.TENSION_CAP",
            category=CATEGORY,
            title="AASHTO transfer tension profile applies MPa cap",
            expected=1.38,
            actual=aashto_transfer.tension_allowable_MPa(fc),
            abs_tolerance=1.0e-12,
            units="MPa",
            engineering_note="Temporary release tension preview uses the smaller of the square-root expression and the explicit MPa cap when applicable.",
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

    transfer_profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Transfer / Release")
    final_profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Final service / Composite")
    deck_profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Deck casting / Pre-composite")
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT2.TRANSFER.STRENGTH_LABEL",
            category=CATEGORY,
            title="Transfer stage exposes f'ci strength basis",
            passed="f'ci" in transfer_profile.concrete_strength_label and "precast gross" in transfer_profile.recommended_section_basis.lower(),
            expected="f'ci + precast gross",
            actual=f"{transfer_profile.concrete_strength_label} / {transfer_profile.recommended_section_basis}",
            engineering_note="Transfer/release checks must not quietly use final service strength or composite section basis.",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="CODE.SLS.LIMIT2.FINAL.SERVICE.LOSSES",
            category=CATEGORY,
            title="Final service profile exposes Pe_eff after losses basis",
            passed="losses" in final_profile.prestress_force_basis.lower() and "staged" in final_profile.recommended_section_basis.lower(),
            expected="Pe_eff after losses + staged basis",
            actual=f"{final_profile.prestress_force_basis} / {final_profile.recommended_section_basis}",
            engineering_note="Final service stress checks must acknowledge prestress losses and staged section-basis effects.",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="CODE.SLS.LIMIT2.DECK_CASTING.COMP",
            category=CATEGORY,
            title="Deck casting preview compression profile is distinct",
            expected=0.55 * fc,
            actual=deck_profile.compression_limit_MPa(fc),
            abs_tolerance=1.0e-9,
            units="MPa",
            engineering_note="Deck casting/pre-composite profile is separate from transfer and final service preview profiles.",
        )
    )
    return results
