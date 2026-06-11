"""PMM Mux-Muy slice envelope helpers.

These helpers clean and validate selected-Pu PMM slice boundaries before the
dashboard and prototype directional demand/capacity check consume them. They
are still prototype engineering-review tools, not production certification.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import pandas as pd
from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, Point, Polygon
from shapely.errors import GEOSException

from concrete_pmm_pro.analysis.warnings import CONVEX_HULL_FALLBACK_WARNING

PASS = "PASS"
OUT_OF_RANGE = "OUT_OF_RANGE"
NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class SliceEnvelopeResult:
    envelope_df: pd.DataFrame
    method: str
    point_count_input: int
    point_count_output: int
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)
    is_valid: bool = False
    used_convex_hull: bool = False
    detected_self_crossing: bool = False


def compute_polar_angle_and_radius(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with polar angle and radius from phiMnx/phiMny."""

    required = {"phiMnx_kNm", "phiMny_kNm"}
    if not required.issubset(df.columns):
        raise ValueError("Slice dataframe must include phiMnx_kNm and phiMny_kNm.")
    result = df.copy()
    result["angle_rad"] = result.apply(lambda row: math.atan2(float(row["phiMny_kNm"]), float(row["phiMnx_kNm"])), axis=1)
    result["radius_kNm"] = result.apply(lambda row: math.hypot(float(row["phiMnx_kNm"]), float(row["phiMny_kNm"])), axis=1)
    return result


def remove_near_duplicate_slice_points(
    slice_df: pd.DataFrame,
    angle_tol_rad: float = 1.0e-4,
    radius_tol_kNm: float = 1.0e-3,
) -> pd.DataFrame:
    """Remove near-duplicate angular points, keeping the largest radius."""

    if slice_df.empty:
        return slice_df.copy()
    working = (
        compute_polar_angle_and_radius(slice_df)
        if not {"angle_rad", "radius_kNm"}.issubset(slice_df.columns)
        else slice_df.copy()
    )
    working = working.sort_values(["angle_rad", "radius_kNm"], ascending=[True, False])
    kept_rows: list[pd.Series] = []
    current_angle: float | None = None
    current_row: pd.Series | None = None

    for _, row in working.iterrows():
        angle = float(row["angle_rad"])
        radius = float(row["radius_kNm"])
        if current_row is None or current_angle is None or abs(angle - current_angle) > angle_tol_rad:
            if current_row is not None:
                kept_rows.append(current_row)
            current_angle = angle
            current_row = row
            continue
        if radius > float(current_row["radius_kNm"]) + radius_tol_kNm:
            current_row = row

    if current_row is not None:
        kept_rows.append(current_row)
    if not kept_rows:
        return working.iloc[0:0].copy()
    return pd.DataFrame(kept_rows).reset_index(drop=True)


def detect_self_crossing_boundary(envelope_df: pd.DataFrame) -> bool:
    """Return True when a closed boundary appears invalid or self-crossing."""

    if envelope_df.empty or len(envelope_df) < 4:
        return False
    try:
        coords = [(float(row.phiMnx_kNm), float(row.phiMny_kNm)) for row in envelope_df.itertuples()]
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        line = LineString(coords)
        polygon = Polygon(coords)
        return (not line.is_simple) or (not polygon.is_valid)
    except (GEOSException, TypeError, ValueError):
        return False


