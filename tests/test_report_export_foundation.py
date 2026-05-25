from __future__ import annotations

import json
from types import SimpleNamespace

from concrete_pmm_pro.reporting import (
    ReportSection,
    build_report_manifest,
    collect_available_report_figures,
    collect_available_report_tables,
    default_report_metadata,
    default_report_section_plan,
    generate_plain_text_report_outline,
    get_engineering_limitations,
    report_figures_to_dataframe,
    report_manifest_to_json_dict,
    report_manifest_to_summary_dataframe,
    report_sections_to_dataframe,
    report_tables_to_dataframe,
)
from concrete_pmm_pro.reporting.readiness import check_report_readiness
from concrete_pmm_pro.reporting.traceability import build_result_traceability_snapshot


def test_default_report_metadata_creates_sensible_defaults() -> None:
    metadata = default_report_metadata("Bridge Pier A")

    assert metadata.report_title == "Concrete PMM Pro Engineering Report"
    assert metadata.project_name == "Bridge Pier A"
    assert metadata.revision == "Draft"


def test_report_section_validates_required_fields() -> None:
    section = ReportSection(section_id="summary", title="Executive Summary")

    assert section.section_id == "summary"
    assert section.status == "AVAILABLE"


def test_default_report_section_plan_includes_warnings_and_limitations() -> None:
    snapshot = build_result_traceability_snapshot({})
    readiness = check_report_readiness(snapshot)
    figures = collect_available_report_figures({})
    limitations = get_engineering_limitations()
    sections = default_report_section_plan(snapshot, readiness, figures, limitations)

    assert any(section.section_id == "warnings_limitations" for section in sections)


def test_default_report_section_plan_marks_uls_missing_without_pmm() -> None:
    snapshot = build_result_traceability_snapshot({})
    sections = default_report_section_plan(snapshot, check_report_readiness(snapshot), [], get_engineering_limitations())
    by_id = {section.section_id: section for section in sections}

    assert by_id["uls_pmm_strength"].status == "MISSING"


def test_default_report_section_plan_marks_sls_missing_without_sls() -> None:
    snapshot = build_result_traceability_snapshot({})
    sections = default_report_section_plan(snapshot, check_report_readiness(snapshot), [], get_engineering_limitations())
    by_id = {section.section_id: section for section in sections}

    assert by_id["sls_stress_check"].status == "MISSING"


def test_collect_available_report_tables_returns_standard_tables() -> None:
    keys = {table.table_key for table in collect_available_report_tables({})}

    assert {
        "result_traceability_snapshot",
        "report_readiness",
        "engineering_warnings",
        "engineering_limitations",
        "unit_conventions",
        "terminology",
    }.issubset(keys)


def test_collect_available_report_tables_detects_serviceability_summary() -> None:
    serviceability = SimpleNamespace(stress_results=[object()])
    tables = collect_available_report_tables({"serviceability_summary": serviceability})
    by_key = {table.table_key: table for table in tables}

    assert by_key["sls_stress_results"].available is True


def test_collect_available_report_tables_detects_pmm_result() -> None:
    tables = collect_available_report_tables({"pmm_result": SimpleNamespace(points=[object(), object()])})
    by_key = {table.table_key: table for table in tables}

    assert by_key["pmm_summary"].available is True


def test_report_tables_to_dataframe_contains_required_columns() -> None:
    df = report_tables_to_dataframe(collect_available_report_tables({}))

    assert {"Table Key", "Title", "Available", "Source", "Recommended", "Row Count", "Description", "Warning"}.issubset(df.columns)


def test_collect_available_report_figures_empty_state_returns_registry() -> None:
    figures = collect_available_report_figures({})

    assert figures
    assert all(figure.available is False for figure in figures)


def test_collect_available_report_figures_detects_serviceability_summary() -> None:
    figures = collect_available_report_figures({"serviceability_summary": SimpleNamespace(stress_results=[object()])})
    by_key = {figure.figure_key: figure for figure in figures}

    assert by_key["sls_section_stress_points"].available is True
    assert by_key["sls_stress_bar_diagram"].available is True


def test_collect_available_report_figures_detects_pmm_result() -> None:
    figures = collect_available_report_figures({"pmm_result": SimpleNamespace(points=[object()])})
    by_key = {figure.figure_key: figure for figure in figures}

    assert by_key["pmm_interaction_surface"].available is True


def test_report_figures_to_dataframe_contains_required_columns() -> None:
    df = report_figures_to_dataframe(collect_available_report_figures({}))

    assert {"Figure Key", "Title", "Available", "Source", "Recommended", "Description", "Warning"}.issubset(df.columns)


def test_build_report_manifest_works_with_empty_session_state() -> None:
    manifest = build_report_manifest({})

    assert manifest.generated_status == "FOUNDATION_ONLY"
    assert manifest.sections


def test_build_report_manifest_includes_traceability_snapshot() -> None:
    manifest = build_report_manifest({})

    assert manifest.traceability_snapshot is not None


def test_build_report_manifest_includes_readiness_summary() -> None:
    manifest = build_report_manifest({})

    assert manifest.readiness_summary.overall_status == "NOT_READY"


def test_build_report_manifest_includes_engineering_limitations() -> None:
    manifest = build_report_manifest({})

    assert len(manifest.engineering_limitations) == len(get_engineering_limitations())


def test_build_report_manifest_includes_unit_conventions() -> None:
    manifest = build_report_manifest({})

    assert any(unit.quantity == "Force" for unit in manifest.unit_conventions)


def test_build_report_manifest_includes_terminology() -> None:
    manifest = build_report_manifest({})

    assert any(term.key == "Pu" for term in manifest.terminology)


def test_build_report_manifest_does_not_trigger_solver_recalculation(monkeypatch) -> None:
    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("solver should not be called")

    monkeypatch.setattr("concrete_pmm_pro.analysis.pmm_solver.run_rc_pmm_solver", _raise_if_called)

    manifest = build_report_manifest({})

    assert manifest.generated_status == "FOUNDATION_ONLY"


def test_report_manifest_to_summary_dataframe_returns_non_empty_dataframe() -> None:
    df = report_manifest_to_summary_dataframe(build_report_manifest({}))

    assert not df.empty
    assert {"Item", "Value"}.issubset(df.columns)


def test_report_manifest_to_json_dict_is_json_serializable() -> None:
    data = report_manifest_to_json_dict(build_report_manifest({}))

    json.dumps(data)


def test_report_sections_to_dataframe_contains_required_columns() -> None:
    manifest = build_report_manifest({})
    df = report_sections_to_dataframe(manifest.sections)

    assert {"Section ID", "Title", "Level", "Include", "Status", "Summary", "Tables", "Figures", "Limitations", "Warnings"}.issubset(df.columns)


def test_generate_plain_text_report_outline_includes_readiness_status() -> None:
    outline = generate_plain_text_report_outline(build_report_manifest({}))

    assert "Readiness Status" in outline


def test_generate_plain_text_report_outline_includes_limitations_count() -> None:
    outline = generate_plain_text_report_outline(build_report_manifest({}))

    assert "Limitations Count" in outline


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")


def test_project_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.project_page as project_page

    assert hasattr(project_page, "render_project_page")
