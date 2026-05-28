"""Verification and validation helpers for Concrete PMM Pro."""

from concrete_pmm_pro.verification.rc_rectangular_benchmarks import RCBenchmarkSummary, run_valid_rc1_benchmark_pack
from concrete_pmm_pro.verification.validation_framework import (
    PMMSolverValidationReport,
    ValidationCaseSpec,
    build_pmm_solver_validation_matrix,
    run_pmm_solver_validation_report,
    validation_matrix_to_dataframe,
)

__all__ = [
    "PMMSolverValidationReport",
    "RCBenchmarkSummary",
    "ValidationCaseSpec",
    "build_pmm_solver_validation_matrix",
    "run_pmm_solver_validation_report",
    "run_valid_rc1_benchmark_pack",
    "validation_matrix_to_dataframe",
]