def _clean_slice_points(slice_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    warnings: list[str] = []
    if slice_df.empty:
        return slice_df.copy(), ["Slice dataframe is empty."]
    polar = compute_polar_angle_and_radius(slice_df)
    numeric_columns = ["phiMnx_kNm", "phiMny_kNm", "angle_rad", "radius_kNm"]
    cleaned = polar.copy()
    for column in numeric_columns:
        cleaned = cleaned[pd.notna(cleaned[column])]
        cleaned = cleaned[cleaned[column].map(lambda value: math.isfinite(float(value)))]
    before_radius = len(cleaned)
    cleaned = cleaned[cleaned["radius_kNm"] > 1.0e-9].copy()
    if len(cleaned) < before_radius:
        warnings.append("Zero or near-zero radius slice points were removed.")
    if "source_method" not in cleaned.columns:
        cleaned["source_method"] = slice_df.attrs.get("method", "unknown")
    cleaned = remove_near_duplicate_slice_points(cleaned)
    return cleaned, warnings


def _boundary_warnings(cleaned: pd.DataFrame) -> tuple[list[str], bool]:
    warnings: list[str] = []
    if cleaned.empty or len(cleaned) < 2:
        return warnings, False

    angles = [float(value) for value in cleaned["angle_rad"].to_list()]
    radii = [float(value) for value in cleaned["radius_kNm"].to_list()]
    duplicate_angles = any(abs(right - left) <= 1.0e-4 for left, right in zip(angles[:-1], angles[1:]))
    if duplicate_angles:
        warnings.append("Duplicate or near-duplicate angles remain in slice envelope.")

    wrapped_angles = angles + [angles[0] + 2.0 * math.pi]
    gaps = [right - left for left, right in zip(wrapped_angles[:-1], wrapped_angles[1:])]
    angular_coverage = 2.0 * math.pi - max(gaps)
    if angular_coverage < math.pi:
        warnings.append("Angular coverage is limited.")
    elif angular_coverage < 1.5 * math.pi:
        warnings.append("Angular coverage is moderate; review slice envelope.")

    large_jump = False
    wrapped_radii = radii + [radii[0]]
    median_radius = sorted(radii)[len(radii) // 2]
    for left, right in zip(wrapped_radii[:-1], wrapped_radii[1:]):
        if median_radius > 0.0 and abs(right - left) > 0.75 * median_radius:
            large_jump = True
            break
    if large_jump:
        warnings.append("Large radius jump detected in slice envelope.")
    return warnings, True



def _positive_ray_intersections(geometry: object, alpha_rad: float) -> list[float]:
    """Return positive distances where a ray from the origin intersects geometry.

    The PMM D/C check needs the boundary distance in the demand moment
    direction.  A polygon/ray intersection is more robust than polar radius
    interpolation for rectangular or faceted envelopes because it intersects the
    actual Mx-My boundary segment rather than interpolating radii between
    neighboring angular vertices.
    """

    direction_x = math.cos(alpha_rad)
    direction_y = math.sin(alpha_rad)
    distances: list[float] = []

    def add_point(x: float, y: float) -> None:
        projection = x * direction_x + y * direction_y
        perpendicular = abs(-direction_y * x + direction_x * y)
        if projection > 1.0e-9 and perpendicular <= max(1.0e-6, 1.0e-8 * abs(projection)):
            distances.append(float(projection))

    def walk(geom: object) -> None:
        if getattr(geom, "is_empty", False):
            return
        if isinstance(geom, Point):
            add_point(float(geom.x), float(geom.y))
            return
        if isinstance(geom, MultiPoint):
            for part in geom.geoms:
                add_point(float(part.x), float(part.y))
            return
        if isinstance(geom, LineString):
            coords = list(geom.coords)
            for x, y in coords:
                add_point(float(x), float(y))
            return
        if isinstance(geom, MultiLineString):
            for part in geom.geoms:
                walk(part)
            return
        if isinstance(geom, GeometryCollection):
            for part in geom.geoms:
                walk(part)
            return

    walk(geometry)
    return sorted(set(round(distance, 9) for distance in distances))


def _estimate_capacity_by_ray_intersection(
    envelope: SliceEnvelopeResult,
    alpha_rad: float,
) -> tuple[float | None, list[str]]:
    """Estimate boundary radius from the actual PMM envelope polygon.

    Returns capacity in kN-m and diagnostic warnings.  It intentionally uses
    the envelope boundary itself; if a clean ray intersection cannot be formed,
    the caller may fall back to angular polar interpolation.
    """

    warnings: list[str] = []
    if envelope.envelope_df.empty or len(envelope.envelope_df) < 3:
        return None, ["Slice envelope has too few points for ray-intersection capacity."]

    try:
        polar_df = compute_polar_angle_and_radius(envelope.envelope_df)
        max_radius = float(polar_df["radius_kNm"].max())
        if not math.isfinite(max_radius) or max_radius <= 0.0:
            return None, ["Slice envelope has no positive radius for ray-intersection capacity."]
        coords = [(float(row.phiMnx_kNm), float(row.phiMny_kNm)) for row in polar_df.itertuples()]
        polygon = Polygon(coords)
        if not polygon.is_valid or polygon.is_empty:
            return None, ["Slice envelope polygon is invalid for ray-intersection capacity."]
        ray_length = max(2.0 * max_radius, max_radius + 1.0)
        ray = LineString([(0.0, 0.0), (ray_length * math.cos(alpha_rad), ray_length * math.sin(alpha_rad))])
        intersections = _positive_ray_intersections(polygon.boundary.intersection(ray), alpha_rad)
        if not intersections:
            return None, ["Demand direction ray did not intersect the slice envelope boundary."]
        if len(intersections) > 1:
            warnings.append(
                "Multiple positive ray intersections detected; nearest boundary used to avoid overestimating directional capacity."
            )
        return min(intersections), warnings
    except (GEOSException, TypeError, ValueError, ArithmeticError) as exc:
        return None, [f"Ray-intersection slice capacity failed: {exc}"]

def build_convex_hull_envelope(slice_df: pd.DataFrame) -> SliceEnvelopeResult:
    """Build a convex hull fallback envelope from slice points."""

    warnings = [CONVEX_HULL_FALLBACK_WARNING]
    try:
        cleaned, clean_warnings = _clean_slice_points(slice_df)
    except (GEOSException, TypeError, ValueError) as exc:
        cleaned = slice_df.iloc[0:0].copy()
        clean_warnings = [f"Convex hull fallback input cleanup failed: {exc}"]
    warnings.extend(clean_warnings)
    if len(cleaned) < 3:
        return SliceEnvelopeResult(
            envelope_df=cleaned,
            method="convex_hull",
            point_count_input=len(slice_df),
            point_count_output=len(cleaned),
            warnings=warnings + ["Too few points for convex hull envelope."],
            info=[],
            is_valid=False,
            used_convex_hull=True,
            detected_self_crossing=False,
        )

    try:
        points = [(float(row.phiMnx_kNm), float(row.phiMny_kNm)) for row in cleaned.itertuples()]
        hull = MultiPoint(points).convex_hull
        if hull.geom_type == "Polygon":
            coords = list(hull.exterior.coords)[:-1]
        elif hull.geom_type == "LineString":
            coords = list(hull.coords)
        else:
            coords = []
        envelope = pd.DataFrame([{"phiMnx_kNm": x, "phiMny_kNm": y, "source_method": "convex_hull"} for x, y in coords])
        if not envelope.empty:
            envelope = compute_polar_angle_and_radius(envelope).sort_values("angle_rad").reset_index(drop=True)
        is_valid = len(envelope) >= 3
        return SliceEnvelopeResult(
            envelope_df=envelope,
            method="convex_hull",
            point_count_input=len(slice_df),
            point_count_output=len(envelope),
            warnings=warnings,
            info=[f"Convex hull envelope contains {len(envelope)} point(s)."],
            is_valid=is_valid,
            used_convex_hull=True,
            detected_self_crossing=False,
        )
    except (GEOSException, TypeError, ValueError) as exc:
        return SliceEnvelopeResult(
            envelope_df=cleaned,
            method="convex_hull",
            point_count_input=len(slice_df),
            point_count_output=len(cleaned),
            warnings=warnings + [f"Convex hull fallback failed: {exc}"],
            info=[],
            is_valid=False,
            used_convex_hull=True,
            detected_self_crossing=False,
        )


def build_slice_envelope(
    slice_df: pd.DataFrame,
    method: str = "polar_max",
) -> SliceEnvelopeResult:
    """Build a cleaned PMM slice envelope."""

    if method == "convex_hull":
        return build_convex_hull_envelope(slice_df)
    if method != "polar_max":
        raise ValueError("Slice envelope method must be polar_max or convex_hull.")

    cleaned, warnings = _clean_slice_points(slice_df)
    cleaned = cleaned.sort_values("angle_rad").reset_index(drop=True)
    boundary_warnings, has_coverage = _boundary_warnings(cleaned)
    warnings.extend(boundary_warnings)
    too_few = len(cleaned) < 8
    if too_few:
        warnings.append("Too few slice envelope points.")

    self_crossing = detect_self_crossing_boundary(cleaned)
    if self_crossing:
        warnings.append("Slice boundary may be noisy or self-crossing.")

    is_valid = (not too_few) and has_coverage and (not self_crossing)
    if not is_valid and len(cleaned) >= 3:
        hull_result = build_convex_hull_envelope(cleaned)
        merged_warnings = warnings + hull_result.warnings
        return SliceEnvelopeResult(
            envelope_df=hull_result.envelope_df,
            method=hull_result.method,
            point_count_input=len(slice_df),
            point_count_output=hull_result.point_count_output,
            warnings=list(dict.fromkeys(merged_warnings)),
            info=hull_result.info,
            is_valid=hull_result.is_valid,
            used_convex_hull=True,
            detected_self_crossing=self_crossing,
        )

    return SliceEnvelopeResult(
        envelope_df=cleaned,
        method="polar_max",
        point_count_input=len(slice_df),
        point_count_output=len(cleaned),
        warnings=list(dict.fromkeys(warnings)),
        info=[f"Polar max envelope contains {len(cleaned)} point(s)."],
        is_valid=is_valid,
        used_convex_hull=False,
        detected_self_crossing=self_crossing,
    )


def _angle_0_to_2pi(angle_rad: float) -> float:
    return angle_rad % (2.0 * math.pi)


def estimate_directional_capacity_from_envelope(
    envelope: SliceEnvelopeResult,
    Mux_kNm: float,
    Muy_kNm: float,
) -> dict[str, object]:
    """Estimate directional moment capacity from a cleaned slice envelope."""

    demand_Mu_kNm = math.hypot(Mux_kNm, Muy_kNm)
    alpha_rad = math.atan2(Muy_kNm, Mux_kNm)
    warnings = list(envelope.warnings)
    if demand_Mu_kNm <= 1.0e-12:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "slice_envelope",
            "status": NOT_CHECKED,
            "warnings": warnings + ["Directional capacity from envelope requires nonzero moment demand."],
        }
    if not envelope.is_valid or envelope.envelope_df.empty:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "slice_envelope",
            "status": NOT_CHECKED,
            "warnings": warnings + ["Slice envelope is invalid; directional capacity was not checked from envelope."],
        }

    capacity_radius, ray_warnings = _estimate_capacity_by_ray_intersection(envelope, alpha_rad)
    if capacity_radius is not None and capacity_radius > 0.0:
        return {
            "capacity_phiMn_kNm": capacity_radius,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": demand_Mu_kNm / capacity_radius,
            "alpha_rad": alpha_rad,
            "method": "slice_envelope_ray",
            "status": PASS,
            "warnings": warnings + ray_warnings,
        }

    # Fallback: angular interpolation is retained only as a secondary method for
    # envelopes that cannot form a valid polygon/ray intersection.  This keeps
    # legacy behavior available while making the primary D/C path more faithful
    # to the actual Mx-My boundary segment.
    polar_df = compute_polar_angle_and_radius(envelope.envelope_df).sort_values("angle_rad")
    polar_points = [
        (_angle_0_to_2pi(float(row.angle_rad)), float(row.radius_kNm))
        for row in polar_df.itertuples()
        if float(row.radius_kNm) > 0.0
    ]
    if len(polar_points) < 2:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "slice_envelope_ray",
            "status": NOT_CHECKED,
            "warnings": warnings + ray_warnings + ["Slice envelope has too few positive-radius points."],
        }

    polar_points = sorted(polar_points, key=lambda item: item[0])
    alpha = _angle_0_to_2pi(alpha_rad)
    wrapped_points = polar_points + [(polar_points[0][0] + 2.0 * math.pi, polar_points[0][1])]
    if alpha < polar_points[0][0]:
        alpha += 2.0 * math.pi

    capacity_radius = None
    for (angle_1, radius_1), (angle_2, radius_2) in zip(wrapped_points[:-1], wrapped_points[1:]):
        if angle_1 <= alpha <= angle_2:
            if abs(angle_2 - angle_1) <= 1.0e-12:
                capacity_radius = max(radius_1, radius_2)
            else:
                ratio = (alpha - angle_1) / (angle_2 - angle_1)
                capacity_radius = radius_1 + ratio * (radius_2 - radius_1)
            break

    if capacity_radius is None or capacity_radius <= 0.0:
        return {
            "capacity_phiMn_kNm": None,
            "demand_Mu_kNm": demand_Mu_kNm,
            "dcr": None,
            "alpha_rad": alpha_rad,
            "method": "slice_envelope_ray",
            "status": OUT_OF_RANGE,
            "warnings": warnings + ray_warnings + ["Could not bracket demand angle on slice envelope."],
        }
    return {
        "capacity_phiMn_kNm": capacity_radius,
        "demand_Mu_kNm": demand_Mu_kNm,
        "dcr": demand_Mu_kNm / capacity_radius,
        "alpha_rad": alpha_rad,
        "method": "slice_envelope_polar_fallback",
        "status": PASS,
        "warnings": warnings + ray_warnings + ["Ray-intersection capacity was unavailable; polar radius interpolation fallback used."],
    }
