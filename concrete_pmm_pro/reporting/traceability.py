"""Result traceability helpers for future report export."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from concrete_pmm_pro.analysis.warnings import (
    DCR_PROTOTYPE_WARNING,
    PMM_PROTOTYPE_WARNING,
    UNBONDED_PRESTRESS_IGNORED_WARNING,
)
from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import analysis_mode_warnings
from concrete_pmm_pro.reporting.limitations import collect_limitations_for_report


SLS_LIMITATION_WARNINGS = [
    "Cracked section redistribution is not implemented yet.",
    "Crack width checks are not implemented yet.",
    "Unbonded prestress model is not implemented yet.",
]


@dataclass(frozen=True)
class ResultTraceabilitySnapshot:
    project_name: str | None = None
    member_type: str | None = None
    analysis_workflow: str | None = None
    section_available: bool = False
    materials_available: bool = False
    rebar_count: int = 0
    prestress_count: int = 0
    custom_stress_point_count: int = 0
    active_custom_stress_point_count: int = 0
    include_default_stress_points: bool = True
    pmm_result_available: bool = False
    pmm_point_count: int = 0
    dc_result_available: bool = False
    governing_uls_combo: str | None = None
    max_uls_dcr: float | None = None
    uls_overall_status: str | None = None
    pmm_capacity_method: str | None = None
    sls_result_available: bool = False
    sls_overall_status: str | None = None
    governing_sls_combo: str | None = None
    governing_sls_point: str | None = None
    max_sls_utilization: float | None = None
    section_basis_used: str | None = None
    prestress_included_in_sls: bool = False
    crack_classification_available: bool = False
    crack_overall_classification: str | None = None
    max_tension_MPa: float | None = None
    pmm_verification_status: str | None = None
    hand_check_status: str | None = None
    sls_verification_status: str | None = None
    limitation_count: int = 0
    high_or_critical_limitation_count: int = 0
    warning_count: int = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReportFigureInfo:
    figure_key: str
    title: str
    available: bool
    source: str
    description: str
    recommended_for_report: bool = True
    warning: str | None = None
    export_format: str = "png_future"


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    if hasattr(mapping, "get"):
        return mapping.get(key, default)
    return getattr(mapping, key, default)


def _coerce_analysis_mode(value: Any) -> AnalysisModeSettings:
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


def deduplicate_preserve_order(warnings: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for warning in warnings:
        if not warning:
            continue
        text = str(warning)
        if text in seen:
            continue
        seen.add(text)
        unique.append(text)
    return unique


def _extend_attr_warnings(warnings: list[str], obj: Any) -> None:
    if obj is None:
        return
    for attr in ("warnings", "info"):
        values = getattr(obj, attr, None)
        if isinstance(values, list):
            warnings.extend(str(item) for item in values if item)


def collect_engineering_warnings(
    pmm_result: Any = None,
    dc_summary: Any = None,
    serviceability_summary: Any = None,
    crack_classification_summary: Any = None,
    analysis_mode_settings: Any = None,
    prestress_check_summary: Any = None,
    additional_warnings: list[str] | None = None,
) -> list[str]:
    warnings: list[str] = []
    _extend_attr_warnings(warnings, pmm_result)
    _extend_attr_warnings(warnings, dc_summary)
    _extend_attr_warnings(warnings, serviceability_summary)
    _extend_attr_warnings(warnings, crack_classification_summary)
    _extend_attr_warnings(warnings, prestress_check_summary)

    mode = _coerce_analysis_mode(analysis_mode_settings)
    warnings.extend(analysis_mode_warnings(mode))
    if mode.member_type == "beam_girder":
        warnings.append("Beam/Girder design checks are not implemented yet.")

    if pmm_result is not None:
        warnings.append(PMM_PROTOTYPE_WARNING)
        points = getattr(pmm_result, "points", []) or []
        if any(getattr(point, "unbonded_prestress_ignored_count", 0) for point in points):
            warnings.append(UNBONDED_PRESTRESS_IGNORED_WARNING)
    if dc_summary is not None:
        warnings.append(DCR_PROTOTYPE_WARNING)
    if serviceability_summary is not None:
        warnings.extend(SLS_LIMITATION_WARNINGS)
    if additional_warnings:
        warnings.extend(additional_warnings)
    return deduplicate_preserve_order(warnings)


def _first_capacity_method(dc_summary: Any) -> str | None:
    for result in getattr(dc_summary, "results", []) or []:
        method = getattr(result, "capacity_method", None)
        if method:
            return str(method)
    return None


def build_result_traceability_snapshot(session_state: Any) -> ResultTraceabilitySnapshot:
    mode = _coerce_analysis_mode(_get(session_state, "analysis_mode_settings", AnalysisModeSettings()))
    pmm_result = _get(session_state, "rc_pmm_result")
    dc_summary = _get(session_state, "rc_demand_capacity_result")
    serviceability_summary = _get(session_state, "serviceability_summary")
    crack_summary = _get(session_state, "crack_classification_summary")
    custom_points = list(_get(session_state, "custom_stress_check_points", []) or [])
    concrete_material = _get(session_state, "concrete_material")
    materials_available = concrete_material is not None
    warnings = collect_engineering_warnings(
        pmm_result=pmm_result,
        dc_summary=dc_summary,
        serviceability_summary=serviceability_summary,
        crack_classification_summary=crack_summary,
        analysis_mode_settings=mode,
        prestress_check_summary=_get(session_state, "prestress_check_summary"),
    )
    limitations = collect_limitations_for_report(session_state, include_all=True)
    high_or_critical = [item for item in limitations if item.risk_level in {"HIGH", "CRITICAL"}]
    return ResultTraceabilitySnapshot(
        project_name=_get(session_state, "project_name"),
        member_type=mode.member_type,
        analysis_workflow=mode.analysis_workflow,
        section_available=_get(session_state, "section_geometry") is not None,
        materials_available=materials_available,
        rebar_count=len(_get(session_state, "rebars", []) or []),
        prestress_count=len(_get(session_state, "prestress_elements", []) or []),
        custom_stress_point_count=len(custom_points),
        active_custom_stress_point_count=len([point for point in custom_points if getattr(point, "active", False)]),
        include_default_stress_points=bool(_get(session_state, "include_default_stress_check_points", True)),
        pmm_result_available=pmm_result is not None,
        pmm_point_count=len(getattr(pmm_result, "points", []) or []),
        dc_result_available=dc_summary is not None,
        governing_uls_combo=getattr(dc_summary, "governing_combo", None),
        max_uls_dcr=getattr(dc_summary, "max_dcr", None),
        uls_overall_status=getattr(dc_summary, "overall_status", None),
        pmm_capacity_method=_first_capacity_method(dc_summary),
        sls_result_available=serviceability_summary is not None and bool(getattr(serviceability_summary, "stress_results", [])),
        sls_overall_status=getattr(serviceability_summary, "overall_status", None),
        governing_sls_combo=getattr(serviceability_summary, "governing_combo", None),
        governing_sls_point=getattr(serviceability_summary, "governing_point", None),
        max_sls_utilization=getattr(serviceability_summary, "max_utilization", None),
        section_basis_used=getattr(serviceability_summary, "section_basis_used", None),
        prestress_included_in_sls=bool(getattr(serviceability_summary, "prestress_included", False)),
        crack_classification_available=crack_summary is not None,
        crack_overall_classification=getattr(crack_summary, "overall_classification", None),
        max_tension_MPa=getattr(crack_summary, "max_tension_MPa", None),
        pmm_verification_status=getattr(_get(session_state, "pmm_verification_summary"), "overall_status", None),
        hand_check_status=getattr(_get(session_state, "pmm_hand_check_summary"), "overall_status", None),
        sls_verification_status=getattr(_get(session_state, "sls_verification_summary"), "overall_status", None),
        limitation_count=len(limitations),
        high_or_critical_limitation_count=len(high_or_critical),
        warning_count=len(warnings),
        warnings=warnings,
    )


def result_traceability_snapshot_to_dataframe(snapshot: ResultTraceabilitySnapshot) -> pd.DataFrame:
    data = snapshot.__dict__.copy()
    data["warnings"] = "\n".join(snapshot.warnings)
    return pd.DataFrame(
        [{"Item": key, "Value": value} for key, value in data.items() if key != "warning_count"]
        + [{"Item": "warning_count", "Value": snapshot.warning_count}],
        columns=["Item", "Value"],
    )


def collect_available_report_figures(session_state: Any) -> list[ReportFigureInfo]:
    pmm_available = _get(session_state, "rc_pmm_result") is not None or _get(session_state, "pmm_result") is not None
    dc_available = _get(session_state, "rc_demand_capacity_result") is not None or _get(session_state, "demand_capacity_summary") is not None
    serviceability_available = _get(session_state, "serviceability_summary") is not None
    crack_available = _get(session_state, "crack_classification_summary") is not None
    transformed_available = bool(getattr(_get(session_state, "serviceability_summary"), "transformed_section_properties", None))
    custom_points = _get(session_state, "custom_stress_check_points", []) or []
    section_available = _get(session_state, "section_geometry") is not None
    return [
        ReportFigureInfo("section_geometry_layout", "Section Geometry Layout", section_available, "section_geometry", "Concrete section outline and void layout."),
        ReportFigureInfo("pmm_dashboard", "PMM Dashboard", pmm_available, "rc_pmm_result", "PMM point cloud and dashboard views."),
        ReportFigureInfo("pmm_interaction_surface", "PMM Interaction Surface", pmm_available, "rc_pmm_result", "PMM point cloud and 3D interaction view."),
        ReportFigureInfo("pmm_mux_muy_slice", "PMM Mux-Muy Slice", pmm_available, "rc_pmm_result", "Selected Pu Mux-Muy slice."),
        ReportFigureInfo("pmm_slice_envelope", "Selected PMM Slice Envelope", pmm_available or dc_available, "rc_pmm_result", "Selected Pu slice and envelope when available."),
        ReportFigureInfo("sls_stress_visualization", "SLS Stress Visualization", serviceability_available, "serviceability_summary", "Selected-combo SLS stress points on section."),
        ReportFigureInfo("sls_section_stress_points", "SLS Section Stress Points", serviceability_available, "serviceability_summary", "Selected-combo SLS stress points on section."),
        ReportFigureInfo("sls_stress_bar_diagram", "SLS Stress Bar Diagram", serviceability_available, "serviceability_summary", "Selected-combo stress bar diagram."),
        ReportFigureInfo("cracking_classification", "Cracking / Tension Classification", crack_available, "crack_classification_summary", "Tension-zone classification overlay/table."),
        ReportFigureInfo("cracking_classification_overlay", "Cracking Classification Overlay", crack_available, "crack_classification_summary", "Tension-zone classification overlay/table."),
        ReportFigureInfo("transformed_section", "Transformed Section Properties", transformed_available, "serviceability_summary", "Uncracked transformed section properties."),
        ReportFigureInfo("transformed_section_preview", "Transformed Section Preview", transformed_available, "serviceability_summary", "Uncracked transformed section properties."),
        ReportFigureInfo("custom_stress_points", "Custom Stress Check Points", bool(custom_points), "custom_stress_check_points", "User-defined SLS stress check points."),
        ReportFigureInfo("custom_stress_points_layout", "Custom Stress Points Layout", bool(custom_points), "custom_stress_check_points", "User-defined SLS stress check points."),
    ]


def report_figures_to_dataframe(figures: list[ReportFigureInfo]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Figure Key": figure.figure_key,
                "Title": figure.title,
                "Available": figure.available,
                "Source": figure.source,
                "Recommended": figure.recommended_for_report,
                "Description": figure.description,
                "Warning": figure.warning or "",
                "Export Format": figure.export_format,
            }
            for figure in figures
        ],
        columns=["Figure Key", "Title", "Available", "Source", "Recommended", "Description", "Warning", "Export Format"],
    )
