from __future__ import annotations

import plotly.graph_objects as go

from concrete_pmm_pro.core.analysis import AnalysisInput
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.serviceability import (
    ServiceabilitySettings,
    StressCheckPoint,
    classify_service_stress_results_for_cracking,
    run_elastic_sls_stress_check,
)
from concrete_pmm_pro.visualization.sls_stress import (
    crack_classification_for_combo,
    make_sls_section_stress_figure,
    make_sls_stress_bar_figure,
    service_stress_results_for_combo,
    service_stress_results_to_plot_dataframe,
    sls_status_color,
)


def _analysis_input() -> AnalysisInput:
    return AnalysisInput(
        section_geometry=rectangle(width_mm=400.0, height_mm=600.0),
        concrete_material=ConcreteMaterial(name="C40", fc_MPa=40.0),
        load_cases=[
            LoadCase(name="SLS-MX", Pu_N=0.0, Mux_Nmm=100_000_000.0, Muy_Nmm=0.0, load_type="SLS"),
            LoadCase(name="SLS-MY", Pu_N=0.0, Mux_Nmm=0.0, Muy_Nmm=100_000_000.0, load_type="SLS"),
        ],
    )


def _summary(settings: ServiceabilitySettings | None = None, custom_points: list[StressCheckPoint] | None = None):
    return run_elastic_sls_stress_check(
        _analysis_input(),
        settings or ServiceabilitySettings(concrete_tension_limit_MPa=10.0),
        custom_stress_check_points=custom_points,
    )


def test_service_stress_results_for_combo_filters_results() -> None:
    summary = _summary()

    results = service_stress_results_for_combo(summary, "SLS-MX")

    assert results
    assert {result.combo_name for result in results} == {"SLS-MX"}


def test_crack_classification_for_combo_filters_results() -> None:
    summary = _summary()
    crack_summary = classify_service_stress_results_for_cracking(summary, summary.settings)

    points = crack_classification_for_combo(crack_summary, "SLS-MX")

    assert points
    assert {point.combo_name for point in points} == {"SLS-MX"}


def test_service_stress_results_to_plot_dataframe_includes_required_columns() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary)

    assert {
        "Combo",
        "Point",
        "x_mm",
        "y_mm",
        "Stress_MPa",
        "External Stress_MPa",
        "Prestress Stress_MPa",
        "Total Stress_MPa",
        "Stress Type",
        "Status",
        "Utilization",
        "Section Basis",
        "Point Type",
        "Source",
        "Include in Governing",
        "Crack Classification",
        "Is Tension",
        "No-Tension Violation",
        "Decompression Violation",
        "Message",
    }.issubset(df.columns)


def test_service_stress_results_to_plot_dataframe_filters_selected_combo() -> None:
    summary = _summary()

    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MY")

    assert set(df["Combo"]) == {"SLS-MY"}


def test_service_stress_results_to_plot_dataframe_merges_crack_classification() -> None:
    summary = _summary(ServiceabilitySettings(concrete_tension_limit_MPa=1.0))
    crack_summary = classify_service_stress_results_for_cracking(summary, summary.settings)

    df = service_stress_results_to_plot_dataframe(summary, crack_summary, combo_name="SLS-MX")

    assert "TENSION_EXCEEDS_LIMIT" in set(df["Crack Classification"].dropna())


def test_sls_status_color_returns_value_for_pass() -> None:
    assert sls_status_color("PASS", "Compression")


def test_sls_status_color_returns_value_for_fail() -> None:
    assert sls_status_color("FAIL", "Tension") == "#dc2626"


def test_make_sls_section_stress_figure_returns_plotly_figure_for_simple_section() -> None:
    summary = _summary()
    crack_summary = classify_service_stress_results_for_cracking(summary, summary.settings)
    df = service_stress_results_to_plot_dataframe(summary, crack_summary, "SLS-MX")

    fig = make_sls_section_stress_figure(_analysis_input().section_geometry, df, "SLS-MX")

    assert isinstance(fig, go.Figure)


def test_make_sls_section_stress_figure_includes_stress_check_point_markers() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX")

    fig = make_sls_section_stress_figure(_analysis_input().section_geometry, df, "SLS-MX")

    assert any(trace.name == "SLS stress points" for trace in fig.data)


def test_make_sls_section_stress_figure_handles_empty_stress_df_safely() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX").iloc[0:0]

    fig = make_sls_section_stress_figure(_analysis_input().section_geometry, df, "SLS-MX")

    assert isinstance(fig, go.Figure)


def test_make_sls_stress_bar_figure_returns_plotly_figure() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX")

    fig = make_sls_stress_bar_figure(df, "SLS-MX")

    assert isinstance(fig, go.Figure)


def test_make_sls_stress_bar_figure_includes_zero_stress_line() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX")

    fig = make_sls_stress_bar_figure(df, "SLS-MX")

    assert fig.layout.shapes


def test_custom_stress_check_point_appears_in_plot_dataframe() -> None:
    custom = [StressCheckPoint(name="Tendon Zone", x_mm=0.0, y_mm=120.0, point_type="tendon_zone")]
    summary = _summary(custom_points=custom)

    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX")

    assert "Tendon Zone" in set(df["Point"])
    assert "tendon_zone" in set(df["Point Type"].dropna())


def test_no_tension_violation_appears_in_plot_dataframe_classification() -> None:
    summary = _summary(ServiceabilitySettings(no_tension_check=True))
    crack_summary = classify_service_stress_results_for_cracking(summary, summary.settings)

    df = service_stress_results_to_plot_dataframe(summary, crack_summary, "SLS-MX")

    assert df["No-Tension Violation"].any()
    assert "NO_TENSION_VIOLATION" in set(df["Crack Classification"].dropna())


def test_decompression_violation_appears_in_plot_dataframe_classification() -> None:
    summary = _summary(ServiceabilitySettings(decompression_check=True))
    crack_summary = classify_service_stress_results_for_cracking(summary, summary.settings)

    df = service_stress_results_to_plot_dataframe(summary, crack_summary, "SLS-MX")

    assert df["Decompression Violation"].any()
    assert "DECOMPRESSION_VIOLATION" in set(df["Crack Classification"].dropna())


def test_visualization_csv_dataframe_can_be_converted_to_csv() -> None:
    summary = _summary()
    df = service_stress_results_to_plot_dataframe(summary, combo_name="SLS-MX")

    csv_text = df.to_csv(index=False)

    assert "Total Stress_MPa" in csv_text


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
