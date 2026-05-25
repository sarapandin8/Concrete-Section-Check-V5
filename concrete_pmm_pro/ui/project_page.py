"""Project save/load page."""

from __future__ import annotations

import streamlit as st

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import analysis_mode_label
from concrete_pmm_pro.io.project_io import (
    ProjectIOError,
    apply_project_to_session_state,
    project_from_json,
    project_from_session_state,
    project_to_json,
)
from concrete_pmm_pro.reporting import build_result_traceability_snapshot, check_report_readiness


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

    st.subheader("Save Project")
    project = project_from_session_state(st.session_state)
    st.download_button(
        "Download Project JSON",
        data=project_to_json(project),
        file_name="concrete_pmm_project.json",
        mime="application/json",
        use_container_width=True,
    )

    st.subheader("Load Project")
    uploaded_file = st.file_uploader("Upload Project JSON", type=["json"])
    if uploaded_file is not None and st.button("Load Project JSON", use_container_width=True):
        st.session_state["_pending_project_json"] = uploaded_file.getvalue().decode("utf-8")
        st.rerun()

    st.subheader("Project Summary")
    section_geometry = st.session_state.get("section_geometry")
    load_cases = st.session_state.get("load_cases", [])
    rebars = st.session_state.get("rebars", [])
    prestress_elements = st.session_state.get("prestress_elements", [])
    custom_points = st.session_state.get("custom_stress_check_points", [])
    include_default_stress_points = bool(st.session_state.get("include_default_stress_check_points", True))
    analysis_mode = st.session_state.get("analysis_mode_settings", AnalysisModeSettings())
    if isinstance(analysis_mode, dict):
        analysis_mode = AnalysisModeSettings.model_validate(analysis_mode)

    metric_cols = st.columns(5)
    metric_cols[0].metric("Section geometry", "Yes" if section_geometry is not None else "No")
    metric_cols[1].metric("Load cases", f"{len(load_cases):,}")
    metric_cols[2].metric("Rebars", f"{len(rebars):,}")
    metric_cols[3].metric("Prestress elements", f"{len(prestress_elements):,}")
    metric_cols[4].metric("Version", project.version)

    validity_cols = st.columns(2)
    rebar_valid = st.session_state.get("rebars_valid_for_analysis")
    prestress_valid = st.session_state.get("prestress_valid_for_analysis")
    validity_cols[0].metric("Rebars valid for analysis", "N/A" if rebar_valid is None else ("Yes" if rebar_valid else "No"))
    validity_cols[1].metric(
        "Prestress valid for analysis",
        "N/A" if prestress_valid is None else ("Yes" if prestress_valid else "No"),
    )

    st.subheader("Analysis Mode Summary")
    mode_cols = st.columns(4)
    mode_cols[0].metric("Member Type", analysis_mode_label(analysis_mode))
    mode_cols[1].metric("Analysis Workflow", analysis_mode.analysis_workflow)
    mode_cols[2].metric("PMM Workflow", "Yes" if analysis_mode.allow_pmm_workflow else "Caution")
    mode_cols[3].metric("SLS Workflow", "Yes" if analysis_mode.allow_sls_workflow else "No")
    st.info(
        "Beam/Girder workflow status: "
        + ("Future / not implemented" if analysis_mode.allow_beam_girder_placeholder else "Not active")
    )

    st.subheader("Custom SLS Stress Points Summary")
    active_custom_count = len([point for point in custom_points if getattr(point, "active", False)])
    point_cols = st.columns(3)
    point_cols[0].metric("Custom points", f"{len(custom_points):,}")
    point_cols[1].metric("Active custom points", f"{active_custom_count:,}")
    point_cols[2].metric("Include default stress points", "Yes" if include_default_stress_points else "No")

    st.subheader("Pre-Report Readiness")
    snapshot = build_result_traceability_snapshot(st.session_state)
    readiness = check_report_readiness(snapshot)
    readiness_cols = st.columns(5)
    readiness_cols[0].metric("Overall Status", readiness.overall_status)
    readiness_cols[1].metric("ULS PMM result", "Yes" if snapshot.pmm_result_available else "No")
    readiness_cols[2].metric("SLS result", "Yes" if snapshot.sls_result_available else "No")
    readiness_cols[3].metric("Warning count", f"{snapshot.warning_count:,}")
    readiness_cols[4].metric("High/Critical limitations", f"{snapshot.high_or_critical_limitation_count:,}")

    manifest = st.session_state.get("report_manifest")
    st.subheader("Report Foundation Summary")
    report_cols = st.columns(4)
    report_cols[0].metric("Report manifest", "Yes" if manifest is not None else "No")
    report_cols[1].metric("Available tables", f"{len([table for table in getattr(manifest, 'tables', []) if table.available]):,}" if manifest else "0")
    report_cols[2].metric("Available figures", f"{len([figure for figure in getattr(manifest, 'figures', []) if figure.available]):,}" if manifest else "0")
    report_cols[3].metric("Engineering limitations", f"{len(getattr(manifest, 'engineering_limitations', [])):,}" if manifest else f"{snapshot.limitation_count:,}")
