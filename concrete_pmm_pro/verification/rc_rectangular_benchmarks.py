"""Rectangular RC PMM validation benchmark pack.

This module is the first validation pack after the framework milestone.  It is
kept independent from the Streamlit UI and deliberately uses transparent hand
formulas for simple rectangular RC sections.  The goal is not to certify every
PMM point; it is to create stable benchmark evidence before prototype warnings
are reduced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe
from concrete_pmm_pro.analysis.strain_compatibility import rebar_net_force_n
from concrete_pmm_pro.code_checks import aci_beta1
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Point2D, Rebar, RebarMaterial, SectionGeometry

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class RCBenchmarkCheck:
    """Single rectangular RC validation check."""

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
class RCBenchmarkSummary:
    """Summary for the VALID.RC1 benchmark pack."""

    checks: list[RCBenchmarkCheck]
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


def _summary(checks: list[RCBenchmarkCheck]) -> RCBenchmarkSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall = FAIL if fail_count else WARNING if warning_count else PASS
    return RCBenchmarkSummary(checks, pass_count, warning_count, fail_count, overall)


def _percent_difference(reference: float, solver: float) -> float:
    return abs(solver - reference) / max(abs(reference), 1.0) * 100.0


def _status_from_difference(percent_difference: float, tolerance_percent: float, fail_percent: float = 25.0) -> str:
    if not math.isfinite(percent_difference):
        return FAIL
    if percent_difference <= tolerance_percent:
        return PASS
    if percent_difference <= fail_percent:
        return WARNING
    return FAIL


def rectangular_geometry(width_mm: float = 400.0, height_mm: float = 600.0) -> SectionGeometry:
    half_b = width_mm / 2.0
    half_h = height_mm / 2.0
    return SectionGeometry(
        name="VALID.RC1 rectangular benchmark",
        outer_polygon=[
            Point2D(x=-half_b, y=-half_h),
            Point2D(x=half_b, y=-half_h),
            Point2D(x=half_b, y=half_h),
            Point2D(x=-half_b, y=half_h),
        ],
        metadata={"validation_case": "VALID.RC1", "width_mm": width_mm, "height_mm": height_mm},
    )


def rectangular_rc_rebars(diameter_mm: float = 25.0, cover_to_bar_center_mm: float = 50.0) -> list[Rebar]:
    x = 125.0
    y = 300.0 - cover_to_bar_center_mm
    return [
        Rebar(x_mm=-x, y_mm=y, diameter_mm=diameter_mm, material_name="Grade420", label="T1"),
        Rebar(x_mm=x, y_mm=y, diameter_mm=diameter_mm, material_name="Grade420", label="T2"),
        Rebar(x_mm=-x, y_mm=-y, diameter_mm=diameter_mm, material_name="Grade420", label="B1"),
        Rebar(x_mm=x, y_mm=-y, diameter_mm=diameter_mm, material_name="Grade420", label="B2"),
    ]


def build_valid_rc1_rectangular_input(
    fc_MPa: float = 40.0,
    fy_MPa: float = 420.0,
    width_mm: float = 400.0,
    height_mm: float = 600.0,
    rebar_diameter_mm: float = 25.0,
) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangular_geometry(width_mm, height_mm),
        concrete_material=ConcreteMaterial(name=f"VALID.RC1 C{fc_MPa:g}", fc_MPa=fc_MPa, ecu=0.003),
        rebar_materials=[RebarMaterial(name="Grade420", fy_MPa=fy_MPa, Es_MPa=200000.0)],
        rebars=rectangular_rc_rebars(rebar_diameter_mm),
        load_cases=[LoadCase(name="ULS-VALID-RC1", Pu_N=500_000.0, Mux_Nmm=120_000_000.0, Muy_Nmm=0.0, load_type="ULS")],
        settings=AnalysisSettings(
            include_rebars=True,
            include_prestress=False,
            use_phi_factor=True,
            transverse_reinforcement="tied",
            subtract_rebar_displaced_concrete=True,
            neutral_axis_angle_steps=24,
            neutral_axis_depth_steps=61,
        ),
    )


def reference_rc_po_N(fc_MPa: float, width_mm: float, height_mm: float, rebars: list[Rebar], fy_MPa: float) -> float:
    Ag = width_mm * height_mm
    Ast = sum(bar.area_mm2 for bar in rebars)
    return 0.85 * fc_MPa * (Ag - Ast) + fy_MPa * Ast


def reference_tied_phiPn_max_N(Po_N: float) -> float:
    return 0.80 * 0.65 * Po_N


def reference_uniaxial_mx_point(
    *,
    c_mm: float,
    width_mm: float = 400.0,
    height_mm: float = 600.0,
    fc_MPa: float = 40.0,
    fy_MPa: float = 420.0,
    Es_MPa: float = 200000.0,
    ecu: float = 0.003,
    rebars: list[Rebar] | None = None,
) -> dict[str, Any]:
    """Return independent rectangular stress-block Pn/Mnx for NA parallel to x.

    Compression is at the top fiber.  Positive compression force follows the
    solver convention.  Mnx is sum(F*y) about the gross centroid.
    """

    bars = rebars if rebars is not None else rectangular_rc_rebars()
    beta1 = aci_beta1(fc_MPa)
    a_mm = min(beta1 * c_mm, height_mm)
    y_top = height_mm / 2.0
    y_block_bottom = y_top - a_mm
    concrete_force = 0.85 * fc_MPa * width_mm * a_mm
    concrete_y = y_top - a_mm / 2.0
    Pn = concrete_force
    Mnx = concrete_force * concrete_y
    rebar_details: list[dict[str, Any]] = []

    for bar in bars:
        distance_from_top = y_top - bar.y_mm
        eps_s = ecu * (1.0 - distance_from_top / c_mm)
        fs = max(-fy_MPa, min(fy_MPa, Es_MPa * eps_s))
        inside_block = bar.y_mm >= y_block_bottom
        force, metadata = rebar_net_force_n(bar.area_mm2, fs, fc_MPa, inside_block, subtract_displaced_concrete=True)
        Pn += force
        Mnx += force * bar.y_mm
        rebar_details.append(
            {
                "label": bar.label,
                "y_mm": bar.y_mm,
                "eps_s": eps_s,
                "fs_MPa": fs,
                "inside_block": inside_block,
                "force_N": force,
                "metadata": metadata,
            }
        )

    return {"Pn_N": Pn, "Mnx_Nmm": Mnx, "beta1": beta1, "a_mm": a_mm, "rebar_details": rebar_details}


def _rectangle_vertices(width_mm: float, height_mm: float) -> list[tuple[float, float]]:
    half_b = width_mm / 2.0
    half_h = height_mm / 2.0
    return [(-half_b, -half_h), (half_b, -half_h), (half_b, half_h), (-half_b, half_h)]


def _project_s(x_mm: float, y_mm: float, nx: float, ny: float) -> float:
    return x_mm * nx + y_mm * ny


def _clip_polygon_by_compression_half_plane(
    vertices: list[tuple[float, float]],
    *,
    nx: float,
    ny: float,
    boundary_s: float,
    tolerance: float = 1.0e-9,
) -> list[tuple[float, float]]:
    """Clip polygon by the compression side of a neutral-axis half-plane.

    The reference implementation stays intentionally independent from the PMM
    solver's Shapely clipping path so a biaxial benchmark is not solver-output
    checking itself.
    """

    if not vertices:
        return []

    def is_inside(point: tuple[float, float]) -> bool:
        return _project_s(point[0], point[1], nx, ny) >= boundary_s - tolerance

    def intersection(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
        start_s = _project_s(start[0], start[1], nx, ny)
        end_s = _project_s(end[0], end[1], nx, ny)
        denominator = start_s - end_s
        if abs(denominator) <= tolerance:
            return end
        t = (start_s - boundary_s) / denominator
        return (start[0] + t * (end[0] - start[0]), start[1] + t * (end[1] - start[1]))

    clipped: list[tuple[float, float]] = []
    previous = vertices[-1]
    previous_inside = is_inside(previous)
    for current in vertices:
        current_inside = is_inside(current)
        if current_inside:
            if not previous_inside:
                clipped.append(intersection(previous, current))
            clipped.append(current)
        elif previous_inside:
            clipped.append(intersection(previous, current))
        previous = current
        previous_inside = current_inside
    return clipped


def _polygon_area_centroid(vertices: list[tuple[float, float]]) -> tuple[float, float, float]:
    if len(vertices) < 3:
        return 0.0, 0.0, 0.0

    twice_area = 0.0
    cx_sum = 0.0
    cy_sum = 0.0
    for index, (x0, y0) in enumerate(vertices):
        x1, y1 = vertices[(index + 1) % len(vertices)]
        cross = x0 * y1 - x1 * y0
        twice_area += cross
        cx_sum += (x0 + x1) * cross
        cy_sum += (y0 + y1) * cross

    signed_area = 0.5 * twice_area
    if abs(signed_area) <= 1.0e-9:
        return 0.0, 0.0, 0.0
    return abs(signed_area), cx_sum / (6.0 * signed_area), cy_sum / (6.0 * signed_area)


def reference_biaxial_pmm_point(
    *,
    theta_rad: float,
    c_mm: float,
    width_mm: float = 400.0,
    height_mm: float = 600.0,
    fc_MPa: float = 40.0,
    fy_MPa: float = 420.0,
    Es_MPa: float = 200000.0,
    ecu: float = 0.003,
    rebars: list[Rebar] | None = None,
) -> dict[str, Any]:
    """Return independent biaxial rectangular stress-block Pn/Mnx/Mny."""

    if c_mm <= 0.0:
        raise ValueError("c_mm must be positive.")
    bars = rebars if rebars is not None else rectangular_rc_rebars()
    beta1 = aci_beta1(fc_MPa)
    nx = math.cos(theta_rad)
    ny = math.sin(theta_rad)
    vertices = _rectangle_vertices(width_mm, height_mm)
    projections = [_project_s(x, y, nx, ny) for x, y in vertices]
    min_s = min(projections)
    max_s = max(projections)
    projected_depth = max_s - min_s
    block_depth = min(beta1 * c_mm, projected_depth)
    boundary_s = max_s - block_depth
    compression_vertices = _clip_polygon_by_compression_half_plane(vertices, nx=nx, ny=ny, boundary_s=boundary_s)
    concrete_area, concrete_x, concrete_y = _polygon_area_centroid(compression_vertices)
    concrete_force = 0.85 * fc_MPa * concrete_area

    Pn = concrete_force
    Mnx = concrete_force * concrete_y
    Mny = concrete_force * concrete_x
    rebar_details: list[dict[str, Any]] = []

    for bar in bars:
        bar_s = _project_s(bar.x_mm, bar.y_mm, nx, ny)
        distance_from_extreme = max_s - bar_s
        eps_s = ecu * (1.0 - distance_from_extreme / c_mm)
        fs = max(-fy_MPa, min(fy_MPa, Es_MPa * eps_s))
        inside_block = bar_s >= boundary_s - 1.0e-9
        concrete_stress_subtracted = 0.85 * fc_MPa if inside_block else 0.0
        net_stress = fs - concrete_stress_subtracted
        force = bar.area_mm2 * net_stress
        Pn += force
        Mnx += force * bar.y_mm
        Mny += force * bar.x_mm
        rebar_details.append(
            {
                "label": bar.label,
                "x_mm": bar.x_mm,
                "y_mm": bar.y_mm,
                "bar_s_mm": bar_s,
                "eps_s": eps_s,
                "fs_MPa": fs,
                "inside_block": inside_block,
                "force_N": force,
            }
        )

    return {
        "Pn_N": Pn,
        "Mnx_Nmm": Mnx,
        "Mny_Nmm": Mny,
        "beta1": beta1,
        "block_depth_mm": block_depth,
        "boundary_s_mm": boundary_s,
        "projected_depth_mm": projected_depth,
        "concrete_area_mm2": concrete_area,
        "concrete_centroid_x_mm": concrete_x,
        "concrete_centroid_y_mm": concrete_y,
        "compression_vertex_count": len(compression_vertices),
        "rebar_details": rebar_details,
    }


def _nearest_solver_point_for_mx(result, target_c_mm: float):
    target_theta = math.pi / 2.0
    return min(
        result.points,
        key=lambda point: (
            abs((point.theta_rad - target_theta + math.pi) % (2.0 * math.pi) - math.pi),
            abs(point.c_mm - target_c_mm),
        ),
    )


def _nearest_solver_point_for_biaxial(result, target_theta_rad: float, target_c_mm: float):
    return min(
        result.points,
        key=lambda point: (
            abs((point.theta_rad - target_theta_rad + math.pi) % (2.0 * math.pi) - math.pi),
            abs(point.c_mm - target_c_mm),
        ),
    )


def run_valid_rc1_benchmark_pack() -> RCBenchmarkSummary:
    """Run the VALID.RC1 rectangular RC benchmark pack."""

    analysis_input = build_valid_rc1_rectangular_input()
    result = run_rc_pmm_solver(analysis_input)
    df = pmm_result_to_display_dataframe(result)
    checks: list[RCBenchmarkCheck] = []

    if df.empty or not result.points:
        return _summary(
            [
                RCBenchmarkCheck(
                    check_id="VALID.RC1.EMPTY",
                    title="PMM result is non-empty",
                    status=FAIL,
                    reference_value=None,
                    solver_value=None,
                    percent_difference=None,
                    tolerance_percent=None,
                    message="Solver returned no PMM points for the benchmark section.",
                )
            ]
        )

    fc = analysis_input.concrete_material.fc_MPa
    fy = analysis_input.rebar_materials[0].fy_MPa
    width = 400.0
    height = 600.0
    reference_po = reference_rc_po_N(fc, width, height, analysis_input.rebars, fy)
    reference_phi_pn = reference_tied_phiPn_max_N(reference_po)
    solver_phi_pn = float(df["phiPn_capped_N"].max())
    phi_diff = _percent_difference(reference_phi_pn, solver_phi_pn)
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.PHI_PN_MAX",
            title="Tied-column max phiPn cap",
            status=_status_from_difference(phi_diff, 10.0, 20.0),
            reference_value=reference_phi_pn,
            solver_value=solver_phi_pn,
            percent_difference=phi_diff,
            tolerance_percent=10.0,
            message="Solver capped axial capacity agrees with independent ACI-style phiPn cap within tolerance.",
            details={"reference_Po_N": reference_po, "solver_point_count": len(result.points)},
        )
    )

    reference_point = reference_uniaxial_mx_point(c_mm=300.0, fc_MPa=fc, fy_MPa=fy, rebars=analysis_input.rebars)
    nearest = _nearest_solver_point_for_mx(result, 300.0)
    p_diff = _percent_difference(reference_point["Pn_N"], nearest.Pn_N)
    m_diff = _percent_difference(reference_point["Mnx_Nmm"], nearest.Mnx_Nmm)
    c_gap = abs(nearest.c_mm - 300.0)
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.MX_C300_PN",
            title="Uniaxial Mx spot check at c approx. 300 mm — Pn",
            status=_status_from_difference(p_diff, 12.0, 25.0),
            reference_value=reference_point["Pn_N"],
            solver_value=nearest.Pn_N,
            percent_difference=p_diff,
            tolerance_percent=12.0,
            message="Solver Pn at the nearest neutral-axis point agrees with independent rectangular-block hand calculation.",
            details={"nearest_c_mm": nearest.c_mm, "c_gap_mm": c_gap, "nearest_theta_rad": nearest.theta_rad},
        )
    )
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.MX_C300_MNX",
            title="Uniaxial Mx spot check at c approx. 300 mm — Mnx",
            status=_status_from_difference(m_diff, 15.0, 30.0),
            reference_value=reference_point["Mnx_Nmm"],
            solver_value=nearest.Mnx_Nmm,
            percent_difference=m_diff,
            tolerance_percent=15.0,
            message="Solver Mnx at the nearest neutral-axis point agrees with independent rectangular-block hand calculation within prototype tolerance.",
            details={"nearest_c_mm": nearest.c_mm, "c_gap_mm": c_gap, "nearest_theta_rad": nearest.theta_rad},
        )
    )

    biaxial_nearest = _nearest_solver_point_for_biaxial(result, math.pi / 4.0, 300.0)
    biaxial_reference = reference_biaxial_pmm_point(
        theta_rad=biaxial_nearest.theta_rad,
        c_mm=biaxial_nearest.c_mm,
        fc_MPa=fc,
        fy_MPa=fy,
        rebars=analysis_input.rebars,
    )
    biaxial_p_diff = _percent_difference(biaxial_reference["Pn_N"], biaxial_nearest.Pn_N)
    biaxial_mnx_diff = _percent_difference(biaxial_reference["Mnx_Nmm"], biaxial_nearest.Mnx_Nmm)
    biaxial_mny_diff = _percent_difference(biaxial_reference["Mny_Nmm"], biaxial_nearest.Mny_Nmm)
    biaxial_details = {
        "nearest_c_mm": biaxial_nearest.c_mm,
        "nearest_theta_rad": biaxial_nearest.theta_rad,
        "target_theta_rad": math.pi / 4.0,
        "target_c_mm": 300.0,
        "reference_concrete_area_mm2": biaxial_reference["concrete_area_mm2"],
        "reference_block_depth_mm": biaxial_reference["block_depth_mm"],
        "compression_vertex_count": biaxial_reference["compression_vertex_count"],
    }
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.BIAX_CDIAG_PN",
            title="Biaxial diagonal neutral-axis spot check - Pn",
            status=_status_from_difference(biaxial_p_diff, 5.0, 15.0),
            reference_value=biaxial_reference["Pn_N"],
            solver_value=biaxial_nearest.Pn_N,
            percent_difference=biaxial_p_diff,
            tolerance_percent=5.0,
            message="Solver Pn at a diagonal neutral-axis point agrees with an independent rectangular clipping reference.",
            details=biaxial_details,
        )
    )
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.BIAX_CDIAG_MNX",
            title="Biaxial diagonal neutral-axis spot check - Mnx",
            status=_status_from_difference(biaxial_mnx_diff, 5.0, 15.0),
            reference_value=biaxial_reference["Mnx_Nmm"],
            solver_value=biaxial_nearest.Mnx_Nmm,
            percent_difference=biaxial_mnx_diff,
            tolerance_percent=5.0,
            message="Solver Mnx at a diagonal neutral-axis point agrees with an independent rectangular clipping reference.",
            details=biaxial_details,
        )
    )
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.BIAX_CDIAG_MNY",
            title="Biaxial diagonal neutral-axis spot check - Mny",
            status=_status_from_difference(biaxial_mny_diff, 5.0, 15.0),
            reference_value=biaxial_reference["Mny_Nmm"],
            solver_value=biaxial_nearest.Mny_Nmm,
            percent_difference=biaxial_mny_diff,
            tolerance_percent=5.0,
            message="Solver Mny at a diagonal neutral-axis point agrees with an independent rectangular clipping reference.",
            details=biaxial_details,
        )
    )

    positive_mnx = float(df["phiMnx_Nmm"].max())
    negative_mnx = abs(float(df["phiMnx_Nmm"].min()))
    mnx_balance = abs(positive_mnx - negative_mnx) / max(positive_mnx, negative_mnx, 1.0)
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.MX_SYMMETRY",
            title="Positive/negative Mx symmetry sanity",
            status=PASS if mnx_balance <= 0.20 else WARNING,
            reference_value=positive_mnx,
            solver_value=negative_mnx,
            percent_difference=mnx_balance * 100.0,
            tolerance_percent=20.0,
            message="Symmetric rectangular RC section has reasonably balanced positive and negative Mx capacity envelope.",
            details={"positive_phiMnx_Nmm": positive_mnx, "negative_phiMnx_abs_Nmm": negative_mnx},
        )
    )

    capacity_columns = ["Pn_N", "Mnx_Nmm", "Mny_Nmm", "phiPn_N", "phiMnx_Nmm", "phiMny_Nmm", "phiPn_capped_N"]
    invalid_columns = [column for column in capacity_columns if df[column].isna().any() or not df[column].map(math.isfinite).all()]
    checks.append(
        RCBenchmarkCheck(
            check_id="VALID.RC1.NUMERIC_SCHEMA",
            title="Capacity-critical PMM columns are finite",
            status=PASS if not invalid_columns else FAIL,
            reference_value=0.0,
            solver_value=float(len(invalid_columns)),
            percent_difference=0.0 if not invalid_columns else 100.0,
            tolerance_percent=0.0,
            message="Capacity-critical PMM columns contain no NaN/Inf values." if not invalid_columns else "Capacity-critical PMM columns contain invalid values.",
            details={"invalid_columns": invalid_columns, "checked_columns": capacity_columns},
        )
    )

    return _summary(checks)
