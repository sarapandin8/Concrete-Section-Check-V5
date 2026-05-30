"""Validation cases for transformed composite section property helpers."""

from __future__ import annotations

from concrete_pmm_pro.geometry.composite import (
    CompositeDeckInput,
    calculate_composite_transformed_section,
    calculate_composite_transformed_section_from_geometry,
    composite_deck_input_from_parameters,
    composite_deck_is_active,
)
from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result

CATEGORY = "Composite Section Properties"


def _rectangle_plus_deck_expected() -> dict[str, float]:
    b = 1000.0
    h = 450.0
    tslab = 100.0
    be_tr = 1000.0
    a_precast = b * h
    y_precast = 0.0
    ix_precast = b * h**3 / 12.0
    a_deck = be_tr * tslab
    y_deck = h / 2.0 + tslab / 2.0
    ix_deck = be_tr * tslab**3 / 12.0
    area = a_precast + a_deck
    ybar = (a_precast * y_precast + a_deck * y_deck) / area
    ix = ix_precast + a_precast * (y_precast - ybar) ** 2 + ix_deck + a_deck * (y_deck - ybar) ** 2
    top = h / 2.0 + tslab
    bottom = -h / 2.0
    return {
        "area": area,
        "cy": ybar,
        "ix": ix,
        "ctop": top - ybar,
        "cbottom": ybar - bottom,
    }


def validate_rectangle_composite_hand_check() -> list[ValidationResult]:
    summary = summarize_geometry(rectangle(1000.0, 450.0))
    deck = CompositeDeckInput(enabled=True, Tslab_mm=100.0, Be_mm=1000.0, Ebeam_MPa=30000.0, Edeck_MPa=30000.0)
    result = calculate_composite_transformed_section(summary, deck)
    expected = _rectangle_plus_deck_expected()
    return [
        numeric_validation_result(case_id="COMP.RECT.ACTIVE_AREA", category=CATEGORY, title="Rectangle + topping transformed area", expected=expected["area"], actual=result.area_mm2, abs_tolerance=1.0e-6, units="mm^2"),
        numeric_validation_result(case_id="COMP.RECT.CY", category=CATEGORY, title="Rectangle + topping centroid y", expected=expected["cy"], actual=result.centroid_y_mm, abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="COMP.RECT.IX", category=CATEGORY, title="Rectangle + topping Ix", expected=expected["ix"], actual=result.ix_mm4, abs_tolerance=1.0e-3, units="mm^4"),
        numeric_validation_result(case_id="COMP.RECT.CTOP", category=CATEGORY, title="Rectangle + topping ctop", expected=expected["ctop"], actual=result.c_top_mm, abs_tolerance=1.0e-9, units="mm"),
        numeric_validation_result(case_id="COMP.RECT.CBOTTOM", category=CATEGORY, title="Rectangle + topping cbottom", expected=expected["cbottom"], actual=result.c_bottom_mm, abs_tolerance=1.0e-9, units="mm"),
    ]


def validate_activation_guards() -> list[ValidationResult]:
    valid_params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
    }
    inactive_no_flag = dict(valid_params)
    inactive_no_flag.pop("composite_enabled")
    inactive_zero_slab = dict(valid_params, Tslab_mm=0.0)
    return [
        boolean_validation_result(case_id="COMP.ACTIVE.EXPLICIT", category=CATEGORY, title="Composite activation requires explicit valid metadata", passed=composite_deck_is_active(valid_params, member_type="beam_girder"), expected=True, actual=composite_deck_is_active(valid_params, member_type="beam_girder")),
        boolean_validation_result(case_id="COMP.ACTIVE.NO_FLAG", category=CATEGORY, title="Composite does not activate without explicit flag", passed=not composite_deck_is_active(inactive_no_flag, member_type="beam_girder"), expected=False, actual=composite_deck_is_active(inactive_no_flag, member_type="beam_girder")),
        boolean_validation_result(case_id="COMP.ACTIVE.COLUMN_GUARD", category=CATEGORY, title="Column/Pier workflow cannot activate composite deck", passed=not composite_deck_is_active(valid_params, member_type="column_pier_pmm"), expected=False, actual=composite_deck_is_active(valid_params, member_type="column_pier_pmm")),
        boolean_validation_result(case_id="COMP.ACTIVE.ZERO_SLAB", category=CATEGORY, title="Zero slab thickness disables composite deck", passed=not composite_deck_is_active(inactive_zero_slab, member_type="beam_girder"), expected=False, actual=composite_deck_is_active(inactive_zero_slab, member_type="beam_girder")),
    ]


