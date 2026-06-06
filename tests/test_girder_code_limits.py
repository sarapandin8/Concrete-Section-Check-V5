import math

import pytest

from concrete_pmm_pro.serviceability import (
    StressLimitInputRow,
    build_girder_sls_limit_profile,
    default_girder_sls_limit_profile,
    girder_service_limit_check_rows,
    run_girder_service_stress_limit_check,
    normalize_girder_sls_stage,
    girder_sls_limit_formula_summary,
    girder_sls_limit_profile_options,
    girder_sls_stage_basis_consistency_warnings,
)
from concrete_pmm_pro.validation.girder_code_limits import validate_girder_code_limits


def test_default_aashto_service_profile_computes_editable_limits() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Final service / Composite")

    assert profile.compression_limit_MPa(45.0) == pytest.approx(27.0)
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.50 * math.sqrt(45.0))
    assert "Confirm" in profile.limitation_note
    aci_service = default_girder_sls_limit_profile("ACI 318", "Final service / Composite")
    assert aci_service.tension_allowable_MPa(45.0) == pytest.approx(0.62 * math.sqrt(45.0))
    assert aci_service.tension_allowable_MPa(45.0) > profile.tension_allowable_MPa(45.0)


def test_default_aci_transfer_profile_is_distinct_stage_profile() -> None:
    profile = default_girder_sls_limit_profile("ACI 318", "Transfer / Release")

    assert profile.compression_limit_ratio == pytest.approx(0.60)
    assert profile.tension_sqrt_fc_ratio == pytest.approx(0.25)
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.25 * math.sqrt(45.0))


def test_girder_code_limit_check_respects_compression_negative_tension_positive() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Final service / Composite")
    result = run_girder_service_stress_limit_check(
        stresses=[StressLimitInputRow("Top", -5.0), StressLimitInputRow("Bottom", 1.0)],
        fc_MPa=45.0,
        profile=profile,
    )

    assert result.overall_status == "PASS"
    assert result.points[0].stress_type == "compression"
    assert result.points[1].stress_type == "tension"
    rows = girder_service_limit_check_rows(result)
    assert rows[0]["Status"] == "PASS"


def test_no_tension_profile_fails_positive_tension() -> None:
    profile = build_girder_sls_limit_profile(
        code="ACI 318",
        stage="User-defined",
        compression_limit_ratio=0.45,
        tension_limit_mode="No tension",
    )
    result = run_girder_service_stress_limit_check(
        stresses=[StressLimitInputRow("Bottom", 0.10)],
        fc_MPa=35.0,
        profile=profile,
    )

    assert result.overall_status == "FAIL"
    assert result.points[0].message.startswith("Tension stress violates")


def test_user_defined_tension_limit_and_overstress_behavior() -> None:
    profile = build_girder_sls_limit_profile(
        code="ACI 318",
        stage="User-defined",
        compression_limit_ratio=0.45,
        tension_limit_mode="User-defined",
        tension_limit_MPa=2.0,
    )

    ok = run_girder_service_stress_limit_check(
        stresses=[StressLimitInputRow("Bottom", 1.0)],
        fc_MPa=40.0,
        profile=profile,
    )
    fail = run_girder_service_stress_limit_check(
        stresses=[StressLimitInputRow("Bottom", 2.5)],
        fc_MPa=40.0,
        profile=profile,
    )

    assert ok.overall_status == "PASS"
    assert ok.points[0].utilization == pytest.approx(0.5)
    assert fail.overall_status == "FAIL"


def test_legacy_stage_labels_are_normalized_for_existing_sessions() -> None:
    assert normalize_girder_sls_stage("Transfer") == "Transfer / Release"
    assert normalize_girder_sls_stage("Service / Final") == "Final service / Composite"


def test_stage_aware_profiles_expose_strength_and_prestress_basis() -> None:
    transfer = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Transfer / Release")
    final = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Final service / Composite")

    assert "f'ci" in transfer.concrete_strength_label
    assert "transfer" in transfer.prestress_force_basis.lower()
    assert "precast gross" in transfer.recommended_section_basis.lower()
    assert "service" in final.concrete_strength_label.lower()
    assert "losses" in final.prestress_force_basis.lower()
    assert "staged" in final.recommended_section_basis.lower()


def test_deck_casting_profile_uses_pre_composite_guidance() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Deck casting / Pre-composite")

    assert profile.compression_limit_ratio == pytest.approx(0.55)
    assert "precast gross" in profile.recommended_section_basis.lower()
    assert "wet deck" in profile.stage_guidance.lower()



