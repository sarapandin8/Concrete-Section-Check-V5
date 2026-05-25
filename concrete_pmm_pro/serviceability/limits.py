"""Serviceability stress limits and point-level judgement helpers."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

from concrete_pmm_pro.serviceability.models import ServiceStressPointResult, ServiceabilitySettings


class ServiceabilityLimitSet(BaseModel):
    """Concrete service stress limits in MPa.

    SLS stress convention:
    - compression is negative
    - tension is positive

    No-tension and decompression checks fail when tensile stress exceeds the
    zero-stress tolerance at the checked concrete stress points.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    compression_limit_MPa: float = Field(gt=0)
    tension_limit_MPa: float = Field(ge=0)
    allow_tension: bool
    no_tension_required: bool
    decompression_required: bool
    stress_zero_tolerance_MPa: float = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)
    info: list[str] = Field(default_factory=list)


def build_serviceability_limit_set(fc_MPa: float, settings: ServiceabilitySettings) -> ServiceabilityLimitSet:
    """Build concrete service stress limits from settings."""

    if fc_MPa <= 0:
        raise ValueError("fc_MPa must be positive for serviceability limits.")

    warnings: list[str] = []
    info: list[str] = []
    compression_limit = settings.concrete_compression_limit_ratio * fc_MPa
    no_tension_required = settings.no_tension_check or settings.concrete_tension_limit_mode == "no_tension"
    decompression_required = settings.decompression_check

    if no_tension_required or decompression_required:
        tension_limit = 0.0
        allow_tension = False
        if decompression_required:
            info.append("Decompression check is enforced as a no-tension check at selected stress points.")
        if no_tension_required:
            info.append("No-tension check is enforced at selected stress points.")
    elif settings.concrete_tension_limit_mode == "user_defined":
        tension_limit = settings.concrete_tension_limit_MPa
        allow_tension = settings.allow_tension
    elif settings.concrete_tension_limit_mode == "sqrt_fc_ratio":
        tension_limit = settings.concrete_tension_sqrt_fc_ratio * math.sqrt(fc_MPa)
        allow_tension = True
    elif settings.concrete_tension_limit_mode == "no_tension":
        tension_limit = 0.0
        allow_tension = False
    else:
        tension_limit = settings.concrete_tension_limit_MPa
        allow_tension = settings.allow_tension
        warnings.append("Unknown tension limit mode; user-defined tension limit was used.")

    return ServiceabilityLimitSet(
        compression_limit_MPa=compression_limit,
        tension_limit_MPa=tension_limit,
        allow_tension=allow_tension,
        no_tension_required=no_tension_required,
        decompression_required=decompression_required,
        stress_zero_tolerance_MPa=settings.stress_zero_tolerance_MPa,
        warnings=warnings,
        info=info,
    )


def check_service_stress_point(
    stress_MPa: float,
    limits: ServiceabilityLimitSet,
) -> tuple[str, str, float | None, str]:
    """Return status, message, utilization, and stress type for one point."""

    tol = limits.stress_zero_tolerance_MPa
    if abs(stress_MPa) <= tol:
        return "PASS", "Stress is near zero.", 0.0, "Zero"

    if stress_MPa < -tol:
        utilization = abs(stress_MPa) / limits.compression_limit_MPa
        if utilization <= 1.0:
            return "PASS", "Compression stress within allowable limit.", utilization, "Compression"
        return "FAIL", "Compression stress exceeds allowable limit.", utilization, "Compression"

    if limits.no_tension_required or limits.decompression_required or not limits.allow_tension or limits.tension_limit_MPa <= tol:
        if limits.decompression_required:
            message = "No-tension/decompression requirement violated."
        elif limits.no_tension_required:
            message = "No-tension requirement violated."
        else:
            message = "Tension is not allowed by the selected serviceability settings."
        return "FAIL", message, None, "Tension"

    utilization = stress_MPa / limits.tension_limit_MPa
    if utilization <= 1.0:
        return "PASS", "Tension stress within allowable limit.", utilization, "Tension"
    return "FAIL", "Tension stress exceeds allowable limit.", utilization, "Tension"


