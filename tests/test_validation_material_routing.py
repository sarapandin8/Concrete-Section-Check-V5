from __future__ import annotations

import pytest

from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    DEFAULT_PRIMARY_CONCRETE_MATERIAL,
)
from concrete_pmm_pro.validation.material_routing import (
    validate_default_material_assignment,
    validate_material_routing,
    validate_plank_composite_metadata,
    validate_pmm_material_guard,
)
from concrete_pmm_pro.validation.models import PASS


def _assert_all_pass(results) -> None:
    assert results
    assert all(result.status == PASS for result in results), [result.to_dict() for result in results if result.status != PASS]


def test_default_material_assignment_keeps_primary_and_topping_separate() -> None:
    results = validate_default_material_assignment()
    by_id = {result.case_id: result for result in results}

    _assert_all_pass(results)
    assert by_id["MAT.ROUTE.PRIMARY_DEFAULT"].actual == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert by_id["MAT.ROUTE.TOPPING_DEFAULT"].actual == DEFAULT_DECK_TOPPING_MATERIAL


def test_plank_default_material_metadata_calculates_n_and_btransformed() -> None:
    results = validate_plank_composite_metadata()
    by_id = {result.case_id: result for result in results}

    _assert_all_pass(results)
    assert by_id["MAT.ROUTE.PLANK.N_RATIO"].actual == pytest.approx(0.8819, abs=0.001)
    assert by_id["MAT.ROUTE.PLANK.BTRANSFORMED"].actual == pytest.approx(by_id["MAT.ROUTE.PLANK.N_RATIO"].actual * 1000.0)


def test_deck_topping_does_not_become_pmm_material_unless_explicit_primary() -> None:
    results = validate_pmm_material_guard()

    _assert_all_pass(results)
    by_id = {result.case_id: result for result in results}
    assert by_id["MAT.ROUTE.PMM_PRIMARY_ONLY"].actual == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert by_id["MAT.ROUTE.TOPPING_NOT_IMPLICIT_PMM"].actual == DEFAULT_PRIMARY_CONCRETE_MATERIAL
    assert by_id["MAT.ROUTE.TOPPING_EXPLICIT_PRIMARY_ALLOWED"].actual == DEFAULT_DECK_TOPPING_MATERIAL


def test_material_routing_validation_suite_passes() -> None:
    _assert_all_pass(validate_material_routing())
