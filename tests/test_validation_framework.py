from __future__ import annotations

from concrete_pmm_pro.verification.validation_framework import (
    build_pmm_solver_validation_matrix,
    run_pmm_solver_validation_report,
    validation_matrix_to_dataframe,
)


def test_validation_matrix_contains_core_solver_risk_areas() -> None:
    cases = build_pmm_solver_validation_matrix()
    case_ids = {case.case_id for case in cases}

    assert "VALID.RC.PO1" in case_ids
    assert "VALID.RC.MX1" in case_ids
    assert "VALID.PS.EPST1" in case_ids
    assert "VALID.PS.PO1" in case_ids
    assert "VALID.PS.STRESS1" in case_ids
    assert "VALID.PMM.DC1" in case_ids
    assert "VALID.NUM1" in case_ids
    assert "VALID.WARN1" in case_ids


def test_validation_matrix_marks_solver_root_causes_instead_of_hiding_warnings() -> None:
    cases = build_pmm_solver_validation_matrix()
    warnings = {warning for case in cases for warning in case.warnings_addressed}

    assert "fpu cap" in warnings
    assert "compression reversal" in warnings
    assert "directional D/C" in warnings
    assert "ACI axial cap" in warnings
    assert "NaN eps_t" in warnings
    assert "prototype wording" in warnings


def test_validation_matrix_has_actionable_next_steps_for_partial_cases() -> None:
    partial_cases = [case for case in build_pmm_solver_validation_matrix() if case.status == "partial"]

    assert partial_cases
    assert all(case.next_action for case in partial_cases)


def test_validation_matrix_dataframe_is_export_friendly() -> None:
    df = validation_matrix_to_dataframe()

    expected_columns = {
        "Case ID",
        "Title",
        "Category",
        "Coverage Status",
        "Purpose",
        "Acceptance",
        "Current Location",
        "Next Action",
        "Warnings Addressed",
    }
    assert expected_columns.issubset(set(df.columns))
    assert not df.empty


def test_pmm_solver_validation_report_runs_current_suites() -> None:
    report = run_pmm_solver_validation_report()

    assert report.validation_cases
    assert report.implemented_case_count >= 4
    assert report.partial_case_count >= 3
    assert report.hand_checks.checks
    assert report.pmm_checks.checks
    assert report.overall_execution_status in {"PASS", "WARNING"}