def _governing_eligible_result(result: ServiceStressPointResult, critical_point_filter: str = "all") -> bool:
    if not result.include_in_governing:
        return False
    if critical_point_filter == "extreme_fibers_only":
        return result.point_type == "extreme_fiber"
    return True


def summarize_serviceability_results(
    stress_results: list[ServiceStressPointResult],
    critical_point_filter: str = "all",
) -> dict[str, object]:
    """Summarize point-level SLS judgement results."""

    if not stress_results:
        return {
            "overall_status": "NOT_CHECKED",
            "governing_combo": None,
            "governing_point": None,
            "governing_status": None,
            "max_compression_MPa": None,
            "max_tension_MPa": None,
            "max_utilization": None,
            "no_tension_violation_count": 0,
            "decompression_violation_count": 0,
            "compression_failure_count": 0,
            "tension_failure_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "warning_count": 0,
        }

    governing_results = [result for result in stress_results if _governing_eligible_result(result, critical_point_filter)]
    if not governing_results:
        return {
            "overall_status": "NOT_CHECKED",
            "governing_combo": None,
            "governing_point": None,
            "governing_status": None,
            "max_compression_MPa": None,
            "max_tension_MPa": None,
            "max_utilization": None,
            "no_tension_violation_count": 0,
            "decompression_violation_count": 0,
            "compression_failure_count": 0,
            "tension_failure_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "warning_count": 0,
        }

    pass_count = sum(1 for result in governing_results if result.status == "PASS")
    fail_count = sum(1 for result in governing_results if result.status == "FAIL")
    warning_count = sum(1 for result in governing_results if result.status == "WARNING")
    overall_status = "FAIL" if fail_count else "WARNING" if warning_count else "PASS"

    max_compression = None
    max_tension = None
    max_utilization = None
    governing_combo = None
    governing_point = None
    governing_status = None
    no_tension_violation_count = 0
    decompression_violation_count = 0
    compression_failure_count = 0
    tension_failure_count = 0
    severe_rank = -1

    for result in governing_results:
        stress = result.stress_MPa
        if stress is not None:
            if stress < 0:
                compression = abs(stress)
                max_compression = compression if max_compression is None else max(max_compression, compression)
            elif stress > 0:
                max_tension = stress if max_tension is None else max(max_tension, stress)

        if result.status == "FAIL":
            if result.stress_type == "Compression":
                compression_failure_count += 1
            elif result.stress_type == "Tension":
                tension_failure_count += 1
            message_lower = result.message.lower()
            if "no-tension" in message_lower:
                no_tension_violation_count += 1
            if "decompression" in message_lower:
                decompression_violation_count += 1

        rank = 0
        utilization = result.utilization
        if utilization is not None:
            rank = 1000 + int(utilization * 1_000_000)
        elif result.status == "FAIL":
            rank = 2_000_000
        elif result.status == "WARNING":
            rank = 500
        if rank > severe_rank:
            severe_rank = rank
            max_utilization = utilization if utilization is not None else max_utilization
            governing_combo = result.combo_name
            governing_point = result.point_name
            governing_status = result.status
        if utilization is not None:
            max_utilization = utilization if max_utilization is None else max(max_utilization, utilization)

    return {
        "overall_status": overall_status,
        "governing_combo": governing_combo,
        "governing_point": governing_point,
        "governing_status": governing_status,
        "max_compression_MPa": max_compression,
        "max_tension_MPa": max_tension,
        "max_utilization": max_utilization,
        "no_tension_violation_count": no_tension_violation_count,
        "decompression_violation_count": decompression_violation_count,
        "compression_failure_count": compression_failure_count,
        "tension_failure_count": tension_failure_count,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "warning_count": warning_count,
    }
