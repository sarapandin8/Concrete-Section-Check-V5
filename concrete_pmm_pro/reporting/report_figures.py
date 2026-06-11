"""Report figure export preparation for future report generation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from concrete_pmm_pro.reporting.traceability import (
    ReportFigureInfo,
    collect_available_report_figures,
    report_figures_to_dataframe,
)
from concrete_pmm_pro.visualization.sls_stress import (
    make_sls_section_stress_figure,
    make_sls_stress_bar_figure,
    service_stress_results_to_plot_dataframe,
)


@dataclass(frozen=True)
class ReportFigureContext:
    selected_uls_combo: str | None = None
    governing_uls_combo: str | None = None
    selected_sls_combo: str | None = None
    selected_pu_kN: float | None = None
    section_basis: str | None = None
    include_prestress_sls: bool | None = None
    use_transformed_section: bool | None = None
    crack_classification_available: bool = False
    pmm_result_available: bool = False
    dc_result_available: bool = False
    pmm_slice_available: bool = False
    pmm_slice_envelope_available: bool = False
    pmm_capacity_method: str | None = None
    pmm_warning_count: int = 0
    sls_result_available: bool = False
    warning_count: int = 0


@dataclass(frozen=True)
class ReportFigureExportItem:
    figure_key: str
    title: str
    available: bool
    source: str
    description: str
    recommended_for_report: bool = True
    export_ready: bool = False
    figure_type: str = "plotly"
    selected_context: str | None = None
    export_filename_png: str | None = None
    export_filename_html: str | None = None
    warning: str | None = None
    limitations: list[str] = field(default_factory=list)


def _get(mapping: Any, key: str, default: Any = None) -> Any:
    if mapping is None:
        return default
    if hasattr(mapping, "get"):
        try:
            return mapping.get(key, default)
        except (AttributeError, TypeError, ValueError):
            return default
    return getattr(mapping, key, default)


def _first_nonempty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _find_dataframe_in_session(session_state: Any, candidate_keys: list[str]) -> pd.DataFrame | None:
    for key in candidate_keys:
        value = _get(session_state, key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
    return None


def _has_columns(df: pd.DataFrame, columns: set[str]) -> bool:
    return columns.issubset(set(df.columns))


def _find_moment_columns(df: pd.DataFrame) -> tuple[str | None, str | None]:
    x_candidates = ["Mux_kNm", "Mnx_kNm", "phiMnx_kNm", "Mx_kNm", "x"]
    y_candidates = ["Muy_kNm", "Mny_kNm", "phiMny_kNm", "My_kNm", "y"]
    x_matches = [column for column in x_candidates if column in df.columns]
    y_matches = [column for column in y_candidates if column in df.columns]
    if not x_matches or not y_matches:
        return None, None
    return x_matches[0], y_matches[0]


def _default_sls_combo(summary: Any) -> str | None:
    combo = getattr(summary, "governing_combo", None)
    if combo:
        return str(combo)
    load_cases = getattr(summary, "sls_load_cases", []) or []
    for load_case in load_cases:
        name = getattr(load_case, "name", None)
        if name:
            return str(name)
    stress_results = getattr(summary, "stress_results", []) or []
    for result in stress_results:
        combo_name = getattr(result, "combo_name", None)
        if combo_name:
            return str(combo_name)
    return None


def build_report_figure_context(session_state: Any) -> ReportFigureContext:
    serviceability = _get(session_state, "serviceability_summary")
    crack = _get(session_state, "crack_classification_summary")
    pmm_result = _get(session_state, "rc_pmm_result")
    if pmm_result is None:
        pmm_result = _get(session_state, "pmm_result")
    dc_summary = _get(session_state, "rc_demand_capacity_result")
    if dc_summary is None:
        dc_summary = _get(session_state, "demand_capacity_summary")
    if dc_summary is None:
        dc_summary = _get(session_state, "dc_summary")
    snapshot = _get(session_state, "result_traceability_snapshot")
    pmm_slice_df = _find_dataframe_in_session(
        session_state,
        ["selected_pmm_slice", "pmm_slice_dataframe", "selected_pmm_slice_dataframe"],
    )
    pmm_envelope_df = _find_dataframe_in_session(
        session_state,
        ["selected_slice_envelope", "pmm_slice_envelope_dataframe", "selected_pmm_slice_envelope_dataframe"],
    )

    selected_sls_combo = _first_nonempty(
        _get(session_state, "selected_sls_combo"),
        _get(session_state, "sls_visualization_selected_combo"),
        _default_sls_combo(serviceability),
    )
    selected_uls_combo = _first_nonempty(
        _get(session_state, "selected_uls_combo"),
        _get(session_state, "pmm_dashboard_selected_combo"),
        getattr(dc_summary, "governing_combo", None),
        getattr(snapshot, "governing_uls_combo", None),
    )
    governing_uls_combo = _first_nonempty(getattr(dc_summary, "governing_combo", None), getattr(snapshot, "governing_uls_combo", None))
    pmm_warnings = getattr(pmm_result, "warnings", []) or []
    pmm_warnings.extend(getattr(dc_summary, "warnings", []) or [])
    return ReportFigureContext(
        selected_uls_combo=None if selected_uls_combo is None else str(selected_uls_combo),
        governing_uls_combo=None if governing_uls_combo is None else str(governing_uls_combo),
        selected_sls_combo=None if selected_sls_combo is None else str(selected_sls_combo),
        selected_pu_kN=_get(session_state, "selected_pu_kN"),
        section_basis=getattr(serviceability, "section_basis_used", None) or getattr(snapshot, "section_basis_used", None),
        include_prestress_sls=getattr(serviceability, "prestress_included", None),
        use_transformed_section=getattr(getattr(serviceability, "settings", None), "use_transformed_section", None),
        crack_classification_available=crack is not None,
        pmm_result_available=pmm_result is not None,
        dc_result_available=dc_summary is not None,
        pmm_slice_available=pmm_slice_df is not None,
        pmm_slice_envelope_available=pmm_envelope_df is not None,
        pmm_capacity_method=getattr(snapshot, "pmm_capacity_method", None),
        pmm_warning_count=len(pmm_warnings),
        sls_result_available=serviceability is not None,
        warning_count=int(getattr(snapshot, "warning_count", 0) or 0),
    )


def safe_report_figure_filename(
    figure_key: str,
    context_label: str | None = None,
    extension: str = "png",
) -> str:
    parts = [figure_key]
    if context_label:
        parts.append(context_label)
    stem = "_".join(parts).lower()
    stem = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    ext = re.sub(r"[^a-z0-9]+", "", extension.lower()) or "png"
    return f"{stem}.{ext}"


def _limitations_for_key(key: str, session_state: Any) -> list[str]:
    limitations: list[str] = []
    if key.startswith("pmm"):
        limitations.append(
            "ACI RC PMM figures may be used for finalized production-preview review only within the validated RC scope; "
            "unsupported PMM routes and fallback capacity methods remain engineering-review items."
        )
    if key == "pmm_slice_envelope":
        limitations.append("Convex hull fallback may overestimate PMM capacity when used.")
    if key.startswith("pmm"):
        limitations.append("PMM figure export uses existing stored result data and does not recompute the solver.")
    if key.startswith("sls") or key.startswith("cracking") or key.startswith("transformed"):
        limitations.append("SLS visualization is point-based, not a full stress contour.")
        limitations.append("Cracked-section redistribution is not implemented.")
    if _get(session_state, "prestress_elements"):
        limitations.append("Unbonded prestress is ignored by the current solvers.")
    return limitations


def _convex_hull_warning(session_state: Any) -> str | None:
    for key in ("selected_slice_envelope", "pmm_slice_envelope_dataframe", "selected_pmm_slice_envelope_dataframe"):
        value = _get(session_state, key)
        attrs = getattr(value, "attrs", {})
        if attrs.get("used_convex_hull") or attrs.get("convex_hull_fallback"):
            return "Convex hull fallback may overestimate PMM capacity."
    warnings = []
    for key in ("rc_demand_capacity_result", "demand_capacity_summary", "dc_summary"):
        obj = _get(session_state, key)
        warnings.extend(getattr(obj, "warnings", []) or [])
    if any("convex hull" in str(warning).lower() for warning in warnings):
        return "Convex hull fallback may overestimate PMM capacity."
    return None


def _context_label_for_key(key: str, context: ReportFigureContext) -> str | None:
    if key.startswith("sls") or key.startswith("cracking"):
        return context.selected_sls_combo
    if key.startswith("pmm"):
        return context.selected_uls_combo or "governing_uls"
    return None


def collect_report_figure_export_items(session_state: Any) -> list[ReportFigureExportItem]:
    context = build_report_figure_context(session_state)
    figures = collect_available_report_figures(session_state)
    export_ready_keys = set()
    if context.sls_result_available and context.selected_sls_combo:
        export_ready_keys.update({"sls_section_stress_points", "sls_stress_bar_diagram"})
    if _get(session_state, "pmm_interaction_surface_figure") is not None:
        export_ready_keys.add("pmm_interaction_surface")
    if context.pmm_slice_available:
        export_ready_keys.add("pmm_mux_muy_slice")
    if context.pmm_slice_envelope_available:
        export_ready_keys.add("pmm_slice_envelope")
    if context.pmm_slice_envelope_available and _get(session_state, "selected_pmm_demand_point") is not None:
        export_ready_keys.add("pmm_demand_capacity_overlay")
    standard_keys = {
        "section_geometry_layout",
        "pmm_interaction_surface",
        "pmm_mux_muy_slice",
        "pmm_slice_envelope",
        "pmm_demand_capacity_overlay",
        "sls_section_stress_points",
        "sls_stress_bar_diagram",
        "cracking_classification_overlay",
        "custom_stress_points_layout",
        "transformed_section_properties_preview",
    }
    items: list[ReportFigureExportItem] = []
    seen: set[str] = set()
    for figure in figures:
        key = "transformed_section_properties_preview" if figure.figure_key == "transformed_section_preview" else figure.figure_key
        if key not in standard_keys and figure.figure_key not in {"sls_stress_visualization", "pmm_dashboard"}:
            continue
        if key in seen:
            continue
        seen.add(key)
        context_label = _context_label_for_key(key, context)
        available = figure.available
        if key == "pmm_mux_muy_slice" and context.pmm_slice_available:
            available = True
        if key == "pmm_slice_envelope" and context.pmm_slice_envelope_available:
            available = True
        if key == "pmm_interaction_surface" and _get(session_state, "pmm_interaction_surface_figure") is not None:
            available = True
        export_ready = key in export_ready_keys or figure.figure_key in export_ready_keys
        warning = figure.warning
        if available and key.startswith("sls") and not context.selected_sls_combo:
            warning = "SLS figure export requires a selected or governing SLS combo."
        if key == "sls_stress_visualization":
            warning = "SLS stress visualization is represented by exportable figures sls_section_stress_points and sls_stress_bar_diagram."
        if available and key.startswith("pmm") and key not in export_ready_keys:
            warning = warning or "PMM figure export requires existing dashboard figure or selected slice data."
        if key == "pmm_interaction_surface" and available and key not in export_ready_keys:
            warning = "3D PMM surface export requires existing dashboard figure state; not recreated during report export."
        hull_warning = _convex_hull_warning(session_state)
        if hull_warning and key in {"pmm_slice_envelope", "pmm_demand_capacity_overlay"}:
            warning = hull_warning
        items.append(
            ReportFigureExportItem(
                figure_key=key,
                title=figure.title,
                available=available,
                source=figure.source,
                description=figure.description,
                recommended_for_report=figure.recommended_for_report,
                export_ready=export_ready,
                selected_context=context_label,
                export_filename_png=safe_report_figure_filename(key, context_label, "png") if available else None,
                export_filename_html=safe_report_figure_filename(key, context_label, "html") if available else None,
                warning=warning,
                limitations=_limitations_for_key(key, session_state),
            )
        )
    pmm_extra = {
        "pmm_demand_capacity_overlay": (
            context.dc_result_available and context.pmm_slice_envelope_available,
            "PMM Demand / Capacity Overlay",
            "selected_pmm_demand_point",
            "Stored PMM slice envelope with demand point overlay.",
        )
    }
    for key, (available, title, source, description) in pmm_extra.items():
        if key in seen:
            continue
        seen.add(key)
        context_label = _context_label_for_key(key, context)
        warning = None
        if available and key not in export_ready_keys:
            warning = "PMM demand/capacity overlay export requires stored envelope data and demand point data."
        items.append(
            ReportFigureExportItem(
                figure_key=key,
                title=title,
                available=available,
                source=source,
                description=description,
                export_ready=key in export_ready_keys,
                selected_context=context_label,
                export_filename_png=safe_report_figure_filename(key, context_label, "png") if available else None,
                export_filename_html=safe_report_figure_filename(key, context_label, "html") if available else None,
                warning=warning or _convex_hull_warning(session_state),
                limitations=_limitations_for_key(key, session_state),
            )
        )
    for key in sorted(standard_keys - seen):
        items.append(
            ReportFigureExportItem(
                figure_key=key,
                title=key.replace("_", " ").title(),
                available=False,
                source="session_state",
                description="Standard report figure slot; source data is not currently available.",
                warning="Source data is not available.",
            )
        )
    return items


def report_figure_export_items_to_dataframe(items: list[ReportFigureExportItem]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Figure Key": item.figure_key,
                "Title": item.title,
                "Available": item.available,
                "Export Ready": item.export_ready,
                "Figure Type": item.figure_type,
                "Source": item.source,
                "Selected Context": item.selected_context or "",
                "PNG Filename": item.export_filename_png or "",
                "HTML Filename": item.export_filename_html or "",
                "Recommended": item.recommended_for_report,
                "Description": item.description,
                "Warning": item.warning or "",
                "Limitations": "; ".join(item.limitations),
            }
            for item in items
        ],
        columns=[
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
        ],
    )


def build_exportable_figure(
    figure_key: str,
    session_state: Any,
    context: ReportFigureContext | None = None,
) -> tuple[go.Figure | None, list[str]]:
    context = context or build_report_figure_context(session_state)
    if figure_key == "pmm_interaction_surface":
        fig = _get(session_state, "pmm_interaction_surface_figure")
        if isinstance(fig, go.Figure):
            return fig, []
        return None, ["3D PMM surface export requires existing dashboard figure state; not recreated during report export."]
    if figure_key == "pmm_mux_muy_slice":
        return _build_pmm_dataframe_figure(
            _find_dataframe_in_session(session_state, ["selected_pmm_slice", "pmm_slice_dataframe", "selected_pmm_slice_dataframe"]),
            "PMM Mux-Muy Slice",
            context,
        )
    if figure_key == "pmm_slice_envelope":
        fig, warnings = _build_pmm_dataframe_figure(
            _find_dataframe_in_session(session_state, ["selected_slice_envelope", "pmm_slice_envelope_dataframe", "selected_pmm_slice_envelope_dataframe"]),
            "PMM Slice Envelope",
            context,
            line_mode=True,
        )
        hull_warning = _convex_hull_warning(session_state)
        if hull_warning:
            warnings.append(hull_warning)
        return fig, warnings
    if figure_key == "pmm_demand_capacity_overlay":
        return _build_pmm_demand_capacity_overlay(session_state, context)

    serviceability = _get(session_state, "serviceability_summary")
    crack_summary = _get(session_state, "crack_classification_summary")
    if serviceability is None:
        return None, ["Serviceability summary is not available."]
    selected_combo = context.selected_sls_combo or _default_sls_combo(serviceability)
    if not selected_combo:
        return None, ["Selected SLS combo is not available."]

    if figure_key == "sls_stress_bar_diagram":
        stress_df = service_stress_results_to_plot_dataframe(serviceability, crack_summary, selected_combo)
        return make_sls_stress_bar_figure(stress_df, selected_combo), []
    if figure_key == "sls_stress_visualization":
        return None, ["SLS stress visualization is represented by exportable figures sls_section_stress_points and sls_stress_bar_diagram."]
    if figure_key == "sls_section_stress_points":
        section_geometry = _get(session_state, "section_geometry")
        if section_geometry is None:
            return None, ["Section geometry is not available."]
        stress_df = service_stress_results_to_plot_dataframe(serviceability, crack_summary, selected_combo)
        return make_sls_section_stress_figure(section_geometry, stress_df, selected_combo), []
    return None, ["Figure export preparation for this figure key is future work."]


def _build_pmm_dataframe_figure(
    df: pd.DataFrame | None,
    title: str,
    context: ReportFigureContext,
    line_mode: bool = False,
) -> tuple[go.Figure | None, list[str]]:
    if df is None or df.empty:
        return None, [f"{title} export requires stored PMM slice/envelope dataframe."]
    x_col, y_col = _find_moment_columns(df)
    if x_col is None or y_col is None:
        return None, ["PMM figure dataframe is missing recognizable Mx/My columns."]
    title_text = title
    if context.selected_pu_kN is not None:
        title_text += f" - Pu = {context.selected_pu_kN:.2f} kN"
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode="lines+markers" if line_mode else "markers",
            name=title,
        )
    )
    fig.update_layout(title=title_text, height=520, paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(title=x_col, scaleanchor="y", scaleratio=1, zeroline=True)
    fig.update_yaxes(title=y_col, zeroline=True)
    return fig, []


def _demand_xy(demand: Any) -> tuple[float | None, float | None, str | None]:
    if demand is None:
        return None, None, None
    if isinstance(demand, dict):
        x = _first_nonempty(demand.get("Mux_kNm"), demand.get("Mnx_kNm"), demand.get("Mx_kNm"), demand.get("x"))
        y = _first_nonempty(demand.get("Muy_kNm"), demand.get("Mny_kNm"), demand.get("My_kNm"), demand.get("y"))
        label = _first_nonempty(demand.get("Combo Name"), demand.get("combo_name"), demand.get("name"), "Demand")
        return x, y, str(label)
    x = _first_nonempty(getattr(demand, "Mux_kNm", None), getattr(demand, "Mnx_kNm", None), getattr(demand, "Mx_kNm", None), getattr(demand, "x", None))
    y = _first_nonempty(getattr(demand, "Muy_kNm", None), getattr(demand, "Mny_kNm", None), getattr(demand, "My_kNm", None), getattr(demand, "y", None))
    label = _first_nonempty(getattr(demand, "combo_name", None), getattr(demand, "name", None), "Demand")
    return x, y, str(label)


def _build_pmm_demand_capacity_overlay(session_state: Any, context: ReportFigureContext) -> tuple[go.Figure | None, list[str]]:
    envelope_df = _find_dataframe_in_session(
        session_state,
        ["selected_slice_envelope", "pmm_slice_envelope_dataframe", "selected_pmm_slice_envelope_dataframe"],
    )
    fig, warnings = _build_pmm_dataframe_figure(envelope_df, "PMM Demand / Capacity Overlay", context, line_mode=True)
    if fig is None:
        return None, warnings
    x, y, label = _demand_xy(_get(session_state, "selected_pmm_demand_point"))
    if x is None or y is None:
        return None, ["PMM demand/capacity overlay export requires stored demand point data."]
    fig.add_trace(
        go.Scatter(
            x=[float(x)],
            y=[float(y)],
            mode="markers+text",
            marker=dict(size=14, color="#dc2626", symbol="x"),
            text=[label],
            textposition="top center",
            name="Demand",
        )
    )
    hull_warning = _convex_hull_warning(session_state)
    if hull_warning:
        warnings.append(hull_warning)
    return fig, warnings


__all__ = [
    "ReportFigureContext",
    "ReportFigureExportItem",
    "ReportFigureInfo",
    "build_exportable_figure",
    "build_report_figure_context",
    "collect_available_report_figures",
    "collect_report_figure_export_items",
    "_find_dataframe_in_session",
    "_find_moment_columns",
    "_has_columns",
    "report_figure_export_items_to_dataframe",
    "report_figures_to_dataframe",
    "safe_report_figure_filename",
]
