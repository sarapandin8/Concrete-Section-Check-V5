from __future__ import annotations

import pytest

from concrete_pmm_pro.analysis.capacity_check import check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.prestress_checks import (
    ERROR,
    IGNORED,
    OK,
    WARNING,
    check_prestress_elements_for_analysis,
    compare_rc_vs_prestress_pmm,
    summarize_prestress_contribution,
)
from concrete_pmm_pro.analysis.result_models import PMMPoint, PMMSolverResult
from concrete_pmm_pro.core.models import LoadCase, PrestressElement


def _prestress(**updates: object) -> PrestressElement:
    data = {
        "x_mm": 0.0,
        "y_mm": -150.0,
        "area_mm2": 140.0,
        "steel_type": "strand",
        "fpu_mpa": 1860.0,
        "fpy_mpa": 1670.0,
        "ep_mpa": 195000.0,
        "pe_eff_n": 100_000.0,
        "initial_stress_mpa": 700.0,
        "initial_strain": None,
        "bonded": True,
        "count": 2,
        "label": "PS1",
    }
    data.update(updates)
    return PrestressElement(**data)


def _invalid_prestress(**updates: object) -> PrestressElement:
    data = _prestress().model_dump()
    data.update(updates)
    return PrestressElement.model_construct(**data)


def _point(P: float, Mx: float, My: float = 0.0, prestress_force: float = 0.0, bonded_count: int = 0) -> PMMPoint:
    return PMMPoint(
        theta_rad=0.0,
        c_mm=100.0,
        Pn_N=P,
        Mnx_Nmm=Mx,
        Mny_Nmm=My,
        phi=0.65,
        phiPn_N=P,
        phiPn_capped_N=P,
        phiMnx_Nmm=Mx,
        phiMny_Nmm=My,
        eps_t=None,
        strain_condition="compression-controlled",
        concrete_area_mm2=1.0,
        concrete_force_N=P,
        prestress_force_N=prestress_force,
        prestress_count=bonded_count,
        bonded_prestress_count=bonded_count,
        unbonded_prestress_ignored_count=0,
    )


def test_prestress_checks_accept_valid_bonded_strand() -> None:
    summary = check_prestress_elements_for_analysis([_prestress()])

    assert summary.ok_count == 1
    assert summary.checks[0].status == OK
    assert summary.bonded_count == 2


def test_prestress_checks_accept_valid_bonded_prestressing_bar() -> None:
    summary = check_prestress_elements_for_analysis(
        [_prestress(steel_type="prestressing_bar", fpy_mpa=1080.0, fpu_mpa=1230.0, label="PT1")]
    )

    assert summary.ok_count == 1
    assert summary.checks[0].steel_type == "prestressing_bar"


def test_prestress_checks_mark_unbonded_as_ignored() -> None:
    summary = check_prestress_elements_for_analysis([_prestress(bonded=False)])

    assert summary.ignored_count == 1
    assert summary.checks[0].status == IGNORED
    assert any("Unbonded prestress is ignored" in message for message in summary.checks[0].messages)


def test_prestress_checks_area_error() -> None:
    summary = check_prestress_elements_for_analysis([_invalid_prestress(area_mm2=0.0)])

    assert summary.error_count == 1
    assert summary.checks[0].status == ERROR
    assert any("area_mm2" in error for error in summary.errors)


def test_prestress_checks_ep_error() -> None:
    summary = check_prestress_elements_for_analysis([_invalid_prestress(ep_mpa=0.0)])

    assert summary.error_count == 1
    assert any("Ep_MPa" in error for error in summary.errors)


def test_prestress_checks_initial_stress_above_fpu_is_error() -> None:
    summary = check_prestress_elements_for_analysis([_invalid_prestress(initial_stress_mpa=1900.0, fpu_mpa=1860.0)])

    assert summary.error_count == 1
    assert any("initial_stress_MPa exceeds fpu_MPa" in error for error in summary.errors)


def test_prestress_checks_high_initial_stress_is_warning() -> None:
    summary = check_prestress_elements_for_analysis([_prestress(initial_stress_mpa=1600.0, fpu_mpa=1860.0)])

    assert summary.warning_count == 1
    assert summary.checks[0].status == WARNING
    assert any("high relative" in warning for warning in summary.warnings)


