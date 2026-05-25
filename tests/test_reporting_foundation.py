from __future__ import annotations

from types import SimpleNamespace

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.models import ConcreteMaterial
from concrete_pmm_pro.geometry.generators import rectangle
from concrete_pmm_pro.reporting import (
    build_result_traceability_snapshot,
    check_report_readiness,
    collect_available_report_figures,
    collect_engineering_warnings,
    deduplicate_preserve_order,
    get_standard_terminology,
    get_unit_conventions,
    report_figures_to_dataframe,
    report_readiness_to_dataframe,
    result_traceability_snapshot_to_dataframe,
    terminology_to_dataframe,
    unit_conventions_to_dataframe,
)


def test_get_standard_terminology_contains_core_terms() -> None:
    terms = get_standard_terminology()

    for key in ("Pu", "Mux", "Muy", "Pe_eff", "No-Tension"):
        assert key in terms


def test_terminology_to_dataframe_contains_required_columns() -> None:
    df = terminology_to_dataframe()

    assert {"Key", "Label", "Description", "Unit", "Category"}.issubset(df.columns)
    assert not df.empty


def test_get_unit_conventions_contains_core_quantities() -> None:
    quantities = {item.quantity for item in get_unit_conventions()}

    assert {"Force", "Moment", "Stress", "Length"}.issubset(quantities)


def test_unit_conventions_to_dataframe_contains_required_columns() -> None:
    df = unit_conventions_to_dataframe()

    assert {"Quantity", "Internal Unit", "Display Unit", "Report Unit", "Conversion Note"}.issubset(df.columns)
    assert not df.empty


def test_deduplicate_preserve_order_removes_duplicates() -> None:
    assert deduplicate_preserve_order(["A", "B", "A", "", "C", "B"]) == ["A", "B", "C"]


def test_collect_engineering_warnings_tolerates_missing_objects() -> None:
    warnings = collect_engineering_warnings()

    assert isinstance(warnings, list)


def test_collect_engineering_warnings_includes_beam_girder_warning() -> None:
    warnings = collect_engineering_warnings(
        analysis_mode_settings=AnalysisModeSettings(member_type="beam_girder")
    )

    assert any("Beam/Girder design checks are not implemented" in warning for warning in warnings)
    assert any("double-count prestress" in warning for warning in warnings)


def test_build_result_traceability_snapshot_empty_session() -> None:
    snapshot = build_result_traceability_snapshot({})

    assert snapshot.section_available is False
    assert snapshot.materials_available is False
    assert snapshot.pmm_result_available is False
    assert snapshot.sls_result_available is False


def test_build_result_traceability_snapshot_detects_pmm_result() -> None:
    session = {
        "rc_pmm_result": SimpleNamespace(points=[SimpleNamespace(unbonded_prestress_ignored_count=0)], warnings=[]),
    }

    snapshot = build_result_traceability_snapshot(session)

    assert snapshot.pmm_result_available is True
    assert snapshot.pmm_point_count == 1


def test_build_result_traceability_snapshot_detects_serviceability_summary() -> None:
    serviceability_summary = SimpleNamespace(
        stress_results=[object()],
        overall_status="PASS",
        governing_combo="SLS-1",
        governing_point="Top fiber",
        max_utilization=0.5,
        section_basis_used="gross",
        prestress_included=False,
        warnings=[],
    )

    snapshot = build_result_traceability_snapshot({"serviceability_summary": serviceability_summary})

    assert snapshot.sls_result_available is True
    assert snapshot.sls_overall_status == "PASS"
    assert snapshot.governing_sls_combo == "SLS-1"


def test_result_traceability_snapshot_to_dataframe_returns_non_empty() -> None:
    snapshot = build_result_traceability_snapshot({})
    df = result_traceability_snapshot_to_dataframe(snapshot)

    assert {"Item", "Value"}.issubset(df.columns)
    assert not df.empty


def test_check_report_readiness_returns_not_ready_for_empty_snapshot() -> None:
    summary = check_report_readiness(build_result_traceability_snapshot({}))

    assert summary.overall_status == "NOT_READY"


def test_check_report_readiness_partial_or_ready_with_section_materials_and_sls() -> None:
    serviceability_summary = SimpleNamespace(stress_results=[object()], overall_status="PASS", warnings=[])
    snapshot = build_result_traceability_snapshot(
        {
            "section_geometry": rectangle(width_mm=400.0, height_mm=600.0),
            "concrete_material": ConcreteMaterial(),
            "serviceability_summary": serviceability_summary,
        }
    )

    summary = check_report_readiness(snapshot)

    assert summary.overall_status in {"PARTIAL", "READY"}


def test_report_readiness_to_dataframe_contains_required_columns() -> None:
    summary = check_report_readiness(build_result_traceability_snapshot({}))
    df = report_readiness_to_dataframe(summary)

    assert {"Category", "Item", "Status", "Message"}.issubset(df.columns)


def test_collect_available_report_figures_empty_session() -> None:
    figures = collect_available_report_figures({})

    assert figures
    assert not any(figure.available for figure in figures)


def test_collect_available_report_figures_detects_pmm_result() -> None:
    figures = collect_available_report_figures({"rc_pmm_result": object()})

    assert any(figure.figure_key == "pmm_dashboard" and figure.available for figure in figures)


def test_collect_available_report_figures_detects_serviceability_summary() -> None:
    figures = collect_available_report_figures({"serviceability_summary": object()})

    assert any(figure.figure_key == "sls_stress_visualization" and figure.available for figure in figures)


def test_report_figures_to_dataframe_contains_required_columns() -> None:
    df = report_figures_to_dataframe(collect_available_report_figures({}))

    assert {"Figure Key", "Title", "Available", "Source", "Recommended", "Description", "Warning"}.issubset(df.columns)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")


def test_project_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.project_page as project_page

    assert hasattr(project_page, "render_project_page")
