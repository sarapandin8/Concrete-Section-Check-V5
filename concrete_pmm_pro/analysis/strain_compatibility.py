"""Strain compatibility utilities for the RC PMM prototype.

Sign convention used here:
- Concrete/rebar compression is positive.
- Rebar tension is negative.
- x is positive to the right and y is positive upward.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from typing import Any

from shapely.geometry import Point, Polygon
from shapely.errors import GEOSException


@dataclass(frozen=True)
class ProjectionFrame:
    nx: float
    ny: float
    tx: float
    ty: float
    min_s: float
    max_s: float
    min_r: float
    max_r: float

    @property
    def projected_depth_mm(self) -> float:
        return self.max_s - self.min_s


def projection_frame(polygon: Polygon, theta_rad: float) -> ProjectionFrame:
    nx = math.cos(theta_rad)
    ny = math.sin(theta_rad)
    tx = -ny
    ty = nx
    coords = list(polygon.exterior.coords)
    for interior in polygon.interiors:
        coords.extend(interior.coords)
    projections = [x * nx + y * ny for x, y in coords]
    transverse = [x * tx + y * ty for x, y in coords]
    return ProjectionFrame(
        nx=nx,
        ny=ny,
        tx=tx,
        ty=ty,
        min_s=min(projections),
        max_s=max(projections),
        min_r=min(transverse),
        max_r=max(transverse),
    )


def transform_sr_to_xy(frame: ProjectionFrame, s: float, r: float) -> tuple[float, float]:
    return (frame.nx * s + frame.tx * r, frame.ny * s + frame.ty * r)


def steel_strain_at_point(x_mm: float, y_mm: float, frame: ProjectionFrame, c_mm: float, ecu: float) -> float:
    s = x_mm * frame.nx + y_mm * frame.ny
    distance_from_extreme_compression = frame.max_s - s
    return ecu * (1.0 - distance_from_extreme_compression / c_mm)


def compression_block_polygon(section_polygon: Polygon, frame: ProjectionFrame, block_depth_mm: float) -> Polygon:
    if block_depth_mm <= 0:
        return Polygon()

    span = max(frame.projected_depth_mm, frame.max_r - frame.min_r, 1.0)
    s_boundary = frame.max_s - block_depth_mm
    s_far = frame.max_s + 10.0 * span
    r_min = frame.min_r - 10.0 * span
    r_max = frame.max_r + 10.0 * span
    half_plane = Polygon(
        [
            transform_sr_to_xy(frame, s_boundary, r_min),
            transform_sr_to_xy(frame, s_far, r_min),
            transform_sr_to_xy(frame, s_far, r_max),
            transform_sr_to_xy(frame, s_boundary, r_max),
        ]
    )
    clipped = section_polygon.intersection(half_plane)
    if clipped.is_empty:
        return Polygon()
    return clipped


def is_point_inside_compression_block(x_mm: float, y_mm: float, compression_polygon: Any) -> bool:
    """Return True when a point is inside or on the compression block boundary."""

    try:
        if compression_polygon is None or compression_polygon.is_empty or not compression_polygon.is_valid:
            return False
        return bool(compression_polygon.covers(Point(float(x_mm), float(y_mm))))
    except (GEOSException, TypeError, ValueError):
        return False


def rebar_net_force_n(
    area_mm2: float,
    steel_stress_MPa: float,
    fc_MPa: float,
    inside_compression_block: bool,
    subtract_displaced_concrete: bool = True,
) -> tuple[float, dict[str, float | bool]]:
    """Return ordinary rebar net force with optional displaced concrete subtraction.

    Compression is positive and tension is negative. If a bar is inside the
    Whitney compression block, subtracting 0.85 f'c avoids double counting the
    concrete stress already present in the compression block.
    """

    if area_mm2 <= 0.0:
        raise ValueError("area_mm2 must be positive.")
    if fc_MPa <= 0.0:
        raise ValueError("fc_MPa must be positive.")

    concrete_stress_subtracted = 0.85 * fc_MPa if subtract_displaced_concrete and inside_compression_block else 0.0
    net_stress = steel_stress_MPa - concrete_stress_subtracted
    return area_mm2 * net_stress, {
        "steel_stress_MPa": float(steel_stress_MPa),
        "concrete_stress_subtracted_MPa": concrete_stress_subtracted,
        "net_stress_MPa": net_stress,
        "inside_compression_block": inside_compression_block,
        "subtract_displaced_concrete": subtract_displaced_concrete,
    }
