from __future__ import annotations

import math

import pytest

from concrete_pmm_pro.analysis.prestress_stress import PRESTRESS_COMPRESSION_REVERSAL_WARNING
from concrete_pmm_pro.core.models import Rebar, RebarMaterial
from concrete_pmm_pro.verification.hand_checks import (
    FAIL,
    HandCheckSummary,
    check_axial_compression_hand,
    check_prestress_strain_spot,
    check_prestress_stress_spot,
    check_rebar_displaced_concrete_spot,
    check_symmetry_spot,
    check_uniaxial_rc_spot,
    hand_check_summary_to_dataframe,
    hand_phiPn_max_rc,
    hand_po_rc,
    hand_rectangular_uniaxial_section_point,
    run_independent_hand_check_suite,
)
from concrete_pmm_pro.verification.pmm_benchmarks import run_independent_hand_check_suite as benchmark_hand_suite


def test_hand_po_rc_computes_expected_simple_section() -> None:
    rebars = [Rebar(x_mm=0.0, y_mm=0.0, diameter_mm=20.0, material_name="Grade420")]
    material = RebarMaterial(name="Grade420", fy_MPa=420.0)
    ast = rebars[0].area_mm2

    po = hand_po_rc(fc_MPa=35.0, Ag_mm2=100_000.0, rebars=rebars, rebar_material_default=material)

    assert po == pytest.approx(0.85 * 35.0 * (100_000.0 - ast) + 420.0 * ast)


def test_hand_phipn_max_tied() -> None:
    assert hand_phiPn_max_rc(1_000_000.0, "tied") == pytest.approx(0.80 * 0.65 * 1_000_000.0)


def test_hand_phipn_max_spiral() -> None:
    assert hand_phiPn_max_rc(1_000_000.0, "spiral") == pytest.approx(0.85 * 0.75 * 1_000_000.0)


def test_rebar_displaced_concrete_hand_spot_check_passes() -> None:
    result = check_rebar_displaced_concrete_spot()

    assert result.status == "PASS"
    assert result.calculated_value == pytest.approx(366_000.0)
    assert result.details["expected_outside_N"] == pytest.approx(400_000.0)


def test_prestress_strain_hand_spot_check_passes() -> None:
    result = check_prestress_strain_spot()

    assert result.status == "PASS"
    assert result.details["compression_case_total"] == pytest.approx(0.004)
    assert result.details["tension_case_total"] == pytest.approx(0.006)


def test_prestress_compression_reversal_hand_check_warns_and_clamps() -> None:
    result = check_prestress_strain_spot()

    assert result.details["raw_reversal_total"] == pytest.approx(-0.0005)
    assert result.details["reversal_stress"] == pytest.approx(0.0)
    assert PRESTRESS_COMPRESSION_REVERSAL_WARNING in result.details["warnings"]


def test_prestress_stress_linear_cap_spot_check_passes() -> None:
    result = check_prestress_stress_spot()

    assert result.status == "PASS"
    assert result.details["linear_stress_MPa"] == pytest.approx(800.0)
    assert result.details["capped_stress_MPa"] == pytest.approx(1180.0)


def test_prestress_stress_bilinear_spot_check_passes() -> None:
    result = check_prestress_stress_spot()
    expected = 930.0 + 0.02 * 200000.0 * (0.006 - 930.0 / 200000.0)

    assert result.status == "PASS"
    assert result.details["bilinear_stress_MPa"] == pytest.approx(expected)


def test_hand_rectangular_uniaxial_section_point_returns_values() -> None:
    point = hand_rectangular_uniaxial_section_point()

    assert point["Pn_N"] != 0.0
    assert math.isfinite(point["Mnx_Nmm"])
    assert point["a_mm"] > 0.0


def test_hand_check_summary_to_dataframe_contains_required_columns() -> None:
    summary = run_independent_hand_check_suite()
    df = hand_check_summary_to_dataframe(summary)

    assert {
        "Check",
        "Status",
        "Calculated Value",
        "Solver Value",
        "Percent Difference",
        "Tolerance Percent",
        "Message",
    }.issubset(df.columns)


def test_independent_hand_check_suite_returns_summary() -> None:
    summary = run_independent_hand_check_suite()

    assert isinstance(summary, HandCheckSummary)
    assert summary.checks


def test_independent_hand_check_suite_has_no_fail_for_normal_benchmarks() -> None:
    summary = run_independent_hand_check_suite()

    assert summary.overall_status != FAIL
    assert summary.fail_count == 0


def test_pmm_benchmark_wrapper_exposes_independent_hand_check_suite() -> None:
    summary = benchmark_hand_suite()

    assert isinstance(summary, HandCheckSummary)


def test_axial_compression_hand_check_returns_pass_or_warning() -> None:
    result = check_axial_compression_hand()

    assert result.status in {"PASS", "WARNING"}
    assert result.calculated_value is not None
    assert result.solver_value is not None
    assert result.percent_difference is not None


def test_uniaxial_rc_spot_check_returns_pass_or_warning() -> None:
    result = check_uniaxial_rc_spot()

    assert result.status in {"PASS", "WARNING"}
    assert result.details


def test_symmetry_spot_checks_return_pass_or_warning() -> None:
    results = check_symmetry_spot()

    assert results
    assert all(result.status in {"PASS", "WARNING"} for result in results)


def test_analysis_page_imports_with_independent_hand_checks() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
