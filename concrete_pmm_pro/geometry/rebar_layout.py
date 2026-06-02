"""Ordinary rebar layout generation helpers.

The helpers in this module are intentionally pure-Python / geometry-only so the
Rebar UI can preview generated layouts without changing the PMM solver.  The
first supported workflow is a conservative perimeter layout for column/pier/
wall/pylon style sections: offset the current section outline inward by a bar
center distance and place bars at approximately uniform spacing along that
inner perimeter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from concrete_pmm_pro.core.models import SectionGeometry
from concrete_pmm_pro.geometry.summary import to_shapely_polygon


@dataclass(frozen=True)
class PerimeterRebarLayoutResult:
    """Generated ordinary rebar layout table plus audit messages."""

    table: pd.DataFrame
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    info: tuple[str, ...] = ()
    perimeter_length_mm: float | None = None
    actual_spacing_mm: float | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def _as_polygon(geometry: SectionGeometry) -> Polygon:
    polygon = to_shapely_polygon(geometry)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if isinstance(polygon, MultiPolygon):
        polygon = max(polygon.geoms, key=lambda part: part.area)
    if not isinstance(polygon, Polygon) or polygon.is_empty or polygon.area <= 0:
        raise ValueError("Section geometry is not a valid polygon.")
    return polygon


def _largest_polygon(geometry: BaseGeometry) -> tuple[Polygon | None, bool]:
    """Return the usable polygon and whether disconnected pieces were discarded."""
    if geometry.is_empty:
        return None, False
    if isinstance(geometry, Polygon):
        return geometry, False
    if isinstance(geometry, MultiPolygon):
        parts = [part for part in geometry.geoms if not part.is_empty and part.area > 0]
        if not parts:
            return None, False
        return max(parts, key=lambda part: part.area), len(parts) > 1
    # Geometry collections can occur for pathological offsets; keep any polygonal
    # components if present and otherwise report failure to the caller.
    parts = [part for part in getattr(geometry, "geoms", []) if isinstance(part, Polygon) and not part.is_empty and part.area > 0]
    if not parts:
        return None, False
    return max(parts, key=lambda part: part.area), len(parts) > 1


def _point_is_effectively_inside(section: Polygon, point: Point, tolerance_mm: float = 1.0e-6) -> bool:
    if section.covers(point):
        return True
    return section.buffer(tolerance_mm).covers(point)


def generate_perimeter_rebar_layout(
    geometry: SectionGeometry | None,
    *,
    bar_size: str,
    diameter_mm: float,
    material: str,
    edge_offset_mm: float = 75.0,
    target_spacing_mm: float = 150.0,
    min_bars: int = 4,
    label_prefix: str = "B",
) -> PerimeterRebarLayoutResult:
    """Generate a preview rebar table from an inward offset perimeter.

    Parameters are deliberately expressed as bar-center layout controls.  The
    generated dataframe uses the standard Rebar table contract so it can be
    previewed and applied to the main Rebar table without touching solver logic.
    """
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    columns = ["Active", "Label", "x_mm", "y_mm", "Bar Size", "Diameter_mm", "Material", "Count", "Note"]
    empty_table = pd.DataFrame(columns=columns)

    if geometry is None:
        return PerimeterRebarLayoutResult(
            table=empty_table,
            errors=("Section geometry is required before a perimeter rebar layout can be generated.",),
        )
    if diameter_mm <= 0:
        return PerimeterRebarLayoutResult(table=empty_table, errors=("Bar diameter must be positive.",))
    if edge_offset_mm <= 0:
        return PerimeterRebarLayoutResult(table=empty_table, errors=("Bar center offset from concrete edge must be positive.",))
    if target_spacing_mm <= 0:
        return PerimeterRebarLayoutResult(table=empty_table, errors=("Target spacing must be positive.",))
    if min_bars < 1:
        return PerimeterRebarLayoutResult(table=empty_table, errors=("Minimum bar count must be at least 1.",))

    try:
        section = _as_polygon(geometry)
    except ValueError as exc:
        return PerimeterRebarLayoutResult(table=empty_table, errors=(str(exc),))

    offset_geom = section.buffer(-float(edge_offset_mm), join_style=2, mitre_limit=2.0)
    layout_polygon, discarded_pieces = _largest_polygon(offset_geom)
    if layout_polygon is None or layout_polygon.is_empty or layout_polygon.area <= 0:
        return PerimeterRebarLayoutResult(
            table=empty_table,
            errors=(
                f"The {edge_offset_mm:g} mm bar-center offset is too large for this section; "
                "reduce the offset or use manual rebar input.",
            ),
        )
    if discarded_pieces:
        warnings.append(
            "Inward offset created disconnected perimeter regions; the largest region is used for this generated preview. Review manually before applying."
        )

    perimeter = layout_polygon.exterior
    perimeter_length_mm = float(perimeter.length)
    if perimeter_length_mm <= 0:
        return PerimeterRebarLayoutResult(table=empty_table, errors=("Generated offset perimeter has zero length.",))

    generated_count = max(int(min_bars), int(math.ceil(perimeter_length_mm / target_spacing_mm)))
    actual_spacing_mm = perimeter_length_mm / generated_count
    if actual_spacing_mm > target_spacing_mm * 1.15:
        warnings.append(
            f"Actual generated spacing is {actual_spacing_mm:.1f} mm, more than 15% above the target {target_spacing_mm:.1f} mm."
        )
    if actual_spacing_mm < max(25.0, diameter_mm):
        warnings.append(
            f"Actual generated spacing is {actual_spacing_mm:.1f} mm; review bar clear spacing/detailing requirements."
        )

    rows: list[dict[str, object]] = []
    outside_count = 0
    prefix = str(label_prefix or "B").strip() or "B"
    for index in range(generated_count):
        distance = index * perimeter_length_mm / generated_count
        point = perimeter.interpolate(distance)
        if not _point_is_effectively_inside(section, point):
            outside_count += 1
        rows.append(
            {
                "Active": True,
                "Label": f"{prefix}{index + 1}",
                "x_mm": round(float(point.x), 3),
                "y_mm": round(float(point.y), 3),
                "Bar Size": str(bar_size),
                "Diameter_mm": float(diameter_mm),
                "Material": str(material or "SD40"),
                "Count": 1,
                "Note": f"Auto perimeter: offset={edge_offset_mm:g} mm, target spacing={target_spacing_mm:g} mm",
            }
        )

    if outside_count:
        errors.append(f"{outside_count} generated bar point(s) are outside concrete; use manual input or adjust the offset.")

    info.append(
        f"Generated {generated_count} bar(s) along an inward offset perimeter; actual spacing ≈ {actual_spacing_mm:.1f} mm."
    )
    info.append(f"Bar center offset from concrete edge = {edge_offset_mm:.1f} mm.")

    return PerimeterRebarLayoutResult(
        table=pd.DataFrame(rows, columns=columns),
        errors=tuple(errors),
        warnings=tuple(warnings),
        info=tuple(info),
        perimeter_length_mm=perimeter_length_mm,
        actual_spacing_mm=actual_spacing_mm,
    )
