"""SLS stress sign and serviceability judgement benchmark checks.

These checks are deterministic engineering-review benchmarks for the current
elastic SLS implementation. They do not replace independent validation or
code-certified software.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    StressCheckPoint,
    classify_service_stress_results_for_cracking,
    compute_gross_section_properties,
    elastic_concrete_stress_section_basis,
    elastic_prestress_stress_section_basis,
    run_elastic_sls_stress_check,
    summarize_effective_prestress_for_sls,
    validate_stress_check_points_against_geometry,
)

PASS = "PASS"
WARNING = "WARNING"
FAIL = "FAIL"


@dataclass(frozen=True)
class SLSBenchmarkCheck:
    name: str
    status: str
    calculated_value: float | None = None
    expected_value: float | None = None
    percent_difference: float | None = None
    tolerance_percent: float | None = None
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SLSBenchmarkSummary:
    checks: list[SLSBenchmarkCheck] = field(default_factory=list)
    pass_count: int = 0
    warning_count: int = 0
    fail_count: int = 0
    overall_status: str = PASS
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _summary(checks: list[SLSBenchmarkCheck]) -> SLSBenchmarkSummary:
    pass_count = sum(check.status == PASS for check in checks)
    warning_count = sum(check.status == WARNING for check in checks)
    fail_count = sum(check.status == FAIL for check in checks)
    overall_status = FAIL if fail_count else WARNING if warning_count else PASS
    return SLSBenchmarkSummary(
        checks=checks,
        pass_count=pass_count,
        warning_count=warning_count,
        fail_count=fail_count,
        overall_status=overall_status,
        warnings=[
            "SLS verification checks are simplified benchmark and sign checks for engineering review.",
        ],
        info=[f"Ran {len(checks)} SLS benchmark check(s)."],
    )


def _percent_difference(expected: float, calculated: float) -> float:
    denominator = max(abs(expected), 1.0)
    return abs(calculated - expected) / denominator * 100.0


def _status_from_difference(percent_difference: float, tolerance_percent: float) -> str:
    if not math.isfinite(percent_difference):
        return FAIL
    return PASS if percent_difference <= tolerance_percent else FAIL


def _base_input(load_cases: list[LoadCase], rebars: list[Rebar] | None = None, prestress_elements: list[PrestressElement] | None = None) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="SLS Benchmark C40", fc_MPa=40.0),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=390.0, Es_MPa=200000.0)],
        rebars=rebars or [],
        prestress_elements=prestress_elements or [],
        load_cases=load_cases,
    )


def build_rectangular_sls_gross_case() -> tuple[AnalysisInput, ServiceabilitySettings]:
    """Return a deterministic rectangular gross SLS benchmark case."""

    load_cases = [
        LoadCase(name="SLS-AXIAL-COMP", Pu_N=1_000_000.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="SLS"),
        LoadCase(name="SLS-MX", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS"),
        LoadCase(name="SLS-MY", Pu_N=0.0, Mux_Nmm=0.0, Muy_Nmm=100_000_000.0, load_type="SLS"),
    ]
    settings = ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0)
    return _base_input(load_cases), settings


def _prestress_element(x_mm: float, y_mm: float, label: str) -> PrestressElement:
    return PrestressElement(
        x_mm=x_mm,
        y_mm=y_mm,
        area_mm2=100.0,
        pe_eff_n=500_000.0,
        bonded=True,
        label=label,
        fpu_mpa=1030.0,
        fpy_mpa=835.0,
        ep_mpa=195000.0,
        steel_type="prestressing_bar",
    )


def build_rectangular_sls_with_top_prestress_case() -> tuple[AnalysisInput, ServiceabilitySettings]:
    settings = ServiceabilitySettings(enabled=True, include_prestress_effective_force=True, concrete_tension_limit_MPa=10.0)
    analysis_input = _base_input(
        [LoadCase(name="SLS-PS-TOP", Pu_N=0.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="SLS")],
        prestress_elements=[_prestress_element(0.0, 200.0, "TOP")],
    )
    return analysis_input, settings


def build_rectangular_sls_with_bottom_prestress_case() -> tuple[AnalysisInput, ServiceabilitySettings]:
    settings = ServiceabilitySettings(enabled=True, include_prestress_effective_force=True, concrete_tension_limit_MPa=10.0)
    analysis_input = _base_input(
        [LoadCase(name="SLS-PS-BOTTOM", Pu_N=0.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="SLS")],
        prestress_elements=[_prestress_element(0.0, -200.0, "BOTTOM")],
    )
    return analysis_input, settings


def build_rectangular_sls_with_transformed_rebar_case() -> tuple[AnalysisInput, ServiceabilitySettings]:
    rebars = [
        Rebar(x_mm=-125.0, y_mm=250.0, diameter_mm=32.0, material_name="SD40", label="T1"),
        Rebar(x_mm=125.0, y_mm=250.0, diameter_mm=32.0, material_name="SD40", label="T2"),
        Rebar(x_mm=-125.0, y_mm=-250.0, diameter_mm=32.0, material_name="SD40", label="B1"),
        Rebar(x_mm=125.0, y_mm=-250.0, diameter_mm=32.0, material_name="SD40", label="B2"),
    ]
    settings = ServiceabilitySettings(
        enabled=True,
        use_transformed_section=True,
        concrete_Ec_MPa=30000.0,
        concrete_tension_limit_MPa=10.0,
    )
    analysis_input = _base_input([LoadCase(name="SLS-MX", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")], rebars=rebars)
    return analysis_input, settings


def build_rectangular_sls_no_tension_case() -> tuple[AnalysisInput, ServiceabilitySettings]:
    settings = ServiceabilitySettings(enabled=True, no_tension_check=True)
    analysis_input = _base_input([LoadCase(name="SLS-NO-TENSION", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")])
    return analysis_input, settings


def _stress_by_combo_and_point(summary, combo_name: str, point_name: str):
    return next(result for result in summary.stress_results if result.combo_name == combo_name and result.point_name == point_name)


def _gross_axial_compression_check() -> SLSBenchmarkCheck:
    analysis_input, settings = build_rectangular_sls_gross_case()
    props = compute_gross_section_properties(analysis_input.section_geometry)
    summary = run_elastic_sls_stress_check(analysis_input, settings)
    expected = -1_000_000.0 / props.area_mm2
    results = [result for result in summary.stress_results if result.combo_name == "SLS-AXIAL-COMP"]
    calculated = [result.stress_MPa for result in results]
    max_diff = max(abs(float(value) - expected) for value in calculated)
    pdiff = _percent_difference(expected, expected + max_diff)
    ok = all(value is not None and value < 0.0 for value in calculated) and max_diff <= 1.0e-9
    return SLSBenchmarkCheck(
        name="Axial compression sign and uniform stress",
        status=PASS if ok else FAIL,
        calculated_value=calculated[0] if calculated else None,
        expected_value=expected,
        percent_difference=pdiff,
        tolerance_percent=0.01,
        message="Axial compression creates uniform negative stress." if ok else "Axial compression sign or uniformity check failed.",
        details={"stresses_MPa": calculated, "area_mm2": props.area_mm2},
    )


def _mux_bending_sign_check() -> SLSBenchmarkCheck:
    analysis_input, settings = build_rectangular_sls_gross_case()
    props = compute_gross_section_properties(analysis_input.section_geometry)
    summary = run_elastic_sls_stress_check(analysis_input, settings)
    top = _stress_by_combo_and_point(summary, "SLS-MX", "Top fiber").stress_MPa
    bottom = _stress_by_combo_and_point(summary, "SLS-MX", "Bottom fiber").stress_MPa
    expected_top = 100_000_000.0 * (props.y_max_mm - props.centroid_y_mm) / props.Ix_mm4
    expected_bottom = 100_000_000.0 * (props.y_min_mm - props.centroid_y_mm) / props.Ix_mm4
    pdiff = max(_percent_difference(expected_top, float(top)), _percent_difference(expected_bottom, float(bottom)))
    ok = top is not None and bottom is not None and top > 0.0 and bottom < 0.0 and pdiff <= 0.01
    return SLSBenchmarkCheck(
        name="Mux bending top/bottom sign",
        status=PASS if ok else FAIL,
        calculated_value=float(top),
        expected_value=expected_top,
        percent_difference=pdiff,
        tolerance_percent=0.01,
        message="Mux bending signs and hand values match the SLS convention." if ok else "Mux bending sign or hand value mismatch.",
        details={"top_MPa": top, "bottom_MPa": bottom, "expected_top_MPa": expected_top, "expected_bottom_MPa": expected_bottom},
    )


def _muy_bending_sign_check() -> SLSBenchmarkCheck:
    analysis_input, settings = build_rectangular_sls_gross_case()
    props = compute_gross_section_properties(analysis_input.section_geometry)
    summary = run_elastic_sls_stress_check(analysis_input, settings)
    right = _stress_by_combo_and_point(summary, "SLS-MY", "Right fiber").stress_MPa
    left = _stress_by_combo_and_point(summary, "SLS-MY", "Left fiber").stress_MPa
    expected_right = 100_000_000.0 * (props.x_max_mm - props.centroid_x_mm) / props.Iy_mm4
    expected_left = 100_000_000.0 * (props.x_min_mm - props.centroid_x_mm) / props.Iy_mm4
    pdiff = max(_percent_difference(expected_right, float(right)), _percent_difference(expected_left, float(left)))
    ok = right is not None and left is not None and right > 0.0 and left < 0.0 and pdiff <= 0.01
    return SLSBenchmarkCheck(
        name="Muy bending left/right sign",
        status=PASS if ok else FAIL,
        calculated_value=float(right),
        expected_value=expected_right,
        percent_difference=pdiff,
        tolerance_percent=0.01,
        message="Muy bending signs and hand values match the SLS convention." if ok else "Muy bending sign or hand value mismatch.",
        details={"right_MPa": right, "left_MPa": left, "expected_right_MPa": expected_right, "expected_left_MPa": expected_left},
    )


def _prestress_stress_for(x_ps: float, y_ps: float, x_point: float, y_point: float) -> float:
    props = compute_gross_section_properties(rectangle(width_mm=400.0, height_mm=600.0))
    contribution = summarize_effective_prestress_for_sls(
        [_prestress_element(x_ps, y_ps, "PS")],
        centroid_x_mm=props.centroid_x_mm,
        centroid_y_mm=props.centroid_y_mm,
        Ix_mm4=props.Ix_mm4,
        Iy_mm4=props.Iy_mm4,
        Ixy_mm4=props.Ixy_mm4,
    )
    return elastic_prestress_stress_section_basis(
        x_point,
        y_point,
        props.area_mm2,
        props.centroid_x_mm,
        props.centroid_y_mm,
        props.Ix_mm4,
        props.Iy_mm4,
        contribution,
    )


def _prestress_sign_checks() -> list[SLSBenchmarkCheck]:
    props = compute_gross_section_properties(rectangle(width_mm=400.0, height_mm=600.0))
    expected_concentric = -500_000.0 / props.area_mm2
    points = [
        (props.centroid_x_mm, props.centroid_y_mm),
        (props.centroid_x_mm, props.y_max_mm),
        (props.centroid_x_mm, props.y_min_mm),
        (props.x_max_mm, props.centroid_y_mm),
        (props.x_min_mm, props.centroid_y_mm),
    ]
    concentric = [_prestress_stress_for(0.0, 0.0, x, y) for x, y in points]
    concentric_ok = all(abs(value - expected_concentric) <= 1.0e-9 for value in concentric)

    top = _prestress_stress_for(0.0, 200.0, props.centroid_x_mm, props.y_max_mm)
    top_bottom = _prestress_stress_for(0.0, 200.0, props.centroid_x_mm, props.y_min_mm)
    bottom = _prestress_stress_for(0.0, -200.0, props.centroid_x_mm, props.y_min_mm)
    bottom_top = _prestress_stress_for(0.0, -200.0, props.centroid_x_mm, props.y_max_mm)
    right = _prestress_stress_for(120.0, 0.0, props.x_max_mm, props.centroid_y_mm)
    right_left = _prestress_stress_for(120.0, 0.0, props.x_min_mm, props.centroid_y_mm)
    left = _prestress_stress_for(-120.0, 0.0, props.x_min_mm, props.centroid_y_mm)
    left_right = _prestress_stress_for(-120.0, 0.0, props.x_max_mm, props.centroid_y_mm)

    return [
        SLSBenchmarkCheck(
            name="Concentric prestress uniform compression",
            status=PASS if concentric_ok else FAIL,
            calculated_value=concentric[0],
            expected_value=expected_concentric,
            percent_difference=_percent_difference(expected_concentric, concentric[0]),
            tolerance_percent=0.01,
            message="Concentric effective prestress creates uniform negative stress." if concentric_ok else "Concentric prestress is not uniform compression.",
            details={"stresses_MPa": concentric},
        ),
        SLSBenchmarkCheck(
            name="Top tendon increases top compression",
            status=PASS if top < top_bottom else FAIL,
            calculated_value=top,
            expected_value=top_bottom,
            message="Top tendon makes top fiber more compressive than bottom." if top < top_bottom else "Top tendon sign check failed.",
            details={"top_MPa": top, "bottom_MPa": top_bottom},
        ),
        SLSBenchmarkCheck(
            name="Bottom tendon increases bottom compression",
            status=PASS if bottom < bottom_top else FAIL,
            calculated_value=bottom,
            expected_value=bottom_top,
            message="Bottom tendon makes bottom fiber more compressive than top." if bottom < bottom_top else "Bottom tendon sign check failed.",
            details={"bottom_MPa": bottom, "top_MPa": bottom_top},
        ),
        SLSBenchmarkCheck(
            name="Right tendon increases right compression",
            status=PASS if right < right_left else FAIL,
            calculated_value=right,
            expected_value=right_left,
            message="Right tendon makes right fiber more compressive than left." if right < right_left else "Right tendon sign check failed.",
            details={"right_MPa": right, "left_MPa": right_left},
        ),
        SLSBenchmarkCheck(
            name="Left tendon increases left compression",
            status=PASS if left < left_right else FAIL,
            calculated_value=left,
            expected_value=left_right,
            message="Left tendon makes left fiber more compressive than right." if left < left_right else "Left tendon sign check failed.",
            details={"left_MPa": left, "right_MPa": left_right},
        ),
    ]


def _transformed_checks() -> list[SLSBenchmarkCheck]:
    gross_input, gross_settings = build_rectangular_sls_gross_case()
    concrete_only_settings = ServiceabilitySettings(
        enabled=True,
        use_transformed_section=True,
        concrete_Ec_MPa=30000.0,
        transformed_include_rebar=False,
        transformed_include_prestress=False,
        concrete_tension_limit_MPa=10.0,
    )
    gross_summary = run_elastic_sls_stress_check(gross_input, gross_settings)
    concrete_only_summary = run_elastic_sls_stress_check(gross_input, concrete_only_settings)
    gross_top = _stress_by_combo_and_point(gross_summary, "SLS-MX", "Top fiber").stress_MPa
    transformed_top = _stress_by_combo_and_point(concrete_only_summary, "SLS-MX", "Top fiber").stress_MPa
    concrete_only_ok = concrete_only_summary.section_basis_used == "transformed_uncracked" and abs(float(gross_top) - float(transformed_top)) <= 1.0e-9

    transformed_input, transformed_settings = build_rectangular_sls_with_transformed_rebar_case()
    transformed_summary = run_elastic_sls_stress_check(transformed_input, transformed_settings)
    gross_for_transformed_summary = run_elastic_sls_stress_check(transformed_input, ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0))
    transformed_props = transformed_summary.transformed_section_properties
    gross_props = transformed_summary.section_properties
    transformed_top_rebar = _stress_by_combo_and_point(transformed_summary, "SLS-MX", "Top fiber").external_stress_MPa
    gross_top_rebar = _stress_by_combo_and_point(gross_for_transformed_summary, "SLS-MX", "Top fiber").external_stress_MPa
    symmetric_ok = (
        transformed_props is not None
        and gross_props is not None
        and abs(transformed_props.centroid_y_mm - gross_props.centroid_y_mm) <= 1.0e-9
        and transformed_props.Ix_mm4 > gross_props.Ix_mm4
        and abs(float(transformed_top_rebar)) < abs(float(gross_top_rebar))
    )

    eccentric_rebar = [Rebar(x_mm=0.0, y_mm=250.0, diameter_mm=40.0, material_name="SD40", label="TOP")]
    eccentric_input = _base_input(
        [LoadCase(name="SLS-MX", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")],
        rebars=eccentric_rebar,
    )
    eccentric_settings = ServiceabilitySettings(enabled=True, use_transformed_section=True, concrete_Ec_MPa=30000.0, concrete_tension_limit_MPa=10.0)
    eccentric_summary = run_elastic_sls_stress_check(eccentric_input, eccentric_settings)
    eccentric_props = eccentric_summary.transformed_section_properties
    top_result = _stress_by_combo_and_point(eccentric_summary, "SLS-MX", "Top fiber")
    manual_top = None
    if eccentric_props is not None:
        manual_top = elastic_concrete_stress_section_basis(
            0.0,
            100_000_000.0,
            0.0,
            top_result.x_mm,
            top_result.y_mm,
            eccentric_props.area_mm2,
            eccentric_props.centroid_x_mm,
            eccentric_props.centroid_y_mm,
            eccentric_props.Ix_mm4,
            eccentric_props.Iy_mm4,
            eccentric_props.Ixy_mm4,
        )
    eccentric_ok = (
        eccentric_props is not None
        and manual_top is not None
        and eccentric_props.centroid_y_mm > compute_gross_section_properties(eccentric_input.section_geometry).centroid_y_mm
        and top_result.section_basis == "transformed_uncracked"
        and abs(float(top_result.external_stress_MPa) - manual_top) <= 1.0e-9
    )

    return [
        SLSBenchmarkCheck(
            name="Concrete-only transformed equals gross stress",
            status=PASS if concrete_only_ok else FAIL,
            calculated_value=float(transformed_top),
            expected_value=float(gross_top),
            percent_difference=_percent_difference(float(gross_top), float(transformed_top)),
            tolerance_percent=0.01,
            message="Concrete-only transformed section matches gross stress." if concrete_only_ok else "Concrete-only transformed stress differs from gross.",
            details={"section_basis": concrete_only_summary.section_basis_used},
        ),
        SLSBenchmarkCheck(
            name="Symmetric transformed rebar reduces bending stress",
            status=PASS if symmetric_ok else FAIL,
            calculated_value=float(transformed_top_rebar),
            expected_value=float(gross_top_rebar),
            message="Symmetric rebar increases transformed inertia and reduces bending stress magnitude."
            if symmetric_ok
            else "Symmetric transformed rebar benchmark failed.",
            details={
                "gross_Ix_mm4": None if gross_props is None else gross_props.Ix_mm4,
                "transformed_Ix_mm4": None if transformed_props is None else transformed_props.Ix_mm4,
                "gross_top_MPa": gross_top_rebar,
                "transformed_top_MPa": transformed_top_rebar,
            },
        ),
        SLSBenchmarkCheck(
            name="Eccentric transformed rebar centroid and stress basis",
            status=PASS if eccentric_ok else FAIL,
            calculated_value=float(top_result.external_stress_MPa),
            expected_value=manual_top,
            percent_difference=None if manual_top is None else _percent_difference(manual_top, float(top_result.external_stress_MPa)),
            tolerance_percent=0.01,
            message="Eccentric transformed rebar shifts centroid and stress uses transformed basis."
            if eccentric_ok
            else "Eccentric transformed rebar benchmark failed.",
            details={"centroid_y_mm": None if eccentric_props is None else eccentric_props.centroid_y_mm, "section_basis": top_result.section_basis},
        ),
    ]


def _judgement_checks() -> list[SLSBenchmarkCheck]:
    no_tension_input, no_tension_settings = build_rectangular_sls_no_tension_case()
    no_tension_summary = run_elastic_sls_stress_check(no_tension_input, no_tension_settings)
    no_tension_ok = no_tension_summary.overall_status == FAIL and no_tension_summary.no_tension_violation_count > 0

    decompression_summary = run_elastic_sls_stress_check(
        no_tension_input,
        ServiceabilitySettings(enabled=True, decompression_check=True),
    )
    decompression_ok = decompression_summary.overall_status == FAIL and decompression_summary.decompression_violation_count > 0

    allowable_pass = run_elastic_sls_stress_check(
        no_tension_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=5.0),
    )
    allowable_fail = run_elastic_sls_stress_check(
        no_tension_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=1.0),
    )

    governing_input = _base_input(
        [
            LoadCase(name="SLS-LOW", Pu_N=0.0, Mux_Nmm=10_000_000.0, Muy_Nmm=0.0, load_type="SLS"),
            LoadCase(name="SLS-HIGH", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS"),
        ]
    )
    governing_summary = run_elastic_sls_stress_check(
        governing_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0),
    )
    governing_ok = (
        governing_summary.governing_combo == "SLS-HIGH"
        and governing_summary.governing_point is not None
        and governing_summary.max_utilization is not None
        and math.isfinite(governing_summary.max_utilization)
    )

    severe_summary = run_elastic_sls_stress_check(governing_input, ServiceabilitySettings(enabled=True, no_tension_check=True))
    severe_ok = severe_summary.overall_status == FAIL and severe_summary.governing_combo is not None and severe_summary.governing_point is not None

    return [
        SLSBenchmarkCheck(
            name="No-tension benchmark fails under tensile stress",
            status=PASS if no_tension_ok else FAIL,
            message="No-tension check detects tensile stress." if no_tension_ok else "No-tension benchmark did not fail as expected.",
            details={"overall_status": no_tension_summary.overall_status, "violations": no_tension_summary.no_tension_violation_count},
        ),
        SLSBenchmarkCheck(
            name="Decompression benchmark fails under tensile stress",
            status=PASS if decompression_ok else FAIL,
            message="Decompression check detects tensile stress." if decompression_ok else "Decompression benchmark did not fail as expected.",
            details={"overall_status": decompression_summary.overall_status, "violations": decompression_summary.decompression_violation_count},
        ),
        SLSBenchmarkCheck(
            name="Allowable tension benchmark passes with high limit",
            status=PASS if allowable_pass.overall_status == PASS else FAIL,
            message="Allowable tension check passes when limit exceeds generated tension."
            if allowable_pass.overall_status == PASS
            else "Allowable tension high-limit benchmark failed.",
            details={"overall_status": allowable_pass.overall_status, "max_tension_MPa": allowable_pass.max_tension_MPa},
        ),
        SLSBenchmarkCheck(
            name="Allowable tension benchmark fails with low limit",
            status=PASS if allowable_fail.overall_status == FAIL else FAIL,
            message="Allowable tension check fails when limit is below generated tension."
            if allowable_fail.overall_status == FAIL
            else "Allowable tension low-limit benchmark did not fail.",
            details={"overall_status": allowable_fail.overall_status, "max_tension_MPa": allowable_fail.max_tension_MPa},
        ),
        SLSBenchmarkCheck(
            name="Governing SLS result benchmark",
            status=PASS if governing_ok else FAIL,
            message="Governing combo/point follows highest utilization." if governing_ok else "Governing result benchmark failed.",
            details={
                "governing_combo": governing_summary.governing_combo,
                "governing_point": governing_summary.governing_point,
                "max_utilization": governing_summary.max_utilization,
            },
        ),
        SLSBenchmarkCheck(
            name="Severe no-tension violation has governing result",
            status=PASS if severe_ok else FAIL,
            message="No-tension violations are treated as severe governing candidates."
            if severe_ok
            else "No-tension violation governing result is missing.",
            details={"governing_combo": severe_summary.governing_combo, "governing_point": severe_summary.governing_point},
        ),
    ]


def _crack_classification_checks() -> list[SLSBenchmarkCheck]:
    pure_compression_input = _base_input(
        [LoadCase(name="SLS-COMP", Pu_N=1_000_000.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="SLS")]
    )
    pure_compression_summary = run_elastic_sls_stress_check(
        pure_compression_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0),
    )
    pure_compression_classification = classify_service_stress_results_for_cracking(
        pure_compression_summary,
        pure_compression_summary.settings,
    )
    pure_compression_ok = pure_compression_classification.overall_classification == "UNCRACKED_BY_CHECK_POINTS"

    bending_input = _base_input(
        [LoadCase(name="SLS-MX", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")]
    )
    tension_summary = run_elastic_sls_stress_check(
        bending_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0),
    )
    tension_classification = classify_service_stress_results_for_cracking(tension_summary, tension_summary.settings)
    tension_ok = tension_classification.overall_classification == "TENSION_PRESENT"

    exceed_summary = run_elastic_sls_stress_check(
        bending_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=1.0),
    )
    exceed_classification = classify_service_stress_results_for_cracking(exceed_summary, exceed_summary.settings)
    exceed_ok = exceed_classification.overall_classification == "TENSION_EXCEEDS_LIMIT"

    no_tension_summary = run_elastic_sls_stress_check(
        bending_input,
        ServiceabilitySettings(enabled=True, no_tension_check=True),
    )
    no_tension_classification = classify_service_stress_results_for_cracking(no_tension_summary, no_tension_summary.settings)
    no_tension_ok = no_tension_classification.overall_classification == "NO_TENSION_VIOLATED"

    decompression_summary = run_elastic_sls_stress_check(
        bending_input,
        ServiceabilitySettings(enabled=True, decompression_check=True),
    )
    decompression_classification = classify_service_stress_results_for_cracking(
        decompression_summary,
        decompression_summary.settings,
    )
    decompression_ok = decompression_classification.overall_classification == "DECOMPRESSION_VIOLATED"

    all_points_summary = run_elastic_sls_stress_check(
        bending_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0, critical_point_filter="all"),
    )
    extreme_filter_settings = all_points_summary.settings.model_copy(update={"critical_point_filter": "extreme_fibers_only"})
    extreme_filter_classification = classify_service_stress_results_for_cracking(all_points_summary, extreme_filter_settings)
    extreme_filter_point_names = [point.point_name for point in extreme_filter_classification.points]
    extreme_filter_ok = (
        "Centroid" in extreme_filter_point_names
        and extreme_filter_classification.governing_point != "Centroid"
    )

    return [
        SLSBenchmarkCheck(
            name="Crack classification pure compression uncracked",
            status=PASS if pure_compression_ok else FAIL,
            message="Pure compression is classified as uncracked by selected check points."
            if pure_compression_ok
            else "Pure compression crack classification failed.",
            details={"overall_classification": pure_compression_classification.overall_classification},
        ),
        SLSBenchmarkCheck(
            name="Crack classification detects tension present",
            status=PASS if tension_ok else FAIL,
            message="Bending tension is classified as tension present."
            if tension_ok
            else "Bending tension classification failed.",
            details={"overall_classification": tension_classification.overall_classification},
        ),
        SLSBenchmarkCheck(
            name="Crack classification detects tension limit exceedance",
            status=PASS if exceed_ok else FAIL,
            message="Low allowable tension limit is classified as exceeded."
            if exceed_ok
            else "Tension limit exceedance classification failed.",
            details={"overall_classification": exceed_classification.overall_classification},
        ),
        SLSBenchmarkCheck(
            name="Crack classification detects no-tension violation",
            status=PASS if no_tension_ok else FAIL,
            message="No-tension check classification detects tensile stress."
            if no_tension_ok
            else "No-tension crack classification failed.",
            details={"overall_classification": no_tension_classification.overall_classification},
        ),
        SLSBenchmarkCheck(
            name="Crack classification detects decompression violation",
            status=PASS if decompression_ok else FAIL,
            message="Decompression check classification detects tensile stress."
            if decompression_ok
            else "Decompression crack classification failed.",
            details={"overall_classification": decompression_classification.overall_classification},
        ),
        SLSBenchmarkCheck(
            name="Crack classification honors extreme-fiber filter",
            status=PASS if extreme_filter_ok else FAIL,
            message="Extreme-fiber classification keeps centroid visible but excludes it from governing."
            if extreme_filter_ok
            else "Extreme-fiber crack classification governing filter failed.",
            details={"point_names": extreme_filter_point_names, "governing_point": extreme_filter_classification.governing_point},
        ),
    ]


def _custom_stress_point_checks() -> list[SLSBenchmarkCheck]:
    custom_point = StressCheckPoint(
        name="Tendon-Zone-Benchmark",
        x_mm=0.0,
        y_mm=100.0,
        point_type="tendon_zone",
        source="user",
    )
    analysis_input = _base_input([LoadCase(name="SLS-CUSTOM", Pu_N=0.0, Mux_Nmm=25_000_000.0, Muy_Nmm=0.0, load_type="SLS")])
    custom_summary = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=[custom_point],
    )
    custom_included_ok = any(result.point_name == "Tendon-Zone-Benchmark" for result in custom_summary.stress_results)

    outside_errors, _outside_warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Outside", x_mm=10_000.0, y_mm=0.0)],
        analysis_input.section_geometry,
    )
    outside_ok = any("outside" in error.lower() for error in outside_errors)

    hollow_geometry = rectangular_hollow(width_mm=1000.0, height_mm=800.0, wall_thickness_mm=100.0)
    void_errors, _void_warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Inside Void", x_mm=0.0, y_mm=0.0)],
        hollow_geometry,
    )
    void_ok = any("void" in error.lower() for error in void_errors)

    non_governing_custom = StressCheckPoint(
        name="Non-Governing-Custom",
        x_mm=0.0,
        y_mm=250.0,
        point_type="custom",
        include_in_governing=False,
        source="user",
    )
    non_governing_summary = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=1.0),
        custom_stress_check_points=[non_governing_custom],
        include_default_stress_check_points=False,
    )
    non_governing_ok = (
        non_governing_summary.stress_results
        and non_governing_summary.overall_status == "NOT_CHECKED"
        and non_governing_summary.governing_combo is None
    )

    crack_summary = classify_service_stress_results_for_cracking(custom_summary, custom_summary.settings)
    tendon_zone_ok = any(
        point.point_name == "Tendon-Zone-Benchmark" and point.classification in {"TENSION_WITHIN_LIMIT", "TENSION_EXCEEDS_LIMIT"}
        for point in crack_summary.points
    )

    return [
        SLSBenchmarkCheck(
            name="Custom stress point included in SLS results",
            status=PASS if custom_included_ok else FAIL,
            message="Custom stress check point is included in elastic SLS results."
            if custom_included_ok
            else "Custom stress check point was missing from elastic SLS results.",
            details={"point_names": [result.point_name for result in custom_summary.stress_results]},
        ),
        SLSBenchmarkCheck(
            name="Custom stress point outside section validation",
            status=PASS if outside_ok else FAIL,
            message="Outside custom stress check point is detected by geometry validation."
            if outside_ok
            else "Outside custom stress check point validation failed.",
            details={"errors": outside_errors},
        ),
        SLSBenchmarkCheck(
            name="Custom stress point inside void validation",
            status=PASS if void_ok else FAIL,
            message="Custom stress check point inside a void is detected by geometry validation."
            if void_ok
            else "Void custom stress check point validation failed.",
            details={"errors": void_errors},
        ),
        SLSBenchmarkCheck(
            name="Custom point excluded from governing summary",
            status=PASS if non_governing_ok else FAIL,
            message="include_in_governing=False prevents a custom point from governing."
            if non_governing_ok
            else "Non-governing custom point affected the governing summary.",
            details={"overall_status": non_governing_summary.overall_status, "governing_combo": non_governing_summary.governing_combo},
        ),
        SLSBenchmarkCheck(
            name="Tendon-zone custom point crack classification",
            status=PASS if tendon_zone_ok else FAIL,
            message="Tendon-zone custom point participates in cracking/tension classification."
            if tendon_zone_ok
            else "Tendon-zone custom point was missing from crack classification.",
            details={"classifications": [(point.point_name, point.classification) for point in crack_summary.points]},
        ),
    ]


def run_sls_verification_suite() -> SLSBenchmarkSummary:
    """Run SLS verification and stress sign benchmark checks."""

    checks: list[SLSBenchmarkCheck] = [
        _gross_axial_compression_check(),
        _mux_bending_sign_check(),
        _muy_bending_sign_check(),
    ]
    checks.extend(_prestress_sign_checks())
    checks.extend(_transformed_checks())
    checks.extend(_judgement_checks())
    checks.extend(_crack_classification_checks())
    checks.extend(_custom_stress_point_checks())
    return _summary(checks)


def sls_benchmark_summary_to_dataframe(summary: SLSBenchmarkSummary) -> pd.DataFrame:
    """Return a stable display/export dataframe for SLS benchmark summaries."""

    return pd.DataFrame(
        [
            {
                "Check": check.name,
                "Status": check.status,
                "Calculated Value": check.calculated_value,
                "Expected Value": check.expected_value,
                "Percent Difference": check.percent_difference,
                "Tolerance Percent": check.tolerance_percent,
                "Message": check.message,
            }
            for check in summary.checks
        ]
    )
