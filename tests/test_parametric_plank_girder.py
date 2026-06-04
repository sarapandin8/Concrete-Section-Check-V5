import pytest

from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry


def _interior_params():
    return {
        "B_mm": 990,
        "b1_mm": 45,
        "b2_mm": 70,
        "b3_mm": 850,
        "H_mm": 450,
        "h1_mm": 80,
        "h2_mm": 140,
        "Tslab_mm": 100,
        "Be_mm": 1000,
        "Ebeam_MPa": 35000,
        "Edeck_MPa": 28560,
        "girder_length_mm": 12000,
    }


def _exterior_params():
    params = _interior_params()
    params.update({"b3_mm": 920, "overhang_mm": 500})
    return params


def test_parametric_plank_interior_generates_valid_precast_section():
    geometry = default_registry.geometry("parametric_plank_girder_interior")(**_interior_params())
    validation = validate_section_geometry(geometry)
    summary = summarize_geometry(geometry)

    assert validation.is_valid
    assert not validation.errors
    assert geometry.metadata["preset"] == "parametric_plank_girder_interior"
    assert geometry.metadata["plank_position"] == "Interior"
    assert geometry.metadata["analysis_compatibility"]["uls_pmm"] == "supported_precast_only"
    assert len(geometry.holes) == 0
    assert summary.area_mm2 > 0
    assert summary.ix_nmm4 and summary.ix_nmm4 > 0
    assert summary.iy_nmm4 and summary.iy_nmm4 > 0


def test_parametric_plank_exterior_generates_valid_precast_section():
    geometry = default_registry.geometry("parametric_plank_girder_exterior")(**_exterior_params())
    validation = validate_section_geometry(geometry)
    summary = summarize_geometry(geometry)

    assert validation.is_valid
    assert geometry.metadata["preset"] == "parametric_plank_girder_exterior"
    assert geometry.metadata["plank_position"] == "Exterior"
    assert summary.area_mm2 > 0
    # exterior girder is intentionally asymmetric
    assert abs(summary.centroid_x_mm) > 1e-6


def test_parametric_plank_composite_metadata_is_auto_calculated():
    geometry = default_registry.geometry("parametric_plank_girder_interior")(**_interior_params())
    composite = geometry.metadata["composite_metadata"]

    assert composite["Be_calculation_mode"] == "manual_current__auto_aashto_planned"
    assert composite["n_Edeck_over_Ebeam"] == pytest.approx(28560 / 35000)
    assert composite["Btransformed_mm"] == pytest.approx(1000 * 28560 / 35000)


@pytest.mark.parametrize(
    "generator_name, params, expected_message",
    [
        ("parametric_plank_girder_interior", {**_interior_params(), "b3_mm": 700}, "B should approximately equal b3 \\+ 2\\*b2"),
        ("parametric_plank_girder_exterior", {**_exterior_params(), "b3_mm": 850}, "B should approximately equal b3 \\+ b2"),
        ("parametric_plank_girder_interior", {**_interior_params(), "h1_mm": 160}, "h1 must not exceed h2"),
        ("parametric_plank_girder_interior", {**_interior_params(), "Ebeam_MPa": 0}, "Ebeam must be greater than zero"),
    ],
)
def test_parametric_plank_rejects_invalid_dimensions(generator_name, params, expected_message):
    with pytest.raises(ValueError, match=expected_message):
        default_registry.geometry(generator_name)(**params)


def test_parametric_plank_dimensions_are_registered():
    symbols = {dim.symbol for dim in default_registry.dimensions("parametric_plank_girder_interior")(**_interior_params())}
    assert {"B", "b1", "b2", "b3", "H", "h1", "h2"}.issubset(symbols)


def _width_at_y(points, y, tol=1e-6):
    xs = []
    for index, p1 in enumerate(points):
        p2 = points[(index + 1) % len(points)]
        if abs(p1.y - p2.y) <= tol:
            if abs(y - p1.y) <= tol:
                xs.extend([p1.x, p2.x])
            continue
        y_min = min(p1.y, p2.y)
        y_max = max(p1.y, p2.y)
        if y_min - tol <= y <= y_max + tol:
            t = (y - p1.y) / (p2.y - p1.y)
            if -tol <= t <= 1.0 + tol:
                xs.append(p1.x + t * (p2.x - p1.x))
    unique = []
    for x in sorted(xs):
        if not unique or abs(x - unique[-1]) > 1e-5:
            unique.append(x)
    assert len(unique) >= 2
    return unique[-1] - unique[0]


