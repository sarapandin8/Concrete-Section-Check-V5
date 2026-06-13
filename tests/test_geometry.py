from __future__ import annotations

import math

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.geometry.generators import circle, rectangle, rectangular_chamfered, rectangular_chamfered_dimensions, rectangular_hollow
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import validate_section_geometry


def test_rectangle_area() -> None:
    geometry = rectangle(width_mm=400, height_mm=600)
    summary = summarize_geometry(geometry)
    assert summary.area_mm2 == 240000
    assert summary.centroid_x_mm == 0
    assert summary.centroid_y_mm == 0


def test_circle_area_approximate() -> None:
    geometry = circle(diameter_mm=1000, segments=256)
    summary = summarize_geometry(geometry)
    expected = math.pi * 500**2
    assert summary.area_mm2 == pytest_approx(expected, rel=0.001)


def test_hollow_rectangle_area() -> None:
    geometry = rectangular_hollow(width_mm=1000, height_mm=800, wall_thickness_mm=100)
    summary = summarize_geometry(geometry)
    assert summary.area_mm2 == 1000 * 800 - 800 * 600


def test_rectangular_chamfered_supports_independent_x_y_chamfers() -> None:
    geometry = rectangular_chamfered(width_mm=500, height_mm=700, chamfer_x_mm=80, chamfer_y_mm=40)
    summary = summarize_geometry(geometry)
    points = [(point.x, point.y) for point in geometry.outer_polygon]

    assert points[0] == (-170.0, -350.0)
    assert points[1] == (170.0, -350.0)
    assert points[2] == (250.0, -310.0)
    assert summary.area_mm2 == pytest_approx(500 * 700 - 2 * 80 * 40, rel=1e-12)
    assert geometry.metadata["chamfer_x_mm"] == 80
    assert geometry.metadata["chamfer_y_mm"] == 40


def test_rectangular_chamfered_legacy_single_chamfer_remains_supported() -> None:
    geometry = rectangular_chamfered(width_mm=500, height_mm=700, chamfer_mm=50)
    points = [(point.x, point.y) for point in geometry.outer_polygon]

    assert points[0] == (-200.0, -350.0)
    assert points[2] == (250.0, -300.0)


def test_rectangular_chamfered_rejects_chamfers_that_remove_a_side() -> None:
    import pytest

    with pytest.raises(ValueError, match="chamfer_x_mm"):
        rectangular_chamfered(width_mm=500, height_mm=700, chamfer_x_mm=250, chamfer_y_mm=40)
    with pytest.raises(ValueError, match="chamfer_y_mm"):
        rectangular_chamfered(width_mm=500, height_mm=700, chamfer_x_mm=80, chamfer_y_mm=350)


def test_rectangular_chamfered_dimension_guides_show_cx_and_cy() -> None:
    dimensions = rectangular_chamfered_dimensions(width_mm=500, height_mm=700, chamfer_x_mm=80, chamfer_y_mm=40)
    symbols = [item.symbol for item in dimensions]

    assert symbols == ["B", "H", "cx", "cy"]


def test_invalid_polygon() -> None:
    geometry = SectionGeometry(
        name="bowtie",
        outer_polygon=[
            Point2D(x=0, y=0),
            Point2D(x=100, y=100),
            Point2D(x=0, y=100),
            Point2D(x=100, y=0),
        ],
    )
    result = validate_section_geometry(geometry)
    assert not result.is_valid
    assert any("invalid" in error.lower() for error in result.errors)


def test_hole_outside_polygon() -> None:
    geometry = SectionGeometry(
        name="bad-hole",
        outer_polygon=[
            Point2D(x=0, y=0),
            Point2D(x=100, y=0),
            Point2D(x=100, y=100),
            Point2D(x=0, y=100),
        ],
        holes=[
            [
                Point2D(x=200, y=200),
                Point2D(x=250, y=200),
                Point2D(x=250, y=250),
                Point2D(x=200, y=250),
            ]
        ],
    )
    result = validate_section_geometry(geometry)
    assert not result.is_valid
    assert any("inside" in error.lower() for error in result.errors)


def test_geometry_summary_fiber_distance_convention_accessors() -> None:
    geometry = rectangle(width_mm=400, height_mm=600)
    summary = summarize_geometry(geometry)

    assert summary.depth_mm == 600
    assert summary.width_mm == 400
    assert summary.centroid_y_from_bottom_mm == 300
    assert summary.centroid_y_from_top_mm == 300
    assert summary.top_fiber_distance_mm == 300
    assert summary.bottom_fiber_distance_mm == 300
    assert summary.centroid_y_offset_from_mid_depth_mm == 0



def pytest_approx(value: float, rel: float) -> object:
    import pytest

    return pytest.approx(value, rel=rel)


def test_rectangle_inertia_and_section_modulus() -> None:
    geometry = rectangle(width_mm=400, height_mm=600)
    summary = summarize_geometry(geometry)
    assert summary.ix_nmm4 == pytest_approx(400 * 600**3 / 12, rel=1e-12)
    assert summary.iy_nmm4 == pytest_approx(600 * 400**3 / 12, rel=1e-12)
    assert summary.z_top_mm3 == pytest_approx(summary.ix_nmm4 / 300, rel=1e-12)
    assert summary.z_bottom_mm3 == pytest_approx(summary.ix_nmm4 / 300, rel=1e-12)
    assert summary.ix_display != "Not calculated"