def test_code_specific_limit_profile_options_expose_realistic_defaults() -> None:
    aashto_final_options = girder_sls_limit_profile_options("AASHTO LRFD Bridge", "Final service / Composite")
    aci_final_options = girder_sls_limit_profile_options("ACI 318", "Final service / Composite")

    assert any("moderate" in option.label.lower() and option.tension_sqrt_fc_ratio == pytest.approx(0.50) for option in aashto_final_options)
    assert any("Class U" in option.label and option.tension_sqrt_fc_ratio == pytest.approx(0.62) for option in aci_final_options)
    assert any(option.tension_limit_mode == "No tension" for option in aashto_final_options)


def test_limit_profile_key_selects_aashto_severe_and_aci_class_t_profiles() -> None:
    aashto_severe = default_girder_sls_limit_profile(
        "AASHTO LRFD Bridge",
        "Final service / Composite",
        limit_profile_key="aashto_service_bonded_severe_full",
    )
    aci_class_t = default_girder_sls_limit_profile(
        "ACI 318",
        "Final service / Composite",
        limit_profile_key="aci_service_class_t_upper",
    )

    assert aashto_severe.tension_allowable_MPa(45.0) == pytest.approx(0.25 * math.sqrt(45.0))
    assert aci_class_t.tension_allowable_MPa(45.0) == pytest.approx(1.00 * math.sqrt(45.0))
    assert "Class T" in aci_class_t.limit_profile_label


def test_transfer_tension_cap_is_visible_in_formula_summary() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Transfer / Release")
    formula = girder_sls_limit_formula_summary(profile=profile, fc_MPa=45.0)

    assert profile.tension_limit_cap_MPa == pytest.approx(1.38)
    assert formula.tension_limit_MPa == pytest.approx(1.38)
    assert "min(" in formula.tension_formula
    assert "1.380" in formula.tension_substitution



def test_aci_transfer_end_zone_profile_and_trace_uses_050_root_fci_at_ends() -> None:
    from concrete_pmm_pro.serviceability import aci_transfer_end_zone_length_m, aci_transfer_tension_limit_trace

    profile = default_girder_sls_limit_profile(
        "ACI 318",
        "Transfer / Release",
        limit_profile_key="aci_transfer_end_zone_verified",
    )
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.25 * math.sqrt(45.0))
    length = aci_transfer_end_zone_length_m(strand_diameter_mm=12.7, basis="Transfer length 60db")
    trace = aci_transfer_tension_limit_trace(span_length_m=20.0, fci_MPa=45.0, end_zone_length_m=length)

    assert length == pytest.approx(0.762)
    assert trace.interior_limit_MPa == pytest.approx(0.25 * math.sqrt(45.0))
    assert trace.end_zone_limit_MPa == pytest.approx(0.50 * math.sqrt(45.0))
    assert trace.y_MPa[0] == pytest.approx(trace.end_zone_limit_MPa)
    assert trace.y_MPa[2] == pytest.approx(trace.interior_limit_MPa)


def test_tension_limit_guidance_selects_aci_transfer_end_zone_only_when_verified() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    verified = recommend_girder_tension_limit_profile(
        code="ACI 318",
        stage="Transfer / Release",
        bonded_tension_reinforcement_verified=True,
    )
    unverified = recommend_girder_tension_limit_profile(
        code="ACI 318",
        stage="Transfer / Release",
        bonded_tension_reinforcement_verified=None,
    )

    assert verified.recommended_profile_key == "aci_transfer_end_zone_verified"
    assert verified.status == "OK"
    assert unverified.recommended_profile_key == "aci_transfer_basic"
    assert unverified.status == "REVIEW"



def test_aashto_construction_verified_bonded_reinforcement_uses_higher_tension_limit() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    guidance = recommend_girder_tension_limit_profile(
        code="AASHTO LRFD Bridge",
        stage="Deck casting / Pre-composite",
        bonded_tension_reinforcement_verified=True,
    )
    profile = default_girder_sls_limit_profile(
        "AASHTO LRFD Bridge",
        "Deck casting / Pre-composite",
        limit_profile_key=guidance.recommended_profile_key,
    )

    assert guidance.recommended_profile_key == "aashto_deck_precomp_bonded_aux"
    assert guidance.status == "OK"
    assert profile.tension_limit_cap_MPa is None
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.58 * math.sqrt(45.0))


def test_aashto_construction_unverified_reinforcement_keeps_capped_tension_limit() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    guidance = recommend_girder_tension_limit_profile(
        code="AASHTO LRFD Bridge",
        stage="Deck casting / Pre-composite",
        bonded_tension_reinforcement_verified=None,
    )
    profile = default_girder_sls_limit_profile(
        "AASHTO LRFD Bridge",
        "Deck casting / Pre-composite",
        limit_profile_key=guidance.recommended_profile_key,
    )

    assert guidance.recommended_profile_key == "aashto_deck_precomp_user"
    assert guidance.status == "REVIEW"
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(1.38)
    assert profile.tension_limit_cap_MPa == pytest.approx(1.38)

