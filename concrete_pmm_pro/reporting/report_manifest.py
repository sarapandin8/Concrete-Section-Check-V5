"""Report manifest foundation for future Word/PDF export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

import pandas as pd

from concrete_pmm_pro.reporting.limitations import EngineeringLimitation, collect_limitations_for_report
from concrete_pmm_pro.reporting.readiness import ReportReadinessSummary, check_report_readiness
from concrete_pmm_pro.reporting.report_figures import (
    ReportFigureContext,
    ReportFigureExportItem,
    ReportFigureInfo,
    build_report_figure_context,
    collect_available_report_figures,
    collect_report_figure_export_items,
)
from concrete_pmm_pro.reporting.report_models import ReportMetadata, ReportSection, default_report_metadata
from concrete_pmm_pro.reporting.report_sections import default_report_section_plan
from concrete_pmm_pro.reporting.report_tables import ReportTableInfo, collect_available_report_tables
from concrete_pmm_pro.reporting.terminology import EngineeringTerm, get_standard_terminology
from concrete_pmm_pro.reporting.traceability import ResultTraceabilitySnapshot, build_result_traceability_snapshot
from concrete_pmm_pro.reporting.units import UnitConvention, get_unit_conventions


@dataclass(frozen=True)
class ReportManifest:
    metadata: ReportMetadata
    traceability_snapshot: ResultTraceabilitySnapshot
    readiness_summary: ReportReadinessSummary
    sections: list[ReportSection]
    tables: list[ReportTableInfo]
    figures: list[ReportFigureInfo]
    engineering_warnings: list[str]
    engineering_limitations: list[EngineeringLimitation]
    unit_conventions: list[UnitConvention]
    terminology: list[EngineeringTerm]
    figure_export_items: list[ReportFigureExportItem] = field(default_factory=list)
    figure_context: ReportFigureContext | None = None
    generated_status: str = "FOUNDATION_ONLY"
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    if hasattr(mapping, "get"):
        try:
            return mapping.get(key, default)
        except (AttributeError, TypeError, ValueError):
            return default
    return getattr(mapping, key, default)


def build_report_manifest(session_state: Any, metadata: ReportMetadata | None = None) -> ReportManifest:
    snapshot = build_result_traceability_snapshot(session_state)
    readiness = check_report_readiness(snapshot)
    limitations = collect_limitations_for_report(session_state, include_all=True)
    figures = collect_available_report_figures(session_state)
    figure_context = build_report_figure_context(session_state)
    figure_export_items = collect_report_figure_export_items(session_state)
    tables = collect_available_report_tables(session_state)
    if metadata is None:
        metadata = default_report_metadata(project_name=snapshot.project_name or _get(session_state, "project_name"))
    sections = default_report_section_plan(snapshot, readiness, figures, limitations)
    warnings = list(snapshot.warnings)
    critical_titles = [item.title for item in limitations if item.risk_level == "CRITICAL"]
    manifest_warnings = ["PDF export and final certified report templates are future work."]
    if critical_titles:
        manifest_warnings.append("Critical limitations require review: " + "; ".join(critical_titles))
    return ReportManifest(
        metadata=metadata,
        traceability_snapshot=snapshot,
        readiness_summary=readiness,
        sections=sections,
        tables=tables,
        figures=figures,
        figure_export_items=figure_export_items,
        figure_context=figure_context,
        engineering_warnings=warnings,
        engineering_limitations=limitations,
        unit_conventions=get_unit_conventions(),
        terminology=list(get_standard_terminology().values()),
        warnings=manifest_warnings,
        info=["Report manifest summarizes stored results. Draft Word export exists; PDF export remains future work."],
    )


def report_manifest_to_summary_dataframe(manifest: ReportManifest) -> pd.DataFrame:
    high_or_critical = [item for item in manifest.engineering_limitations if item.risk_level in {"HIGH", "CRITICAL"}]
    data = {
        "Generated Status": manifest.generated_status,
        "Report Title": manifest.metadata.report_title,
        "Project Name": manifest.metadata.project_name or "",
        "Revision": manifest.metadata.revision,
        "Readiness Status": manifest.readiness_summary.overall_status,
        "Section Count": len(manifest.sections),
        "Available Tables": len([table for table in manifest.tables if table.available]),
        "Available Figures": len([figure for figure in manifest.figures if figure.available]),
        "Engineering Warning Count": len(manifest.engineering_warnings),
        "Engineering Limitation Count": len(manifest.engineering_limitations),
        "High/Critical Limitation Count": len(high_or_critical),
        "Critical Limitations": "; ".join(item.title for item in manifest.engineering_limitations if item.risk_level == "CRITICAL"),
    }
    return pd.DataFrame([{"Item": key, "Value": value} for key, value in data.items()], columns=["Item", "Value"])


def _jsonify(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonify(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonify(item) for item in value]
    return value


def report_manifest_to_json_dict(manifest: ReportManifest) -> dict[str, Any]:
    return _jsonify(manifest)


def generate_plain_text_report_outline(manifest: ReportManifest) -> str:
    lines = [
        f"{manifest.metadata.report_title} - Draft Outline",
        "",
        f"Readiness Status: {manifest.readiness_summary.overall_status}",
        f"Warnings Count: {len(manifest.engineering_warnings)}",
        f"Limitations Count: {len(manifest.engineering_limitations)}",
        f"High/Critical Limitations: {len([item for item in manifest.engineering_limitations if item.risk_level in {'HIGH', 'CRITICAL'}])}",
    ]
    critical = [item.title for item in manifest.engineering_limitations if item.risk_level == "CRITICAL"]
    if critical:
        lines.append("Critical Limitations: " + "; ".join(critical))
    lines.append("")
    for index, section in enumerate(manifest.sections, start=1):
        lines.append(f"{index}. {section.title}")
        lines.append(f"   Status: {section.status}")
        if section.summary:
            lines.append(f"   Notes: {section.summary}")
        if section.table_keys:
            lines.append("   Tables: " + ", ".join(section.table_keys))
        if section.figure_keys:
            lines.append("   Figures: " + ", ".join(section.figure_keys))
        if section.limitation_keys:
            lines.append("   Limitations: " + ", ".join(section.limitation_keys))
        if section.warnings:
            lines.append(f"   Warnings: {len(section.warnings)} item(s)")
        lines.append("")
    lines.append("Report manifest and draft Word export are available. PDF export remains future work.")
    return "\n".join(lines)
