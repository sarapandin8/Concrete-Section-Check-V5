from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from concrete_pmm_pro.core.models import LoadCase, Point2D, SectionGeometry
from concrete_pmm_pro.reporting import (
    ReportFigureContext,
    build_exportable_figure,
    build_report_figure_context,
    build_report_manifest,
    collect_report_figure_export_items,
    plotly_figure_to_html_bytes,
    plotly_figure_to_png_bytes,
    report_figure_export_items_to_dataframe,
    report_manifest_to_json_dict,
    safe_report_figure_filename,
)
from concrete_pmm_pro.reporting.report_figures import _find_dataframe_in_session, _find_moment_columns, _has_columns
from concrete_pmm_pro.serviceability import ServiceStressPointResult, ServiceabilitySettings, ServiceabilitySummary


def _simple_serviceability_summary() -> ServiceabilitySummary:
    return ServiceabilitySummary(
        enabled=True,
        settings=ServiceabilitySettings(enabled=True),
        section_properties=None,
        sls_load_cases=[LoadCase(name="SLS Service 1", load_type="SLS")],
        stress_results=[
            ServiceStressPointResult(
                combo_name="SLS Service 1",
                point_name="Top fiber",
                x_mm=0.0,
                y_mm=300.0,
                stress_MPa=1.2,
                total_stress_MPa=1.2,
                external_stress_MPa=1.2,
                prestress_stress_MPa=0.0,
                stress_type="Tension",
                status="PASS",
                utilization=0.6,
                message="Tension stress within allowable limit.",
            ),
            ServiceStressPointResult(
                combo_name="SLS Service 1",
                point_name="Bottom fiber",
                x_mm=0.0,
                y_mm=-300.0,
                stress_MPa=-1.2,
                total_stress_MPa=-1.2,
                external_stress_MPa=-1.2,
                prestress_stress_MPa=0.0,
                stress_type="Compression",
                status="PASS",
                utilization=0.2,
                message="Compression stress within allowable limit.",
            ),
        ],
        overall_status="PASS",
        governing_combo="SLS Service 1",
        section_basis_used="gross",
    )


def _simple_section() -> SectionGeometry:
    return SectionGeometry(
        outer_polygon=[
            Point2D(x=-200.0, y=-300.0),
            Point2D(x=200.0, y=-300.0),
            Point2D(x=200.0, y=300.0),
            Point2D(x=-200.0, y=300.0),
        ]
    )


def test_report_figure_context_default_creation() -> None:
    context = ReportFigureContext()

    assert context.pmm_result_available is False
    assert context.sls_result_available is False


def test_requirements_include_kaleido_for_plotly_png_export() -> None:
    requirements_text = Path("requirements.txt").read_text(encoding="utf-8")

    assert "plotly>=5.22,<6" in requirements_text
    assert "kaleido==0.2.1" in requirements_text


def test_build_report_figure_context_empty_state() -> None:
    context = build_report_figure_context({})

    assert context.selected_uls_combo is None
    assert context.selected_sls_combo is None


def test_collect_report_figure_export_items_empty_state() -> None:
    items = collect_report_figure_export_items({})

    assert items
    assert all(item.available is False for item in items)


def test_collect_report_figure_export_items_includes_standard_keys() -> None:
    keys = {item.figure_key for item in collect_report_figure_export_items({})}

    assert {"section_geometry_layout", "pmm_interaction_surface", "sls_section_stress_points"}.issubset(keys)


def test_sls_figure_items_available_with_serviceability_summary() -> None:
    items = collect_report_figure_export_items({"serviceability_summary": _simple_serviceability_summary()})
    by_key = {item.figure_key: item for item in items}

    assert by_key["sls_section_stress_points"].available is True
    assert by_key["sls_stress_bar_diagram"].available is True


def test_sls_stress_visualization_is_not_export_ready() -> None:
    items = collect_report_figure_export_items({"serviceability_summary": _simple_serviceability_summary()})
    by_key = {item.figure_key: item for item in items}

    assert by_key["sls_stress_visualization"].export_ready is False


def test_sls_stress_bar_diagram_export_ready_with_sls_data() -> None:
    items = collect_report_figure_export_items({"serviceability_summary": _simple_serviceability_summary()})
    by_key = {item.figure_key: item for item in items}

    assert by_key["sls_stress_bar_diagram"].export_ready is True


