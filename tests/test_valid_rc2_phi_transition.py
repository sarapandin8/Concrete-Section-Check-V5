from __future__ import annotations

from concrete_pmm_pro.verification.rc_phi_transition_benchmarks import run_valid_rc2_phi_transition_benchmark_pack
from concrete_pmm_pro.verification.validation_framework import run_pmm_solver_validation_report


def test_valid_rc2_phi_transition_pack_runs_without_failures() -> None:
    summary = run_valid_rc2_phi_transition_benchmark_pack()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status in {"PASS", "WARNING"}
    assert any(check.check_id == "VALID.RC2.SOLVER_REGION_COVERAGE" for check in summary.checks)
    assert any(check.check_id == "VALID.RC2.SOLVER_PHI_MATCH" for check in summary.checks)


def test_valid_rc2_solver_samples_all_phi_regions() -> None:
    summary = run_valid_rc2_phi_transition_benchmark_pack()
    coverage = next(check for check in summary.checks if check.check_id == "VALID.RC2.SOLVER_REGION_COVERAGE")

    assert coverage.status == "PASS"
    assert coverage.details["condition_counts"]["compression-controlled"] > 0
    assert coverage.details["condition_counts"]["transition"] > 0
    assert coverage.details["condition_counts"]["tension-controlled"] > 0


def test_valid_rc2_solver_phi_matches_reference_helper() -> None:
    summary = run_valid_rc2_phi_transition_benchmark_pack()
    match = next(check for check in summary.checks if check.check_id == "VALID.RC2.SOLVER_PHI_MATCH")

    assert match.status == "PASS"
    assert match.details["mismatch_count"] == 0


def test_validation_report_includes_rc2_execution_status() -> None:
    report = run_pmm_solver_validation_report()

    assert report.rc_phi_transition.checks
    assert report.rc_phi_transition.overall_status in {"PASS", "WARNING"}
    assert any(case.case_id == "VALID.RC2" for case in report.validation_cases)
