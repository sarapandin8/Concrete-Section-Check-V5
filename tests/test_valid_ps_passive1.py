from __future__ import annotations

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.verification.ps_passive_benchmarks import (
    PASS,
    passive_rc_plus_ps_input,
    run_valid_ps_passive_benchmark_pack,
)
from concrete_pmm_pro.verification.validation_framework import run_pmm_solver_validation_report


def test_passive_ps_input_has_zero_initial_prestress() -> None:
    model = passive_rc_plus_ps_input()
    element = model.prestress_elements[0]

    assert element.pe_eff_n == 0.0
    assert element.initial_stress_mpa is None
    assert element.initial_strain is None
    assert element.bonded is True


def test_passive_ps_solver_does_not_emit_active_prestress_warnings() -> None:
    result = run_rc_pmm_solver(passive_rc_plus_ps_input())
    messages = "\n".join(result.warnings).lower()

    assert "compression reversal" not in messages
    assert "reached fpu cap" not in messages
    assert "active prestress stress model" not in messages
    assert any("Passive bonded prestressing steel is included" in item for item in result.info)


def test_valid_ps_passive_benchmark_pack_passes() -> None:
    summary = run_valid_ps_passive_benchmark_pack()

    assert summary.checks
    assert summary.fail_count == 0
    assert summary.overall_status == PASS
    assert any(check.check_id == "SOLVER.PS.PASSIVE1.NO_ACTIVE_WARNINGS" and check.status == PASS for check in summary.checks)
    assert any(check.check_id == "SOLVER.PS.PASSIVE1.SIGNED_FORCE" and check.status == PASS for check in summary.checks)


def test_validation_report_includes_passive_ps_suite() -> None:
    report = run_pmm_solver_validation_report()

    assert report.ps_passive.checks
    assert report.ps_passive.fail_count == 0
    assert any(case.case_id == "SOLVER.PS.PASSIVE1" for case in report.validation_cases)
