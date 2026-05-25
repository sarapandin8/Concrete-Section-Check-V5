"""Benchmark-style PMM verification cases.

These checks are engineering sanity checks for the current prototype. They are
not independent design certification and deliberately avoid production-grade
PMM interpolation assumptions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import PMMSolverResult, pmm_result_to_display_dataframe, summarize_pmm_result
from concrete_pmm_pro.analysis.slice_envelope import (
    build_convex_hull_envelope,
    build_slice_envelope,
    estimate_directional_capacity_from_envelope,
)
from concrete_pmm_pro.analysis.strain_compatibility import rebar_net_force_n
from concrete_pmm_pro.code_checks import nominal_po_rc
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import (
    ConcreteMaterial,
    LoadCase,
    Point2D,
    PrestressElement,
    PrestressSteelMaterial,
    Rebar,
    RebarMaterial,
    SectionGeometry,
)
from concrete_pmm_pro.visualization.pmm_dashboard import (
    estimate_directional_capacity_from_slice,
    pmm_slice_at_pu_interpolated,
)

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class PMMVerificationCheck:
    name: str
    status: str
    message: str
    values: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PMMVerificationSummary:
    checks: list[PMMVerificationCheck]
    pass_count: int
    warning_count: int
    fail_count: int
    overall_status: str


def _summary(checks: list[PMMVerificationCheck]) -> PMMVerificationSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    if fail_count:
        overall_status = FAIL
    elif warning_count:
        overall_status = WARNING
    else:
        overall_status = PASS
    return PMMVerificationSummary(
        checks=checks,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        overall_status=overall_status,
    )


def _rectangular_geometry(B_mm: float = 600.0, H_mm: float = 600.0) -> SectionGeometry:
    half_b = B_mm / 2.0
    half_h = H_mm / 2.0
    return SectionGeometry(
        name="Benchmark rectangular column",
        outer_polygon=[
            Point2D(x=-half_b, y=-half_h),
            Point2D(x=half_b, y=-half_h),
            Point2D(x=half_b, y=half_h),
            Point2D(x=-half_b, y=half_h),
        ],
        holes=[],
        metadata={"benchmark": True, "B_mm": B_mm, "H_mm": H_mm},
    )


def _symmetric_rebars(diameter_mm: float = 25.0, offset_mm: float = 225.0) -> list[Rebar]:
    points = [
        (-offset_mm, -offset_mm),
        (offset_mm, -offset_mm),
        (offset_mm, offset_mm),
        (-offset_mm, offset_mm),
        (0.0, -offset_mm),
        (offset_mm, 0.0),
        (0.0, offset_mm),
        (-offset_mm, 0.0),
    ]
    return [
        Rebar(x_mm=x, y_mm=y, diameter_mm=diameter_mm, material_name="Grade420", label=f"B{index + 1}")
        for index, (x, y) in enumerate(points)
    ]


def _benchmark_settings(include_prestress: bool) -> AnalysisSettings:
    return AnalysisSettings(
        include_rebars=True,
        include_prestress=include_prestress,
        use_phi_factor=True,
        transverse_reinforcement="tied",
        neutral_axis_angle_steps=24,
        neutral_axis_depth_steps=32,
        note="Benchmark verification settings.",
    )


def _benchmark_load_cases() -> list[LoadCase]:
    return [
        LoadCase(
            name="ULS-BENCH",
            Pu_N=1_000_000.0,
            Mux_Nmm=120_000_000.0,
            Muy_Nmm=80_000_000.0,
            load_type="ULS",
            active=True,
        )
    ]


def _pt_bar_material() -> PrestressSteelMaterial:
    return PrestressSteelMaterial(
        name="PT Bar Benchmark 32 - 835/1030",
        steel_type="prestressing_bar",
        diameter_mm=32.0,
        area_mm2=math.pi * 32.0**2 / 4.0,
        grade="835/1030",
        fpy_MPa=835.0,
        fpu_MPa=1030.0,
        Ep_MPa=195000.0,
        source="benchmark",
        area_source="pi*d^2/4",
    )


def _pt_bar_element(bonded: bool = True) -> PrestressElement:
    area = math.pi * 32.0**2 / 4.0
    return PrestressElement(
        id="benchmark-pt-bar",
        label="PTB1",
        steel_type="prestressing_bar",
        x_mm=0.0,
        y_mm=-225.0,
        area_mm2=area,
        diameter_mm=32.0,
        material_name="PT Bar Benchmark 32 - 835/1030",
        fpy_mpa=835.0,
        fpu_mpa=1030.0,
        ep_mpa=195000.0,
        initial_stress_mpa=650.0,
        pe_eff_n=650.0 * area,
        bonded=bonded,
        count=2,
    )


def _case(fc_MPa: float = 35.0, rebar_diameter_mm: float = 25.0, prestress: list[PrestressElement] | None = None, include_prestress: bool = False) -> AnalysisInput:
    rebar_material = RebarMaterial(name="Grade420", fy_MPa=420.0, Es_MPa=200000.0)
    prestress_elements = prestress or []
    prestress_materials = [_pt_bar_material()] if prestress_elements else []
    return AnalysisInput(
        section_geometry=_rectangular_geometry(),
        concrete_material=ConcreteMaterial(name=f"Concrete fc {fc_MPa:g}", fc_MPa=fc_MPa, ecu=0.003),
        rebar_materials=[rebar_material],
        prestress_materials=prestress_materials,
        rebars=_symmetric_rebars(rebar_diameter_mm),
        prestress_elements=prestress_elements,
        load_cases=_benchmark_load_cases(),
        settings=_benchmark_settings(include_prestress),
    )


def build_rectangular_rc_column_case() -> AnalysisInput:
    return _case(fc_MPa=35.0, rebar_diameter_mm=25.0, include_prestress=False)


def build_rectangular_rc_column_high_fc_case() -> AnalysisInput:
    return _case(fc_MPa=55.0, rebar_diameter_mm=25.0, include_prestress=False)


def build_rectangular_rc_column_high_as_case() -> AnalysisInput:
    return _case(fc_MPa=35.0, rebar_diameter_mm=36.0, include_prestress=False)


def build_rectangular_rc_with_bonded_pt_bar_case() -> AnalysisInput:
    return _case(fc_MPa=35.0, rebar_diameter_mm=25.0, prestress=[_pt_bar_element(bonded=True)], include_prestress=True)


def build_rectangular_rc_without_prestress_matching_case() -> AnalysisInput:
    return _case(fc_MPa=35.0, rebar_diameter_mm=25.0, include_prestress=False)


def _build_rectangular_rc_with_unbonded_pt_bar_case() -> AnalysisInput:
    return _case(fc_MPa=35.0, rebar_diameter_mm=25.0, prestress=[_pt_bar_element(bonded=False)], include_prestress=True)


def _max_capped_phiPn(result: PMMSolverResult) -> float:
    df = pmm_result_to_display_dataframe(result)
    return float(df["phiPn_capped_N"].max()) if not df.empty else 0.0


def _max_abs_column(result: PMMSolverResult, column: str) -> float:
    df = pmm_result_to_display_dataframe(result)
    return float(df[column].abs().max()) if not df.empty else 0.0


def _finite_result_check(name: str, result: PMMSolverResult) -> PMMVerificationCheck:
    summary = summarize_pmm_result(result)
    ok = summary["point_count"] > 0 and not summary["has_nan"] and not summary["has_inf"]
    return PMMVerificationCheck(
        name=name,
        status=PASS if ok else FAIL,
        message="PMM result is finite and non-empty." if ok else "PMM result is empty or contains NaN/Inf.",
        values=summary,
    )


def _positive_negative_balance(result: PMMSolverResult, column: str, tolerance: float = 0.20) -> PMMVerificationCheck:
    df = pmm_result_to_display_dataframe(result)
    positive = float(df[column].max())
    negative_magnitude = abs(float(df[column].min()))
    denominator = max(positive, negative_magnitude, 1.0)
    imbalance = abs(positive - negative_magnitude) / denominator
    ok = positive > 0.0 and negative_magnitude > 0.0 and imbalance <= tolerance
    axis = "Mnx" if "Mnx" in column else "Mny"
    return PMMVerificationCheck(
        name=f"Symmetry balance {axis}",
        status=PASS if ok else WARNING,
        message=(
            f"Positive/negative {axis} capacities are balanced within {tolerance:.0%}."
            if ok
            else f"Positive/negative {axis} capacity imbalance exceeds {tolerance:.0%}; review point-cloud discretization."
        ),
        values={"positive": positive, "negative_magnitude": negative_magnitude, "imbalance": imbalance},
    )


def run_pmm_verification_suite() -> PMMVerificationSummary:
    base_input = build_rectangular_rc_column_case()
    high_fc_input = build_rectangular_rc_column_high_fc_case()
    high_as_input = build_rectangular_rc_column_high_as_case()
    pt_input = build_rectangular_rc_with_bonded_pt_bar_case()
    rc_matching_input = build_rectangular_rc_without_prestress_matching_case()
    unbonded_input = _build_rectangular_rc_with_unbonded_pt_bar_case()

    base_result = run_rc_pmm_solver(base_input)
    high_fc_result = run_rc_pmm_solver(high_fc_input)
    high_as_result = run_rc_pmm_solver(high_as_input)
    pt_result = run_rc_pmm_solver(pt_input)
    rc_matching_result = run_rc_pmm_solver(rc_matching_input)
    unbonded_result = run_rc_pmm_solver(unbonded_input)
    no_displacement_input = base_input.model_copy(deep=True)
    no_displacement_input.settings = no_displacement_input.settings.model_copy(update={"subtract_rebar_displaced_concrete": False})
    no_displacement_result = run_rc_pmm_solver(no_displacement_input)

    checks: list[PMMVerificationCheck] = []
    checks.append(_finite_result_check("Base RC finite result", base_result))

    base_cap = _max_capped_phiPn(base_result)
    po = nominal_po_rc(
        base_input.concrete_material.fc_MPa,
        600.0 * 600.0,
        base_input.rebars,
        base_input.rebar_materials[0],
    )
    cap_upper = 1.05 * po
    checks.append(
        PMMVerificationCheck(
            name="Axial compression sanity",
            status=PASS if 0.0 < base_cap < cap_upper else FAIL,
            message="Max capped phiPn is positive and below a nominal Po-like upper bound."
            if 0.0 < base_cap < cap_upper
            else "Max capped phiPn is outside the expected benchmark range.",
            values={"max_capped_phiPn_N": base_cap, "po_upper_bound_N": cap_upper},
        )
    )

    high_fc_cap = _max_capped_phiPn(high_fc_result)
    checks.append(
        PMMVerificationCheck(
            name="Higher fc increases compression capacity",
            status=PASS if high_fc_cap > base_cap else FAIL,
            message="Higher f'c increases max capped phiPn." if high_fc_cap > base_cap else "Higher f'c did not increase max capped phiPn.",
            values={"base_phiPn_capped_N": base_cap, "high_fc_phiPn_capped_N": high_fc_cap},
        )
    )

    high_as_cap = _max_capped_phiPn(high_as_result)
    checks.append(
        PMMVerificationCheck(
            name="Higher As does not reduce compression capacity",
            status=PASS if high_as_cap >= 0.995 * base_cap else FAIL,
            message="Higher As does not reduce max capped phiPn." if high_as_cap >= 0.995 * base_cap else "Higher As reduced max capped phiPn.",
            values={"base_phiPn_capped_N": base_cap, "high_as_phiPn_capped_N": high_as_cap},
        )
    )

    gross_force, _gross_meta = rebar_net_force_n(
        area_mm2=100.0,
        steel_stress_MPa=300.0,
        fc_MPa=35.0,
        inside_compression_block=True,
        subtract_displaced_concrete=False,
    )
    net_force, _net_meta = rebar_net_force_n(
        area_mm2=100.0,
        steel_stress_MPa=300.0,
        fc_MPa=35.0,
        inside_compression_block=True,
        subtract_displaced_concrete=True,
    )
    outside_force, _outside_meta = rebar_net_force_n(
        area_mm2=100.0,
        steel_stress_MPa=300.0,
        fc_MPa=35.0,
        inside_compression_block=False,
        subtract_displaced_concrete=True,
    )
    checks.append(
        PMMVerificationCheck(
            name="Rebar net force inside compression block",
            status=PASS if net_force < gross_force else FAIL,
            message="Displaced concrete subtraction reduces compressive rebar force inside the compression block."
            if net_force < gross_force
            else "Displaced concrete subtraction did not reduce inside-block rebar force.",
            values={"gross_force_N": gross_force, "net_force_N": net_force},
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Rebar net force outside compression block",
            status=PASS if outside_force == gross_force else FAIL,
            message="Outside-block ordinary rebar force remains As*fs."
            if outside_force == gross_force
            else "Outside-block ordinary rebar force changed unexpectedly.",
            values={"outside_force_N": outside_force, "gross_force_N": gross_force},
        )
    )

    base_df = pmm_result_to_display_dataframe(base_result)
    no_displacement_df = pmm_result_to_display_dataframe(no_displacement_result)
    enabled_max_pn = float(base_df["Pn_N"].max())
    disabled_max_pn = float(no_displacement_df["Pn_N"].max())
    displacement_changes_result = any(
        enabled.Pn_N != no_subtract.Pn_N
        for enabled, no_subtract in zip(base_result.points, no_displacement_result.points)
        if enabled.rebar_inside_compression_count > 0
    )
    checks.append(
        PMMVerificationCheck(
            name="PMM changes with rebar displacement subtraction",
            status=PASS if displacement_changes_result else FAIL,
            message="PMM result changes in compression-dominant states when subtraction is enabled."
            if displacement_changes_result
            else "PMM result did not change when displaced concrete subtraction was toggled.",
            values={"enabled_max_Pn_N": enabled_max_pn, "disabled_max_Pn_N": disabled_max_pn},
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Subtraction does not increase pure compression capacity",
            status=PASS if enabled_max_pn <= disabled_max_pn else FAIL,
            message="Enabled displaced concrete subtraction does not increase max nominal compression."
            if enabled_max_pn <= disabled_max_pn
            else "Enabled displaced concrete subtraction increased max nominal compression.",
            values={"enabled_max_Pn_N": enabled_max_pn, "disabled_max_Pn_N": disabled_max_pn},
        )
    )

    checks.append(_positive_negative_balance(base_result, "phiMnx_Nmm"))
    checks.append(_positive_negative_balance(base_result, "phiMny_Nmm"))

    rc_df = pmm_result_to_display_dataframe(rc_matching_result)
    pt_df = pmm_result_to_display_dataframe(pt_result)
    delta_phiPn = abs(float(pt_df["phiPn_kN"].max()) - float(rc_df["phiPn_kN"].max()))
    delta_mnx = abs(float(pt_df["phiMnx_kNm"].abs().max()) - float(rc_df["phiMnx_kNm"].abs().max()))
    delta_mny = abs(float(pt_df["phiMny_kNm"].abs().max()) - float(rc_df["phiMny_kNm"].abs().max()))
    prestress_changed = max(delta_phiPn, delta_mnx, delta_mny) > 1.0e-6
    checks.append(
        PMMVerificationCheck(
            name="Bonded PT Bar changes PMM result",
            status=PASS if prestress_changed else FAIL,
            message="RC + bonded PT Bar envelope differs from RC-only benchmark."
            if prestress_changed
            else "Bonded PT Bar produced near-zero envelope change.",
            values={"delta_max_phiPn_kN": delta_phiPn, "delta_max_abs_phiMnx_kNm": delta_mnx, "delta_max_abs_phiMny_kNm": delta_mny},
        )
    )

    max_ps_force = float(pt_df["prestress_force_N"].abs().max())
    checks.append(
        PMMVerificationCheck(
            name="Bonded PT Bar force included",
            status=PASS if max_ps_force > 0.0 else FAIL,
            message="Bonded PT Bar produces nonzero prestress force in at least some PMM points."
            if max_ps_force > 0.0
            else "Bonded PT Bar did not produce nonzero prestress force.",
            values={"max_abs_prestress_force_N": max_ps_force},
        )
    )

    unbonded_df = pmm_result_to_display_dataframe(unbonded_result)
    unbonded_warning = any("Unbonded prestress is not included" in warning for warning in unbonded_result.warnings)
    ignored_count = int(unbonded_df["unbonded_prestress_ignored_count"].max()) if not unbonded_df.empty else 0
    checks.append(
        PMMVerificationCheck(
            name="Unbonded prestress ignored",
            status=PASS if unbonded_warning and ignored_count > 0 and float(unbonded_df["prestress_force_N"].abs().max()) == 0.0 else FAIL,
            message="Unbonded prestress is ignored with warning." if unbonded_warning and ignored_count > 0 else "Unbonded prestress ignore behavior was not detected.",
            values={"ignored_count": ignored_count, "warnings": unbonded_result.warnings},
        )
    )

    interpolated_slice_df = pmm_slice_at_pu_interpolated(base_df, 1000.0)
    envelope = build_slice_envelope(interpolated_slice_df)
    checks.append(
        PMMVerificationCheck(
            name="Interpolated Pu slice available",
            status=PASS if not interpolated_slice_df.empty else FAIL,
            message="Interpolated Pu slice is available for the benchmark result."
            if not interpolated_slice_df.empty
            else "Interpolated Pu slice is empty.",
            values={
                "display_rows": len(base_df),
                "slice_rows": len(interpolated_slice_df),
                "slice_method": interpolated_slice_df.attrs.get("method"),
                "slice_warnings": interpolated_slice_df.attrs.get("warnings", []),
            },
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Interpolated slice point count",
            status=PASS if len(interpolated_slice_df) >= 8 else FAIL,
            message="Interpolated slice has a reasonable number of directional points."
            if len(interpolated_slice_df) >= 8
            else "Interpolated slice has too few directional points.",
            values={"slice_rows": len(interpolated_slice_df)},
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Interpolated slice method used",
            status=PASS if interpolated_slice_df.attrs.get("method") == "interpolated" else WARNING,
            message="Normal benchmark uses interpolated PMM slice."
            if interpolated_slice_df.attrs.get("method") == "interpolated"
            else "Normal benchmark fell back to tolerance slice.",
            values={"slice_method": interpolated_slice_df.attrs.get("method")},
        )
    )

    demand_case = base_input.load_cases[0]
    directional_estimate = estimate_directional_capacity_from_slice(
        interpolated_slice_df,
        demand_case.Mux_Nmm / 1_000_000.0,
        demand_case.Muy_Nmm / 1_000_000.0,
    )
    finite_directional_capacity = directional_estimate.get("capacity_phiMn_kNm") is not None and directional_estimate["capacity_phiMn_kNm"] > 0
    checks.append(
        PMMVerificationCheck(
            name="Directional capacity from interpolated slice",
            status=PASS if finite_directional_capacity else FAIL,
            message="Directional capacity from interpolated slice is finite for the benchmark demand."
            if finite_directional_capacity
            else "Directional capacity from interpolated slice could not be estimated.",
            values=directional_estimate,
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Refined D/C finite and nonnegative",
            status=PASS if directional_estimate.get("dcr") is not None and directional_estimate["dcr"] >= 0.0 else FAIL,
            message="Refined D/C from interpolated slice is finite and nonnegative."
            if directional_estimate.get("dcr") is not None and directional_estimate["dcr"] >= 0.0
            else "Refined D/C from interpolated slice is unavailable.",
            values={"dcr": directional_estimate.get("dcr")},
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Slice envelope available",
            status=PASS if envelope.is_valid and envelope.point_count_output >= 8 else FAIL,
            message="Slice envelope is valid and has enough points."
            if envelope.is_valid and envelope.point_count_output >= 8
            else "Slice envelope is invalid or sparse.",
            values={
                "method": envelope.method,
                "point_count_output": envelope.point_count_output,
                "warnings": envelope.warnings,
                "used_convex_hull": envelope.used_convex_hull,
            },
        )
    )
    finite_radii = not envelope.envelope_df.empty and envelope.envelope_df["radius_kNm"].map(lambda value: math.isfinite(float(value))).all()
    checks.append(
        PMMVerificationCheck(
            name="Slice envelope finite radii",
            status=PASS if finite_radii else FAIL,
            message="Slice envelope radii are finite." if finite_radii else "Slice envelope includes non-finite radii.",
            values={"point_count_output": envelope.point_count_output},
        )
    )
    envelope_estimate = estimate_directional_capacity_from_envelope(
        envelope,
        demand_case.Mux_Nmm / 1_000_000.0,
        demand_case.Muy_Nmm / 1_000_000.0,
    )
    checks.append(
        PMMVerificationCheck(
            name="Directional capacity from slice envelope",
            status=PASS if envelope_estimate.get("capacity_phiMn_kNm") is not None and envelope_estimate["capacity_phiMn_kNm"] > 0 else FAIL,
            message="Directional capacity from slice envelope is finite for the benchmark demand."
            if envelope_estimate.get("capacity_phiMn_kNm") is not None and envelope_estimate["capacity_phiMn_kNm"] > 0
            else "Directional capacity from slice envelope could not be estimated.",
            values=envelope_estimate,
        )
    )
    checks.append(
        PMMVerificationCheck(
            name="Envelope D/C finite and nonnegative",
            status=PASS if envelope_estimate.get("dcr") is not None and envelope_estimate["dcr"] >= 0.0 else FAIL,
            message="Envelope D/C is finite and nonnegative."
            if envelope_estimate.get("dcr") is not None and envelope_estimate["dcr"] >= 0.0
            else "Envelope D/C is unavailable.",
            values={"dcr": envelope_estimate.get("dcr")},
        )
    )
    noisy_slice = interpolated_slice_df.head(6).copy()
    hull_result = build_convex_hull_envelope(noisy_slice)
    checks.append(
        PMMVerificationCheck(
            name="Convex hull fallback check",
            status=PASS if hull_result.used_convex_hull and hull_result.warnings else FAIL,
            message="Convex hull fallback reports its warning."
            if hull_result.used_convex_hull and hull_result.warnings
            else "Convex hull fallback did not report as expected.",
            values={"used_convex_hull": hull_result.used_convex_hull, "warnings": hull_result.warnings},
        )
    )

    return _summary(checks)


def run_independent_hand_check_suite():
    """Run independent hand checks via the dedicated hand-check module."""

    from concrete_pmm_pro.verification.hand_checks import run_independent_hand_check_suite as _run

    return _run()
