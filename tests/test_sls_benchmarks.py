from __future__ import annotations

import pytest

from concrete_pmm_pro.serviceability import (
    compute_gross_section_properties,
    run_elastic_sls_stress_check,
    service_stress_results_to_dataframe,
)
from concrete_pmm_pro.verification.sls_benchmarks import (
    SLSBenchmarkSummary,
    build_rectangular_sls_gross_case,
    build_rectangular_sls_no_tension_case,
    build_rectangular_sls_with_bottom_prestress_case,
    build_rectangular_sls_with_top_prestress_case,
    build_rectangular_sls_with_transformed_rebar_case,
    run_sls_verification_suite,
    sls_benchmark_summary_to_dataframe,
)


def _result(summary, combo: str, point: str):
    return next(result for result in summary.stress_results if result.combo_name == combo and result.point_name == point)


def test_build_rectangular_sls_gross_case_returns_valid_input_and_settings() -> None:
    analysis_input, settings = build_rectangular_sls_gross_case()

    assert analysis_input.section_geometry is not None
    assert settings.enabled is True
    assert {case.name for case in analysis_input.load_cases} == {"SLS-AXIAL-COMP", "SLS-MX", "SLS-MY"}


def test_axial_compression_hand_check_gives_negative_uniform_stress() -> None:
    analysis_input, settings = build_rectangular_sls_gross_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)
    stresses = [result.stress_MPa for result in summary.stress_results if result.combo_name == "SLS-AXIAL-COMP"]

    assert all(stress < 0 for stress in stresses)
    assert max(stresses) == pytest.approx(min(stresses))


def test_axial_compression_hand_value_equals_negative_pu_over_area() -> None:
    analysis_input, settings = build_rectangular_sls_gross_case()
    props = compute_gross_section_properties(analysis_input.section_geometry)
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    centroid = _result(summary, "SLS-AXIAL-COMP", "Centroid")

    assert centroid.stress_MPa == pytest.approx(-1_000_000 / props.area_mm2)


def test_mux_bending_gives_opposite_signs_at_top_bottom() -> None:
    analysis_input, settings = build_rectangular_sls_gross_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    top = _result(summary, "SLS-MX", "Top fiber")
    bottom = _result(summary, "SLS-MX", "Bottom fiber")

    assert top.stress_MPa > 0
    assert bottom.stress_MPa < 0
    assert top.stress_MPa == pytest.approx(-bottom.stress_MPa)


def test_muy_bending_gives_opposite_signs_at_left_right() -> None:
    analysis_input, settings = build_rectangular_sls_gross_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    right = _result(summary, "SLS-MY", "Right fiber")
    left = _result(summary, "SLS-MY", "Left fiber")

    assert right.stress_MPa > 0
    assert left.stress_MPa < 0
    assert right.stress_MPa == pytest.approx(-left.stress_MPa)


