"""Prestress stress-state governing-region validation benchmark pack.

VALID.PS2 is a validation/QA layer, not a solver-equation rewrite.  It checks
that prestress stress-state warnings (fpu cap and compression reversal clamp)
are traceable to PMM point metadata and can be separated into background PMM
surface events versus events near the governing demand Pu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.units import N_to_kN
from concrete_pmm_pro.verification.ps_bonded_benchmarks import PASS, WARNING, FAIL, ps_only_input, rc_plus_ps_input


@dataclass(frozen=True)
class PSStressRegionCheck:
    """Single prestress stress-region validation check."""

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
class PSStressRegionSummary:
    """Summary for the VALID.PS2 benchmark pack."""

    checks: list[PSStressRegionCheck]
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


def _summary(checks: list[PSStressRegionCheck]) -> PSStressRegionSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return PSStressRegionSummary(checks, pass_count, warning_count, fail_count, overall)


def _governing_case(model: AnalysisInput):
    result = run_rc_pmm_solver(model)
    dc_summary = check_uls_demands_against_rc_pmm(result, model.load_cases)
    governing_name = dc_summary.governing_combo
    governing_result = next((item for item in dc_summary.results if item.combo_name == governing_name), None)
    return result, dc_summary, governing_result


def _near_governing_pu_slice(df: pd.DataFrame, Pu_kN: float, tolerance_kN: float | None = None) -> pd.DataFrame:
    """Return PMM rows near the governing demand Pu using the same display axis.

    This intentionally uses phiPn_kN because the UI/DC workflow slices the
    phi-reduced PMM surface for demand/capacity traceability.
    """

    if df.empty or "phiPn_kN" not in df:
        return df.iloc[0:0].copy()
    p = pd.to_numeric(df["phiPn_kN"], errors="coerce")
    finite = df[p.notna()].copy()
    if finite.empty:
        return finite
    p = pd.to_numeric(finite["phiPn_kN"], errors="coerce")
    axial_range = float(p.max() - p.min())
    tolerance = tolerance_kN if tolerance_kN is not None else max(0.02 * axial_range, 50.0)
    return finite[(p - Pu_kN).abs() <= tolerance].copy()


def _event_count(df: pd.DataFrame, column: str) -> int:
    if df.empty or column not in df:
        return 0
    values = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    return int((values > 0.0).sum())


def _check_stress_metadata_schema() -> PSStressRegionCheck:
    result = run_rc_pmm_solver(rc_plus_ps_input())
    df = pmm_result_to_display_dataframe(result)
    required = {"prestress_reached_fpu_cap_count", "prestress_compression_reversal_count", "prestress_stress_warning_count"}
    missing = sorted(required.difference(df.columns))
    numeric_ok = True
    if not missing and not df.empty:
        numeric = df[list(required)].apply(pd.to_numeric, errors="coerce")
        numeric_ok = not numeric.isna().any().any()
    ok = not missing and numeric_ok
    return PSStressRegionCheck(
        check_id="VALID.PS2.METADATA_SCHEMA",
        title="Prestress stress-state metadata is available per PMM point",
        status=PASS if ok else FAIL,
        reference_value=0.0,
        solver_value=float(len(missing)),
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "PMM display data exposes fpu-cap, compression-reversal, and stress-warning counts per point."
            if ok
            else "Prestress stress-state metadata is missing or nonnumeric; governing-region classification cannot be trusted."
        ),
        details={"missing_columns": missing, "point_count": len(df)},
    )


def _check_background_fpu_cap_not_near_default_governing_pu() -> PSStressRegionCheck:
    result, dc_summary, governing = _governing_case(rc_plus_ps_input())
    df = pmm_result_to_display_dataframe(result)
    if governing is None:
        return PSStressRegionCheck(
            check_id="VALID.PS2.FPU_BACKGROUND_CLASSIFICATION",
            title="fpu-cap events can be separated from the governing Pu region",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=None,
            message="No governing D/C result was available for the RC+PS benchmark.",
            details={"dc_status": dc_summary.overall_status},
        )
    near = _near_governing_pu_slice(df, N_to_kN(governing.Pu_N))
    global_fpu = _event_count(df, "prestress_reached_fpu_cap_count")
    near_fpu = _event_count(near, "prestress_reached_fpu_cap_count")
    ok = global_fpu > 0 and near_fpu == 0 and governing.dcr is not None
    return PSStressRegionCheck(
        check_id="VALID.PS2.FPU_BACKGROUND_CLASSIFICATION",
        title="Default fpu-cap warnings are background PMM-surface events for this benchmark",
        status=PASS if ok else WARNING,
        reference_value=0.0,
        solver_value=float(near_fpu),
        percent_difference=0.0 if near_fpu == 0 else 100.0,
        tolerance_percent=0.0,
        message=(
            "The deterministic RC+PS benchmark has fpu-cap events globally, but none near the governing Pu slice."
            if ok
            else "fpu-cap events are present near the governing Pu slice; review whether they should remain governing-impact warnings."
        ),
        details={
            "governing_combo": governing.combo_name,
            "governing_dcr": governing.dcr,
            "governing_Pu_kN": N_to_kN(governing.Pu_N),
            "global_fpu_point_count": global_fpu,
            "near_governing_fpu_point_count": near_fpu,
            "near_governing_point_count": len(near),
        },
    )


def _check_compression_reversal_metadata_and_region() -> PSStressRegionCheck:
    # A tendon high in the section with the default benchmark demand exercises
    # compression-side strain states without changing production equations.
    model = rc_plus_ps_input(y_mm=250.0, label="PS-TOP", pe_eff_n=140_000.0)
    result, dc_summary, governing = _governing_case(model)
    df = pmm_result_to_display_dataframe(result)
    global_reversal = _event_count(df, "prestress_compression_reversal_count")
    near_reversal = 0
    near_count = 0
    if governing is not None:
        near = _near_governing_pu_slice(df, N_to_kN(governing.Pu_N))
        near_reversal = _event_count(near, "prestress_compression_reversal_count")
        near_count = len(near)
    ok = global_reversal > 0 and governing is not None and governing.dcr is not None
    return PSStressRegionCheck(
        check_id="VALID.PS2.COMPRESSION_REVERSAL_REGION",
        title="Compression-reversal events are traceable to PMM regions",
        status=PASS if ok else WARNING,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Compression-reversal events are recorded per PMM point and can be counted near the governing Pu region."
            if ok
            else "Compression-reversal events were not traceable for this benchmark; review stress metadata."
        ),
        details={
            "governing_combo": None if governing is None else governing.combo_name,
            "governing_dcr": None if governing is None else governing.dcr,
            "global_compression_reversal_point_count": global_reversal,
            "near_governing_compression_reversal_point_count": near_reversal,
            "near_governing_point_count": near_count,
            "dc_status": dc_summary.overall_status,
        },
    )


def _check_governing_dc_trace_is_available() -> PSStressRegionCheck:
    _, dc_summary, governing = _governing_case(rc_plus_ps_input())
    ok = (
        governing is not None
        and governing.dcr is not None
        and governing.capacity_phiMn_Nmm is not None
        and governing.capacity_method is not None
    )
    return PSStressRegionCheck(
        check_id="VALID.PS2.GOVERNING_TRACE_AVAILABLE",
        title="Governing D/C trace is available for stress-warning impact review",
        status=PASS if ok else FAIL,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "The benchmark has a governing D/C result with capacity method metadata for impact classification."
            if ok
            else "The benchmark lacks governing D/C trace metadata; warning-impact classification cannot be reviewed."
        ),
        details={
            "overall_status": dc_summary.overall_status,
            "governing_combo": None if governing is None else governing.combo_name,
            "governing_dcr": None if governing is None else governing.dcr,
            "capacity_method": None if governing is None else governing.capacity_method,
            "used_fallback": None if governing is None else governing.used_fallback,
            "warning_count": None if governing is None else governing.warning_count,
        },
    )


def _check_ps_only_region_slice_available() -> PSStressRegionCheck:
    result, _, governing = _governing_case(ps_only_input())
    df = pmm_result_to_display_dataframe(result)
    if governing is None:
        return PSStressRegionCheck(
            check_id="VALID.PS2.PS_ONLY_REGION_SLICE",
            title="PS-only benchmark supports governing-region stress review",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=None,
            message="No governing result was available for the PS-only benchmark.",
        )
    near = _near_governing_pu_slice(df, N_to_kN(governing.Pu_N))
    ok = not near.empty and governing.dcr is not None
    return PSStressRegionCheck(
        check_id="VALID.PS2.PS_ONLY_REGION_SLICE",
        title="PS-only PMM can be sliced near governing Pu for warning impact review",
        status=PASS if ok else WARNING,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "The PS-only benchmark has PMM points near the governing Pu for stress-warning impact review."
            if ok
            else "The PS-only benchmark has limited PMM points near governing Pu; review discretization/tolerance."
        ),
        details={
            "governing_combo": governing.combo_name,
            "governing_dcr": governing.dcr,
            "near_governing_point_count": len(near),
            "global_fpu_point_count": _event_count(df, "prestress_reached_fpu_cap_count"),
            "near_governing_fpu_point_count": _event_count(near, "prestress_reached_fpu_cap_count"),
        },
    )


def run_valid_ps2_stress_region_benchmark_pack() -> PSStressRegionSummary:
    """Run the VALID.PS2 prestress stress-state governing-region benchmark pack."""

    checks = [
        _check_stress_metadata_schema(),
        _check_governing_dc_trace_is_available(),
        _check_background_fpu_cap_not_near_default_governing_pu(),
        _check_compression_reversal_metadata_and_region(),
        _check_ps_only_region_slice_available(),
    ]
    return _summary(checks)
