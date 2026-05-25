from __future__ import annotations

import math

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar, RebarMaterial
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    build_serviceability_limit_set,
    check_service_stress_point,
    run_elastic_sls_stress_check,
    service_stress_results_to_dataframe,
    summarize_serviceability_results,
)
from concrete_pmm_pro.serviceability.models import ServiceStressPointResult


def _analysis_input(
    load_case: LoadCase,
    *,
    rebars: list[Rebar] | None = None,
    prestress_elements: list[PrestressElement] | None = None,
) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(fc_MPa=40),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400, Es_MPa=200_000)],
        rebars=rebars or [],
        prestress_elements=prestress_elements or [],
        load_cases=[load_case],
    )


def test_build_serviceability_limit_set_compression_limit_ratio_times_fc() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(concrete_compression_limit_ratio=0.45))

    assert limits.compression_limit_MPa == pytest.approx(18.0)


def test_build_serviceability_limit_set_no_tension_sets_zero_tension_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(no_tension_check=True, concrete_tension_limit_MPa=3.0))

    assert limits.tension_limit_MPa == pytest.approx(0.0)
    assert limits.allow_tension is False
    assert limits.no_tension_required is True


def test_build_serviceability_limit_set_decompression_sets_zero_tension_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(decompression_check=True, concrete_tension_limit_MPa=3.0))

    assert limits.tension_limit_MPa == pytest.approx(0.0)
    assert limits.allow_tension is False
    assert limits.decompression_required is True


def test_build_serviceability_limit_set_sqrt_fc_ratio() -> None:
    limits = build_serviceability_limit_set(
        36,
        ServiceabilitySettings(concrete_tension_limit_mode="sqrt_fc_ratio", concrete_tension_sqrt_fc_ratio=0.5),
    )

    assert limits.tension_limit_MPa == pytest.approx(0.5 * math.sqrt(36))


def test_check_service_stress_point_passes_compression_within_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings())

    status, message, utilization, stress_type = check_service_stress_point(-10, limits)

    assert status == "PASS"
    assert "Compression" in message
    assert utilization == pytest.approx(10 / 18)
    assert stress_type == "Compression"


def test_check_service_stress_point_fails_compression_over_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(concrete_compression_limit_ratio=0.25))

    status, message, utilization, stress_type = check_service_stress_point(-12, limits)

    assert status == "FAIL"
    assert "exceeds" in message
    assert utilization == pytest.approx(12 / 10)
    assert stress_type == "Compression"


def test_check_service_stress_point_passes_tension_within_user_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(concrete_tension_limit_MPa=3.0))

    status, message, utilization, stress_type = check_service_stress_point(2.0, limits)

    assert status == "PASS"
    assert "Tension" in message
    assert utilization == pytest.approx(2 / 3)
    assert stress_type == "Tension"


def test_check_service_stress_point_fails_tension_over_user_limit() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(concrete_tension_limit_MPa=3.0))

    status, message, utilization, stress_type = check_service_stress_point(4.0, limits)

    assert status == "FAIL"
    assert "Tension" in message
    assert utilization == pytest.approx(4 / 3)
    assert stress_type == "Tension"


def test_check_service_stress_point_fails_tension_when_no_tension_required() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(no_tension_check=True))

    status, message, utilization, stress_type = check_service_stress_point(0.001, limits)

    assert status == "FAIL"
    assert "No-tension" in message
    assert utilization is None
    assert stress_type == "Tension"


def test_check_service_stress_point_fails_tension_when_decompression_required() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(decompression_check=True))

    status, message, utilization, stress_type = check_service_stress_point(0.001, limits)

    assert status == "FAIL"
    assert "decompression" in message
    assert utilization is None
    assert stress_type == "Tension"


def test_check_service_stress_point_near_zero_passes_as_zero() -> None:
    limits = build_serviceability_limit_set(40, ServiceabilitySettings(stress_zero_tolerance_MPa=1.0e-6))

    status, _message, utilization, stress_type = check_service_stress_point(5.0e-7, limits)

    assert status == "PASS"
    assert utilization == pytest.approx(0.0)
    assert stress_type == "Zero"


def test_summarize_serviceability_results_returns_fail_if_any_point_fails() -> None:
    summary = summarize_serviceability_results(
        [
            ServiceStressPointResult(combo_name="SLS-01", point_name="Top", x_mm=0, y_mm=0, status="PASS"),
            ServiceStressPointResult(
                combo_name="SLS-02",
                point_name="Bottom",
                x_mm=0,
                y_mm=0,
                stress_MPa=2,
                stress_type="Tension",
                status="FAIL",
                message="No-tension requirement violated.",
            ),
        ]
    )

    assert summary["overall_status"] == "FAIL"
    assert summary["no_tension_violation_count"] == 1


