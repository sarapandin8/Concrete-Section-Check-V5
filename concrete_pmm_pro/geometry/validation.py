"""Shapely-backed section validation."""

from __future__ import annotations

from dataclasses import dataclass, field

from shapely.geometry import Point, Polygon
from shapely.validation import explain_validity

from concrete_pmm_pro.core.models import PrestressElement, Rebar, SectionGeometry
from concrete_pmm_pro.geometry.summary import to_shapely_polygon


@dataclass
class ValidationResult:
    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def validate_section_geometry(
    geometry: SectionGeometry,
    rebars: list[Rebar] | None = None,
    prestress_elements: list[PrestressElement] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    outer = Polygon([point.as_tuple() for point in geometry.outer_polygon])
    if not outer.is_valid:
        errors.append(f"Outer polygon is invalid: {explain_validity(outer)}")

    section = to_shapely_polygon(geometry)
    if not section.is_valid:
        errors.append(f"Section polygon is invalid: {explain_validity(section)}")

    if section.area <= 0:
        errors.append("Section area must be positive")

    for index, hole_points in enumerate(geometry.holes, start=1):
        hole = Polygon([point.as_tuple() for point in hole_points])
        if not hole.is_valid:
            errors.append(f"Hole {index} is invalid: {explain_validity(hole)}")
        if not hole.within(outer):
            errors.append(f"Hole {index} must be fully inside the outer polygon")

    for index, rebar in enumerate(rebars or [], start=1):
        point = Point(rebar.x_mm, rebar.y_mm)
        if not section.covers(point):
            errors.append(f"Rebar {index} is outside concrete")

    for index, element in enumerate(prestress_elements or [], start=1):
        point = Point(element.x_mm, element.y_mm)
        if not section.covers(point):
            errors.append(f"Prestress element {index} is outside concrete")

    if not errors:
        info.append("Geometry is valid and has positive concrete area.")

    return ValidationResult(is_valid=not errors, errors=errors, warnings=warnings, info=info)
