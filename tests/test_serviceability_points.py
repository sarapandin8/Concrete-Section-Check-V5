from __future__ import annotations

import pandas as pd
import pytest

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase
from concrete_pmm_pro.geometry.generators import rectangle, rectangular_hollow
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    StressCheckPoint,
    classify_service_stress_results_for_cracking,
    crack_classification_to_dataframe,
    custom_stress_check_points_from_dataframe,
    dataframe_to_stress_check_points,
    default_stress_check_points,
    merge_default_and_custom_stress_check_points,
    run_elastic_sls_stress_check,
    service_stress_results_to_dataframe,
    stress_check_points_to_dataframe,
    validate_stress_check_points_against_geometry,
)
from concrete_pmm_pro.serviceability.section_properties import compute_gross_section_properties


def _custom_df(**overrides) -> pd.DataFrame:
    row = {
        "Active": True,
        "Name": "Tendon Zone",
        "x_mm": 0.0,
        "y_mm": 100.0,
        "Point Type": "tendon_zone",
        "Include in Governing": True,
        "Note": "review point",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def _analysis_input(load_case: LoadCase | None = None) -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="C40", fc_MPa=40.0),
        load_cases=[load_case or LoadCase(name="SLS-01", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")],
    )


def test_stress_check_point_supports_custom_metadata() -> None:
    point = StressCheckPoint(
        name="Tendon Zone",
        x_mm=0.0,
        y_mm=100.0,
        point_type="tendon_zone",
        active=True,
        include_in_governing=False,
        source="user",
    )

    assert point.point_type == "tendon_zone"
    assert point.active is True
    assert point.include_in_governing is False
    assert point.source == "user"


def test_custom_stress_check_points_from_dataframe_parses_valid_points() -> None:
    result = custom_stress_check_points_from_dataframe(_custom_df())

    assert not result.errors
    assert len(result.points) == 1
    assert result.points[0].point_type == "tendon_zone"


def test_blank_name_is_auto_generated() -> None:
    result = custom_stress_check_points_from_dataframe(_custom_df(Name=""))

    assert result.points[0].name == "Custom-1"
    assert any("blank name" in item for item in result.info)


def test_nonnumeric_xy_produces_error() -> None:
    result = custom_stress_check_points_from_dataframe(_custom_df(x_mm="bad"))

    assert result.errors
    assert not result.points


def test_unknown_point_type_becomes_custom_with_warning() -> None:
    result = custom_stress_check_points_from_dataframe(_custom_df(**{"Point Type": "mystery"}))

    assert result.points[0].point_type == "custom"
    assert any("unknown point type" in warning for warning in result.warnings)


def test_inactive_custom_point_is_ignored_for_analysis() -> None:
    result = custom_stress_check_points_from_dataframe(_custom_df(Active=False))

    assert not result.points
    assert any("inactive" in item for item in result.info)


def test_stress_check_points_dataframe_conversion_preserves_inactive_rows() -> None:
    points = [
        StressCheckPoint(
            name="Stored Active",
            x_mm=0.0,
            y_mm=100.0,
            point_type="tendon_zone",
            active=True,
            include_in_governing=True,
            note="active",
        ),
        StressCheckPoint(
            name="Stored Inactive",
            x_mm=50.0,
            y_mm=0.0,
            point_type="segmental_joint",
            active=False,
            include_in_governing=False,
            note="inactive",
        ),
    ]

    df = stress_check_points_to_dataframe(points)
    round_trip = dataframe_to_stress_check_points(df)

    assert {"Active", "Name", "x_mm", "y_mm", "Point Type", "Include in Governing", "Note"}.issubset(df.columns)
    assert len(round_trip) == 2
    assert round_trip[0].point_type == "tendon_zone"
    assert round_trip[1].active is False
    assert round_trip[1].include_in_governing is False
    assert round_trip[1].note == "inactive"


def test_validate_stress_check_points_allows_point_inside_concrete() -> None:
    errors, warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Inside", x_mm=0.0, y_mm=0.0)],
        rectangle(width_mm=400.0, height_mm=600.0),
    )

    assert not errors
    assert not warnings


def test_validate_stress_check_points_allows_point_on_boundary() -> None:
    errors, _warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Boundary", x_mm=200.0, y_mm=0.0)],
        rectangle(width_mm=400.0, height_mm=600.0),
    )

    assert not errors


def test_validate_stress_check_points_rejects_point_outside_concrete() -> None:
    errors, _warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Outside", x_mm=300.0, y_mm=0.0)],
        rectangle(width_mm=400.0, height_mm=600.0),
    )

    assert any("outside" in error.lower() for error in errors)