def test_summarize_serviceability_results_identifies_governing_combo_and_point() -> None:
    summary = summarize_serviceability_results(
        [
            ServiceStressPointResult(
                combo_name="SLS-01",
                point_name="Top",
                x_mm=0,
                y_mm=0,
                stress_MPa=-4,
                stress_type="Compression",
                utilization=0.3,
                status="PASS",
            ),
            ServiceStressPointResult(
                combo_name="SLS-02",
                point_name="Bottom",
                x_mm=0,
                y_mm=0,
                stress_MPa=-8,
                stress_type="Compression",
                utilization=0.9,
                status="PASS",
            ),
        ]
    )

    assert summary["governing_combo"] == "SLS-02"
    assert summary["governing_point"] == "Bottom"
    assert summary["max_utilization"] == pytest.approx(0.9)


def test_run_sls_stress_check_no_tension_fails_when_tensile_stress_exists() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS")),
        ServiceabilitySettings(no_tension_check=True),
    )

    assert summary.overall_status == "FAIL"
    assert summary.no_tension_violation_count > 0
    assert any(result.stress_type == "Tension" and result.status == "FAIL" for result in summary.stress_results)


def test_run_sls_stress_check_decompression_fails_when_tensile_stress_exists() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS")),
        ServiceabilitySettings(decompression_check=True),
    )

    assert summary.overall_status == "FAIL"
    assert summary.decompression_violation_count > 0


def test_run_sls_stress_check_allowable_tension_can_pass_below_limit() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=10_000_000, Muy_Nmm=0, load_type="SLS")),
        ServiceabilitySettings(concrete_tension_limit_MPa=1.0),
    )

    assert summary.overall_status == "PASS"
    assert summary.max_tension_MPa is not None
    assert summary.max_tension_MPa < 1.0


def test_transformed_section_basis_works_with_no_tension_check() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(
            LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=100_000_000, Muy_Nmm=0, load_type="SLS"),
            rebars=[Rebar(x_mm=0, y_mm=250, diameter_mm=32)],
        ),
        ServiceabilitySettings(use_transformed_section=True, concrete_Ec_MPa=30_000, no_tension_check=True),
    )

    assert summary.section_basis_used == "transformed_uncracked"
    assert summary.overall_status == "FAIL"
    assert summary.no_tension_violation_count > 0


def test_effective_prestress_contribution_affects_total_stress_and_status() -> None:
    load_case = LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=10_000_000, Muy_Nmm=0, load_type="SLS")
    base = run_elastic_sls_stress_check(_analysis_input(load_case), ServiceabilitySettings(no_tension_check=True))
    with_prestress = run_elastic_sls_stress_check(
        _analysis_input(
            load_case,
            prestress_elements=[PrestressElement(x_mm=0, y_mm=100, area_mm2=100, pe_eff_n=240_000, bonded=True)],
        ),
        ServiceabilitySettings(no_tension_check=True, include_prestress_effective_force=True),
    )

    assert base.overall_status == "FAIL"
    assert with_prestress.overall_status == "PASS"
    assert any(result.prestress_stress_MPa != pytest.approx(0.0) for result in with_prestress.stress_results)


def test_critical_point_filter_extreme_fibers_only_excludes_centroid_from_governing_results() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=-240_000, Mux_Nmm=0, Muy_Nmm=0, load_type="SLS")),
        ServiceabilitySettings(critical_point_filter="extreme_fibers_only", concrete_tension_limit_MPa=2.0),
    )

    assert any(result.point_name == "Centroid" for result in summary.stress_results)
    assert summary.governing_point != "Centroid"
    assert len(summary.stress_results) == 5


def test_serviceability_settings_round_trip_preserves_new_fields() -> None:
    project = ProjectModel(
        serviceability_settings=ServiceabilitySettings(
            no_tension_check=True,
            decompression_check=True,
            stress_zero_tolerance_MPa=2.0e-6,
            critical_point_filter="extreme_fibers_only",
        )
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded.serviceability_settings is not None
    assert loaded.serviceability_settings.no_tension_check is True
    assert loaded.serviceability_settings.decompression_check is True
    assert loaded.serviceability_settings.stress_zero_tolerance_MPa == pytest.approx(2.0e-6)
    assert loaded.serviceability_settings.critical_point_filter == "extreme_fibers_only"


def test_service_stress_results_to_dataframe_includes_judgement_columns() -> None:
    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=0, Mux_Nmm=10_000_000, Muy_Nmm=0, load_type="SLS")),
        ServiceabilitySettings(concrete_tension_limit_MPa=1.0),
    )

    df = service_stress_results_to_dataframe(summary)

    assert {"Stress Type", "Limit_MPa", "Utilization", "Status", "Message"}.issubset(df.columns)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