def test_concentric_prestress_gives_uniform_negative_stress() -> None:
    from concrete_pmm_pro.core.models import LoadCase, PrestressElement
    from concrete_pmm_pro.verification.sls_benchmarks import _base_input
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input = _base_input(
        [LoadCase(name="SLS-PS", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
        prestress_elements=[PrestressElement(x_mm=0, y_mm=0, area_mm2=100, pe_eff_n=500_000, bonded=True)],
    )
    summary = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(include_prestress_effective_force=True, concrete_tension_limit_MPa=10),
    )
    stresses = [result.prestress_stress_MPa for result in summary.stress_results]

    assert all(stress < 0 for stress in stresses)
    assert max(stresses) == pytest.approx(min(stresses))


def test_top_prestress_makes_top_stress_more_compressive_than_bottom() -> None:
    analysis_input, settings = build_rectangular_sls_with_top_prestress_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    top = _result(summary, "SLS-PS-TOP", "Top fiber")
    bottom = _result(summary, "SLS-PS-TOP", "Bottom fiber")

    assert top.prestress_stress_MPa < bottom.prestress_stress_MPa


def test_bottom_prestress_makes_bottom_stress_more_compressive_than_top() -> None:
    analysis_input, settings = build_rectangular_sls_with_bottom_prestress_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    top = _result(summary, "SLS-PS-BOTTOM", "Top fiber")
    bottom = _result(summary, "SLS-PS-BOTTOM", "Bottom fiber")

    assert bottom.prestress_stress_MPa < top.prestress_stress_MPa


def test_right_prestress_makes_right_stress_more_compressive_than_left() -> None:
    from concrete_pmm_pro.core.models import LoadCase
    from concrete_pmm_pro.verification.sls_benchmarks import _base_input, _prestress_element
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input = _base_input(
        [LoadCase(name="SLS-PS-RIGHT", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
        prestress_elements=[_prestress_element(120, 0, "RIGHT")],
    )
    summary = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(include_prestress_effective_force=True, concrete_tension_limit_MPa=10),
    )
    right = _result(summary, "SLS-PS-RIGHT", "Right fiber")
    left = _result(summary, "SLS-PS-RIGHT", "Left fiber")

    assert right.prestress_stress_MPa < left.prestress_stress_MPa


def test_left_prestress_makes_left_stress_more_compressive_than_right() -> None:
    from concrete_pmm_pro.core.models import LoadCase
    from concrete_pmm_pro.verification.sls_benchmarks import _base_input, _prestress_element
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input = _base_input(
        [LoadCase(name="SLS-PS-LEFT", Pu_N=0, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")],
        prestress_elements=[_prestress_element(-120, 0, "LEFT")],
    )
    summary = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(include_prestress_effective_force=True, concrete_tension_limit_MPa=10),
    )
    right = _result(summary, "SLS-PS-LEFT", "Right fiber")
    left = _result(summary, "SLS-PS-LEFT", "Left fiber")

    assert left.prestress_stress_MPa < right.prestress_stress_MPa


def test_concrete_only_transformed_stress_matches_gross_stress_approximately() -> None:
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input, gross_settings = build_rectangular_sls_gross_case()
    gross = run_elastic_sls_stress_check(analysis_input, gross_settings)
    transformed = run_elastic_sls_stress_check(
        analysis_input,
        ServiceabilitySettings(
            use_transformed_section=True,
            transformed_include_rebar=False,
            transformed_include_prestress=False,
            concrete_Ec_MPa=30_000,
            concrete_tension_limit_MPa=10,
        ),
    )

    for gross_result, transformed_result in zip(gross.stress_results, transformed.stress_results, strict=True):
        assert transformed_result.stress_MPa == pytest.approx(gross_result.stress_MPa)


def test_symmetric_transformed_rebar_increases_inertia_and_reduces_stress_magnitude() -> None:
    analysis_input, transformed_settings = build_rectangular_sls_with_transformed_rebar_case()
    transformed = run_elastic_sls_stress_check(analysis_input, transformed_settings)
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    gross = run_elastic_sls_stress_check(analysis_input, ServiceabilitySettings(concrete_tension_limit_MPa=10))

    assert transformed.transformed_section_properties.Ix_mm4 > gross.section_properties.Ix_mm4
    transformed_top = _result(transformed, "SLS-MX", "Top fiber")
    gross_top = _result(gross, "SLS-MX", "Top fiber")
    assert abs(transformed_top.external_stress_MPa) < abs(gross_top.external_stress_MPa)


def test_transformed_result_uses_transformed_uncracked_basis() -> None:
    analysis_input, settings = build_rectangular_sls_with_transformed_rebar_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    assert summary.section_basis_used == "transformed_uncracked"
    assert {result.section_basis for result in summary.stress_results} == {"transformed_uncracked"}


def test_no_tension_benchmark_fails_when_tensile_stress_exists() -> None:
    analysis_input, settings = build_rectangular_sls_no_tension_case()
    summary = run_elastic_sls_stress_check(analysis_input, settings)

    assert summary.overall_status == "FAIL"
    assert summary.no_tension_violation_count > 0


def test_decompression_benchmark_fails_when_tensile_stress_exists() -> None:
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input, _settings = build_rectangular_sls_no_tension_case()
    summary = run_elastic_sls_stress_check(analysis_input, ServiceabilitySettings(decompression_check=True))

    assert summary.overall_status == "FAIL"
    assert summary.decompression_violation_count > 0


def test_allowable_tension_benchmark_passes_when_limit_is_high() -> None:
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input, _settings = build_rectangular_sls_no_tension_case()
    summary = run_elastic_sls_stress_check(analysis_input, ServiceabilitySettings(concrete_tension_limit_MPa=5.0))

    assert summary.overall_status == "PASS"


def test_allowable_tension_benchmark_fails_when_limit_is_low() -> None:
    from concrete_pmm_pro.serviceability import ServiceabilitySettings

    analysis_input, _settings = build_rectangular_sls_no_tension_case()
    summary = run_elastic_sls_stress_check(analysis_input, ServiceabilitySettings(concrete_tension_limit_MPa=1.0))

    assert summary.overall_status == "FAIL"


def test_governing_sls_benchmark_identifies_governing_combo_and_point() -> None:
    from concrete_pmm_pro.core.models import LoadCase
    from concrete_pmm_pro.serviceability import ServiceabilitySettings
    from concrete_pmm_pro.verification.sls_benchmarks import _base_input

    analysis_input = _base_input(
        [
            LoadCase(name="SLS-LOW", Pu_N=0, Mux_Nmm=10_000_000, Muy_Nmm=0, load_type="SLS"),
            LoadCase(name="SLS-HIGH", Pu_N=0, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS"),
        ]
    )
    summary = run_elastic_sls_stress_check(analysis_input, ServiceabilitySettings(concrete_tension_limit_MPa=10))

    assert summary.governing_combo == "SLS-HIGH"
    assert summary.governing_point
    assert summary.max_utilization is not None


def test_run_sls_verification_suite_returns_summary() -> None:
    summary = run_sls_verification_suite()

    assert isinstance(summary, SLSBenchmarkSummary)
    assert summary.checks


def test_sls_verification_suite_has_no_fail_for_normal_benchmark_setup() -> None:
    summary = run_sls_verification_suite()

    assert summary.fail_count == 0
    assert summary.overall_status in {"PASS", "WARNING"}


def test_sls_benchmark_summary_to_dataframe_contains_required_columns() -> None:
    summary = run_sls_verification_suite()
    df = sls_benchmark_summary_to_dataframe(summary)

    assert {
        "Check",
        "Status",
        "Calculated Value",
        "Expected Value",
        "Percent Difference",
        "Tolerance Percent",
        "Message",
    }.issubset(df.columns)


def test_sls_verification_csv_dataframe_can_convert_to_csv() -> None:
    summary = run_sls_verification_suite()
    csv_text = sls_benchmark_summary_to_dataframe(summary).to_csv(index=False)

    assert "Check" in csv_text


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
