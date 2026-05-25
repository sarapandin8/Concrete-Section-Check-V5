from __future__ import annotations

import json
import math

import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, Point2D, Rebar, RebarMaterial, SectionGeometry
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.io.project_io import project_from_json, project_to_json
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    build_serviceability_summary_from_analysis_input,
    compute_gross_section_properties,
    default_stress_check_points,
    get_active_sls_load_cases,
    sls_load_cases_to_display_dataframe,
)


def _analysis_input(load_cases: list[LoadCase] | None = None) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400, height_mm=600),
        concrete_material=ConcreteMaterial(fc_MPa=40),
        rebar_materials=[RebarMaterial(name="SD40", fy_MPa=400)],
        rebars=[Rebar(x_mm=0, y_mm=0, diameter_mm=25)],
        load_cases=load_cases
        or [
            LoadCase(name="ULS-01", Pu_N=1_000_000, Mux_Nmm=200_000_000, Muy_Nmm=0, load_type="ULS"),
            LoadCase(name="SLS-01", Pu_N=500_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="SLS"),
        ],
    )


def test_serviceability_settings_default_creation() -> None:
    settings = ServiceabilitySettings()

    assert settings.enabled is False
    assert settings.stress_sign_convention == "compression_negative"
    assert settings.section_basis == "gross"
    assert settings.check_load_type == "SLS"


def test_serviceability_settings_rejects_invalid_compression_limit_ratio() -> None:
    with pytest.raises(ValueError):
        ServiceabilitySettings(concrete_compression_limit_ratio=0.0)


def test_serviceability_settings_supports_no_tension_mode() -> None:
    settings = ServiceabilitySettings(
        concrete_tension_limit_mode="no_tension",
        concrete_tension_limit_MPa=3.0,
        allow_tension=True,
    )

    assert settings.concrete_tension_limit_MPa == 0.0
    assert settings.allow_tension is False


def test_compute_gross_section_properties_rectangle_area() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))

    assert props.area_mm2 == pytest.approx(240_000)


def test_compute_gross_section_properties_rectangle_centroid() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))

    assert props.centroid_x_mm == pytest.approx(0.0)
    assert props.centroid_y_mm == pytest.approx(0.0)


def test_compute_gross_section_properties_rectangle_inertia() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))

    assert props.Ix_mm4 == pytest.approx(400 * 600**3 / 12)
    assert props.Iy_mm4 == pytest.approx(600 * 400**3 / 12)
    assert props.Ixy_mm4 == pytest.approx(0.0)


def test_compute_gross_section_properties_handles_hollow_section_net_area() -> None:
    section = rectangular_hollow(
        width_mm=1000,
        height_mm=800,
        t_top_mm=100,
        t_bottom_mm=150,
        t_left_mm=120,
        t_right_mm=180,
    )

    props = compute_gross_section_properties(section)

    assert props.area_mm2 == pytest.approx(1000 * 800 - (1000 - 120 - 180) * (800 - 100 - 150))


def test_default_stress_check_points_returns_expected_points() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400, height_mm=600))
    points = default_stress_check_points(props)
    names = {point.name for point in points}

    assert {"Top fiber", "Bottom fiber", "Left fiber", "Right fiber", "Centroid"}.issubset(names)


def test_get_active_sls_load_cases_filters_active_sls_only() -> None:
    loads = [
        LoadCase(name="ULS", active=True, load_type="ULS"),
        LoadCase(name="SLS-active", active=True, load_type="SLS"),
        LoadCase(name="SLS-inactive", active=False, load_type="SLS"),
    ]

    filtered = get_active_sls_load_cases(loads)

    assert [load.name for load in filtered] == ["SLS-active"]


def test_sls_load_cases_to_display_dataframe_converts_units() -> None:
    loads = [LoadCase(name="SLS-01", Pu_N=500_000, Mux_Nmm=100_000_000, Muy_Nmm=50_000_000, load_type="SLS")]

    df = sls_load_cases_to_display_dataframe(loads)

    assert df.loc[0, "Pu_kN"] == pytest.approx(500)
    assert df.loc[0, "Mux_kNm"] == pytest.approx(100)
    assert df.loc[0, "Muy_kNm"] == pytest.approx(50)


def test_build_serviceability_summary_returns_section_properties_and_sls_loads() -> None:
    summary = build_serviceability_summary_from_analysis_input(_analysis_input(), ServiceabilitySettings(enabled=True))

    assert summary.enabled is True
    assert summary.section_properties is not None
    assert summary.section_properties.area_mm2 == pytest.approx(240_000)
    assert len(summary.sls_load_cases) == 1
    assert len(summary.check_points) == 5


def test_build_serviceability_summary_warns_when_no_sls_load_cases() -> None:
    summary = build_serviceability_summary_from_analysis_input(
        _analysis_input([LoadCase(name="ULS-01", load_type="ULS")]),
        ServiceabilitySettings(),
    )

    assert any("No active SLS load cases" in warning for warning in summary.warnings)


def test_project_model_round_trip_preserves_serviceability_settings() -> None:
    project = ProjectModel(
        serviceability_settings=ServiceabilitySettings(
            enabled=True,
            concrete_compression_limit_ratio=0.50,
            concrete_tension_limit_mode="sqrt_fc_ratio",
        )
    )

    loaded = project_from_json(project_to_json(project))

    assert loaded.serviceability_settings is not None
    assert loaded.serviceability_settings.enabled is True
    assert loaded.serviceability_settings.concrete_compression_limit_ratio == pytest.approx(0.50)
    assert loaded.serviceability_settings.concrete_tension_limit_mode == "sqrt_fc_ratio"


def test_old_project_without_serviceability_settings_loads_safely() -> None:
    text = json.dumps({"project_name": "Legacy", "version": "3.8"})

    loaded = project_from_json(text)

    assert loaded.project_name == "Legacy"
    assert isinstance(loaded.serviceability_settings, ServiceabilitySettings)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
