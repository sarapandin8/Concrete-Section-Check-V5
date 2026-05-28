"""Bonded prestress PMM validation benchmark pack.

VALID.PS1 is intentionally a benchmark/verification layer, not a solver
rewrite.  It creates small deterministic PS-only and RC+PS sections so the
project can distinguish solver limitations from input mistakes before reducing
prestress-related engineering warnings in the UI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.code_checks import aci_max_phiPn, nominal_po_rc, nominal_po_rc_prestressed
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class PSBenchmarkCheck:
    """Single bonded-prestress validation check."""

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
class PSBenchmarkSummary:
    """Summary for the VALID.PS1 benchmark pack."""

    checks: list[PSBenchmarkCheck]
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


def _summary(checks: list[PSBenchmarkCheck]) -> PSBenchmarkSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return PSBenchmarkSummary(checks, pass_count, warning_count, fail_count, overall)


def _percent_difference(reference: float, solver: float) -> float:
    return abs(solver - reference) / max(abs(reference), 1.0) * 100.0


def _status_from_difference(percent_difference: float, tolerance_percent: float, fail_percent: float = 10.0) -> str:
    if not math.isfinite(percent_difference):
        return FAIL
    if percent_difference <= tolerance_percent:
        return PASS
    if percent_difference <= fail_percent:
        return WARNING
    return FAIL


def benchmark_concrete() -> ConcreteMaterial:
    return ConcreteMaterial(name="VALID.PS1 C40", fc_MPa=40.0, ecu=0.003)


def benchmark_rebar_material() -> RebarMaterial:
    return RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)


def benchmark_rebars() -> list[Rebar]:
    return [
        Rebar(x_mm=-150.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B1"),
        Rebar(x_mm=150.0, y_mm=-250.0, diameter_mm=25.0, material_name="Grade420", label="B2"),
        Rebar(x_mm=-150.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T1"),
        Rebar(x_mm=150.0, y_mm=250.0, diameter_mm=25.0, material_name="Grade420", label="T2"),
    ]


def benchmark_bonded_strand(**updates: object) -> PrestressElement:
    """Return one deterministic bonded strand/tendon-group element.

    ``area_mm2`` is treated as total prestressing steel area for this element.
    ``pe_eff_n`` is therefore the effective force for the same element.  This
    mirrors the current solver model and avoids Strand Count double counting.
    """

    data: dict[str, object] = {
        "x_mm": 0.0,
        "y_mm": -250.0,
        "area_mm2": 140.0,
        "steel_type": "strand",
        "material_name": "Tendon 6-1",
        "fpy_mpa": 1580.0,
        "fpu_mpa": 1860.0,
        "ep_mpa": 195000.0,
        "pe_eff_n": 140_000.0,  # 1000 MPa effective stress for 140 mm2.
        "bonded": True,
        "count": 1,
        "label": "PS1",
    }
    data.update(updates)
    return PrestressElement(**data)


def ps_only_input(**prestress_updates: object) -> AnalysisInput:
    prestress = benchmark_bonded_strand(**prestress_updates)
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0, name="VALID.PS1 PS-only rectangle"),
        concrete_material=benchmark_concrete(),
        rebar_materials=[benchmark_rebar_material()],
        rebars=[],
        prestress_elements=[prestress],
        load_cases=[LoadCase(name="ULS-PS1", Pu_N=500_000.0, Mux_Nmm=80_000_000.0, Muy_Nmm=0.0)],
        settings=AnalysisSettings(
            include_rebars=True,
            include_prestress=True,
            neutral_axis_angle_steps=24,
            neutral_axis_depth_steps=61,
            transverse_reinforcement="tied",
            prestress_stress_model="bilinear",
            subtract_rebar_displaced_concrete=True,
        ),
    )


def rc_plus_ps_input(**prestress_updates: object) -> AnalysisInput:
    prestress = benchmark_bonded_strand(**prestress_updates)
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0, name="VALID.PS1 RC+PS rectangle"),
        concrete_material=benchmark_concrete(),
        rebar_materials=[benchmark_rebar_material()],
        rebars=benchmark_rebars(),
        prestress_elements=[prestress],
        load_cases=[LoadCase(name="ULS-RCPS1", Pu_N=800_000.0, Mux_Nmm=120_000_000.0, Muy_Nmm=0.0)],
        settings=AnalysisSettings(
            include_rebars=True,
            include_prestress=True,
            neutral_axis_angle_steps=24,
            neutral_axis_depth_steps=61,
            transverse_reinforcement="tied",
            prestress_stress_model="bilinear",
            subtract_rebar_displaced_concrete=True,
        ),
    )


def rc_only_control_input() -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0, name="VALID.PS1 RC control rectangle"),
        concrete_material=benchmark_concrete(),
        rebar_materials=[benchmark_rebar_material()],
        rebars=benchmark_rebars(),
        prestress_elements=[],
        load_cases=[LoadCase(name="ULS-RC-CONTROL", Pu_N=800_000.0, Mux_Nmm=120_000_000.0, Muy_Nmm=0.0)],
        settings=AnalysisSettings(
            include_rebars=True,
            include_prestress=False,
            neutral_axis_angle_steps=24,
            neutral_axis_depth_steps=61,
            transverse_reinforcement="tied",
            subtract_rebar_displaced_concrete=True,
        ),
    )


def reference_ps_initial_stress_mpa(element: PrestressElement) -> float:
    return element.pe_eff_n / element.area_mm2


def reference_ps_initial_strain(element: PrestressElement) -> float:
    return reference_ps_initial_stress_mpa(element) / element.ep_mpa


def reference_ps_po_N(input_model: AnalysisInput) -> float:
    Ag = 400.0 * 600.0
    return nominal_po_rc_prestressed(
        input_model.concrete_material.fc_MPa,
        Ag,
        input_model.rebars,
        input_model.rebar_materials[0] if input_model.rebar_materials else None,
        input_model.prestress_elements,
    )


def _check_ps_only_eps_t_tracking() -> PSBenchmarkCheck:
    result = run_rc_pmm_solver(ps_only_input())
    tension_points = [point for point in result.points if point.eps_t is not None]
    transition_or_tension = [
        point for point in tension_points if point.strain_condition in {"transition", "tension-controlled"}
    ]
    ok = bool(result.points) and bool(tension_points) and bool(transition_or_tension) and max(point.phi for point in tension_points) > 0.65
    return PSBenchmarkCheck(
        check_id="VALID.PS1.PS_ONLY_EPST",
        title="PS-only bonded prestress can control eps_t and phi",
        status=PASS if ok else FAIL,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "Bonded prestress-only benchmark produces tensile-strain controlled PMM points for phi evaluation."
            if ok
            else "Bonded prestress-only benchmark did not produce expected eps_t/phi-controlled points."
        ),
        details={
            "point_count": len(result.points),
            "eps_t_point_count": len(tension_points),
            "transition_or_tension_count": len(transition_or_tension),
            "warnings": result.warnings,
        },
    )


def _check_initial_strain_from_pe_eff() -> PSBenchmarkCheck:
    element = benchmark_bonded_strand()
    reference_stress = 1000.0
    reference_strain = reference_stress / element.ep_mpa
    stress = reference_ps_initial_stress_mpa(element)
    strain = reference_ps_initial_strain(element)
    stress_diff = _percent_difference(reference_stress, stress)
    strain_diff = _percent_difference(reference_strain, strain)
    ok = stress_diff <= 1.0e-12 and strain_diff <= 1.0e-12
    return PSBenchmarkCheck(
        check_id="VALID.PS1.PE_EFF_TO_FPE",
        title="Pe_eff converts to fpe and initial strain without product metadata",
        status=PASS if ok else FAIL,
        reference_value=reference_stress,
        solver_value=stress,
        percent_difference=max(stress_diff, strain_diff),
        tolerance_percent=0.0,
        message=(
            "Prestress effective force converts to fpe and initial strain using Area and Ep only."
            if ok
            else "Prestress effective force conversion differs from benchmark expectation."
        ),
        details={
            "reference_stress_MPa": reference_stress,
            "computed_stress_MPa": stress,
            "reference_strain": reference_strain,
            "computed_strain": strain,
            "area_mm2": element.area_mm2,
            "pe_eff_N": element.pe_eff_n,
            "Ep_MPa": element.ep_mpa,
        },
    )


def _check_ps_po_inclusion() -> PSBenchmarkCheck:
    model = rc_plus_ps_input()
    Ag = 400.0 * 600.0
    rc_only_po = nominal_po_rc(model.concrete_material.fc_MPa, Ag, model.rebars, model.rebar_materials[0])
    ps_po = reference_ps_po_N(model)
    element = model.prestress_elements[0]
    Aps = element.area_mm2 * element.count
    expected_delta = element.fpy_mpa * Aps - 0.85 * model.concrete_material.fc_MPa * Aps
    actual_delta = ps_po - rc_only_po
    diff = _percent_difference(expected_delta, actual_delta)
    status = _status_from_difference(diff, tolerance_percent=0.01, fail_percent=1.0)
    return PSBenchmarkCheck(
        check_id="VALID.PS1.PO_INCLUDES_APS",
        title="Prestress-aware Po includes bonded Aps using fpy and deducts concrete area",
        status=status,
        reference_value=expected_delta,
        solver_value=actual_delta,
        percent_difference=diff,
        tolerance_percent=0.01,
        message=(
            "Prestress-aware Po delta matches the independent Aps(fpy - 0.85fc') benchmark."
            if status == PASS
            else "Prestress-aware Po delta differs from Aps strength benchmark; review Po helper."
        ),
        details={"rc_only_po_N": rc_only_po, "ps_po_N": ps_po, "Aps_mm2": Aps, "fpy_MPa": element.fpy_mpa},
    )


def _check_rc_plus_ps_capacity_trend() -> PSBenchmarkCheck:
    rc_result = run_rc_pmm_solver(rc_only_control_input())
    ps_result = run_rc_pmm_solver(rc_plus_ps_input())
    rc_df = pmm_result_to_display_dataframe(rc_result)
    ps_df = pmm_result_to_display_dataframe(ps_result)
    if rc_df.empty or ps_df.empty:
        return PSBenchmarkCheck(
            check_id="VALID.PS1.RCPS_CAPACITY_TREND",
            title="RC+PS benchmark produces usable PMM capacity data",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=None,
            message="RC-only or RC+PS PMM result is empty.",
        )
    rc_max_mx = float(rc_df["phiMnx_Nmm"].abs().max())
    ps_max_mx = float(ps_df["phiMnx_Nmm"].abs().max())
    prestress_points = int((ps_df["prestress_force_N"].abs() > 0.0).sum())
    # A bonded tendon near the bottom fiber should affect the Mx envelope in this
    # deterministic benchmark.  The check is trend-based, not a certification.
    trend_ok = ps_max_mx > rc_max_mx and prestress_points > 0
    diff = _percent_difference(rc_max_mx, ps_max_mx)
    return PSBenchmarkCheck(
        check_id="VALID.PS1.RCPS_CAPACITY_TREND",
        title="RC+PS benchmark shows prestress contribution in PMM results",
        status=PASS if trend_ok else WARNING,
        reference_value=rc_max_mx,
        solver_value=ps_max_mx,
        percent_difference=diff,
        tolerance_percent=None,
        message=(
            "RC+PS benchmark has nonzero prestress force and a changed Mx capacity envelope relative to RC-only control."
            if trend_ok
            else "RC+PS benchmark did not show the expected capacity trend; review tendon layout and benchmark assumptions."
        ),
        details={"rc_max_abs_phiMnx_Nmm": rc_max_mx, "rcps_max_abs_phiMnx_Nmm": ps_max_mx, "prestress_points": prestress_points},
    )


def _check_stress_warning_metadata() -> PSBenchmarkCheck:
    # Use a deliberately high effective stress to exercise stress-warning metadata
    # without changing production solver equations.
    result = run_rc_pmm_solver(ps_only_input(pe_eff_n=245_000.0, label="PS-HIGH"))
    df = pmm_result_to_display_dataframe(result)
    if df.empty:
        return PSBenchmarkCheck(
            check_id="VALID.PS1.STRESS_WARNING_METADATA",
            title="Prestress stress warnings are exposed as PMM metadata",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=None,
            message="High-prestress benchmark produced no PMM result points.",
        )
    fpu_cap_points = int((df["prestress_reached_fpu_cap_count"] > 0).sum())
    stress_warning_points = int((df["prestress_stress_warning_count"] > 0).sum())
    # fpu-cap events are expected at some ultimate PMM failure-envelope points.
    # They are retained as PMM metadata, not emitted as standalone global
    # engineering warnings unless governing-impact checks require escalation.
    ok = fpu_cap_points > 0 and not any("fpu cap" in warning for warning in result.warnings)
    return PSBenchmarkCheck(
        check_id="VALID.PS1.STRESS_WARNING_METADATA",
        title="Prestress fpu-cap warnings are traceable to PMM point metadata",
        status=PASS if ok else WARNING,
        reference_value=1.0,
        solver_value=1.0 if ok else 0.0,
        percent_difference=0.0 if ok else 100.0,
        tolerance_percent=0.0,
        message=(
            "High-prestress benchmark records fpu-cap events in PMM point metadata without promoting background cap events to global warnings."
            if ok
            else "High-prestress benchmark did not expose expected fpu-cap metadata or still emits background fpu-cap global warnings; review stress-state instrumentation."
        ),
        details={
            "point_count": len(df),
            "fpu_cap_points": fpu_cap_points,
            "stress_warning_points": stress_warning_points,
            "warnings": result.warnings,
        },
    )


def _check_numeric_schema() -> PSBenchmarkCheck:
    result = run_rc_pmm_solver(rc_plus_ps_input())
    df = pmm_result_to_display_dataframe(result)
    required = [
        "Pn_N",
        "Mnx_Nmm",
        "Mny_Nmm",
        "phi",
        "phiPn_N",
        "phiMnx_Nmm",
        "phiMny_Nmm",
        "prestress_force_N",
        "max_prestress_stress_MPa",
    ]
    if df.empty:
        return PSBenchmarkCheck(
            check_id="VALID.PS1.NUMERIC_SCHEMA",
            title="Prestress PMM numeric result schema is finite",
            status=FAIL,
            reference_value=None,
            solver_value=None,
            percent_difference=None,
            tolerance_percent=None,
            message="RC+PS PMM result dataframe is empty.",
        )
    numeric = df[required].apply(pd.to_numeric, errors="coerce")
    bad_columns = [column for column in required if numeric[column].isna().any() or not numeric[column].map(math.isfinite).all()]
    return PSBenchmarkCheck(
        check_id="VALID.PS1.NUMERIC_SCHEMA",
        title="Prestress PMM capacity-critical columns contain finite values",
        status=PASS if not bad_columns else FAIL,
        reference_value=0.0,
        solver_value=float(len(bad_columns)),
        percent_difference=0.0 if not bad_columns else 100.0,
        tolerance_percent=0.0,
        message=(
            "Capacity-critical RC+PS PMM columns are finite. eps_t may be absent for compression-controlled points by design."
            if not bad_columns
            else "One or more capacity-critical RC+PS PMM columns contain NaN/Inf values."
        ),
        details={"bad_columns": bad_columns, "point_count": len(df)},
    )


def run_valid_ps1_bonded_prestress_benchmark_pack() -> PSBenchmarkSummary:
    """Run the VALID.PS1 bonded prestress benchmark pack."""

    checks = [
        _check_ps_only_eps_t_tracking(),
        _check_initial_strain_from_pe_eff(),
        _check_ps_po_inclusion(),
        _check_rc_plus_ps_capacity_trend(),
        _check_stress_warning_metadata(),
        _check_numeric_schema(),
    ]
    return _summary(checks)
