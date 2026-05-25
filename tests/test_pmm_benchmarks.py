from __future__ import annotations

import pytest

from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.result_models import pmm_result_to_display_dataframe, summarize_pmm_result
from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.visualization.pmm_dashboard import pmm_slice_at_pu
from concrete_pmm_pro.verification.pmm_benchmarks import (
    FAIL,
    PMMVerificationSummary,
    build_rectangular_rc_column_case,
    build_rectangular_rc_column_high_as_case,
    build_rectangular_rc_column_high_fc_case,
    build_rectangular_rc_with_bonded_pt_bar_case,
    run_pmm_verification_suite,
)


@pytest.fixture(scope="module")
def base_result():
    return run_rc_pmm_solver(build_rectangular_rc_column_case())


def _max_capped_phiPn(result) -> float:
    df = pmm_result_to_display_dataframe(result)
    return float(df["phiPn_capped_N"].max())


def _balance_ratio(result, column: str) -> float:
    df = pmm_result_to_display_dataframe(result)
    positive = float(df[column].max())
    negative = abs(float(df[column].min()))
    return abs(positive - negative) / max(positive, negative, 1.0)


def test_build_rectangular_rc_column_case_returns_valid_analysis_input() -> None:
    analysis_input = build_rectangular_rc_column_case()

    assert isinstance(analysis_input, AnalysisInput)
    assert analysis_input.section_geometry.outer_polygon
    assert analysis_input.rebars
    assert not analysis_input.prestress_elements


def test_base_benchmark_solver_produces_non_empty_result(base_result) -> None:
    assert len(base_result.points) > 0


def test_benchmark_result_contains_no_nan_or_inf(base_result) -> None:
    summary = summarize_pmm_result(base_result)

    assert summary["has_nan"] is False
    assert summary["has_inf"] is False


def test_higher_fc_increases_max_capped_phipn(base_result) -> None:
    high_fc_result = run_rc_pmm_solver(build_rectangular_rc_column_high_fc_case())

    assert _max_capped_phiPn(high_fc_result) > _max_capped_phiPn(base_result)


def test_higher_as_does_not_reduce_max_capped_phipn(base_result) -> None:
    high_as_result = run_rc_pmm_solver(build_rectangular_rc_column_high_as_case())

    assert _max_capped_phiPn(high_as_result) >= 0.995 * _max_capped_phiPn(base_result)


def test_symmetric_benchmark_has_balanced_positive_negative_mnx(base_result) -> None:
    assert _balance_ratio(base_result, "phiMnx_Nmm") <= 0.20


def test_symmetric_benchmark_has_balanced_positive_negative_mny(base_result) -> None:
    assert _balance_ratio(base_result, "phiMny_Nmm") <= 0.20


def test_rc_plus_bonded_pt_bar_benchmark_differs_from_rc_only(base_result) -> None:
    pt_result = run_rc_pmm_solver(build_rectangular_rc_with_bonded_pt_bar_case())
    rc_df = pmm_result_to_display_dataframe(base_result)
    pt_df = pmm_result_to_display_dataframe(pt_result)
    delta = abs(float(pt_df["phiPn_kN"].max()) - float(rc_df["phiPn_kN"].max()))
    delta += abs(float(pt_df["phiMnx_kNm"].abs().max()) - float(rc_df["phiMnx_kNm"].abs().max()))
    delta += abs(float(pt_df["phiMny_kNm"].abs().max()) - float(rc_df["phiMny_kNm"].abs().max()))

    assert delta > 0.0


def test_bonded_pt_bar_produces_nonzero_prestress_force() -> None:
    pt_result = run_rc_pmm_solver(build_rectangular_rc_with_bonded_pt_bar_case())
    df = pmm_result_to_display_dataframe(pt_result)

    assert float(df["prestress_force_N"].abs().max()) > 0.0


def test_unbonded_prestress_remains_ignored_with_warning() -> None:
    analysis_input = build_rectangular_rc_with_bonded_pt_bar_case()
    unbonded = analysis_input.prestress_elements[0].model_copy(update={"bonded": False})
    analysis_input = analysis_input.model_copy(update={"prestress_elements": [unbonded]})
    result = run_rc_pmm_solver(analysis_input)
    df = pmm_result_to_display_dataframe(result)

    assert any("Unbonded prestress is not included" in warning for warning in result.warnings)
    assert int(df["unbonded_prestress_ignored_count"].max()) == unbonded.count
    assert float(df["prestress_force_N"].abs().max()) == pytest.approx(0.0)


def test_pmm_slice_at_pu_returns_non_empty_slice_for_benchmark_result(base_result) -> None:
    df = pmm_result_to_display_dataframe(base_result)
    slice_df = pmm_slice_at_pu(df, 1000.0)

    assert not slice_df.empty


def test_run_pmm_verification_suite_returns_summary() -> None:
    summary = run_pmm_verification_suite()

    assert isinstance(summary, PMMVerificationSummary)
    assert summary.checks


def test_verification_suite_includes_rebar_displaced_concrete_checks() -> None:
    summary = run_pmm_verification_suite()
    names = {check.name for check in summary.checks}

    assert "Rebar net force inside compression block" in names
    assert "PMM changes with rebar displacement subtraction" in names


def test_verification_suite_overall_status_is_not_fail() -> None:
    summary = run_pmm_verification_suite()

    assert summary.overall_status != FAIL


def test_analysis_page_imports_without_error_for_verification_expander() -> None:
    from concrete_pmm_pro.ui import analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
