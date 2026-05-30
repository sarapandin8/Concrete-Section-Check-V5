import pytest

from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry


def _default_params():
    return {
        "B1_mm": 800,
        "B2_mm": 500,
        "D1_mm": 1400,
        "D2_mm": 200,
        "D3_mm": 150,
        "D5_mm": 250,
        "D6_mm": 150,
        "T1_mm": 200,
        "T2_mm": 200,
        "C1_mm": 0,
    }


def test_parametric_i_girder_generates_valid_section():
    geometry = default_registry.geometry("parametric_i_girder")(**_default_params())
    validation = validate_section_geometry(geometry)
    summary = summarize_geometry(geometry)

    assert validation.is_valid
    assert not validation.errors
    assert geometry.metadata["preset"] == "parametric_i_girder"
    assert geometry.metadata["zone_depths_mm"]["web_clear_zone"] == 650
    assert geometry.metadata["analysis_compatibility"]["uls_pmm"] == "supported"
    assert len(geometry.holes) == 0
    assert summary.area_mm2 > 0
    assert abs(summary.centroid_x_mm) < 1e-6
    assert summary.ix_nmm4 is not None and summary.ix_nmm4 > 0
    assert summary.iy_nmm4 is not None and summary.iy_nmm4 > 0
    assert summary.z_top_mm3 is not None and summary.z_top_mm3 > 0
    assert summary.z_bottom_mm3 is not None and summary.z_bottom_mm3 > 0
    assert summary.ix_display != "Not calculated"
    assert summary.iy_display != "Not calculated"


def test_parametric_i_girder_dimensions_are_registered():
    dimensions = default_registry.dimensions("parametric_i_girder")(**_default_params())
    symbols = {dim.symbol for dim in dimensions}
    assert {"B1", "B2", "D1", "D2", "D3", "D5", "D6", "T1", "T2"}.issubset(symbols)


def test_parametric_i_girder_c1_dimension_is_optional():
    params = _default_params()
    assert "C1" not in {dim.symbol for dim in default_registry.dimensions("parametric_i_girder")(**params)}
    params["C1_mm"] = 50
    assert "C1" in {dim.symbol for dim in default_registry.dimensions("parametric_i_girder")(**params)}


@pytest.mark.parametrize(
    "override, expected_message",
    [
        ({"D1_mm": 700}, "D1 must be greater"),
        ({"T1_mm": 900}, "T1 must not exceed B1"),
        ({"T2_mm": 700}, "T2 must not exceed B2"),
        ({"B1_mm": 0}, "B1 must be greater than zero"),
    ],
)
def test_parametric_i_girder_rejects_invalid_dimensions(override, expected_message):
    params = _default_params()
    params.update(override)
    with pytest.raises(ValueError, match=expected_message):
        default_registry.geometry("parametric_i_girder")(**params)
