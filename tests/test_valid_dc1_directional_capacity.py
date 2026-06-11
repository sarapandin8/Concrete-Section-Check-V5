from __future__ import annotations

from concrete_pmm_pro.verification.dc_directional_benchmarks import run_valid_dc1_directional_benchmark_pack


def test_valid_dc1_directional_benchmark_pack_passes() -> None:
    summary = run_valid_dc1_directional_benchmark_pack()

    assert summary.overall_status == "PASS"
    assert summary.fail_count == 0
    assert summary.pass_count == 5


def test_valid_dc1_summary_dataframe_contains_expected_checks() -> None:
    summary = run_valid_dc1_directional_benchmark_pack()
    df = summary.to_dataframe()

    assert set(df["Check ID"]) == {
        "SOLVER.PMM.DC1.RECT_X_RAY",
        "SOLVER.PMM.DC1.RECT_DIAGONAL_RAY",
        "SOLVER.PMM.DC1.DC_SUMMARY_PRIMARY",
        "SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY",
        "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE",
    }


def test_valid_dc1_includes_rc_specific_no_overestimate_guard() -> None:
    summary = run_valid_dc1_directional_benchmark_pack()
    check = next(item for item in summary.checks if item.check_id == "SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE")

    assert check.status == "PASS"
    assert check.solver_value is not None
    assert check.reference_value is not None
    assert check.solver_value <= check.reference_value * 1.0001
    assert check.details["capacity_method"] == "slice_envelope"
    assert check.details["envelope_method"] == "polar_max"
    assert check.details["used_convex_hull"] is False
    assert check.details["used_fallback"] is False
    assert check.details["estimate_method"] == "slice_envelope_ray"
