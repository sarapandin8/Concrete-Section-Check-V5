"""Project save/load page."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import streamlit as st

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import analysis_mode_label
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.io.project_io import (
    ProjectIOError,
    apply_project_to_session_state,
    project_from_json,
    project_from_session_state,
    project_to_json,
)
from concrete_pmm_pro.reporting import build_result_traceability_snapshot, check_report_readiness


@dataclass(frozen=True)
class DashboardCard:
    title: str
    value: str
    detail: str = ""
    status: str = "info"
    strong: bool = False


_DASHBOARD_CSS = """
<style>
.cpmm-dashboard-card {
  border: 1px solid #d9dee7;
  border-left: 4px solid #7b8794;
  border-radius: 8px;
  padding: 0.85rem 0.95rem;
  background: #ffffff;
  min-height: 112px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.cpmm-dashboard-card.primary {
  min-height: 132px;
  background: #fbfcfe;
}
.cpmm-dashboard-card.ready { border-left-color: #2e7d32; }
.cpmm-dashboard-card.warning { border-left-color: #b7791f; }
.cpmm-dashboard-card.danger { border-left-color: #b42318; }
.cpmm-dashboard-card.info { border-left-color: #8ea3c8; }
.cpmm-dashboard-card.neutral { border-left-color: #7b8794; }
.cpmm-summary-strip {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.7rem 0.85rem;
  margin-bottom: 0.25rem;
}
.cpmm-summary-title {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.18rem;
}
.cpmm-summary-value {
  color: #101828;
  font-size: 1.02rem;
  font-weight: 720;
  line-height: 1.2;
  overflow-wrap: anywhere;
}
.cpmm-summary-detail {
  color: #667085;
  font-size: 0.76rem;
  line-height: 1.25;
  margin-top: 0.2rem;
}
.cpmm-card-title {
  color: #475467;
  font-size: 0.78rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.35rem;
}
.cpmm-card-value {
  color: #101828;
  font-size: 1.05rem;
  font-weight: 720;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.cpmm-card-detail {
  color: #667085;
  font-size: 0.82rem;
  line-height: 1.35;
  margin-top: 0.35rem;
}
.cpmm-status-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.13rem 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0;
  margin-top: 0.45rem;
}
.cpmm-status-badge.ready { color: #1f5f2a; background: #e7f5e8; }
.cpmm-status-badge.warning { color: #7a4b00; background: #fff4d6; }
.cpmm-status-badge.danger { color: #9f1f17; background: #fde8e7; }
.cpmm-status-badge.info { color: #1849a9; background: #e8f1ff; }
.cpmm-status-badge.neutral { color: #475467; background: #eef1f5; }
.cpmm-compact-panel {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.8rem 0.95rem;
  margin-bottom: 0.5rem;
}
.cpmm-kv-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.38rem 0;
}
.cpmm-kv-row:last-child { border-bottom: 0; }
.cpmm-kv-label {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 600;
}
.cpmm-kv-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 650;
  text-align: right;
  overflow-wrap: anywhere;
}
</style>
"""


def status_style_for_value(value: Any) -> str:
    text = str(value).strip().upper()
    if text in {"READY", "YES", "PASS", "PASSED", "VALID", "COMPLETE", "AVAILABLE"}:
        return "ready"
    if text in {"WARNING", "WARNINGS", "PARTIAL", "CAUTION"}:
        return "warning"
    if text in {"NOT_READY", "NO", "FAIL", "FAILED", "INVALID", "CRITICAL", "ERROR"}:
        return "danger"
    if text in {"N/A", "NA", "NONE", "NOT ACTIVE", "FUTURE / NOT IMPLEMENTED"}:
        return "neutral"
    return "info"


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


def _dashboard_card_html(card: DashboardCard) -> str:
    status = card.status if card.status in {"ready", "warning", "danger", "info", "neutral"} else "info"
    detail_html = f'<div class="cpmm-card-detail">{escape(card.detail)}</div>' if card.detail else ""
    badge_html = f'<span class="cpmm-status-badge {status}">{escape(status.upper())}</span>' if card.strong else ""
    primary_class = " primary" if card.strong else ""
    return (
        f'<div class="cpmm-dashboard-card {status}{primary_class}">'
        f'<div class="cpmm-card-title">{escape(card.title)}</div>'
        f'<div class="cpmm-card-value">{escape(card.value)}</div>'
        f"{detail_html}"
        f"{badge_html}"
        "</div>"
    )


def _summary_item_html(card: DashboardCard) -> str:
    detail_html = f'<div class="cpmm-summary-detail">{escape(card.detail)}</div>' if card.detail else ""
    return (
        '<div class="cpmm-summary-strip">'
        f'<div class="cpmm-summary-title">{escape(card.title)}</div>'
        f'<div class="cpmm-summary-value">{escape(card.value)}</div>'
        f"{detail_html}"
        "</div>"
    )


def _compact_panel_html(cards: list[DashboardCard]) -> str:
    rows: list[str] = []
    for card in cards:
        badge = ""
        if card.strong:
            status = card.status if card.status in {"ready", "warning", "danger", "info", "neutral"} else "info"
            badge = f' <span class="cpmm-status-badge {status}">{escape(status.upper())}</span>'
        rows.append(
            '<div class="cpmm-kv-row">'
            f'<div class="cpmm-kv-label">{escape(card.title)}</div>'
            f'<div class="cpmm-kv-value">{escape(card.value)}{badge}</div>'
            "</div>"
        )
    return '<div class="cpmm-compact-panel">' + "".join(rows) + "</div>"


def _render_dashboard_card(card: DashboardCard) -> None:
    st.markdown(_dashboard_card_html(card), unsafe_allow_html=True)


def _render_dashboard_section(title: str, cards: list[DashboardCard], columns: int = 4) -> None:
    st.subheader(title)
    for start in range(0, len(cards), columns):
        cols = st.columns(min(columns, len(cards) - start))
        for column, card in zip(cols, cards[start : start + columns]):
            with column:
                _render_dashboard_card(card)


def _render_summary_strip(title: str, cards: list[DashboardCard]) -> None:
    st.subheader(title)
    cols = st.columns(len(cards))
    for column, card in zip(cols, cards):
        with column:
            st.markdown(_summary_item_html(card), unsafe_allow_html=True)


def _render_compact_panel(title: str, cards: list[DashboardCard], columns: int = 1) -> None:
    st.subheader(title)
    chunk_size = max(1, (len(cards) + columns - 1) // columns)
    cols = st.columns(columns)
    for index, column in enumerate(cols):
        chunk = cards[index * chunk_size : (index + 1) * chunk_size]
        if chunk:
            with column:
                st.markdown(_compact_panel_html(chunk), unsafe_allow_html=True)


def _count_available(items: Any) -> int:
    return len([item for item in items if getattr(item, "available", False)])


def _project_overview_cards(
    project: ProjectModel,
    section_geometry: Any,
    load_cases: list[Any],
    rebars: list[Any],
    prestress_elements: list[Any],
    rebar_valid: bool | None,
    prestress_valid: bool | None,
) -> list[DashboardCard]:
    return [
        DashboardCard(
            "Geometry",
            "Yes" if section_geometry is not None else "No",
            "Generated section available" if section_geometry is not None else "Build section",
            status_style_for_value("Yes" if section_geometry is not None else "No"),
        ),
        DashboardCard("Load Cases", f"{len(load_cases):,}", "Stored load combinations", "ready" if load_cases else "neutral"),
        DashboardCard("Rebars", f"{len(rebars):,}", f"Valid for analysis: {_format_bool(rebar_valid)}", status_style_for_value(_format_bool(rebar_valid))),
        DashboardCard(
            "Prestress Elements",
            f"{len(prestress_elements):,}",
            f"Valid for analysis: {_format_bool(prestress_valid)}",
            status_style_for_value(_format_bool(prestress_valid)),
        ),
        DashboardCard("Version", project.version, "", "neutral"),
    ]


def _analysis_configuration_cards(analysis_mode: AnalysisModeSettings) -> list[DashboardCard]:
    beam_status = "Future / not implemented" if analysis_mode.allow_beam_girder_placeholder else "Not active"
    return [
        DashboardCard("Member Type", analysis_mode_label(analysis_mode), "Active analysis context", "info"),
        DashboardCard("Analysis Workflow", analysis_mode.analysis_workflow, "Configured workflow mode", "info"),
        DashboardCard(
            "PMM Workflow",
            "Yes" if analysis_mode.allow_pmm_workflow else "Caution",
            "ULS/PMM workspace availability",
            "ready" if analysis_mode.allow_pmm_workflow else "warning",
            strong=not analysis_mode.allow_pmm_workflow,
        ),
        DashboardCard(
            "SLS Workflow",
            "Yes" if analysis_mode.allow_sls_workflow else "No",
            "Service stress workflow availability",
            "ready" if analysis_mode.allow_sls_workflow else "danger",
            strong=not analysis_mode.allow_sls_workflow,
        ),
        DashboardCard("Beam/Girder Workflow", beam_status, "Placeholder workflow status", status_style_for_value(beam_status)),
    ]


def _sls_stress_point_cards(custom_points: list[Any], include_default_stress_points: bool) -> list[DashboardCard]:
    active_custom_count = len([point for point in custom_points if getattr(point, "active", False)])
    return [
        DashboardCard("Custom Points", f"{len(custom_points):,}", "User-defined SLS review points", "info" if custom_points else "neutral"),
        DashboardCard("Active Custom Points", f"{active_custom_count:,}", "Included in SLS review", "ready" if active_custom_count else "neutral"),
        DashboardCard(
            "Include Default Stress Points",
            "Yes" if include_default_stress_points else "No",
            "Automatic section review points",
            "ready" if include_default_stress_points else "neutral",
        ),
    ]


def _pre_report_readiness_cards(snapshot: Any, readiness: Any) -> list[DashboardCard]:
    warning_status = "warning" if snapshot.warning_count else "ready"
    limitation_status = "danger" if snapshot.high_or_critical_limitation_count else "ready"
    return [
        DashboardCard("Overall Status", readiness.overall_status, "Pre-report readiness result", status_style_for_value(readiness.overall_status), strong=True),
        DashboardCard("ULS PMM Result", "Yes" if snapshot.pmm_result_available else "No", "Stored PMM result available", status_style_for_value("Yes" if snapshot.pmm_result_available else "No"), strong=True),
        DashboardCard("SLS Result", "Yes" if snapshot.sls_result_available else "No", "Stored serviceability result available", status_style_for_value("Yes" if snapshot.sls_result_available else "No"), strong=True),
        DashboardCard("Warning Count", f"{snapshot.warning_count:,}", "Stored engineering warnings", warning_status, strong=bool(snapshot.warning_count)),
        DashboardCard(
            "High/Critical Limitations",
            f"{snapshot.high_or_critical_limitation_count:,}",
            "Limitations requiring attention",
            limitation_status,
            strong=bool(snapshot.high_or_critical_limitation_count),
        ),
    ]


def _report_foundation_cards(manifest: Any, snapshot: Any) -> list[DashboardCard]:
    tables = _count_available(getattr(manifest, "tables", [])) if manifest else 0
    figures = _count_available(getattr(manifest, "figures", [])) if manifest else 0
    limitations = len(getattr(manifest, "engineering_limitations", [])) if manifest else snapshot.limitation_count
    return [
        DashboardCard("Report Manifest", "Yes" if manifest is not None else "No", "Report registry built", status_style_for_value("Yes" if manifest is not None else "No"), strong=manifest is None),
        DashboardCard("Available Tables", f"{tables:,}", "Manifest table registry", "neutral"),
        DashboardCard("Available Figures", f"{figures:,}", "Manifest figure registry", "neutral"),
        DashboardCard("Engineering Limitations", f"{limitations:,}", "Report limitation registry", "warning" if limitations else "ready", strong=bool(limitations)),
    ]


def _apply_pending_project_load() -> None:
    pending_json = st.session_state.pop("_pending_project_json", None)
    if pending_json is None:
        return

    try:
        project = project_from_json(pending_json)
        apply_project_to_session_state(project, st.session_state)
    except ProjectIOError as exc:
        st.session_state["_project_load_error"] = str(exc)
        return

    st.session_state["_project_load_success"] = (
        "Project JSON loaded. Review Section Builder, Rebar, Prestress, and Loads tabs before future analysis."
    )


def _ensure_project_defaults() -> None:
    st.session_state.setdefault("project_name", "Untitled Project")
    st.session_state.setdefault("designer", "")
    st.session_state.setdefault("description", "")
    st.session_state.setdefault("design_code", "ACI 318")


def render_project_page() -> None:
    _apply_pending_project_load()
    _ensure_project_defaults()

    st.markdown(_DASHBOARD_CSS, unsafe_allow_html=True)
    st.subheader("Project")

    success_message = st.session_state.pop("_project_load_success", None)
    error_message = st.session_state.pop("_project_load_error", None)
    if success_message:
        st.success(success_message)
    if error_message:
        st.error(f"Invalid project file: {error_message}")

    with st.form("project_information_form"):
        st.text_input("Project Name", key="project_name")
        st.text_input("Designer", key="designer")
        st.text_area("Description", key="description")
        st.text_input("Design Code", key="design_code")
        if st.form_submit_button("Update Project Info"):
            st.success("Project information updated.")

    project = project_from_session_state(st.session_state)

    st.subheader("Save / Load Project")
    save_col, load_col = st.columns(2)
    with save_col:
        st.download_button(
            "Download Project JSON",
            data=project_to_json(project),
            file_name="concrete_pmm_project.json",
            mime="application/json",
            use_container_width=True,
        )
    with load_col:
        uploaded_file = st.file_uploader("Upload Project JSON", type=["json"])
        if uploaded_file is not None and st.button("Load Project JSON", use_container_width=True):
            st.session_state["_pending_project_json"] = uploaded_file.getvalue().decode("utf-8")
            st.rerun()

    section_geometry = st.session_state.get("section_geometry")
    load_cases = st.session_state.get("load_cases", [])
    rebars = st.session_state.get("rebars", [])
    prestress_elements = st.session_state.get("prestress_elements", [])
    custom_points = st.session_state.get("custom_stress_check_points", [])
    include_default_stress_points = bool(st.session_state.get("include_default_stress_check_points", True))
    analysis_mode = st.session_state.get("analysis_mode_settings", AnalysisModeSettings())
    if isinstance(analysis_mode, dict):
        analysis_mode = AnalysisModeSettings.model_validate(analysis_mode)

    rebar_valid = st.session_state.get("rebars_valid_for_analysis")
    prestress_valid = st.session_state.get("prestress_valid_for_analysis")
    _render_summary_strip(
        "Project Summary",
        _project_overview_cards(project, section_geometry, load_cases, rebars, prestress_elements, rebar_valid, prestress_valid),
    )

    snapshot = build_result_traceability_snapshot(st.session_state)
    readiness = check_report_readiness(snapshot)
    _render_dashboard_section("Pre-Report Readiness", _pre_report_readiness_cards(snapshot, readiness), columns=5)

    _render_compact_panel("Analysis Configuration", _analysis_configuration_cards(analysis_mode), columns=2)

    _render_compact_panel("SLS Stress Points", _sls_stress_point_cards(custom_points, include_default_stress_points), columns=1)

    manifest = st.session_state.get("report_manifest")
    _render_compact_panel("Report Foundation", _report_foundation_cards(manifest, snapshot), columns=2)
