from __future__ import annotations

import pytest

from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    DEFAULT_PRIMARY_CONCRETE_MATERIAL,
    default_concrete_materials,
)
from concrete_pmm_pro.core.models import ConcreteMaterial
from concrete_pmm_pro.validation.materials import ACI_EC_CASES_MPA, validate_materials
from concrete_pmm_pro.validation.models import PASS


def test_validation_material_cases_pass() -> None:
    results = validate_materials()

    assert results
    assert all(result.status == PASS for result in results)


@pytest.mark.parametrize("grade, expected", [(grade, expected) for grade, (_, expected) in ACI_EC_CASES_MPA.items()])
def test_validation_aci_ec_expected_values_are_present(grade: str, expected: float) -> None:
    result = next(item for item in validate_materials() if item.case_id == f"MAT.EC.{grade}")

    assert result.expected == pytest.approx(expected)
    assert result.actual == pytest.approx(expected, abs=1.0)


def test_validation_default_material_library_contains_required_grades() -> None:
    names = {material.name for material in default_concrete_materials()}

    assert DEFAULT_PRIMARY_CONCRETE_MATERIAL in names
    assert DEFAULT_DECK_TOPPING_MATERIAL in names
    assert {"C28", "C30", "C35", "C40", "C45", "C50", "C55", "C60"}.issubset(names)


def test_validation_manual_ec_override_uses_manual_value() -> None:
    material = ConcreteMaterial(name="Manual", fc_MPa=45.0, Ec_method="Manual", Ec_MPa=32100.0)

    assert material.effective_Ec_MPa == pytest.approx(32100.0)


def test_validation_old_concrete_material_without_ec_fields_still_works() -> None:
    material = ConcreteMaterial.model_validate({"name": "Old C35", "fc_MPa": 35.0, "ecu": 0.003})

    assert material.effective_Ec_MPa == pytest.approx(27805.6, abs=0.1)
