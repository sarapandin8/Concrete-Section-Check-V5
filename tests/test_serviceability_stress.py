from __future__ import annotations

import math

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Rebar, RebarMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    check_concrete_stress_status,
    compute_gross_section_properties,
    default_stress_check_points,
    elastic_concrete_stress_gross,
    run_gross_section_sls_stress_check,
    service_stress_limits,
    service_stress_results_to_dataframe,
)


def _props():
    return compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))


def _analysis_input(load_cases: list[LoadCase]) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(fc_MPa=40),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400)],
        rebars=[Rebar(x_mm=0, y_mm=0, diameter_mm=25)],
        load_cases=load_cases,
    )


def test_elastic_concrete_stress_gross_axial_compression_is_negative() -> None:
    stress = elastic_concrete_stress_gross(240_000, 0, 0, 0, 0, _props())

    assert stress == pytest.approx(-1.0)


def test_elastic_concrete_stress_gross_axial_tension_is_positive() -> None:
    stress = elastic_concrete_stress_gross(-240_000, 0, 0, 0, 0, _props())

    assert stress == pytest.approx(1.0)


def test_elastic_concrete_stress_gross_bending_about_x_opposite_top_bottom_signs() -> None:
    props = _props()
    top = elastic_concrete_stress_gross(0, 100_000_000, 0, 0, props.y_max_mm, props)
    bottom = elastic_concrete_stress_gross(0, 100_000_000, 0, 0, props.y_min_mm, props)

    assert top > 0
    assert bottom < 0
    assert top == pytest.approx(-bottom)


def test_elastic_concrete_stress_gross_bending_about_y_opposite_left_right_signs() -> None:
    props = _props()
    right = elastic_concrete_stress_gross(0, 0, 100_000_000, props.x_max_mm, 0, props)
    left = elastic_concrete_stress_gross(0, 0, 100_000_000, props.x_min_mm, 0, props)

    assert right > 0
    assert left < 0
    assert right == pytest.approx(-left)


def test_service_stress_limits_compression_limit_ratio_times_fc() -> None:
    limits = service_stress_limits(40, ServiceabilitySettings(concrete_compression_limit_ratio=0.45))

    assert limits["compression_limit_MPa"] == pytest.approx(18.0)


def test_service_stress_limits_no_tension_gives_zero_tension_limit() -> None:
    limits = service_stress_limits(
        40,
        ServiceabilitySettings(concrete_tension_limit_mode="no_tension", concrete_tension_limit_MPa=3.0),
    )

    assert limits["tension_limit_MPa"] == pytest.approx(0.0)
    assert limits["allow_tension"] is False


def test_service_stress_limits_sqrt_fc_ratio() -> None:
    limits = service_stress_limits(
        36,
        ServiceabilitySettings(concrete_tension_limit_mode="sqrt_fc_ratio", concrete_tension_sqrt_fc_ratio=0.5),
    )

    assert limits["tension_limit_MPa"] == pytest.approx(3.0)


def test_check_concrete_stress_status_passes_compression_within_limit() -> None:
    status, message = check_concrete_stress_status(-10, 18, 3)

    assert status == "PASS"
    assert "within" in message


def test_check_concrete_stress_status_fails_compression_exceeding_limit() -> None:
    status, message = check_concrete_stress_status(-20, 18, 3)

    assert status == "FAIL"
    assert "exceeds" in message


def test_check_concrete_stress_status_passes_tension_within_limit() -> None:
    status, message = check_concrete_stress_status(2, 18, 3, allow_tension=True)

    assert status == "PASS"
    assert "Tension" in message


def test_check_concrete_stress_status_fails_no_tension_violation() -> None:
    status, message = check_concrete_stress_status(0.1, 18, 0, allow_tension=False)

    assert status == "FAIL"
    assert "No-tension" in message


def test_run_gross_section_sls_stress_check_returns_results_for_active_sls() -> None:
    analysis_input = _analysis_input(
        [
            LoadCase(name="SLS-01", Pu_N=240_000, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS"),
            LoadCase(name="SLS-02", Pu_N=240_000, Mux_Nmm=0, Muy_Nmm=100_000_000, load_type="SLS", active=False),
        ]
    )

    summary = run_gross_section_sls_stress_check(analysis_input, ServiceabilitySettings(enabled=True, concrete_tension_limit_MPa=10))

    assert len(summary.sls_load_cases) == 1
    assert len(summary.stress_results) == 5
    assert {result.combo_name for result in summary.stress_results} == {"SLS-01"}


def test_run_gross_section_sls_stress_check_ignores_uls_load_cases() -> None:
    analysis_input = _analysis_input(
        [
            LoadCase(name="ULS-01", Pu_N=999_000, Mux_Nmm=999_000, Muy_Nmm=999_000, load_type="ULS"),
            LoadCase(name="SLS-01", Pu_N=240_000, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS"),
        ]
    )

    summary = run_gross_section_sls_stress_check(analysis_input, ServiceabilitySettings())

    assert {load.name for load in summary.sls_load_cases} == {"SLS-01"}
    assert {result.combo_name for result in summary.stress_results} == {"SLS-01"}


def test_service_stress_results_to_dataframe_contains_required_columns() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([LoadCase(name="SLS-01", Pu_N=240_000, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")]),
        ServiceabilitySettings(),
    )

    df = service_stress_results_to_dataframe(summary)

    assert {
        "Combo",
        "Point",
        "x_mm",
        "y_mm",
        "Stress_MPa",
        "Stress Type",
        "Limit_MPa",
        "Utilization",
        "Status",
        "Message",
    }.issubset(df.columns)


def test_serviceability_summary_identifies_governing_utilization() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([LoadCase(name="SLS-01", Pu_N=240_000, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS")]),
        ServiceabilitySettings(concrete_tension_limit_MPa=10),
    )

    assert summary.governing_combo == "SLS-01"
    assert summary.governing_point is not None
    assert summary.max_utilization is not None
    assert summary.max_utilization >= 0


def test_service_stress_results_dataframe_can_convert_to_csv() -> None:
    summary = run_gross_section_sls_stress_check(
        _analysis_input([LoadCase(name="SLS-01", Pu_N=240_000, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")]),
        ServiceabilitySettings(),
    )
    csv_text = service_stress_results_to_dataframe(summary).to_csv(index=False)

    assert "Stress_MPa" in csv_text


def test_default_points_stress_results_include_compression_negative_tension_positive() -> None:
    props = _props()
    points = {point.name: point for point in default_stress_check_points(props)}
    top_stress = elastic_concrete_stress_gross(0, 100_000_000, 0, points["Top fiber"].x_mm, points["Top fiber"].y_mm, props)
    bottom_stress = elastic_concrete_stress_gross(0, 100_000_000, 0, points["Bottom fiber"].x_mm, points["Bottom fiber"].y_mm, props)

    assert top_stress > 0
    assert bottom_stress < 0


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
