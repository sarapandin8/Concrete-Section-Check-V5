"""Validation runner for Concrete PMM Pro QA checks."""

from __future__ import annotations

from collections.abc import Callable

from concrete_pmm_pro.validation.composite_section import validate_composite_section_properties
from concrete_pmm_pro.validation.material_routing import validate_material_routing
from concrete_pmm_pro.validation.materials import validate_materials
from concrete_pmm_pro.validation.models import ValidationReport, ValidationResult
from concrete_pmm_pro.validation.pmm_sanity import validate_pmm_solver_sanity
from concrete_pmm_pro.validation.prestress_guards import validate_prestress_guards
from concrete_pmm_pro.validation.section_properties import validate_section_properties

ValidationSuite = Callable[[], list[ValidationResult]]


def validation_suites() -> list[ValidationSuite]:
    return [
        validate_materials,
        validate_section_properties,
        validate_composite_section_properties,
        validate_material_routing,
        validate_pmm_solver_sanity,
        validate_prestress_guards,
    ]


def run_all_validations() -> ValidationReport:
    results: list[ValidationResult] = []
    for suite in validation_suites():
        results.extend(suite())
    return ValidationReport(results)
