"""Draft Word report export from an existing report manifest."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd
from docx import Document
from docx.document import Document as DocumentObject
from docx.shared import Inches, Pt

from concrete_pmm_pro.reporting.figure_export import plotly_figure_to_png_bytes
from concrete_pmm_pro.reporting.limitations import engineering_limitations_to_dataframe
from concrete_pmm_pro.reporting.report_figures import build_exportable_figure, report_figure_export_items_to_dataframe
from concrete_pmm_pro.reporting.report_manifest import ReportManifest, report_manifest_to_summary_dataframe
from concrete_pmm_pro.reporting.report_sections import report_sections_to_dataframe
from concrete_pmm_pro.reporting.report_tables import report_tables_to_dataframe
from concrete_pmm_pro.reporting.readiness import report_readiness_to_dataframe
from concrete_pmm_pro.reporting.terminology import terminology_to_dataframe
from concrete_pmm_pro.reporting.traceability import result_traceability_snapshot_to_dataframe
from concrete_pmm_pro.reporting.units import unit_conventions_to_dataframe


@dataclass(frozen=True)
class ReportExportOptions:
    include_appendices: bool = True
    include_figures: bool = True
    max_table_rows: int = 30
    include_full_terminology: bool = True
    include_full_registries: bool = True


def add_report_heading(document: DocumentObject, text: str, level: int = 1) -> None:
    document.add_heading(text, level=max(1, min(level, 3)))


def apply_document_defaults(document: DocumentObject) -> None:
    section = document.sections[0]
    section.page_width = Inches(8.27)
    section.page_height = Inches(11.69)
    section.top_margin = Inches(0.75)
    section.bottom_margin = Inches(0.75)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    style = document.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(10)
    style.paragraph_format.space_after = Pt(4)


def apply_heading_styles(document: DocumentObject) -> None:
    for style_name, size in [("Title", 20), ("Heading 1", 15), ("Heading 2", 12), ("Heading 3", 10)]:
        style = document.styles[style_name]
        style.font.name = "Arial"
        style.font.size = Pt(size)
        style.font.bold = True


def set_table_style(table, compact: bool = True) -> None:
    table.style = "Table Grid"
    table.autofit = True
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.font.name = "Arial"
                    run.font.size = Pt(8 if compact else 9)


def add_page_break(document: DocumentObject) -> None:
    document.add_page_break()


def add_report_footer_note(document: DocumentObject) -> None:
    for section in document.sections:
        footer = section.footer.paragraphs[0]
        footer.text = "Concrete PMM Pro draft report - prototype engineering review only"
        footer.style = document.styles["Footer"]


def add_draft_disclaimer(document: DocumentObject) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(
        "This document is a draft engineering report generated from current analysis results. "
        "It is not a final design certification."
    )
    run.bold = True


def add_key_value_table(document: DocumentObject, items, title: str | None = None) -> None:
    rows = [{"Item": key, "Value": value} for key, value in items]
    dataframe_to_word_table(document, pd.DataFrame(rows), title=title)


def _as_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def dataframe_to_word_table(
    document: DocumentObject,
    dataframe: pd.DataFrame,
    title: str | None = None,
    max_rows: int | None = None,
) -> None:
    if title:
        document.add_paragraph(title, style=None).runs[0].bold = True
    if dataframe is None or dataframe.empty:
        document.add_paragraph("No data available.")
        return
    source_rows = len(dataframe)
    display_df = dataframe.copy()
    if max_rows is not None and source_rows > max_rows:
        display_df = display_df.head(max_rows)
    table = document.add_table(rows=1, cols=len(display_df.columns))
    header_cells = table.rows[0].cells
    for index, column in enumerate(display_df.columns):
        header_cells[index].text = str(column)
        for run in header_cells[index].paragraphs[0].runs:
            run.bold = True
    for _, row in display_df.iterrows():
        cells = table.add_row().cells
        for index, column in enumerate(display_df.columns):
            cells[index].text = _as_display(row[column])
    set_table_style(table)
    if max_rows is not None and source_rows > max_rows:
        document.add_paragraph("Table truncated for draft report. Full data available from CSV export.")


def add_warning_box_or_section(document: DocumentObject, warnings: list[str], title: str) -> None:
    add_report_heading(document, title, level=2)
    if not warnings:
        document.add_paragraph("No engineering warnings recorded.")
        return
    for warning in warnings:
        document.add_paragraph(str(warning), style="List Bullet")


def add_limitations_section(document: DocumentObject, limitations) -> None:
    add_report_heading(document, "Engineering Limitations", level=1)
    ordered = sorted(
        list(limitations),
        key=lambda item: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}.get(item.risk_level, 4),
    )
    high_critical = [item for item in ordered if item.risk_level in {"HIGH", "CRITICAL"}]
    if high_critical:
        document.add_paragraph("High/Critical limitations requiring review:")
        for item in high_critical:
            document.add_paragraph(f"{item.title} ({item.risk_level})", style="List Bullet")
    dataframe = engineering_limitations_to_dataframe(ordered)
    keep_columns = ["Title", "Risk Level", "Status", "Category", "User Note", "Recommended Action"]
    dataframe_to_word_table(document, dataframe[keep_columns], max_rows=50)


def add_unit_conventions_section(document: DocumentObject, unit_conventions) -> None:
    add_report_heading(document, "Unit Conventions", level=1)
    dataframe = pd.DataFrame(
        [
            {
                "Quantity": item.quantity,
                "Internal Unit": item.internal_unit,
                "Display Unit": item.display_unit,
                "Report Unit": item.report_unit,
                "Conversion Note": item.conversion_note,
            }
            for item in unit_conventions
        ]
    )
    dataframe_to_word_table(document, dataframe if not dataframe.empty else unit_conventions_to_dataframe(), max_rows=50)


def add_terminology_section(document: DocumentObject, terminology) -> None:
    add_report_heading(document, "Standard Terminology", level=1)
    dataframe = pd.DataFrame(
        [
            {
                "Key": item.key,
                "Label": item.label,
                "Description": item.description,
                "Unit": item.unit or "",
                "Category": item.category,
            }
            for item in terminology
        ]
    )
    dataframe_to_word_table(document, dataframe if not dataframe.empty else terminology_to_dataframe(), max_rows=60)


def _add_cover(document: DocumentObject, manifest: ReportManifest) -> None:
    metadata = manifest.metadata
    document.add_heading(metadata.report_title, level=0)
    document.add_paragraph("Draft engineering report generated from current stored analysis results.")
    rows = [
        ("Project name", metadata.project_name),
        ("Organization", metadata.organization),
        ("Project number", metadata.project_number),
        ("Prepared by", metadata.prepared_by),
        ("Checked by", metadata.checked_by),
        ("Revision", metadata.revision),
        ("Report date", metadata.report_date),
        ("Draft status", "Draft / not final certification"),
        ("Note", metadata.note),
    ]
    add_key_value_table(document, rows)
    add_draft_disclaimer(document)
    add_page_break(document)


def _add_executive_summary(document: DocumentObject, manifest: ReportManifest) -> None:
    add_report_heading(document, "Executive Summary", level=1)
    snapshot = manifest.traceability_snapshot
    document.add_paragraph(
        "This is a draft engineering report generated from the current analysis results and implemented prototype checks."
    )
    summary = {
        "Readiness status": manifest.readiness_summary.overall_status,
        "Analysis mode / member type": snapshot.member_type or "",
        "ULS result available": "Yes" if snapshot.pmm_result_available else "No",
        "SLS result available": "Yes" if snapshot.sls_result_available else "No",
        "Governing ULS combo": snapshot.governing_uls_combo or "Not available",
        "Governing SLS combo": snapshot.governing_sls_combo or "Not available",
        "Governing SLS point": snapshot.governing_sls_point or "Not available",
        "Warning count": len(manifest.engineering_warnings),
        "High/Critical limitation count": len(
            [item for item in manifest.engineering_limitations if item.risk_level in {"HIGH", "CRITICAL"}]
        ),
        "Available figure count": len([figure for figure in manifest.figures if figure.available]),
    }
    dataframe_to_word_table(document, pd.DataFrame([{"Item": key, "Value": value} for key, value in summary.items()]))
    if not snapshot.pmm_result_available:
        document.add_paragraph("No ULS PMM result is currently available in the stored session.")
    if not snapshot.sls_result_available:
        document.add_paragraph("No SLS result is currently available in the stored session.")


def _add_analysis_scope(document: DocumentObject, manifest: ReportManifest) -> None:
    add_report_heading(document, "Analysis Mode and Scope", level=1)
    snapshot = manifest.traceability_snapshot
    scope_rows = [
        {"Item": "Member type", "Value": snapshot.member_type or ""},
        {"Item": "Analysis workflow", "Value": snapshot.analysis_workflow or ""},
        {"Item": "PMM workflow status", "Value": "Available" if snapshot.pmm_result_available else "Not run / not available"},
        {"Item": "SLS workflow status", "Value": "Available" if snapshot.sls_result_available else "Not run / not available"},
    ]
    dataframe_to_word_table(document, pd.DataFrame(scope_rows))
    if snapshot.member_type == "beam_girder":
        document.add_paragraph("Beam/Girder design checks are future work and are not implemented in this report.")


def _add_figures(document: DocumentObject, manifest: ReportManifest, session_state: Any | None, options: ReportExportOptions) -> None:
    add_report_heading(document, "Draft Figures", level=1)
    if not options.include_figures:
        document.add_paragraph("Figures were not included in this draft report per export options.")
        return
    export_ready_items = [item for item in manifest.figure_export_items if item.export_ready]
    if not export_ready_items:
        document.add_paragraph("No export-ready figures are currently available.")
        return
    for index, item in enumerate(export_ready_items, start=1):
        add_report_heading(document, f"Figure {index} - {item.title}", level=2)
        if item.selected_context:
            document.add_paragraph(f"Selected context: {item.selected_context}")
        document.add_paragraph(f"Figure source: {item.source}")
        if item.limitations:
            document.add_paragraph("Limitations: " + "; ".join(item.limitations))
        fig, figure_warnings = build_exportable_figure(item.figure_key, session_state or {}, manifest.figure_context)
        if fig is None:
            document.add_paragraph("[Figure not embedded: source data is unavailable.]")
            for warning in figure_warnings:
                document.add_paragraph(str(warning), style="List Bullet")
            continue
        png_bytes, png_warnings = plotly_figure_to_png_bytes(fig)
        if png_bytes:
            document.add_picture(BytesIO(png_bytes), width=Inches(6.4))
            document.add_paragraph(f"Figure {index} - {item.title}")
        else:
            document.add_paragraph("[Figure not embedded: PNG export unavailable. HTML export remains available from the application.]")
            for warning in [*figure_warnings, *png_warnings]:
                document.add_paragraph(str(warning), style="List Bullet")


def _add_generation_notes(document: DocumentObject, manifest: ReportManifest) -> None:
    add_report_heading(document, "Report Generation Notes", level=1)
    rows = [
        ("Generated status", manifest.generated_status),
        ("Data source", "Stored session results and report manifest"),
        ("Solver recalculation", "No solver recalculation during report export"),
        ("Word report status", "Draft engineering report"),
        ("PDF export", "Future work"),
        ("Calculation changes", "Report generation does not change PMM/SLS calculations"),
    ]
    add_key_value_table(document, rows)


def build_draft_word_report(
    manifest: ReportManifest,
    session_state: Any | None = None,
    options: ReportExportOptions | None = None,
) -> bytes:
    options = options or ReportExportOptions()
    document = Document()
    apply_document_defaults(document)
    apply_heading_styles(document)
    add_report_footer_note(document)
    _add_cover(document, manifest)
    _add_executive_summary(document, manifest)
    _add_analysis_scope(document, manifest)

    add_report_heading(document, "Result Traceability Snapshot", level=1)
    dataframe_to_word_table(document, result_traceability_snapshot_to_dataframe(manifest.traceability_snapshot), max_rows=options.max_table_rows)

    add_report_heading(document, "Report Readiness", level=1)
    dataframe_to_word_table(document, report_readiness_to_dataframe(manifest.readiness_summary), max_rows=options.max_table_rows)

    add_warning_box_or_section(document, manifest.engineering_warnings, "Engineering Warnings")
    add_limitations_section(document, manifest.engineering_limitations)
    add_unit_conventions_section(document, manifest.unit_conventions)

    add_report_heading(document, "Available Report Tables", level=1)
    dataframe_to_word_table(document, report_tables_to_dataframe(manifest.tables), max_rows=options.max_table_rows)

    add_report_heading(document, "Available Report Figures", level=1)
    figure_summary = report_figure_export_items_to_dataframe(manifest.figure_export_items)[
        ["Figure Key", "Title", "Available", "Export Ready", "Selected Context", "Warning"]
    ]
    dataframe_to_word_table(document, figure_summary, max_rows=options.max_table_rows)

    _add_figures(document, manifest, session_state, options)
    _add_generation_notes(document, manifest)

    if options.include_appendices:
        add_report_heading(document, "Appendices", level=1)
        dataframe_to_word_table(document, report_sections_to_dataframe(manifest.sections), title="Report Section Plan", max_rows=options.max_table_rows)
        if options.include_full_registries:
            dataframe_to_word_table(document, report_tables_to_dataframe(manifest.tables), title="Full Report Table Registry", max_rows=options.max_table_rows)
            dataframe_to_word_table(document, report_figure_export_items_to_dataframe(manifest.figure_export_items), title="Full Report Figure Registry", max_rows=options.max_table_rows)
        if options.include_full_terminology:
            add_terminology_section(document, manifest.terminology)
        dataframe_to_word_table(document, report_manifest_to_summary_dataframe(manifest), title="Raw Manifest Summary", max_rows=options.max_table_rows)

    document.add_paragraph("PDF export remains future work.")
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def save_draft_word_report(
    manifest: ReportManifest,
    output_path: str,
    session_state: Any | None = None,
    options: ReportExportOptions | None = None,
) -> None:
    Path(output_path).write_bytes(build_draft_word_report(manifest, session_state=session_state, options=options))
