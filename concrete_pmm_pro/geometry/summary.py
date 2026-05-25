"""Geometry summary calculations."""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from concrete_pmm_pro.core.models import SectionGeometry


@dataclass(frozen=True)
class GeometrySummary:
    area_mm2: float
    centroid_x_mm: float
    centroid_y_mm: float
    ix_nmm4: None = None
    iy_nmm4: None = None

    @property
    def ix_display(self) -> str:
        return "TODO"

    @property
    def iy_display(self) -> str:
        return "TODO"


def to_shapely_polygon(geometry: SectionGeometry) -> Polygon:
    outer = [point.as_tuple() for point in geometry.outer_polygon]
    holes = [[point.as_tuple() for point in hole] for hole in geometry.holes]
    return Polygon(outer, holes)


def summarize_geometry(geometry: SectionGeometry) -> GeometrySummary:
    polygon = to_shapely_polygon(geometry)
    centroid = polygon.centroid
    return GeometrySummary(area_mm2=float(polygon.area), centroid_x_mm=float(centroid.x), centroid_y_mm=float(centroid.y))
