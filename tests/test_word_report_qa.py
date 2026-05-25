from __future__ import annotations

from dataclasses import replace
from io import BytesIO

from docx import Document

from concrete_pmm_pro.reporting import build_report_manifest
from concrete_pmm_pro.reporting.limitations import EngineeringLimitation
from concrete_pmm_pro.reporting.report_qa import (
    extract_docx_headings,
    extract_docx_text,
    report_qa_summary_to_dataframe,
    run_word_report_qa,
    validate_draft_disclaimer,
    validate_engineering_limitations_present,
    validate_engineering_warnings_present,
    validate_no_misleading_certification_language,
    validate_report_tables_and_figures_present,
    validate_required_report_headings,
    validate_terminology_present,
    validate_traceability_and_readiness_present,
    validate_unit_conventions_present,
)
from concrete_pmm_pro.reporting.word_export import build_draft_word_report


def _docx_with_paragraphs(*paragraphs: str) -> bytes:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _generated_report():
    manifest = build_report_manifest({})
    return manifest, build_draft_word_report(manifest)


def _statuses(items):
    return {item.status for item in items}


def test_extract_docx_text_returns_text_from_generated_report() -> None:
    _, report_bytes = _generated_report()

    text = extract_docx_text(report_bytes)

    assert "Concrete PMM Pro Engineering Report" in text
    assert "Engineering Limitations" in text


def test_extract_docx_headings_returns_expected_headings() -> None:
    _, report_bytes = _generated_report()

    headings = extract_docx_headings(report_bytes)

    assert "Executive Summary" in headings
    assert "Engineering Limitations" in headings


def test_validate_required_report_headings_passes_for_generated_report() -> None:
    _, report_bytes = _generated_report()

    items = validate_required_report_headings(report_bytes)

    assert all(item.status == "PASS" for item in items)


def test_validate_draft_disclaimer_passes_for_generated_report() -> None:
    _, report_bytes = _generated_report()

    assert validate_draft_disclaimer(report_bytes).status == "PASS"


def test_validate_draft_disclaimer_fails_for_docx_without_disclaimer() -> None:
    report_bytes = _docx_with_paragraphs("Engineering report", "Final calculations")

    assert validate_draft_disclaimer(report_bytes).status == "FAIL"


def test_validate_engineering_limitations_present_passes_when_limitations_are_present() -> None:
    manifest, report_bytes = _generated_report()

    items = validate_engineering_limitations_present(report_bytes, manifest)

    assert "FAIL" not in _statuses(items)


def test_validate_engineering_limitations_present_fails_if_high_limitation_missing() -> None:
    manifest, report_bytes = _generated_report()
    extra = EngineeringLimitation(
        key="missing_high_limitation",
        title="Missing high risk limitation phrase",
        status="SIMPLIFIED",
        risk_level="HIGH",
        category="SLS",
        user_note="This limitation is intentionally absent from the generated document.",
        engineering_note="QA should catch this missing high-risk item.",
    )
    mutated = replace(manifest, engineering_limitations=[*manifest.engineering_limitations, extra])

    items = validate_engineering_limitations_present(report_bytes, mutated)

    assert any(item.status == "FAIL" and item.check_name == "missing_high_limitation" for item in items)


def test_validate_engineering_warnings_present_handles_empty_warnings() -> None:
    manifest, report_bytes = _generated_report()

    items = validate_engineering_warnings_present(report_bytes, manifest)

    assert "FAIL" not in _statuses(items)


def test_validate_engineering_warnings_present_detects_non_empty_warnings() -> None:
    manifest = replace(build_report_manifest({}), engineering_warnings=["Review prototype limitations before issuing."])
    report_bytes = build_draft_word_report(manifest)

    items = validate_engineering_warnings_present(report_bytes, manifest)

    assert any(item.status == "PASS" and item.check_name == "Warning details" for item in items)


def test_validate_unit_conventions_present_detects_force_moment_stress_units() -> None:
    _, report_bytes = _generated_report()

    items = validate_unit_conventions_present(report_bytes)
    names = {item.check_name: item.status for item in items}

    assert names["Force / kN"] == "PASS"
    assert names["Moment / kN-m"] == "PASS"
    assert names["Stress / MPa"] == "PASS"


def test_validate_terminology_present_detects_core_terms() -> None:
    _, report_bytes = _generated_report()

    items = validate_terminology_present(report_bytes)
    names = {item.check_name: item.status for item in items}

    assert names["Pu"] == "PASS"
    assert names["Mux"] == "PASS"
    assert names["Muy"] == "PASS"
    assert names["Pe_eff"] == "PASS"


def test_validate_traceability_and_readiness_present_passes_for_generated_report() -> None:
    manifest, report_bytes = _generated_report()

    items = validate_traceability_and_readiness_present(report_bytes, manifest)

    assert "FAIL" not in _statuses(items)


def test_validate_report_tables_and_figures_present_passes_for_generated_report() -> None:
    manifest, report_bytes = _generated_report()

    items = validate_report_tables_and_figures_present(report_bytes, manifest)

    assert "FAIL" not in _statuses(items)


def test_validate_no_misleading_certification_language_allows_negative_disclaimer() -> None:
    report_bytes = _docx_with_paragraphs("This is not a final design certification.")

    items = validate_no_misleading_certification_language(report_bytes)

    assert "FAIL" not in _statuses(items)


def test_validate_no_misleading_certification_language_fails_for_overstatement() -> None:
    report_bytes = _docx_with_paragraphs("This report is a fully validated certified design.")

    items = validate_no_misleading_certification_language(report_bytes)

    assert any(item.status == "FAIL" for item in items)


def test_run_word_report_qa_returns_summary() -> None:
    manifest, report_bytes = _generated_report()

    summary = run_word_report_qa(report_bytes, manifest)

    assert summary.items
    assert summary.pass_count > 0


def test_run_word_report_qa_normal_generated_report_has_no_failures() -> None:
    manifest, report_bytes = _generated_report()

    summary = run_word_report_qa(report_bytes, manifest)

    assert summary.overall_status in {"PASS", "WARNING"}
    assert summary.fail_count == 0


def test_report_qa_summary_to_dataframe_contains_required_columns() -> None:
    manifest, report_bytes = _generated_report()
    summary = run_word_report_qa(report_bytes, manifest)

    dataframe = report_qa_summary_to_dataframe(summary)

    assert {"Category", "Check", "Status", "Message"}.issubset(dataframe.columns)


def test_analysis_page_imports_without_error() -> None:
    import concrete_pmm_pro.ui.analysis_page as analysis_page

    assert hasattr(analysis_page, "render_analysis_page")
