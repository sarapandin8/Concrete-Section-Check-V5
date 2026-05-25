"""Cracking and tension-zone classification from elastic SLS stress results.

Milestone 4.7 intentionally does not redistribute stresses or solve a cracked
transformed section. It classifies the existing service stress check points so
future cracked-section work has a stable data contract.
"""

from __future__ import annotations

from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from concrete_pmm_pro.serviceability.models import ServiceabilitySettings, ServiceabilitySummary

CrackPointClassification = Literal[
    "COMPRESSION",
    "ZERO",
    "TENSION_WITHIN_LIMIT",
    "TENSION_EXCEEDS_LIMIT",
    "NO_TENSION_VIOLATION",
    "DECOMPRESSION_VIOLATION",
]

CrackOverallClassification = Literal[
    "UNCRACKED_BY_CHECK_POINTS",
    "TENSION_PRESENT",
    "TENSION_EXCEEDS_LIMIT",
    "NO_TENSION_VIOLATED",
    "DECOMPRESSION_VIOLATED",
    "NOT_CHECKED",
]

_EXTREME_FIBER_POINT_NAMES = {
    "top fiber",
    "bottom fiber",
    "left fiber",
    "right fiber",
}


class CrackClassificationPoint(BaseModel):
    """Classification for one SLS stress result point."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    combo_name: str
    point_name: str
    x_mm: float
    y_mm: float
    stress_MPa: float
    section_basis: str | None = None
    point_type: str | None = None
    source: str | None = None
    include_in_governing: bool = True
    is_tension: bool
    exceeds_tension_limit: bool
    no_tension_violation: bool
    decompression_violation: bool
    classification: CrackPointClassification
    message: str


class CrackClassificationSummary(BaseModel):
    """Summary of tension/cracking risk at selected SLS stress check points."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    points: list[CrackClassificationPoint] = Field(default_factory=list)
    overall_classification: CrackOverallClassification = "NOT_CHECKED"
    tension_point_count: int = 0
    max_tension_MPa: float = 0.0
    governing_combo: str | None = None
    governing_point: str | None = None
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)


def _is_extreme_fiber_point(point_name: str) -> bool:
    return point_name.strip().lower() in _EXTREME_FIBER_POINT_NAMES


def _governing_eligible(point: CrackClassificationPoint, settings: ServiceabilitySettings) -> bool:
    if not point.include_in_governing:
        return False
    if settings.critical_point_filter == "extreme_fibers_only":
        return point.point_type == "extreme_fiber" or _is_extreme_fiber_point(point.point_name)
    return True


def _point_message(classification: str, stress_MPa: float, limit_MPa: float | None) -> str:
    if classification == "DECOMPRESSION_VIOLATION":
        return "Decompression requirement violated by tensile stress at this check point."
    if classification == "NO_TENSION_VIOLATION":
        return "No-tension requirement violated by tensile stress at this check point."
    if classification == "TENSION_EXCEEDS_LIMIT":
        if limit_MPa is None:
            return "Concrete tensile stress exceeds the selected limit."
        return f"Concrete tensile stress {stress_MPa:.3f} MPa exceeds limit {limit_MPa:.3f} MPa."
    if classification == "TENSION_WITHIN_LIMIT":
        return "Concrete tensile stress is present but within the selected limit."
    if classification == "ZERO":
        return "Stress is near zero at this check point."
    return "Concrete stress is compressive at this check point."


def _classify_point(
    *,
    stress_MPa: float,
    limit_MPa: float | None,
    settings: ServiceabilitySettings,
) -> tuple[str, bool, bool, bool, bool, str]:
    """Classify one point under the SLS convention.

    Compression is negative and tension is positive. No-tension and
    decompression are treated as tensile-stress violations at selected points
    in Milestone 4.7; full cracked-section redistribution is future work.
    """

    tol = settings.stress_zero_tolerance_MPa
    no_tension_required = settings.no_tension_check or settings.concrete_tension_limit_mode == "no_tension"
    decompression_required = settings.decompression_check

    if stress_MPa < -tol:
        classification = "COMPRESSION"
    elif abs(stress_MPa) <= tol:
        classification = "ZERO"
    else:
        if decompression_required:
            classification = "DECOMPRESSION_VIOLATION"
        elif no_tension_required:
            classification = "NO_TENSION_VIOLATION"
        elif limit_MPa is not None and limit_MPa > tol and stress_MPa > limit_MPa:
            classification = "TENSION_EXCEEDS_LIMIT"
        elif limit_MPa is not None and limit_MPa <= tol and not settings.allow_tension:
            classification = "NO_TENSION_VIOLATION"
        else:
            classification = "TENSION_WITHIN_LIMIT"

    is_tension = stress_MPa > tol
    exceeds_tension_limit = (
        is_tension
        and limit_MPa is not None
        and limit_MPa > tol
        and stress_MPa > limit_MPa
    )
    no_tension_violation = is_tension and (classification == "NO_TENSION_VIOLATION")
    decompression_violation = is_tension and (classification == "DECOMPRESSION_VIOLATION")
    message = _point_message(classification, stress_MPa, limit_MPa)
    return (
        classification,
        is_tension,
        exceeds_tension_limit,
        no_tension_violation,
        decompression_violation,
        message,
    )


