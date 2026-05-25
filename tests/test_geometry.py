from __future__ import annotations

import math

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.geometry.generators import circle, rectangle, rectangular_hollow
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


def pytest_approx(value: float, rel: float) -> object:
    import pytest

    return pytest.approx(value, rel=rel)
