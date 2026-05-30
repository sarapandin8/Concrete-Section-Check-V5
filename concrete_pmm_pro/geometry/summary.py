"""Geometry summary calculations.

The Section Builder uses this lightweight module to show analysis-ready gross
section properties.  Units are mm-based: area in mm² and second moments of area
in mm⁴.  The calculations intentionally support holes because future girder
presets (box / plank voids) will need the same summary path.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon

from concrete_pmm_pro.core.models import Point2D, SectionGeometry


@dataclass(frozen=True)
class _RingProperties:
    area_mm2: float
    centroid_x_mm: float
    centroid_y_mm: float
    ix_origin_mm4: float
    iy_origin_mm4: float
    ixy_origin_mm4: float


@dataclass(frozen=True)
class GeometrySummary:
    area_mm2: float
    centroid_x_mm: float
    centroid_y_mm: float
    ix_nmm4: float | None = None
    iy_nmm4: float | None = None
    ixy_nmm4: float | None = None
    x_min_mm: float | None = None
    x_max_mm: float | None = None
    y_min_mm: float | None = None
    y_max_mm: float | None = None
    z_top_mm3: float | None = None
    z_bottom_mm3: float | None = None
    z_left_mm3: float | None = None
    z_right_mm3: float | None = None
    warnings: tuple[str, ...] = ()

    @property
    def ix_display(self) -> str:
        return _engineering_display(self.ix_nmm4, "mm^4")

    @property
    def iy_display(self) -> str:
        return _engineering_display(self.iy_nmm4, "mm^4")

    @property
    def z_top_display(self) -> str:
        return _engineering_display(self.z_top_mm3, "mm^3")

    @property
    def z_bottom_display(self) -> str:
        return _engineering_display(self.z_bottom_mm3, "mm^3")

    @property
    def depth_mm(self) -> float | None:
        if self.y_min_mm is None or self.y_max_mm is None:
            return None
        return self.y_max_mm - self.y_min_mm

    @property
    def width_mm(self) -> float | None:
        if self.x_min_mm is None or self.x_max_mm is None:
            return None
        return self.x_max_mm - self.x_min_mm

    @property
    def centroid_y_from_bottom_mm(self) -> float | None:
        if self.y_min_mm is None:
            return None
        return self.centroid_y_mm - self.y_min_mm

    @property
    def centroid_y_from_top_mm(self) -> float | None:
        if self.y_max_mm is None:
            return None
        return self.y_max_mm - self.centroid_y_mm

    @property
    def centroid_y_offset_from_mid_depth_mm(self) -> float | None:
        if self.y_min_mm is None or self.y_max_mm is None:
            return None
        return self.centroid_y_mm - 0.5 * (self.y_min_mm + self.y_max_mm)

    @property
    def top_fiber_distance_mm(self) -> float | None:
        return self.centroid_y_from_top_mm

    @property
    def bottom_fiber_distance_mm(self) -> float | None:
        return self.centroid_y_from_bottom_mm

    @property
    def centroid_x_offset_from_mid_width_mm(self) -> float | None:
        if self.x_min_mm is None or self.x_max_mm is None:
            return None
        return self.centroid_x_mm - 0.5 * (self.x_min_mm + self.x_max_mm)


def _engineering_display(value: float | None, unit: str) -> str:
    if value is None or not math.isfinite(value):
        return "Not calculated"
    abs_value = abs(value)
    if abs_value >= 1.0e12:
        return f"{value / 1.0e12:,.3f}e12 {unit}"
    if abs_value >= 1.0e9:
        return f"{value / 1.0e9:,.3f}e9 {unit}"
    if abs_value >= 1.0e6:
        return f"{value / 1.0e6:,.3f}e6 {unit}"
    return f"{value:,.1f} {unit}"


def to_shapely_polygon(geometry: SectionGeometry) -> Polygon:
    outer = [point.as_tuple() for point in geometry.outer_polygon]
    holes = [[point.as_tuple() for point in hole] for hole in geometry.holes]
    return Polygon(outer, holes)


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
    return _RingProperties(
        area_mm2=abs(signed_area),
        centroid_x_mm=cx_num / (6.0 * signed_area),
        centroid_y_mm=cy_num / (6.0 * signed_area),
        ix_origin_mm4=orientation * ix_num / 12.0,
        iy_origin_mm4=orientation * iy_num / 12.0,
        ixy_origin_mm4=orientation * ixy_num / 24.0,
    )


def _section_modulus(inertia_mm4: float, distance_mm: float) -> float | None:
    if distance_mm <= 0:
        return None
    return inertia_mm4 / distance_mm


def summarize_geometry(geometry: SectionGeometry) -> GeometrySummary:
    """Return gross section area, centroid, inertia, and extreme-fiber data.

    Holes are subtracted by area and by origin second moments.  The returned
    centroidal Ix/Iy are gross concrete properties about the generated section
    centroid, ready for future SLS prestressed-girder checks.
    """

    polygon = to_shapely_polygon(geometry)
    if polygon.is_empty or polygon.area <= 0 or not polygon.is_valid:
        centroid = polygon.centroid
        return GeometrySummary(area_mm2=float(polygon.area), centroid_x_mm=float(centroid.x), centroid_y_mm=float(centroid.y))

    outer = _ring_properties(geometry.outer_polygon)
    holes = [_ring_properties(hole) for hole in geometry.holes]

    area = outer.area_mm2 - sum(hole.area_mm2 for hole in holes)
    if area <= 0:
        raise ValueError("Invalid section geometry: net gross area must be positive.")

    first_x = outer.area_mm2 * outer.centroid_x_mm - sum(hole.area_mm2 * hole.centroid_x_mm for hole in holes)
    first_y = outer.area_mm2 * outer.centroid_y_mm - sum(hole.area_mm2 * hole.centroid_y_mm for hole in holes)
    cx = first_x / area
    cy = first_y / area

    ix_origin = outer.ix_origin_mm4 - sum(hole.ix_origin_mm4 for hole in holes)
    iy_origin = outer.iy_origin_mm4 - sum(hole.iy_origin_mm4 for hole in holes)
    ixy_origin = outer.ixy_origin_mm4 - sum(hole.ixy_origin_mm4 for hole in holes)
    ix_centroid = ix_origin - area * cy * cy
    iy_centroid = iy_origin - area * cx * cx
    ixy_centroid = ixy_origin - area * cx * cy

    warnings: list[str] = []
    if ix_centroid < 0 or iy_centroid < 0:
        warnings.append("Gross section inertia sign was corrected from polygon ring orientation.")
        ix_centroid = abs(ix_centroid)
        iy_centroid = abs(iy_centroid)

    x_min, y_min, x_max, y_max = polygon.bounds
    return GeometrySummary(
        area_mm2=float(area),
        centroid_x_mm=float(cx),
        centroid_y_mm=float(cy),
        ix_nmm4=float(ix_centroid),
        iy_nmm4=float(iy_centroid),
        ixy_nmm4=float(ixy_centroid),
        x_min_mm=float(x_min),
        x_max_mm=float(x_max),
        y_min_mm=float(y_min),
        y_max_mm=float(y_max),
        z_top_mm3=_section_modulus(float(ix_centroid), float(y_max) - cy),
        z_bottom_mm3=_section_modulus(float(ix_centroid), cy - float(y_min)),
        z_left_mm3=_section_modulus(float(iy_centroid), cx - float(x_min)),
        z_right_mm3=_section_modulus(float(iy_centroid), float(x_max) - cx),
        warnings=tuple(warnings),
    )
