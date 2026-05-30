"""Validation guards for concrete material assignment and routing."""

from __future__ import annotations

import math

from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    DEFAULT_PRIMARY_CONCRETE_MATERIAL,
    c35_topping_material,
    c45_precast_material,
    default_concrete_materials,
    ensure_concrete_material_library,
)
from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Material Routing"


def _plank_metadata_values(be_mm: float = 1000.0) -> tuple[float, float, float, float]:
    primary = c45_precast_material()
    topping = c35_topping_material()
    ebeam = primary.effective_Ec_MPa
    edeck = topping.effective_Ec_MPa
    n_ratio = edeck / ebeam
    btransformed = n_ratio * be_mm
    return ebeam, edeck, n_ratio, btransformed


def validate_default_material_assignment() -> list[ValidationResult]:
    state = ensure_concrete_material_library(
        concrete_material=c45_precast_material(),
        concrete_materials=default_concrete_materials(),
        active_concrete_material_name=DEFAULT_PRIMARY_CONCRETE_MATERIAL,
        deck_topping_material_name=DEFAULT_DECK_TOPPING_MATERIAL,
    )
    return [
        boolean_validation_result(
            case_id="MAT.ROUTE.PRIMARY_DEFAULT",
            category=CATEGORY,
            title="Default primary concrete is C45_PRECAST",
            passed=state.active_concrete_material_name == DEFAULT_PRIMARY_CONCRETE_MATERIAL,
            expected=DEFAULT_PRIMARY_CONCRETE_MATERIAL,
            actual=state.active_concrete_material_name,
        ),
        boolean_validation_result(
            case_id="MAT.ROUTE.TOPPING_DEFAULT",
            category=CATEGORY,
            title="Default deck/topping concrete is C35_TOPPING",
            passed=state.deck_topping_material_name == DEFAULT_DECK_TOPPING_MATERIAL,
            expected=DEFAULT_DECK_TOPPING_MATERIAL,
            actual=state.deck_topping_material_name,
        ),
        boolean_validation_result(
            case_id="MAT.ROUTE.PRIMARY_SEPARATE_FROM_TOPPING",
            category=CATEGORY,
            title="Primary and topping assignments are separate",
            passed=state.active_material.name != state.deck_topping_material.name,
            expected="separate primary and deck/topping assignments",
            actual={"primary": state.active_material.name, "deck_topping": state.deck_topping_material.name},
        ),
    ]


def validate_plank_composite_metadata() -> list[ValidationResult]:
    ebeam, edeck, n_ratio, btransformed = _plank_metadata_values()
    expected_n = (4700.0 * math.sqrt(35.0)) / (4700.0 * math.sqrt(45.0))
    return [
        numeric_validation_result(
            case_id="MAT.ROUTE.PLANK.EBEAM",
            category=CATEGORY,
            title="Plank Ebeam uses primary/precast effective Ec",
            expected=4700.0 * math.sqrt(45.0),
            actual=ebeam,
            abs_tolerance=1.0,
            units="MPa",
        ),
        numeric_validation_result(
            case_id="MAT.ROUTE.PLANK.EDECK",
            category=CATEGORY,
            title="Plank Edeck uses deck/topping effective Ec",
            expected=4700.0 * math.sqrt(35.0),
            actual=edeck,
            abs_tolerance=1.0,
            units="MPa",
        ),
        numeric_validation_result(
            case_id="MAT.ROUTE.PLANK.N_RATIO",
            category=CATEGORY,
            title="Plank modular ratio n = Edeck/Ebeam",
            expected=expected_n,
            actual=n_ratio,
            rel_tolerance=1.0e-6,
            engineering_note="Deck/topping material affects transformed-width metadata only in MATERIAL1.",
        ),
        numeric_validation_result(
            case_id="MAT.ROUTE.PLANK.BTRANSFORMED",
            category=CATEGORY,
            title="Plank Btransformed = n * Be",
            expected=expected_n * 1000.0,
            actual=btransformed,
            rel_tolerance=1.0e-6,
            units="mm",
        ),
    ]


def validate_pmm_material_guard() -> list[ValidationResult]:
    primary = c45_precast_material()
    topping = c35_topping_material()
    analysis_input = AnalysisInput(
        section_geometry=rectangle(400.0, 600.0),
        concrete_material=primary,
    )
    explicit_topping_primary = AnalysisInput(
        section_geometry=rectangle(400.0, 600.0),
        concrete_material=topping,
    )
    return [
        boolean_validation_result(
            case_id="MAT.ROUTE.PMM_PRIMARY_ONLY",
            category=CATEGORY,
            title="PMM input receives primary concrete material",
            passed=analysis_input.concrete_material.name == DEFAULT_PRIMARY_CONCRETE_MATERIAL,
            expected=DEFAULT_PRIMARY_CONCRETE_MATERIAL,
            actual=analysis_input.concrete_material.name,
            engineering_note="Deck/topping concrete must not enter PMM unless selected as primary.",
        ),
        boolean_validation_result(
            case_id="MAT.ROUTE.TOPPING_NOT_IMPLICIT_PMM",
            category=CATEGORY,
            title="C35_TOPPING is not implicit PMM material",
            passed=analysis_input.concrete_material.name != DEFAULT_DECK_TOPPING_MATERIAL,
            expected=f"PMM material is not {DEFAULT_DECK_TOPPING_MATERIAL}",
            actual=analysis_input.concrete_material.name,
        ),
        boolean_validation_result(
            case_id="MAT.ROUTE.TOPPING_EXPLICIT_PRIMARY_ALLOWED",
            category=CATEGORY,
            title="C35_TOPPING can be PMM material only when explicit primary",
            passed=explicit_topping_primary.concrete_material.name == DEFAULT_DECK_TOPPING_MATERIAL,
            expected=DEFAULT_DECK_TOPPING_MATERIAL,
            actual=explicit_topping_primary.concrete_material.name,
        ),
    ]


def validate_material_routing() -> list[ValidationResult]:
    return [
        *validate_default_material_assignment(),
        *validate_plank_composite_metadata(),
        *validate_pmm_material_guard(),
    ]
