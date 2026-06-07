"""Prototype RC PMM demand/capacity checks.

This module estimates capacity from the RC/PS PMM point cloud. It is intentionally
not a final design-certification algorithm: bonded prestress is included by the
prototype solver when enabled, while unbonded prestress, refined biaxial axial-cap
interaction, and refined PMM surface interpolation remain future work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from concrete_pmm_pro.analysis.result_models import PMMSolverResult, pmm_result_to_display_dataframe
from concrete_pmm_pro.analysis.warnings import (
    BONDED_PRESTRESS_PROTOTYPE_WARNING,
    DCR_PROTOTYPE_WARNING,
    PMM_PROTOTYPE_WARNING,
    RC_AXIAL_CAP_LIMITATION_WARNING,
    UNBONDED_PRESTRESS_IGNORED_WARNING,
    deduplicate_warnings,
)
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm

PASS = "PASS"
FAIL = "FAIL"
OUT_OF_RANGE = "OUT_OF_RANGE"
NOT_CHECKED = "NOT_CHECKED"


@dataclass(frozen=True)
class DemandCapacityResult:
    combo_name: str
    Pu_N: float
    Mux_Nmm: float
    Muy_Nmm: float
    Mu_Nmm: float
    moment_angle_rad: float
    capacity_Mn_Nmm: float | None
    capacity_phiMn_Nmm: float | None
    capacity_phiPn_N: float | None
    dcr: float | None
    status: str
    message: str
    capacity_method: str | None = None
    slice_method: str | None = None
    envelope_method: str | None = None
    used_fallback: bool = False
    warning_count: int = 0


@dataclass(frozen=True)
class DemandCapacitySummary:
    results: list[DemandCapacityResult] = field(default_factory=list)
    governing_combo: str | None = None
    max_dcr: float | None = None
    overall_status: str = NOT_CHECKED
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _angular_difference(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def _positive_directional_points(pmm_result: PMMSolverResult, alpha: float) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for point in pmm_result.points:
        mx = point.phiMnx_Nmm
        my = point.phiMny_Nmm
        mdir = mx * math.cos(alpha) + my * math.sin(alpha)
        if mdir <= 0:
            continue
        beta = math.atan2(my, mx)
        points.append(
            {
                "P": point.phiPn_N,
                "Mdir": mdir,
                "beta": beta,
                "angle_diff": _angular_difference(beta, alpha),
            }
        )
    return points


def _interpolate_capacity_at_pu(points: list[dict[str, float]], Pu_N: float) -> tuple[float | None, str]:
    if len(points) < 2:
        return None, NOT_CHECKED
    sorted_points = sorted(points, key=lambda item: item["P"])
    min_p = sorted_points[0]["P"]
    max_p = sorted_points[-1]["P"]
    if Pu_N < min_p or Pu_N > max_p:
        return None, OUT_OF_RANGE

    best_capacity: float | None = None
    for left, right in zip(sorted_points[:-1], sorted_points[1:]):
        p1 = left["P"]
        p2 = right["P"]
        if p1 == p2:
            if abs(Pu_N - p1) <= 1.0e-9:
                candidate = max(left["Mdir"], right["Mdir"])
                best_capacity = candidate if best_capacity is None else max(best_capacity, candidate)
            continue
        if (p1 <= Pu_N <= p2) or (p2 <= Pu_N <= p1):
            ratio = (Pu_N - p1) / (p2 - p1)
            candidate = left["Mdir"] + ratio * (right["Mdir"] - left["Mdir"])
            best_capacity = candidate if best_capacity is None else max(best_capacity, candidate)

    if best_capacity is None:
        nearest = min(sorted_points, key=lambda item: abs(item["P"] - Pu_N))
        best_capacity = nearest["Mdir"]
    return best_capacity, PASS


def _max_axial_capacity_N(pmm_result: PMMSolverResult) -> float | None:
    capacities = [
        point.phiPn_capped_N if point.phiPn_capped_N is not None else point.phiPn_N
        for point in pmm_result.points
    ]
    return max(capacities) if capacities else None


def estimate_directional_capacity(
    pmm_result: PMMSolverResult,
    Pu_N: float,
    Mux_Nmm: float,
    Muy_Nmm: float,
) -> dict[str, Any]:
    """Estimate phi-reduced moment capacity for a Pu and Mux/Muy direction."""

    alpha = math.atan2(Muy_Nmm, Mux_Nmm)
    warnings: list[str] = ["Prototype directional PMM interpolation will be refined in a future milestone."]
    candidate_points = _positive_directional_points(pmm_result, alpha)
    if len(candidate_points) < 2:
        return {
            "capacity_phiMn_Nmm": None,
            "capacity_phiPn_N": None,
            "angular_tolerance_used": None,
            "interpolation_status": NOT_CHECKED,
            "warnings": warnings + ["Not enough PMM points with positive directional capacity."],
        }

    selected: list[dict[str, float]] = []
    tolerance_used = math.radians(10.0)
    for degrees in (10.0, 15.0, 20.0, 25.0, 30.0):
        tolerance = math.radians(degrees)
        selected = [point for point in candidate_points if point["angle_diff"] <= tolerance]
        tolerance_used = tolerance
        if len(selected) >= 2:
            if degrees > 10.0:
                warnings.append(f"Angular interpolation tolerance widened to {degrees:g} degrees.")
            break
    else:
        selected = sorted(candidate_points, key=lambda point: point["angle_diff"])[: max(2, min(6, len(candidate_points)))]
        tolerance_used = max(point["angle_diff"] for point in selected)
        warnings.append("Using nearest angular PMM points because directional tolerance had too few points.")

    capacity, status = _interpolate_capacity_at_pu(selected, Pu_N)
    if status == OUT_OF_RANGE:
        warnings.append("Demand Pu is outside the selected PMM axial range.")
    if status == NOT_CHECKED:
        warnings.append("Capacity could not be interpolated from selected PMM points.")

    return {
        "capacity_phiMn_Nmm": capacity,
        "capacity_phiPn_N": Pu_N if capacity is not None else None,
        "angular_tolerance_used": tolerance_used,
        "interpolation_status": status,
        "warnings": warnings,
    }


def _axial_only_check(combo: LoadCase, max_phiPn_N: float) -> DemandCapacityResult:
    dcr = combo.Pu_N / max_phiPn_N if max_phiPn_N > 0 else None
    if dcr is None:
        return DemandCapacityResult(
            combo_name=combo.name,
            Pu_N=combo.Pu_N,
            Mux_Nmm=combo.Mux_Nmm,
            Muy_Nmm=combo.Muy_Nmm,
            Mu_Nmm=0.0,
            moment_angle_rad=0.0,
            capacity_Mn_Nmm=None,
            capacity_phiMn_Nmm=None,
            capacity_phiPn_N=None,
            dcr=None,
            status=NOT_CHECKED,
            message="Axial capacity could not be estimated.",
            capacity_method="not_checked",
            slice_method=None,
            envelope_method=None,
            used_fallback=False,
        )
    status = PASS if dcr <= 1.0 else FAIL
    return DemandCapacityResult(
        combo_name=combo.name,
        Pu_N=combo.Pu_N,
        Mux_Nmm=combo.Mux_Nmm,
        Muy_Nmm=combo.Muy_Nmm,
        Mu_Nmm=0.0,
        moment_angle_rad=0.0,
        capacity_Mn_Nmm=None,
        capacity_phiMn_Nmm=None,
        capacity_phiPn_N=max_phiPn_N,
        dcr=dcr,
        status=status,
        message="Axial-only prototype check against capped maximum phiPn.",
        capacity_method="axial_capped_capacity",
        slice_method=None,
        envelope_method=None,
        used_fallback=False,
    )


def check_uls_demands_against_rc_pmm(
    pmm_result: PMMSolverResult,
    load_cases: list[LoadCase],
) -> DemandCapacitySummary:
    warnings = [
        PMM_PROTOTYPE_WARNING,
        DCR_PROTOTYPE_WARNING,
        RC_AXIAL_CAP_LIMITATION_WARNING,
    ]
    if any((getattr(point, "active_prestress_count", 0) > 0 or point.bonded_prestress_count > 0) for point in pmm_result.points):
        warnings.append(BONDED_PRESTRESS_PROTOTYPE_WARNING)
    if any(point.unbonded_prestress_ignored_count > 0 for point in pmm_result.points):
        warnings.append(UNBONDED_PRESTRESS_IGNORED_WARNING)
    active_uls = [load_case for load_case in load_cases if load_case.active and load_case.load_type == "ULS"]
    if not active_uls:
        return DemandCapacitySummary(
            results=[],
            governing_combo=None,
            max_dcr=None,
            overall_status=NOT_CHECKED,
            warnings=warnings,
            info=["No active ULS load cases were available for demand/capacity checking."],
        )

    max_phiPn = _max_axial_capacity_N(pmm_result)
    if max_phiPn is None:
        return DemandCapacitySummary(
            results=[],
            governing_combo=None,
            max_dcr=None,
            overall_status=NOT_CHECKED,
            warnings=warnings + ["PMM result is empty."],
            info=[],
        )

    results: list[DemandCapacityResult] = []
    display_df = pmm_result_to_display_dataframe(pmm_result)
    build_slice_envelope = None
    estimate_directional_capacity_from_envelope = None
    estimate_directional_capacity_from_slice = None
    pmm_slice_at_pu = None
    if not display_df.empty:
        from concrete_pmm_pro.analysis.slice_envelope import (
            build_slice_envelope as _build_slice_envelope,
            estimate_directional_capacity_from_envelope as _estimate_directional_capacity_from_envelope,
        )
        from concrete_pmm_pro.visualization.pmm_dashboard import (
            estimate_directional_capacity_from_slice as _estimate_directional_capacity_from_slice,
            pmm_slice_at_pu as _pmm_slice_at_pu,
        )

        build_slice_envelope = _build_slice_envelope
        estimate_directional_capacity_from_envelope = _estimate_directional_capacity_from_envelope
        estimate_directional_capacity_from_slice = _estimate_directional_capacity_from_slice
        pmm_slice_at_pu = _pmm_slice_at_pu
    for combo in active_uls:
        mu = math.hypot(combo.Mux_Nmm, combo.Muy_Nmm)
        angle = math.atan2(combo.Muy_Nmm, combo.Mux_Nmm) if mu > 0 else 0.0
        if mu <= 1.0e-9:
            results.append(_axial_only_check(combo, float(max_phiPn)))
            continue

        capacity: float | None = None
        interpolation_status = NOT_CHECKED
        capacity_phiPn_N: float | None = None
        message = "Directional PMM capacity could not be estimated."
        capacity_method: str | None = None
        slice_method: str | None = None
        envelope_method: str | None = None
        used_fallback = False
        combo_warning_count = 0
        if not display_df.empty and pmm_slice_at_pu is not None and build_slice_envelope is not None:
            slice_df = pmm_slice_at_pu(display_df, N_to_kN(combo.Pu_N))
            slice_warnings = slice_df.attrs.get("warnings", [])
            combo_warning_count += len(slice_warnings)
            warnings.extend(slice_warnings)
            slice_method = slice_df.attrs.get("method")
            envelope = build_slice_envelope(slice_df)
            combo_warning_count += len(envelope.warnings)
            warnings.extend(envelope.warnings)
            envelope_method = envelope.method
            if envelope.is_valid and estimate_directional_capacity_from_envelope is not None:
                envelope_estimate = estimate_directional_capacity_from_envelope(
                    envelope,
                    Nmm_to_kNm(combo.Mux_Nmm),
                    Nmm_to_kNm(combo.Muy_Nmm),
                )
                envelope_warnings = envelope_estimate.get("warnings", [])
                combo_warning_count += len(envelope_warnings)
                warnings.extend(envelope_warnings)
                capacity_kNm = envelope_estimate.get("capacity_phiMn_kNm")
                if capacity_kNm is not None and capacity_kNm > 0:
                    capacity = float(capacity_kNm) * 1_000_000.0
                    capacity_phiPn_N = combo.Pu_N
                    interpolation_status = envelope_estimate.get("status", PASS)
                    method_name = str(envelope_estimate.get("method") or "slice_envelope")
                    if method_name == "slice_envelope_ray":
                        message = "Checked using PMM slice envelope ray-intersection at Pu."
                    else:
                        message = "Checked using PMM slice envelope at Pu."
                    capacity_method = "slice_envelope"

            if (
                (capacity is None or capacity <= 0)
                and slice_df.attrs.get("method") == "interpolated"
                and estimate_directional_capacity_from_slice is not None
            ):
                slice_estimate = estimate_directional_capacity_from_slice(
                    slice_df,
                    Nmm_to_kNm(combo.Mux_Nmm),
                    Nmm_to_kNm(combo.Muy_Nmm),
                )
                slice_estimate_warnings = slice_estimate.get("warnings", [])
                combo_warning_count += len(slice_estimate_warnings)
                warnings.extend(slice_estimate_warnings)
                capacity_kNm = slice_estimate.get("capacity_phiMn_kNm")
                if capacity_kNm is not None and capacity_kNm > 0:
                    capacity = float(capacity_kNm) * 1_000_000.0
                    capacity_phiPn_N = combo.Pu_N
                    interpolation_status = slice_estimate.get("status", PASS)
                    message = "Checked using interpolated slice fallback at Pu."
                    capacity_method = "interpolated_slice"
                    used_fallback = True

        if capacity is None or capacity <= 0:
            estimate = estimate_directional_capacity(pmm_result, combo.Pu_N, combo.Mux_Nmm, combo.Muy_Nmm)
            estimate_warnings = estimate.get("warnings", [])
            combo_warning_count += len(estimate_warnings) + 1
            warnings.extend(estimate_warnings)
            warnings.append("Checked using point-cloud directional fallback.")
            capacity = estimate.get("capacity_phiMn_Nmm")
            interpolation_status = estimate.get("interpolation_status", NOT_CHECKED)
            capacity_phiPn_N = estimate.get("capacity_phiPn_N")
            message = f"Checked using point-cloud directional fallback. Status: {interpolation_status}."
            capacity_method = "point_cloud_fallback"
            used_fallback = True
        if capacity is None or capacity <= 0:
            results.append(
                DemandCapacityResult(
                    combo_name=combo.name,
                    Pu_N=combo.Pu_N,
                    Mux_Nmm=combo.Mux_Nmm,
                    Muy_Nmm=combo.Muy_Nmm,
                    Mu_Nmm=mu,
                    moment_angle_rad=angle,
                    capacity_Mn_Nmm=None,
                    capacity_phiMn_Nmm=None,
                    capacity_phiPn_N=capacity_phiPn_N,
                    dcr=None,
                    status=OUT_OF_RANGE if interpolation_status == OUT_OF_RANGE else NOT_CHECKED,
                    message="Directional PMM capacity could not be estimated.",
                    capacity_method=capacity_method or "not_checked",
                    slice_method=slice_method,
                    envelope_method=envelope_method,
                    used_fallback=used_fallback,
                    warning_count=combo_warning_count,
                )
            )
            continue

        dcr = mu / float(capacity)
        status = PASS if dcr <= 1.0 else FAIL
        results.append(
            DemandCapacityResult(
                combo_name=combo.name,
                Pu_N=combo.Pu_N,
                Mux_Nmm=combo.Mux_Nmm,
                Muy_Nmm=combo.Muy_Nmm,
                Mu_Nmm=mu,
                moment_angle_rad=angle,
                capacity_Mn_Nmm=None,
                capacity_phiMn_Nmm=float(capacity),
                capacity_phiPn_N=capacity_phiPn_N,
                dcr=dcr,
                status=status,
                message=message,
                capacity_method=capacity_method,
                slice_method=slice_method,
                envelope_method=envelope_method,
                used_fallback=used_fallback,
                warning_count=combo_warning_count,
            )
        )

    finite_results = [result for result in results if result.dcr is not None]
    governing = max(finite_results, key=lambda result: result.dcr, default=None)
    if any(result.status == FAIL for result in results):
        overall_status = FAIL
    elif any(result.status in {OUT_OF_RANGE, NOT_CHECKED} for result in results):
        overall_status = OUT_OF_RANGE
    else:
        overall_status = PASS

    return DemandCapacitySummary(
        results=results,
        governing_combo=None if governing is None else governing.combo_name,
        max_dcr=None if governing is None else governing.dcr,
        overall_status=overall_status,
        warnings=deduplicate_warnings(warnings),
        info=[f"Checked {len(results)} active ULS load case(s).", "SLS load cases are ignored for this prototype."],
    )
