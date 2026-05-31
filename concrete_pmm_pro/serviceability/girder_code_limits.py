"""Beam/Girder service-stress code-limit preview helpers.

CODE.SLS.LIMIT1 adds a deliberately small, pure-Python limit-check framework
for the Beam/Girder SLS preview workspace.  The helpers are intended to make
code selection, stress-sign handling, and PASS/FAIL reporting explicit before
full project-specific AASHTO/ACI clause calibration is implemented.

Important scope guard:
- This module does not generate loads or stages.
- This module does not change PMM, prestress, rebar, report, or geometry logic.
- Default profiles are editable preview profiles and must be verified against
  the governing project specification and code edition before final design.

Stress convention:
- compression stress is negative
- tension stress is positive
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

GirderSLSCode = Literal["AASHTO LRFD Bridge", "ACI 318"]
GirderSLSStage = Literal["Transfer", "Service / Final", "User-defined"]
TensionLimitMode = Literal["No tension", "sqrt(fc) ratio", "User-defined"]
StressLimitStatus = Literal["PASS", "FAIL", "NOT_CHECKED"]

DEFAULT_GIRDER_SLS_CODES: tuple[GirderSLSCode, ...] = ("AASHTO LRFD Bridge", "ACI 318")
DEFAULT_GIRDER_SLS_STAGES: tuple[GirderSLSStage, ...] = ("Transfer", "Service / Final", "User-defined")
DEFAULT_TENSION_LIMIT_MODES: tuple[TensionLimitMode, ...] = ("No tension", "sqrt(fc) ratio", "User-defined")


@dataclass(frozen=True)
class GirderServiceStressLimitProfile:
    """Concrete service-stress limit profile for one Beam/Girder preview check."""

    code: GirderSLSCode
    stage: GirderSLSStage
    compression_limit_ratio: float
    tension_limit_mode: TensionLimitMode
    tension_sqrt_fc_ratio: float = 0.0
    tension_limit_MPa: float = 0.0
    stress_zero_tolerance_MPa: float = 5.0e-4
    clause_note: str = ""
    limitation_note: str = ""

    def compression_limit_MPa(self, fc_MPa: float) -> float:
        _require_positive("fc_MPa", fc_MPa)
        _require_positive("compression_limit_ratio", self.compression_limit_ratio)
        return float(self.compression_limit_ratio) * float(fc_MPa)

    def tension_allowable_MPa(self, fc_MPa: float) -> float:
        _require_positive("fc_MPa", fc_MPa)
        if self.tension_limit_mode == "No tension":
            return 0.0
        if self.tension_limit_mode == "User-defined":
            if float(self.tension_limit_MPa) < 0.0:
                raise ValueError("tension_limit_MPa must not be negative.")
            return float(self.tension_limit_MPa)
        if float(self.tension_sqrt_fc_ratio) < 0.0:
            raise ValueError("tension_sqrt_fc_ratio must not be negative.")
        return float(self.tension_sqrt_fc_ratio) * math.sqrt(float(fc_MPa))


@dataclass(frozen=True)
class GirderStressLimitPointResult:
    """Limit-check result for one reported fiber stress."""

    fiber: str
    stress_MPa: float
    stress_type: str
    compression_limit_MPa: float
    tension_limit_MPa: float
    utilization: float | None
    status: StressLimitStatus
    message: str


@dataclass(frozen=True)
class GirderServiceStressLimitCheckResult:
    """Limit-check result for one Beam/Girder stress preview case."""

    profile: GirderServiceStressLimitProfile
    fc_MPa: float
    points: tuple[GirderStressLimitPointResult, ...]
    overall_status: StressLimitStatus
    warnings: tuple[str, ...] = ()

    @property
    def max_utilization(self) -> float | None:
        values = [point.utilization for point in self.points if point.utilization is not None]
        return max(values) if values else None

    @property
    def failed_count(self) -> int:
        return sum(1 for point in self.points if point.status == "FAIL")


@dataclass(frozen=True)
class StressLimitInputRow:
    """Simple stress row accepted by the pure limit checker."""

    fiber: str
    stress_MPa: float


def _require_positive(name: str, value: float) -> None:
    if not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a positive finite value.")


def _require_finite(name: str, value: float) -> None:
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite.")


def default_girder_sls_limit_profile(
    code: GirderSLSCode = "AASHTO LRFD Bridge",
    stage: GirderSLSStage = "Service / Final",
) -> GirderServiceStressLimitProfile:
    """Return an editable default profile for one code/stage combination.

    The values are intentionally centralized here so future clause-calibrated
    milestones can update them without touching the UI or stress kernels.
    """

    if code not in DEFAULT_GIRDER_SLS_CODES:
        raise ValueError(f"Unsupported girder SLS code profile: {code!r}")
    if stage not in DEFAULT_GIRDER_SLS_STAGES:
        raise ValueError(f"Unsupported girder SLS stage: {stage!r}")

    base_note = (
        "Initial editable preview profile. Verify the selected code edition, project specifications, "
        "concrete age/strength at stage, prestress class, reinforcement conditions, and local authority requirements before final design."
    )
    if stage == "Transfer":
        return GirderServiceStressLimitProfile(
            code=code,
            stage=stage,
            compression_limit_ratio=0.60,
            tension_limit_mode="sqrt(fc) ratio",
            tension_sqrt_fc_ratio=0.25,
            clause_note=f"{code} prestressed-concrete transfer stress profile placeholder.",
            limitation_note=base_note,
        )
    if stage == "Service / Final":
        return GirderServiceStressLimitProfile(
            code=code,
            stage=stage,
            compression_limit_ratio=0.45,
            tension_limit_mode="sqrt(fc) ratio",
            tension_sqrt_fc_ratio=0.50,
            clause_note=f"{code} prestressed-concrete service stress profile placeholder.",
            limitation_note=base_note,
        )
    return GirderServiceStressLimitProfile(
        code=code,
        stage=stage,
        compression_limit_ratio=0.45,
        tension_limit_mode="User-defined",
        tension_limit_MPa=0.0,
        clause_note=f"{code} user-defined stress profile.",
        limitation_note=base_note,
    )


def build_girder_sls_limit_profile(
    *,
    code: GirderSLSCode,
    stage: GirderSLSStage,
    compression_limit_ratio: float | None = None,
    tension_limit_mode: TensionLimitMode | None = None,
    tension_sqrt_fc_ratio: float | None = None,
    tension_limit_MPa: float | None = None,
    stress_zero_tolerance_MPa: float | None = None,
) -> GirderServiceStressLimitProfile:
    """Build a profile from defaults plus optional user overrides."""

    base = default_girder_sls_limit_profile(code, stage)
    profile = GirderServiceStressLimitProfile(
        code=base.code,
        stage=base.stage,
        compression_limit_ratio=float(base.compression_limit_ratio if compression_limit_ratio is None else compression_limit_ratio),
        tension_limit_mode=base.tension_limit_mode if tension_limit_mode is None else tension_limit_mode,
        tension_sqrt_fc_ratio=float(base.tension_sqrt_fc_ratio if tension_sqrt_fc_ratio is None else tension_sqrt_fc_ratio),
        tension_limit_MPa=float(base.tension_limit_MPa if tension_limit_MPa is None else tension_limit_MPa),
        stress_zero_tolerance_MPa=float(base.stress_zero_tolerance_MPa if stress_zero_tolerance_MPa is None else stress_zero_tolerance_MPa),
        clause_note=base.clause_note,
        limitation_note=base.limitation_note,
    )
    _require_positive("compression_limit_ratio", profile.compression_limit_ratio)
    if profile.tension_limit_mode == "sqrt(fc) ratio" and profile.tension_sqrt_fc_ratio < 0.0:
        raise ValueError("tension_sqrt_fc_ratio must not be negative.")
    if profile.tension_limit_mode == "User-defined" and profile.tension_limit_MPa < 0.0:
        raise ValueError("tension_limit_MPa must not be negative.")
    if profile.stress_zero_tolerance_MPa < 0.0:
        raise ValueError("stress_zero_tolerance_MPa must not be negative.")
    return profile


def _stress_type(stress_MPa: float, *, zero_tolerance_MPa: float) -> str:
    if abs(float(stress_MPa)) <= float(zero_tolerance_MPa):
        return "zero"
    return "compression" if float(stress_MPa) < 0.0 else "tension"


def check_girder_stress_limit_point(
    *,
    fiber: str,
    stress_MPa: float,
    fc_MPa: float,
    profile: GirderServiceStressLimitProfile,
) -> GirderStressLimitPointResult:
    """Check one top/bottom fiber stress against the selected profile."""

    if not str(fiber).strip():
        raise ValueError("fiber name must not be blank.")
    _require_finite("stress_MPa", stress_MPa)
    _require_positive("fc_MPa", fc_MPa)
    compression_limit = profile.compression_limit_MPa(fc_MPa)
    tension_limit = profile.tension_allowable_MPa(fc_MPa)
    stress_type = _stress_type(stress_MPa, zero_tolerance_MPa=profile.stress_zero_tolerance_MPa)

    if stress_type == "zero":
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=0.0,
            status="PASS",
            message="Stress is near zero.",
        )

    if stress_type == "compression":
        utilization = abs(float(stress_MPa)) / compression_limit
        status: StressLimitStatus = "PASS" if utilization <= 1.0 else "FAIL"
        message = "Compression stress within preview limit." if status == "PASS" else "Compression stress exceeds preview limit."
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=utilization,
            status=status,
            message=message,
        )

    if profile.tension_limit_mode == "No tension" or tension_limit <= profile.stress_zero_tolerance_MPa:
        return GirderStressLimitPointResult(
            fiber=str(fiber),
            stress_MPa=float(stress_MPa),
            stress_type=stress_type,
            compression_limit_MPa=compression_limit,
            tension_limit_MPa=tension_limit,
            utilization=None,
            status="FAIL",
            message="Tension stress violates no-tension preview limit.",
        )

    utilization = float(stress_MPa) / tension_limit
    status = "PASS" if utilization <= 1.0 else "FAIL"
    message = "Tension stress within preview limit." if status == "PASS" else "Tension stress exceeds preview limit."
    return GirderStressLimitPointResult(
        fiber=str(fiber),
        stress_MPa=float(stress_MPa),
        stress_type=stress_type,
        compression_limit_MPa=compression_limit,
        tension_limit_MPa=tension_limit,
        utilization=utilization,
        status=status,
        message=message,
    )


def run_girder_service_stress_limit_check(
    *,
    stresses: list[StressLimitInputRow] | tuple[StressLimitInputRow, ...],
    fc_MPa: float,
    profile: GirderServiceStressLimitProfile,
) -> GirderServiceStressLimitCheckResult:
    """Check a set of top/bottom stresses against a preview code-limit profile."""

    _require_positive("fc_MPa", fc_MPa)
    if not stresses:
        return GirderServiceStressLimitCheckResult(
            profile=profile,
            fc_MPa=float(fc_MPa),
            points=(),
            overall_status="NOT_CHECKED",
            warnings=("No stresses were provided for limit checking.",),
        )
    points = tuple(
        check_girder_stress_limit_point(
            fiber=row.fiber,
            stress_MPa=float(row.stress_MPa),
            fc_MPa=float(fc_MPa),
            profile=profile,
        )
        for row in stresses
    )
    overall: StressLimitStatus = "FAIL" if any(point.status == "FAIL" for point in points) else "PASS"
    warnings = (
        "CODE.SLS.LIMIT1 is a preview framework only. Confirm code edition, project clauses, prestress class, and stage-specific f'c before final design.",
    )
    return GirderServiceStressLimitCheckResult(
        profile=profile,
        fc_MPa=float(fc_MPa),
        points=points,
        overall_status=overall,
        warnings=warnings,
    )


def girder_service_limit_check_rows(result: GirderServiceStressLimitCheckResult) -> list[dict[str, object]]:
    """Return stable table rows for Streamlit/report display."""

    return [
        {
            "Fiber": point.fiber,
            "Stress (MPa)": point.stress_MPa,
            "Stress type": point.stress_type,
            "Compression limit (MPa)": point.compression_limit_MPa,
            "Tension limit (MPa)": point.tension_limit_MPa,
            "Utilization": point.utilization,
            "Status": point.status,
            "Message": point.message,
        }
        for point in result.points
    ]
