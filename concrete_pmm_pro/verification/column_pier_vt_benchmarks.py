"""ACI RC Column/Pier shear-torsion benchmark references.

ULS.COL.VT.QA1 is an independent hand-check pack for the scoped
nonprestressed ACI RC Column/Pier V+T gate.  It mirrors the public method
statement used by the Analysis view without importing Streamlit or UI helper
functions, so the app result can be compared against a separate reference.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class ColumnPierVTBenchmarkCase:
    """Reference input for one ACI RC Column/Pier V+T hand check."""

    case_id: str
    title: str
    direction: str
    width_mm: float = 400.0
    height_mm: float = 600.0
    fc_MPa: float = 35.0
    vu_kN: float = 120.0
    tu_kNm: float = 20.0
    tie_offset_mm: float = 50.0
    transverse_diameter_mm: float = 12.0
    transverse_legs: int = 2
    transverse_spacing_mm: float = 150.0
    transverse_fy_MPa: float = 390.0
    longitudinal_al_mm2: float = 2.0 * math.pi * 25.0**2 / 4.0


@dataclass(frozen=True)
class ColumnPierVTBenchmarkCheck:
    """Single numeric benchmark check."""

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
class ColumnPierVTBenchmarkSummary:
    """Summary for ULS.COL.VT.QA1 benchmark references."""

    checks: list[ColumnPierVTBenchmarkCheck]
    pass_count: int
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


def benchmark_cases() -> list[ColumnPierVTBenchmarkCase]:
    """Return the independent reference cases used by ULS.COL.VT.QA1."""

    return [
        ColumnPierVTBenchmarkCase(
            case_id="ULS.COL.VT.QA1.VUY_MODERATE",
            title="Moderate Vuy + Tu combined V+T check",
            direction="Vuy",
            vu_kN=120.0,
            tu_kNm=20.0,
        ),
        ColumnPierVTBenchmarkCase(
            case_id="ULS.COL.VT.QA1.VUX_MODERATE",
            title="Moderate Vux + Tu combined V+T check",
            direction="Vux",
            vu_kN=80.0,
            tu_kNm=20.0,
        ),
        ColumnPierVTBenchmarkCase(
            case_id="ULS.COL.VT.QA1.ZERO_SHEAR_TORSION_ONLY",
            title="Zero shear with active torsion",
            direction="Vuy",
            vu_kN=0.0,
            tu_kNm=20.0,
        ),
        ColumnPierVTBenchmarkCase(
            case_id="ULS.COL.VT.QA1.THRESHOLD_ONLY",
            title="Torsion below threshold remains source-gated",
            direction="Vuy",
            vu_kN=120.0,
            tu_kNm=5.0,
        ),
    ]


def reference_values(case: ColumnPierVTBenchmarkCase) -> dict[str, float | str]:
    """Return independent hand-check values for a benchmark case."""

    phi = 0.75
    cot_theta = 1.0
    sqrt_fc = math.sqrt(case.fc_MPa)
    if case.direction == "Vux":
        bw_mm = case.height_mm
        d_mm = 0.80 * case.width_mm
    else:
        bw_mm = case.width_mm
        d_mm = 0.80 * case.height_mm

    aoh_mm2 = max(case.width_mm - 2.0 * case.tie_offset_mm, 0.0) * max(case.height_mm - 2.0 * case.tie_offset_mm, 0.0)
    ao_mm2 = 0.85 * aoh_mm2
    ph_mm = 2.0 * max(case.width_mm + case.height_mm - 4.0 * case.tie_offset_mm, 0.0)
    acp_mm2 = case.width_mm * case.height_mm
    pcp_mm = 2.0 * (case.width_mm + case.height_mm)

    bar_area_mm2 = math.pi * case.transverse_diameter_mm**2 / 4.0
    avs_mm2_per_mm = bar_area_mm2 * float(case.transverse_legs) / case.transverse_spacing_mm
    ats_mm2_per_mm = bar_area_mm2 / case.transverse_spacing_mm

    vc_kN = 0.17 * sqrt_fc * bw_mm * d_mm / 1000.0
    phi_tcr_kNm = phi * (0.083 * sqrt_fc * acp_mm2 * acp_mm2 / pcp_mm) / 1.0e6
    if abs(case.tu_kNm) <= phi_tcr_kNm + 1.0e-9:
        shear_strength_dc = abs(case.vu_kN) / (phi * (vc_kN + avs_mm2_per_mm * case.transverse_fy_MPa * d_mm / 1000.0))
        avs_required = max(0.062 * sqrt_fc * bw_mm / case.transverse_fy_MPa, 0.35 * bw_mm / case.transverse_fy_MPa)
        avs_dc = avs_required / avs_mm2_per_mm
        spacing_dc = case.transverse_spacing_mm / min(0.50 * d_mm, 600.0)
        shear_governing_dc = max(shear_strength_dc, avs_dc, spacing_dc)
        return {
            "threshold_status": "BELOW THRESHOLD",
            "overall_dc": shear_governing_dc,
            "shear_strength_dc": shear_strength_dc,
            "shear_min_avs_dc": avs_dc,
            "shear_spacing_dc": spacing_dc,
            "phi_tcr_kNm": phi_tcr_kNm,
            "bw_mm": bw_mm,
            "d_mm": d_mm,
            "ao_mm2": ao_mm2,
            "aoh_mm2": aoh_mm2,
            "ph_mm": ph_mm,
            "provided_av_2at_per_s": avs_mm2_per_mm + 2.0 * ats_mm2_per_mm,
        }

    shear_stress_MPa = abs(case.vu_kN) * 1000.0 / (bw_mm * d_mm)
    torsion_stress_MPa = abs(case.tu_kNm) * 1.0e6 * ph_mm / (1.7 * aoh_mm2 * aoh_mm2)
    interaction_stress_MPa = math.sqrt(shear_stress_MPa * shear_stress_MPa + torsion_stress_MPa * torsion_stress_MPa)
    vc_stress_MPa = vc_kN * 1000.0 / (bw_mm * d_mm)
    stress_limit_MPa = phi * (vc_stress_MPa + 0.66 * sqrt_fc)
    stress_dc = interaction_stress_MPa / stress_limit_MPa

    shear_req = max(
        0.0,
        (abs(case.vu_kN) * 1000.0 / phi - vc_kN * 1000.0)
        / (case.transverse_fy_MPa * d_mm * cot_theta),
    )
    torsion_req = abs(case.tu_kNm) * 1.0e6 / (phi * 2.0 * ao_mm2 * case.transverse_fy_MPa * cot_theta)
    combined_req = shear_req + 2.0 * torsion_req
    min_req = max(0.062 * sqrt_fc * bw_mm / case.transverse_fy_MPa, 0.35 * bw_mm / case.transverse_fy_MPa)
    governing_req = max(combined_req, min_req)
    provided_total = avs_mm2_per_mm + 2.0 * ats_mm2_per_mm
    transverse_dc = governing_req / provided_total
    al_req = torsion_req * ph_mm * cot_theta * cot_theta
    longitudinal_dc = al_req / case.longitudinal_al_mm2
    overall_dc = max(stress_dc, transverse_dc, longitudinal_dc)

    return {
        "threshold_status": "DESIGN REQUIRED",
        "overall_dc": overall_dc,
        "stress_dc": stress_dc,
        "transverse_dc": transverse_dc,
        "longitudinal_dc": longitudinal_dc,
        "shear_stress_MPa": shear_stress_MPa,
        "torsion_stress_MPa": torsion_stress_MPa,
        "interaction_stress_MPa": interaction_stress_MPa,
        "stress_limit_MPa": stress_limit_MPa,
        "shear_req_mm2_per_mm": shear_req,
        "torsion_req_mm2_per_mm": torsion_req,
        "combined_req_mm2_per_mm": combined_req,
        "min_req_mm2_per_mm": min_req,
        "governing_req_mm2_per_mm": governing_req,
        "provided_av_2at_per_s": provided_total,
        "al_req_mm2": al_req,
        "al_provided_mm2": case.longitudinal_al_mm2,
        "phi_tcr_kNm": phi_tcr_kNm,
        "bw_mm": bw_mm,
        "d_mm": d_mm,
        "ao_mm2": ao_mm2,
        "aoh_mm2": aoh_mm2,
        "ph_mm": ph_mm,
    }


def _percent_difference(reference: float, solver: float) -> float:
    return abs(float(solver) - float(reference)) / max(abs(float(reference)), 1.0) * 100.0


def make_benchmark_check(
    *,
    check_id: str,
    title: str,
    reference_value: float,
    solver_value: float,
    message: str,
    details: dict[str, Any] | None = None,
    tolerance_percent: float = 1.0e-6,
) -> ColumnPierVTBenchmarkCheck:
    """Build a benchmark check from a reference and solver value."""

    diff = _percent_difference(reference_value, solver_value)
    return ColumnPierVTBenchmarkCheck(
        check_id=check_id,
        title=title,
        status=PASS if diff <= tolerance_percent else FAIL,
        reference_value=float(reference_value),
        solver_value=float(solver_value),
        percent_difference=diff,
        tolerance_percent=tolerance_percent,
        message=message,
        details=details or {},
    )


def summarize_checks(checks: list[ColumnPierVTBenchmarkCheck]) -> ColumnPierVTBenchmarkSummary:
    """Return a compact benchmark summary."""

    pass_count = sum(check.status == PASS for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else PASS
    return ColumnPierVTBenchmarkSummary(
        checks=checks,
        pass_count=pass_count,
        fail_count=fail_count,
        overall_status=overall,
    )