def test_prestress_checks_fpy_greater_than_fpu_is_error() -> None:
    summary = check_prestress_elements_for_analysis([_invalid_prestress(fpy_mpa=1900.0, fpu_mpa=1860.0)])

    assert summary.error_count == 1
    assert any("fpy_MPa must be less than fpu_MPa" in error for error in summary.errors)


def test_prestress_checks_missing_initial_input_is_warning() -> None:
    summary = check_prestress_elements_for_analysis(
        [_prestress(initial_stress_mpa=None, initial_strain=None, pe_eff_n=0.0)]
    )

    assert summary.warning_count == 1
    assert any("passive high-strength steel" in warning for warning in summary.warnings)


def test_prestress_checks_pe_eff_stress_above_fpu_is_warning() -> None:
    summary = check_prestress_elements_for_analysis([_prestress(pe_eff_n=300_000.0, area_mm2=100.0, fpu_mpa=1860.0)])

    assert summary.warning_count == 1
    assert any("Pe_eff_N produces stress greater than fpu_MPa" in warning for warning in summary.warnings)


def test_prestress_checks_pt_bar_missing_fpy_warns() -> None:
    summary = check_prestress_elements_for_analysis(
        [_prestress(steel_type="prestressing_bar", fpy_mpa=None, fpu_mpa=1230.0, label="PT1")]
    )

    assert summary.warning_count == 1
    assert any("missing fpy_MPa" in warning for warning in summary.warnings)


def test_prestress_checks_fpy_close_to_fpu_warns() -> None:
    summary = check_prestress_elements_for_analysis([_prestress(fpy_mpa=1750.0, fpu_mpa=1860.0)])

    assert summary.warning_count == 1
    assert any("close to fpu_MPa" in warning for warning in summary.warnings)


def test_prestress_checks_initial_stress_above_fpy_warns() -> None:
    summary = check_prestress_elements_for_analysis([_prestress(initial_stress_mpa=900.0, fpy_mpa=835.0, fpu_mpa=1030.0)])

    assert summary.warning_count == 1
    assert any("exceeds fpy_MPa" in warning for warning in summary.warnings)


def test_summarize_prestress_contribution_counts_forces() -> None:
    result = PMMSolverResult(points=[_point(1000.0, 100.0, prestress_force=-250.0, bonded_count=3)])

    summary = summarize_prestress_contribution(result)

    assert summary["bonded_prestress_count"] == 3
    assert summary["max_abs_prestress_force_N"] == pytest.approx(250.0)
    assert summary["max_abs_prestress_force_kN"] == pytest.approx(0.25)
    assert summary["has_prestress_force"] is True


def test_compare_rc_vs_prestress_pmm_reports_nonzero_delta() -> None:
    rc_result = PMMSolverResult(points=[_point(1000.0, 100.0)])
    ps_result = PMMSolverResult(points=[_point(1500.0, 180.0, prestress_force=-200.0, bonded_count=1)])

    comparison = compare_rc_vs_prestress_pmm(rc_result, ps_result)

    assert comparison["delta_max_phiPn_kN"] == pytest.approx(0.5)
    assert comparison["delta_max_abs_phiMnx_kNm"] == pytest.approx(0.00008)


def test_compare_rc_vs_prestress_pmm_warns_when_no_prestress_force() -> None:
    rc_result = PMMSolverResult(points=[_point(1000.0, 100.0)])
    ps_result = PMMSolverResult(points=[_point(1000.0, 100.0, prestress_force=0.0, bonded_count=1)])

    comparison = compare_rc_vs_prestress_pmm(rc_result, ps_result)

    assert any("no measurable prestress force" in warning for warning in comparison["warnings"])
    assert any("envelope change is near zero" in warning for warning in comparison["warnings"])


def test_demand_capacity_warns_when_using_bonded_prestress_result() -> None:
    summary = check_uls_demands_against_rc_pmm(
        PMMSolverResult(points=[_point(1000.0, 100.0, prestress_force=-200.0, bonded_count=1)]),
        [LoadCase(name="ULS-01", Pu_N=500.0, Mux_Nmm=0.0, Muy_Nmm=0.0, load_type="ULS")],
    )

    assert any("Bonded prestress is included" in warning for warning in summary.warnings)


def test_analysis_page_imports_with_prestress_verification() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