def test_export_ready_figure_keys_do_not_duplicate_sls_bar_chart() -> None:
    items = collect_report_figure_export_items({"serviceability_summary": _simple_serviceability_summary()})
    export_ready = {item.figure_key for item in items if item.export_ready}

    assert "sls_stress_bar_diagram" in export_ready
    assert "sls_stress_visualization" not in export_ready


def test_pmm_figure_items_available_with_pmm_result() -> None:
    items = collect_report_figure_export_items({"pmm_result": SimpleNamespace(points=[object()])})
    by_key = {item.figure_key: item for item in items}

    assert by_key["pmm_interaction_surface"].available is True


def test_pmm_figure_limitations_use_guarded_production_preview_wording() -> None:
    items = collect_report_figure_export_items({"pmm_result": SimpleNamespace(points=[object()])})
    pmm_item = next(item for item in items if item.figure_key == "pmm_interaction_surface")
    text = " ".join(pmm_item.limitations)

    assert "finalized production-preview review only within the validated RC scope" in text
    assert "fallback capacity methods remain engineering-review items" in text
    assert "prototype engineering review tools" not in text


def test_pmm_interaction_surface_not_export_ready_without_dashboard_figure() -> None:
    items = collect_report_figure_export_items({"pmm_result": SimpleNamespace(points=[object()])})
    by_key = {item.figure_key: item for item in items}

    assert by_key["pmm_interaction_surface"].available is True
    assert by_key["pmm_interaction_surface"].export_ready is False


def test_pmm_interaction_surface_export_ready_with_stored_dashboard_figure() -> None:
    items = collect_report_figure_export_items(
        {"pmm_interaction_surface_figure": go.Figure(data=[go.Scatter3d(x=[0, 1], y=[0, 1], z=[0, 1])])}
    )
    by_key = {item.figure_key: item for item in items}

    assert by_key["pmm_interaction_surface"].available is True
    assert by_key["pmm_interaction_surface"].export_ready is True


def test_pmm_mux_muy_slice_export_ready_with_slice_dataframe() -> None:
    df = pd.DataFrame({"Mnx_kNm": [0.0, 10.0], "Mny_kNm": [0.0, 20.0]})
    items = collect_report_figure_export_items({"selected_pmm_slice": df})
    by_key = {item.figure_key: item for item in items}

    assert by_key["pmm_mux_muy_slice"].available is True
    assert by_key["pmm_mux_muy_slice"].export_ready is True


def test_pmm_slice_envelope_export_ready_with_envelope_dataframe() -> None:
    df = pd.DataFrame({"phiMnx_kNm": [0.0, 10.0], "phiMny_kNm": [0.0, 20.0]})
    items = collect_report_figure_export_items({"selected_slice_envelope": df})
    by_key = {item.figure_key: item for item in items}

    assert by_key["pmm_slice_envelope"].available is True
    assert by_key["pmm_slice_envelope"].export_ready is True


def test_safe_report_figure_filename_sanitizes_spaces_and_symbols() -> None:
    assert safe_report_figure_filename("SLS Stress Points!", "SLS Service #1", "PNG") == "sls_stress_points_sls_service_1.png"


def test_safe_report_figure_filename_includes_context_label() -> None:
    assert safe_report_figure_filename("pmm_mux_muy_slice", "governing uls") == "pmm_mux_muy_slice_governing_uls.png"


def test_report_figure_export_items_to_dataframe_contains_required_columns() -> None:
    df = report_figure_export_items_to_dataframe(collect_report_figure_export_items({}))

    assert {
        "Figure Key",
        "Title",
        "Available",
        "Export Ready",
        "Figure Type",
        "Source",
        "Selected Context",
        "PNG Filename",
        "HTML Filename",
        "Recommended",
        "Description",
        "Warning",
        "Limitations",
    }.issubset(df.columns)


def test_plotly_figure_to_html_bytes_returns_bytes() -> None:
    data = plotly_figure_to_html_bytes(go.Figure(data=[go.Bar(x=["A"], y=[1])]))

    assert isinstance(data, bytes)
    assert b"html" in data.lower()


def test_plotly_figure_to_png_bytes_returns_bytes_or_warning() -> None:
    data, warnings = plotly_figure_to_png_bytes(go.Figure(data=[go.Bar(x=["A"], y=[1])]))

    assert data is not None or warnings


def test_build_exportable_figure_returns_none_when_data_missing() -> None:
    fig, warnings = build_exportable_figure("sls_stress_bar_diagram", {})

    assert fig is None
    assert warnings


