from __future__ import annotations

from concrete_pmm_pro.validation.models import PASS, SKIPPED
from concrete_pmm_pro.validation.pmm_sanity import validate_pmm_solver_sanity


def test_pmm_sanity_validation_runs_or_skips_with_clear_status() -> None:
    results = validate_pmm_solver_sanity()

    assert results
    statuses = {result.status for result in results}
    assert statuses.issubset({PASS, SKIPPED})
    if SKIPPED in statuses:
        assert all(result.engineering_note for result in results if result.status == SKIPPED)
    else:
        assert all(result.status == PASS for result in results)


def test_pmm_sanity_checks_expected_invariants_when_solver_runs() -> None:
    results = validate_pmm_solver_sanity()
    if any(result.status == SKIPPED for result in results):
        return
    by_id = {result.case_id: result for result in results}

    assert by_id["PMM.SANITY.NON_EMPTY"].actual > 0
    assert by_id["PMM.SANITY.NO_NAN_INF"].status == PASS
    assert by_id["PMM.SANITY.POSITIVE_COMPRESSION"].status == PASS
    assert by_id["PMM.SANITY.MX_SYMMETRY"].status == PASS
    assert by_id["PMM.SANITY.MY_SYMMETRY"].status == PASS
    assert by_id["PMM.SANITY.SMALL_DEMAND_PASS"].status == PASS
    assert by_id["PMM.SANITY.LARGE_DEMAND_HIGHER"].status == PASS
