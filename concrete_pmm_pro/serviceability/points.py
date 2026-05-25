"""Custom serviceability stress check point parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.errors import GEOSException

from concrete_pmm_pro.core.models import SectionGeometry
from concrete_pmm_pro.geometry.summary import to_shapely_polygon
from concrete_pmm_pro.serviceability.models import StressCheckPoint

ALLOWED_STRESS_POINT_TYPES = {
    "extreme_fiber",
    "reference",
    "tendon_zone",
    "web_flange_junction",
    "reentrant_corner",
    "construction_joint",
    "segmental_joint",
    "custom",
}


@dataclass(frozen=True)
class PointParseResult:
    points: list[StressCheckPoint] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return isinstance(value, str) and not value.strip()


def _blank_row(row: pd.Series) -> bool:
    return all(_is_blank(value) for value in row.to_dict().values())


def _as_bool(value: Any, default: bool) -> bool:
    if _is_blank(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "checked"}:
        return True
    if text in {"false", "no", "n", "0", "unchecked"}:
        return False
    return default


def _as_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _unique_name(name: str, used_names: set[str]) -> str:
    if name not in used_names:
        used_names.add(name)
        return name
    suffix = 2
    while f"{name} ({suffix})" in used_names:
        suffix += 1
    unique = f"{name} ({suffix})"
    used_names.add(unique)
    return unique


def custom_stress_check_points_from_dataframe(df: pd.DataFrame) -> PointParseResult:
    """Parse active custom SLS stress check points from an editable dataframe."""

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    points: list[StressCheckPoint] = []
    used_names: set[str] = set()
    auto_index = 1
    inactive_count = 0

    if df.empty:
        return PointParseResult(info=["No custom stress check point rows were provided."])

    for row_number, row in df.iterrows():
        if _blank_row(row):
            continue

        active = _as_bool(row.get("Active"), True)
        if not active:
            inactive_count += 1
            continue

        raw_name = "" if _is_blank(row.get("Name")) else str(row.get("Name")).strip()
        if not raw_name:
            raw_name = f"Custom-{auto_index}"
            auto_index += 1
            info.append(f"Row {row_number + 1}: blank name was set to {raw_name}.")

        name = _unique_name(raw_name, used_names)
        if name != raw_name:
            warnings.append(f"Row {row_number + 1}: duplicate name '{raw_name}' was renamed to '{name}'.")

        x_mm = _as_float(row.get("x_mm"))
        y_mm = _as_float(row.get("y_mm"))
        if x_mm is None:
            errors.append(f"Row {row_number + 1} ({name}): x_mm must be numeric.")
        if y_mm is None:
            errors.append(f"Row {row_number + 1} ({name}): y_mm must be numeric.")
        if x_mm is None or y_mm is None:
            continue

        raw_point_type = "custom" if _is_blank(row.get("Point Type")) else str(row.get("Point Type")).strip()
        point_type = raw_point_type if raw_point_type in ALLOWED_STRESS_POINT_TYPES else "custom"
        if point_type != raw_point_type:
            warnings.append(f"Row {row_number + 1} ({name}): unknown point type '{raw_point_type}' was set to custom.")

        points.append(
            StressCheckPoint(
                name=name,
                x_mm=x_mm,
                y_mm=y_mm,
                point_type=point_type,
                active=True,
                include_in_governing=_as_bool(row.get("Include in Governing"), True),
                source="user",
                note=None if _is_blank(row.get("Note")) else str(row.get("Note")).strip(),
            )
        )

    if inactive_count:
        info.append(f"Ignored {inactive_count} inactive custom stress check point row(s).")
    return PointParseResult(points=points, errors=errors, warnings=warnings, info=info)


def stress_check_points_to_dataframe(points: list[StressCheckPoint]) -> pd.DataFrame:
    """Convert stored custom stress check points to the editable UI table shape."""

    return pd.DataFrame(
        [
            {
                "Active": point.active,
                "Name": point.name,
                "x_mm": point.x_mm,
                "y_mm": point.y_mm,
                "Point Type": point.point_type,
                "Include in Governing": point.include_in_governing,
                "Note": point.note or "",
            }
            for point in points
        ],
        columns=["Active", "Name", "x_mm", "y_mm", "Point Type", "Include in Governing", "Note"],
    )


def dataframe_to_stress_check_points(df: pd.DataFrame) -> list[StressCheckPoint]:
    """Convert an editable table to persisted custom points, preserving inactive rows.

    Unlike custom_stress_check_points_from_dataframe(), this helper is for
    project persistence and keeps inactive rows when their coordinates are
    valid. Rows with missing/non-numeric coordinates are treated as temporary
    UI rows and are not serialized into project JSON.
    """

    points: list[StressCheckPoint] = []
    used_names: set[str] = set()
    auto_index = 1
    if df.empty:
        return points

    for _row_number, row in df.iterrows():
        if _blank_row(row):
            continue

        x_mm = _as_float(row.get("x_mm"))
        y_mm = _as_float(row.get("y_mm"))
        if x_mm is None or y_mm is None:
            continue

        raw_name = "" if _is_blank(row.get("Name")) else str(row.get("Name")).strip()
        if not raw_name:
            raw_name = f"Custom-{auto_index}"
            auto_index += 1
        name = _unique_name(raw_name, used_names)

        raw_point_type = "custom" if _is_blank(row.get("Point Type")) else str(row.get("Point Type")).strip()
        point_type = raw_point_type if raw_point_type in ALLOWED_STRESS_POINT_TYPES else "custom"

        points.append(
            StressCheckPoint(
                name=name,
                x_mm=x_mm,
                y_mm=y_mm,
                point_type=point_type,
                active=_as_bool(row.get("Active"), True),
                include_in_governing=_as_bool(row.get("Include in Governing"), True),
                source="user",
                note=None if _is_blank(row.get("Note")) else str(row.get("Note")).strip(),
            )
        )

    return points


def merge_default_and_custom_stress_check_points(
    default_points: list[StressCheckPoint],
    custom_points: list[StressCheckPoint],
    include_default_points: bool = True,
) -> list[StressCheckPoint]:
    """Merge default points first, followed by active custom points."""

    merged: list[StressCheckPoint] = []
    used_names: set[str] = set()
    source_points = list(default_points) if include_default_points else []
    source_points.extend(point for point in custom_points if point.active)

    for point in source_points:
        name = _unique_name(point.name, used_names)
        merged.append(point.model_copy(update={"name": name}))
    return merged


def validate_stress_check_points_against_geometry(
    points: list[StressCheckPoint],
    section_geometry: SectionGeometry | None,
) -> tuple[list[str], list[str]]:
    """Validate stress check points against concrete area and voids."""

    errors: list[str] = []
    warnings: list[str] = []
    if section_geometry is None:
        warnings.append("Section geometry is not available; stress check point geometry validation skipped.")
        return errors, warnings

    try:
        section = to_shapely_polygon(section_geometry)
        outer = Polygon([point.as_tuple() for point in section_geometry.outer_polygon])
        holes = [Polygon([point.as_tuple() for point in hole]) for hole in section_geometry.holes]
    except (GEOSException, TypeError, ValueError) as exc:  # defensive around Shapely geometry construction
        errors.append(f"Stress check point geometry validation failed: {exc}")
        return errors, warnings

    if section.is_empty or not section.is_valid:
        errors.append("Section geometry is invalid; stress check point geometry validation failed.")
        return errors, warnings

    for point in points:
        shapely_point = Point(point.x_mm, point.y_mm)
        if not outer.covers(shapely_point):
            errors.append(f"Stress check point '{point.name}' is outside concrete.")
            continue
        if any(hole.contains(shapely_point) for hole in holes):
            errors.append(f"Stress check point '{point.name}' is inside a void/hole.")
            continue
        if not section.covers(shapely_point):
            errors.append(f"Stress check point '{point.name}' is outside the net concrete section.")

    return errors, warnings
