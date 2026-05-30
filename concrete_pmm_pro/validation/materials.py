"""Concrete material validation cases."""

from __future__ import annotations

import math

from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    DEFAULT_PRIMARY_CONCRETE_MATERIAL,
    aci_concrete_ec_mpa,
    c35_topping_material,
    c45_precast_material,
    default_concrete_materials,
)
from concrete_pmm_pro.core.models import ConcreteMaterial
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Materials"

ACI_EC_CASES_MPA = {
    "C28": (28.0, 24870.0),
    "C30": (30.0, 25743.0),
    "C35": (35.0, 27806.0),
    "C40": (40.0, 29725.0),
    "C45": (45.0, 31529.0),
    "C50": (50.0, 33234.0),
    "C55": (55.0, 34856.0),
    "C60": (60.0, 36407.0),
}


def validate_aci_ec_values() -> list[ValidationResult]:
    results: list[ValidationResult] = []
    for grade, (fc_mpa, expected_ec) in ACI_EC_CASES_MPA.items():
        results.append(
            numeric_validation_result(
                case_id=f"MAT.EC.{grade}",
                category=CATEGORY,
                title=f"ACI Ec for {grade}",
                expected=expected_ec,
                actual=aci_concrete_ec_mpa(fc_mpa),
                abs_tolerance=1.0,
                units="MPa",
                engineering_note="ACI normal-weight concrete Ec = 4700 * sqrt(fc_MPa).",
            )
        )
    return results


def validate_default_material_library() -> list[ValidationResult]:
    materials = {material.name: material for material in default_concrete_materials()}
    required = {
        DEFAULT_PRIMARY_CONCRETE_MATERIAL,
        DEFAULT_DECK_TOPPING_MATERIAL,
        "C28",
        "C30",
        "C35",
        "C40",
        "C45",
        "C50",
        "C55",
        "C60",
    }
    results = [
        boolean_validation_result(
            case_id="MAT.LIB.DEFAULTS",
            category=CATEGORY,
            title="Default concrete library contains required entries",
            passed=required.issubset(set(materials)),
            expected=sorted(required),
            actual=sorted(materials),
            engineering_note="MATERIAL1 defaults must be available without replacing legacy primary concrete.",
        )
    ]
    if DEFAULT_PRIMARY_CONCRETE_MATERIAL in materials:
        results.append(
            numeric_validation_result(
                case_id="MAT.LIB.C45_PRECAST.EC",
                category=CATEGORY,
                title="C45_PRECAST effective Ec",
                expected=4700.0 * math.sqrt(45.0),
                actual=materials[DEFAULT_PRIMARY_CONCRETE_MATERIAL].effective_Ec_MPa,
                abs_tolerance=1.0,
                units="MPa",
            )
        )
    if DEFAULT_DECK_TOPPING_MATERIAL in materials:
        results.append(
            numeric_validation_result(
                case_id="MAT.LIB.C35_TOPPING.EC",
                category=CATEGORY,
                title="C35_TOPPING effective Ec",
                expected=4700.0 * math.sqrt(35.0),
                actual=materials[DEFAULT_DECK_TOPPING_MATERIAL].effective_Ec_MPa,
                abs_tolerance=1.0,
                units="MPa",
            )
        )
    return results


def validate_material_effective_ec() -> list[ValidationResult]:
    auto = c45_precast_material()
    topping = c35_topping_material()
    manual = ConcreteMaterial(
        name="C45_MANUAL_EC",
        fc_MPa=45.0,
        Ec_method="Manual",
        Ec_MPa=33333.0,
    )
    legacy = ConcreteMaterial.model_validate({"name": "Legacy C35", "fc_MPa": 35.0})
    return [
        numeric_validation_result(
            case_id="MAT.EC.AUTO.PROPERTY",
            category=CATEGORY,
            title="ConcreteMaterial auto effective Ec",
            expected=4700.0 * math.sqrt(45.0),
            actual=auto.effective_Ec_MPa,
            abs_tolerance=1.0,
            units="MPa",
        ),
        numeric_validation_result(
            case_id="MAT.EC.TOPPING.PROPERTY",
            category=CATEGORY,
            title="ConcreteMaterial topping effective Ec",
            expected=4700.0 * math.sqrt(35.0),
            actual=topping.effective_Ec_MPa,
            abs_tolerance=1.0,
            units="MPa",
        ),
        numeric_validation_result(
            case_id="MAT.EC.MANUAL.OVERRIDE",
            category=CATEGORY,
            title="Manual Ec override is used",
            expected=33333.0,
            actual=manual.effective_Ec_MPa,
            abs_tolerance=0.0,
            units="MPa",
            engineering_note="A valid manual Ec_MPa must not silently fall back to ACI auto.",
        ),
        numeric_validation_result(
            case_id="MAT.EC.LEGACY.DEFAULTS",
            category=CATEGORY,
            title="Legacy ConcreteMaterial without Ec fields loads safely",
            expected=4700.0 * math.sqrt(35.0),
            actual=legacy.effective_Ec_MPa,
            abs_tolerance=1.0,
            units="MPa",
        ),
    ]


def validate_materials() -> list[ValidationResult]:
    return [
        *validate_aci_ec_values(),
        *validate_default_material_library(),
        *validate_material_effective_ec(),
    ]
