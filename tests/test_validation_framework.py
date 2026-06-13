from __future__ import annotations

from concrete_pmm_pro.verification.validation_framework import (
    build_pmm_solver_validation_matrix,
    run_pmm_solver_validation_report,
    validation_matrix_to_dataframe,
)
from concrete_pmm_pro.validation import run_all_validations
from concrete_pmm_pro.validation.models import (
    FAIL,
    PASS,
    SKIPPED,
    WARNING,
    ValidationReport,
    ValidationResult,
    boolean_validation_result,
    numeric_validation_result,
    validation_summary,
)


def test_validation_matrix_contains_core_solver_risk_areas() -> None:
    cases = build_pmm_solver_validation_matrix()
    case_ids = {case.case_id for case in cases}

    assert "VALID.RC.PO1" in case_ids
    assert "VALID.RC.MX1" in case_ids
    assert "VALID.PS.EPST1" in case_ids
    assert "VALID.PS.PO1" in case_ids
    assert "QA.PO1" in case_ids
    assert "SOLVER.PS.COMP1" in case_ids
    assert "PMM.BENCH.PS.CUSTOM1" in case_ids
    assert "VALID.PMM.DC1" in case_ids
    assert "PMM.FINAL.RC1.SCOPE" in case_ids
    assert "PMM.FINAL.RC1.UNIAXIAL.REF" in case_ids
    assert "PMM.FINAL.RC1.BIAXIAL.REF" in case_ids
    assert "PMM.FINAL.RC1.DC.NO_OVERESTIMATE" in case_ids
    assert "PMM.FINAL.RC1.STATUS.READINESS1" in case_ids
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
    assert "production-preview readiness" in warnings
    assert "custom shape PMM" in warnings
    assert "final certification guard" in warnings


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
    assert report.po_axial_cap.checks
    assert report.pmm_final_rc1.checks
    assert report.pmm_final_rc1.overall_status in {"PASS", "WARNING"}
    assert report.overall_execution_status in {"PASS", "WARNING"}


def test_validation_result_structure_is_export_friendly() -> None:
    result = ValidationResult(
        case_id="QA.TEST.1",
        category="Framework",
        title="Result structure",
        status=PASS,
        expected=1.0,
        actual=1.0,
        tolerance=0.0,
        difference=0.0,
        units="unit",
        engineering_note="note",
    )

    data = result.to_dict()

    assert data["case_id"] == "QA.TEST.1"
    assert data["status"] == PASS
    assert data["expected"] == 1.0
    assert data["engineering_note"] == "note"


def test_validation_summary_counts_statuses() -> None:
    results = [
        ValidationResult("QA.PASS", "Framework", "Pass", PASS),
        ValidationResult("QA.FAIL", "Framework", "Fail", FAIL),
        ValidationResult("QA.WARNING", "Framework", "Warning", WARNING),
        ValidationResult("QA.SKIP", "Framework", "Skip", SKIPPED),
    ]

    summary = validation_summary(results)

    assert summary["total"] == 4
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["warnings"] == 1
    assert summary["skipped"] == 1
    assert summary["overall_status"] == "FAIL"
    assert summary["failed_case_ids"] == ["QA.FAIL"]
    assert summary["warning_case_ids"] == ["QA.WARNING"]


def test_numeric_and_boolean_helpers_set_expected_statuses() -> None:
    numeric_pass = numeric_validation_result(
        case_id="QA.NUM.PASS",
        category="Framework",
        title="Numeric pass",
        expected=100.0,
        actual=100.5,
        abs_tolerance=1.0,
    )
    numeric_fail = numeric_validation_result(
        case_id="QA.NUM.FAIL",
        category="Framework",
        title="Numeric fail",
        expected=100.0,
        actual=102.0,
        abs_tolerance=1.0,
    )
    boolean_pass = boolean_validation_result(
        case_id="QA.BOOL.PASS",
        category="Framework",
        title="Boolean pass",
        passed=True,
    )

    assert numeric_pass.status == PASS
    assert numeric_fail.status == FAIL
    assert boolean_pass.status == PASS


def test_run_all_validations_returns_structured_report() -> None:
    report = run_all_validations()

    assert isinstance(report, ValidationReport)
    assert report.results
    assert report.summary()["total"] == len(report.results)
    assert report.summary()["overall_status"] in {"PASS", "PASS_WITH_WARNINGS", "PASS_WITH_SKIPS", "FAIL"}
