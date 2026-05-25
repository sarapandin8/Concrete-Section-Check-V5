"""Gross concrete section property calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon

from concrete_pmm_pro.core.models import Point2D, SectionGeometry
from concrete_pmm_pro.serviceability.models import GrossSectionProperties, StressCheckPoint


@dataclass(frozen=True)
class _RingProperties:
    area: float
    cx: float
    cy: float
    ix_origin: float
    iy_origin: float
    ixy_origin: float


def _as_xy(points: list[Point2D]) -> list[tuple[float, float]]:
    xy = [(float(point.x), float(point.y)) for point in points]
    if xy and xy[0] != xy[-1]:
        xy.append(xy[0])
    return xy


def _ring_properties(points: list[Point2D]) -> _RingProperties:
    xy = _as_xy(points)
    if len(xy) < 4:
        raise ValueError("Invalid section geometry: polygon ring must contain at least three points.")

    area2 = 0.0
    cx_num = 0.0
    cy_num = 0.0
    ix_num = 0.0
    iy_num = 0.0
    ixy_num = 0.0
    for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
        cross = x0 * y1 - x1 * y0
        area2 += cross
        cx_num += (x0 + x1) * cross
        cy_num += (y0 + y1) * cross
        ix_num += (y0 * y0 + y0 * y1 + y1 * y1) * cross
        iy_num += (x0 * x0 + x0 * x1 + x1 * x1) * cross
        ixy_num += (2.0 * x0 * y0 + x0 * y1 + x1 * y0 + 2.0 * x1 * y1) * cross

    signed_area = area2 / 2.0
    if math.isclose(signed_area, 0.0, abs_tol=1.0e-12):
        raise ValueError("Invalid section geometry: polygon ring area is zero.")

    orientation = 1.0 if signed_area > 0 else -1.0
    area = abs(signed_area)
    cx = cx_num / (6.0 * signed_area)
    cy = cy_num / (6.0 * signed_area)
    return _RingProperties(
        area=area,
        cx=cx,
        cy=cy,
        ix_origin=orientation * ix_num / 12.0,
        iy_origin=orientation * iy_num / 12.0,
        ixy_origin=orientation * ixy_num / 24.0,
    )


def _section_polygon(section_geometry: SectionGeometry) -> Polygon:
    outer = [(point.x, point.y) for point in section_geometry.outer_polygon]
    holes = [[(point.x, point.y) for point in hole] for hole in section_geometry.holes]
    polygon = Polygon(outer, holes)
    if polygon.is_empty or polygon.area <= 0:
        raise ValueError("Invalid section geometry: gross section area must be positive.")
    if not polygon.is_valid:
        raise ValueError("Invalid section geometry: polygon is invalid.")
    return polygon


def _section_modulus(inertia_mm4: float, distance_mm: float) -> float | None:
    if distance_mm <= 0:
        return None
    return inertia_mm4 / distance_mm


def compute_gross_section_properties(section_geometry: SectionGeometry) -> GrossSectionProperties:
    """Compute net gross concrete properties for outer polygon minus holes."""

    polygon = _section_polygon(section_geometry)
    outer = _ring_properties(section_geometry.outer_polygon)
    hole_props = [_ring_properties(hole) for hole in section_geometry.holes]

    net_area = outer.area - sum(hole.area for hole in hole_props)
    if net_area <= 0:
        raise ValueError("Invalid section geometry: net gross area must be positive.")

    first_moment_x = outer.area * outer.cx - sum(hole.area * hole.cx for hole in hole_props)
    first_moment_y = outer.area * outer.cy - sum(hole.area * hole.cy for hole in hole_props)
    cx = first_moment_x / net_area
    cy = first_moment_y / net_area

    ix_origin = outer.ix_origin - sum(hole.ix_origin for hole in hole_props)
    iy_origin = outer.iy_origin - sum(hole.iy_origin for hole in hole_props)
    ixy_origin = outer.ixy_origin - sum(hole.ixy_origin for hole in hole_props)
    ix_centroid = ix_origin - net_area * cy * cy
    iy_centroid = iy_origin - net_area * cx * cx
    ixy_centroid = ixy_origin - net_area * cx * cy

    warnings: list[str] = []
    if abs(ix_centroid) <= 1.0e-9 or abs(iy_centroid) <= 1.0e-9:
        raise ValueError("Invalid section geometry: gross section inertia must be positive.")
    if ix_centroid < 0 or iy_centroid < 0:
        warnings.append("Gross section inertia sign was corrected from polygon ring orientation.")
        ix_centroid = abs(ix_centroid)
        iy_centroid = abs(iy_centroid)

    x_min, y_min, x_max, y_max = polygon.bounds
    return GrossSectionProperties(
        area_mm2=net_area,
        centroid_x_mm=cx,
        centroid_y_mm=cy,
        Ix_mm4=ix_centroid,
        Iy_mm4=iy_centroid,
        Ixy_mm4=ixy_centroid,
        x_min_mm=float(x_min),
        x_max_mm=float(x_max),
        y_min_mm=float(y_min),
        y_max_mm=float(y_max),
        section_modulus_top_mm3=_section_modulus(ix_centroid, float(y_max) - cy),
        section_modulus_bottom_mm3=_section_modulus(ix_centroid, cy - float(y_min)),
        section_modulus_left_mm3=_section_modulus(iy_centroid, cx - float(x_min)),
        section_modulus_right_mm3=_section_modulus(iy_centroid, float(x_max) - cx),
        warnings=warnings,
    )


def default_stress_check_points(section_properties: GrossSectionProperties) -> list[StressCheckPoint]:
    """Return default extreme-fiber and centroid points for future SLS stress checks."""

    cx = section_properties.centroid_x_mm
    cy = section_properties.centroid_y_mm
    return [
        StressCheckPoint(
            name="Top fiber",
            x_mm=cx,
            y_mm=section_properties.y_max_mm,
            point_type="extreme_fiber",
            source="default",
            note="Default gross-section top fiber.",
        ),
        StressCheckPoint(
            name="Bottom fiber",
            x_mm=cx,
            y_mm=section_properties.y_min_mm,
            point_type="extreme_fiber",
            source="default",
            note="Default gross-section bottom fiber.",
        ),
        StressCheckPoint(
            name="Left fiber",
            x_mm=section_properties.x_min_mm,
            y_mm=cy,
            point_type="extreme_fiber",
            source="default",
            note="Default gross-section left fiber.",
        ),
        StressCheckPoint(
            name="Right fiber",
            x_mm=section_properties.x_max_mm,
            y_mm=cy,
            point_type="extreme_fiber",
            source="default",
            note="Default gross-section right fiber.",
        ),
        StressCheckPoint(
            name="Centroid",
            x_mm=cx,
            y_mm=cy,
            point_type="reference",
            include_in_governing=False,
            source="default",
            note="Gross concrete centroid.",
        ),
    ]
