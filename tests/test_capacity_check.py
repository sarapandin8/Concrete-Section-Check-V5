from __future__ import annotations

import pytest

from concrete_pmm_pro.analysis.capacity_check import (
    FAIL,
    OUT_OF_RANGE,
    PASS,
    check_uls_demands_against_rc_pmm,
    estimate_directional_capacity,
)
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.core.models import LoadCase


def _point(P: float, Mx: float, My: float = 0.0, capped_P: float | None = None) -> PMMPoint:
    return PMMPoint(
        theta_rad=0.0,
        c_mm=100.0,
        Pn_N=P,
        Mnx_Nmm=Mx,
        Mny_Nmm=My,
        phi=0.65,
        phiPn_N=P,
        phiPn_capped_N=capped_P,
        phiMnx_Nmm=Mx,
        phiMny_Nmm=My,
        eps_t=None,
        strain_condition="compression-controlled",
        concrete_area_mm2=1.0,
        concrete_force_N=P,
    )


def _synthetic_result() -> PMMSolverResult:
    return PMMSolverResult(
        points=[
            _point(0.0, 100.0),
            _point(1_000.0, 200.0),
            _point(2_000.0, 300.0),
            _point(3_000.0, 400.0),
        ]
    )


def _capped_axial_result() -> PMMSolverResult:
    return PMMSolverResult(
        points=[
            _point(0.0, 100.0, capped_P=0.0),
            _point(1_000.0, 100.0, capped_P=900.0),
            _point(2_000.0, 100.0, capped_P=1_200.0),
            _point(3_000.0, 100.0, capped_P=1_500.0),
        ]
    )


def test_estimate_directional_capacity_returns_capacity_for_synthetic_result() -> None:
    estimate = estimate_directional_capacity(_synthetic_result(), Pu_N=1_500.0, Mux_Nmm=100.0, Muy_Nmm=0.0)

    assert estimate["interpolation_status"] == PASS
    assert estimate["capacity_phiMn_Nmm"] == pytest.approx(250.0)


def test_estimate_directional_capacity_returns_out_of_range_when_pu_is_outside_range() -> None:
    estimate = estimate_directional_capacity(_synthetic_result(), Pu_N=5_000.0, Mux_Nmm=100.0, Muy_Nmm=0.0)

    assert estimate["interpolation_status"] == OUT_OF_RANGE
    assert estimate["capacity_phiMn_Nmm"] is None


def test_check_uls_demands_against_rc_pmm_handles_passing_load_case() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-PASS", Pu_N=1_500.0, Mux_Nmm=125.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].status == PASS
    assert summary.max_dcr == pytest.approx(0.5)


def test_check_uls_demands_against_rc_pmm_handles_failing_load_case() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-FAIL", Pu_N=1_500.0, Mux_Nmm=500.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].status == FAIL
    assert summary.max_dcr == pytest.approx(2.0)


def test_check_uls_demands_against_rc_pmm_ignores_sls_load_cases() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [
            LoadCase(name="SLS-01", Pu_N=1_500.0, Mux_Nmm=500.0, Muy_Nmm=0.0, load_type="SLS"),
            LoadCase(name="ULS-01", Pu_N=1_500.0, Mux_Nmm=125.0, Muy_Nmm=0.0, load_type="ULS"),
        ],
    )

    assert len(summary.results) == 1
    assert summary.results[0].combo_name == "ULS-01"


def test_axial_only_demand_below_max_phipn_passes() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-AXIAL", Pu_N=1_500.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].status == PASS
    assert summary.results[0].dcr == pytest.approx(0.5)


def test_axial_only_demand_above_max_phipn_fails() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-AXIAL", Pu_N=4_000.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].status == FAIL
    assert summary.results[0].dcr == pytest.approx(4_000.0 / 3_000.0)


def test_axial_only_demand_uses_capped_capacity_when_available() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _capped_axial_result(),
        [LoadCase(name="ULS-AXIAL", Pu_N=1_800.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].status == FAIL
    assert summary.results[0].capacity_phiPn_N == pytest.approx(1_500.0)
    assert summary.results[0].dcr == pytest.approx(1_800.0 / 1_500.0)
    assert "capped maximum phiPn" in summary.results[0].message


def test_directional_dcr_is_mu_divided_by_capacity_phimn() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [LoadCase(name="ULS-DCR", Pu_N=1_500.0, Mux_Nmm=125.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert summary.results[0].capacity_phiMn_Nmm == pytest.approx(250.0)
    assert summary.results[0].dcr == pytest.approx(125.0 / 250.0)


def test_demand_capacity_summary_identifies_governing_combo() -> None:
    summary = check_uls_demands_against_rc_pmm(
        _synthetic_result(),
        [
            LoadCase(name="ULS-LOW", Pu_N=1_500.0, Mux_Nmm=50.0, Muy_Nmm=0.0, load_type="ULS"),
            LoadCase(name="ULS-HIGH", Pu_N=1_500.0, Mux_Nmm=200.0, Muy_Nmm=0.0, load_type="ULS"),
        ],
    )

    assert summary.governing_combo == "ULS-HIGH"
    assert summary.max_dcr == pytest.approx(0.8)


def test_analysis_page_imports_without_error_for_demand_capacity_ui() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