def _overall_classification(
    points: list[CrackClassificationPoint],
    settings: ServiceabilitySettings,
) -> CrackOverallClassification:
    governing_points = [point for point in points if _governing_eligible(point, settings)]
    if not governing_points:
        return "NOT_CHECKED"
    classifications = {point.classification for point in governing_points}
    if "DECOMPRESSION_VIOLATION" in classifications:
        return "DECOMPRESSION_VIOLATED"
    if "NO_TENSION_VIOLATION" in classifications:
        return "NO_TENSION_VIOLATED"
    if "TENSION_EXCEEDS_LIMIT" in classifications:
        return "TENSION_EXCEEDS_LIMIT"
    if any(point.is_tension for point in governing_points):
        return "TENSION_PRESENT"
    return "UNCRACKED_BY_CHECK_POINTS"


def _governing_tension_point(
    points: list[CrackClassificationPoint],
    settings: ServiceabilitySettings,
) -> CrackClassificationPoint | None:
    governing_points = [point for point in points if _governing_eligible(point, settings)]
    if not governing_points:
        return None
    priority = {
        "DECOMPRESSION_VIOLATION": 5,
        "NO_TENSION_VIOLATION": 4,
        "TENSION_EXCEEDS_LIMIT": 3,
        "TENSION_WITHIN_LIMIT": 2,
        "ZERO": 1,
        "COMPRESSION": 0,
    }
    tension_or_violation = [point for point in governing_points if point.is_tension or priority[point.classification] >= 3]
    if not tension_or_violation:
        return None
    return max(tension_or_violation, key=lambda point: (priority[point.classification], point.stress_MPa))


def classify_service_stress_results_for_cracking(
    serviceability_summary: ServiceabilitySummary,
    settings: ServiceabilitySettings,
) -> CrackClassificationSummary:
    """Classify tension/cracking risk from existing SLS stress results."""

    warnings = [
        "Cracked section analysis is not implemented yet.",
        "This classification is based only on selected stress check points.",
        "A section may crack between check points if not sufficiently sampled.",
    ]
    info: list[str] = []
    source_results = list(serviceability_summary.stress_results)
    if settings.critical_point_filter == "extreme_fibers_only":
        info.append("Critical point filter is extreme_fibers_only; only extreme-fiber points govern classification.")

    points: list[CrackClassificationPoint] = []
    for result in source_results:
        stress = result.total_stress_MPa if result.total_stress_MPa is not None else result.stress_MPa
        if stress is None:
            continue
        classification, is_tension, exceeds_limit, no_tension_violation, decompression_violation, message = _classify_point(
            stress_MPa=float(stress),
            limit_MPa=result.limit_MPa,
            settings=settings,
        )
        points.append(
            CrackClassificationPoint(
                combo_name=result.combo_name,
                point_name=result.point_name,
                x_mm=result.x_mm,
                y_mm=result.y_mm,
                stress_MPa=float(stress),
                section_basis=result.section_basis,
                point_type=result.point_type,
                source=result.point_source,
                include_in_governing=result.include_in_governing,
                is_tension=is_tension,
                exceeds_tension_limit=exceeds_limit,
                no_tension_violation=no_tension_violation,
                decompression_violation=decompression_violation,
                classification=classification,
                message=message,
            )
        )

    tension_points = [point for point in points if point.is_tension]
    governing = _governing_tension_point(points, settings)
    return CrackClassificationSummary(
        points=points,
        overall_classification=_overall_classification(points, settings),
        tension_point_count=len(tension_points),
        max_tension_MPa=max((point.stress_MPa for point in tension_points), default=0.0),
        governing_combo=None if governing is None else governing.combo_name,
        governing_point=None if governing is None else governing.point_name,
        warnings=warnings,
        info=info,
    )


def crack_classification_to_dataframe(summary: CrackClassificationSummary) -> pd.DataFrame:
    """Return cracking/tension classification results for display and CSV export."""

    columns = [
        "Combo",
        "Point",
        "x_mm",
        "y_mm",
        "Stress_MPa",
        "Section Basis",
        "Point Type",
        "Source",
        "Include in Governing",
        "Is Tension",
        "Exceeds Tension Limit",
        "No-Tension Violation",
        "Decompression Violation",
        "Classification",
        "Message",
    ]
    rows = [
        {
            "Combo": point.combo_name,
            "Point": point.point_name,
            "x_mm": point.x_mm,
            "y_mm": point.y_mm,
            "Stress_MPa": point.stress_MPa,
            "Section Basis": point.section_basis,
            "Point Type": point.point_type,
            "Source": point.source,
            "Include in Governing": point.include_in_governing,
            "Is Tension": point.is_tension,
            "Exceeds Tension Limit": point.exceeds_tension_limit,
            "No-Tension Violation": point.no_tension_violation,
            "Decompression Violation": point.decompression_violation,
            "Classification": point.classification,
            "Message": point.message,
        }
        for point in summary.points
    ]
    return pd.DataFrame(rows, columns=columns)
