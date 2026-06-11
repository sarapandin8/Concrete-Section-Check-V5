"""Directional PMM demand/capacity validation benchmark pack.

SOLVER.PMM.DC1 validates how the app reads moment capacity from a PMM
Mx-My slice at a selected axial load.  The checks use analytic synthetic
slice envelopes so the expected directional capacity is known independently of
PMM solver discretization.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult, pmm_result_to_display_dataframe
from concrete_pmm_pro.analysis.slice_envelope import SliceEnvelopeResult, build_slice_envelope, estimate_directional_capacity_from_envelope
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import Nmm_to_kNm
from concrete_pmm_pro.verification.rc_rectangular_benchmarks import FAIL, PASS, WARNING, build_valid_rc1_rectangular_input


@dataclass(frozen=True)
class DCDirectionalBenchmarkCheck:
    """Single directional demand/capacity benchmark check."""

    check_id: str
    title: str
    status: str
    reference_value: float | None
    solver_value: float | None
    percent_difference: float | None
    tolerance_percent: float | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DCDirectionalBenchmarkSummary:
    """Summary for SOLVER.PMM.DC1 directional D/C benchmark pack."""

    checks: list[DCDirectionalBenchmarkCheck]
    pass_count: int
    warning_count: int
    fail_count: int
    overall_status: str

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "Check ID": check.check_id,
                    "Title": check.title,
                    "Status": check.status,
                    "Reference": check.reference_value,
                    "Solver": check.solver_value,
                    "Difference (%)": check.percent_difference,
                    "Tolerance (%)": check.tolerance_percent,
                    "Message": check.message,
                }
                for check in self.checks
            ]
        )


def _summary(checks: list[DCDirectionalBenchmarkCheck]) -> DCDirectionalBenchmarkSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return DCDirectionalBenchmarkSummary(checks, pass_count, warning_count, fail_count, overall)


def _percent_difference(reference: float, solver: float) -> float:
    return abs(solver - reference) / max(abs(reference), 1.0) * 100.0


def _status(percent_difference: float, tolerance_percent: float) -> str:
    if not math.isfinite(percent_difference):
        return FAIL
    return PASS if percent_difference <= tolerance_percent else FAIL


def _rectangular_slice(mx_capacity: float = 100.0, my_capacity: float = 50.0) -> pd.DataFrame:
    """Return a rectangular Mx-My slice with known ray capacities."""

    return pd.DataFrame(
        [
            {"phiMnx_kNm": -mx_capacity, "phiMny_kNm": -my_capacity, "phiPn_kN": 1000.0},
            {"phiMnx_kNm": mx_capacity, "phiMny_kNm": -my_capacity, "phiPn_kN": 1000.0},
            {"phiMnx_kNm": mx_capacity, "phiMny_kNm": my_capacity, "phiPn_kN": 1000.0},
            {"phiMnx_kNm": -mx_capacity, "phiMny_kNm": my_capacity, "phiPn_kN": 1000.0},
        ]
    )


def _synthetic_rectangular_pmm(mx_capacity: float = 100.0, my_capacity: float = 50.0) -> PMMSolverResult:
    """Return two axial layers so the preferred Pu-slice interpolation is used."""

    points: list[PMMPoint] = []
    vertices = [(-mx_capacity, -my_capacity), (mx_capacity, -my_capacity), (mx_capacity, my_capacity), (-mx_capacity, my_capacity)]
    for p_kN, c_mm in ((900.0, 100.0), (1100.0, 200.0)):
        for index, (mx, my) in enumerate(vertices):
            points.append(
                PMMPoint(
                    theta_rad=2.0 * math.pi * index / len(vertices),
                    c_mm=c_mm,
                    Pn_N=p_kN * 1000.0,
                    Mnx_Nmm=mx * 1_000_000.0,
                    Mny_Nmm=my * 1_000_000.0,
                    phi=0.65,
                    phiPn_N=p_kN * 1000.0,
                    phiPn_capped_N=p_kN * 1000.0,
                    phiMnx_Nmm=mx * 1_000_000.0,
                    phiMny_Nmm=my * 1_000_000.0,
                    eps_t=None,
                    strain_condition="compression-controlled",
                    concrete_area_mm2=1.0,
                    concrete_force_N=1.0,
                )
            )
    return PMMSolverResult(points=points)


def _check_rectangular_ray_capacity_x_direction() -> DCDirectionalBenchmarkCheck:
    envelope = build_slice_envelope(_rectangular_slice())
    estimate = estimate_directional_capacity_from_envelope(envelope, Mux_kNm=40.0, Muy_kNm=0.0)
    solver = float(estimate["capacity_phiMn_kNm"] or 0.0)
    reference = 100.0
    diff = _percent_difference(reference, solver)
    return DCDirectionalBenchmarkCheck(
        check_id="SOLVER.PMM.DC1.RECT_X_RAY",
        title="Rectangular slice ray capacity in +Mx direction",
        status=_status(diff, 0.1),
        reference_value=reference,
        solver_value=solver,
        percent_difference=diff,
        tolerance_percent=0.1,
        message="Ray-intersection capacity matches the rectangular boundary in the +Mx direction.",
        details={"method": estimate.get("method"), "warnings": estimate.get("warnings", [])},
    )


def _check_rectangular_ray_capacity_diagonal() -> DCDirectionalBenchmarkCheck:
    envelope = build_slice_envelope(_rectangular_slice())
    estimate = estimate_directional_capacity_from_envelope(envelope, Mux_kNm=40.0, Muy_kNm=40.0)
    # For a rectangle |Mx|<=100, |My|<=50 and a 45-degree ray, the ray hits My=50 first.
    reference = 50.0 / math.sin(math.radians(45.0))
    solver = float(estimate["capacity_phiMn_kNm"] or 0.0)
    diff = _percent_difference(reference, solver)
    return DCDirectionalBenchmarkCheck(
        check_id="SOLVER.PMM.DC1.RECT_DIAGONAL_RAY",
        title="Rectangular slice ray capacity in diagonal direction",
        status=_status(diff, 0.1),
        reference_value=reference,
        solver_value=solver,
        percent_difference=diff,
        tolerance_percent=0.1,
        message="Ray-intersection capacity uses the actual rectangle edge instead of polar-radius interpolation.",
        details={"method": estimate.get("method"), "warnings": estimate.get("warnings", [])},
    )


def _check_dc_summary_uses_primary_slice_method() -> DCDirectionalBenchmarkCheck:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_rectangular_pmm(),
        [LoadCase(name="ULS-DC1", Pu_N=1_000_000.0, Mux_Nmm=40_000_000.0, Muy_Nmm=40_000_000.0)],
    )
    result = summary.results[0]
    reference_capacity = 50.0 / math.sin(math.radians(45.0))
    reference_dcr = math.hypot(40.0, 40.0) / reference_capacity
    solver_dcr = float(result.dcr or 0.0)
    diff = _percent_difference(reference_dcr, solver_dcr)
    ok_method = result.capacity_method == "slice_envelope" and not result.used_fallback
    ok = diff <= 0.1 and ok_method
    return DCDirectionalBenchmarkCheck(
        check_id="SOLVER.PMM.DC1.DC_SUMMARY_PRIMARY",
        title="D/C summary uses primary slice-envelope ray capacity",
        status=PASS if ok else FAIL,
        reference_value=reference_dcr,
        solver_value=solver_dcr,
        percent_difference=diff,
        tolerance_percent=0.1,
        message=(
            "Governing D/C is computed from the primary slice envelope without fallback."
            if ok
            else "D/C summary did not use the expected primary slice-envelope capacity path."
        ),
        details={"capacity_method": result.capacity_method, "used_fallback": result.used_fallback, "message": result.message},
    )


def _non_star_noisy_envelope() -> SliceEnvelopeResult:
    """Return a synthetic noisy envelope whose +Mx ray intersects twice.

    This is not an RC section benchmark. It is an algorithm guard: when the
    ray crosses multiple positive boundary points, using the farthest point can
    overestimate capacity. The conservative first boundary is the safe value.
    """

    envelope = pd.DataFrame(
        [
            {"phiMnx_kNm": -100.0, "phiMny_kNm": -100.0},
            {"phiMnx_kNm": 200.0, "phiMny_kNm": -100.0},
            {"phiMnx_kNm": 200.0, "phiMny_kNm": 100.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": 100.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": 60.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": 60.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": 20.0},
            {"phiMnx_kNm": 20.0, "phiMny_kNm": 20.0},
            {"phiMnx_kNm": 20.0, "phiMny_kNm": -20.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": -20.0},
            {"phiMnx_kNm": 100.0, "phiMny_kNm": -60.0},
            {"phiMnx_kNm": -100.0, "phiMny_kNm": -60.0},
        ]
    )
    return SliceEnvelopeResult(
        envelope_df=envelope,
        method="manual_non_star_guard",
        point_count_input=len(envelope),
        point_count_output=len(envelope),
        warnings=[],
        info=["Synthetic non-star/noisy envelope for D/C no-overestimate guard."],
        is_valid=True,
        used_convex_hull=False,
        detected_self_crossing=False,
    )


def _check_non_star_ray_uses_nearest_boundary() -> DCDirectionalBenchmarkCheck:
    estimate = estimate_directional_capacity_from_envelope(_non_star_noisy_envelope(), Mux_kNm=50.0, Muy_kNm=0.0)
    solver = float(estimate["capacity_phiMn_kNm"] or 0.0)
    reference = 20.0
    diff = _percent_difference(reference, solver)
    warnings = [str(warning) for warning in estimate.get("warnings", [])]
    ok = diff <= 0.1 and any("nearest boundary" in warning for warning in warnings)
    return DCDirectionalBenchmarkCheck(
        check_id="SOLVER.PMM.DC1.NONSTAR_NEAREST_RAY",
        title="Non-star envelope uses nearest ray boundary",
        status=PASS if ok else FAIL,
        reference_value=reference,
        solver_value=solver,
        percent_difference=diff,
        tolerance_percent=0.1,
        message=(
            "Multiple ray intersections use the nearest boundary to avoid directional capacity overestimate."
            if ok
            else "Multiple ray intersections did not use the expected nearest-boundary capacity guard."
        ),
        details={"method": estimate.get("method"), "warnings": warnings},
    )


def _check_rc_rectangular_primary_dc_no_overestimate() -> DCDirectionalBenchmarkCheck:
    """Confirm the real RC PMM path does not exceed its direct slice ray bound."""

    analysis_input = build_valid_rc1_rectangular_input()
    demand = LoadCase(
        name="ULS-DC1-RC-RECT",
        Pu_N=1_200_000.0,
        Mux_Nmm=120_000_000.0,
        Muy_Nmm=60_000_000.0,
        load_type="ULS",
        active=True,
    )
    analysis_input.load_cases = [demand]
    pmm_result = run_rc_pmm_solver(analysis_input)
    summary = check_uls_demands_against_rc_pmm(pmm_result, [demand])
    if not summary.results:
        return DCDirectionalBenchmarkCheck(
            check_id="SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE",
            title="RC rectangular D/C uses primary ray capacity without overestimate",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=0.1,
            message="RC rectangular D/C benchmark returned no demand/capacity result.",
        )

    result = summary.results[0]
    from concrete_pmm_pro.visualization.pmm_dashboard import pmm_slice_at_pu

    pmm_df = pmm_result_to_display_dataframe(pmm_result)
    slice_df = pmm_slice_at_pu(pmm_df, demand.Pu_N / 1000.0)
    envelope = build_slice_envelope(slice_df)
    estimate = estimate_directional_capacity_from_envelope(envelope, Nmm_to_kNm(demand.Mux_Nmm), Nmm_to_kNm(demand.Muy_Nmm))
    reference_capacity = estimate.get("capacity_phiMn_kNm")
    solver_capacity = None if result.capacity_phiMn_Nmm is None else Nmm_to_kNm(result.capacity_phiMn_Nmm)
    if reference_capacity is None or solver_capacity is None or reference_capacity <= 0.0:
        return DCDirectionalBenchmarkCheck(
            check_id="SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE",
            title="RC rectangular D/C uses primary ray capacity without overestimate",
            status=FAIL,
            reference_value=reference_capacity,
            solver_value=solver_capacity,
            percent_difference=None,
            tolerance_percent=0.1,
            message="RC rectangular D/C benchmark could not establish a direct slice ray reference capacity.",
            details={
                "capacity_method": result.capacity_method,
                "slice_method": result.slice_method,
                "envelope_method": envelope.method,
                "estimate_method": estimate.get("method"),
                "estimate_warnings": estimate.get("warnings", []),
            },
        )

    diff = _percent_difference(float(reference_capacity), float(solver_capacity))
    overestimate_percent = max(0.0, (float(solver_capacity) / float(reference_capacity) - 1.0) * 100.0)
    expected_method = (
        result.capacity_method == "slice_envelope"
        and result.used_fallback is False
        and result.envelope_method == "polar_max"
        and envelope.method == "polar_max"
        and envelope.used_convex_hull is False
        and estimate.get("method") == "slice_envelope_ray"
    )
    ok = expected_method and diff <= 0.1 and overestimate_percent <= 0.01
    return DCDirectionalBenchmarkCheck(
        check_id="SOLVER.PMM.DC1.RC_RECT_PRIMARY_NO_OVERESTIMATE",
        title="RC rectangular D/C uses primary ray capacity without overestimate",
        status=PASS if ok else FAIL,
        reference_value=float(reference_capacity),
        solver_value=float(solver_capacity),
        percent_difference=diff,
        tolerance_percent=0.1,
        message=(
            "Actual RC rectangular PMM D/C result uses the primary slice-envelope ray capacity and does not exceed the direct ray-boundary estimate."
            if ok
            else "Actual RC rectangular PMM D/C result did not satisfy the primary no-overestimate path guard."
        ),
        details={
            "capacity_method": result.capacity_method,
            "slice_method": result.slice_method,
            "envelope_method": envelope.method,
            "result_envelope_method": result.envelope_method,
            "used_convex_hull": envelope.used_convex_hull,
            "estimate_method": estimate.get("method"),
            "used_fallback": result.used_fallback,
            "Pu_kN": demand.Pu_N / 1000.0,
            "Mux_kNm": Nmm_to_kNm(demand.Mux_Nmm),
            "Muy_kNm": Nmm_to_kNm(demand.Muy_Nmm),
            "solver_dcr": result.dcr,
            "overestimate_percent": overestimate_percent,
            "estimate_warnings": estimate.get("warnings", []),
            "summary_warning_count": result.warning_count,
        },
    )


def run_valid_dc1_directional_benchmark_pack() -> DCDirectionalBenchmarkSummary:
    """Run SOLVER.PMM.DC1 validation checks."""

    return _summary(
        [
            _check_rectangular_ray_capacity_x_direction(),
            _check_rectangular_ray_capacity_diagonal(),
            _check_dc_summary_uses_primary_slice_method(),
            _check_non_star_ray_uses_nearest_boundary(),
            _check_rc_rectangular_primary_dc_no_overestimate(),
        ]
    )
