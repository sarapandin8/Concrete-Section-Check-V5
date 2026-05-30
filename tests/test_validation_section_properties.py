from __future__ import annotations

import pytest

from concrete_pmm_pro.validation.models import PASS
from concrete_pmm_pro.validation.section_properties import (
    validate_circle_properties,
    validate_exterior_plank_signature,
    validate_hollow_rectangle_properties,
    validate_i_girder_signature,
    validate_interior_plank_signature,
    validate_rectangle_properties,
    validate_section_properties,
)


def _assert_all_pass(results) -> None:
    assert results
    assert all(result.status == PASS for result in results), [result.to_dict() for result in results if result.status != PASS]


def test_rectangle_hand_calculation_validation_passes() -> None:
    _assert_all_pass(validate_rectangle_properties())


def test_circle_hand_calculation_validation_passes() -> None:
    _assert_all_pass(validate_circle_properties())


def test_hollow_rectangle_hand_calculation_validation_passes() -> None:
    _assert_all_pass(validate_hollow_rectangle_properties())


def test_interior_plank_accepted_benchmark_validation_passes() -> None:
    results = validate_interior_plank_signature()

    _assert_all_pass(results)
    by_id = {result.case_id: result for result in results}
    assert by_id["SEC.PLANK.INT.AREA"].actual == 405650.0
    assert by_id["SEC.PLANK.INT.CY_BOTTOM"].actual == pytest.approx(220.92, abs=0.05)


def test_exterior_plank_geometry_sanity_validation_passes() -> None:
    _assert_all_pass(validate_exterior_plank_signature())


def test_i_girder_geometry_sanity_validation_passes() -> None:
    _assert_all_pass(validate_i_girder_signature())


def test_section_property_validation_suite_passes() -> None:
    _assert_all_pass(validate_section_properties())
