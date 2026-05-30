import pytest

from concrete_pmm_pro.geometry.effective_width import (
    EffectiveWidthInput,
    calculate_aashto_effective_slab_width,
)
from concrete_pmm_pro.validation.effective_width import validate_effective_width


def test_interior_effective_width_spacing_governs_for_default_plank_metadata():
    result = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=12000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=1000.0,
            top_width_mm=900.0,
            position="interior",
        )
    )

    assert result.effective_width_mm == pytest.approx(1000.0)
    assert result.governing_limit == "Girder spacing S"
    assert {candidate.label for candidate in result.candidates} == {"L/4", "Girder spacing S", "Top width + 16Tslab"}


def test_interior_effective_width_local_slab_limit_can_govern():
    result = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=20000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=4000.0,
            top_width_mm=900.0,
            position="interior",
        )
    )

    assert result.effective_width_mm == pytest.approx(2500.0)
    assert result.governing_limit == "Top width + 16Tslab"


def test_interior_effective_width_span_limit_can_govern():
    result = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=8000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=5000.0,
            top_width_mm=1000.0,
            position="interior",
        )
    )

    assert result.effective_width_mm == pytest.approx(2000.0)
    assert result.governing_limit == "L/4"


def test_exterior_effective_width_uses_overhang_and_tributary_guard():
    result = calculate_aashto_effective_slab_width(
        EffectiveWidthInput(
            span_length_mm=12000.0,
            slab_thickness_mm=100.0,
            girder_spacing_mm=2000.0,
            top_width_mm=500.0,
            position="exterior",
            deck_overhang_mm=600.0,
        )
    )

    assert result.effective_width_mm == pytest.approx(1600.0)
    assert result.governing_limit == "Exterior tributary width"
    assert result.position == "exterior"


def test_effective_width_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="span_length"):
        calculate_aashto_effective_slab_width(
            EffectiveWidthInput(
                span_length_mm=0.0,
                slab_thickness_mm=100.0,
                girder_spacing_mm=1000.0,
                top_width_mm=900.0,
            )
        )


def test_effective_width_validation_suite_passes():
    results = validate_effective_width()
    assert results
    assert all(result.status == "PASS" for result in results)
