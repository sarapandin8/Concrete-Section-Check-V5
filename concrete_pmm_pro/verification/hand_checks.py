"""Independent hand-calculation spot checks for PMM prototypes.

These checks are intentionally simple engineering-review comparisons. They do
not replace independent detailed validation or code-certified software.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.prestress_stress import (
    PRESTRESS_COMPRESSION_REVERSAL_WARNING,
    PRESTRESS_FPU_CAP_WARNING,
    prestress_stress_mpa,
    prestress_total_tensile_strain,
)
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.analysis.strain_compatibility import rebar_net_force_n
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class HandCheckResult:
    name: str
    status: str
    calculated_value: float | None
    solver_value: float | None
    percent_difference: float | None
    tolerance_percent: float | None
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HandCheckSummary:
    checks: list[HandCheckResult] = field(default_factory=list)
    pass_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    overall_status: str = PASS
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _summary(checks: list[HandCheckResult], warnings: list[str] | None = None, info: list[str] | None = None) -> HandCheckSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall_status = FAIL if fail_count else WARNING if warning_count else PASS
    return HandCheckSummary(
        checks=checks,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        overall_status=overall_status,
        warnings=warnings or [],
        info=info or [],
    )


def _percent_difference(calculated: float, solver: float) -> float:
    denominator = max(abs(calculated), 1.0)
    return abs(solver - calculated) / denominator * 100.0


def _status_from_difference(percent_difference: float, tolerance_percent: float, fail_percent: float = 25.0) -> str:
    if not math.isfinite(percent_difference):
        return FAIL
    if percent_difference <= tolerance_percent:
        return PASS
    if percent_difference <= fail_percent:
        return WARNING
    return FAIL


def _aci_beta1_independent(fc_MPa: float) -> float:
    if fc_MPa <= 28.0:
        return 0.85
    return max(0.65, 0.85 - 0.05 * ((fc_MPa - 28.0) / 7.0))


def hand_po_rc(
    fc_MPa: float,
    Ag_mm2: float,
    rebars: list[Rebar],
    rebar_material_default: RebarMaterial | None = None,
    subtract_rebar_area: bool = True,
) -> float:
    """Return independent hand Po for ordinary RC axial compression."""

    if fc_MPa <= 0.0:
        raise ValueError("fc_MPa must be positive.")
    if Ag_mm2 <= 0.0:
        raise ValueError("Ag_mm2 must be positive.")
    default_material = rebar_material_default or RebarMaterial(name="Default", fy_MPa=390.0)
    Ast = sum(rebar.area_mm2 for rebar in rebars)
    concrete_area = Ag_mm2 - Ast if subtract_rebar_area else Ag_mm2
    if concrete_area < 0.0:
        raise ValueError("Ag_mm2 minus total rebar area must not be negative.")

    steel_force = 0.0
    for rebar in rebars:
        fy = getattr(rebar, "fy_MPa", None) or getattr(rebar, "fy_mpa", None) or default_material.fy_MPa
        steel_force += float(fy) * rebar.area_mm2
    return 0.85 * fc_MPa * concrete_area + steel_force


def hand_phiPn_max_rc(Po_N: float, transverse_reinforcement: str) -> float:
    """Return independent ACI-style prototype max phiPn."""

    if transverse_reinforcement == "tied":
        return 0.80 * 0.65 * Po_N
    if transverse_reinforcement == "spiral":
        return 0.85 * 0.75 * Po_N
    raise ValueError("transverse_reinforcement must be tied or spiral.")


def check_rebar_displaced_concrete_spot() -> HandCheckResult:
    inside_force, inside_metadata = rebar_net_force_n(1000.0, 400.0, 40.0, inside_compression_block=True)
    outside_force, outside_metadata = rebar_net_force_n(1000.0, 400.0, 40.0, inside_compression_block=False)
    expected_inside = 1000.0 * (400.0 - 0.85 * 40.0)
    expected_outside = 1000.0 * 400.0
    ok = abs(inside_force - expected_inside) <= 1.0e-9 and abs(outside_force - expected_outside) <= 1.0e-9
    return HandCheckResult(
        name="Rebar displaced concrete spot check",
        status=PASS if ok else FAIL,
        calculated_value=expected_inside,
        solver_value=inside_force,
        percent_difference=_percent_difference(expected_inside, inside_force),
        tolerance_percent=0.01,
        message="Rebar net force matches hand calculation inside and outside compression block."
        if ok
        else "Rebar net force does not match hand calculation.",
        details={
            "expected_inside_N": expected_inside,
            "inside_force_N": inside_force,
            "inside_metadata": inside_metadata,
            "expected_outside_N": expected_outside,
            "outside_force_N": outside_force,
            "outside_metadata": outside_metadata,
        },
    )


def check_prestress_strain_spot() -> HandCheckResult:
    compression_total = prestress_total_tensile_strain(0.005, 0.001)
    tension_total = prestress_total_tensile_strain(0.005, -0.001)
    raw_reversal = prestress_total_tensile_strain(0.0005, 0.001)
    stress, warnings = prestress_stress_mpa(raw_reversal, Ep_MPa=200000.0, fpu_MPa=1180.0, fpy_MPa=930.0)
    ok = (
        compression_total == 0.004
        and tension_total == 0.006
        and raw_reversal == -0.0005
        and stress == 0.0
        and PRESTRESS_COMPRESSION_REVERSAL_WARNING in warnings
    )
    return HandCheckResult(
        name="Prestress strain convention spot check",
        status=PASS if ok else FAIL,
        calculated_value=0.004,
        solver_value=compression_total,
        percent_difference=_percent_difference(0.004, compression_total),
        tolerance_percent=0.01,
        message="Prestress strain convention eps_pe - eps_section and compression clamp match hand expectation."
        if ok
        else "Prestress strain convention spot check did not match expected values.",
        details={
            "compression_case_total": compression_total,
            "tension_case_total": tension_total,
            "raw_reversal_total": raw_reversal,
            "reversal_stress": stress,
            "warnings": warnings,
        },
    )


def check_prestress_stress_spot() -> HandCheckResult:
    linear_stress, linear_warnings = prestress_stress_mpa(0.004, Ep_MPa=200000.0, fpu_MPa=1180.0, model="linear_cap")
    capped_stress, cap_warnings = prestress_stress_mpa(0.010, Ep_MPa=200000.0, fpu_MPa=1180.0, model="linear_cap")
    bilinear_stress, bilinear_warnings = prestress_stress_mpa(
        0.006,
        Ep_MPa=200000.0,
        fpu_MPa=1180.0,
        fpy_MPa=930.0,
        model="bilinear",
    )
    eps_y = 930.0 / 200000.0
    expected_bilinear = 930.0 + 0.02 * 200000.0 * (0.006 - eps_y)
    ok = (
        linear_stress == 800.0
        and capped_stress == 1180.0
        and PRESTRESS_FPU_CAP_WARNING in cap_warnings
        and bilinear_stress == expected_bilinear
    )
    return HandCheckResult(
        name="Prestress stress model spot check",
        status=PASS if ok else FAIL,
        calculated_value=expected_bilinear,
        solver_value=bilinear_stress,
        percent_difference=_percent_difference(expected_bilinear, bilinear_stress),
        tolerance_percent=0.01,
        message="Linear cap, fpu cap, and bilinear prestress stresses match hand spot checks."
        if ok
        else "Prestress stress model spot check did not match expected values.",
        details={
            "linear_stress_MPa": linear_stress,
            "linear_warnings": linear_warnings,
            "capped_stress_MPa": capped_stress,
            "cap_warnings": cap_warnings,
            "bilinear_stress_MPa": bilinear_stress,
            "bilinear_expected_MPa": expected_bilinear,
            "bilinear_warnings": bilinear_warnings,
        },
    )


def _benchmark_rebars() -> list[Rebar]:
    return [
        Rebar(x_mm=-225.0, y_mm=-225.0, diameter_mm=25.0, material_name="Grade420", label="B1"),
        Rebar(x_mm=225.0, y_mm=-225.0, diameter_mm=25.0, material_name="Grade420", label="B2"),
        Rebar(x_mm=225.0, y_mm=225.0, diameter_mm=25.0, material_name="Grade420", label="B3"),
        Rebar(x_mm=-225.0, y_mm=225.0, diameter_mm=25.0, material_name="Grade420", label="B4"),
        Rebar(x_mm=0.0, y_mm=-225.0, diameter_mm=25.0, material_name="Grade420", label="B5"),
        Rebar(x_mm=225.0, y_mm=0.0, diameter_mm=25.0, material_name="Grade420", label="B6"),
        Rebar(x_mm=0.0, y_mm=225.0, diameter_mm=25.0, material_name="Grade420", label="B7"),
        Rebar(x_mm=-225.0, y_mm=0.0, diameter_mm=25.0, material_name="Grade420", label="B8"),
    ]


def _base_hand_input() -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=600.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="Hand C35", fc_MPa=35.0, ecu=0.003),
        rebar_materials=[RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)],
        rebars=_benchmark_rebars(),
        load_cases=[LoadCase(name="ULS-HAND", Pu_N=1_000_000.0, Mux_Nmm=120_000_000.0, Muy_Nmm=80_000_000.0)],
        settings=AnalysisSettings(
            include_rebars=True,
            include_prestress=False,
            neutral_axis_angle_steps=24,
            neutral_axis_depth_steps=32,
            transverse_reinforcement="tied",
        ),
    )


def check_axial_compression_hand(input_model: AnalysisInput | None = None) -> HandCheckResult:
    analysis_input = input_model or _base_hand_input()
    result = run_rc_pmm_solver(analysis_input)
    df = pmm_result_to_display_dataframe(result)
    if df.empty:
        return HandCheckResult(
            name="Axial compression hand phiPn,max check",
            status=FAIL,
            calculated_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=10.0,
            message="Solver PMM result is empty.",
            details={},
        )
    Ag = 600.0 * 600.0
    Po = hand_po_rc(
        analysis_input.concrete_material.fc_MPa,
        Ag,
        analysis_input.rebars,
        analysis_input.rebar_materials[0] if analysis_input.rebar_materials else None,
    )
    hand_phi = hand_phiPn_max_rc(Po, analysis_input.settings.transverse_reinforcement)
    solver_phi = float(df["phiPn_capped_N"].max())
    difference = _percent_difference(hand_phi, solver_phi)
    status = _status_from_difference(difference, tolerance_percent=10.0, fail_percent=25.0)
    if solver_phi <= 0.0 or not math.isfinite(solver_phi):
        status = FAIL
    return HandCheckResult(
        name="Axial compression hand phiPn,max check",
        status=status,
        calculated_value=hand_phi,
        solver_value=solver_phi,
        percent_difference=difference,
        tolerance_percent=10.0,
        message="Solver capped axial capacity is within prototype tolerance of hand phiPn,max."
        if status == PASS
        else "Solver capped axial capacity differs from hand phiPn,max; review discretization and axial cap assumptions.",
        details={"Po_N": Po, "solver_point_count": len(result.points)},
    )


def hand_rectangular_uniaxial_section_point(
    b_mm: float = 400.0,
    h_mm: float = 600.0,
    fc_MPa: float = 40.0,
    fy_MPa: float = 420.0,
    Es_MPa: float = 200000.0,
    ecu: float = 0.003,
    c_mm: float = 300.0,
    subtract_displaced_concrete: bool = True,
) -> dict[str, Any]:
    """Return a simple independent uniaxial rectangular section point."""

    beta1 = _aci_beta1_independent(fc_MPa)
    a_mm = min(beta1 * c_mm, h_mm)
    concrete_stress = 0.85 * fc_MPa
    concrete_force = concrete_stress * b_mm * a_mm
    y_ref = 0.0
    y_top = h_mm / 2.0
    y_block_bottom = y_top - a_mm
    concrete_y = y_top - a_mm / 2.0
    Pn = concrete_force
    Mnx = concrete_force * (concrete_y - y_ref)

    rebar_layers = [
        {"count": 2, "y_mm": h_mm / 2.0 - 50.0, "diameter_mm": 25.0},
        {"count": 2, "y_mm": -h_mm / 2.0 + 50.0, "diameter_mm": 25.0},
    ]
    rebar_details: list[dict[str, Any]] = []
    for layer in rebar_layers:
        area_each = math.pi * float(layer["diameter_mm"]) ** 2 / 4.0
        y = float(layer["y_mm"])
        distance_from_top = y_top - y
        eps_s = ecu * (1.0 - distance_from_top / c_mm)
        fs = max(-fy_MPa, min(fy_MPa, Es_MPa * eps_s))
        inside = y >= y_block_bottom
        force_each, metadata = rebar_net_force_n(area_each, fs, fc_MPa, inside, subtract_displaced_concrete)
        total_force = force_each * int(layer["count"])
        Pn += total_force
        Mnx += total_force * (y - y_ref)
        rebar_details.append({"y_mm": y, "eps_s": eps_s, "fs_MPa": fs, "inside": inside, "force_N": total_force, "metadata": metadata})

    return {
        "Pn_N": Pn,
        "Mnx_Nmm": Mnx,
        "beta1": beta1,
        "a_mm": a_mm,
        "concrete_force_N": concrete_force,
        "rebar_details": rebar_details,
    }


def _uniaxial_solver_input() -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="Hand C40", fc_MPa=40.0, ecu=0.003),
        rebar_materials=[RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)],
        rebars=[
            Rebar(x_mm=-125.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T1"),
            Rebar(x_mm=125.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T2"),
            Rebar(x_mm=-125.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B1"),
            Rebar(x_mm=125.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B2"),
        ],
        load_cases=[LoadCase(name="ULS-HAND-UNI", Pu_N=500_000.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0)],
        settings=AnalysisSettings(
            neutral_axis_angle_steps=12,
            neutral_axis_depth_steps=61,
            transverse_reinforcement="tied",
            subtract_rebar_displaced_concrete=True,
        ),
    )


def check_uniaxial_rc_spot() -> HandCheckResult:
    hand = hand_rectangular_uniaxial_section_point()
    result = run_rc_pmm_solver(_uniaxial_solver_input())
    if not result.points:
        return HandCheckResult(
            name="Uniaxial RC strain compatibility spot check",
            status=WARNING,
            calculated_value=hand["Pn_N"],
            solver_value=None,
            percent_difference=None,
            tolerance_percent=15.0,
            message="Solver produced no points for uniaxial spot check.",
            details={"hand": hand},
        )

    target_theta = math.pi / 2.0
    target_c = 300.0
    candidates = sorted(
        result.points,
        key=lambda point: (
            abs((point.theta_rad - target_theta + math.pi) % (2.0 * math.pi) - math.pi),
            abs(point.c_mm - target_c),
        ),
    )
    nearest = candidates[0]
    theta_diff = abs((nearest.theta_rad - target_theta + math.pi) % (2.0 * math.pi) - math.pi)
    if theta_diff > 1.0e-9 or abs(nearest.c_mm - target_c) > 35.0:
        return HandCheckResult(
            name="Uniaxial RC strain compatibility spot check",
            status=WARNING,
            calculated_value=hand["Pn_N"],
            solver_value=nearest.Pn_N,
            percent_difference=_percent_difference(hand["Pn_N"], nearest.Pn_N),
            tolerance_percent=15.0,
            message="Nearest solver theta/c point is too far from the hand-check target; review discretization.",
            details={"hand": hand, "nearest_theta": nearest.theta_rad, "nearest_c_mm": nearest.c_mm},
        )

    p_diff = _percent_difference(hand["Pn_N"], nearest.Pn_N)
    m_diff = _percent_difference(hand["Mnx_Nmm"], nearest.Mnx_Nmm)
    status = PASS if p_diff <= 15.0 and m_diff <= 20.0 else WARNING
    return HandCheckResult(
        name="Uniaxial RC strain compatibility spot check",
        status=status,
        calculated_value=hand["Mnx_Nmm"],
        solver_value=nearest.Mnx_Nmm,
        percent_difference=m_diff,
        tolerance_percent=20.0,
        message="Simplified hand P/M point agrees with nearest solver point within prototype tolerance."
        if status == PASS
        else "Simplified hand P/M point differs from nearest solver point; review discretization and assumptions.",
        details={
            "hand": hand,
            "solver_Pn_N": nearest.Pn_N,
            "solver_Mnx_Nmm": nearest.Mnx_Nmm,
            "solver_theta_rad": nearest.theta_rad,
            "solver_c_mm": nearest.c_mm,
            "Pn_percent_difference": p_diff,
            "Mnx_percent_difference": m_diff,
        },
    )


def check_symmetry_spot() -> list[HandCheckResult]:
    result = run_rc_pmm_solver(_base_hand_input())
    df = pmm_result_to_display_dataframe(result)
    checks: list[HandCheckResult] = []
    for column, axis in [("phiMnx_Nmm", "Mnx"), ("phiMny_Nmm", "Mny")]:
        positive = float(df[column].max())
        negative_magnitude = abs(float(df[column].min()))
        imbalance = abs(positive - negative_magnitude) / max(positive, negative_magnitude, 1.0) * 100.0
        if not math.isfinite(imbalance) or positive <= 0.0 or negative_magnitude <= 0.0:
            status = FAIL
        elif imbalance <= 20.0:
            status = PASS
        else:
            status = WARNING
        checks.append(
            HandCheckResult(
                name=f"Symmetry sanity spot check {axis}",
                status=status,
                calculated_value=positive,
                solver_value=negative_magnitude,
                percent_difference=imbalance,
                tolerance_percent=20.0,
                message=f"Positive and negative {axis} capacities are reasonably balanced."
                if status == PASS
                else f"Positive and negative {axis} capacities show notable imbalance; review discretization.",
                details={"positive": positive, "negative_magnitude": negative_magnitude},
            )
        )
    return checks


def run_independent_hand_check_suite() -> HandCheckSummary:
    """Run independent PMM hand-calculation spot checks."""

    checks = [
        check_axial_compression_hand(),
        check_rebar_displaced_concrete_spot(),
        check_prestress_strain_spot(),
        check_prestress_stress_spot(),
        check_uniaxial_rc_spot(),
    ]
    checks.extend(check_symmetry_spot())
    return _summary(
        checks,
        warnings=[
            "Hand checks are simplified spot checks for engineering review and do not replace independent detailed validation."
        ],
        info=[f"Ran {len(checks)} independent hand-check item(s)."],
    )


def hand_check_summary_to_dataframe(summary: HandCheckSummary) -> pd.DataFrame:
    """Return a stable display/export dataframe for hand check summaries."""

    return pd.DataFrame(
        [
            {
                "Check": check.name,
                "Status": check.status,
                "Calculated Value": check.calculated_value,
                "Solver Value": check.solver_value,
                "Percent Difference": check.percent_difference,
                "Tolerance Percent": check.tolerance_percent,
                "Message": check.message,
            }
            for check in summary.checks
        ]
    )