def validate_modular_ratio_and_width() -> list[ValidationResult]:
    params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
    }
    deck = composite_deck_input_from_parameters(params, member_type="beam_girder")
    return [
        numeric_validation_result(case_id="COMP.N_RATIO.C35_C45", category=CATEGORY, title="C35/C45 modular ratio", expected=27806.0 / 31529.0, actual=deck.modular_ratio, abs_tolerance=1.0e-12),
        numeric_validation_result(case_id="COMP.BTR.C35_C45", category=CATEGORY, title="Transformed width equals n x Be", expected=(27806.0 / 31529.0) * 1000.0, actual=deck.transformed_width_mm, abs_tolerance=1.0e-9, units="mm"),
    ]




def validate_i_girder_composite_display_kernel() -> list[ValidationResult]:
    """Protect I-Girder transformed-section display without touching solver paths."""

    params = {
        "B1_mm": 800.0,
        "B2_mm": 500.0,
        "D1_mm": 1400.0,
        "D2_mm": 200.0,
        "D3_mm": 150.0,
        "D5_mm": 250.0,
        "D6_mm": 150.0,
        "T1_mm": 200.0,
        "T2_mm": 200.0,
        "C1_mm": 0.0,
    }
    geometry = default_registry.geometry("parametric_i_girder")(**params)
    deck_params = {
        "composite_enabled": True,
        "Tslab_mm": 200.0,
        "Be_mm": 2000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
    }
    deck = composite_deck_input_from_parameters(deck_params, member_type="beam_girder")
    composite = calculate_composite_transformed_section_from_geometry(geometry, deck)
    return [
        boolean_validation_result(
            case_id="COMP.IGIRDER.ACTIVE",
            category=CATEGORY,
            title="I-Girder composite metadata activates only with explicit valid deck/topping input",
            passed=deck.enabled and composite.active,
            expected=True,
            actual={"deck_enabled": deck.enabled, "composite_active": composite.active},
        ),
        boolean_validation_result(
            case_id="COMP.IGIRDER.AREA_INCREASE",
            category=CATEGORY,
            title="I-Girder transformed composite area exceeds precast gross area",
            passed=composite.area_mm2 > composite.precast_area_mm2,
            expected="A_tr > A_precast",
            actual={"A_tr": composite.area_mm2, "A_precast": composite.precast_area_mm2},
            units="mm^2",
        ),
        numeric_validation_result(
            case_id="COMP.IGIRDER.TOP_FIBER",
            category=CATEGORY,
            title="I-Girder composite top fiber includes deck/topping thickness",
            expected=700.0 + deck_params["Tslab_mm"],
            actual=composite.top_fiber_y_mm,
            abs_tolerance=1.0e-9,
            units="mm",
            engineering_note="Default I-Girder D1=1400 has precast top fiber at +700 mm.",
        ),
        numeric_validation_result(
            case_id="COMP.IGIRDER.BTR",
            category=CATEGORY,
            title="I-Girder transformed width equals n x Be",
            expected=deck_params["Be_mm"] * deck_params["Edeck_MPa"] / deck_params["Ebeam_MPa"],
            actual=composite.transformed_width_mm,
            abs_tolerance=1.0e-9,
            units="mm",
        ),
    ]


def validate_composite_section_properties() -> list[ValidationResult]:
    return [
        *validate_rectangle_composite_hand_check(),
        *validate_activation_guards(),
        *validate_modular_ratio_and_width(),
        *validate_i_girder_composite_display_kernel(),
    ]