def test_parametric_plank_interior_user_confirmed_stepped_profile_widths():
    params = _interior_params()
    geometry = default_registry.geometry("parametric_plank_girder_interior")(**params)
    pts = geometry.outer_polygon
    bottom_y = -params["H_mm"] / 2.0
    y1 = bottom_y + params["h1_mm"]
    y2 = bottom_y + params["h2_mm"]
    top_y = params["H_mm"] / 2.0

    assert _width_at_y(pts, bottom_y) == pytest.approx(params["B_mm"])
    assert _width_at_y(pts, y1) == pytest.approx(params["B_mm"])
    assert _width_at_y(pts, y2) == pytest.approx(params["b3_mm"])
    assert _width_at_y(pts, top_y) == pytest.approx(params["B_mm"] - 2 * params["b1_mm"])


def test_parametric_plank_exterior_user_confirmed_right_vertical_profile():
    params = _exterior_params()
    geometry = default_registry.geometry("parametric_plank_girder_exterior")(**params)
    pts = geometry.outer_polygon
    bottom_y = -params["H_mm"] / 2.0
    y1 = bottom_y + params["h1_mm"]
    y2 = bottom_y + params["h2_mm"]
    top_y = params["H_mm"] / 2.0
    x_left = -params["B_mm"] / 2.0
    x_right = params["B_mm"] / 2.0

    assert any(abs(p.x - x_right) < 1e-6 and abs(p.y - bottom_y) < 1e-6 for p in pts)
    assert any(abs(p.x - x_right) < 1e-6 and abs(p.y - top_y) < 1e-6 for p in pts)
    assert any(abs(p.x - x_left) < 1e-6 and abs(p.y - bottom_y) < 1e-6 for p in pts)
    assert any(abs(p.x - x_left) < 1e-6 and abs(p.y - y1) < 1e-6 for p in pts)
    assert any(abs(p.x - (x_left + params["b2_mm"])) < 1e-6 and abs(p.y - y2) < 1e-6 for p in pts)
    assert any(abs(p.x - (x_left + params["b1_mm"])) < 1e-6 and abs(p.y - top_y) < 1e-6 for p in pts)
    assert _width_at_y(pts, y2) == pytest.approx(params["b3_mm"])


def _void_centers_from_left(geometry, B_mm):
    centers = []
    for hole in geometry.holes:
        xs = [point.x for point in hole]
        ys = [point.y for point in hole]
        centers.append((round((min(xs) + max(xs)) / 2.0 + B_mm / 2.0, 6), round((min(ys) + max(ys)) / 2.0 + geometry.metadata["parameters"]["H_mm"] / 2.0, 6)))
    return centers


def test_voided_plank_interior_adds_three_circular_voids_at_user_coordinates():
    params = _interior_params()
    geometry = default_registry.geometry("parametric_plank_girder_voided_interior")(**params)
    validation = validate_section_geometry(geometry)
    solid = default_registry.geometry("parametric_plank_girder_interior")(**params)
    solid_summary = summarize_geometry(solid)
    voided_summary = summarize_geometry(geometry)

    assert validation.is_valid
    assert geometry.metadata["preset"] == "parametric_plank_girder_voided_interior"
    assert geometry.metadata["girder_type"] == "Voided Plank Girder"
    assert len(geometry.holes) == 3
    assert [center[0] for center in _void_centers_from_left(geometry, params["B_mm"])] == [245.0, 495.0, 745.0]
    assert [center[1] for center in _void_centers_from_left(geometry, params["B_mm"])] == [225.0, 225.0, 225.0]
    assert voided_summary.area_mm2 < solid_summary.area_mm2


def test_voided_plank_exterior_adds_three_circular_voids_at_user_coordinates():
    params = _exterior_params()
    geometry = default_registry.geometry("parametric_plank_girder_voided_exterior")(**params)
    validation = validate_section_geometry(geometry)

    assert validation.is_valid
    assert geometry.metadata["preset"] == "parametric_plank_girder_voided_exterior"
    assert geometry.metadata["plank_position"] == "Exterior"
    assert len(geometry.holes) == 3
    assert [center[0] for center in _void_centers_from_left(geometry, params["B_mm"])] == [240.0, 540.0, 810.0]
    assert [center[1] for center in _void_centers_from_left(geometry, params["B_mm"])] == [225.0, 225.0, 225.0]


def test_voided_plank_presets_are_available_in_section_preset_json():
    from concrete_pmm_pro.geometry.presets import preset_by_key  # noqa: PLC0415

    interior = preset_by_key("parametric_plank_girder_voided_interior")
    exterior = preset_by_key("parametric_plank_girder_voided_exterior")
    assert interior["display_name"] == "Precast Voided Plank Girder — Interior"
    assert exterior["display_name"] == "Precast Voided Plank Girder — Exterior"
    assert any(param["name"] == "void_diameter_mm" for param in interior["parameters"])
    assert any(param["name"] == "void_middle_x_from_left_mm" for param in exterior["parameters"])
