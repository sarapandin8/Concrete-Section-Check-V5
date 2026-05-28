from __future__ import annotations

from concrete_pmm_pro.verification.ps_stress_region_benchmarks import (
    PASS,
    run_valid_ps2_stress_region_benchmark_pack,
)
from concrete_pmm_pro.verification.validation_framework import run_pmm_solver_validation_report


def test_valid_ps2_benchmark_pack_runs_without_failures() -> None:
    summary = run_valid_ps2_stress_region_benchmark_pack()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status in {PASS, "WARNING"}
    assert any(check.check_id == "VALID.PS2.METADATA_SCHEMA" and check.status == PASS for check in summary.checks)
    assert any(check.check_id == "VALID.PS2.GOVERNING_TRACE_AVAILABLE" and check.status == PASS for check in summary.checks)
    assert any(check.check_id == "VALID.PS2.FPU_BACKGROUND_CLASSIFICATION" for check in summary.checks)


def test_valid_ps2_dataframe_is_report_ready() -> None:
    summary = run_valid_ps2_stress_region_benchmark_pack()
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Reference", "Solver", "Difference (%)", "Tolerance (%)"}.issubset(df.columns)


def test_valid_ps2_background_fpu_details_are_actionable() -> None:
    summary = run_valid_ps2_stress_region_benchmark_pack()
    check = next(item for item in summary.checks if item.check_id == "VALID.PS2.FPU_BACKGROUND_CLASSIFICATION")

    assert "global_fpu_point_count" in check.details
    assert "near_governing_fpu_point_count" in check.details
    assert check.details["global_fpu_point_count"] >= check.details["near_governing_fpu_point_count"]


def test_valid_ps2_compression_reversal_details_are_traceable() -> None:
    summary = run_valid_ps2_stress_region_benchmark_pack()
    check = next(item for item in summary.checks if item.check_id == "VALID.PS2.COMPRESSION_REVERSAL_REGION")

    assert "global_compression_reversal_point_count" in check.details
    assert "near_governing_compression_reversal_point_count" in check.details


def test_validation_report_includes_valid_ps2_execution() -> None:
    report = run_pmm_solver_validation_report()

    assert report.ps_stress_regions.checks
    assert report.ps_stress_regions.fail_count == 0
    assert any(case.case_id == "VALID.PS2" for case in report.validation_cases)