def test_girder_code_limit_validation_suite_passes() -> None:
    results = validate_girder_code_limits()

    assert results
    assert {result.status for result in results} == {"PASS"}


def test_limit_formula_summary_shows_code_stage_formula_text() -> None:
    profile = default_girder_sls_limit_profile("ACI 318", "Transfer / Release")
    formula = girder_sls_limit_formula_summary(profile=profile, fc_MPa=45.0)

    assert "0.600" in formula.compression_formula
    assert "f'ci" in formula.compression_formula
    assert "27.000 MPa" in formula.compression_substitution
    assert "0.250" in formula.tension_formula
    assert "1.677 MPa" in formula.tension_substitution
    assert formula.profile_note.startswith("ACI 318")


def test_stage_basis_consistency_warns_for_transfer_with_final_composite_row() -> None:
    warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Transfer / Release",
        section_basis_label="Composite transformed section",
        load_stage="Final service",
        load_component="Total SLS resultant",
    )

    assert any("Stage mismatch" in warning for warning in warnings)
    assert any("precast gross" in warning.lower() for warning in warnings)
    assert any("Total SLS resultant" in warning for warning in warnings)


def test_stage_basis_consistency_accepts_final_service_composite_live_load() -> None:
    warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Final service / Composite",
        section_basis_label="Composite transformed section",
        load_stage="Final service",
        load_component="LL+IM",
    )

    assert warnings == ()


def test_transfer_stage_requires_transfer_prestress_effect_for_preview_status() -> None:
    warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Transfer / Release",
        section_basis_label="Precast gross section",
        load_stage="Transfer / Release",
        load_component="Girder self-weight",
        stress_includes_prestress=False,
    )

    assert any("Pe_transfer" in warning for warning in warnings)
    assert any("does not include transfer prestress" in warning for warning in warnings)


def test_transfer_stage_warns_when_pe_eff_after_losses_is_used_as_release_force() -> None:
    warnings = girder_sls_stage_basis_consistency_warnings(
        profile_stage="Transfer / Release",
        section_basis_label="Precast gross section",
        load_stage="Transfer / Release",
        load_component="Transfer prestress + self-weight",
        stress_includes_prestress=True,
        prestress_force_state="Pe_eff after losses",
    )

    assert any("Pe_transfer" in warning for warning in warnings)
    assert any("final Pe_eff after losses" in warning for warning in warnings)


def test_tension_limit_guidance_selects_aashto_transfer_aux_when_verified() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    guidance = recommend_girder_tension_limit_profile(
        code="AASHTO LRFD Bridge",
        stage="Transfer / Release",
        bonded_tension_reinforcement_verified=True,
    )

    assert guidance.recommended_profile_key == "aashto_transfer_bonded_aux"
    assert guidance.status == "OK"


def test_tension_limit_guidance_keeps_review_for_unverified_aashto_moderate_service() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    guidance = recommend_girder_tension_limit_profile(
        code="AASHTO LRFD Bridge",
        stage="Final service / Composite",
        bonded_tension_reinforcement_verified=None,
        exposure_condition="Moderate exposure / bonded",
    )

    assert guidance.recommended_profile_key == "aashto_service_bonded_moderate_full"
    assert guidance.status == "REVIEW"
    assert any("assumes bonded" in warning for warning in guidance.warnings)


def test_tension_limit_guidance_selects_aci_class_t_but_requires_review_when_not_verified() -> None:
    from concrete_pmm_pro.serviceability import recommend_girder_tension_limit_profile

    guidance = recommend_girder_tension_limit_profile(
        code="ACI 318",
        stage="Final service / Composite",
        bonded_tension_reinforcement_verified=False,
        aci_service_class="Class T",
    )

    assert guidance.recommended_profile_key == "aci_service_class_t_upper"
    assert guidance.status == "REVIEW"
    assert any("Class T" in warning for warning in guidance.warnings)


def test_aci_construction_cip_pour_uses_modulus_of_rupture_tension_limit() -> None:
    profile = default_girder_sls_limit_profile("ACI 318", "Deck casting / Pre-composite")
    formula = girder_sls_limit_formula_summary(profile=profile, fc_MPa=45.0)

    assert profile.limit_profile_key == "aci_deck_precomp_cip_pour_fr"
    assert profile.compression_limit_ratio == pytest.approx(0.60)
    assert profile.tension_sqrt_fc_ratio == pytest.approx(0.62)
    assert profile.tension_limit_cap_MPa is None
    assert profile.compression_limit_MPa(45.0) == pytest.approx(27.0)
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.62 * math.sqrt(45.0))
    assert "0.620" in formula.tension_formula
    assert "4.159 MPa" in formula.tension_substitution
    assert "CIP pour" in profile.limit_profile_label
