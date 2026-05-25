from __future__ import annotations

import math

import pytest

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import (
    PMMPoint,
    PMMSolverResult,
    active_load_cases_to_display_dataframe,
    pmm_result_to_display_dataframe,
    summarize_pmm_result,
)
from concrete_pmm_pro.code_checks import aci_phi_from_tensile_strain
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle


def _sample_analysis_input(with_prestress: bool = False) -> AnalysisInput:
    prestress_elements = []
    if with_prestress:
        prestress_elements.append(PrestressElement(x_mm=0, y_mm=-150, area_mm2=140, steel_type="strand", pe_eff_n=100_000))
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(name="C35", fc_MPa=35, ecu=0.003, beta1=0.80),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200000)],
        rebars=[
            Rebar(x_mm=-150, y_mm=-250, diameter_mm=25, material_name="SD40", label="B1"),
            Rebar(x_mm=150, y_mm=-250, diameter_mm=25, material_name="SD40", label="B2"),
            Rebar(x_mm=150, y_mm=250, diameter_mm=25, material_name="SD40", label="B3"),
            Rebar(x_mm=-150, y_mm=250, diameter_mm=25, material_name="SD40", label="B4"),
        ],
        prestress_elements=prestress_elements,
        load_cases=[LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="ULS")],
        settings=AnalysisSettings(neutral_axis_angle_steps=12, neutral_axis_depth_steps=10),
    )


def test_aci_phi_compression_controlled_tied_is_about_065() -> None:
    assert aci_phi_from_tensile_strain(0.0, transverse_reinforcement="tied") == pytest.approx(0.65)


def test_aci_phi_tension_controlled_is_about_090() -> None:
    assert aci_phi_from_tensile_strain(0.006) == pytest.approx(0.90)


def test_aci_phi_transition_is_between_limits() -> None:
    phi = aci_phi_from_tensile_strain(0.003)

    assert 0.65 < phi < 0.90


def test_run_rc_pmm_solver_produces_non_empty_result_for_rectangle_with_rebars() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    assert result.points


def test_pmm_result_point_count_equals_angle_steps_times_depth_steps() -> None:
    analysis_input = _sample_analysis_input()
    result = run_rc_pmm_solver(analysis_input)

    assert len(result.points) == analysis_input.settings.neutral_axis_angle_steps * analysis_input.settings.neutral_axis_depth_steps


def test_result_dataframe_contains_required_columns() -> None:
    df = run_rc_pmm_solver(_sample_analysis_input()).to_dataframe()

    assert {"Pn_N", "Mnx_Nmm", "Mny_Nmm", "phi", "phiPn_N", "phiPn_capped_N", "phiMnx_Nmm", "phiMny_Nmm"}.issubset(df.columns)


def test_some_points_have_positive_axial_compression_capacity() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    assert any(point.Pn_N > 0 for point in result.points)


def test_symmetric_rectangle_result_numbers_are_finite() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    for point in result.points:
        assert math.isfinite(point.Pn_N)
        assert math.isfinite(point.Mnx_Nmm)
        assert math.isfinite(point.Mny_Nmm)
        assert math.isfinite(point.phi)


def test_solver_warns_if_prestress_is_present_but_ignored() -> None:
    analysis_input = _sample_analysis_input(with_prestress=True)
    analysis_input.settings.include_prestress = False
    result = run_rc_pmm_solver(analysis_input)

    assert any("Prestress elements are present but excluded by analysis settings" in warning for warning in result.warnings)


def test_solver_uses_analysis_input_without_session_state() -> None:
    analysis_input = _sample_analysis_input()
    result = run_rc_pmm_solver(analysis_input)

    assert result.info


def test_concrete_compression_area_is_nonnegative() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    assert all(point.concrete_area_mm2 >= 0 for point in result.points)


def test_phi_values_are_between_tied_limits() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    assert all(0.65 <= point.phi <= 0.90 for point in result.points)


def test_app_import_still_works() -> None:
    import app

    assert hasattr(app, "main")


def test_pmm_display_dataframe_contains_display_unit_columns() -> None:
    df = pmm_result_to_display_dataframe(run_rc_pmm_solver(_sample_analysis_input()))

    assert {"phiPn_kN", "phiPn_capped_kN", "phiMnx_kNm", "phiMny_kNm"}.issubset(df.columns)


def test_pmm_display_dataframe_unit_conversions_are_correct() -> None:
    result = PMMSolverResult(
        points=[
            PMMPoint(
                theta_rad=0,
                c_mm=1,
                Pn_N=1000,
                Mnx_Nmm=1_000_000,
                Mny_Nmm=-1_000_000,
                phi=0.65,
                phiPn_N=1000,
                phiPn_capped_N=900,
                phiMnx_Nmm=1_000_000,
                phiMny_Nmm=-1_000_000,
                eps_t=None,
                strain_condition="compression-controlled",
                concrete_area_mm2=1,
                concrete_force_N=1000,
            )
        ]
    )

    df = pmm_result_to_display_dataframe(result)

    assert df.loc[0, "Pn_kN"] == pytest.approx(1.0)
    assert df.loc[0, "Mnx_kNm"] == pytest.approx(1.0)
    assert df.loc[0, "phiPn_kN"] == pytest.approx(1.0)
    assert df.loc[0, "phiPn_capped_kN"] == pytest.approx(0.9)
    assert df.loc[0, "phiMnx_kNm"] == pytest.approx(1.0)


def test_solver_adds_capped_phipn_values() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())

    assert all(point.phiPn_capped_N is not None for point in result.points)
    assert max(point.phiPn_capped_N for point in result.points if point.phiPn_capped_N is not None) <= max(
        point.phiPn_N for point in result.points
    )


def test_spiral_transverse_reinforcement_can_increase_compression_phi() -> None:
    analysis_input = _sample_analysis_input()
    analysis_input.settings = AnalysisSettings(
        neutral_axis_angle_steps=12,
        neutral_axis_depth_steps=10,
        transverse_reinforcement="spiral",
    )
    result = run_rc_pmm_solver(analysis_input)

    assert any(point.phi == pytest.approx(0.75) for point in result.points)


def test_summarize_pmm_result_returns_point_count() -> None:
    result = run_rc_pmm_solver(_sample_analysis_input())
    summary = summarize_pmm_result(result)

    assert summary["point_count"] == len(result.points)


def test_summarize_pmm_result_detects_no_nan_or_inf_for_sample_result() -> None:
    summary = summarize_pmm_result(run_rc_pmm_solver(_sample_analysis_input()))

    assert summary["has_nan"] is False
    assert summary["has_inf"] is False


def test_summarize_pmm_result_phi_range_is_expected() -> None:
    summary = summarize_pmm_result(run_rc_pmm_solver(_sample_analysis_input()))

    assert 0.65 <= summary["phi_min"] <= 0.90
    assert 0.65 <= summary["phi_max"] <= 0.90


def test_active_uls_demand_display_dataframe_converts_units() -> None:
    load_cases = [
        LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=500_000_000, Muy_Nmm=300_000_000, load_type="ULS"),
        LoadCase(name="SLS-01", Pu_N=1, Mux_Nmm=1, Muy_Nmm=1, load_type="SLS"),
    ]

    df = active_load_cases_to_display_dataframe(load_cases, "ULS")

    assert len(df) == 1
    assert df.loc[0, "Pu_kN"] == pytest.approx(1000.0)
    assert df.loc[0, "Mux_kNm"] == pytest.approx(500.0)
    assert df.loc[0, "Muy_kNm"] == pytest.approx(300.0)


def test_analysis_page_imports_without_error() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
