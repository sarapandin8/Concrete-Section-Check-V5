"""Validation cases for AASHTO.BE1 effective slab-width helper."""

from __future__ import annotations

from concrete_pmm_pro.geometry.effective_width import EffectiveWidthInput, calculate_aashto_effective_slab_width
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Effective Slab Width"


def validate_effective_width() -> list[ValidationResult]:
    results: list[ValidationResult] = []

    interior_spacing = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=12000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=1000.0,
            top_width_mm=900.0,
            position="interior",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="BE.INT.SPACING",
            category=CATEGORY,
            title="Interior effective width controlled by spacing",
            expected=1000.0,
            actual=interior_spacing.effective_width_mm,
            abs_tolerance=1.0e-9,
            units="mm",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="BE.INT.SPACING_GOV",
            category=CATEGORY,
            title="Interior spacing governing label",
            passed=interior_spacing.governing_limit == "Girder spacing S",
            expected="Girder spacing S",
            actual=interior_spacing.governing_limit,
        )
    )

    interior_local = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=20000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=4000.0,
            top_width_mm=900.0,
            position="interior",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="BE.INT.LOCAL",
            category=CATEGORY,
            title="Interior effective width controlled by top width plus 16Tslab",
            expected=2500.0,
            actual=interior_local.effective_width_mm,
            abs_tolerance=1.0e-9,
            units="mm",
        )
    )

    interior_span = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=8000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=5000.0,
            top_width_mm=1000.0,
            position="interior",
        )
    )
    results.append(
        numeric_validation_result(
            case_id="BE.INT.SPAN",
            category=CATEGORY,
            title="Interior effective width controlled by span/4",
            expected=2000.0,
            actual=interior_span.effective_width_mm,
            abs_tolerance=1.0e-9,
            units="mm",
        )
    )

    exterior = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=12000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=2000.0,
            top_width_mm=500.0,
            position="exterior",
            deck_overhang_mm=600.0,
        )
    )
    # L/4 = 3000, tributary = 1600, side-limited = 500 + 600 + min(750,800) = 1850
    results.append(
        numeric_validation_result(
            case_id="BE.EXT.TRIBUTARY",
            category=CATEGORY,
            title="Exterior effective width controlled by tributary width",
            expected=1600.0,
            actual=exterior.effective_width_mm,
            abs_tolerance=1.0e-9,
            units="mm",
        )
    )
    results.append(
        boolean_validation_result(
            case_id="BE.EXT.POSITION",
            category=CATEGORY,
            title="Exterior helper preserves member position",
            passed=exterior.position == "exterior",
            expected="exterior",
            actual=exterior.position,
        )
    )

    return results
