"""Shared validation result models for engineering QA checks.

The validation package is intentionally pure Python.  It records expected and
actual behavior without changing solver, UI, or project data paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

ValidationStatus = Literal["PASS", "FAIL", "WARNING", "SKIPPED"]

PASS: ValidationStatus = "PASS"
FAIL: ValidationStatus = "FAIL"
WARNING: ValidationStatus = "WARNING"
SKIPPED: ValidationStatus = "SKIPPED"


@dataclass(frozen=True)
class ValidationResult:
    case_id: str
    category: str
    title: str
    status: ValidationStatus
    expected: Any = None
    actual: Any = None
    tolerance: Any = None
    difference: Any = None
    units: str | None = None
    engineering_note: str | None = None

    @property
    def is_pass(self) -> bool:
        return self.status == PASS

    @property
    def is_fail(self) -> bool:
        return self.status == FAIL

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "category": self.category,
            "title": self.title,
            "status": self.status,
            "expected": self.expected,
            "actual": self.actual,
            "tolerance": self.tolerance,
            "difference": self.difference,
            "units": self.units,
            "engineering_note": self.engineering_note,
        }


@dataclass(frozen=True)
class ValidationReport:
    results: list[ValidationResult]

    def summary(self) -> dict[str, Any]:
        passed = sum(1 for result in self.results if result.status == PASS)
        failed = sum(1 for result in self.results if result.status == FAIL)
        warnings = sum(1 for result in self.results if result.status == WARNING)
        skipped = sum(1 for result in self.results if result.status == SKIPPED)
        if failed:
            overall_status = "FAIL"
        elif warnings:
            overall_status = "PASS_WITH_WARNINGS"
        elif skipped:
            overall_status = "PASS_WITH_SKIPS"
        else:
            overall_status = "PASS"
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "skipped": skipped,
            "overall_status": overall_status,
            "failed_case_ids": [result.case_id for result in self.results if result.status == FAIL],
            "warning_case_ids": [result.case_id for result in self.results if result.status == WARNING],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "results": [result.to_dict() for result in self.results],
        }


def validation_summary(results: list[ValidationResult]) -> dict[str, Any]:
    return ValidationReport(results).summary()


def numeric_validation_result(
    *,
    case_id: str,
    category: str,
    title: str,
    expected: float,
    actual: float,
    abs_tolerance: float | None = None,
    rel_tolerance: float | None = None,
    units: str | None = None,
    engineering_note: str | None = None,
) -> ValidationResult:
    """Return PASS/FAIL for an engineering numeric comparison."""
    abs_tol = 0.0 if abs_tolerance is None else float(abs_tolerance)
    rel_tol = 0.0 if rel_tolerance is None else abs(float(expected)) * float(rel_tolerance)
    tolerance = max(abs_tol, rel_tol)
    difference = float(actual) - float(expected)
    status: ValidationStatus = PASS if math.isfinite(actual) and abs(difference) <= tolerance else FAIL
    return ValidationResult(
        case_id=case_id,
        category=category,
        title=title,
        status=status,
        expected=float(expected),
        actual=float(actual),
        tolerance=tolerance,
        difference=difference,
        units=units,
        engineering_note=engineering_note,
    )


def boolean_validation_result(
    *,
    case_id: str,
    category: str,
    title: str,
    passed: bool,
    expected: Any = True,
    actual: Any = None,
    units: str | None = None,
    engineering_note: str | None = None,
) -> ValidationResult:
    return ValidationResult(
        case_id=case_id,
        category=category,
        title=title,
        status=PASS if passed else FAIL,
        expected=expected,
        actual=actual if actual is not None else passed,
        units=units,
        engineering_note=engineering_note,
    )


def skipped_validation_result(
    *,
    case_id: str,
    category: str,
    title: str,
    engineering_note: str,
) -> ValidationResult:
    return ValidationResult(
        case_id=case_id,
        category=category,
        title=title,
        status=SKIPPED,
        engineering_note=engineering_note,
    )
