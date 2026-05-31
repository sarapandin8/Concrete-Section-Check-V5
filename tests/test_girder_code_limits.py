import math

import pytest

from concrete_pmm_pro.serviceability import (
    StressLimitInputRow,
    build_girder_sls_limit_profile,
    default_girder_sls_limit_profile,
    girder_service_limit_check_rows,
    run_girder_service_stress_limit_check,
)
from concrete_pmm_pro.validation.girder_code_limits import validate_girder_code_limits


def test_default_aashto_service_profile_computes_editable_limits() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Service / Final")

    assert profile.compression_limit_MPa(45.0) == pytest.approx(20.25)
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.50 * math.sqrt(45.0))
    assert "Verify" in profile.limitation_note


def test_default_aci_transfer_profile_is_distinct_stage_profile() -> None:
    profile = default_girder_sls_limit_profile("ACI 318", "Transfer")

    assert profile.compression_limit_ratio == pytest.approx(0.60)
    assert profile.tension_sqrt_fc_ratio == pytest.approx(0.25)
    assert profile.tension_allowable_MPa(45.0) == pytest.approx(0.25 * math.sqrt(45.0))


def test_girder_code_limit_check_respects_compression_negative_tension_positive() -> None:
    profile = default_girder_sls_limit_profile("AASHTO LRFD Bridge", "Service / Final")
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


def test_girder_code_limit_validation_suite_passes() -> None:
    results = validate_girder_code_limits()

    assert results
    assert {result.status for result in results} == {"PASS"}
