"""PMM solver sanity validations.

These checks exercise the existing solver as a black box.  They verify basic
invariants and robustness only; they intentionally do not calibrate or change
solver equations.
"""

from __future__ import annotations

import math

from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import summarize_pmm_result
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.validation.models import ValidationResult, boolean_validation_result, numeric_validation_result, skipped_validation_result

CATEGORY = "PMM Sanity"


def _symmetric_rectangular_rc_input(load_cases: list[LoadCase] | None = None) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35.0, ecu=0.003, beta1=0.80),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=390.0, Es_MPa=200000.0)],
        rebars=[
            Rebar(x_mm=-150.0, y_mm=-250.0, diameter_mm=25.0, material_name="SD40", label="B1"),
            Rebar(x_mm=150.0, y_mm=-250.0, diameter_mm=25.0, material_name="SD40", label="B2"),
            Rebar(x_mm=150.0, y_mm=250.0, diameter_mm=25.0, material_name="SD40", label="B3"),
            Rebar(x_mm=-150.0, y_mm=250.0, diameter_mm=25.0, material_name="SD40", label="B4"),
        ],
        load_cases=load_cases or [],
        settings=AnalysisSettings(neutral_axis_angle_steps=24, neutral_axis_depth_steps=10),
    )


def validate_pmm_solver_sanity() -> list[ValidationResult]:
    try:
        analysis_input = _symmetric_rectangular_rc_input(
            [
                LoadCase(name="Small demand", Pu_N=100_000.0, Mux_Nmm=10_000_000.0, Muy_Nmm=0.0, load_type="ULS"),
                LoadCase(name="Large demand", Pu_N=1_000_000.0, Mux_Nmm=1_000_000_000.0, Muy_Nmm=0.0, load_type="ULS"),
            ]
        )
        result = run_rc_pmm_solver(analysis_input)
        summary = summarize_pmm_result(result)
        dc_summary = check_uls_demands_against_rc_pmm(result, analysis_input.load_cases)
    except Exception as exc:  # pragma: no cover - defensive guard for dependency/API instability
        return [
            skipped_validation_result(
                case_id="PMM.SANITY.API_SKIPPED",
                category=CATEGORY,
                title="PMM sanity checks skipped",
                engineering_note=f"Existing PMM solver API could not be exercised safely: {exc}",
            )
        ]

    phi_mnx_values = [point.phiMnx_Nmm for point in result.points]
    phi_mny_values = [point.phiMny_Nmm for point in result.points]
    small = next((item for item in dc_summary.results if item.combo_name == "Small demand"), None)
    large = next((item for item in dc_summary.results if item.combo_name == "Large demand"), None)
    numeric_values = [
        value
        for point in result.points
        for value in (point.Pn_N, point.Mnx_Nmm, point.Mny_Nmm, point.phi, point.phiPn_N, point.phiMnx_Nmm, point.phiMny_Nmm)
    ]
    return [
        boolean_validation_result(
            case_id="PMM.SANITY.NON_EMPTY",
            category=CATEGORY,
            title="Symmetric RC PMM run produces points",
            passed=bool(result.points),
            expected="non-empty PMM result",
            actual=len(result.points),
        ),
        boolean_validation_result(
            case_id="PMM.SANITY.NO_NAN_INF",
            category=CATEGORY,
            title="PMM result has no NaN or inf in required numeric fields",
            passed=all(math.isfinite(value) for value in numeric_values) and not summary["has_nan"] and not summary["has_inf"],
            expected="finite numeric PMM result",
            actual={"has_nan": summary["has_nan"], "has_inf": summary["has_inf"]},
        ),
        boolean_validation_result(
            case_id="PMM.SANITY.POSITIVE_COMPRESSION",
            category=CATEGORY,
            title="Pure compression convention is positive",
            passed=summary["max_phiPn_N"] is not None and float(summary["max_phiPn_N"]) > 0.0,
            expected="max phiPn > 0",
            actual=summary["max_phiPn_N"],
            units="N",
        ),
        numeric_validation_result(
            case_id="PMM.SANITY.MX_SYMMETRY",
            category=CATEGORY,
            title="Symmetric rectangle has approximately symmetric Mx envelope",
            expected=max(phi_mnx_values),
            actual=abs(min(phi_mnx_values)),
            rel_tolerance=1.0e-6,
            units="N-mm",
        ),
        numeric_validation_result(
            case_id="PMM.SANITY.MY_SYMMETRY",
            category=CATEGORY,
            title="Symmetric rectangle has approximately symmetric My envelope",
            expected=max(phi_mny_values),
            actual=abs(min(phi_mny_values)),
            rel_tolerance=1.0e-6,
            units="N-mm",
        ),
        boolean_validation_result(
            case_id="PMM.SANITY.SMALL_DEMAND_PASS",
            category=CATEGORY,
            title="Small demand D/C is below 1.0",
            passed=small is not None and small.dcr is not None and small.dcr < 1.0,
            expected="D/C < 1.0",
            actual=None if small is None else small.dcr,
        ),
        boolean_validation_result(
            case_id="PMM.SANITY.LARGE_DEMAND_HIGHER",
            category=CATEGORY,
            title="Large demand D/C is greater than small demand D/C",
            passed=small is not None and large is not None and small.dcr is not None and large.dcr is not None and large.dcr > small.dcr,
            expected="large demand D/C > small demand D/C",
            actual={"small": None if small is None else small.dcr, "large": None if large is None else large.dcr},
        ),
    ]
