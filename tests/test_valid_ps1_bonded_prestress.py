from __future__ import annotations

from concrete_pmm_pro.verification.ps_bonded_benchmarks import (
    PASS,
    benchmark_bonded_strand,
    ps_only_input,
    rc_plus_ps_input,
    reference_ps_initial_strain,
    reference_ps_initial_stress_mpa,
    run_valid_ps1_bonded_prestress_benchmark_pack,
)
from concrete_pmm_pro.verification.validation_framework import run_pmm_solver_validation_report


def test_valid_ps1_inputs_are_prestress_benchmark_models() -> None:
    ps_only = ps_only_input()
    rcps = rc_plus_ps_input()

    assert not ps_only.rebars
    assert len(ps_only.prestress_elements) == 1
    assert ps_only.prestress_elements[0].bonded is True
    assert len(rcps.rebars) == 4
    assert len(rcps.prestress_elements) == 1
    assert rcps.settings.include_prestress is True


def test_valid_ps1_pe_eff_reference_conversion() -> None:
    element = benchmark_bonded_strand()

    assert reference_ps_initial_stress_mpa(element) == 1000.0
    assert reference_ps_initial_strain(element) == 1000.0 / 195000.0


def test_valid_ps1_benchmark_pack_runs_without_failures() -> None:
    summary = run_valid_ps1_bonded_prestress_benchmark_pack()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status in {PASS, "WARNING"}
    assert any(check.check_id == "VALID.PS1.PS_ONLY_EPST" and check.status == PASS for check in summary.checks)
    assert any(check.check_id == "VALID.PS1.PO_INCLUDES_APS" and check.status == PASS for check in summary.checks)
    assert any(check.check_id == "VALID.PS1.NUMERIC_SCHEMA" and check.status == PASS for check in summary.checks)


def test_valid_ps1_dataframe_is_report_ready() -> None:
    summary = run_valid_ps1_bonded_prestress_benchmark_pack()
    df = summary.to_dataframe()

    assert not df.empty
    assert {"Check ID", "Title", "Status", "Reference", "Solver", "Difference (%)", "Tolerance (%)"}.issubset(df.columns)


def test_validation_report_includes_valid_ps1_execution() -> None:
    report = run_pmm_solver_validation_report()

    assert report.ps_benchmarks.checks
    assert report.ps_benchmarks.fail_count == 0
    assert any(case.case_id == "VALID.PS1" for case in report.validation_cases)
