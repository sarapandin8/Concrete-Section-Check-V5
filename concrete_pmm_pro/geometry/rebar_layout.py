"""Ordinary rebar layout generation helpers.

The helpers in this module are intentionally pure-Python / geometry-only so the
Rebar UI can preview generated layouts without changing the PMM solver.  The
first supported workflow is a conservative perimeter layout for column/pier/
wall/pylon style sections: offset the current section outline inward by a bar
center distance, place bars at geometric corner/control points first, and fill
bars along each segment at approximately the target spacing.
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


def _as_outer_polygon(geometry: SectionGeometry) -> Polygon:
    polygon = Polygon([point.as_tuple() for point in geometry.outer_polygon])
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if isinstance(polygon, MultiPolygon):
        polygon = max(polygon.geoms, key=lambda part: part.area)
    if not isinstance(polygon, Polygon) or polygon.is_empty or polygon.area <= 0:
        raise ValueError("Section outer boundary is not a valid polygon.")
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


def _normalize_vector(dx: float, dy: float) -> tuple[float, float] | None:
    length = math.hypot(dx, dy)
    if length <= 1.0e-9:
        return None
    return dx / length, dy / length


def _turn_angle_degrees(prev_point: tuple[float, float], point: tuple[float, float], next_point: tuple[float, float]) -> float:
    """Return the absolute change in tangent direction at a ring vertex.

    Rectangular/polygonal corners typically produce about 90 degrees.  Vertices
    from a discretized circle produce only a few degrees, so they are not treated
    as mandatory corner bars.
    """
    incoming = _normalize_vector(point[0] - prev_point[0], point[1] - prev_point[1])
    outgoing = _normalize_vector(next_point[0] - point[0], next_point[1] - point[1])
    if incoming is None or outgoing is None:
        return 0.0
    cross = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
    dot = max(-1.0, min(1.0, incoming[0] * outgoing[0] + incoming[1] * outgoing[1]))
    return abs(math.degrees(math.atan2(cross, dot)))


def _corner_vertex_indices(coords: list[tuple[float, float]], threshold_degrees: float = 30.0) -> list[int]:
    """Find polygon/kink vertices where mandatory control bars should be placed."""
    if len(coords) < 3:
        return []
    indices: list[int] = []
    for index, point in enumerate(coords):
        prev_point = coords[index - 1]
        next_point = coords[(index + 1) % len(coords)]
        if _turn_angle_degrees(prev_point, point, next_point) >= threshold_degrees:
            indices.append(index)
    return indices


def _ring_vertex_distances(coords: list[tuple[float, float]]) -> list[float]:
    distances = [0.0]
    for index in range(1, len(coords)):
        previous = coords[index - 1]
        current = coords[index]
        distances.append(distances[-1] + math.hypot(current[0] - previous[0], current[1] - previous[1]))
    return distances


def _dedup_distances(distances: Iterable[float], perimeter_length_mm: float, tolerance_mm: float = 1.0e-5) -> list[float]:
    unique: list[float] = []
    for value in sorted((float(distance) % perimeter_length_mm for distance in distances)):
        if not unique or abs(value - unique[-1]) > tolerance_mm:
            unique.append(value)
    if len(unique) > 1 and abs((unique[0] + perimeter_length_mm) - unique[-1]) <= tolerance_mm:
        unique.pop()
    return unique


def _uniform_distances(perimeter_length_mm: float, target_spacing_mm: float, min_bars: int) -> tuple[list[float], float]:
    generated_count = max(int(min_bars), int(math.ceil(perimeter_length_mm / target_spacing_mm)))
    actual_spacing_mm = perimeter_length_mm / generated_count
    return [index * perimeter_length_mm / generated_count for index in range(generated_count)], actual_spacing_mm


def _corner_controlled_distances(
    layout_polygon: Polygon,
    *,
    target_spacing_mm: float,
    min_bars: int,
    corner_angle_threshold_degrees: float = 30.0,
) -> tuple[list[float], float, int]:
    """Place mandatory bars at offset-polygon corners and fill each segment.

    Returns generated distances along the offset perimeter, the maximum segment
    spacing used, and the number of detected control/corner points.  If no real
    corners are detected, the caller should use uniform spacing logic instead.
    """
    perimeter = layout_polygon.exterior
    perimeter_length_mm = float(perimeter.length)
    coords = [(float(x), float(y)) for x, y in list(perimeter.coords)[:-1]]
    control_indices = _corner_vertex_indices(coords, threshold_degrees=corner_angle_threshold_degrees)
    if len(control_indices) < 2:
        distances, actual_spacing = _uniform_distances(perimeter_length_mm, target_spacing_mm, min_bars)
        return distances, actual_spacing, 0

    vertex_distances = _ring_vertex_distances(coords)
    control_distances = [vertex_distances[index] for index in control_indices]
    control_distances = _dedup_distances(control_distances, perimeter_length_mm)
    if len(control_distances) < 2:
        distances, actual_spacing = _uniform_distances(perimeter_length_mm, target_spacing_mm, min_bars)
        return distances, actual_spacing, 0

    segment_lengths: list[float] = []
    for index, start in enumerate(control_distances):
        end = control_distances[(index + 1) % len(control_distances)]
        if end <= start:
            end += perimeter_length_mm
        segment_lengths.append(end - start)

    segment_intervals = [max(1, int(math.ceil(length / target_spacing_mm))) for length in segment_lengths]
    # Points generated by segment intervals include each control point exactly
    # once plus intermediate bars within each segment.  Increase intervals on
    # the longest current spacing segments when a user asks for a higher minimum
    # bar count than the spacing rule would produce.
    while sum(segment_intervals) < int(min_bars):
        spacing_by_segment = [segment_lengths[i] / max(1, segment_intervals[i]) for i in range(len(segment_lengths))]
        index_to_increase = max(range(len(spacing_by_segment)), key=spacing_by_segment.__getitem__)
        segment_intervals[index_to_increase] += 1

    generated_distances: list[float] = []
    max_spacing = 0.0
    for segment_index, start in enumerate(control_distances):
        intervals = segment_intervals[segment_index]
        length = segment_lengths[segment_index]
        step = length / intervals
        max_spacing = max(max_spacing, step)
        for j in range(intervals):
            generated_distances.append(start + j * step)

    return _dedup_distances(generated_distances, perimeter_length_mm), max_spacing, len(control_distances)


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

    try:
        outer_boundary = _as_outer_polygon(geometry)
    except ValueError as exc:
        return PerimeterRebarLayoutResult(table=empty_table, errors=(str(exc),))

    offset_geom = outer_boundary.buffer(-float(edge_offset_mm), join_style=2, mitre_limit=2.0)
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

    distances, actual_spacing_mm, control_count = _corner_controlled_distances(
        layout_polygon,
        target_spacing_mm=float(target_spacing_mm),
        min_bars=int(min_bars),
    )
    generated_count = len(distances)
    if control_count:
        info.append(
            f"Corner-controlled layout: {control_count} section corner/control bar(s) placed before filling intermediate bars."
        )
    else:
        info.append("No geometric corner/control points were detected; uniform perimeter layout is used.")

    if actual_spacing_mm > target_spacing_mm * 1.15:
        warnings.append(
            f"Maximum generated spacing is {actual_spacing_mm:.1f} mm, more than 15% above the target {target_spacing_mm:.1f} mm."
        )
    if actual_spacing_mm < max(25.0, diameter_mm):
        warnings.append(
            f"Minimum generated spacing may be close; maximum segment spacing is {actual_spacing_mm:.1f} mm. Review clear spacing/detailing requirements."
        )

    rows: list[dict[str, object]] = []
    outside_count = 0
    void_count = 0
    hole_polygons = [Polygon([point.as_tuple() for point in hole]) for hole in geometry.holes]
    prefix = str(label_prefix or "B").strip() or "B"
    for index, distance in enumerate(distances):
        point = perimeter.interpolate(distance % perimeter_length_mm)
        if any(hole.covers(point) for hole in hole_polygons):
            void_count += 1
        elif not _point_is_effectively_inside(section, point):
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
                "Note": f"Auto perimeter: corner-controlled, offset={edge_offset_mm:g} mm, target spacing={target_spacing_mm:g} mm",
            }
        )

    if void_count:
        errors.append(
            f"{void_count} generated bar point(s) are inside a void/hole; reduce the offset, use manual input, or use a future inner-face layout."
        )
    if outside_count:
        errors.append(f"{outside_count} generated bar point(s) are outside concrete; use manual input or adjust the offset.")

    info.append(
        f"Generated {generated_count} bar(s) along an inward offset perimeter; maximum segment spacing ≈ {actual_spacing_mm:.1f} mm."
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
