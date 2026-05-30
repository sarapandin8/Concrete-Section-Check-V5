from __future__ import annotations

import pytest

from concrete_pmm_pro.validation.models import PASS
from concrete_pmm_pro.validation.prestress_guards import (
    validate_breaking_load_is_reference_only,
    validate_duct_and_strand_count_guards,
    validate_pe_eff_fpe_relationship,
    validate_prestress_guards,
)


def _assert_all_pass(results) -> None:
    assert results
    assert all(result.status == PASS for result in results), [result.to_dict() for result in results if result.status != PASS]


def test_prestress_pe_eff_fpe_relationship_guard_passes() -> None:
    results = validate_pe_eff_fpe_relationship()

    _assert_all_pass(results)
    by_id = {result.case_id: result for result in results}
    assert by_id["PS.GUARD.PE_FROM_FPE"].actual == pytest.approx(1848.0)
    assert by_id["PS.GUARD.FPE_FROM_PE"].actual == pytest.approx(1100.0)


def test_breaking_load_remains_reference_only_guard_passes() -> None:
    _assert_all_pass(validate_breaking_load_is_reference_only())


def test_duct_and_strand_count_guards_pass() -> None:
    _assert_all_pass(validate_duct_and_strand_count_guards())


def test_prestress_guard_validation_suite_passes() -> None:
    _assert_all_pass(validate_prestress_guards())
