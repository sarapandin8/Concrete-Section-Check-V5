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
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.analysis.slice_envelope import build_slice_envelope, estimate_directional_capacity_from_envelope
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.verification.rc_rectangular_benchmarks import FAIL, PASS, WARNING


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


def run_valid_dc1_directional_benchmark_pack() -> DCDirectionalBenchmarkSummary:
    """Run SOLVER.PMM.DC1 validation checks."""

    return _summary(
        [
            _check_rectangular_ray_capacity_x_direction(),
            _check_rectangular_ray_capacity_diagonal(),
            _check_dc_summary_uses_primary_slice_method(),
        ]
    )
