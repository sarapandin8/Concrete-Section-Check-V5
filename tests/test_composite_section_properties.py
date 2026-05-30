import math

import pytest

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
from concrete_pmm_pro.validation.composite_section import validate_composite_section_properties


def test_composite_activation_requires_explicit_flag_and_beam_workflow():
    params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
    }
    assert composite_deck_is_active(params, member_type="beam_girder")
    assert not composite_deck_is_active({k: v for k, v in params.items() if k != "composite_enabled"}, member_type="beam_girder")
    assert not composite_deck_is_active(params, member_type="column_pier_pmm")
    assert not composite_deck_is_active(dict(params, Tslab_mm=0.0), member_type="beam_girder")
    assert not composite_deck_is_active(dict(params, Be_mm=0.0), member_type="beam_girder")


def test_composite_deck_input_from_parameters_calculates_n_and_transformed_width():
    params = {
        "composite_enabled": True,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
    }
    deck = composite_deck_input_from_parameters(params, member_type="beam_girder")
    assert deck.enabled is True
    assert deck.modular_ratio == pytest.approx(27806.0 / 31529.0)
    assert deck.transformed_width_mm == pytest.approx(1000.0 * 27806.0 / 31529.0)


def test_rectangle_plus_same_modulus_deck_matches_hand_calculation():
    b = 1000.0
    h = 450.0
    tslab = 100.0
    summary = summarize_geometry(rectangle(b, h))
    deck = CompositeDeckInput(enabled=True, Tslab_mm=tslab, Be_mm=b, Ebeam_MPa=30000.0, Edeck_MPa=30000.0)
    composite = calculate_composite_transformed_section(summary, deck)

    a1 = b * h
    y1 = 0.0
    ix1 = b * h**3 / 12.0
    a2 = b * tslab
    y2 = h / 2.0 + tslab / 2.0
    ix2 = b * tslab**3 / 12.0
    area = a1 + a2
    ybar = (a1 * y1 + a2 * y2) / area
    ix = ix1 + a1 * (y1 - ybar) ** 2 + ix2 + a2 * (y2 - ybar) ** 2

    assert composite.area_mm2 == pytest.approx(area)
    assert composite.centroid_y_mm == pytest.approx(ybar)
    assert composite.centroid_y_from_bottom_mm == pytest.approx(ybar + h / 2.0)
    assert composite.ix_mm4 == pytest.approx(ix)
    assert composite.c_top_mm == pytest.approx((h / 2.0 + tslab) - ybar)
    assert composite.c_bottom_mm == pytest.approx(ybar + h / 2.0)
    assert composite.z_top_mm3 == pytest.approx(ix / composite.c_top_mm)
    assert composite.z_bottom_mm3 == pytest.approx(ix / composite.c_bottom_mm)


def test_calculation_rejects_inactive_or_invalid_composite_input():
    summary = summarize_geometry(rectangle(1000.0, 450.0))
    with pytest.raises(ValueError, match="not active"):
        calculate_composite_transformed_section(summary, CompositeDeckInput(False, 100.0, 1000.0, 30000.0, 30000.0))
    with pytest.raises(ValueError, match="Tslab"):
        calculate_composite_transformed_section(summary, CompositeDeckInput(True, 0.0, 1000.0, 30000.0, 30000.0))


def test_interior_plank_composite_calculation_is_separate_from_gross_properties():
    params = {
        "B_mm": 990.0,
        "b1_mm": 45.0,
        "b2_mm": 70.0,
        "b3_mm": 850.0,
        "H_mm": 450.0,
        "h1_mm": 80.0,
        "h2_mm": 140.0,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
        "girder_length_mm": 12000.0,
    }
    geometry = default_registry.geometry("parametric_plank_girder_interior")(**params)
    gross = summarize_geometry(geometry)
    composite = calculate_composite_transformed_section_from_geometry(
        geometry,
        CompositeDeckInput(True, params["Tslab_mm"], params["Be_mm"], params["Ebeam_MPa"], params["Edeck_MPa"]),
    )

    assert gross.area_mm2 == pytest.approx(405650.0)
    assert composite.area_mm2 > gross.area_mm2
    assert composite.top_fiber_y_mm == pytest.approx(gross.y_max_mm + params["Tslab_mm"])
    assert composite.bottom_fiber_y_mm == pytest.approx(gross.y_min_mm)
    assert composite.modular_ratio == pytest.approx(params["Edeck_MPa"] / params["Ebeam_MPa"])
    assert composite.transformed_width_mm == pytest.approx(params["Be_mm"] * params["Edeck_MPa"] / params["Ebeam_MPa"])




def test_i_girder_composite_calculation_is_display_only_and_separate_from_gross_properties():
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
    gross = summarize_geometry(geometry)
    deck = CompositeDeckInput(True, Tslab_mm=200.0, Be_mm=2000.0, Ebeam_MPa=31529.0, Edeck_MPa=27806.0)
    composite = calculate_composite_transformed_section_from_geometry(geometry, deck)

    assert composite.area_mm2 > gross.area_mm2
    assert composite.top_fiber_y_mm == pytest.approx(gross.y_max_mm + deck.Tslab_mm)
    assert composite.bottom_fiber_y_mm == pytest.approx(gross.y_min_mm)
    assert composite.modular_ratio == pytest.approx(deck.Edeck_MPa / deck.Ebeam_MPa)
    assert composite.transformed_width_mm == pytest.approx(deck.Be_mm * deck.Edeck_MPa / deck.Ebeam_MPa)

def test_composite_validation_suite_passes():
    results = validate_composite_section_properties()
    assert results
    assert all(result.status == "PASS" for result in results)