def test_build_exportable_figure_builds_sls_stress_bar() -> None:
    fig, warnings = build_exportable_figure(
        "sls_stress_bar_diagram",
        {"serviceability_summary": _simple_serviceability_summary()},
    )

    assert fig is not None
    assert not warnings


def test_build_exportable_figure_sls_visualization_returns_non_duplicate_warning() -> None:
    fig, warnings = build_exportable_figure(
        "sls_stress_visualization",
        {"serviceability_summary": _simple_serviceability_summary()},
    )

    assert fig is None
    assert any("represented by exportable figures" in warning for warning in warnings)


def test_build_exportable_figure_builds_sls_section_stress_points() -> None:
    fig, warnings = build_exportable_figure(
        "sls_section_stress_points",
        {"serviceability_summary": _simple_serviceability_summary(), "section_geometry": _simple_section()},
    )

    assert fig is not None
    assert not warnings


def test_build_exportable_figure_builds_pmm_mux_muy_slice() -> None:
    fig, warnings = build_exportable_figure(
        "pmm_mux_muy_slice",
        {"selected_pmm_slice": pd.DataFrame({"Mux_kNm": [0.0, 10.0], "Muy_kNm": [0.0, 20.0]})},
    )

    assert fig is not None
    assert not warnings


def test_build_exportable_figure_builds_pmm_slice_envelope() -> None:
    fig, warnings = build_exportable_figure(
        "pmm_slice_envelope",
        {"selected_slice_envelope": pd.DataFrame({"phiMnx_kNm": [0.0, 10.0], "phiMny_kNm": [0.0, 20.0]})},
    )

    assert fig is not None
    assert not warnings


def test_build_exportable_figure_pmm_overlay_warns_without_demand_point() -> None:
    fig, warnings = build_exportable_figure(
        "pmm_demand_capacity_overlay",
        {"selected_slice_envelope": pd.DataFrame({"phiMnx_kNm": [0.0, 10.0], "phiMny_kNm": [0.0, 20.0]})},
    )

    assert fig is None
    assert any("demand point" in warning for warning in warnings)


def test_pmm_figure_export_does_not_trigger_solver_recalculation(monkeypatch) -> None:
    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("solver should not be called")

    monkeypatch.setattr("concrete_pmm_pro.analysis.pmm_solver.run_rc_pmm_solver", _raise_if_called)
    fig, warnings = build_exportable_figure(
        "pmm_mux_muy_slice",
        {"selected_pmm_slice": pd.DataFrame({"Mnx_kNm": [0.0, 10.0], "Mny_kNm": [0.0, 20.0]})},
    )

    assert fig is not None
    assert not warnings


def test_missing_pmm_dataframe_columns_return_warning() -> None:
    fig, warnings = build_exportable_figure("pmm_mux_muy_slice", {"selected_pmm_slice": pd.DataFrame({"a": [1.0]})})

    assert fig is None
    assert any("missing recognizable" in warning for warning in warnings)


def test_find_dataframe_in_session_uses_candidate_keys() -> None:
    df = pd.DataFrame({"x": [1.0], "y": [2.0]})

    assert _find_dataframe_in_session({"candidate": df}, ["missing", "candidate"]) is df


def test_has_columns_checks_required_columns() -> None:
    assert _has_columns(pd.DataFrame({"x": [1], "y": [2]}), {"x", "y"}) is True


def test_find_moment_columns_finds_mnx_mny() -> None:
    assert _find_moment_columns(pd.DataFrame({"Mnx_kNm": [1.0], "Mny_kNm": [2.0]})) == ("Mnx_kNm", "Mny_kNm")


def test_find_moment_columns_returns_none_for_missing_data() -> None:
    assert _find_moment_columns(pd.DataFrame({"a": [1.0], "b": [2.0]})) == (None, None)


def test_report_manifest_includes_figure_context() -> None:
    manifest = build_report_manifest({})

    assert manifest.figure_context is not None


def test_report_manifest_includes_figure_export_items() -> None:
    manifest = build_report_manifest({})

    assert manifest.figure_export_items


def test_report_manifest_to_json_dict_remains_serializable() -> None:
    data = report_manifest_to_json_dict(build_report_manifest({"serviceability_summary": _simple_serviceability_summary()}))

    json.dumps(data)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")


def test_project_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.project_page as project_page

    assert hasattr(project_page, "render_project_page")