def test_validate_stress_check_points_rejects_point_inside_void() -> None:
    errors, _warnings = validate_stress_check_points_against_geometry(
        [StressCheckPoint(name="Void", x_mm=0.0, y_mm=0.0)],
        rectangular_hollow(width_mm=1000.0, height_mm=800.0, wall_thickness_mm=100.0),
    )

    assert any("void" in error.lower() for error in errors)


def test_merge_default_and_custom_stress_check_points_preserves_order() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400.0, height_mm=600.0))
    default_points = default_stress_check_points(props)
    custom = [StressCheckPoint(name="Custom A", x_mm=0.0, y_mm=100.0)]

    merged = merge_default_and_custom_stress_check_points(default_points, custom)

    assert merged[0].name == "Top fiber"
    assert merged[-1].name == "Custom A"


def test_merge_default_and_custom_stress_check_points_can_exclude_defaults() -> None:
    props = compute_gross_section_properties(rectangle(width_mm=400.0, height_mm=600.0))
    default_points = default_stress_check_points(props)
    custom = [StressCheckPoint(name="Custom A", x_mm=0.0, y_mm=100.0)]

    merged = merge_default_and_custom_stress_check_points(default_points, custom, include_default_points=False)

    assert [point.name for point in merged] == ["Custom A"]


def test_sls_stress_check_includes_custom_point_in_results() -> None:
    custom = [StressCheckPoint(name="Tendon Zone", x_mm=0.0, y_mm=100.0, point_type="tendon_zone")]

    summary = run_elastic_sls_stress_check(
        _analysis_input(),
        ServiceabilitySettings(concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=custom,
    )

    assert any(result.point_name == "Tendon Zone" for result in summary.stress_results)


def test_sls_stress_check_excludes_loaded_inactive_custom_point() -> None:
    custom = [
        StressCheckPoint(name="Loaded Active", x_mm=0.0, y_mm=100.0, point_type="tendon_zone", active=True),
        StressCheckPoint(name="Loaded Inactive", x_mm=0.0, y_mm=-100.0, point_type="custom", active=False),
    ]

    summary = run_elastic_sls_stress_check(
        _analysis_input(),
        ServiceabilitySettings(concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=custom,
        include_default_stress_check_points=False,
    )

    point_names = {result.point_name for result in summary.stress_results}
    assert "Loaded Active" in point_names
    assert "Loaded Inactive" not in point_names


def test_service_stress_dataframe_includes_custom_point_fields() -> None:
    custom = [StressCheckPoint(name="Tendon Zone", x_mm=0.0, y_mm=100.0, point_type="tendon_zone")]
    summary = run_elastic_sls_stress_check(
        _analysis_input(),
        ServiceabilitySettings(concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=custom,
    )
    df = service_stress_results_to_dataframe(summary)

    assert {"Point Type", "Source", "Include in Governing"}.issubset(df.columns)


def test_cracking_classification_dataframe_includes_custom_point_fields() -> None:
    custom = [StressCheckPoint(name="Tendon Zone", x_mm=0.0, y_mm=100.0, point_type="tendon_zone")]
    summary = run_elastic_sls_stress_check(
        _analysis_input(),
        ServiceabilitySettings(concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=custom,
    )
    classification = classify_service_stress_results_for_cracking(summary, summary.settings)
    df = crack_classification_to_dataframe(classification)

    assert {"Point Type", "Source", "Include in Governing"}.issubset(df.columns)
    assert "Tendon Zone" in set(df["Point"])


def test_include_in_governing_false_prevents_point_from_governing_summary() -> None:
    custom = [
        StressCheckPoint(
            name="Non-Governing",
            x_mm=0.0,
            y_mm=250.0,
            include_in_governing=False,
        )
    ]

    summary = run_elastic_sls_stress_check(
        _analysis_input(),
        ServiceabilitySettings(concrete_tension_limit_MPa=1.0),
        custom_stress_check_points=custom,
        include_default_stress_check_points=False,
    )

    assert summary.stress_results
    assert summary.overall_status == "NOT_CHECKED"
    assert summary.governing_point is None


def test_critical_point_filter_extreme_fibers_only_excludes_custom_non_extreme_from_governing() -> None:
    custom = [
        StressCheckPoint(
            name="Custom Tension",
            x_mm=0.0,
            y_mm=250.0,
            point_type="custom",
            include_in_governing=True,
        )
    ]

    summary = run_elastic_sls_stress_check(
        _analysis_input(LoadCase(name="SLS-01", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS")),
        ServiceabilitySettings(critical_point_filter="extreme_fibers_only", concrete_tension_limit_MPa=1.0),
        custom_stress_check_points=custom,
    )

    assert any(result.point_name == "Custom Tension" for result in summary.stress_results)
    assert summary.governing_point != "Custom Tension"


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
