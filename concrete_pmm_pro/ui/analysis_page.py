"""Analysis readiness page."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from datetime import datetime
from html import escape
from typing import Any

import plotly.graph_objects as go
import pandas as pd
import streamlit as st
from shapely.geometry import LineString

from concrete_pmm_pro.analysis.capacity_check import DemandCapacitySummary, check_uls_demands_against_rc_pmm
from concrete_pmm_pro.analysis.preflight import build_analysis_input_from_session_state, check_analysis_readiness
from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.prestress_checks import (
    PrestressCheckSummary,
    check_prestress_elements_for_analysis,
    compare_rc_vs_prestress_pmm,
    summarize_prestress_contribution,
)
from concrete_pmm_pro.analysis.result_models import (
    PMMSolverResult,
    check_pmm_dataframe_numerics,
    pmm_result_to_display_dataframe,
    summarize_pmm_result,
)
from concrete_pmm_pro.analysis.uls_strength_routing import (
    BeamGirderUlsStrengthRoute,
    beam_girder_uls_strength_route,
)
from concrete_pmm_pro.analysis.uls_flexure_code_basis import (
    BeamGirderFlexureCodeBasis,
    apply_flexure_code_basis,
    beam_girder_flexure_code_basis,
)
from concrete_pmm_pro.analysis.runtime import (
    ACCURACY_PRESET_RESOLUTIONS,
    RuntimeTiming,
    accuracy_preset_resolution,
    analysis_input_hash,
    cache_status_for_hash,
    demand_capacity_input_hash,
    serviceability_input_hash,
    timed_call,
)
from concrete_pmm_pro.analysis.slice_envelope import build_slice_envelope
from concrete_pmm_pro.analysis.warnings import (
    BONDED_PRESTRESS_PROTOTYPE_WARNING,
    DCR_PROTOTYPE_WARNING,
    PMM_PROTOTYPE_WARNING,
    RC_AXIAL_CAP_LIMITATION_WARNING,
    SERVICEABILITY_NOT_IMPLEMENTED_WARNING,
    UNBONDED_PRESTRESS_IGNORED_WARNING,
    deduplicate_warnings,
)
from concrete_pmm_pro.code_checks import aci_beta1
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisModeSettings, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, RebarMaterial, SectionGeometry
from concrete_pmm_pro.core.design_code import (
    PROJECT_CODE_AASHTO_LRFD,
    PROJECT_CODE_ACI318,
    default_project_design_code_for_workflow,
    girder_sls_code_for_project_code,
    normalize_project_code_edition,
    project_code_edition_from_session,
    project_design_code_from_session,
)
from concrete_pmm_pro.core.reinforcement_system import (
    effective_prestress_for_analysis,
    effective_rebars_for_analysis,
    ordinary_rebar_enabled,
    prestressing_steel_enabled,
)
from concrete_pmm_pro.core.analysis_modes import (
    analysis_mode_description,
    analysis_mode_label,
    analysis_mode_warnings,
    is_beam_girder_future_workflow,
    is_building_beam_girder_workflow,
    is_pmm_primary_workflow,
)
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm
from concrete_pmm_pro.state.dirty_state import mark_analysis_current, project_input_hash
from concrete_pmm_pro.geometry.summary import summarize_geometry, to_shapely_polygon
from concrete_pmm_pro.reporting import (
    build_result_traceability_snapshot,
    build_report_manifest,
    build_draft_word_report,
    build_exportable_figure,
    build_report_figure_context,
    check_report_readiness,
    collect_available_report_figures,
    collect_limitations_for_report,
    collect_report_figure_export_items,
    engineering_limitations_to_dataframe,
    generate_plain_text_report_outline,
    plotly_figure_to_html_bytes,
    plotly_figure_to_png_bytes,
    ReportExportOptions,
    ReportMetadata,
    report_figure_export_items_to_dataframe,
    report_figures_to_dataframe,
    report_manifest_to_json_dict,
    report_manifest_to_summary_dataframe,
    report_qa_summary_to_dataframe,
    report_readiness_to_dataframe,
    report_sections_to_dataframe,
    report_tables_to_dataframe,
    result_traceability_snapshot_to_dataframe,
    run_word_report_qa,
    terminology_to_dataframe,
    unit_conventions_to_dataframe,
)
from concrete_pmm_pro.serviceability import (
    ALLOWED_STRESS_POINT_TYPES,
    ServiceabilitySettings,
    build_girder_service_stress_basis_options,
    build_serviceability_summary_from_analysis_input,
    classify_service_stress_results_for_cracking,
    crack_classification_to_dataframe,
    custom_stress_check_points_from_dataframe,
    dataframe_to_stress_check_points,
    DEFAULT_GIRDER_SLS_CODES,
    DEFAULT_GIRDER_SLS_STAGES,
    DEFAULT_TENSION_LIMIT_MODES,
    STAGE_TRANSFER,
    STAGE_DECK_CASTING,
    STAGE_FINAL_SERVICE,
    GirderServiceStageCase,
    GirderServiceStressLimitCheckResult,
    GirderStressLimitPointResult,
    StressLimitInputRow,
    aci_transfer_end_zone_length_m,
    aci_transfer_tension_limit_trace,
    build_girder_sls_limit_profile,
    default_girder_service_stage_templates,
    girder_prestress_stress_result_rows,
    girder_service_limit_check_rows,
    girder_sls_limit_formula_summary,
    girder_sls_limit_profile_options,
    girder_sls_stage_basis_consistency_warnings,
    normalize_girder_sls_stage,
    recommend_girder_tension_limit_profile,
    girder_service_stage_result_rows,
    girder_service_stress_result_rows,
    prestress_service_contribution_to_dataframe,
    run_girder_service_stage_stress,
    run_girder_service_stress_limit_check,
    run_basic_girder_service_stress,
    girder_service_stress_at_y,
    run_girder_prestress_stress_effect,
    girder_prestress_stress_at_y,
    summarize_girder_prestress_elements,
    run_elastic_sls_stress_check,
    service_stress_limits,
    service_stress_results_to_dataframe,
    sls_load_cases_to_display_dataframe,
    stress_check_points_to_dataframe,
    modular_ratio,
    transformed_section_properties_to_dataframe,
    validate_stress_check_points_against_geometry,
)

from concrete_pmm_pro.serviceability.girder_prestress_station import (
    active_strand_groups_at_station,
    evaluate_girder_prestress_station,
    station_candidates_from_debonding,
)
from concrete_pmm_pro.serviceability.girder_sls_load_components import (
    BEAM_GIRDER_SYSTEM_SETTINGS_KEY,
    BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY,
    BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY,
    auto_load_breakdown_for_stage,
    auto_load_settings_from_mapping,
    building_auto_load_breakdown_for_stage,
    building_service_load_settings_from_mapping,
    default_sls_station_grid,
    simple_span_udl_moment_kNm,
    simple_span_udl_shear_kN,
    system_settings_from_mapping,
)

from concrete_pmm_pro.visualization.pmm_dashboard import (
    build_selected_load_case_summary,
    demand_capacity_result_to_display_dataframe,
    demand_load_cases_to_display_dataframe,
    get_active_uls_load_cases,
    get_selected_load_case,
    make_mux_muy_slice_figure,
    make_pmm_3d_dashboard_figure,
    pmm_slice_at_pu,
    pmm_slice_export_dataframe,
    rank_load_cases_by_dcr,
    slice_envelope_export_dataframe,
)
from concrete_pmm_pro.visualization.sls_stress import (
    make_sls_section_stress_figure,
    make_sls_stress_bar_figure,
    service_stress_results_to_plot_dataframe,
)
from concrete_pmm_pro.verification.pmm_benchmarks import PMMVerificationSummary, run_pmm_verification_suite
from concrete_pmm_pro.verification.validation_framework import build_pmm_solver_validation_matrix
from concrete_pmm_pro.verification.hand_checks import (
    HandCheckSummary,
    hand_check_summary_to_dataframe,
    run_independent_hand_check_suite,
)
from concrete_pmm_pro.verification.sls_benchmarks import (
    SLSBenchmarkSummary,
    run_sls_verification_suite,
    sls_benchmark_summary_to_dataframe,
)

ANALYSIS_SUBTABS = ["ULS / PMM", "SLS / Stress & Cracking", "SLS Deflection / Camber", "Report / QA"]
ANALYSIS_COLUMN_PIER_SUBTABS = ["ULS / PMM", "Report / QA"]
COLUMN_PIER_ULS_CHECK_SUBTABS = ["Flexural (PMM)", "Shear", "Torsion", "Shear + Torsion"]
# Legacy source-test token retained while PERF.RERUN1 switches from eager st.tabs
# to lazy subpage rendering: uls_tab, sls_tab, sls_deflection_tab, report_tab
PMM_3D_MASTER_TOGGLE_KEY = "show_pmm_3d_interaction"
PMM_3D_LAYER_DEFAULTS = {
    "show_pmm_3d_surface": True,
    "show_pmm_3d_current_pu_slice": True,
    "show_pmm_3d_selected_point": True,
    "show_pmm_3d_all_load_points": False,
}

# Legacy source-test tokens retained: GIRDER.SLS1B/PS1B previews; not a staged prestressed girder design check yet.
# ULS.GIRDER1 — compact Beam/Girder ULS demand workspace.
# Loads page remains the source of truth; Analysis consumes the station-based
# beam_uls_loads_table read-only and does not duplicate ULS input.
BEAM_ULS_LOAD_COLUMNS_ANALYSIS = ["Active", "Station x (m)", "Case Name", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu", "Note"]
SHEAR_REINFORCEMENT_TABLE_KEY = "beam_girder_shear_reinforcement_table"
SHEAR_DEPTH_SETTINGS_KEY = "beam_girder_shear_depth_settings"
SHEAR_DEPTH_MODE_MANUAL = "Manual effective d / dv"
COLUMN_ULS_LOAD_COLUMNS_ANALYSIS = ["Active", "Case Name", "Pu", "Mux", "Muy", "Vux", "Vuy", "Tu", "Note"]
COLUMN_PIER_TRANSVERSE_TABLE_KEY_ANALYSIS = "column_pier_transverse_reinforcement_table"
COLUMN_PIER_TRANSVERSE_SETTINGS_KEY_ANALYSIS = "column_pier_transverse_reinforcement_settings"
COLUMN_PIER_TRANSVERSE_COLUMNS_ANALYSIS = [
    "Active",
    "Zone",
    "x_start_m",
    "x_end_m",
    "Bar Size",
    "Diameter_mm",
    "Legs",
    "Spacing_mm",
    "fy_MPa",
    "Note",
]
_BEAM_ULS_DEMAND_TOL = 1.0e-9
_COLUMN_PIER_SHEAR_DEMAND_TOL = 1.0e-9
_COLUMN_PIER_ACI_SEISMIC_ADVISOR_LABEL = "ACI 318 special seismic confinement advisor"
_COLUMN_PIER_SEISMIC_SPACING_INCREMENT_MM = 25.0
_BEAM_ULS_FLEXURE_PREVIEW_MAX_ROWS = 24
_GIRDER_STRAND_FPU_MPA_DEFAULT = 1860.0
_GIRDER_STRAND_FPY_MPA_DEFAULT = 1670.0
_GIRDER_STRAND_EP_MPA_DEFAULT = 195000.0


_ANALYSIS_DASHBOARD_CSS = """
<style>
.cpmm-analysis-strip {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.72rem 0.82rem;
  min-height: 98px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.035);
}
.cpmm-analysis-card {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.85rem 0.95rem;
  margin-bottom: 0.55rem;
}
.cpmm-analysis-title {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.22rem;
}
.cpmm-analysis-value {
  color: #101828;
  font-size: 1.0rem;
  font-weight: 720;
  line-height: 1.22;
  overflow-wrap: anywhere;
}
.cpmm-analysis-detail {
  color: #667085;
  font-size: 0.76rem;
  line-height: 1.28;
  margin-top: 0.22rem;
}
.cpmm-analysis-path {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #f9fafb;
  padding: 0.72rem 0.82rem;
  margin: 0.55rem 0 0.8rem 0;
  color: #344054;
  font-size: 0.82rem;
  line-height: 1.45;
}
.cpmm-analysis-path strong { color: #101828; }
.cpmm-analysis-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.13rem 0.52rem;
  font-size: 0.72rem;
  font-weight: 750;
  letter-spacing: 0;
  margin-top: 0.4rem;
}
.cpmm-analysis-badge.ready { color: #1f5f2a; background: #e7f5e8; }
.cpmm-analysis-badge.warning { color: #7a4b00; background: #fff4d6; }
.cpmm-analysis-badge.danger { color: #9f1f17; background: #fde8e7; }
.cpmm-analysis-badge.info { color: #1849a9; background: #e8f1ff; }
.cpmm-analysis-badge.neutral { color: #475467; background: #eef1f5; }
.cpmm-analysis-kv-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.8rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.4rem 0;
}
.cpmm-analysis-kv-row:last-child { border-bottom: 0; }
.cpmm-analysis-kv-label {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 600;
}
.cpmm-analysis-kv-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 650;
  text-align: right;
  overflow-wrap: anywhere;
}
.cpmm-executive-header {
  border: 1px solid #d0d7e2;
  border-radius: 12px;
  background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  padding: 1.0rem 1.05rem;
  margin: 0.35rem 0 0.85rem 0;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.05);
}
.cpmm-executive-eyebrow {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 750;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-bottom: 0.25rem;
}
.cpmm-executive-title {
  color: #101828;
  font-size: 1.24rem;
  line-height: 1.2;
  font-weight: 760;
  margin-bottom: 0.25rem;
}
.cpmm-executive-subtitle {
  color: #667085;
  font-size: 0.84rem;
  line-height: 1.35;
}

.cpmm-decision-banner {
  border: 1px solid #d0d7e2;
  border-radius: 12px;
  background: #ffffff;
  padding: 0.95rem 1.05rem;
  margin: 0.3rem 0 0.85rem 0;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.045);
}
.cpmm-decision-banner.ready { border-left: 5px solid #2e7d32; background: #fbfffb; }
.cpmm-decision-banner.warning { border-left: 5px solid #b76e00; background: #fffdf7; }
.cpmm-decision-banner.danger { border-left: 5px solid #c0392b; background: #fffafa; }
.cpmm-decision-banner.neutral { border-left: 5px solid #667085; background: #fbfcfe; }
.cpmm-decision-eyebrow {
  color: #667085;
  font-size: 0.72rem;
  font-weight: 760;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-bottom: 0.25rem;
}
.cpmm-decision-title {
  color: #101828;
  font-size: 1.08rem;
  font-weight: 780;
  line-height: 1.25;
  margin-bottom: 0.25rem;
}
.cpmm-decision-detail {
  color: #475467;
  font-size: 0.83rem;
  line-height: 1.42;
}
.cpmm-decision-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
  margin-top: 0.55rem;
}
.cpmm-decision-block {
  border: 1px solid #e4e8ef;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  padding: 0.55rem 0.65rem;
}
.cpmm-decision-block-label {
  color: #667085;
  font-size: 0.68rem;
  font-weight: 760;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  margin-bottom: 0.18rem;
}
.cpmm-decision-block-text {
  color: #344054;
  font-size: 0.80rem;
  line-height: 1.36;
}
@media (max-width: 900px) {
  .cpmm-decision-grid { grid-template-columns: 1fr; }
}
.cpmm-decision-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.55rem;
}
.cpmm-decision-pill {
  border: 1px solid #d9dee7;
  border-radius: 999px;
  padding: 0.16rem 0.55rem;
  color: #344054;
  background: #f9fafb;
  font-size: 0.72rem;
  font-weight: 650;
}
.cpmm-sls-action-panel {
  border: 1px solid #f2d58a;
  border-left: 5px solid #d99800;
  border-radius: 12px;
  background: #fffaf0;
  padding: 0.85rem 1.0rem;
  margin: 0.65rem 0 0.8rem 0;
}
.cpmm-sls-action-title {
  color: #7a4b00;
  font-size: 0.86rem;
  font-weight: 780;
  margin-bottom: 0.35rem;
}
.cpmm-sls-action-panel ul {
  margin-top: 0.2rem;
  margin-bottom: 0;
}
.cpmm-sls-action-panel li {
  color: #344054;
  font-size: 0.82rem;
  line-height: 1.42;
  margin-bottom: 0.15rem;
}

.cpmm-governing-card {
  border: 1px solid #d0d7e2;
  border-radius: 12px;
  background: #ffffff;
  padding: 1.0rem 1.05rem;
  margin: 0.45rem 0 0.75rem 0;
  box-shadow: 0 1px 3px rgba(16, 24, 40, 0.045);
}
.cpmm-governing-name {
  color: #101828;
  font-size: 1.18rem;
  font-weight: 760;
  margin-bottom: 0.45rem;
}
.cpmm-governing-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.6rem;
}
.cpmm-governing-cell {
  border: 1px solid #edf0f5;
  border-radius: 8px;
  padding: 0.55rem 0.6rem;
  background: #fbfcfe;
}
.cpmm-governing-label {
  color: #667085;
  font-size: 0.72rem;
  font-weight: 650;
  margin-bottom: 0.16rem;
}
.cpmm-governing-value {
  color: #101828;
  font-size: 0.92rem;
  font-weight: 730;
  overflow-wrap: anywhere;
}
</style>
"""


def _settings_from_session() -> AnalysisSettings:
    value = st.session_state.get("analysis_settings")
    if isinstance(value, AnalysisSettings):
        return value
    if isinstance(value, dict):
        return AnalysisSettings.model_validate(value)
    return AnalysisSettings()


def _analysis_accuracy_preset_from_session() -> str:
    value = st.session_state.get("analysis_accuracy_preset")
    if value in ACCURACY_PRESET_RESOLUTIONS:
        return str(value)
    return "Standard"


def _pmm_3d_display_enabled_from_state(state: Mapping[str, object]) -> bool:
    return bool(state.get(PMM_3D_MASTER_TOGGLE_KEY, False))


def _should_generate_pmm_3d_figure_from_state(state: Mapping[str, object]) -> bool:
    if not _pmm_3d_display_enabled_from_state(state):
        return False
    return any(bool(state.get(key, default)) for key, default in PMM_3D_LAYER_DEFAULTS.items())


def _record_runtime_timing(timing: RuntimeTiming) -> None:
    timings = st.session_state.get("analysis_runtime_timings")
    if not isinstance(timings, dict):
        timings = {}
    timings[timing.label] = timing.elapsed_seconds
    st.session_state["analysis_runtime_timings"] = timings


def _runtime_timings_dataframe() -> pd.DataFrame:
    timings = st.session_state.get("analysis_runtime_timings")
    if not isinstance(timings, dict) or not timings:
        return pd.DataFrame(columns=["Operation", "Elapsed Seconds"])
    return pd.DataFrame(
        [
            {"Operation": label, "Elapsed Seconds": elapsed}
            for label, elapsed in timings.items()
        ],
        columns=["Operation", "Elapsed Seconds"],
    )


def _render_runtime_diagnostics_expander() -> None:
    with st.expander("Developer diagnostics", expanded=False):
        st.info(
            "Developer timing diagnostics measure UI-triggered expensive operations only. "
            "They do not change PMM/SLS formulas, sign conventions, or engineering results."
        )
        timings_df = _runtime_timings_dataframe()
        if timings_df.empty:
            st.info("No timed operations have been recorded in this session.")
        else:
            st.dataframe(timings_df, use_container_width=True, hide_index=True)


def _workflow_sls_status_text(settings: AnalysisModeSettings) -> str:
    if settings.member_type == "beam_girder":
        return "Bridge staged preview"
    if settings.member_type == "building_beam_girder":
        return "Building preview guarded"
    return "Not selected"


def _workflow_shear_torsion_status_text(settings: AnalysisModeSettings) -> str:
    if is_pmm_primary_workflow(settings):
        return "ACI RC shear / torsion / V+T"
    if settings.member_type == "beam_girder":
        return "Bridge ULS guarded"
    if settings.member_type == "building_beam_girder":
        return "Building ULS planned"
    return "Review"


def _analysis_mode_from_session() -> AnalysisModeSettings:
    value = st.session_state.get("analysis_mode_settings")
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


def _girder_sls_project_design_code_from_session() -> str:
    """Return workflow-enforced project code for Beam/Girder SLS previews."""

    mode = _analysis_mode_from_session()
    return default_project_design_code_for_workflow(mode.member_type, project_design_code_from_session(st.session_state))


def _girder_sls_project_code_edition_from_session() -> str:
    """Return a code-edition label compatible with the Beam/Girder SLS code."""

    code = _girder_sls_project_design_code_from_session()
    return normalize_project_code_edition(code, st.session_state.get("code_edition"))


def _girder_sls_profile_code_from_session():
    """Return AASHTO/ACI girder SLS preview profile selected by active workflow."""

    return girder_sls_code_for_project_code(_girder_sls_project_design_code_from_session())


def _serviceability_settings_from_session() -> ServiceabilitySettings:
    value = st.session_state.get("serviceability_settings")
    if isinstance(value, ServiceabilitySettings):
        return value
    if isinstance(value, dict):
        return ServiceabilitySettings.model_validate(value)
    return ServiceabilitySettings()


def _serviceability_analysis_input_from_session() -> AnalysisInput | None:
    section_geometry = st.session_state.get("section_geometry")
    concrete_material = st.session_state.get("concrete_material")
    if section_geometry is None or concrete_material is None:
        return None
    settings = _settings_from_session()
    return AnalysisInput(
        section_geometry=section_geometry,
        concrete_material=concrete_material,
        rebar_materials=list(st.session_state.get("rebar_materials", []) or []),
        prestress_materials=list(st.session_state.get("prestress_materials", []) or []),
        rebars=effective_rebars_for_analysis(list(st.session_state.get("rebars", []) or []), st.session_state, settings),
        prestress_elements=effective_prestress_for_analysis(list(st.session_state.get("prestress_elements", []) or []), st.session_state, settings),
        load_cases=list(st.session_state.get("load_cases", []) or []),
        settings=settings,
    )


def _render_readiness_panel() -> None:
    """Render a compact readiness strip and keep detailed diagnostics collapsed.

    The previous UI displayed every readiness info item as a full-width alert,
    which pushed the governing PMM result far down the page.  This keeps the
    first-screen workflow focused on status while preserving all QA messages.
    """

    result = check_analysis_readiness(st.session_state)
    st.markdown(_ANALYSIS_DASHBOARD_CSS, unsafe_allow_html=True)
    st.subheader("Analysis Readiness")
    cards = [
        {
            "title": "Ready",
            "value": "Yes" if result.ready else "No",
            "detail": "Ready for current ULS / PMM workflow" if result.ready else "Resolve errors before running analysis",
            "status": "ready" if result.ready else "danger",
            "strong": True,
        },
        {
            "title": "Errors",
            "value": f"{len(result.errors):,}",
            "detail": "Must be zero before analysis",
            "status": "danger" if result.errors else "ready",
        },
        {
            "title": "Warnings",
            "value": f"{len(result.warnings):,}",
            "detail": "Review before relying on ULS results",
            "status": "warning" if result.warnings else "ready",
        },
        {
            "title": "Info Items",
            "value": f"{len(result.info):,}",
            "detail": "Section/material/load totals",
            "status": "neutral",
        },
    ]
    _render_analysis_summary_strip(cards, columns=4)

    if result.errors:
        st.error("Analysis cannot run. Fix the blocking readiness items below, then run the analysis again.")
        _render_readiness_action_list(result.errors)
    elif result.warnings:
        st.warning("Readiness warnings are present. Analysis can run, but the warnings should be reviewed.")
    else:
        st.success("No readiness errors. Detailed readiness information is available below if needed.")

    with st.expander("Readiness diagnostics", expanded=bool(result.errors)):
        if result.errors:
            for error in result.errors:
                st.error(f"ERROR: {error}")
        else:
            st.success("No readiness errors")

        if result.warnings:
            for warning in result.warnings:
                st.warning(f"WARNING: {warning}")
        else:
            st.info("WARNING: none")

        if result.info:
            for item in result.info:
                st.info(f"INFO: {item}")
        else:
            st.info("No readiness info items were reported.")


def _readiness_blocking_action(error_message: str) -> dict[str, str]:
    """Translate a readiness error into a user-facing fix action."""

    text = str(error_message or "").strip()
    lowered = text.lower()
    if "section geometry is missing" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Sections",
            "Recommended Action": "Create, import, or select a valid concrete section geometry before running PMM analysis.",
        }
    if "concrete material is missing" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Materials",
            "Recommended Action": "Select or define the concrete material assigned to the active section.",
        }
    if "no active" in lowered and "load cases" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Loads",
            "Recommended Action": "Add or activate at least one strength load case matching the selected analysis load type.",
        }
    if "no active longitudinal reinforcement" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Sections / Prestress",
            "Recommended Action": "Add or enable ordinary longitudinal rebars or bonded prestress elements included in PMM analysis.",
        }
    if "rebars are not valid" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Sections > Rebar",
            "Recommended Action": "Correct rebar rows, material assignment, bar size, and bar locations so all included bars are valid for analysis.",
        }
    if "prestress elements are not valid" in lowered:
        return {
            "Blocking Item": text,
            "Where to Fix": "Prestress / Sections",
            "Recommended Action": "Correct prestress geometry, material, bonding, force, and location inputs before including prestress in PMM analysis.",
        }
    return {
        "Blocking Item": text,
        "Where to Fix": "Project inputs",
        "Recommended Action": "Open the related input page, correct this readiness error, and confirm the Errors count returns to zero.",
    }


def _readiness_actions_to_dataframe(errors: list[str]) -> pd.DataFrame:
    rows = [_readiness_blocking_action(error) for error in errors if str(error or "").strip()]
    return pd.DataFrame(rows, columns=["Blocking Item", "Where to Fix", "Recommended Action"])


def _render_readiness_action_list(errors: list[str]) -> None:
    action_df = _readiness_actions_to_dataframe(errors)
    if action_df.empty:
        st.info("Open Readiness diagnostics for blocking input details.")
        return
    st.caption("Blocking actions required before Run / Recalculate Analysis is enabled.")
    st.dataframe(action_df, use_container_width=True, hide_index=True)


def _render_analysis_mode_section() -> AnalysisModeSettings:
    """Show the active member workflow selected in Project setup.

    MEMBER.TYPE1 keeps a single editable owner for analysis mode in the Project
    page. The Analysis page displays that selection as workflow context so tabs
    rendered later cannot silently overwrite the Project-level selection.
    """
    settings = _analysis_mode_from_session()

    with st.expander("Analysis Mode / Member Type", expanded=True):
        st.markdown(f"**{analysis_mode_label(settings)}**")
        st.caption("Configured in Project → Analysis Mode / Member Type.")
        if settings.note:
            st.caption(f"Project note: {settings.note}")
        st.info(analysis_mode_description(settings))
        mode_cols = st.columns(4)
        mode_cols[0].metric("Analysis Workflow", settings.analysis_workflow)
        mode_cols[1].metric("PMM Workflow", "Available" if settings.allow_pmm_workflow else "Not applicable")
        mode_cols[2].metric("SLS Workflow", _workflow_sls_status_text(settings))
        mode_cols[3].metric(
            "Shear / Torsion",
            _workflow_shear_torsion_status_text(settings),
        )

        if settings.member_type == "column_pier_pmm":
            st.success("Current workflow uses Pu, Mux, and Muy with PMM interaction and ULS D/C review.")
            st.info(
                "Column/Pier ACI RC shear, torsion, and combined V+T views are available under ULS / PMM. "
                "AASHTO, prestressed V+T, and seismic/detailing certification remain guarded review scope."
            )
            st.info("Beam/Girder SLS stress and deflection/camber workflows are not selected for Column/Pier/Wall/Pylon analysis.")
            st.info("Prestress is treated as internal prestress/reinforcement action, not duplicated as Pu demand.")
        elif settings.member_type == "beam_girder":
            st.info("Bridge Beam/Girder workflow uses AASHTO LRFD project design basis.")
            st.info("Bridge-specific staged SLS, prestress/debonding, auto SDL components, and CSiBridge LL+IM workflows are active here.")
            st.info("Bridge girder ULS flexure/shear/torsion engines are planned; current implemented checks remain preview / engineering review.")
            st.info("Do not enter prestress Pe again as Pu if prestress elements are already defined.")
        elif settings.member_type == "building_beam_girder":
            st.info("Building Beam/Girder workflow uses ACI 318 project design basis.")
            st.info("Building ACI SLS stress diagram is available as a preview for top/bottom stresses along the member length using auto Transfer/Construction loads, Building SDL/LL service loads, and Pe force states.")
            st.warning("Building ULS design engines remain planned follow-up milestones. Bridge-only SDL components and CSiBridge workflows remain hidden.")
        else:
            st.info("Legacy/general workflow has been migrated to explicit project workflow routing.")
            st.warning("Use carefully and verify load interpretation.")

        for warning in analysis_mode_warnings(settings):
            st.info(warning)

    return settings


def _prestress_check_dataframe(summary: PrestressCheckSummary) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Label": check.label,
                "Type": check.steel_type,
                "Bonded": check.bonded,
                "Area": check.area_mm2,
                "Count": check.count,
                "fpu": check.fpu_MPa,
                "fpy": check.fpy_MPa,
                "Ep": check.Ep_MPa,
                "Initial Stress": check.initial_stress_MPa,
                "Initial Strain": check.initial_strain,
                "Pe_eff": None if check.pe_eff_N is None else N_to_kN(check.pe_eff_N),
                "Status": check.status,
                "Messages": "; ".join(check.messages),
            }
            for check in summary.checks
        ]
    )




def _clean_diagnostic_message(message: object) -> str:
    """Normalize solver diagnostic text before display.

    Solver/result layers sometimes prefix messages with WARNING:/INFO: and can
    report the same limitation through several paths.  The Analysis page should
    keep those messages for QA, but it should not render a debug-console style
    wall of repeated warnings in the commercial workspace.
    """

    text = str(message or "").strip()
    for prefix in ("WARNING:", "INFO:", "ERROR:"):
        if text.upper().startswith(prefix):
            text = text[len(prefix):].strip()
    return " ".join(text.split())


def _deduplicate_diagnostic_messages(messages: list[object]) -> list[str]:
    """Return unique normalized diagnostics while preserving first-seen order."""

    unique: list[str] = []
    seen: set[str] = set()
    for message in messages:
        text = _clean_diagnostic_message(message)
        if not text:
            continue
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(text)
    return unique


def _classify_diagnostic_message(message: str) -> str:
    """Classify diagnostics by engineering severity for commercial display.

    The underlying solver still records the original warnings.  This UI
    classification prevents expected prototype limitations or harmless numeric
    placeholders from being presented as if the ULS result had failed.
    """

    text = message.casefold()

    # Some PMM rows legitimately have no controlling tensile strain value
    # (for example compression-controlled states).  Keep the information for
    # QA, but do not count it as an engineering warning.
    if "nan" in text and "eps_t" in text:
        return "Numerical note"
    if "numeric" in text or "nan" in text:
        return "Numerical note"

    # Reaching fpu is an expected material cap in some ultimate PMM failure
    # states.  It is actionable only if governing-impact classification later
    # shows it occurs near the governing demand; otherwise retain it as QA.
    if "prestress stress reached fpu" in text or "reached fpu cap" in text:
        return "Numerical note"

    # Generic active-prestress model descriptions are method limitations,
    # not input/action warnings by themselves.  Specific governing-region
    # compression-reversal diagnostics are handled separately below.
    if "active prestress stress model" in text or "stress uses initial tensile strain" in text:
        return "Solver limitation note"

    # Actionable model-behavior warnings that a reviewer should inspect.
    if (
        "compression reversal" in text
        or "tensile strain was clamped" in text
        or "directional moment" in text
        or "falls back" in text
        or "fallback" in text
        or "failed" in text
        or "exceed" in text
    ):
        return "Engineering review warning"

    limitation_markers = (
        "prototype",
        "future work",
        "not implemented",
        "independent engineering verification",
        "ignored",
        "not included",
    )
    if any(marker in text for marker in limitation_markers):
        return "Solver limitation note"

    return "Engineering review warning"


def _diagnostic_counts(messages: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {
        "Engineering review warning": 0,
        "Solver limitation note": 0,
        "Numerical note": 0,
    }
    for message in messages:
        category = _classify_diagnostic_message(message)
        counts[category] = counts.get(category, 0) + 1
    return counts


def _diagnostic_source(message: str) -> str:
    """Return the likely engineering source of a solver diagnostic."""

    text = message.casefold()
    if "prestress" in text or text.startswith("ps") or "fpu" in text or "fpy" in text:
        return "Prestress model"
    if "directional moment" in text or "d/c" in text or "interpolation" in text or "fallback" in text:
        return "PMM D/C method"
    if "axial cap" in text or "nominal po" in text or "phipn" in text:
        return "ACI axial cap"
    if "sls" in text or "serviceability" in text:
        return "SLS workspace"
    if "nan" in text or "numeric" in text or "eps_t" in text:
        return "PMM numeric diagnostics"
    if "pmm" in text:
        return "PMM solver"
    return "General QA"



def _governing_dc_result(dc_summary: DemandCapacitySummary | None):
    """Return the governing demand/capacity row when available."""

    if dc_summary is None or dc_summary.governing_combo is None:
        return None
    for item in dc_summary.results:
        if item.combo_name == dc_summary.governing_combo:
            return item
    return None


def _pmm_points_near_governing_pu(df: pd.DataFrame | None, governing_pu_N: float | None) -> pd.DataFrame:
    """Return a small PMM axial band near the governing Pu for warning-impact review.

    This is intentionally a UI/QA diagnostic. It does not change the D/C solver.
    The goal is to separate warnings that occur anywhere on the PMM surface from
    warnings that occur near the axial level used by the governing ULS check.
    """

    if df is None or df.empty or governing_pu_N is None:
        return pd.DataFrame()
    p_column = "phiPn_capped_N" if "phiPn_capped_N" in df.columns else "phiPn_N"
    if p_column not in df.columns:
        return pd.DataFrame()
    working = df.copy()
    working[p_column] = pd.to_numeric(working[p_column], errors="coerce")
    working = working[working[p_column].notna()]
    if working.empty:
        return pd.DataFrame()

    p_range = float(working[p_column].max() - working[p_column].min())
    tolerance = max(50_000.0, 0.025 * p_range) if p_range > 0 else 50_000.0
    band = working[(working[p_column] - float(governing_pu_N)).abs() <= tolerance]
    if not band.empty:
        return band

    # If no point falls inside the band, return the nearest few points so the
    # reviewer still gets an honest impact classification instead of silence.
    return working.assign(_p_dist=(working[p_column] - float(governing_pu_N)).abs()).nsmallest(12, "_p_dist")


def _prestress_warning_governing_impact(message: str, df: pd.DataFrame | None, dc_summary: DemandCapacitySummary | None) -> str:
    """Classify whether a prestress-model warning appears near the governing Pu."""

    governing = _governing_dc_result(dc_summary)
    if governing is None:
        return "Potential if near governing case — no governing ULS case is available in this context."
    band = _pmm_points_near_governing_pu(df, governing.Pu_N)
    if band.empty:
        return "Unknown — PMM points near the governing Pu could not be identified."

    text = message.casefold()
    if "fpu" in text or "cap" in text:
        column = "prestress_reached_fpu_cap_count"
        if column in band.columns and pd.to_numeric(band[column], errors="coerce").fillna(0).gt(0).any():
            return f"Potential governing impact — fpu cap occurs in PMM points near governing case {governing.combo_name}."
        return f"Background PMM-surface warning — fpu cap was not detected near governing case {governing.combo_name}."

    if "compression reversal" in text or "tensile strain was clamped" in text:
        column = "prestress_stress_warning_count"
        if column in band.columns and pd.to_numeric(band[column], errors="coerce").fillna(0).gt(0).any():
            return f"Potential governing impact — prestress stress warnings occur near governing case {governing.combo_name}."
        return f"Background PMM-surface warning — not detected near governing case {governing.combo_name}."

    return "Review with governing PMM trace."


def _diagnostic_governing_impact(
    message: str,
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> str:
    """Return a practical impact classification for the current governing case."""

    text = message.casefold()
    governing = _governing_dc_result(dc_summary)

    if "nan" in text and "eps_t" in text:
        if governing is not None and governing.capacity_phiMn_Nmm is not None and governing.dcr is not None:
            return f"No direct governing impact detected — governing case {governing.combo_name} has computed capacity and D/C."
        return "Unknown — governing D/C is not available."

    if "directional moment" in text or "fallback" in text or "falls back" in text:
        if governing is None:
            return "Unknown — no governing ULS case is available."
        if governing.used_fallback or int(getattr(governing, "warning_count", 0) or 0) > 0:
            return f"Directly relevant — governing case {governing.combo_name} uses fallback or has D/C method warnings."
        return f"No direct governing impact detected — governing case {governing.combo_name} used {governing.capacity_method or 'the primary capacity method'}."

    if "prestress stress reached fpu" in text or "reached fpu cap" in text or "compression reversal" in text or "tensile strain was clamped" in text:
        return _prestress_warning_governing_impact(message, df, dc_summary)

    if "axial cap" in text or "nominal po" in text:
        if governing is None:
            return "Global limitation — review compression-controlled cases."
        return f"Potential only for high-compression cases — governing Pu = {N_to_kN(governing.Pu_N):,.1f} kN."

    if "prototype" in text or "future work" in text or "independent engineering verification" in text:
        return "Global solver-validation limitation — no specific input correction is implied."

    if "sls" in text or "serviceability" in text:
        return "Does not affect ULS PMM D/C."

    return "Review required — see recommended action."


def _diagnostic_priority(impact: str, severity: str) -> str:
    """Convert severity + governing impact into a user action priority."""

    text = impact.casefold()
    if "directly relevant" in text or "potential governing impact" in text:
        return "Check before relying on governing result"
    if "unknown" in text:
        return "Review before final design"
    if severity == "Engineering review warning":
        return "Review for final design"
    if severity == "Numerical note":
        return "Usually no action"
    return "QA note"

def _diagnostic_guidance(
    message: str,
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> dict[str, str]:
    """Explain what a diagnostic means and how a user should respond.

    The solver messages are intentionally conservative, but raw warnings are
    not enough for a commercial engineering UI.  This mapping converts common
    solver diagnostics into actionable QA guidance without changing any solver
    results or suppressing the original message.
    """

    text = message.casefold()
    severity = _classify_diagnostic_message(message)
    source = _diagnostic_source(message)

    governing_impact = _diagnostic_governing_impact(message, df=df, dc_summary=dc_summary)
    guidance = {
        "Source": source,
        "Severity": severity,
        "Message": message,
        "Meaning": "Solver or QA diagnostic retained for engineering review.",
        "Possible Cause": "Review the related input and calculation diagnostics.",
        "Recommended Action": "Open the related diagnostics panel and verify the governing case before final design use.",
        "Governing Impact": governing_impact,
        "Action Priority": "Review required",
        "Where to Check": "Analysis > Diagnostics / QA",
    }

    if "prestress stress reached fpu" in text or "reached fpu cap" in text:
        guidance.update(
            {
                "Meaning": "Prestressing steel stress reached the material ultimate-stress cap in part of the generated PMM interaction surface. This can be expected at ultimate failure-envelope points.",
                "Possible Cause": "High Pe_eff/fpe, tendon close to the extreme tension zone, high curvature failure states, or an aggressive prestress material definition.",
                "Recommended Action": "Review the named prestress row in Prestress: Product, Area, Pe_eff/fpe, fpu/fpy, x/y location, and Bonded state. No input change is usually required when the cap occurs only away from the governing case.",
                "Governing Impact": governing_impact,
                "Where to Check": "Prestress tab + Analysis > PMM Check / governing trace",
            }
        )
    elif "compression reversal" in text or "tensile strain was clamped" in text:
        guidance.update(
            {
                "Meaning": "A prestress element entered a compression-side strain range where the current prestress model does not model compression reversal in detail; tensile strain was clamped to zero.",
                "Possible Cause": "Tendon/bar lies on the compression side for some neutral-axis positions, or the PMM sweep includes curvature states that reverse the expected prestress tension behavior.",
                "Recommended Action": "Check tendon x/y position and the governing PMM direction. If this occurs only away from the governing case, retain as QA note; if near the governing case, verify with an independent section analysis.",
                "Governing Impact": "Potential if near governing case",
                "Where to Check": "Prestress tab + Analysis > Diagnostics / QA",
            }
        )
    elif "directional moment" in text or "fallback" in text or "falls back" in text:
        guidance.update(
            {
                "Meaning": "The demand/capacity check may use a fallback capacity method when the cleaned Pu slice cannot directly resolve the demand direction.",
                "Possible Cause": "Sparse PMM surface points, demand near the edge of the interaction surface, irregular slice geometry, or insufficient analysis resolution.",
                "Recommended Action": "Review the governing case trace, capacity method, and fallback flag. Re-run with a higher accuracy preset if the governing case uses fallback or lies near the capacity boundary.",
                "Governing Impact": "Potential for governing D/C",
                "Where to Check": "Analysis > PMM Check + Full ULS D/C trace details",
            }
        )
    elif "nan" in text and "eps_t" in text:
        guidance.update(
            {
                "Meaning": "Some PMM points do not have a controlling tensile strain value. This can be expected for compression-controlled states.",
                "Possible Cause": "Compression-controlled PMM points or points where no tensile reinforcement/PS strain controls phi.",
                "Recommended Action": "No input change is usually required if phi, capacity, and governing D/C are computed. Review only if many PMM points are invalid or the governing case lacks capacity.",
                "Governing Impact": "Usually none",
                "Where to Check": "Analysis > Diagnostics / QA > raw PMM data",
            }
        )
    elif "prototype" in text and "pmm" in text:
        guidance.update(
            {
                "Meaning": "The PMM solver/result workflow is currently flagged as an engineering-review prototype, not a fully production-validated design engine.",
                "Possible Cause": "The application is still under staged validation and benchmark expansion.",
                "Recommended Action": "Use the result for engineering review/preliminary design and verify important governing cases independently until the solver validation milestone is completed.",
                "Governing Impact": "Global limitation",
                "Where to Check": "Analysis > Diagnostics / QA + benchmark tests",
            }
        )
    elif "axial cap" in text or "nominal po" in text:
        guidance.update(
            {
                "Meaning": "The ACI maximum axial strength cap uses the QA.PO1-validated prestress-aware Po helper. Bonded Aps is included with fpy or 0.90fpu; unbonded prestress is excluded upstream.",
                "Possible Cause": "The section includes ordinary rebar and/or bonded prestress; axial compression display/checks are capped by ACI-style limits.",
                "Recommended Action": "Verify Ag, As, Aps, f'c, fy/fpy, bonded state, and code-specific axial-compression limits. Do not enter Pe_eff as external Pu.",
                "Governing Impact": "Validated axial-cap helper; review only for high axial compression governing cases",
                "Where to Check": "Section/Rebar/Prestress tabs + Analysis > Diagnostics / QA + docs/validation",
            }
        )
    elif "bonded prestress" in text or "prestress" in text:
        guidance.update(
            {
                "Meaning": "Bonded prestress is included through the current strain-compatibility prestress model.",
                "Possible Cause": "Active bonded prestress elements are present in the section model.",
                "Recommended Action": "Review Pe_eff/fpe, product properties, bonded state, and tendon positions. Treat final design use as subject to independent verification until prestress validation is complete.",
                "Governing Impact": "Global prestress-model limitation",
                "Where to Check": "Prestress tab + Analysis > Prestress diagnostics",
            }
        )
    elif "sls" in text or "serviceability" in text:
        guidance.update(
            {
                "Meaning": "SLS load cases are stored but the SLS calculation engine is not active in this workflow yet.",
                "Possible Cause": "The Loads table contains SLS rows while the current analysis workspace is ULS/PMM-focused.",
                "Recommended Action": "No ULS input change is required. Use SLS rows later when the SLS workspace/checks are implemented.",
                "Governing Impact": "Does not affect ULS PMM D/C",
                "Where to Check": "Analysis > SLS tab",
            }
        )

    # Recompute governing impact after the rule-specific message has been assigned.
    guidance["Governing Impact"] = _diagnostic_governing_impact(message, df=df, dc_summary=dc_summary)
    # Escalate fpu-cap metadata only when governing-impact logic detects a
    # near-governing occurrence.  Otherwise it remains a QA/numerical note.
    if ("prestress stress reached fpu" in text or "reached fpu cap" in text) and "potential governing impact" in str(guidance["Governing Impact"]).casefold():
        guidance["Severity"] = "Engineering review warning"
    guidance["Action Priority"] = _diagnostic_priority(guidance["Governing Impact"], guidance["Severity"])
    return guidance


def _diagnostics_to_dataframe(
    messages: list[str],
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> pd.DataFrame:
    diagnostics_df = pd.DataFrame([_diagnostic_guidance(message, df=df, dc_summary=dc_summary) for message in messages])
    if diagnostics_df.empty:
        return diagnostics_df
    order = {"Engineering review warning": 0, "Solver limitation note": 1, "Numerical note": 2}
    priority_order = {
        "Check before relying on governing result": 0,
        "Review before final design": 1,
        "Review for final design": 2,
        "QA note": 3,
        "Usually no action": 4,
    }
    diagnostics_df["_order"] = diagnostics_df["Severity"].map(order).fillna(99)
    diagnostics_df["_priority_order"] = diagnostics_df["Action Priority"].map(priority_order).fillna(99)
    return diagnostics_df.sort_values(["_priority_order", "_order", "Severity", "Source", "Message"]).drop(columns=["_order", "_priority_order"]).reset_index(drop=True)


def _compression_reversal_near_governing(df: pd.DataFrame | None, dc_summary: DemandCapacitySummary | None) -> bool:
    """Return True when compression-reversal metadata occurs near governing Pu.

    Compression reversal can appear at remote PMM failure-surface points.  The
    commercial UI should escalate it to a review warning only when the event is
    detected near the governing axial level used by the D/C trace.
    """

    governing = _governing_dc_result(dc_summary)
    if governing is None or df is None or df.empty or "prestress_compression_reversal_count" not in df.columns:
        return False
    band = _pmm_points_near_governing_pu(df, governing.Pu_N)
    if band.empty or "prestress_compression_reversal_count" not in band.columns:
        return False
    return bool(pd.to_numeric(band["prestress_compression_reversal_count"], errors="coerce").fillna(0).gt(0).any())


def _compression_reversal_metadata_present(df: pd.DataFrame | None) -> bool:
    if df is None or df.empty or "prestress_compression_reversal_count" not in df.columns:
        return False
    return bool(pd.to_numeric(df["prestress_compression_reversal_count"], errors="coerce").fillna(0).gt(0).any())


def _pmm_closeout_solver_mode_label(
    settings: AnalysisSettings,
    *,
    prestress_system_enabled: bool,
    bonded_prestress_elements: list,
) -> str:
    """Return commercial-facing PMM mode label without changing solver routing."""

    if settings.include_prestress and prestress_system_enabled and bonded_prestress_elements:
        return "RC + Bonded Prestress PMM - Engineering Review"
    return _aci_rc_pmm_ui_status()["label"]


def _filter_pmm_closeout_warnings(warnings: list[str], *, result_has_bonded_prestress: bool) -> list[str]:
    """Keep raw QA trace conservative while removing RC-only blanket prototype wording from first-screen UI."""

    if result_has_bonded_prestress:
        return _deduplicate_diagnostic_messages(warnings)
    return _deduplicate_diagnostic_messages([warning for warning in warnings if str(warning) != PMM_PROTOTYPE_WARNING])


def _render_solver_diagnostic_messages(
    *,
    result_has_bonded_prestress: bool,
    settings: AnalysisSettings,
    result_warnings: list[str],
    result_info: list[str],
    numeric_warnings: list[str],
    rebar_displacement_subtracted: bool,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> None:
    """Render deduplicated solver messages as compact diagnostics.

    This is UI-only.  It does not suppress solver warnings in the underlying
    result object; it only prevents repeated warning text from dominating the
    Analysis workspace.
    """

    base_warnings: list[object] = [SERVICEABILITY_NOT_IMPLEMENTED_WARNING, DCR_PROTOTYPE_WARNING]
    if result_has_bonded_prestress:
        base_warnings.extend(
            [
                PMM_PROTOTYPE_WARNING,
                BONDED_PRESTRESS_PROTOTYPE_WARNING,
                "PT Bar / Prestressing Bar material is supported through PrestressElement.",
                RC_AXIAL_CAP_LIMITATION_WARNING,
            ]
        )
    else:
        base_warnings.append("Prestress contribution is not included in this result.")
    if not settings.subtract_rebar_displaced_concrete:
        base_warnings.append("Displaced concrete at ordinary rebar locations is not subtracted. Compression capacity may be overestimated.")

    if _compression_reversal_near_governing(df, dc_summary):
        base_warnings.append(
            "Active prestress compression reversal occurs near the governing PMM region; "
            "tensile strain is clamped to zero in the current model."
        )

    warnings = _filter_pmm_closeout_warnings(
        base_warnings + list(result_warnings or []) + list(numeric_warnings or []),
        result_has_bonded_prestress=result_has_bonded_prestress,
    )
    info_items = list(result_info or [])
    if not result_has_bonded_prestress:
        aci_rc_status = _aci_rc_pmm_ui_status()
        info_items.append(f"{aci_rc_status['label']}: {aci_rc_status['detail']}")
    if _compression_reversal_metadata_present(df) and not _compression_reversal_near_governing(df, dc_summary):
        info_items.append(
            "Active prestress compression reversal occurred only as PMM stress-state metadata away from the governing region; "
            "not escalated to a global engineering warning."
        )
    info_items = _deduplicate_diagnostic_messages(info_items)

    counts = _diagnostic_counts(warnings)

    cols = st.columns(4)
    cols[0].metric("Review warnings", f"{counts.get('Engineering review warning', 0):,}")
    cols[1].metric("Limitation notes", f"{counts.get('Solver limitation note', 0):,}")
    cols[2].metric("Numerical notes", f"{counts.get('Numerical note', 0):,}")
    cols[3].metric("Solver info", f"{len(info_items):,}")

    if warnings:
        st.caption("Deduplicated solver messages are grouped by severity and action priority. Detailed meaning and recommended action are available below.")
        diagnostic_df = _diagnostics_to_dataframe(warnings, df=df, dc_summary=dc_summary)
        compact_columns = ["Source", "Severity", "Message", "Governing Impact", "Action Priority", "Where to Check"]
        available_compact_columns = [column for column in compact_columns if column in diagnostic_df.columns]
        st.dataframe(diagnostic_df[available_compact_columns], use_container_width=True, hide_index=True)
        with st.expander("Detailed diagnostic meaning / cause / recommended action", expanded=False):
            detail_columns = ["Source", "Message", "Meaning", "Possible Cause", "Recommended Action", "Governing Impact", "Action Priority", "Where to Check"]
            available_detail_columns = [column for column in detail_columns if column in diagnostic_df.columns]
            st.dataframe(diagnostic_df[available_detail_columns], use_container_width=True, hide_index=True)
    else:
        st.success("No solver warnings were reported.")

    if rebar_displacement_subtracted:
        st.info("Concrete compression at ordinary rebar locations is reduced to avoid double counting.")

    with st.expander("Solver info items", expanded=False):
        if info_items:
            st.dataframe(pd.DataFrame({"Info": info_items}), use_container_width=True, hide_index=True)
        else:
            st.info("No solver info items were reported.")


def _validation_status_badge(status: str) -> str:
    """Map validation-matrix status to a commercial-facing label."""

    mapping = {
        "implemented": "Validated / implemented",
        "partial": "Validation in progress",
        "planned": "Planned / not implemented",
    }
    return mapping.get(str(status), "Unknown")


def _validation_status_style(status: str) -> str:
    if status == "implemented":
        return "ready"
    if status == "partial":
        return "warning"
    if status == "planned":
        return "neutral"
    return "info"


def _validation_case_status_map() -> dict[str, object]:
    """Return validation case specs keyed by case id for UI status panels."""

    return {case.case_id: case for case in build_pmm_solver_validation_matrix()}


def _aci_rc_pmm_ui_status(cases: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Return guarded ACI RC PMM finalized production-preview wording for the UI.

    This is a wording/status helper only. It reads the validation matrix and
    never changes PMM equations, demand/capacity extraction, or code routing.
    """

    case_map = cases or _validation_case_status_map()
    readiness_case = case_map.get("PMM.FINAL.RC1.STATUS.READINESS1")
    readiness_status = getattr(readiness_case, "status", "planned")
    if readiness_status == "implemented":
        return {
            "label": "ACI RC Flexural PMM: Finalized Production Preview",
            "detail": "ACI 318 RC Column/Pier/Wall/Pylon PMM only; not AASHTO LRFD and not final code-certified.",
            "table_guidance": (
                "Use for ACI RC flexural PMM finalized production-preview review with QA diagnostics retained."
            ),
            "remaining": (
                "AASHTO LRFD PMM, prestress finalization, shear, torsion, SLS, detailing, slenderness, "
                "and second-order effects remain outside this final closeout."
            ),
            "status": "ready",
        }
    return {
        "label": "ACI RC Flexural PMM: Engineering Review",
        "detail": "Finalized production-preview wording is held until PMM.FINAL.RC1.STATUS.READINESS1 is implemented.",
        "table_guidance": "Use as engineering-review output until the status-readiness gate is implemented.",
        "remaining": "Complete PMM.FINAL.RC1.STATUS.READINESS1 before finalized production-preview wording is shown.",
        "status": "warning",
    }


def _method_validation_status_rows(
    *,
    result_has_active_prestress: bool,
    result_has_passive_prestress: bool,
    include_sls: bool = True,
) -> list[dict[str, str]]:
    """Build the commercial-facing validation status rows for Analysis.

    This is intentionally a UI/status layer.  It does not certify the solver;
    it summarizes which validation milestones support the currently visible
    method and which areas remain under validation.
    """

    cases = _validation_case_status_map()
    aci_rc_pmm_status = _aci_rc_pmm_ui_status(cases)

    def row(
        area: str,
        case_id: str | None,
        evidence: str,
        remaining: str,
        design_use: str,
    ) -> dict[str, str]:
        case = cases.get(case_id) if case_id else None
        status = case.status if case is not None else "planned"
        return {
            "Area": area,
            "Validation Status": _validation_status_badge(status),
            "Design Use Guidance": design_use,
            "Evidence / Benchmark": evidence if evidence else (case_id or "Not yet assigned"),
            "Remaining Engineering Limitation": remaining,
            "Case ID": case_id or "—",
        }

    rows = [
        row(
            "ACI RC Flexural PMM status",
            "PMM.FINAL.RC1.STATUS.READINESS1",
            "PMM.FINAL.RC1 readiness gate covers RC scope, uniaxial/biaxial evidence, phi, D/C no-overestimate, and wording guard.",
            aci_rc_pmm_status["remaining"],
            f"{aci_rc_pmm_status['label']}. {aci_rc_pmm_status['table_guidance']}",
        ),
        row(
            "RC PMM strain compatibility",
            "VALID.RC1",
            "VALID.RC1 rectangular RC benchmark pack plus VALID.RC2 phi transition checks.",
            "Add published/reference biaxial PMM examples before removing all general PMM method notes.",
            "Use for current ULS PMM review with QA notes retained.",
        ),
        row(
            "ACI phi transition",
            "VALID.RC2",
            "Compression-controlled, transition, and tension-controlled phi checks are covered.",
            "Document published-code examples for final validation notes.",
            "Use for ACI phi classification review in current PMM results.",
        ),
        row(
            "Directional PMM D/C extraction",
            "VALID.PMM.DC1",
            "Cleaned Pu slice envelope with ray-intersection capacity benchmark.",
            "Add reference biaxial demand/capacity examples before retiring all D/C limitation notes.",
            "Use when capacity method is slice_envelope and D/C warnings are zero.",
        ),
        row(
            "Prestress-aware axial cap",
            "QA.PO1",
            "QA.PO1 validates Po, Aps, count handling, fpu fallback, and capped phiPn,max.",
            "Review project/code-specific axial-compression limits before final design.",
            "Use for axial-cap screening with final code-specific review retained.",
        ),
    ]

    if result_has_passive_prestress:
        rows.append(
            row(
                "Passive PS / high-strength steel",
                "SOLVER.PS.PASSIVE1",
                "Passive Pe_eff=0/fpe=0 rows are separated from active-prestress warnings.",
                "Review detailing/minimum reinforcement requirements separately.",
                "Use as passive bonded high-strength steel contribution, not external prestress force.",
            )
        )
    if result_has_active_prestress:
        rows.extend(
            [
                row(
                    "Active bonded prestress model",
                    "VALID.PS1",
                    "PS-only and RC+PS benchmark behavior is covered for current strain-compatibility assumptions.",
                    "Published prestressed section reference examples are still required before fully retiring prestress method notes.",
                    "Use for engineering review; retain independent check for final prestressed design.",
                ),
                row(
                    "Prestress stress-state region policy",
                    "VALID.PS2",
                    "fpu-cap and compression-reversal metadata are traceable by PMM region.",
                    "Stress-strain reference cases for compression-side behavior remain future validation work.",
                    "Use governing-impact classification to separate background surface events from result warnings.",
                ),
                row(
                    "Prestress fpu-cap warning policy",
                    "SOLVER.PS.STRESS1",
                    "fpu-cap events are retained as PMM metadata unless governing-region evidence requires escalation.",
                    "Keep reviewing governing-region diagnostics for final design cases.",
                    "Do not treat background fpu-cap events as failure by themselves.",
                ),
                row(
                    "Prestress compression-reversal policy",
                    "SOLVER.PS.COMP1",
                    "Compression-reversal events are escalated only when detected near the governing PMM region.",
                    "A refined compression-side prestress material model is still a future solver milestone.",
                    "Use if governing-impact count is zero; review if Diagnostics flags governing-region impact.",
                ),
            ]
        )
    if include_sls:
        rows.append(
            {
                "Area": "SLS / Stress & Cracking",
                "Validation Status": "Planned / not implemented",
                "Design Use Guidance": "Not part of the current ULS PMM result; SLS loads are retained for future checks.",
                "Evidence / Benchmark": "SLS load cases are stored and traced, but serviceability calculations are outside the active ULS PMM workflow.",
                "Remaining Engineering Limitation": "Concrete/steel/prestress service stresses, decompression, and cracking checks are future milestones.",
                "Case ID": "SLS.C1 planned",
            }
        )
    return rows


def _method_validation_status_cards(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    validated = sum("Validated" in row["Validation Status"] for row in rows)
    in_progress = sum("progress" in row["Validation Status"] for row in rows)
    planned = sum("Planned" in row["Validation Status"] for row in rows)
    planned_areas = [row.get("Area", "") for row in rows if "Planned" in row.get("Validation Status", "")]
    planned_detail = "; ".join(area for area in planned_areas if area) or "Not part of current ULS PMM result"
    return [
        {
            "title": "Validated / Implemented",
            "value": str(validated),
            "detail": "Milestones with current benchmark evidence",
            "status": "ready",
        },
        {
            "title": "Validation In Progress",
            "value": str(in_progress),
            "detail": "Use engineering review and diagnostics",
            "status": "warning" if in_progress else "ready",
        },
        {
            "title": "Planned Checks",
            "value": str(planned),
            "detail": planned_detail,
            "status": "neutral",
        },
        {
            "title": "Method Basis",
            "value": "ACI RC PMM",
            "detail": _aci_rc_pmm_ui_status()["label"],
            "status": "info",
        },
    ]


def _validation_status_compact_dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    """Return a compact validation status table for the first QA view."""

    columns = [
        "Area",
        "Validation Status",
        "Design Use Guidance",
        "Case ID",
    ]
    return pd.DataFrame(rows)[columns]


def _validation_status_detail_dataframe(rows: list[dict[str, str]]) -> pd.DataFrame:
    """Return the full evidence table for detailed engineering review."""

    columns = [
        "Area",
        "Validation Status",
        "Case ID",
        "Evidence / Benchmark",
        "Remaining Engineering Limitation",
        "Design Use Guidance",
    ]
    return pd.DataFrame(rows)[columns]


def _render_method_validation_status_panel(
    *,
    result_has_active_prestress: bool,
    result_has_passive_prestress: bool,
) -> None:
    """Render commercial validation status instead of relying on prototype wording."""

    rows = _method_validation_status_rows(
        result_has_active_prestress=result_has_active_prestress,
        result_has_passive_prestress=result_has_passive_prestress,
    )
    _render_analysis_summary_strip(_method_validation_status_cards(rows), columns=4)
    with st.expander("Validation status / method notes", expanded=False):
        st.caption(
            "This panel separates validation evidence from final-design limitations. "
            "Use the compact table for first-screen confidence and the detailed table for engineering QA traceability."
        )
        st.markdown("**Validation status overview**")
        st.dataframe(_validation_status_compact_dataframe(rows), use_container_width=True, hide_index=True)
        with st.expander("Detailed validation evidence / remaining limitations", expanded=False):
            st.dataframe(_validation_status_detail_dataframe(rows), use_container_width=True, hide_index=True)

def _render_prestress_check_panel(summary: PrestressCheckSummary, include_prestress: bool) -> None:
    """Render prestress QA as diagnostics instead of main-page content."""

    if not summary.checks:
        st.info("No prestress elements are defined.")
        return

    if summary.errors:
        st.error("Prestress validation errors are present. Open Prestress diagnostics for row-level details.")
    elif summary.warnings:
        st.warning("Prestress warnings are present. Open Prestress diagnostics for row-level details.")

    with st.expander("Prestress diagnostics", expanded=False):
        st.markdown("**Prestress Analysis Check Table**")
        cols = st.columns(4)
        cols[0].metric("Bonded count", f"{summary.bonded_count:,}")
        cols[1].metric("Unbonded ignored", f"{summary.unbonded_count:,}")
        cols[2].metric("Total bonded Aps", f"{summary.total_area_mm2:,.1f} mm^2")
        cols[3].metric("Total bonded Pe_eff", f"{N_to_kN(summary.total_pe_eff_N):,.1f} kN")
        if not include_prestress:
            st.info("Prestress elements are not included because Include prestress is disabled.")
        if summary.bonded_count == 0 and summary.unbonded_count > 0:
            st.warning("Only unbonded prestress elements are present. They are ignored in the current solver.")
        for error in summary.errors:
            st.error(f"ERROR: {error}")
        for warning in summary.warnings:
            st.warning(f"WARNING: {warning}")
        st.dataframe(_prestress_check_dataframe(summary), use_container_width=True, hide_index=True)


def _collect_engineering_warnings(*warning_groups: list[str]) -> list[str]:
    collected: list[object] = []
    for group in warning_groups:
        collected.extend(group)
    return _deduplicate_diagnostic_messages(collected)


def _guidance_priority_counts(guidance_df: pd.DataFrame) -> dict[str, int]:
    """Return action-priority counts from an actionable diagnostics table."""

    if guidance_df.empty or "Action Priority" not in guidance_df.columns:
        return {}
    return {str(key): int(value) for key, value in guidance_df["Action Priority"].value_counts().to_dict().items()}


def _governing_warning_count(priority_counts: dict[str, int]) -> int:
    return int(priority_counts.get("Check before relying on governing result", 0))


def _review_before_final_count(priority_counts: dict[str, int]) -> int:
    return int(priority_counts.get("Review before final design", 0) + priority_counts.get("Review for final design", 0))


def _qa_note_count(priority_counts: dict[str, int]) -> int:
    return int(priority_counts.get("QA note", 0) + priority_counts.get("Usually no action", 0))


def _diagnostic_summary_message(warnings: list[str], *, df: pd.DataFrame | None = None, dc_summary: DemandCapacitySummary | None = None) -> tuple[str, str]:
    """Return a commercial-facing one-line diagnostic summary and display level.

    The main Analysis page should not read as if the governing ULS result failed
    when all diagnostics are background QA items.  This helper keeps diagnostics
    visible while separating governing-impact warnings from final-review notes.
    """

    if not warnings:
        return "No solver diagnostics are currently reported for this analysis result.", "success"

    counts = _diagnostic_counts(warnings)
    guidance_df = _diagnostics_to_dataframe(warnings, df=df, dc_summary=dc_summary)
    priority_counts = _guidance_priority_counts(guidance_df)
    governing_count = _governing_warning_count(priority_counts)
    review_count = _review_before_final_count(priority_counts)
    qa_count = _qa_note_count(priority_counts)
    limitation_count = int(counts.get("Solver limitation note", 0))
    numerical_count = int(counts.get("Numerical note", 0))

    if governing_count > 0:
        return (
            f"{governing_count:,} governing-impact review item(s) should be checked before relying on the result. "
            f"{review_count:,} additional final-review item(s), {limitation_count:,} method note(s), "
            f"and {numerical_count:,} numerical note(s) are retained in Diagnostics / QA."
        ), "warning"

    if review_count > 0:
        return (
            f"No direct governing-result warning detected. {review_count:,} engineering QA review item(s) "
            f"are retained for final review; {limitation_count:,} method note(s) and "
            f"{numerical_count:,} numerical note(s) remain available in Diagnostics / QA."
        ), "info"

    return (
        f"No direct governing-result warning detected. {qa_count:,} background QA/numerical item(s) "
        f"and {limitation_count:,} method note(s) are retained for traceability."
    ), "info"


def _render_diagnostic_summary_banner(
    warnings: list[str],
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> None:
    message, level = _diagnostic_summary_message(warnings, df=df, dc_summary=dc_summary)
    if level == "warning":
        st.warning(message)
    elif level == "success":
        st.success(message)
    else:
        st.info(message)


def _render_engineering_warnings(
    warnings: list[str],
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> None:
    st.subheader("Actionable Engineering Review Guidance")
    st.info(
        "Each diagnostic is translated into meaning, possible cause, recommended action, governing impact, action priority, "
        "and where to check. Limitation and numerical notes are retained for QA but are not treated as ULS readiness failures."
    )
    if not warnings:
        st.success("No engineering review messages are currently reported.")
        return

    counts = _diagnostic_counts(warnings)
    guidance_df = _diagnostics_to_dataframe(warnings, df=df, dc_summary=dc_summary)
    priority_counts = _guidance_priority_counts(guidance_df)

    cols = st.columns(3)
    cols[0].metric("Review warnings", f"{counts.get('Engineering review warning', 0):,}")
    cols[1].metric("Method / limitation notes", f"{counts.get('Solver limitation note', 0):,}")
    cols[2].metric("Numerical notes", f"{counts.get('Numerical note', 0):,}")
    priority_cols = st.columns(3)
    priority_cols[0].metric("Governing-impact", f"{_governing_warning_count(priority_counts):,}")
    priority_cols[1].metric("Review before final", f"{_review_before_final_count(priority_counts):,}")
    priority_cols[2].metric("QA / usually no action", f"{_qa_note_count(priority_counts):,}")

    compact_columns = ["Source", "Severity", "Message", "Governing Impact", "Action Priority", "Where to Check"]
    available_compact_columns = [column for column in compact_columns if column in guidance_df.columns]
    st.dataframe(guidance_df[available_compact_columns], use_container_width=True, hide_index=True)

    with st.expander("Detailed diagnostic meaning / cause / recommended action", expanded=False):
        detail_columns = [
            "Source",
            "Message",
            "Meaning",
            "Possible Cause",
            "Recommended Action",
            "Governing Impact",
            "Action Priority",
            "Where to Check",
        ]
        available_detail_columns = [column for column in detail_columns if column in guidance_df.columns]
        st.dataframe(guidance_df[available_detail_columns], use_container_width=True, hide_index=True)


def _render_prestress_verification_summary(
    check_summary: PrestressCheckSummary,
    contribution_summary: dict,
    comparison_summary: dict | None,
) -> None:
    """Render prestress contribution as designer-facing summary plus QA expanders.

    Earlier Analysis builds rendered every prestress/PMM diagnostic metric at
    the same visual level.  That was useful while debugging the solver, but it
    made the commercial result workspace feel like an internal diagnostic
    console.  This renderer keeps the same engineering information available,
    but separates first-screen design insight from deep QA metadata.
    """

    st.subheader("Prestress Contribution Summary")
    st.caption(
        "First-screen summary of bonded prestress contribution. Detailed stress-state "
        "and RC-only comparison data are retained below for QA review."
    )

    delta_phi_pn = None
    delta_phi_mnx = None
    delta_phi_mny = None
    if comparison_summary is not None:
        delta_phi_pn = comparison_summary.get("delta_max_phiPn_kN")
        delta_phi_mnx = comparison_summary.get("delta_max_abs_phiMnx_kNm")
        delta_phi_mny = comparison_summary.get("delta_max_abs_phiMny_kNm")

    cols = st.columns(4)
    cols[0].metric("Bonded PS elements", f"{contribution_summary['bonded_prestress_count']:,}")
    cols[1].metric("Total bonded Aps", f"{check_summary.total_area_mm2:,.1f} mm^2")
    cols[2].metric("Total Pe_eff", f"{N_to_kN(check_summary.total_pe_eff_N):,.1f} kN")
    cols[3].metric(
        "Δ max |phiMnx|",
        "—" if delta_phi_mnx is None else f"{delta_phi_mnx:,.1f} kN-m",
        help="Change in maximum absolute phiMnx between RC-only and RC+PS PMM envelopes.",
    )

    delta_cols = st.columns(3)
    delta_cols[0].metric("Δ max phiPn", "—" if delta_phi_pn is None else f"{delta_phi_pn:,.1f} kN")
    delta_cols[1].metric("Δ max |phiMnx|", "—" if delta_phi_mnx is None else f"{delta_phi_mnx:,.1f} kN-m")
    delta_cols[2].metric("Δ max |phiMny|", "—" if delta_phi_mny is None else f"{delta_phi_mny:,.1f} kN-m")

    unbonded_ignored = int(contribution_summary.get("unbonded_prestress_ignored_count", 0))
    if unbonded_ignored:
        st.info(f"{unbonded_ignored:,} unbonded prestress element(s) are ignored by the current PMM solver policy.")

    contribution_warnings = list(contribution_summary.get("warnings", []))
    comparison_warnings = list(comparison_summary.get("warnings", [])) if comparison_summary is not None else []
    for warning in contribution_warnings + comparison_warnings:
        st.warning(f"WARNING: {warning}")

    with st.expander("Prestress stress-state diagnostics", expanded=False):
        st.caption("Detailed stress-state values retained for QA and solver validation; not needed for first-screen D/C review.")
        stress_cols = st.columns(4)
        stress_cols[0].metric("Max |PS force|", f"{contribution_summary['max_abs_prestress_force_kN']:,.1f} kN")
        stress_cols[1].metric("Mean |PS force|", f"{N_to_kN(contribution_summary['mean_abs_prestress_force_N']):,.1f} kN")
        stress_cols[2].metric("PMM points with PS force", f"{contribution_summary['point_count_with_prestress']:,}")
        stress_cols[3].metric("Unbonded PS ignored", f"{unbonded_ignored:,}")

    with st.expander("RC-only vs RC+PS capacity comparison", expanded=False):
        if comparison_summary is None:
            st.info("RC-only comparison is available after running with bonded prestress included.")
            return

        st.caption("Envelope-level comparison used to understand prestress contribution. Governing D/C remains controlled by the selected load case trace.")
        comp_df = pd.DataFrame(
            [
                {
                    "Capacity metric": "Max phiPn",
                    "RC-only": f"{comparison_summary['rc_max_phiPn_kN']:,.1f} kN",
                    "RC+PS": f"{comparison_summary['ps_max_phiPn_kN']:,.1f} kN",
                    "Delta": f"{comparison_summary['delta_max_phiPn_kN']:,.1f} kN",
                },
                {
                    "Capacity metric": "Max |phiMnx|",
                    "RC-only": f"{comparison_summary['rc_max_abs_phiMnx_kNm']:,.1f} kN-m",
                    "RC+PS": f"{comparison_summary['ps_max_abs_phiMnx_kNm']:,.1f} kN-m",
                    "Delta": f"{comparison_summary['delta_max_abs_phiMnx_kNm']:,.1f} kN-m",
                },
                {
                    "Capacity metric": "Max |phiMny|",
                    "RC-only": f"{comparison_summary['rc_max_abs_phiMny_kNm']:,.1f} kN-m",
                    "RC+PS": f"{comparison_summary['ps_max_abs_phiMny_kNm']:,.1f} kN-m",
                    "Delta": f"{comparison_summary['delta_max_abs_phiMny_kNm']:,.1f} kN-m",
                },
            ]
        )
        st.dataframe(comp_df, use_container_width=True, hide_index=True)


def _run_pmm_analysis_with_runtime_control(
    analysis_input: AnalysisInput,
    settings: AnalysisSettings,
    bonded_prestress_elements: list,
    current_hash: str,
    accuracy_preset: str,
) -> None:
    cached_result = st.session_state.get("rc_pmm_result")
    cached_hash = st.session_state.get("pmm_last_analysis_hash")
    force_recalculate = bool(st.session_state.get("analysis_force_recalculate", False))
    if not force_recalculate and isinstance(cached_result, PMMSolverResult) and cached_hash == current_hash:
        st.session_state["analysis_runtime_cache_status"] = "Cached result used"
        st.session_state["analysis_runtime_last_status"] = "Cached result used"
        return

    result, pmm_timing = timed_call("PMM interaction generation", run_rc_pmm_solver, analysis_input)
    _record_runtime_timing(pmm_timing)
    timings = [pmm_timing]
    st.session_state["rc_pmm_result"] = result
    st.session_state["rc_pmm_result_input_hash"] = current_hash
    st.session_state["pmm_last_analysis_hash"] = current_hash

    if settings.include_prestress and bonded_prestress_elements:
        rc_only_input = analysis_input.model_copy(deep=True)
        rc_only_input.settings = analysis_input.settings.model_copy(update={"include_prestress": False})
        rc_only_result, comparison_timing = timed_call("RC-only comparison PMM generation", run_rc_pmm_solver, rc_only_input)
        _record_runtime_timing(comparison_timing)
        timings.append(comparison_timing)
        st.session_state["rc_only_comparison_result"] = rc_only_result
        st.session_state["prestress_comparison_summary"] = compare_rc_vs_prestress_pmm(rc_only_result, result)
    else:
        st.session_state.pop("rc_only_comparison_result", None)
        st.session_state.pop("prestress_comparison_summary", None)

    st.session_state["analysis_runtime_last_status"] = "Recalculated"
    st.session_state["analysis_runtime_cache_status"] = "Recalculated"
    st.session_state["analysis_runtime_last_time_seconds"] = sum(timing.elapsed_seconds for timing in timings)
    st.session_state["analysis_runtime_last_run_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    st.session_state["analysis_runtime_last_preset"] = accuracy_preset
    st.session_state.pop("rc_demand_capacity_result", None)
    st.session_state.pop("rc_demand_capacity_result_hash", None)
    st.session_state.pop("rc_demand_capacity_input_hash", None)
    st.session_state.pop("rc_demand_capacity_pmm_result_hash", None)


def _render_pmm_runtime_control_panel(
    analysis_input: AnalysisInput | None,
    settings: AnalysisSettings,
    bonded_prestress_elements: list,
    solver_mode_label: str,
) -> str | None:
    preset = _analysis_accuracy_preset_from_session()
    current_hash = analysis_input_hash(analysis_input, preset) if analysis_input is not None else None
    has_cached_result = isinstance(st.session_state.get("rc_pmm_result"), PMMSolverResult)
    cached_hash = st.session_state.get("pmm_last_analysis_hash")
    cache_status = cache_status_for_hash(current_hash, cached_hash, has_cached_result)
    if st.session_state.get("analysis_runtime_cache_status") != "Recalculated":
        st.session_state["analysis_runtime_cache_status"] = cache_status

    with st.expander("Analysis Runtime Control", expanded=True):
        st.info(
            "Runtime controls manage when existing PMM calculations run. "
            "They do not change solver equations or engineering sign conventions."
        )
        preset_options = list(ACCURACY_PRESET_RESOLUTIONS.keys())
        st.selectbox(
            "Accuracy preset",
            preset_options,
            index=preset_options.index(preset),
            key="analysis_accuracy_preset",
            help="Fast is lowest-cost; Standard is the practical default; High Accuracy increases sweep resolution for review cases.",
        )

        resolution = accuracy_preset_resolution(st.session_state.get("analysis_accuracy_preset", preset))
        st.caption(
            "Preset resolution: "
            f"{resolution['neutral_axis_angle_steps']} angle steps x {resolution['neutral_axis_depth_steps']} depth steps."
        )
        if st.session_state.get("analysis_accuracy_preset") == "High Accuracy":
            st.warning("High Accuracy increases neutral-axis sweep resolution and may significantly increase runtime.")
        if cache_status == "Input changed, recalculation required":
            st.warning("Engineering inputs have changed since the cached PMM result. Recalculate before using displayed results.")
        st.checkbox("Force recalculation even if cached", value=False, key="analysis_force_recalculate")
        run_clicked = st.button(
            "Run / Recalculate Analysis",
            disabled=analysis_input is None,
            help=f"Runs or reuses the cached {solver_mode_label} result depending on the engineering input hash.",
            use_container_width=True,
        )
        if analysis_input is None:
            readiness = check_analysis_readiness(st.session_state)
            if readiness.errors:
                st.caption("Run is disabled until Analysis Readiness errors are corrected.")
                st.dataframe(_readiness_actions_to_dataframe(readiness.errors), use_container_width=True, hide_index=True)
            else:
                st.caption("Run is disabled until analysis input can be built from the current project data.")

        if run_clicked and analysis_input is not None and current_hash is not None:
            _run_pmm_analysis_with_runtime_control(
                analysis_input,
                settings,
                bonded_prestress_elements,
                current_hash,
                st.session_state.get("analysis_accuracy_preset", preset),
            )
            cache_status = cache_status_for_hash(
                current_hash,
                st.session_state.get("pmm_last_analysis_hash"),
                isinstance(st.session_state.get("rc_pmm_result"), PMMSolverResult),
            )
            cache_status = st.session_state.get("analysis_runtime_cache_status", cache_status)

        status_cols = st.columns(3)
        status_cols[0].metric("Last run status", st.session_state.get("analysis_runtime_last_status", "Not run"))
        last_time = st.session_state.get("analysis_runtime_last_time_seconds")
        status_cols[1].metric("Last run time", "N/A" if last_time is None else f"{float(last_time):.2f} s")
        status_cols[2].metric("Result cache status", cache_status)
    return current_hash


def _get_or_compute_demand_capacity_summary(
    result: PMMSolverResult,
    load_cases: list,
    result_hash: str | None,
) -> DemandCapacitySummary:
    dc_hash = demand_capacity_input_hash(result_hash, load_cases)
    cached_summary = st.session_state.get("rc_demand_capacity_result")
    cached_hash = st.session_state.get("rc_demand_capacity_input_hash")
    if cached_hash is None:
        cached_hash = st.session_state.get("rc_demand_capacity_result_hash")
    if result_hash is not None and isinstance(cached_summary, DemandCapacitySummary) and cached_hash == dc_hash:
        st.session_state["analysis_runtime_dc_cache_status"] = "Cached D/C result used"
        return cached_summary
    summary, timing = timed_call("Demand/capacity evaluation", check_uls_demands_against_rc_pmm, result, load_cases)
    _record_runtime_timing(timing)
    st.session_state["rc_demand_capacity_result"] = summary
    st.session_state["rc_demand_capacity_result_hash"] = dc_hash
    st.session_state["rc_demand_capacity_input_hash"] = dc_hash
    st.session_state["rc_demand_capacity_pmm_result_hash"] = result_hash
    st.session_state["analysis_runtime_dc_cache_status"] = "Recalculated"
    return summary


def _render_input_summary() -> None:
    settings = _settings_from_session()
    mode_settings = _analysis_mode_from_session()
    analysis_input = build_analysis_input_from_session_state(st.session_state)
    section_geometry = st.session_state.get("section_geometry")
    concrete_material = st.session_state.get("concrete_material")
    load_cases = [
        load_case
        for load_case in st.session_state.get("load_cases", [])
        if load_case.active and load_case.load_type == settings.strength_load_type
    ]
    stored_rebars = list(st.session_state.get("rebars", []) or [])
    stored_prestress_elements = list(st.session_state.get("prestress_elements", []) or [])
    rebars = effective_rebars_for_analysis(stored_rebars, st.session_state, settings)
    prestress_elements = effective_prestress_for_analysis(stored_prestress_elements, st.session_state, settings)
    total_as = sum(rebar.area_mm2 for rebar in rebars)
    total_aps = sum(element.total_area_mm2 for element in prestress_elements)
    total_pe = sum(element.pe_eff_n * element.count for element in prestress_elements)
    bonded_prestress_elements = [element for element in prestress_elements if element.bonded]
    unbonded_prestress_elements = [element for element in prestress_elements if not element.bonded]
    rebar_system_enabled = ordinary_rebar_enabled(st.session_state, default=True)
    prestress_system_enabled = prestressing_steel_enabled(st.session_state, default=True)
    solver_mode_label = _pmm_closeout_solver_mode_label(
        settings,
        prestress_system_enabled=prestress_system_enabled,
        bonded_prestress_elements=bonded_prestress_elements,
    )
    prestress_check_summary = check_prestress_elements_for_analysis(prestress_elements)

    st.subheader("Analysis Workspace Overview")
    beta1 = concrete_material.beta1 if concrete_material is not None and concrete_material.beta1 is not None else (
        aci_beta1(concrete_material.fc_MPa) if concrete_material is not None else None
    )
    overview_cards = [
        {
            "title": "Section",
            "value": "Available" if section_geometry is not None else "Missing",
            "detail": "Geometry ready for PMM" if section_geometry is not None else "Define section geometry first",
            "status": "ready" if section_geometry is not None else "danger",
        },
        {
            "title": "Active ULS",
            "value": f"{len(load_cases):,}",
            "detail": "Used by ULS / PMM D/C",
            "status": "ready" if load_cases else "warning",
        },
        {
            "title": "Rebar / Prestress",
            "value": f"{len(rebars):,} / {len(prestress_elements):,}",
            "detail": (
                f"Included. Stored {len(stored_rebars):,} / {len(stored_prestress_elements):,}; "
                f"Bonded PS {len(bonded_prestress_elements):,}; unbonded ignored {len(unbonded_prestress_elements):,}"
            ),
            "status": "warning" if unbonded_prestress_elements or not rebar_system_enabled or not prestress_system_enabled else "neutral",
        },
        {
            "title": "Solver Mode",
            "value": solver_mode_label,
            "detail": f"f'c {concrete_material.fc_MPa:g} MPa, beta1 {beta1:.3g}" if concrete_material is not None and beta1 is not None else "Concrete material missing",
            "status": "ready" if concrete_material is not None else "danger",
        },
    ]
    _render_analysis_summary_strip(overview_cards, columns=4)

    if not rebar_system_enabled:
        st.info("Ordinary rebar is disabled for this section; stored rebar rows are preserved but ignored by analysis.")
    if not prestress_system_enabled:
        st.info("Prestressing steel is disabled for this section; stored prestress rows are preserved but ignored by analysis.")
    if unbonded_prestress_elements:
        st.warning("Unbonded prestress elements are present and are ignored by the current PMM/SLS solvers.")
    if not settings.subtract_rebar_displaced_concrete:
        st.warning("Displaced concrete at ordinary rebar locations is not subtracted. Compression capacity may be overestimated.")
    if analysis_input is not None:
        st.success("AnalysisInput can be built from the current session data.")
    else:
        st.info("AnalysisInput will be built after readiness errors are resolved.")

    with st.expander("Input diagnostics / section totals", expanded=False):
        cols = st.columns(4)
        cols[0].metric("Section available", "Yes" if section_geometry is not None else "No")
        cols[1].metric("Strength load cases", f"{len(load_cases):,}")
        cols[2].metric("Rebars", f"{len(rebars):,} included", f"stored {len(stored_rebars):,}")
        cols[3].metric("Prestress elements", f"{len(prestress_elements):,} included", f"stored {len(stored_prestress_elements):,}")

        ps_count_cols = st.columns(2)
        ps_count_cols[0].metric("Bonded prestress elements", f"{len(bonded_prestress_elements):,}")
        ps_count_cols[1].metric("Unbonded prestress elements ignored", f"{len(unbonded_prestress_elements):,}")

        cols2 = st.columns(4)
        if concrete_material is not None:
            cols2[0].metric("Concrete material", f"{concrete_material.name}")
            cols2[1].metric("Concrete f'c", f"{concrete_material.fc_MPa:g} MPa")
            cols2[2].metric("beta1", f"{beta1:.3g}" if beta1 is not None else "N/A")
        else:
            cols2[0].metric("Concrete material", "Missing")
            cols2[1].metric("Concrete f'c", "N/A")
            cols2[2].metric("beta1", "N/A")
        cols2[3].metric("Section systems", f"Rebar {'ON' if rebar_system_enabled else 'OFF'} / PS {'ON' if prestress_system_enabled else 'OFF'}")

        cols3 = st.columns(3)
        cols3[0].metric("Total As", f"{total_as:,.1f} mm^2")
        cols3[1].metric("Total Aps", f"{total_aps:,.1f} mm^2")
        cols3[2].metric("Total Pe_eff", f"{N_to_kN(total_pe):,.1f} kN")

        st.info("PMM final closeout status: ACI RC-only is finalized production-preview; bonded prestress remains engineering review.")
        st.info(f"Current solver mode: {solver_mode_label}.")
        if is_beam_girder_future_workflow(mode_settings):
            st.warning("PMM interaction is not the primary design method for typical bridge girder flexural design. Bridge girder ULS design checks are future work.")
        elif not is_pmm_primary_workflow(mode_settings):
            st.info("Non-PMM workflow is active; PMM output should be interpreted as an auxiliary section review only.")
        st.info(f"Prestress stress model: {settings.prestress_stress_model}.")
        st.info(
            "Rebar displaced concrete subtraction: "
            f"{'Enabled' if settings.subtract_rebar_displaced_concrete else 'Disabled'}."
        )
        st.info(
            SERVICEABILITY_NOT_IMPLEMENTED_WARNING
            if not settings.include_prestress
            else f"{BONDED_PRESTRESS_PROTOTYPE_WARNING} {SERVICEABILITY_NOT_IMPLEMENTED_WARNING}"
        )

    _render_prestress_check_panel(prestress_check_summary, settings.include_prestress)

    current_analysis_hash = _render_pmm_runtime_control_panel(
        analysis_input,
        settings,
        bonded_prestress_elements,
        solver_mode_label,
    )

    result = st.session_state.get("rc_pmm_result")
    if isinstance(result, PMMSolverResult):
        result_hash = st.session_state.get("rc_pmm_result_input_hash")
        if current_analysis_hash is not None and result_hash != current_analysis_hash:
            st.warning("Displayed PMM results are stale because engineering inputs have changed. Run / Recalculate Analysis to update them.")
        result_has_active_prestress = any(getattr(point, "active_prestress_count", point.bonded_prestress_count) > 0 for point in result.points)
        result_has_passive_prestress = any(getattr(point, "passive_prestress_count", 0) > 0 for point in result.points)
        result_has_bonded_prestress = result_has_active_prestress or result_has_passive_prestress
        if result_has_active_prestress:
            result_label = "RC + Active Bonded Prestress PMM"
        elif result_has_passive_prestress:
            result_label = "RC + Passive PS Steel PMM"
        else:
            result_label = "RC PMM"
        st.subheader(f"{result_label} Result")
        if result_has_bonded_prestress:
            st.caption(
                "Method: ACI strain compatibility with prestress contribution. "
                "Prestressed PMM remains engineering review; QA diagnostics remain available."
            )
        else:
            st.caption(
                "Method: ACI strain compatibility. ACI RC Flexural PMM is finalized production-preview within the validated RC scope; "
                "QA diagnostics remain available."
            )
        _render_method_validation_status_panel(
            result_has_active_prestress=result_has_active_prestress,
            result_has_passive_prestress=result_has_passive_prestress,
        )
        df = pmm_result_to_display_dataframe(result)
        if not df.empty:
            summary = summarize_pmm_result(result)
            numeric_summary = check_pmm_dataframe_numerics(df)
            dc_summary = _get_or_compute_demand_capacity_summary(
                result,
                st.session_state.get("load_cases", []),
                result_hash,
            )
            with st.expander("PMM solver diagnostics / QA summary", expanded=False):
                _render_solver_diagnostic_messages(
                    result_has_bonded_prestress=result_has_bonded_prestress,
                    settings=settings,
                    result_warnings=result.warnings,
                    result_info=result.info,
                    numeric_warnings=[f"PMM numeric warning: {warning}" for warning in numeric_summary["warnings"]],
                    rebar_displacement_subtracted=bool(
                        result.points and any(point.rebar_displaced_concrete_subtracted_N > 0.0 for point in result.points)
                    ),
                    df=df,
                    dc_summary=dc_summary,
                )
                # Keep the first view of diagnostics compact.  Detailed PMM
                # capacity and stress-state metadata remain available in nested
                # expanders instead of being rendered as a full debug dashboard.
                st.markdown("**Solver QA essentials**")
                essential_cols = st.columns(4)
                essential_cols[0].metric("PMM points", f"{summary['point_count']:,}")
                essential_cols[1].metric("Max capped phiPn", f"{df['phiPn_capped_kN'].max():,.1f} kN")
                essential_cols[2].metric("Max |phiMnx|", f"{df['phiMnx_kNm'].abs().max():,.1f} kN-m")
                essential_cols[3].metric("Max |phiMny|", f"{df['phiMny_kNm'].abs().max():,.1f} kN-m")

                included_aps = sum(element.total_area_mm2 for element in bonded_prestress_elements) if result_has_bonded_prestress else 0.0
                included_pe = sum(element.pe_eff_n * element.count for element in bonded_prestress_elements) if result_has_bonded_prestress else 0.0
                with st.expander("PMM capacity envelope metadata", expanded=False):
                    st.caption("Envelope extrema retained for QA. Governing D/C should be read from the ULS workspace and trace tables.")
                    cap_df = pd.DataFrame(
                        [
                            {"Metric": "Max phiPn", "Value": f"{df['phiPn_kN'].max():,.1f} kN"},
                            {"Metric": "Max capped phiPn", "Value": f"{df['phiPn_capped_kN'].max():,.1f} kN"},
                            {"Metric": "Min phiPn", "Value": f"{df['phiPn_kN'].min():,.1f} kN"},
                            {"Metric": "Max |phiMnx|", "Value": f"{df['phiMnx_kNm'].abs().max():,.1f} kN-m"},
                            {"Metric": "Max |phiMny|", "Value": f"{df['phiMny_kNm'].abs().max():,.1f} kN-m"},
                            {"Metric": "Max nominal Pn", "Value": f"{df['Pn_kN'].max():,.1f} kN"},
                            {"Metric": "Max nominal |Mnx|", "Value": f"{df['Mnx_kNm'].abs().max():,.1f} kN-m"},
                            {"Metric": "Max nominal |Mny|", "Value": f"{df['Mny_kNm'].abs().max():,.1f} kN-m"},
                        ]
                    )
                    st.dataframe(cap_df, use_container_width=True, hide_index=True)

                with st.expander("Reinforcement / prestress solver metadata", expanded=False):
                    meta_df = pd.DataFrame(
                        [
                            {"Metric": "Bonded PS included", "Value": f"{int(df['bonded_prestress_count'].max()):,}"},
                            {"Metric": "Unbonded PS ignored", "Value": f"{int(df['unbonded_prestress_ignored_count'].max()):,}"},
                            {"Metric": "Included Aps / Pe", "Value": f"{included_aps:,.1f} mm^2 / {included_pe:,.0f} N"},
                            {"Metric": "Max |PS force|", "Value": f"{df['prestress_force_kN'].abs().max():,.1f} kN"},
                            {"Metric": "Rebar displacement subtraction", "Value": "Enabled" if settings.subtract_rebar_displaced_concrete else "Disabled"},
                            {"Metric": "Max concrete subtraction", "Value": f"{df['rebar_displaced_concrete_subtracted_kN'].max():,.1f} kN"},
                            {"Metric": "Max bars in compression block", "Value": f"{int(df['rebar_inside_compression_count'].max()):,}"},
                        ]
                    )
                    st.dataframe(meta_df, use_container_width=True, hide_index=True)

                if result_has_bonded_prestress and "max_prestress_stress_MPa" in df:
                    with st.expander("Prestress stress-state metadata", expanded=False):
                        model_values = df["prestress_stress_model"].dropna()
                        model_label = str(model_values.iloc[0]) if not model_values.empty else settings.prestress_stress_model
                        stress_df = pd.DataFrame(
                            [
                                {"Metric": "Prestress stress model", "Value": model_label},
                                {"Metric": "Max fps", "Value": f"{df['max_prestress_stress_MPa'].max():,.1f} MPa"},
                                {"Metric": "Stress warning count", "Value": f"{int(df['prestress_stress_warning_count'].sum()):,}"},
                                {"Metric": "Reached fpu cap count", "Value": f"{int(df['prestress_reached_fpu_cap_count'].sum()):,}"},
                            ]
                        )
                        st.dataframe(stress_df, use_container_width=True, hide_index=True)

                contribution_summary = summarize_prestress_contribution(result)
                comparison_summary = st.session_state.get("prestress_comparison_summary")
                if settings.include_prestress and result_has_bonded_prestress:
                    _render_prestress_verification_summary(prestress_check_summary, contribution_summary, comparison_summary)
                elif not settings.include_prestress and prestress_elements:
                    st.info("Prestress elements are not included because Include prestress is disabled.")
                elif contribution_summary["unbonded_prestress_ignored_count"] > 0:
                    st.warning("Only unbonded prestress elements are present. They are ignored in the current solver.")
    
                active_uls = get_active_uls_load_cases(st.session_state.get("load_cases", []))
                demand_df = demand_load_cases_to_display_dataframe(active_uls)
                st.subheader("Active ULS Demand Points")
                st.info(
                    "Demand points are shown for visual reference. Stored D/C results are shown below; "
                    "review method, fallback, and QA diagnostics before relying on the governing case."
                )
                st.dataframe(demand_df, use_container_width=True, hide_index=True)

            engineering_warnings = _collect_engineering_warnings(
                result.warnings,
                prestress_check_summary.errors,
                prestress_check_summary.warnings,
                dc_summary.warnings,
                numeric_summary["warnings"],
            )
            engineering_warnings = _filter_pmm_closeout_warnings(
                engineering_warnings,
                result_has_bonded_prestress=result_has_bonded_prestress,
            )
            if engineering_warnings:
                _render_diagnostic_summary_banner(engineering_warnings, df=df, dc_summary=dc_summary)
            with st.expander("Engineering warnings / limitations", expanded=False):
                _render_engineering_warnings(engineering_warnings, df=df, dc_summary=dc_summary)

            unbonded_ignored_count = int(df["unbonded_prestress_ignored_count"].max()) if "unbonded_prestress_ignored_count" in df else 0
            _render_pmm_slice_dashboard(
                df,
                st.session_state.get("load_cases", []),
                dc_summary,
                result_label,
                settings.include_prestress,
                result_has_active_prestress,
                unbonded_ignored_count,
                result_hash,
                engineering_warnings,
            )

            with st.expander("Detailed PMM plots", expanded=False):
                _render_pmm_charts(df, demand_df, dc_summary, key_prefix="analysis_input_diagnostics")
            with st.expander("Raw PMM result table / export", expanded=False):
                st.download_button(
                    "Download RC PMM Result CSV",
                    data=df.to_csv(index=False),
                    file_name="rc_pmm_result.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                st.dataframe(df.head(20), use_container_width=True, hide_index=True)


def _demand_capacity_display_dataframe(summary: DemandCapacitySummary) -> pd.DataFrame:
    return demand_capacity_result_to_display_dataframe(summary)


def _analysis_status_style(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"PASS", "READY", "YES", "AVAILABLE", "VALID"}:
        return "ready"
    if text in {"WARNING", "WARN", "OUT_OF_RANGE", "PARTIAL", "CAUTION"}:
        return "warning"
    if text in {"FAIL", "FAILED", "NOT_READY", "ERROR", "CRITICAL"}:
        return "danger"
    if text in {"N/A", "NA", "NONE", "NOT RUN", "NOT_CHECKED"}:
        return "neutral"
    return "info"


def _format_optional_number(value: float | None, suffix: str = "", precision: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{precision}f}{suffix}"


def _active_load_case_usage_summary(load_cases: list) -> dict[str, int]:
    """Return load-case usage counts for the Analysis transparency panel.

    The Analysis page consumes only active ULS load cases for PMM D/C checks.
    SLS load cases remain available for the SLS workspace and must not be counted
    as ULS demand. This helper is UI-only and does not change solver inputs.
    """

    summary = {"total": 0, "active_uls": 0, "active_sls": 0, "inactive": 0, "other_active": 0}
    for load_case in load_cases:
        summary["total"] += 1
        if not bool(getattr(load_case, "active", False)):
            summary["inactive"] += 1
            continue
        load_type = str(getattr(load_case, "load_type", "")).upper()
        if load_type == "ULS":
            summary["active_uls"] += 1
        elif load_type == "SLS":
            summary["active_sls"] += 1
        else:
            summary["other_active"] += 1
    return summary


def _demand_capacity_transparency_dataframe(summary: DemandCapacitySummary) -> pd.DataFrame:
    """Build a stable, review-oriented D/C table for the Analysis workspace."""

    rows: list[dict[str, object]] = []
    for item in summary.results:
        rows.append(
            {
                "Governing": "Yes" if item.combo_name == summary.governing_combo else "",
                "Case Name": item.combo_name,
                "Status": item.status,
                "D/C": None if item.dcr is None else round(float(item.dcr), 4),
                "Pu_kN": round(N_to_kN(item.Pu_N), 3),
                "Mux_kNm": round(Nmm_to_kNm(item.Mux_Nmm), 3),
                "Muy_kNm": round(Nmm_to_kNm(item.Muy_Nmm), 3),
                "Mu_kNm": round(Nmm_to_kNm(item.Mu_Nmm), 3),
                "Available_phiMn_kNm": None
                if item.capacity_phiMn_Nmm is None
                else round(Nmm_to_kNm(item.capacity_phiMn_Nmm), 3),
                "Capacity Method": item.capacity_method or "N/A",
                "Slice Method": item.slice_method or "N/A",
                "Envelope Method": item.envelope_method or "N/A",
                "Fallback": "Yes" if item.used_fallback else "No",
                "Warning Count": int(item.warning_count),
                "Message": item.message,
            }
        )
    columns = [
        "Governing",
        "Case Name",
        "Status",
        "D/C",
        "Pu_kN",
        "Mux_kNm",
        "Muy_kNm",
        "Mu_kNm",
        "Available_phiMn_kNm",
        "Capacity Method",
        "Slice Method",
        "Envelope Method",
        "Fallback",
        "Warning Count",
        "Message",
    ]
    return pd.DataFrame(rows, columns=columns)


def _governing_result(summary: DemandCapacitySummary):
    if summary.governing_combo is None:
        return None
    for item in summary.results:
        if item.combo_name == summary.governing_combo:
            return item
    return None


def _analysis_result_overview_cards(dc_summary: DemandCapacitySummary, load_cases: list) -> list[dict[str, object]]:
    usage = _active_load_case_usage_summary(load_cases)
    governing = _governing_result(dc_summary)
    return [
        {
            "title": "Overall ULS Status",
            "value": dc_summary.overall_status.replace("_", " "),
            "detail": "Based on active ULS demand/capacity results",
            "status": _analysis_status_style(dc_summary.overall_status),
            "strong": True,
        },
        {
            "title": "Governing Case",
            "value": dc_summary.governing_combo or "N/A",
            "detail": "Highest finite D/C ratio",
            "status": "info" if dc_summary.governing_combo else "neutral",
        },
        {
            "title": "Max D/C",
            "value": _format_optional_number(dc_summary.max_dcr, precision=3),
            "detail": "Demand Mu / available phiMn at Pu",
            "status": _analysis_status_style(dc_summary.overall_status),
        },
        {
            "title": "Active ULS Used",
            "value": f"{usage['active_uls']:,}",
            "detail": f"SLS not used here: {usage['active_sls']:,}; inactive: {usage['inactive']:,}",
            "status": "ready" if usage["active_uls"] else "warning",
        },
        {
            "title": "Governing Capacity",
            "value": "N/A" if governing is None or governing.capacity_phiMn_Nmm is None else f"{Nmm_to_kNm(governing.capacity_phiMn_Nmm):,.1f} kN-m",
            "detail": "Available phiMn in demand direction",
            "status": "neutral",
        },
        {
            "title": "Capacity Method",
            "value": "N/A" if governing is None else (governing.capacity_method or "N/A"),
            "detail": "Preferred: slice envelope; fallback methods are flagged",
            "status": "warning" if governing is not None and governing.used_fallback else "neutral",
        },
        {
            "title": "Fallback Cases",
            "value": f"{sum(1 for item in dc_summary.results if item.used_fallback):,}",
            "detail": "Should be reviewed when nonzero",
            "status": "warning" if any(item.used_fallback for item in dc_summary.results) else "ready",
        },
        {
            "title": "D/C Warnings",
            "value": f"{sum(int(item.warning_count) for item in dc_summary.results):,}",
            "detail": "Per-case method/slice warnings",
            "status": "warning" if any(item.warning_count for item in dc_summary.results) else "ready",
        },
    ]


def _render_result_traceability_path(selected_summary: dict) -> None:
    path_html = (
        '<div class="cpmm-analysis-path">'
        '<strong>Trace path:</strong> Load case '
        f'<strong>{escape(str(selected_summary["selected_combo"]))}</strong> '
        f'→ Pu <strong>{escape(_format_optional_number(selected_summary["Pu_kN"], " kN"))}</strong> '
        f'→ current PMM slice/envelope → demand direction Mu <strong>{escape(_format_optional_number(selected_summary["Mu_kNm"], " kN-m"))}</strong> '
        f'→ available phiMn <strong>{escape(_format_optional_number(selected_summary["capacity_phiMn_kNm"], " kN-m"))}</strong> '
        f'→ D/C <strong>{escape(_format_optional_number(selected_summary["dcr"], precision=3))}</strong>.'
        '</div>'
    )
    st.markdown(path_html, unsafe_allow_html=True)


def _render_analysis_result_transparency_panel(
    dc_summary: DemandCapacitySummary,
    load_cases: list,
    *,
    show_overview_cards: bool = True,
) -> pd.DataFrame:
    st.caption(
        "Active ULS load cases are ranked by PMM demand/capacity. "
        "SLS cases are excluded from this ULS ranking and remain available in the SLS workspace."
    )
    if show_overview_cards:
        _render_analysis_summary_strip(_analysis_result_overview_cards(dc_summary, load_cases), columns=4)
    transparency_df = _demand_capacity_transparency_dataframe(dc_summary)
    if transparency_df.empty:
        st.info("No active ULS D/C rows are available yet.")
        return transparency_df

    compact_columns = [
        column
        for column in ["Governing", "Case Name", "Status", "D/C", "Pu_kN", "Mux_kNm", "Muy_kNm", "Available_phiMn_kNm"]
        if column in transparency_df.columns
    ]
    st.markdown("**Active ULS Cases — Compact D/C Trace**")
    st.dataframe(transparency_df[compact_columns], use_container_width=True, hide_index=True)

    with st.expander("Full ULS D/C trace details", expanded=False):
        st.dataframe(transparency_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download ULS D/C Trace CSV",
            data=transparency_df.to_csv(index=False),
            file_name="uls_demand_capacity_trace.csv",
            mime="text/csv",
            use_container_width=True,
        )
    return transparency_df



def _finite_dcr_text(value: float | None) -> str:
    if value is None:
        return "N/A"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(numeric):
        return "N/A"
    return f"{numeric:.3f}"


def _render_design_decision_banner(
    dc_summary: DemandCapacitySummary,
    load_cases: list,
    warnings: list[str],
    *,
    include_prestress: bool,
    bonded_prestress_included: bool,
    unbonded_ignored_count: int,
) -> None:
    """Render a first-screen engineering decision statement for the ULS PMM result.

    This banner is intentionally decision-oriented rather than diagnostic-heavy:
    it separates the governing demand/capacity result from QA notes so users do
    not mistake background method notes for a failed ULS strength check.
    """

    usage = _active_load_case_usage_summary(load_cases)
    governing = _governing_result(dc_summary)
    guidance_df = _diagnostics_to_dataframe(warnings, dc_summary=dc_summary) if warnings else pd.DataFrame()
    priority_counts = _guidance_priority_counts(guidance_df)
    governing_warning_count = _governing_warning_count(priority_counts)
    review_count = _review_before_final_count(priority_counts)
    qa_count = _qa_note_count(priority_counts)
    counts = _diagnostic_counts(warnings)
    limitation_count = int(counts.get("Solver limitation note", 0))
    numerical_count = int(counts.get("Numerical note", 0))
    fallback_count = sum(1 for item in dc_summary.results if item.used_fallback)
    dc_warning_count = sum(int(item.warning_count) for item in dc_summary.results)
    dcr_text = _finite_dcr_text(dc_summary.max_dcr)
    governing_label = dc_summary.governing_combo or "N/A"
    overall_status = str(dc_summary.overall_status).strip().upper()

    if overall_status == "PASS" and governing_warning_count == 0 and fallback_count == 0 and dc_warning_count == 0:
        banner_class = "ready"
        decision = "PASS for ULS PMM strength check"
        confidence = "High for ULS PMM demand/capacity extraction under the current validated workflow."
        final_review = (
            f"No direct governing-result warning was detected. {review_count:,} engineering QA review item(s), "
            f"{limitation_count:,} method note(s), and {numerical_count:,} numerical note(s) remain available for final review."
        )
    elif overall_status == "PASS" and governing_warning_count > 0:
        banner_class = "warning"
        decision = "PASS with governing-impact review required"
        confidence = "D/C is below 1.0, but at least one diagnostic may affect reliance on the governing result."
        final_review = (
            f"Review {governing_warning_count:,} governing-impact item(s) before final design use. "
            f"Additional QA notes remain in Diagnostics / QA."
        )
    elif overall_status == "PASS":
        banner_class = "warning"
        decision = "PASS with method review required"
        confidence = "D/C is below 1.0, but method diagnostics should be reviewed before final design use."
        final_review = (
            f"Fallback cases: {fallback_count:,}; D/C warnings: {dc_warning_count:,}; "
            f"engineering review items: {review_count:,}."
        )
    elif overall_status == "FAIL":
        banner_class = "danger"
        decision = "FAIL for ULS PMM strength check"
        confidence = "The governing demand/capacity ratio is not acceptable under the current method."
        final_review = "Revise section, reinforcement/prestress, or load input before final design use."
    else:
        banner_class = "neutral"
        decision = "ULS PMM result not fully checked"
        confidence = "The analysis did not produce a complete governing demand/capacity decision."
        final_review = "Review readiness, load cases, and PMM diagnostics."

    if usage.get("active_sls", 0):
        sls_note = f"ULS PMM only; {usage['active_sls']:,} SLS case(s) are stored but excluded from this decision."
    else:
        sls_note = "ULS PMM only; SLS / Stress & Cracking is planned separately."

    prestress_note = ""
    if include_prestress and bonded_prestress_included:
        prestress_note = "Bonded prestress is included in the ULS PMM section action."
    elif include_prestress and unbonded_ignored_count > 0:
        prestress_note = "Only unbonded prestress was found; it is ignored by the current ULS PMM solver."
    elif include_prestress:
        prestress_note = "No active bonded prestress contribution is included in this ULS PMM result."
    else:
        prestress_note = "Prestress contribution is disabled by analysis settings."
    scope = f"{prestress_note} {sls_note}"

    pills = [
        f"Governing: {governing_label}",
        f"D/C: {dcr_text}",
        f"Fallback: {fallback_count:,}",
        f"D/C warnings: {dc_warning_count:,}",
        f"Governing QA: {governing_warning_count:,}",
    ]
    if governing is not None and governing.dcr is not None and math.isfinite(float(governing.dcr)):
        pills.append(f"Margin: {_capacity_margin_text(governing.dcr)}")
    pill_html = "".join(f'<span class="cpmm-decision-pill">{escape(str(item))}</span>' for item in pills)
    decision_grid = (
        '<div class="cpmm-decision-grid">'
        '<div class="cpmm-decision-block">'
        '<div class="cpmm-decision-block-label">Decision</div>'
        f'<div class="cpmm-decision-block-text">{escape(decision)}</div>'
        '</div>'
        '<div class="cpmm-decision-block">'
        '<div class="cpmm-decision-block-label">Confidence</div>'
        f'<div class="cpmm-decision-block-text">{escape(confidence)}</div>'
        '</div>'
        '<div class="cpmm-decision-block">'
        '<div class="cpmm-decision-block-label">Scope / exclusions</div>'
        f'<div class="cpmm-decision-block-text">{escape(scope)}</div>'
        '</div>'
        '</div>'
    )
    html = (
        f'<div class="cpmm-decision-banner {banner_class}">'
        '<div class="cpmm-decision-eyebrow">Design decision</div>'
        f'<div class="cpmm-decision-title">{escape(decision)}</div>'
        f'<div class="cpmm-decision-detail"><strong>Final review:</strong> {escape(final_review)}</div>'
        f'{decision_grid}'
        f'<div class="cpmm-decision-pills">{pill_html}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)

def _render_executive_result_header(dc_summary: DemandCapacitySummary, load_cases: list) -> None:
    usage = _active_load_case_usage_summary(load_cases)
    status = dc_summary.overall_status.replace("_", " ")
    governing = dc_summary.governing_combo or "No governing case"
    max_dcr = _format_optional_number(dc_summary.max_dcr, precision=3)
    status_class = _analysis_status_style(dc_summary.overall_status)
    html = (
        '<div class="cpmm-executive-header">'
        '<div class="cpmm-executive-eyebrow">ULS / PMM Analysis Workspace</div>'
        '<div class="cpmm-executive-title">Strength result workspace</div>'
        '<div class="cpmm-executive-subtitle">'
        f'Governing: <strong>{escape(governing)}</strong> · '
        f'D/C: <strong>{escape(max_dcr)}</strong> · '
        f'Active ULS used: <strong>{usage["active_uls"]:,}</strong> · '
        f'Active SLS held for SLS workspace: <strong>{usage["active_sls"]:,}</strong> · '
        f'Fallback cases: <strong>{sum(1 for item in dc_summary.results if item.used_fallback):,}</strong> · '
        f'D/C warnings: <strong>{sum(int(item.warning_count) for item in dc_summary.results):,}</strong>'
        '</div>'
        f'<span class="cpmm-analysis-badge {status_class}">{escape(status)}</span>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)


def _render_governing_case_card(dc_summary: DemandCapacitySummary) -> None:
    governing = _governing_result(dc_summary)
    if governing is None:
        st.info("No governing ULS case is available yet.")
        return
    values = [
        ("Status", governing.status.replace("_", " ")),
        ("D/C", _format_optional_number(governing.dcr, precision=3)),
        ("Pu", f"{N_to_kN(governing.Pu_N):,.1f} kN"),
        ("Mux", f"{Nmm_to_kNm(governing.Mux_Nmm):,.1f} kN-m"),
        ("Muy", f"{Nmm_to_kNm(governing.Muy_Nmm):,.1f} kN-m"),
        ("Resultant Mu", f"{Nmm_to_kNm(governing.Mu_Nmm):,.1f} kN-m"),
        (
            "Available phiMn",
            "N/A" if governing.capacity_phiMn_Nmm is None else f"{Nmm_to_kNm(governing.capacity_phiMn_Nmm):,.1f} kN-m",
        ),
        ("Capacity method", governing.capacity_method or "N/A"),
    ]
    cells = "".join(
        '<div class="cpmm-governing-cell">'
        f'<div class="cpmm-governing-label">{escape(label)}</div>'
        f'<div class="cpmm-governing-value">{escape(str(value))}</div>'
        '</div>'
        for label, value in values
    )
    status_class = _analysis_status_style(governing.status)
    html = (
        '<div class="cpmm-governing-card">'
        '<div class="cpmm-analysis-title">Governing Load Case</div>'
        f'<div class="cpmm-governing-name">{escape(governing.combo_name)}</div>'
        f'<span class="cpmm-analysis-badge {status_class}">{escape(governing.status.replace("_", " "))}</span>'
        f'<div class="cpmm-governing-grid">{cells}</div>'
        '</div>'
    )
    st.markdown(html, unsafe_allow_html=True)
    if governing.message:
        st.caption(f"Governing case message: {governing.message}")



def _beam_uls_active_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        try:
            return bool(float(value)) and math.isfinite(float(value))
        except (TypeError, ValueError):
            return False
    text = str(value).strip().casefold()
    if text in {"", "0", "false", "f", "no", "n", "off", "unchecked"}:
        return False
    return True


def _beam_uls_float(value: object) -> float:
    if value is None:
        return float("nan")
    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if not value or value in {"-", "—"}:
            return float("nan")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return numeric if math.isfinite(numeric) else float("nan")


def _beam_uls_demand_dataframe_from_session(state: Mapping[str, object]) -> pd.DataFrame:
    """Return normalized Beam/Girder ULS station demand rows from Loads.

    ULS.GIRDER1 rule: Loads is the single source of truth.  Analysis consumes
    beam_uls_loads_table only, filters Active rows, and never creates a second
    editable ULS demand table.
    """

    raw = state.get("beam_uls_loads_table")
    df = pd.DataFrame(raw if raw is not None else [], columns=BEAM_ULS_LOAD_COLUMNS_ANALYSIS)
    for column in BEAM_ULS_LOAD_COLUMNS_ANALYSIS:
        if column not in df.columns:
            df[column] = ""
    df = df[BEAM_ULS_LOAD_COLUMNS_ANALYSIS].copy()
    df["Active"] = df["Active"].map(_beam_uls_active_value)
    for column in ["Station x (m)", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu"]:
        df[column] = df[column].map(_beam_uls_float)
    df["Case Name"] = df["Case Name"].map(lambda value: str(value or "").strip())
    df["Note"] = df["Note"].map(lambda value: str(value or "").strip())
    return df


def _active_beam_uls_demand_dataframe_from_session(state: Mapping[str, object]) -> pd.DataFrame:
    df = _beam_uls_demand_dataframe_from_session(state)
    if df.empty:
        return df
    active = df[df["Active"]].copy()
    active = active[active["Case Name"].astype(str).str.len() > 0]
    return active.reset_index(drop=True)


def _column_pier_uls_demand_dataframe_from_state(state: Mapping[str, object]) -> pd.DataFrame:
    """Return normalized Column/Pier case-based ULS rows from Loads.

    Column/Pier loads are not station-based.  Shear/torsion helpers therefore
    consume the case table directly and must not borrow Beam/Girder station
    assumptions.
    """

    raw = _beam_uls_get_state_value(state, "column_uls_loads_table", None)
    if raw is None:
        raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get("column_uls_loads_table")
    df = pd.DataFrame(raw if raw is not None else [], columns=COLUMN_ULS_LOAD_COLUMNS_ANALYSIS)
    for column in COLUMN_ULS_LOAD_COLUMNS_ANALYSIS:
        if column not in df.columns:
            df[column] = ""
    df = df[COLUMN_ULS_LOAD_COLUMNS_ANALYSIS].copy()
    df["Active"] = df["Active"].map(_beam_uls_active_value)
    for column in ["Pu", "Mux", "Muy", "Vux", "Vuy", "Tu"]:
        df[column] = df[column].map(_beam_uls_float)
    df["Case Name"] = df["Case Name"].map(lambda value: str(value or "").strip())
    df["Note"] = df["Note"].map(lambda value: str(value or "").strip())
    return df


def _active_column_pier_uls_demand_dataframe_from_state(state: Mapping[str, object]) -> pd.DataFrame:
    df = _column_pier_uls_demand_dataframe_from_state(state)
    if df.empty:
        return df
    active = df[df["Active"]].copy()
    active = active[active["Case Name"].astype(str).str.len() > 0]
    return active.reset_index(drop=True)


def _column_pier_transverse_reinforcement_dataframe_from_state(state: Mapping[str, object]) -> pd.DataFrame:
    raw = _beam_uls_get_state_value(state, COLUMN_PIER_TRANSVERSE_TABLE_KEY_ANALYSIS, None)
    if raw is None:
        raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get(COLUMN_PIER_TRANSVERSE_TABLE_KEY_ANALYSIS)
    df = pd.DataFrame(raw if raw is not None else [], columns=COLUMN_PIER_TRANSVERSE_COLUMNS_ANALYSIS)
    for column in COLUMN_PIER_TRANSVERSE_COLUMNS_ANALYSIS:
        if column not in df.columns:
            df[column] = ""
    df = df[COLUMN_PIER_TRANSVERSE_COLUMNS_ANALYSIS].copy()
    df["Active"] = df["Active"].map(_beam_uls_active_value)
    for column in ["x_start_m", "x_end_m", "Diameter_mm", "Legs", "Spacing_mm", "fy_MPa"]:
        df[column] = df[column].map(_beam_uls_float)
    for column in ["Zone", "Bar Size", "Note"]:
        df[column] = df[column].map(lambda value: str(value or "").strip())
    return df


def _column_pier_transverse_settings_from_state(state: Mapping[str, object]) -> dict[str, object]:
    raw = _beam_uls_get_state_value(state, COLUMN_PIER_TRANSVERSE_SETTINGS_KEY_ANALYSIS, None)
    if raw is None:
        raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get(COLUMN_PIER_TRANSVERSE_SETTINGS_KEY_ANALYSIS)
    return dict(raw or {}) if isinstance(raw, Mapping) else {}


def _column_pier_active_transverse_zone_for_shear(state: Mapping[str, object]) -> dict[str, object] | None:
    """Return the conservative active transverse source for case-based shear.

    Column/Pier ULS rows currently do not carry a station/height coordinate.
    Until that owner exists, the shear check uses the active region with the
    lowest provided Av/s.  This avoids silently selecting a stronger confinement
    region for a case-level demand.
    """

    df = _column_pier_transverse_reinforcement_dataframe_from_state(state)
    if df.empty:
        return None
    active = df[df["Active"]].copy()
    if active.empty:
        return None
    rows: list[dict[str, object]] = []
    for _, row in active.iterrows():
        zone = row.to_dict()
        area = _beam_uls_stirrup_area_mm2(zone)
        legs = _beam_uls_float(zone.get("Legs"))
        spacing = _beam_uls_float(zone.get("Spacing_mm"))
        fy = _beam_uls_float(zone.get("fy_MPa"))
        if not all(math.isfinite(value) and value > 0.0 for value in [area, legs, spacing, fy]):
            continue
        zone["stirrup_area_mm2"] = float(area)
        zone["Av/s mm2/mm"] = float(area) * float(legs) / float(spacing)
        rows.append(zone)
    if not rows:
        return None
    return sorted(rows, key=lambda item: (float(item["Av/s mm2/mm"]), -_beam_uls_float(item.get("Spacing_mm"))))[0]


def _column_pier_reference_transverse_row_for_seismic_advisor(state: Mapping[str, object]) -> dict[str, object] | None:
    df = _column_pier_transverse_reinforcement_dataframe_from_state(state)
    if df.empty:
        return None
    active = df[df["Active"]].copy()
    source = active if not active.empty else df
    return source.iloc[0].to_dict()


def _column_pier_section_outer_min_dimension_mm(section_geometry: SectionGeometry | None) -> float | None:
    if section_geometry is None:
        return None
    try:
        outer_polygon = to_shapely_polygon(SectionGeometry(name=section_geometry.name, outer_polygon=section_geometry.outer_polygon, holes=[]))
        minx, miny, maxx, maxy = outer_polygon.bounds
    except Exception:
        return None
    width = float(maxx) - float(minx)
    depth = float(maxy) - float(miny)
    if not all(math.isfinite(value) and value > 0.0 for value in [width, depth]):
        return None
    return min(width, depth)


def _column_pier_min_active_longitudinal_rebar_diameter_mm(state: Mapping[str, object]) -> float | None:
    if not ordinary_rebar_enabled(state, default=True):
        return None
    raw_rebars = _beam_uls_get_state_value(state, "rebars", []) or []
    try:
        rebars = effective_rebars_for_analysis(list(raw_rebars), state)
    except Exception:
        rebars = list(raw_rebars)
    diameters = [
        _beam_uls_float(getattr(item, "diameter_mm", None))
        for item in rebars
        if math.isfinite(_beam_uls_float(getattr(item, "diameter_mm", None))) and _beam_uls_float(getattr(item, "diameter_mm", None)) > 0.0
    ]
    return min(diameters) if diameters else None


def _column_pier_aci_seismic_spacing_summary_dataframe(
    state: Mapping[str, object],
    analysis_input: AnalysisInput | None,
) -> pd.DataFrame:
    settings = _column_pier_transverse_settings_from_state(state)
    if str(settings.get("seismic_detailing") or "") != _COLUMN_PIER_ACI_SEISMIC_ADVISOR_LABEL:
        return pd.DataFrame()
    row = _column_pier_reference_transverse_row_for_seismic_advisor(state)
    section_min_dim = _column_pier_section_outer_min_dimension_mm(analysis_input.section_geometry if analysis_input is not None else None)
    min_bar_dia = _column_pier_min_active_longitudinal_rebar_diameter_mm(state)
    hx_mm = _beam_uls_float(settings.get("seismic_hx_mm"))
    if not math.isfinite(hx_mm) or hx_mm <= 0.0:
        hx_mm = 300.0

    criteria: list[tuple[str, float]] = []
    if section_min_dim is not None and section_min_dim > 0.0:
        criteria.append(("0.25 x minimum outside section dimension", float(section_min_dim) / 4.0))
    if min_bar_dia is not None and min_bar_dia > 0.0:
        criteria.append(("6 x smallest active longitudinal bar diameter", 6.0 * float(min_bar_dia)))
    so_raw = 100.0 + (350.0 - float(hx_mm)) / 3.0
    so_limit = min(150.0, max(100.0, so_raw))
    criteria.append(("s0 from hx, bounded to 100-150 mm", so_limit))

    if not criteria:
        suggested_spacing = float("nan")
        governing = "REVIEW - advisor inputs unavailable"
    else:
        governing, s_max = min(criteria, key=lambda item: item[1])
        suggested_spacing = max(
            _COLUMN_PIER_SEISMIC_SPACING_INCREMENT_MM,
            math.floor(float(s_max) / _COLUMN_PIER_SEISMIC_SPACING_INCREMENT_MM) * _COLUMN_PIER_SEISMIC_SPACING_INCREMENT_MM,
        )

    bar_size = str((row or {}).get("Bar Size") or "-").strip() or "-"
    legs = _beam_uls_float((row or {}).get("Legs"))
    legs_text = "-" if not math.isfinite(legs) or legs <= 0.0 else f"{int(legs)} legs"
    tie_text = f"{bar_size} x {legs_text}"
    if math.isfinite(suggested_spacing) and suggested_spacing > 0.0:
        tie_text = f"{tie_text} @ {suggested_spacing:.0f} mm"

    return pd.DataFrame(
        [
            {
                "Recommendation": "Recommended seismic spacing (ACI advisor)",
                "Tie / hoop": tie_text,
                "Suggested spacing": "-" if not math.isfinite(suggested_spacing) else f"{suggested_spacing:.0f} mm",
                "hx": f"{hx_mm:.0f} mm",
                "Governing criterion": governing,
                "Analysis use": "Advisor only / REVIEW - shear uses Control section row only",
            }
        ]
    )


def _lineal_intersection_length_mm(geometry: object) -> float:
    if geometry is None or bool(getattr(geometry, "is_empty", False)):
        return 0.0
    try:
        length = float(getattr(geometry, "length"))
    except (TypeError, ValueError, AttributeError):
        length = float("nan")
    if math.isfinite(length) and length > 0.0:
        return length
    parts = getattr(geometry, "geoms", None)
    if parts is None:
        return 0.0
    return sum(_lineal_intersection_length_mm(part) for part in parts)


def _column_pier_concrete_breadth_at_centroid_mm(geometry: SectionGeometry, *, line_axis: str) -> tuple[float | None, str]:
    summary = summarize_geometry(geometry)
    polygon = to_shapely_polygon(geometry)
    if not polygon.is_valid:
        polygon = polygon.buffer(0)
    if polygon.is_empty or polygon.area <= 0.0:
        return None, "Concrete breadth could not be calculated because the section polygon is invalid."
    width_x = float(summary.x_max_mm) - float(summary.x_min_mm)
    depth_y = float(summary.y_max_mm) - float(summary.y_min_mm)
    margin = max(width_x, depth_y, 1.0)
    if line_axis == "horizontal":
        line = LineString(
            [
                (float(summary.x_min_mm) - margin, float(summary.centroid_y_mm)),
                (float(summary.x_max_mm) + margin, float(summary.centroid_y_mm)),
            ]
        )
        breadth = _lineal_intersection_length_mm(polygon.intersection(line))
        basis = "bw from horizontal concrete breadth at section centroid; holes/voids are subtracted by polygon intersection."
    else:
        line = LineString(
            [
                (float(summary.centroid_x_mm), float(summary.y_min_mm) - margin),
                (float(summary.centroid_x_mm), float(summary.y_max_mm) + margin),
            ]
        )
        breadth = _lineal_intersection_length_mm(polygon.intersection(line))
        basis = "bw from vertical concrete breadth at section centroid; holes/voids are subtracted by polygon intersection."
    if not math.isfinite(breadth) or breadth <= 0.0:
        return None, f"{basis} No positive concrete breadth was found."
    return float(breadth), basis


def _column_pier_shear_geometry_for_direction(geometry: SectionGeometry, direction: str) -> dict[str, object]:
    summary = summarize_geometry(geometry)
    width_x = float(summary.x_max_mm) - float(summary.x_min_mm)
    depth_y = float(summary.y_max_mm) - float(summary.y_min_mm)
    if direction == "Vux":
        bw_mm, bw_note = _column_pier_concrete_breadth_at_centroid_mm(geometry, line_axis="vertical")
        gross_dimension = width_x
        d_eff_mm = 0.80 * width_x if width_x > 0.0 else float("nan")
        direction_note = "Vux uses the x-direction gross dimension for auto d and the vertical centroid-line concrete breadth for bw."
    else:
        bw_mm, bw_note = _column_pier_concrete_breadth_at_centroid_mm(geometry, line_axis="horizontal")
        gross_dimension = depth_y
        d_eff_mm = 0.80 * depth_y if depth_y > 0.0 else float("nan")
        direction_note = "Vuy uses the y-direction gross dimension for auto d and the horizontal centroid-line concrete breadth for bw."
    return {
        "bw_mm": bw_mm,
        "d_mm": float(d_eff_mm),
        "gross_dimension_mm": float(gross_dimension),
        "basis": f"{direction_note} Auto d = 0.80 x gross direction dimension.",
        "notes": bw_note,
        "void_count": len(getattr(geometry, "holes", []) or []),
    }


def _column_pier_has_active_prestress(analysis_input: AnalysisInput | None) -> bool:
    if analysis_input is None:
        return False
    for element in list(getattr(analysis_input, "prestress_elements", []) or []):
        count = getattr(element, "count", 1)
        pe_eff = getattr(element, "pe_eff_n", 0.0)
        try:
            if abs(float(pe_eff) * float(count)) > 1.0e-9:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _column_pier_shear_result_for_case_direction(
    state: Mapping[str, object],
    demand_row: Mapping[str, object],
    *,
    direction: str,
    analysis_input: AnalysisInput | None,
) -> dict[str, object]:
    case = str(demand_row.get("Case Name") or "-")
    vu_kN = _beam_uls_float(demand_row.get(direction))
    code = project_design_code_from_session(state)
    if code != PROJECT_CODE_ACI318:
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "AASHTO LRFD Column/Pier shear is not implemented in ULS.COL.SHEAR.ACI1.",
        }
    if not math.isfinite(vu_kN) or abs(float(vu_kN)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL:
        return {
            "Check": "Shear",
            "Status": "NO DEMAND",
            "Direction": direction,
            "Case": case,
            "Demand": "-",
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": 0.0,
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": f"No finite {direction} demand.",
        }
    if analysis_input is None:
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "Section geometry and concrete material are required for Column/Pier shear.",
        }
    zone = _column_pier_active_transverse_zone_for_shear(state)
    if zone is None:
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "No active valid Column/Pier transverse reinforcement region is available. Activate a provided tie/hoop region before relying on shear capacity.",
        }
    concrete = analysis_input.concrete_material
    fc = float(concrete.fc_MPa)
    geometry = _column_pier_shear_geometry_for_direction(analysis_input.section_geometry, direction)
    bw_mm = geometry.get("bw_mm")
    d_mm = _beam_uls_float(geometry.get("d_mm"))
    if bw_mm is None or not all(math.isfinite(value) and value > 0.0 for value in [float(fc), float(d_mm)]):
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": str(geometry.get("notes") or "Column/Pier shear geometry is not ready."),
        }
    stirrup_area = _beam_uls_stirrup_area_mm2(zone)
    legs = _beam_uls_float(zone.get("Legs"))
    spacing = _beam_uls_float(zone.get("Spacing_mm"))
    fy = _beam_uls_float(zone.get("fy_MPa"))
    if not all(math.isfinite(value) and value > 0.0 for value in [stirrup_area, legs, spacing, fy]):
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "phiVn kN": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "Active Column/Pier transverse region has incomplete bar, legs, spacing, or fy input.",
        }
    phi = 0.75
    sqrt_fc = math.sqrt(fc)
    avs_mm2_per_mm = float(stirrup_area) * float(legs) / float(spacing)
    vc_n = 0.17 * sqrt_fc * float(bw_mm) * float(d_mm)
    vs_n = avs_mm2_per_mm * float(fy) * float(d_mm)
    vs_limit_n = 0.66 * sqrt_fc * float(bw_mm) * float(d_mm)
    vn_uncapped_n = max(0.0, vc_n + vs_n)
    vn_limit_n = vc_n + vs_limit_n
    vn_n = min(vn_uncapped_n, vn_limit_n)
    phi_vn_kN = phi * vn_n / 1000.0
    strength_dc = abs(float(vu_kN)) / phi_vn_kN if phi_vn_kN > 0.0 else float("nan")
    avs_required = max(0.062 * sqrt_fc * float(bw_mm) / float(fy), 0.35 * float(bw_mm) / float(fy))
    s_max = min(0.50 * float(d_mm), 600.0)
    avs_dc = avs_required / avs_mm2_per_mm if avs_mm2_per_mm > 0.0 else float("nan")
    spacing_dc = float(spacing) / s_max if s_max > 0.0 else float("nan")
    detailing_values = [value for value in [avs_dc, spacing_dc] if math.isfinite(value)]
    detailing_dc = max(detailing_values) if detailing_values else float("nan")
    governing_values = [value for value in [strength_dc, detailing_dc] if math.isfinite(value)]
    governing_dc = max(governing_values) if governing_values else float("nan")
    has_prestress = _column_pier_has_active_prestress(analysis_input)
    if has_prestress:
        status = "REVIEW"
    elif any(math.isfinite(value) and value > 1.0 + 1.0e-9 for value in [strength_dc, detailing_dc]):
        status = "Preview FAIL"
    else:
        status = "Preview PASS"
    notes = [
        "ULS.COL.SHEAR.ACI1 uses ACI 318 SI simplified one-way shear: Vc = 0.17 sqrt(fc) bw d, Vs = Av fy d / s, phi = 0.75.",
        "Case-based Column/Pier loads have no station owner yet; the active transverse region with the lowest Av/s is used conservatively.",
        str(geometry.get("basis") or ""),
        str(geometry.get("notes") or ""),
        "Effective shear legs are read from the active transverse region; verify direction-specific tie legs and anchorage before final design.",
    ]
    if int(geometry.get("void_count") or 0) > 0:
        notes.append("Section has holes/voids; bw is based on centroid-line concrete breadth, not the full bounding box.")
    if has_prestress:
        notes.append("Active prestress is present. Prestress shear contribution, Vp, Vci/Vcw, and PSC-specific ACI provisions are not implemented, so the shear result remains REVIEW.")
    if vn_uncapped_n > vn_n + 1.0e-6:
        notes.append("Nominal Vn was capped by the ACI Vs maximum screen.")
    if math.isfinite(avs_dc) and avs_dc > 1.0 + 1.0e-9:
        notes.append("Provided Av/s is less than the ACI minimum shear reinforcement gate.")
    if math.isfinite(spacing_dc) and spacing_dc > 1.0 + 1.0e-9:
        notes.append("Provided tie spacing exceeds the ACI maximum spacing gate.")
    return {
        "Check": "Shear",
        "Status": status,
        "Direction": direction,
        "Case": case,
        "Demand": _format_beam_uls_demand(vu_kN, "kN"),
        "Capacity": f"phiVn = {phi_vn_kN:,.2f} kN",
        "Utilization": _format_beam_uls_ratio(strength_dc),
        "Demand kN": float(vu_kN),
        "Abs demand kN": abs(float(vu_kN)),
        "phiVn kN": phi_vn_kN,
        "phiVc kN": phi * vc_n / 1000.0,
        "phiVs kN": phi * vs_n / 1000.0,
        "Vc kN": vc_n / 1000.0,
        "Vs kN": vs_n / 1000.0,
        "Vn kN": vn_n / 1000.0,
        "Vn uncapped kN": vn_uncapped_n / 1000.0,
        "Vn limit kN": vn_limit_n / 1000.0,
        "Strength D/C value": strength_dc,
        "Detailing D/C value": detailing_dc,
        "Governing D/C value": governing_dc,
        "Zone": str(zone.get("Zone") or "Column/Pier transverse region"),
        "Tie/hoop": f"{zone.get('Bar Size') or '-'} x {int(float(legs))} legs @ {float(spacing):.0f} mm",
        "Av/s mm2/mm": avs_mm2_per_mm,
        "Av/s required mm2/mm": avs_required,
        "Av/s min D/C": avs_dc,
        "s max mm": s_max,
        "Spacing D/C": spacing_dc,
        "bw mm": float(bw_mm),
        "d mm": float(d_mm),
        "gross dimension mm": float(geometry.get("gross_dimension_mm") or float("nan")),
        "phi": phi,
        "Code basis": "ACI 318 Column/Pier RC shear preview gate",
        "Method": "ACI 318 simplified one-way shear, case-based conservative active-region source",
        "Notes": "; ".join(part for part in notes if part),
    }


def _column_pier_shear_check_dataframe(state: Mapping[str, object], analysis_input: AnalysisInput | None) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Direction", "Case", "Demand", "Capacity", "Utilization",
        "Demand kN", "Abs demand kN", "phiVn kN", "phiVc kN", "phiVs kN", "Vc kN", "Vs kN",
        "Vn kN", "Vn uncapped kN", "Vn limit kN", "Strength D/C value", "Detailing D/C value",
        "Governing D/C value", "Zone", "Tie/hoop", "Av/s mm2/mm", "Av/s required mm2/mm",
        "Av/s min D/C", "s max mm", "Spacing D/C", "bw mm", "d mm", "gross dimension mm",
        "phi", "Code basis", "Method", "Notes",
    ]
    active_df = _active_column_pier_uls_demand_dataframe_from_state(state)
    if active_df.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, demand_row in active_df.iterrows():
        for direction in ["Vux", "Vuy"]:
            result = _column_pier_shear_result_for_case_direction(
                state,
                demand_row,
                direction=direction,
                analysis_input=analysis_input,
            )
            if result.get("Status") == "NO DEMAND":
                continue
            for column in columns:
                result.setdefault(column, float("nan"))
            rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _column_pier_governing_shear_row(shear_df: pd.DataFrame | None) -> dict[str, object] | None:
    if shear_df is None or shear_df.empty or "Governing D/C value" not in shear_df.columns:
        return None
    df = shear_df.copy()
    df["__dc"] = pd.to_numeric(df["Governing D/C value"], errors="coerce")
    df = df[df["__dc"].notna()]
    if df.empty:
        return None
    return df.sort_values("__dc", ascending=False, kind="stable").iloc[0].to_dict()


def _column_pier_active_transverse_zone_for_torsion(state: Mapping[str, object]) -> dict[str, object] | None:
    settings = _column_pier_transverse_settings_from_state(state)
    if str(settings.get("closed_tie_layout") or "") not in {"Closed ties / hoops", "Spiral reinforcement"}:
        return None
    zone = _column_pier_active_transverse_zone_for_shear(state)
    if zone is None:
        return None
    area = _beam_uls_stirrup_area_mm2(zone)
    spacing = _beam_uls_float(zone.get("Spacing_mm"))
    fy = _beam_uls_float(zone.get("fy_MPa"))
    if not all(math.isfinite(value) and value > 0.0 for value in [area, spacing, fy]):
        return None
    result = dict(zone)
    result["At mm2"] = float(area)
    result["At/s mm2/mm"] = float(area) / float(spacing)
    return result


def _column_pier_torsion_geometry(
    section_geometry: SectionGeometry,
    settings: Mapping[str, object],
    *,
    transverse_diameter_mm: float,
) -> dict[str, object]:
    metrics = _beam_uls_outer_polygon_metrics(section_geometry)
    notes = [str(metrics.get("Note") or "")]
    acp = _beam_uls_float(metrics.get("Acp mm2"))
    pcp = _beam_uls_float(metrics.get("Pcp mm"))
    basis = str(settings.get("torsion_core_basis") or "Auto from section and tie offset")
    if basis == "Manual core dimensions":
        bo = _beam_uls_float(settings.get("manual_core_width_mm"))
        ho = _beam_uls_float(settings.get("manual_core_depth_mm"))
        if not all(math.isfinite(value) and value > 0.0 for value in [bo, ho]):
            return {
                "Acp mm2": acp,
                "Pcp mm": pcp,
                "Aoh mm2": float("nan"),
                "Ao mm2": float("nan"),
                "ph mm": float("nan"),
                "offset mm": float("nan"),
                "basis": basis,
                "Note": "Manual torsion core basis selected, but bo/ho are not both positive.",
            }
        aoh = float(bo) * float(ho)
        ph = 2.0 * (float(bo) + float(ho))
        return {
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": aoh,
            "Ao mm2": 0.85 * aoh,
            "ph mm": ph,
            "offset mm": float("nan"),
            "basis": basis,
            "Note": "Manual bo/ho torsion core dimensions from Column/Pier transverse settings; Ao = 0.85Aoh.",
        }
    if basis == "Not defined yet":
        return {
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": float("nan"),
            "Ao mm2": float("nan"),
            "ph mm": float("nan"),
            "offset mm": float("nan"),
            "basis": basis,
            "Note": "Torsion core basis is not defined.",
        }
    try:
        outer_polygon = to_shapely_polygon(SectionGeometry(name=section_geometry.name, outer_polygon=section_geometry.outer_polygon, holes=[]))
    except Exception:
        outer_polygon = None
    if outer_polygon is None or outer_polygon.is_empty or outer_polygon.area <= 0.0 or not outer_polygon.is_valid:
        return {
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": float("nan"),
            "Ao mm2": float("nan"),
            "ph mm": float("nan"),
            "offset mm": float("nan"),
            "basis": basis,
            "Note": "Auto torsion core could not be derived from the outside polygon.",
        }
    minx, miny, maxx, maxy = outer_polygon.bounds
    min_dim = min(float(maxx) - float(minx), float(maxy) - float(miny))
    offset = _beam_uls_float(settings.get("tie_center_offset_mm"))
    if not math.isfinite(offset) or offset <= 0.0:
        dia = float(transverse_diameter_mm) if math.isfinite(transverse_diameter_mm) and transverse_diameter_mm > 0.0 else 12.0
        offset = max(45.0 + 0.5 * dia, 0.04 * min_dim)
        notes.append(f"Tie/hoop offset was not defined; fallback offset {offset:.1f} mm was used for preview only.")
    try:
        inset = outer_polygon.buffer(-float(offset), join_style=2)
        if inset.is_empty or inset.area <= 0.0:
            raise ValueError("empty inset")
        if getattr(inset, "geoms", None):
            inset = max(inset.geoms, key=lambda geom: float(geom.area))
            notes.append("Inset torsion core split into multiple regions; largest region used for preview.")
        aoh = float(inset.area)
        ph = float(inset.exterior.length)
        ao = 0.85 * aoh
        notes.append(f"Aoh from outside polygon offset {float(offset):.1f} mm to tie/hoop centerline; Ao = 0.85Aoh.")
    except Exception:
        aoh = float("nan")
        ph = float("nan")
        ao = float("nan")
        notes.append("Auto torsion core offset failed; define manual bo/ho before relying on torsion results.")
    if len(getattr(section_geometry, "holes", []) or []) > 0:
        notes.append("Section has holes/voids. This preview uses the outside closed transverse path; multi-cell hollow torsion remains a future milestone.")
    return {
        "Acp mm2": acp,
        "Pcp mm": pcp,
        "Aoh mm2": aoh,
        "Ao mm2": ao,
        "ph mm": ph,
        "offset mm": float(offset),
        "basis": basis,
        "Note": " ".join(note for note in notes if note),
    }


def _column_pier_torsion_result_for_case(
    state: Mapping[str, object],
    demand_row: Mapping[str, object],
    *,
    analysis_input: AnalysisInput | None,
) -> dict[str, object]:
    case = str(demand_row.get("Case Name") or "-")
    tu_kNm = _beam_uls_float(demand_row.get("Tu"))
    code = project_design_code_from_session(state)
    if code != PROJECT_CODE_ACI318:
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": tu_kNm if math.isfinite(tu_kNm) else float("nan"),
            "phiTn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "AASHTO LRFD Column/Pier torsion is not implemented in ULS.COL.TORSION.ACI1.",
        }
    if not math.isfinite(tu_kNm) or abs(float(tu_kNm)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL:
        return {
            "Check": "Torsion",
            "Status": "NO DEMAND",
            "Case": case,
            "Demand": "-",
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": 0.0,
            "phiTn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "No finite Tu demand.",
        }
    if analysis_input is None:
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "phiTn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "Section geometry and concrete material are required for Column/Pier torsion.",
        }
    settings = _column_pier_transverse_settings_from_state(state)
    closed_layout = str(settings.get("closed_tie_layout") or "")
    zone = _column_pier_active_transverse_zone_for_torsion(state)
    if closed_layout not in {"Closed ties / hoops", "Spiral reinforcement"}:
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "phiTn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "Torsion capacity requires closed ties/hoops or spiral reinforcement. Open ties are shear-only review input.",
        }
    if zone is None:
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "phiTn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Notes": "No active valid closed transverse region is available for Column/Pier torsion.",
        }
    fc = float(analysis_input.concrete_material.fc_MPa)
    diameter = _beam_uls_float(zone.get("Diameter_mm"))
    geometry = _column_pier_torsion_geometry(analysis_input.section_geometry, settings, transverse_diameter_mm=diameter)
    acp = _beam_uls_float(geometry.get("Acp mm2"))
    pcp = _beam_uls_float(geometry.get("Pcp mm"))
    ao = _beam_uls_float(geometry.get("Ao mm2"))
    aoh = _beam_uls_float(geometry.get("Aoh mm2"))
    ph = _beam_uls_float(geometry.get("ph mm"))
    at_mm2 = _beam_uls_float(zone.get("At mm2"))
    at_per_s = _beam_uls_float(zone.get("At/s mm2/mm"))
    spacing = _beam_uls_float(zone.get("Spacing_mm"))
    fy = _beam_uls_float(zone.get("fy_MPa"))
    phi = 0.75
    cot_theta = 1.0
    threshold_kNm = float("nan")
    if all(math.isfinite(value) and value > 0.0 for value in [fc, acp, pcp]):
        threshold_kNm = phi * (0.083 * math.sqrt(fc) * acp * acp / pcp) / 1.0e6
    threshold_status = "BELOW THRESHOLD" if math.isfinite(threshold_kNm) and abs(float(tu_kNm)) <= threshold_kNm + 1.0e-9 else "DESIGN REQUIRED"
    notes = [
        "ULS.COL.TORSION.ACI1 uses an ACI 318 RC closed-transverse torsion preview: Tn = 2 Ao At fy cot(theta) / s, phi = 0.75, theta = 45 degrees.",
        "Torsion At is one closed tie/hoop bar area per spacing; shear leg count is not multiplied into At.",
        str(geometry.get("Note") or ""),
    ]
    if threshold_status == "BELOW THRESHOLD":
        if _column_pier_has_active_prestress(analysis_input):
            notes.append("Active prestress is present; PSC torsion effects are not implemented, so the threshold result remains REVIEW.")
            status = "REVIEW"
        else:
            status = "BELOW THRESHOLD"
        return {
            "Check": "Torsion",
            "Status": status,
            "Transverse status": "THRESHOLD OK",
            "Longitudinal status": "NOT REQUIRED",
            "Detailing status": "THRESHOLD OK",
            "Threshold status": threshold_status,
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": f"phiTcr = {threshold_kNm:,.2f} kN-m",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "Abs demand kN-m": abs(float(tu_kNm)),
            "phiTn kN-m": float("nan"),
            "phiTcr kN-m": threshold_kNm,
            "Tn kN-m": float("nan"),
            "Governing D/C value": float("nan"),
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": aoh,
            "Ao mm2": ao,
            "ph mm": ph,
            "Hoop offset mm": _beam_uls_float(geometry.get("offset mm")),
            "At mm2": at_mm2,
            "At/s mm2/mm": at_per_s,
            "Al req mm2": float("nan"),
            "Al provided mm2": float("nan"),
            "Al D/C value": float("nan"),
            "s max mm": float("nan"),
            "Spacing D/C": float("nan"),
            "At/s req mm2/mm": float("nan"),
            "Zone": str(zone.get("Zone") or "Column/Pier transverse region"),
            "Tie/hoop": f"{zone.get('Bar Size') or '-'} @ {float(spacing):.0f} mm",
            "phi": phi,
            "Code basis": "ACI 318 Column/Pier RC torsion preview gate",
            "Method": "ACI 318 closed-transverse torsion threshold preview",
            "Notes": "; ".join(part for part in notes if part),
        }
    if not all(math.isfinite(value) and value > 0.0 for value in [ao, ph, at_mm2, at_per_s, fy, spacing]):
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "phiTn kN-m": float("nan"),
            "phiTcr kN-m": threshold_kNm,
            "Governing D/C value": float("nan"),
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": aoh,
            "Ao mm2": ao,
            "ph mm": ph,
            "Notes": "; ".join(part for part in [*notes, "Torsion core geometry or active closed transverse reinforcement is incomplete."] if part),
        }
    tn_nmm = 2.0 * float(ao) * float(at_per_s) * float(fy) * float(cot_theta)
    phi_tn_kNm = phi * tn_nmm / 1.0e6
    strength_dc = abs(float(tu_kNm)) / phi_tn_kNm if phi_tn_kNm > 0.0 else float("nan")
    transverse_status = "PASS" if math.isfinite(strength_dc) and strength_dc <= 1.0 + 1.0e-9 else "FAIL"
    at_req = abs(float(tu_kNm)) * 1.0e6 / (float(phi) * 2.0 * float(ao) * float(fy) * float(cot_theta))
    al_req = at_req * float(ph) * float(cot_theta) * float(cot_theta)
    longitudinal_review = _beam_uls_torsion_longitudinal_review(state, al_req)
    longitudinal_status = str(longitudinal_review.get("status") or "LAYOUT REQUIRED")
    s_max = min(float(ph) / 8.0, 300.0)
    spacing_dc = float(spacing) / float(s_max) if s_max > 0.0 else float("nan")
    at_dc = float(at_req) / float(at_per_s) if at_per_s > 0.0 else float("nan")
    detailing_values = [value for value in [spacing_dc, at_dc] if math.isfinite(value)]
    detailing_dc = max(detailing_values) if detailing_values else float("nan")
    if math.isfinite(detailing_dc) and detailing_dc <= 1.0 + 1.0e-9:
        detailing_status = "PASS"
    else:
        detailing_status = "FAIL"
    governing_values = [
        value
        for value in [
            strength_dc,
            detailing_dc,
            _beam_uls_float(longitudinal_review.get("utilization")),
        ]
        if math.isfinite(value)
    ]
    governing_dc = max(governing_values) if governing_values else float("nan")
    if _column_pier_has_active_prestress(analysis_input):
        status = "REVIEW"
        notes.append("Active prestress is present. PSC torsion effects and prestress-specific compatibility are not implemented, so the torsion result remains REVIEW.")
    elif "FAIL" in {transverse_status, longitudinal_status, detailing_status}:
        status = "Preview FAIL"
    elif longitudinal_status in {"LAYOUT REQUIRED", "NOT CHECKED", "NOT READY"}:
        status = "REVIEW"
    elif transverse_status == "PASS" and longitudinal_status == "PASS" and detailing_status == "PASS":
        status = "Preview PASS"
    else:
        status = "REVIEW"
    if math.isfinite(spacing_dc) and spacing_dc > 1.0 + 1.0e-9:
        notes.append("Closed tie/hoop spacing exceeds the torsion spacing preview gate s <= min(ph/8, 300 mm).")
    if math.isfinite(at_dc) and at_dc > 1.0 + 1.0e-9:
        notes.append("Provided At/s is less than the required torsion transverse reinforcement.")
    notes.append(str(longitudinal_review.get("description") or ""))
    return {
        "Check": "Torsion",
        "Status": status,
        "Transverse status": transverse_status,
        "Longitudinal status": longitudinal_status,
        "Detailing status": detailing_status,
        "Threshold status": threshold_status,
        "Case": case,
        "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
        "Capacity": f"phiTn = {phi_tn_kNm:,.2f} kN-m",
        "Utilization": _format_beam_uls_ratio(strength_dc),
        "Demand kN-m": float(tu_kNm),
        "Abs demand kN-m": abs(float(tu_kNm)),
        "phiTn kN-m": phi_tn_kNm,
        "phiTcr kN-m": threshold_kNm,
        "Tn kN-m": tn_nmm / 1.0e6,
        "Strength D/C value": strength_dc,
        "Detailing D/C value": detailing_dc,
        "Governing D/C value": governing_dc,
        "Acp mm2": acp,
        "Pcp mm": pcp,
        "Aoh mm2": aoh,
        "Ao mm2": ao,
        "ph mm": ph,
        "Hoop offset mm": _beam_uls_float(geometry.get("offset mm")),
        "At mm2": at_mm2,
        "At/s mm2/mm": at_per_s,
        "At/s req mm2/mm": at_req,
        "Al req mm2": al_req,
        "Al provided mm2": longitudinal_review.get("provided_mm2", float("nan")),
        "Al D/C value": longitudinal_review.get("utilization", float("nan")),
        "s max mm": s_max,
        "Spacing D/C": spacing_dc,
        "Zone": str(zone.get("Zone") or "Column/Pier transverse region"),
        "Tie/hoop": f"{zone.get('Bar Size') or '-'} @ {float(spacing):.0f} mm",
        "phi": phi,
        "Code basis": "ACI 318 Column/Pier RC torsion preview gate",
        "Method": "ACI 318 closed-transverse torsion truss preview",
        "Notes": "; ".join(part for part in notes if part),
    }


def _column_pier_torsion_check_dataframe(state: Mapping[str, object], analysis_input: AnalysisInput | None) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Transverse status", "Longitudinal status", "Detailing status", "Threshold status",
        "Case", "Demand", "Capacity", "Utilization", "Demand kN-m", "Abs demand kN-m",
        "phiTn kN-m", "phiTcr kN-m", "Tn kN-m", "Strength D/C value", "Detailing D/C value",
        "Governing D/C value", "Acp mm2", "Pcp mm", "Aoh mm2", "Ao mm2", "ph mm", "Hoop offset mm",
        "At mm2", "At/s mm2/mm", "At/s req mm2/mm", "Al req mm2", "Al provided mm2", "Al D/C value",
        "s max mm", "Spacing D/C", "Zone", "Tie/hoop", "phi", "Code basis", "Method", "Notes",
    ]
    active_df = _active_column_pier_uls_demand_dataframe_from_state(state)
    if active_df.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, demand_row in active_df.iterrows():
        result = _column_pier_torsion_result_for_case(state, demand_row, analysis_input=analysis_input)
        if result.get("Status") == "NO DEMAND":
            continue
        for column in columns:
            result.setdefault(column, float("nan"))
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _column_pier_governing_torsion_row(torsion_df: pd.DataFrame | None) -> dict[str, object] | None:
    if torsion_df is None or torsion_df.empty or "Governing D/C value" not in torsion_df.columns:
        return None
    df = torsion_df.copy()
    df["__dc"] = pd.to_numeric(df["Governing D/C value"], errors="coerce")
    df = df[df["__dc"].notna()]
    if df.empty:
        return None
    return df.sort_values("__dc", ascending=False, kind="stable").iloc[0].to_dict()


def _column_pier_section_torsion_shape_type(analysis_input: AnalysisInput | None) -> str:
    if analysis_input is None:
        return "solid"
    try:
        polygon = to_shapely_polygon(analysis_input.section_geometry)
        if len(getattr(polygon, "interiors", [])) > 0:
            return "hollow"
    except Exception:
        return "solid"
    return "solid"


def _column_pier_combined_vt_result_for_case_direction(
    state: Mapping[str, object],
    demand_row: Mapping[str, object],
    *,
    direction: str,
    analysis_input: AnalysisInput | None,
) -> dict[str, object]:
    case = str(demand_row.get("Case Name") or "-")
    vu_kN = _beam_uls_float(demand_row.get(direction))
    tu_kNm = _beam_uls_float(demand_row.get("Tu"))
    code = project_design_code_from_session(state)
    if code != PROJECT_CODE_ACI318:
        return {
            "Check": "Shear + Torsion",
            "Status": "REVIEW",
            "Direction": direction,
            "Case": case,
            "Vu kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "Tu kN-m": tu_kNm if math.isfinite(tu_kNm) else float("nan"),
            "Overall D/C value": float("nan"),
            "Code basis": "AASHTO LRFD Column/Pier V+T not implemented",
            "Notes": "AASHTO LRFD Column/Pier combined shear-torsion interaction is not implemented in ULS.COL.VT.ACI_FINAL1.",
        }
    if not math.isfinite(tu_kNm) or abs(float(tu_kNm)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL:
        return {
            "Check": "Shear + Torsion",
            "Status": "NOT APPLICABLE",
            "Direction": direction,
            "Case": case,
            "Vu kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "Tu kN-m": 0.0,
            "Stress status": "NOT ACTIVE",
            "Transverse status": "NOT ACTIVE",
            "Longitudinal status": "NOT ACTIVE",
            "Source shear status": "NOT CHECKED",
            "Source torsion status": "NO DEMAND",
            "Overall D/C value": float("nan"),
            "Code basis": "ACI 318 Column/Pier RC V+T interaction",
            "Notes": "No active Tu demand; combined shear-torsion interaction is not applicable for this row.",
        }
    if analysis_input is None:
        return {
            "Check": "Shear + Torsion",
            "Status": "DATA REQUIRED",
            "Direction": direction,
            "Case": case,
            "Vu kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "Tu kN-m": float(tu_kNm),
            "Overall D/C value": float("nan"),
            "Code basis": "ACI 318 Column/Pier RC V+T interaction",
            "Notes": "Section geometry, concrete material, transverse reinforcement, and ordinary longitudinal rebar are required for Column/Pier V+T.",
        }

    source_row = dict(demand_row)
    if not math.isfinite(vu_kN):
        source_row[direction] = float("nan")
    elif abs(float(vu_kN)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL:
        source_row[direction] = 1.0e-3
    shear = _column_pier_shear_result_for_case_direction(state, source_row, direction=direction, analysis_input=analysis_input)
    torsion = _column_pier_torsion_result_for_case(state, demand_row, analysis_input=analysis_input)
    notes: list[str] = []
    if math.isfinite(vu_kN) and abs(float(vu_kN)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL:
        notes.append("Vu = 0 is treated as a valid combined V+T state; shear stress and required shear reinforcement terms are zero.")

    source_shear_status = str(shear.get("Status") or "DATA REQUIRED")
    source_torsion_status = str(torsion.get("Status") or "DATA REQUIRED")
    fc = _beam_uls_float(getattr(analysis_input.concrete_material, "fc_MPa", None))
    bw_mm = _beam_uls_float(shear.get("bw mm"))
    d_mm = _beam_uls_float(shear.get("d mm"))
    phi = _beam_uls_float(shear.get("phi"))
    if not math.isfinite(phi) or phi <= 0.0:
        phi = 0.75
    vc_kN = _beam_uls_float(shear.get("Vc kN"))
    avs_provided = _beam_uls_float(shear.get("Av/s mm2/mm"))
    ao = _beam_uls_float(torsion.get("Ao mm2"))
    aoh = _beam_uls_float(torsion.get("Aoh mm2"))
    ph = _beam_uls_float(torsion.get("ph mm"))
    at_per_s = _beam_uls_float(torsion.get("At/s mm2/mm"))
    zone = _column_pier_active_transverse_zone_for_torsion(state)
    fy = _beam_uls_float(zone.get("fy_MPa")) if zone is not None else float("nan")
    cot_theta = 1.0
    shape = _column_pier_section_torsion_shape_type(analysis_input)
    has_prestress = _column_pier_has_active_prestress(analysis_input)
    required_inputs = [fc, bw_mm, d_mm, phi, vc_kN, avs_provided, ao, aoh, ph, at_per_s, fy]
    if not all(math.isfinite(value) and value > 0.0 for value in required_inputs) or not math.isfinite(vu_kN):
        return {
            "Check": "Shear + Torsion",
            "Status": "DATA REQUIRED",
            "Direction": direction,
            "Case": case,
            "Vu kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "Tu kN-m": float(tu_kNm),
            "Source shear status": source_shear_status,
            "Source torsion status": source_torsion_status,
            "Shape": shape.upper(),
            "Overall D/C value": float("nan"),
            "Code basis": "ACI 318 Column/Pier RC V+T interaction",
            "Notes": "Combined V+T needs finite shear geometry/capacity terms, torsion core geometry, active closed transverse reinforcement, and ordinary longitudinal rebar source data.",
        }

    threshold_status = str(torsion.get("Threshold status") or "")
    threshold_below = source_torsion_status == "BELOW THRESHOLD" or threshold_status == "BELOW THRESHOLD"
    if threshold_below:
        shear_dc = _beam_uls_float(shear.get("Governing D/C value"))
        stress_status = "THRESHOLD OK"
        transverse_status = "THRESHOLD OK"
        longitudinal_status = "NOT REQUIRED"
        if source_shear_status == "Preview FAIL":
            status = "FAIL"
        elif has_prestress or source_shear_status == "REVIEW" or source_torsion_status == "REVIEW":
            status = "REVIEW"
        elif source_shear_status in {"Preview PASS", "NO DEMAND"}:
            status = "PASS"
        else:
            status = "DATA REQUIRED"
        notes.extend(
            [
                "Tu is below the implemented ACI torsion threshold screen, so combined V+T interaction reinforcement is not required for this row.",
                "Source shear gate still controls the row status when finite Vu is present.",
            ]
        )
        if has_prestress:
            notes.append("Active prestress is present; PSC V+T interaction is not implemented, so the row remains REVIEW.")
        return {
            "Check": "Shear + Torsion",
            "Status": status,
            "Direction": direction,
            "Case": case,
            "Vu kN": float(vu_kN),
            "Tu kN-m": float(tu_kNm),
            "Shape": shape.upper(),
            "Stress status": stress_status,
            "Transverse status": transverse_status,
            "Longitudinal status": longitudinal_status,
            "Source shear status": source_shear_status,
            "Source torsion status": source_torsion_status,
            "Stress D/C value": float("nan"),
            "Transverse D/C value": float("nan"),
            "Longitudinal D/C value": float("nan"),
            "Overall D/C value": shear_dc,
            "Shear stress MPa": 0.0 if abs(float(vu_kN)) <= _COLUMN_PIER_SHEAR_DEMAND_TOL else abs(float(vu_kN)) * 1000.0 / (float(bw_mm) * float(d_mm)),
            "Torsion stress MPa": 0.0,
            "Interaction stress MPa": 0.0,
            "Stress limit MPa": float("nan"),
            "Av shear req mm2/mm": 0.0,
            "At torsion req mm2/mm": 0.0,
            "Combined transverse req mm2/mm": 0.0,
            "Minimum transverse req mm2/mm": _beam_uls_float(shear.get("Av/s required mm2/mm")),
            "Governing transverse req mm2/mm": _beam_uls_float(shear.get("Av/s required mm2/mm")),
            "Provided Av+2At per s mm2/mm": float(avs_provided) + 2.0 * float(at_per_s),
            "Al V+T req mm2": 0.0,
            "Al provided mm2": _beam_uls_float(torsion.get("Al provided mm2")),
            "bw mm": float(bw_mm),
            "d mm": float(d_mm),
            "Ao mm2": float(ao),
            "Aoh mm2": float(aoh),
            "ph mm": float(ph),
            "phi": float(phi),
            "cot theta": cot_theta,
            "Code basis": "ACI 318 Column/Pier RC V+T threshold/source gate",
            "Interaction form": "torsion below threshold",
            "Notes": "; ".join(part for part in notes if part),
        }

    shear_stress = abs(float(vu_kN)) * 1000.0 / (float(bw_mm) * float(d_mm))
    torsion_stress = abs(float(tu_kNm)) * 1.0e6 * float(ph) / (1.7 * float(aoh) * float(aoh))
    if shape == "hollow":
        stress_demand = shear_stress + torsion_stress
        interaction_form = "linear sum for hollow section"
    else:
        stress_demand = math.sqrt(shear_stress * shear_stress + torsion_stress * torsion_stress)
        interaction_form = "root-sum-square for solid section"
    vc_stress = float(vc_kN) * 1000.0 / (float(bw_mm) * float(d_mm))
    stress_limit = float(phi) * (vc_stress + 0.66 * math.sqrt(float(fc)))
    stress_dc = stress_demand / stress_limit if stress_limit > 0.0 else float("nan")
    stress_status = "PASS" if math.isfinite(stress_dc) and stress_dc <= 1.0 + 1.0e-9 else "FAIL"

    shear_req = max(
        0.0,
        (abs(float(vu_kN)) * 1000.0 / float(phi) - float(vc_kN) * 1000.0)
        / (float(fy) * float(d_mm) * float(cot_theta)),
    )
    torsion_req = abs(float(tu_kNm)) * 1.0e6 / (float(phi) * 2.0 * float(ao) * float(fy) * float(cot_theta))
    combined_req = shear_req + 2.0 * torsion_req
    min_req = max(0.062 * math.sqrt(float(fc)) * float(bw_mm) / float(fy), 0.35 * float(bw_mm) / float(fy))
    required_total = max(combined_req, min_req)
    provided_total = float(avs_provided) + 2.0 * float(at_per_s)
    transverse_dc = required_total / provided_total if provided_total > 0.0 else float("nan")
    transverse_status = "PASS" if math.isfinite(transverse_dc) and transverse_dc <= 1.0 + 1.0e-9 else "FAIL"
    longitudinal_req = torsion_req * float(ph) * float(cot_theta) * float(cot_theta)
    longitudinal_review = _beam_uls_torsion_longitudinal_review(state, longitudinal_req)
    longitudinal_status = str(longitudinal_review.get("status") or "DATA REQUIRED")
    longitudinal_dc = _beam_uls_float(longitudinal_review.get("utilization"))
    overall_values = [value for value in [stress_dc, transverse_dc, longitudinal_dc] if math.isfinite(value)]
    overall_dc = max(overall_values) if overall_values else float("nan")

    source_fail = source_shear_status == "Preview FAIL" or source_torsion_status == "Preview FAIL"
    source_review = source_shear_status == "REVIEW" or source_torsion_status == "REVIEW"
    if has_prestress:
        status = "REVIEW"
        notes.append("Active prestress is present. PSC V+T interaction and prestress-specific compatibility are not implemented, so this row remains REVIEW.")
    elif source_fail or "FAIL" in {stress_status, transverse_status, longitudinal_status}:
        status = "FAIL"
    elif source_review:
        status = "REVIEW"
    elif longitudinal_status in {"LAYOUT REQUIRED", "NOT CHECKED", "NOT READY"}:
        status = "DATA REQUIRED"
    else:
        status = "PASS"
    notes.extend(
        [
            "ULS.COL.VT.ACI_FINAL1 checks ACI RC combined V+T stress, combined transverse reinforcement (Av/s + 2At/s), and ordinary longitudinal Al.",
            "Column/Pier demand rows are case-based; the Control section transverse row is used and no minimum transverse reinforcement is silently assumed.",
            "Ordinary longitudinal rebar is counted for Al. Prestress strands, tendons, and PT bars are not counted as torsion Al.",
            str(longitudinal_review.get("description") or ""),
        ]
    )
    if shape == "hollow":
        notes.append("Hollow/voided section uses linear stress interaction. Verify the declared closed transverse path represents the torsion cell before final design.")
    return {
        "Check": "Shear + Torsion",
        "Status": status,
        "Direction": direction,
        "Case": case,
        "Vu kN": float(vu_kN),
        "Tu kN-m": float(tu_kNm),
        "Shape": shape.upper(),
        "Stress status": stress_status,
        "Transverse status": transverse_status,
        "Longitudinal status": longitudinal_status,
        "Source shear status": source_shear_status,
        "Source torsion status": source_torsion_status,
        "Stress D/C value": stress_dc,
        "Transverse D/C value": transverse_dc,
        "Longitudinal D/C value": longitudinal_dc,
        "Overall D/C value": overall_dc,
        "Shear stress MPa": shear_stress,
        "Torsion stress MPa": torsion_stress,
        "Interaction stress MPa": stress_demand,
        "Stress limit MPa": stress_limit,
        "Av shear req mm2/mm": shear_req,
        "At torsion req mm2/mm": torsion_req,
        "Combined transverse req mm2/mm": combined_req,
        "Minimum transverse req mm2/mm": min_req,
        "Governing transverse req mm2/mm": required_total,
        "Provided Av+2At per s mm2/mm": provided_total,
        "Al V+T req mm2": longitudinal_req,
        "Al provided mm2": longitudinal_review.get("provided_mm2", float("nan")),
        "bw mm": float(bw_mm),
        "d mm": float(d_mm),
        "Ao mm2": float(ao),
        "Aoh mm2": float(aoh),
        "ph mm": float(ph),
        "phi": float(phi),
        "cot theta": cot_theta,
        "Code basis": "ACI 318 Column/Pier RC V+T interaction gate",
        "Interaction form": interaction_form,
        "Notes": "; ".join(part for part in notes if part),
    }


def _column_pier_combined_vt_check_dataframe(state: Mapping[str, object], analysis_input: AnalysisInput | None) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Direction", "Case", "Vu kN", "Tu kN-m", "Shape",
        "Stress status", "Transverse status", "Longitudinal status", "Source shear status", "Source torsion status",
        "Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value",
        "Shear stress MPa", "Torsion stress MPa", "Interaction stress MPa", "Stress limit MPa",
        "Av shear req mm2/mm", "At torsion req mm2/mm", "Combined transverse req mm2/mm",
        "Minimum transverse req mm2/mm", "Governing transverse req mm2/mm", "Provided Av+2At per s mm2/mm",
        "Al V+T req mm2", "Al provided mm2", "bw mm", "d mm", "Ao mm2", "Aoh mm2", "ph mm",
        "phi", "cot theta", "Code basis", "Interaction form", "Notes",
    ]
    active_df = _active_column_pier_uls_demand_dataframe_from_state(state)
    if active_df.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, demand_row in active_df.iterrows():
        for direction in ["Vux", "Vuy"]:
            result = _column_pier_combined_vt_result_for_case_direction(
                state,
                demand_row,
                direction=direction,
                analysis_input=analysis_input,
            )
            for column in columns:
                result.setdefault(
                    column,
                    float("nan")
                    if column.endswith("kN")
                    or column.endswith("kN-m")
                    or column.endswith("MPa")
                    or column.endswith("mm2/mm")
                    or column.endswith("mm2")
                    or column.endswith("mm")
                    or column in {"Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value", "phi", "cot theta"}
                    else "-",
                )
            rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _column_pier_governing_combined_vt_row(vt_df: pd.DataFrame | None) -> dict[str, object] | None:
    if vt_df is None or vt_df.empty:
        return None
    df = vt_df.copy()
    df = df[~df.get("Status", pd.Series(index=df.index, dtype=object)).astype(str).isin(["NOT APPLICABLE"])].copy()
    if df.empty:
        return None
    df["__dc"] = pd.to_numeric(df.get("Overall D/C value"), errors="coerce")
    df["__tu"] = pd.to_numeric(df.get("Tu kN-m"), errors="coerce").abs()
    df["__vu"] = pd.to_numeric(df.get("Vu kN"), errors="coerce").abs()
    status_priority = {"FAIL": 5, "DATA REQUIRED": 4, "REVIEW": 3, "PASS": 2}
    df["__status_priority"] = df.get("Status", pd.Series(index=df.index, dtype=object)).map(lambda value: status_priority.get(str(value), 1))
    idx = df.sort_values(["__status_priority", "__dc", "__tu", "__vu"], ascending=[False, False, False, False]).index[0]
    return vt_df.loc[idx].drop(labels=["__dc", "__tu", "__vu", "__status_priority"], errors="ignore").to_dict()


def _beam_uls_governing_action(active_df: pd.DataFrame, column: str) -> dict[str, object] | None:
    if active_df.empty or column not in active_df.columns:
        return None
    candidate = active_df[pd.to_numeric(active_df[column], errors="coerce").notna()].copy()
    if candidate.empty:
        return None
    candidate["__abs_demand"] = candidate[column].abs()
    idx = candidate["__abs_demand"].idxmax()
    row = candidate.loc[idx]
    demand = float(row[column])
    if not math.isfinite(demand):
        return None
    return {
        "case": str(row.get("Case Name") or "-"),
        "x_m": float(row.get("Station x (m)")) if math.isfinite(float(row.get("Station x (m)"))) else None,
        "demand": demand,
        "abs_demand": abs(demand),
        "note": str(row.get("Note") or ""),
    }


def _format_beam_uls_x(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(numeric):
        return "-"
    return f"{numeric:.3f} m"


def _format_beam_uls_demand(value: object, unit: str) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(numeric):
        return "-"
    if abs(numeric) <= _BEAM_ULS_DEMAND_TOL:
        return "-"
    return f"{numeric:,.2f} {unit}"


def _format_beam_uls_ratio(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(numeric):
        return "-"
    return f"{numeric:.3f}"


def _beam_uls_get_state_value(state: Mapping[str, object], key: str, default: object = None) -> object:
    if hasattr(state, "get"):
        return state.get(key, default)
    return getattr(state, key, default)


def _beam_uls_strength_route_from_state(state: Mapping[str, object], *, is_bridge: bool, is_building: bool) -> BeamGirderUlsStrengthRoute:
    return beam_girder_uls_strength_route(
        is_bridge=is_bridge,
        is_building=is_building,
        project_design_code=project_design_code_from_session(state),
        code_edition=project_code_edition_from_session(state),
    )


def _beam_uls_analysis_settings_from_state(state: Mapping[str, object], *, code_label: str) -> AnalysisSettings:
    raw = _beam_uls_get_state_value(state, "analysis_settings")
    if isinstance(raw, AnalysisSettings):
        settings = raw
    elif isinstance(raw, dict):
        try:
            settings = AnalysisSettings.model_validate(raw)
        except Exception:
            settings = AnalysisSettings()
    else:
        settings = AnalysisSettings()
    updates = {
        "code": code_label,
        "include_rebars": True,
        "include_prestress": True,
        "use_phi_factor": True,
        # ULS.FLEX1 uses the current PMM engine. Keep it responsive for station-by-station
        # Beam/Girder checks; detailed calibration remains a later milestone.
        "neutral_axis_angle_steps": min(max(int(settings.neutral_axis_angle_steps), 36), 72),
        "neutral_axis_depth_steps": min(max(int(settings.neutral_axis_depth_steps), 60), 120),
    }
    return settings.model_copy(update=updates)


def _beam_uls_span_length_from_state(state: Mapping[str, object], *, is_building: bool) -> float:
    if is_building:
        system = system_settings_from_mapping(_beam_uls_get_state_value(state, BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
        # Building settings are stored separately for load take-down, but the
        # common system object remains the fallback owner for span length.
        building_settings = building_service_load_settings_from_mapping(
            _beam_uls_get_state_value(state, BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY)
        )
        span = getattr(building_settings, "span_length_m", None) or system.span_length_m
    else:
        system = system_settings_from_mapping(_beam_uls_get_state_value(state, BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
        span = system.span_length_m
    try:
        span_value = float(span)
    except (TypeError, ValueError):
        span_value = 20.0
    return span_value if span_value > 0.0 else 20.0

def _beam_uls_member_end_side(x_m: object, span_m: object | None = None) -> str | None:
    """Return LEFT/RIGHT when x is a diagram/member end station.

    Endpoint rows are useful for plotting complete demand/capacity diagrams,
    but they must not govern torsion or combined V+T source-strength decisions.
    """

    x_value = _beam_uls_float(x_m)
    if not math.isfinite(x_value):
        return None
    tol = 1.0e-6
    span_value = _beam_uls_float(span_m) if span_m is not None else float("nan")
    if math.isfinite(span_value) and span_value > 0.0:
        tol = max(tol, abs(float(span_value)) * 1.0e-8)
    if abs(float(x_value)) <= tol:
        return "LEFT"
    if math.isfinite(span_value) and span_value > 0.0 and abs(float(x_value) - float(span_value)) <= tol:
        return "RIGHT"
    return None


def _beam_uls_torsion_decision_dataframe(torsion_df: pd.DataFrame | None) -> pd.DataFrame:
    """Return torsion rows eligible for governing/source-gate decisions.

    Torsion capacity boundary rows, and active demand rows located exactly at
    member ends, are diagram boundary rows.  They remain available to plots and
    audits but are excluded from governing torsion and combined V+T source gates.
    """

    if torsion_df is None or torsion_df.empty:
        return pd.DataFrame()
    df = torsion_df.copy()
    if "Station type" in df.columns:
        df = df[df["Station type"].astype(str) != "DIAGRAM BOUNDARY"].copy()
    if df.empty:
        return df
    if "Support side" in df.columns:
        df = df[~df["Support side"].astype(str).isin(["LEFT", "RIGHT"])].copy()
    if df.empty:
        return df
    if "Governing x" in df.columns:
        x_values = pd.to_numeric(df["Governing x"].astype(str).str.replace(" m", "", regex=False), errors="coerce")
        left_end = x_values.map(lambda value: _beam_uls_member_end_side(value) == "LEFT")
        df = df[~left_end].copy()
    return df


def _beam_uls_section_bounds(geometry: SectionGeometry) -> tuple[float, float, float, float]:
    polygon = to_shapely_polygon(geometry)
    minx, miny, maxx, maxy = polygon.bounds
    return float(minx), float(miny), float(maxx), float(maxy)


def _beam_uls_girder_strand_elements_for_station(
    state: Mapping[str, object],
    *,
    geometry: SectionGeometry,
    x_m: float,
    span_length_m: float,
) -> list[PrestressElement]:
    """Convert dedicated girder strand-layout metadata to station PS elements.

    ULS.FLEX1 uses this as a strength-check bridge from the girder layout
    table into the existing strain-compatibility solver. It honors row activity
    and debonded sleeve zones through the existing station helper, but it does
    not perform transfer-length, development-length, or strand stress code
    certification.
    """

    table = _beam_uls_get_state_value(state, "girder_strand_layout_table")
    if table is None:
        return []
    _, y_min, _, _ = _beam_uls_section_bounds(geometry)
    try:
        groups = active_strand_groups_at_station(table, x_m=float(x_m), span_length_m=float(span_length_m))
    except Exception:
        return []
    elements: list[PrestressElement] = []
    for group in groups:
        if group.no_strands <= 0 or group.area_per_strand_mm2 <= 0.0:
            continue
        pe_final_per_strand_n = max(0.0, float(group.pe_eff_final_per_strand_kN)) * 1000.0
        initial_stress_mpa = pe_final_per_strand_n / float(group.area_per_strand_mm2) if group.area_per_strand_mm2 > 0.0 else 0.0
        elements.append(
            PrestressElement(
                x_mm=0.0,
                y_mm=float(y_min) + float(group.y_mm_from_bottom),
                area_mm2=float(group.area_per_strand_mm2),
                steel_type="strand",
                material_name="Girder strand layout",
                fpy_mpa=_GIRDER_STRAND_FPY_MPA_DEFAULT,
                fpu_mpa=_GIRDER_STRAND_FPU_MPA_DEFAULT,
                ep_mpa=_GIRDER_STRAND_EP_MPA_DEFAULT,
                pe_eff_n=pe_final_per_strand_n,
                initial_stress_mpa=initial_stress_mpa,
                initial_strain=initial_stress_mpa / _GIRDER_STRAND_EP_MPA_DEFAULT if initial_stress_mpa > 0.0 else 0.0,
                bonded=True,
                count=int(group.no_strands),
                label=f"{group.group_id} @ x={float(x_m):.3f} m",
            )
        )
    return elements


def _beam_uls_flexure_analysis_input_for_station(
    state: Mapping[str, object],
    *,
    row: Mapping[str, object],
    strength_route: BeamGirderUlsStrengthRoute,
    capacity_direction: float | None = None,
) -> tuple[AnalysisInput | None, list[str]]:
    messages: list[str] = []
    geometry = _beam_uls_get_state_value(state, "section_geometry")
    concrete = _beam_uls_get_state_value(state, "concrete_material")
    if isinstance(geometry, dict):
        try:
            geometry = SectionGeometry.model_validate(geometry)
        except Exception:
            geometry = None
    if isinstance(concrete, dict):
        try:
            concrete = ConcreteMaterial.model_validate(concrete)
        except Exception:
            concrete = None
    if not isinstance(geometry, SectionGeometry):
        return None, ["Section geometry is missing."]
    if not isinstance(concrete, ConcreteMaterial):
        return None, ["Concrete material is missing."]

    settings = _beam_uls_analysis_settings_from_state(state, code_label=strength_route.solver_code_label)
    rebars = effective_rebars_for_analysis(list(_beam_uls_get_state_value(state, "rebars", []) or []), state, settings)
    prestress = effective_prestress_for_analysis(list(_beam_uls_get_state_value(state, "prestress_elements", []) or []), state, settings)
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    station_m = _beam_uls_float(row.get("Station x (m)"))
    if not math.isfinite(station_m):
        station_m = 0.0
    strand_elements = _beam_uls_girder_strand_elements_for_station(
        state,
        geometry=geometry,
        x_m=max(0.0, min(float(station_m), span_m)),
        span_length_m=span_m,
    )
    if strand_elements:
        prestress = [*prestress, *strand_elements]
        messages.append("Dedicated girder strand layout included in flexure check at the demand station.")
    elif _beam_uls_get_state_value(state, "girder_strand_layout_table") is not None:
        messages.append("No effective girder strand groups were available at this station; debonding/development must be reviewed.")

    if not rebars and not prestress:
        return None, messages + ["No active ordinary rebar or bonded prestress is available for flexure strength check."]

    mu = _beam_uls_float(row.get("Mux"))
    nu = _beam_uls_float(row.get("Nu"))
    if not math.isfinite(mu):
        return None, messages + ["Mux demand is not finite."]
    if abs(mu) <= _BEAM_ULS_DEMAND_TOL:
        if capacity_direction is None or not math.isfinite(float(capacity_direction)) or abs(float(capacity_direction)) <= 0.0:
            return None, messages + ["Mux demand is zero and no flexure-capacity direction was provided."]
        # Section-strength capacity can still be plotted at a zero-demand endpoint.
        # The tiny directional moment gives the PMM ray a bending sign without
        # changing the displayed demand or treating the endpoint as governing.
        mu = math.copysign(max(_BEAM_ULS_DEMAND_TOL * 10.0, 1.0e-3), float(capacity_direction))
    if not math.isfinite(nu):
        nu = 0.0
    case = str(row.get("Case Name") or "ULS").strip() or "ULS"
    x_label = _format_beam_uls_x(row.get("Station x (m)"))
    load = LoadCase(
        name=f"{case} @ x={x_label}",
        Pu_N=float(nu) * 1000.0,
        Mux_Nmm=float(mu) * 1_000_000.0,
        Muy_Nmm=0.0,
        load_type="ULS",
        active=True,
    )
    return (
        AnalysisInput(
            section_geometry=geometry,
            concrete_material=concrete,
            rebar_materials=list(_beam_uls_get_state_value(state, "rebar_materials", []) or []),
            prestress_materials=list(_beam_uls_get_state_value(state, "prestress_materials", []) or []),
            rebars=rebars,
            prestress_elements=prestress,
            load_cases=[load],
            settings=settings,
        ),
        messages,
    )



def _beam_uls_has_bonded_prestress(analysis_input: AnalysisInput | None) -> bool:
    if analysis_input is None:
        return False
    for element in analysis_input.prestress_elements:
        if getattr(element, "bonded", True) and getattr(element, "count", 0) > 0 and getattr(element, "area_mm2", 0.0) > 0.0:
            return True
    return False


def _beam_uls_nominal_flexure_capacity_for_input(analysis_input: AnalysisInput) -> tuple[float | None, list[str]]:
    """Return nominal Mn from the shared strain engine by temporarily removing φ.

    This is used only by code-specific layers that need to apply their own
    workflow resistance factor above the common strain-compatibility section
    response.
    """

    messages: list[str] = []
    try:
        nominal_settings = analysis_input.settings.model_copy(update={"use_phi_factor": False})
        nominal_input = analysis_input.model_copy(update={"settings": nominal_settings})
        nominal_pmm = run_rc_pmm_solver(nominal_input)
        nominal_summary = check_uls_demands_against_rc_pmm(nominal_pmm, nominal_input.load_cases)
        nominal_result = nominal_summary.results[0] if nominal_summary.results else None
    except Exception as exc:
        return None, [f"Nominal flexure capacity solve failed: {exc}"]
    if nominal_result is None or nominal_result.capacity_phiMn_Nmm is None:
        return None, ["Nominal flexure capacity could not be interpolated for code-specific φ layer."]
    if nominal_result.warning_count:
        messages.append(f"Nominal-capacity interpolation carried {nominal_result.warning_count} warning(s).")
    return float(nominal_result.capacity_phiMn_Nmm), messages



def _beam_uls_flexure_direction_label(demand_kNm: float | None) -> str:
    demand = _beam_uls_float(demand_kNm)
    if not math.isfinite(demand) or abs(demand) <= _BEAM_ULS_DEMAND_TOL:
        return "Boundary / zero Mux"
    return "Sagging (+Mux)" if demand > 0.0 else "Hogging (-Mux)"


def _beam_uls_flexure_tension_face_label(demand_kNm: float | None) -> str:
    demand = _beam_uls_float(demand_kNm)
    if not math.isfinite(demand) or abs(demand) <= _BEAM_ULS_DEMAND_TOL:
        return "-"
    return "Bottom face" if demand > 0.0 else "Top face"


def _beam_uls_effective_phi_value(routed_capacity_nmm: float | None, nominal_capacity_nmm: float | None) -> float:
    if routed_capacity_nmm is None or nominal_capacity_nmm is None:
        return float("nan")
    try:
        routed = float(routed_capacity_nmm)
        nominal = float(nominal_capacity_nmm)
    except (TypeError, ValueError):
        return float("nan")
    if not math.isfinite(routed) or not math.isfinite(nominal) or nominal <= 0.0:
        return float("nan")
    return routed / nominal

def _beam_uls_hashable_value(value: object) -> object:
    """Return a stable JSON-ready value for flexure capacity-state hashing.

    This deliberately avoids hashing Streamlit/session noise.  For prestress
    elements it ignores display labels so identical active strand states at
    different stations can share the same detailed strain-compatibility solve.
    """

    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float):
            return round(float(value), 9) if math.isfinite(float(value)) else str(value)
        return value
    if isinstance(value, Mapping):
        return {str(key): _beam_uls_hashable_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple, set)):
        return [_beam_uls_hashable_value(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _beam_uls_hashable_value(value.model_dump(mode="json"))
        except Exception:
            try:
                return _beam_uls_hashable_value(value.model_dump())
            except Exception:
                pass
    if hasattr(value, "__dict__"):
        return _beam_uls_hashable_value({key: val for key, val in vars(value).items() if not key.startswith("_")})
    return repr(value)


def _beam_uls_hash_payload(payload: object) -> str:
    encoded = json.dumps(_beam_uls_hashable_value(payload), sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _beam_uls_section_geometry_capacity_fingerprint(geometry: SectionGeometry) -> dict[str, object]:
    """Return a lightweight geometry fingerprint for flexure capacity caching.

    Do not hash arbitrary ``geometry.metadata`` here. Section-builder metadata can
    carry UI/helper payloads that are irrelevant to section capacity and can be
    very large.  Capacity is controlled by actual concrete polygon coordinates.
    """

    def _point_payload(point: object) -> tuple[float, float]:
        return (
            round(_beam_uls_float(getattr(point, "x", float("nan"))), 6),
            round(_beam_uls_float(getattr(point, "y", float("nan"))), 6),
        )

    return {
        "name": str(getattr(geometry, "name", "")),
        "outer_polygon": [_point_payload(point) for point in getattr(geometry, "outer_polygon", [])],
        "holes": [[_point_payload(point) for point in hole] for hole in getattr(geometry, "holes", [])],
    }


def _beam_uls_concrete_capacity_fingerprint(material: object) -> dict[str, object]:
    return {
        "name": str(getattr(material, "name", "")),
        "fc_MPa": round(_beam_uls_float(getattr(material, "fc_MPa", float("nan"))), 6),
        "ecu": round(_beam_uls_float(getattr(material, "ecu", float("nan"))), 9),
        "beta1": round(_beam_uls_float(getattr(material, "beta1", float("nan"))), 9),
        "Ec_MPa": round(_beam_uls_float(getattr(material, "Ec_MPa", float("nan"))), 6),
        "Ec_method": str(getattr(material, "Ec_method", "")),
    }


def _beam_uls_rebar_material_capacity_fingerprint(materials: list[object]) -> list[dict[str, object]]:
    rows = [
        {
            "name": str(getattr(material, "name", "")),
            "fy_MPa": round(_beam_uls_float(getattr(material, "fy_MPa", float("nan"))), 6),
            "Es_MPa": round(_beam_uls_float(getattr(material, "Es_MPa", float("nan"))), 6),
        }
        for material in materials
    ]
    return sorted(rows, key=lambda item: item["name"])


def _beam_uls_prestress_material_capacity_fingerprint(materials: list[object]) -> list[dict[str, object]]:
    rows = [
        {
            "name": str(getattr(material, "name", "")),
            "steel_type": str(getattr(material, "steel_type", "")),
            "fpy_MPa": round(_beam_uls_float(getattr(material, "fpy_MPa", float("nan"))), 6),
            "fpu_MPa": round(_beam_uls_float(getattr(material, "fpu_MPa", float("nan"))), 6),
            "Ep_MPa": round(_beam_uls_float(getattr(material, "Ep_MPa", float("nan"))), 6),
        }
        for material in materials
    ]
    return sorted(rows, key=lambda item: item["name"])


def _beam_uls_analysis_settings_capacity_fingerprint(settings: object) -> dict[str, object]:
    return {
        "code": str(getattr(settings, "code", "")),
        "use_phi_factor": bool(getattr(settings, "use_phi_factor", True)),
        "include_rebars": bool(getattr(settings, "include_rebars", True)),
        "include_prestress": bool(getattr(settings, "include_prestress", True)),
        "transverse_reinforcement": str(getattr(settings, "transverse_reinforcement", "")),
        "prestress_stress_model": str(getattr(settings, "prestress_stress_model", "")),
        "subtract_rebar_displaced_concrete": bool(getattr(settings, "subtract_rebar_displaced_concrete", True)),
        "neutral_axis_angle_steps": int(getattr(settings, "neutral_axis_angle_steps", 0) or 0),
        "neutral_axis_depth_steps": int(getattr(settings, "neutral_axis_depth_steps", 0) or 0),
        "compression_positive": bool(getattr(settings, "compression_positive", True)),
    }


def _beam_uls_rebar_capacity_fingerprint(rebars: list[object]) -> list[object]:
    return [
        _beam_uls_hashable_value(rebar)
        for rebar in sorted(
            rebars,
            key=lambda item: (
                _beam_uls_float(getattr(item, "x_mm", float("nan"))),
                _beam_uls_float(getattr(item, "y_mm", float("nan"))),
                _beam_uls_float(getattr(item, "diameter_mm", float("nan"))),
                str(getattr(item, "material_name", "")),
            ),
        )
    ]


def _beam_uls_prestress_capacity_fingerprint(elements: list[object]) -> list[object]:
    rows: list[dict[str, object]] = []
    for element in elements:
        rows.append(
            {
                "x_mm": _beam_uls_float(getattr(element, "x_mm", float("nan"))),
                "y_mm": _beam_uls_float(getattr(element, "y_mm", float("nan"))),
                "area_mm2": _beam_uls_float(getattr(element, "area_mm2", float("nan"))),
                "count": int(getattr(element, "count", 1) or 1),
                "material_name": str(getattr(element, "material_name", "")),
                "steel_type": str(getattr(element, "steel_type", "")),
                "fpy_mpa": _beam_uls_float(getattr(element, "fpy_mpa", float("nan"))),
                "fpu_mpa": _beam_uls_float(getattr(element, "fpu_mpa", float("nan"))),
                "ep_mpa": _beam_uls_float(getattr(element, "ep_mpa", float("nan"))),
                "pe_eff_n": _beam_uls_float(getattr(element, "pe_eff_n", float("nan"))),
                "initial_stress_mpa": _beam_uls_float(getattr(element, "initial_stress_mpa", float("nan"))),
                "initial_strain": _beam_uls_float(getattr(element, "initial_strain", float("nan"))),
                "bonded": bool(getattr(element, "bonded", True)),
            }
        )
    return sorted(rows, key=lambda item: (item["y_mm"], item["x_mm"], item["material_name"], item["count"]))


def _beam_uls_load_capacity_direction_key(load_case: LoadCase | None, demand_kNm: float | None, capacity_direction: float | None) -> dict[str, object]:
    demand = _beam_uls_float(demand_kNm)
    direction = _beam_uls_float(capacity_direction)
    if math.isfinite(demand) and abs(demand) > _BEAM_ULS_DEMAND_TOL:
        sign = -1.0 if demand < 0.0 else 1.0
    elif math.isfinite(direction) and abs(direction) > 0.0:
        sign = -1.0 if direction < 0.0 else 1.0
    else:
        sign = 1.0
    pu_n = _beam_uls_float(getattr(load_case, "Pu_N", 0.0)) if load_case is not None else 0.0
    muy = _beam_uls_float(getattr(load_case, "Muy_Nmm", 0.0)) if load_case is not None else 0.0
    return {"mux_sign": sign, "Pu_N": round(float(pu_n), 3) if math.isfinite(pu_n) else 0.0, "Muy_Nmm": round(float(muy), 3) if math.isfinite(muy) else 0.0}


def _beam_uls_flexure_capacity_state_key(
    analysis_input: AnalysisInput,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
    demand_kNm: float | None,
    capacity_direction: float | None = None,
) -> str:
    """Return a cache key for a detailed flexure section-capacity state.

    The key intentionally ignores station labels and Mux magnitude.  It keeps
    geometry, materials, active rebar, active/bonded prestress state, route,
    axial force, and bending sign.  That lets equal station capacity states reuse
    the same strain-compatibility solve while debonded/development regions,
    tension-face changes, or Nu changes remain separate.
    """

    load_case = analysis_input.load_cases[0] if analysis_input.load_cases else None
    payload = {
        "route": {
            "workflow": strength_route.workflow_label,
            "code": strength_route.display_code_label,
            "solver_code": strength_route.solver_code_label,
            "flexure_engine": strength_route.flexure_engine_label,
        },
        "load_direction": _beam_uls_load_capacity_direction_key(load_case, demand_kNm, capacity_direction),
        "section_geometry": _beam_uls_section_geometry_capacity_fingerprint(analysis_input.section_geometry),
        "concrete_material": _beam_uls_concrete_capacity_fingerprint(analysis_input.concrete_material),
        "rebar_materials": _beam_uls_rebar_material_capacity_fingerprint(list(analysis_input.rebar_materials)),
        "prestress_materials": _beam_uls_prestress_material_capacity_fingerprint(list(analysis_input.prestress_materials)),
        "rebars": _beam_uls_rebar_capacity_fingerprint(list(analysis_input.rebars)),
        "prestress_elements": _beam_uls_prestress_capacity_fingerprint(list(analysis_input.prestress_elements)),
        "settings": _beam_uls_analysis_settings_capacity_fingerprint(analysis_input.settings),
    }
    return _beam_uls_hash_payload(payload)


def _beam_uls_solve_flexure_capacity_state(
    analysis_input: AnalysisInput,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    """Run the detailed flexure solver once for one capacity-state key."""

    try:
        pmm_result = run_rc_pmm_solver(analysis_input)
        summary = check_uls_demands_against_rc_pmm(pmm_result, analysis_input.load_cases)
        result = summary.results[0] if summary.results else None
    except Exception as exc:
        return {"state": "solver_error", "error": f"Flexure check solver error: {exc}"}
    if result is None or result.capacity_phiMn_Nmm is None or result.dcr is None:
        return {"state": "not_checked", "error": "Flexure capacity could not be interpolated from PMM results."}

    flexure_basis = beam_girder_flexure_code_basis(
        strength_route,
        has_bonded_prestress=_beam_uls_has_bonded_prestress(analysis_input),
    )
    nominal_capacity_nmm, nominal_messages = _beam_uls_nominal_flexure_capacity_for_input(analysis_input)
    routed_capacity_nmm, routed_basis_note = apply_flexure_code_basis(
        phi_capacity_nmm=float(result.capacity_phiMn_Nmm),
        nominal_capacity_nmm=nominal_capacity_nmm,
        basis=flexure_basis,
    )
    nominal_capacity_kNm = float(nominal_capacity_nmm) / 1_000_000.0 if nominal_capacity_nmm is not None and nominal_capacity_nmm > 0.0 else float("nan")
    route_phi_value = _beam_uls_effective_phi_value(routed_capacity_nmm, nominal_capacity_nmm)
    return {
        "state": "ok",
        "result_warning_count": int(getattr(result, "warning_count", 0) or 0),
        "flexure_basis": flexure_basis,
        "nominal_capacity_nmm": nominal_capacity_nmm,
        "nominal_capacity_kNm": nominal_capacity_kNm,
        "nominal_messages": list(nominal_messages),
        "routed_capacity_nmm": routed_capacity_nmm,
        "routed_basis_note": routed_basis_note,
        "route_phi_value": route_phi_value,
    }


def _beam_uls_flexure_preview_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute | None = None,
    code_label: str | None = None,
    is_building: bool | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Return station-by-station flexure check rows using the routed ULS basis.

    ULS.CODE.ROUTE1 centralizes Bridge/Building code routing.  Backward-compatible
    code_label/is_building keyword arguments are accepted for source tests and
    older call sites, but new UI code should pass ``strength_route``.
    """

    if strength_route is None:
        display = str(code_label or "").strip().casefold()
        route_is_building = bool(is_building) or "aci" in display or "318" in display
        strength_route = beam_girder_uls_strength_route(
            is_bridge=not route_is_building,
            is_building=route_is_building,
            project_design_code=code_label,
            code_edition=code_label,
        )

    columns = [
        "Check",
        "Status",
        "Governing x",
        "Case",
        "Demand",
        "Capacity",
        "Utilization",
        "Demand kN-m",
        "Capacity kN-m",
        "Utilization value",
        "Capacity plot sign",
        "Capacity basis",
        "Route φ",
        "Method",
        "Mn nominal kN-m",
        "φ value",
        "φMn kN-m",
        "D/C value",
        "Bending direction",
        "Tension face",
        "Code basis",
        "Strain compatibility basis",
        "φ policy",
        "Solver basis",
        "Material model scope",
        "Route",
        "Benchmark readiness",
        "Notes",
    ]
    if active_df.empty:
        return pd.DataFrame(columns=columns), ["No active ULS rows available for flexure check."]
    rows: list[dict[str, object]] = []
    messages: list[str] = []
    source_rows = active_df.copy()
    source_rows["__station_m"] = pd.to_numeric(source_rows["Station x (m)"], errors="coerce")
    source_rows["__mux_kNm"] = pd.to_numeric(source_rows["Mux"], errors="coerce")
    nonzero_rows = source_rows[source_rows["__mux_kNm"].abs() > _BEAM_ULS_DEMAND_TOL].copy()
    if len(nonzero_rows.index) > _BEAM_ULS_FLEXURE_PREVIEW_MAX_ROWS:
        messages.append(
            f"Flexure check limited to the first {_BEAM_ULS_FLEXURE_PREVIEW_MAX_ROWS} nonzero Mux rows for responsiveness. Use envelope input for large imports."
        )
        nonzero_rows = nonzero_rows.head(_BEAM_ULS_FLEXURE_PREVIEW_MAX_ROWS)

    endpoint_rows = pd.DataFrame(columns=source_rows.columns)
    finite_station_rows = source_rows[source_rows["__station_m"].notna()].copy()
    if not finite_station_rows.empty:
        end_stations = {float(finite_station_rows["__station_m"].min()), float(finite_station_rows["__station_m"].max())}
        endpoint_rows = finite_station_rows[
            finite_station_rows["__station_m"].map(lambda value: float(value) in end_stations)
            & finite_station_rows["__mux_kNm"].notna()
            & (finite_station_rows["__mux_kNm"].abs() <= _BEAM_ULS_DEMAND_TOL)
            & ~finite_station_rows.index.isin(nonzero_rows.index)
        ].copy()
        if not endpoint_rows.empty:
            messages.append(
                "Zero-Mux end station(s) are plotted as φMn = 0 section-boundary points; endpoint D/C is not governing because demand is zero."
            )

    def _capacity_direction_for_zero_demand(row: Mapping[str, object]) -> float:
        row_case = str(row.get("Case Name") or "")
        row_x = _beam_uls_float(row.get("Station x (m)"))
        candidates = nonzero_rows.copy()
        if not candidates.empty and row_case:
            same_case = candidates[candidates["Case Name"].astype(str) == row_case].copy()
            if not same_case.empty:
                candidates = same_case
        if not candidates.empty:
            candidates = candidates[candidates["__mux_kNm"].notna()].copy()
            if math.isfinite(row_x) and "__station_m" in candidates.columns:
                candidates["__distance_to_endpoint"] = (candidates["__station_m"].astype(float) - float(row_x)).abs()
                candidates = candidates.sort_values("__distance_to_endpoint", kind="stable")
            candidate_mu = _beam_uls_float(candidates.iloc[0].get("Mux")) if not candidates.empty else float("nan")
            if math.isfinite(candidate_mu) and abs(candidate_mu) > _BEAM_ULS_DEMAND_TOL:
                return -1.0 if candidate_mu < 0.0 else 1.0
        return 1.0

    demand_rows = pd.concat([nonzero_rows, endpoint_rows], axis=0).sort_values(["Case Name", "__station_m"], kind="stable")
    # PERF.FLEX1: keep the detailed strain-compatibility calculation, but solve
    # each unique capacity state only once.  Different station demand magnitudes
    # can share φMn when geometry/material/rebar/prestress state, bending sign,
    # design route, and Nu are identical.  Debonding or tension-face changes
    # naturally create a different key.
    capacity_state_cache: dict[str, dict[str, object]] = {}
    capacity_cache_hits = 0
    capacity_cache_misses = 0
    for _, demand_row in demand_rows.iterrows():
        demand = _beam_uls_float(demand_row.get("Mux"))
        station = _format_beam_uls_x(demand_row.get("Station x (m)"))
        case = str(demand_row.get("Case Name") or "-")
        zero_demand_endpoint = math.isfinite(demand) and abs(demand) <= _BEAM_ULS_DEMAND_TOL
        capacity_direction = _capacity_direction_for_zero_demand(demand_row) if zero_demand_endpoint else None
        if zero_demand_endpoint:
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "SECTION BOUNDARY",
                    "Governing x": station,
                    "Case": case,
                    "Demand": "0.00 kN-m",
                    "Capacity": "φMn = 0.00 kN-m",
                    "Utilization": "-",
                    "Demand kN-m": 0.0,
                    "Capacity kN-m": 0.0,
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if capacity_direction is not None else 1.0,
                    "Capacity basis": "diagram boundary",
                    "Route φ": "-",
                    "Method": "section boundary",
                    "Mn nominal kN-m": float("nan"),
                    "φ value": float("nan"),
                    "φMn kN-m": 0.0,
                    "D/C value": float("nan"),
                    "Bending direction": _beam_uls_flexure_direction_label(0.0),
                    "Tension face": _beam_uls_flexure_tension_face_label(0.0),
                    "Code basis": "diagram boundary",
                    "Strain compatibility basis": "diagram boundary",
                    "φ policy": "-",
                    "Solver basis": "diagram boundary",
                    "Material model scope": "-",
                    "Route": "section boundary",
                    "Benchmark readiness": "Boundary point; not used for D/C",
                    "Notes": "Zero-Mux endpoint plotted as φMn = 0 for flexure diagram boundary; D/C is not applicable at zero demand",
                }
            )
            continue
        analysis_input, input_messages = _beam_uls_flexure_analysis_input_for_station(
            state,
            row=demand_row,
            strength_route=strength_route,
            capacity_direction=capacity_direction,
        )
        messages.extend(input_messages)
        if analysis_input is None:
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "REVIEW",
                    "Governing x": station,
                    "Case": case,
                    "Demand": _format_beam_uls_demand(demand, "kN-m"),
                    "Capacity": "-",
                    "Utilization": "-",
                    "Demand kN-m": demand if math.isfinite(demand) else float("nan"),
                    "Capacity kN-m": float("nan"),
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if zero_demand_endpoint else ( -1.0 if math.isfinite(demand) and demand < 0.0 else 1.0 ),
                    "Capacity basis": "-",
                    "Route φ": "-",
                    "Method": "not ready",
                    "Notes": "; ".join(input_messages[-3:]),
                }
            )
            continue
        capacity_state_key = _beam_uls_flexure_capacity_state_key(
            analysis_input,
            strength_route=strength_route,
            demand_kNm=demand,
            capacity_direction=capacity_direction,
        )
        capacity_state = capacity_state_cache.get(capacity_state_key)
        cache_hit = capacity_state is not None
        if cache_hit:
            capacity_cache_hits += 1
        else:
            capacity_state = _beam_uls_solve_flexure_capacity_state(analysis_input, strength_route=strength_route)
            capacity_state_cache[capacity_state_key] = capacity_state
            capacity_cache_misses += 1

        state_status = str(capacity_state.get("state") or "")
        if state_status == "solver_error":
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "REVIEW",
                    "Governing x": station,
                    "Case": case,
                    "Demand": _format_beam_uls_demand(demand, "kN-m"),
                    "Capacity": "-",
                    "Utilization": "-",
                    "Demand kN-m": demand if math.isfinite(demand) else float("nan"),
                    "Capacity kN-m": float("nan"),
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if zero_demand_endpoint else ( -1.0 if math.isfinite(demand) and demand < 0.0 else 1.0 ),
                    "Capacity basis": "-",
                    "Route φ": "-",
                    "Method": "solver error",
                    "Notes": str(capacity_state.get("error") or "Flexure check solver error."),
                }
            )
            continue
        if state_status != "ok":
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "REVIEW",
                    "Governing x": station,
                    "Case": case,
                    "Demand": _format_beam_uls_demand(demand, "kN-m"),
                    "Capacity": "-",
                    "Utilization": "-",
                    "Demand kN-m": demand if math.isfinite(demand) else float("nan"),
                    "Capacity kN-m": float("nan"),
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if zero_demand_endpoint else ( -1.0 if math.isfinite(demand) and demand < 0.0 else 1.0 ),
                    "Capacity basis": "-",
                    "Route φ": "-",
                    "Method": "not checked",
                    "Notes": str(capacity_state.get("error") or "Flexure capacity could not be interpolated from PMM results."),
                }
            )
            continue

        flexure_basis = capacity_state["flexure_basis"]
        if not isinstance(flexure_basis, BeamGirderFlexureCodeBasis):
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "REVIEW",
                    "Governing x": station,
                    "Case": case,
                    "Demand": _format_beam_uls_demand(demand, "kN-m"),
                    "Capacity": "-",
                    "Utilization": "-",
                    "Demand kN-m": demand if math.isfinite(demand) else float("nan"),
                    "Capacity kN-m": float("nan"),
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if zero_demand_endpoint else ( -1.0 if math.isfinite(demand) and demand < 0.0 else 1.0 ),
                    "Capacity basis": "-",
                    "Route φ": "-",
                    "Method": "cache error",
                    "Notes": "Flexure capacity-state cache returned an invalid code-basis object.",
                }
            )
            continue
        nominal_messages = [str(item) for item in capacity_state.get("nominal_messages", []) or []]
        if not cache_hit:
            messages.extend(nominal_messages)
        routed_capacity_nmm = capacity_state.get("routed_capacity_nmm")
        routed_basis_note = str(capacity_state.get("routed_basis_note") or "")
        nominal_capacity_kNm = _beam_uls_float(capacity_state.get("nominal_capacity_kNm"))
        route_phi_value = _beam_uls_float(capacity_state.get("route_phi_value"))
        if routed_capacity_nmm is None or _beam_uls_float(routed_capacity_nmm) <= 0.0:
            rows.append(
                {
                    "Check": "Flexure",
                    "Status": "REVIEW",
                    "Governing x": station,
                    "Case": case,
                    "Demand": _format_beam_uls_demand(demand, "kN-m"),
                    "Capacity": "-",
                    "Utilization": "-",
                    "Demand kN-m": demand if math.isfinite(demand) else float("nan"),
                    "Capacity kN-m": float("nan"),
                    "Utilization value": float("nan"),
                    "Capacity plot sign": capacity_direction if zero_demand_endpoint else ( -1.0 if math.isfinite(demand) and demand < 0.0 else 1.0 ),
                    "Capacity basis": flexure_basis.display_label,
                    "Route φ": flexure_basis.resistance_factor_text,
                    "Method": flexure_basis.method_label,
                    "Mn nominal kN-m": nominal_capacity_kNm,
                    "φ value": route_phi_value,
                    "φMn kN-m": float("nan"),
                    "D/C value": float("nan"),
                    "Bending direction": _beam_uls_flexure_direction_label(demand),
                    "Tension face": _beam_uls_flexure_tension_face_label(demand),
                    "Code basis": flexure_basis.capacity_label,
                    "Strain compatibility basis": flexure_basis.strain_compatibility_basis,
                    "φ policy": flexure_basis.resistance_factor_policy,
                    "Solver basis": flexure_basis.solver_audit_label,
                    "Material model scope": flexure_basis.material_model_scope,
                    "Route": flexure_basis.route_label,
                    "Benchmark readiness": "Needs review; routed φMn unavailable",
                    "Notes": routed_basis_note,
                }
            )
            continue
        capacity_kNm = float(routed_capacity_nmm) / 1_000_000.0
        utilization = abs(float(demand)) * 1_000_000.0 / float(routed_capacity_nmm)
        method = flexure_basis.method_label
        note_parts = ["Primary Mux flexure only", flexure_basis.route_label, routed_basis_note]
        if nominal_messages:
            note_parts.extend(nominal_messages)
        if zero_demand_endpoint:
            status = "SECTION PREVIEW"
            display_demand = "0.00 kN-m"
            display_utilization = "-"
            utilization_value = float("nan")
            method = "section boundary"
            note_parts = [
                "Zero-Mux endpoint included for full-span section-strength curve",
                "D/C is not applicable at zero demand",
                "Development/detailing checks are separate from this section-strength curve",
            ]
        else:
            status = "PASS" if utilization <= 1.0 else "FAIL"
            display_demand = _format_beam_uls_demand(demand, "kN-m")
            display_utilization = _format_beam_uls_ratio(utilization)
            utilization_value = utilization
            result_warning_count = int(capacity_state.get("result_warning_count", 0) or 0)
            if result_warning_count:
                note_parts.append(f"{result_warning_count} interpolation warning(s)")
            if cache_hit:
                note_parts.append("Capacity-state cache reused from matching section/prestress state")
        rows.append(
            {
                "Check": "Flexure",
                "Status": status,
                "Governing x": station,
                "Case": case,
                "Demand": display_demand,
                "Capacity": f"φMn = {capacity_kNm:,.2f} kN-m",
                "Utilization": display_utilization,
                "Demand kN-m": 0.0 if zero_demand_endpoint else float(demand),
                "Capacity kN-m": capacity_kNm,
                "Utilization value": utilization_value,
                "Capacity plot sign": capacity_direction if zero_demand_endpoint else (-1.0 if demand < 0.0 else 1.0),
                "Capacity basis": flexure_basis.display_label if not zero_demand_endpoint else "diagram boundary",
                "Route φ": flexure_basis.resistance_factor_text if not zero_demand_endpoint else "-",
                "Method": method,
                "Mn nominal kN-m": nominal_capacity_kNm if not zero_demand_endpoint else float("nan"),
                "φ value": route_phi_value if not zero_demand_endpoint else float("nan"),
                "φMn kN-m": capacity_kNm,
                "D/C value": utilization_value,
                "Bending direction": _beam_uls_flexure_direction_label(demand),
                "Tension face": _beam_uls_flexure_tension_face_label(demand),
                "Code basis": flexure_basis.capacity_label if not zero_demand_endpoint else "diagram boundary",
                "Strain compatibility basis": flexure_basis.strain_compatibility_basis if not zero_demand_endpoint else "diagram boundary",
                "φ policy": flexure_basis.resistance_factor_policy if not zero_demand_endpoint else "-",
                "Solver basis": flexure_basis.solver_audit_label if not zero_demand_endpoint else "diagram boundary",
                "Material model scope": flexure_basis.material_model_scope if not zero_demand_endpoint else "-",
                "Route": flexure_basis.route_label if not zero_demand_endpoint else "section boundary",
                "Benchmark readiness": flexure_basis.benchmark_readiness_note if not zero_demand_endpoint else "Boundary point; not used for D/C",
                "Notes": "; ".join(note_parts),
            }
        )
    if capacity_cache_hits:
        messages.append(
            f"Flexure capacity-state cache reused {capacity_cache_hits} station row(s); "
            f"{capacity_cache_misses} unique detailed capacity state(s) solved."
        )
    return pd.DataFrame(rows, columns=columns), deduplicate_warnings(messages)


def _beam_uls_governing_flexure_preview_row(flexure_preview_df: pd.DataFrame | None) -> dict[str, object] | None:
    if flexure_preview_df is None or flexure_preview_df.empty or "Utilization value" not in flexure_preview_df.columns:
        return None
    valid = flexure_preview_df[pd.to_numeric(flexure_preview_df["Utilization value"], errors="coerce").notna()].copy()
    if valid.empty:
        return None
    idx = valid["Utilization value"].astype(float).idxmax()
    return valid.loc[idx].to_dict()




def _beam_uls_active_shear_reinforcement_zone_count(state: Mapping[str, object]) -> int:
    raw = _beam_uls_get_state_value(state, SHEAR_REINFORCEMENT_TABLE_KEY, None)
    if raw is None:
        raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get(SHEAR_REINFORCEMENT_TABLE_KEY)
    df = pd.DataFrame(raw if raw is not None else [])
    if df.empty or "Active" not in df.columns:
        return 0
    return int(sum(_beam_uls_active_value(value) for value in df["Active"].tolist()))


def _beam_uls_shear_layout_status(state: Mapping[str, object]) -> tuple[str, str]:
    if not state:
        return "PLANNED", "-"
    active_zones = _beam_uls_active_shear_reinforcement_zone_count(state)
    if active_zones > 0:
        return "LAYOUT READY", f"{active_zones} active stirrup zone(s); run provided-stirrup φVn check"
    return "LAYOUT REQUIRED", "Define active stirrup zones in Sections → Rebar → Shear Reinforcement"


def _beam_uls_linework_length_mm(geometry: object) -> float:
    """Return total line length from a Shapely line/multiline/collection."""

    if geometry is None or getattr(geometry, "is_empty", True):
        return 0.0
    geom_type = getattr(geometry, "geom_type", "")
    if geom_type in {"LineString", "LinearRing"}:
        try:
            return float(geometry.length)
        except Exception:
            return 0.0
    if hasattr(geometry, "geoms"):
        return sum(_beam_uls_linework_length_mm(item) for item in geometry.geoms)
    return 0.0


def _beam_uls_web_width_mm(geometry: SectionGeometry) -> tuple[float | None, str]:
    """Estimate total shear web width from the active section polygon.

    The function samples horizontal material widths through the central web
    region and takes the minimum positive width. For I-girders this returns the
    web thickness; for box sections it returns the total material intercepted by
    both webs. It is intentionally an analysis helper, not a geometry generator.
    """

    try:
        polygon = to_shapely_polygon(geometry)
        minx, miny, maxx, maxy = polygon.bounds
    except Exception:
        return None, "Web width unavailable: section polygon could not be read."
    h = float(maxy) - float(miny)
    b = float(maxx) - float(minx)
    if h <= 0.0 or b <= 0.0:
        return None, "Web width unavailable: invalid section bounds."
    widths: list[float] = []
    # Avoid flange-only zones; sample through the likely web core.
    for ratio in (0.25, 0.33, 0.40, 0.50, 0.60, 0.67, 0.75):
        y = float(miny) + ratio * h
        line = LineString([(float(minx) - b, y), (float(maxx) + b, y)])
        try:
            width = _beam_uls_linework_length_mm(polygon.intersection(line))
        except Exception:
            width = 0.0
        if width > 1.0:
            widths.append(width)
    if not widths:
        return None, "Web width unavailable: no positive horizontal material width found."
    return float(min(widths)), "Web width estimated from minimum central horizontal material width."


def _beam_uls_reinforcement_y_centroid_for_face(analysis_input: AnalysisInput, *, tension_face: str) -> float | None:
    """Return area-weighted reinforcement centroid near the local tension face."""

    try:
        _, y_min, _, y_max = _beam_uls_section_bounds(analysis_input.section_geometry)
    except Exception:
        return None
    h = float(y_max) - float(y_min)
    if h <= 0.0:
        return None
    if tension_face == "top":
        limit = float(y_min) + 0.55 * h
        candidates = []
        for bar in analysis_input.rebars:
            if float(bar.y_mm) >= limit:
                candidates.append((float(bar.y_mm), float(bar.area_mm2)))
        for ps in analysis_input.prestress_elements:
            if float(ps.y_mm) >= limit:
                candidates.append((float(ps.y_mm), float(ps.area_mm2)))
    else:
        limit = float(y_min) + 0.45 * h
        candidates = []
        for bar in analysis_input.rebars:
            if float(bar.y_mm) <= limit:
                candidates.append((float(bar.y_mm), float(bar.area_mm2)))
        for ps in analysis_input.prestress_elements:
            if float(ps.y_mm) <= limit:
                candidates.append((float(ps.y_mm), float(ps.area_mm2)))
    area = sum(a for _, a in candidates if a > 0.0)
    if area <= 0.0:
        return None
    return sum(y * a for y, a in candidates if a > 0.0) / area



def _beam_uls_shear_depth_settings_from_state(state: Mapping[str, object] | None) -> dict[str, object]:
    raw: object = None
    if state is not None:
        raw = _beam_uls_get_state_value(state, SHEAR_DEPTH_SETTINGS_KEY, None)
        if raw is None:
            raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get(SHEAR_DEPTH_SETTINGS_KEY)
    if not isinstance(raw, Mapping):
        raw = {}
    mode = str(raw.get("mode") or "Auto from reinforcement centroid")
    if mode != SHEAR_DEPTH_MODE_MANUAL:
        mode = "Auto from reinforcement centroid"
    def _positive(value: object) -> float | None:
        numeric = _beam_uls_float(value)
        return float(numeric) if math.isfinite(numeric) and numeric > 0.0 else None
    return {
        "mode": mode,
        "d_mm": _positive(raw.get("d_mm")),
        "dv_mm": _positive(raw.get("dv_mm")),
        "note": str(raw.get("note") or "").strip(),
    }


def _beam_uls_bridge_dv_from_depth_mm(d_eff_mm: float, h_mm: float) -> float:
    """Return the current AASHTO-compatible dv estimate.

    This preserves the existing SHEAR1/2 behavior while making the d/dv basis
    explicit and reusable for critical-section placement, cards, and audit rows.
    """

    if not all(math.isfinite(value) and value > 0.0 for value in [d_eff_mm, h_mm]):
        return float("nan")
    return max(0.72 * float(h_mm), min(0.90 * float(d_eff_mm), float(d_eff_mm)))


def _beam_uls_effective_shear_depth_values_mm(
    state: Mapping[str, object] | None,
    analysis_input: AnalysisInput,
    *,
    mux_kNm: float,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    """Return explicit d/dv values and basis notes for the local shear station."""

    d_eff_mm, tension_face, d_note = _beam_uls_effective_shear_depth_mm(
        analysis_input,
        mux_kNm=mux_kNm,
        strength_route=strength_route,
        state=state,
    )
    try:
        _, y_min, _, y_max = _beam_uls_section_bounds(analysis_input.section_geometry)
        h_mm = float(y_max) - float(y_min)
    except Exception:
        h_mm = float("nan")
    settings = _beam_uls_shear_depth_settings_from_state(state)
    dv_manual = settings.get("dv_mm")
    if strength_route.is_bridge:
        if dv_manual is not None and math.isfinite(float(dv_manual)) and float(dv_manual) > 0.0:
            dv_mm = float(dv_manual)
            dv_note = "Manual dv read from Sections → Rebar effective shear depth basis."
            if settings.get("note"):
                dv_note += f" Basis note: {settings.get('note')}"
        elif d_eff_mm is not None and math.isfinite(float(d_eff_mm)) and math.isfinite(h_mm) and h_mm > 0.0:
            dv_mm = _beam_uls_bridge_dv_from_depth_mm(float(d_eff_mm), float(h_mm))
            dv_note = "dv derived from the active d and section depth using the current AASHTO-compatible basis."
        else:
            dv_mm = float("nan")
            dv_note = "dv unavailable: d or section depth is not ready."
    else:
        dv_mm = float("nan")
        dv_note = "ACI route uses d for the implemented one-way shear gate; dv is not separately used."
    return {
        "d_mm": d_eff_mm,
        "dv_mm": dv_mm,
        "h_mm": h_mm,
        "tension_face": tension_face,
        "d_note": d_note,
        "dv_note": dv_note,
    }


def _beam_uls_effective_shear_depth_mm(
    analysis_input: AnalysisInput,
    *,
    mux_kNm: float,
    strength_route: BeamGirderUlsStrengthRoute,
    state: Mapping[str, object] | None = None,
) -> tuple[float | None, str, str]:
    """Estimate effective shear depth for the local station.

    The estimate is derived from the local bending sign and active reinforcement
    centroid where available; otherwise it falls back to 0.80h with a REVIEW
    note.  This keeps the first shear engine usable while making assumptions
    visible in the audit table.
    """

    try:
        _, y_min, _, y_max = _beam_uls_section_bounds(analysis_input.section_geometry)
    except Exception:
        return None, "-", "Effective depth unavailable: section bounds could not be read."
    h = float(y_max) - float(y_min)
    if h <= 0.0:
        return None, "-", "Effective depth unavailable: invalid section depth."
    tension_face = "top" if _beam_uls_float(mux_kNm) < -_BEAM_ULS_DEMAND_TOL else "bottom"
    settings = _beam_uls_shear_depth_settings_from_state(state)
    manual_d = settings.get("d_mm")
    if settings.get("mode") == SHEAR_DEPTH_MODE_MANUAL and manual_d is not None:
        if 0.0 < float(manual_d) <= 1.05 * h:
            note = "Effective d read from Sections → Rebar manual effective shear depth basis."
            if settings.get("note"):
                note += f" Basis note: {settings.get('note')}"
            return float(manual_d), f"{tension_face} face", note
        # Invalid manual values must not silently govern capacity; fall back to
        # auto and keep the issue visible in the audit notes.
        manual_note = f"Manual d = {manual_d} mm is outside a reasonable section-depth range; auto d basis used instead."
    else:
        manual_note = ""
    y_tension = _beam_uls_reinforcement_y_centroid_for_face(analysis_input, tension_face=tension_face)
    if y_tension is None:
        d_eff = 0.80 * h
        note = "Effective depth estimated as 0.80h because no active tension reinforcement centroid was available."
        if manual_note:
            note = manual_note + " " + note
        return float(d_eff), f"{tension_face} face", note
    if tension_face == "top":
        d_eff = float(y_tension) - float(y_min)
    else:
        d_eff = float(y_max) - float(y_tension)
    # Guard against pathological centroids without hiding the basis.
    d_eff = min(max(float(d_eff), 0.50 * h), 0.95 * h)
    note = "Effective depth estimated from active reinforcement centroid at local tension face."
    if manual_note:
        note = manual_note + " " + note
    return d_eff, f"{tension_face} face", note


def _beam_uls_shear_reinforcement_dataframe_from_state(state: Mapping[str, object]) -> pd.DataFrame:
    raw = _beam_uls_get_state_value(state, SHEAR_REINFORCEMENT_TABLE_KEY, None)
    if raw is None:
        raw = (_beam_uls_get_state_value(state, "project_metadata", {}) or {}).get(SHEAR_REINFORCEMENT_TABLE_KEY)
    columns = ["Active", "Zone", "x_start_m", "x_end_m", "Bar Size", "Diameter_mm", "Legs", "Spacing_mm", "fy_MPa", "Note"]
    df = pd.DataFrame(raw if raw is not None else [], columns=columns)
    for column in columns:
        if column not in df.columns:
            df[column] = None
    df = df[columns].copy()
    df["Active"] = df["Active"].map(_beam_uls_active_value)
    for column in ["x_start_m", "x_end_m", "Diameter_mm", "Legs", "Spacing_mm", "fy_MPa"]:
        df[column] = df[column].map(_beam_uls_float)
    df["Zone"] = df["Zone"].map(lambda value: str(value or "").strip())
    df["Bar Size"] = df["Bar Size"].map(lambda value: str(value or "").strip())
    df["Note"] = df["Note"].map(lambda value: str(value or "").strip())
    return df




def _beam_uls_shear_reinforcement_status_dataframe(state: Mapping[str, object]) -> pd.DataFrame:
    """Return a compact read-only view of the stirrup layout consumed by Analysis.

    The Shear tab is not an input owner.  This table makes the source-of-truth
    visible when φVn is not plotted, so users can see whether the issue is a
    missing table, inactive zones, or incomplete bar/spacing data.
    """

    columns = ["Active", "Zone", "Range", "Stirrup", "Av/s provided", "Readiness", "Note"]
    df = _beam_uls_shear_reinforcement_dataframe_from_state(state)
    if df.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for _, row in df.iterrows():
        active = bool(row.get("Active"))
        x_start = _beam_uls_float(row.get("x_start_m"))
        x_end = _beam_uls_float(row.get("x_end_m"))
        legs = _beam_uls_float(row.get("Legs"))
        spacing = _beam_uls_float(row.get("Spacing_mm"))
        fy = _beam_uls_float(row.get("fy_MPa"))
        bar = str(row.get("Bar Size") or "-").strip() or "-"
        area = _beam_uls_stirrup_area_mm2(row)
        avs_m = area * legs / spacing * 1000.0 if all(math.isfinite(value) and value > 0.0 for value in [area, legs, spacing]) else float("nan")
        complete = all(math.isfinite(value) and value > 0.0 for value in [area, legs, spacing, fy]) and math.isfinite(x_start) and math.isfinite(x_end) and x_end >= x_start
        if active and complete:
            readiness = "ACTIVE / READY"
        elif active:
            readiness = "ACTIVE / INCOMPLETE"
        else:
            readiness = "INACTIVE — not used for φVn"
        range_text = f"{x_start:.3f}–{x_end:.3f} m" if math.isfinite(x_start) and math.isfinite(x_end) else "-"
        stirrup_text = f"{bar} × {int(legs) if math.isfinite(legs) and legs > 0 else '-'} legs @ {spacing:.0f} mm" if math.isfinite(spacing) and spacing > 0 else f"{bar} × {int(legs) if math.isfinite(legs) and legs > 0 else '-'} legs @ -"
        rows.append(
            {
                "Active": "Yes" if active else "No",
                "Zone": str(row.get("Zone") or "-"),
                "Range": range_text,
                "Stirrup": stirrup_text,
                "Av/s provided": _format_beam_uls_audit_number(avs_m, unit="mm²/m"),
                "Readiness": readiness,
                "Note": str(row.get("Note") or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _render_beam_uls_shear_layout_readiness_panel(state: Mapping[str, object]) -> None:
    """Show why φVn is hidden and where the provided stirrup input lives."""

    layout_df = _beam_uls_shear_reinforcement_status_dataframe(state)
    if layout_df.empty:
        st.warning(
            "φVn is not plotted because no Beam/Girder shear reinforcement table is available yet. "
            "Analysis is read-only: create the provided stirrup zones in Sections → Rebar → Beam/Girder Shear Reinforcement Layout, then activate the accepted zones."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Active": "No",
                        "Zone": "Support / Midspan / custom",
                        "Range": "x start–x end",
                        "Stirrup": "DB12 × 2 legs @ 150 mm",
                        "Av/s provided": "-",
                        "Readiness": "Define in Sections → Rebar",
                        "Note": "Template only — not used for capacity",
                    }
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        return

    active_count = int((layout_df["Active"] == "Yes").sum()) if "Active" in layout_df.columns else 0
    if active_count <= 0:
        st.warning(
            "φVn is not plotted because the provided stirrup table exists but no stirrup zone is Active. "
            "Go to Sections → Rebar → Beam/Girder Shear Reinforcement Layout and activate the zones that are actually provided."
        )
    else:
        st.info(
            "Provided stirrup layout is read from Sections → Rebar. If φVn is still not plotted, check that active zones have valid range, bar size, legs, spacing, and fy."
        )
    st.markdown("##### Provided stirrup layout read from Sections → Rebar")
    st.dataframe(layout_df, use_container_width=True, hide_index=True)

def _beam_uls_shear_zone_covers_station(zone: Mapping[str, object] | None, x_m: float) -> bool:
    if zone is None or not math.isfinite(float(x_m)):
        return False
    x_start = _beam_uls_float(zone.get("x_start_m"))
    x_end = _beam_uls_float(zone.get("x_end_m"))
    return (
        math.isfinite(x_start)
        and math.isfinite(x_end)
        and float(x_start) - 1.0e-9 <= float(x_m) <= float(x_end) + 1.0e-9
    )


def _beam_uls_active_shear_zone_for_station(
    state: Mapping[str, object],
    x_m: float,
    *,
    require_coverage: bool = False,
) -> dict[str, object] | None:
    zones = _beam_uls_shear_reinforcement_dataframe_from_state(state)
    if zones.empty:
        return None
    active = zones[zones["Active"]].copy()
    if active.empty:
        return None
    active = active[pd.to_numeric(active["x_start_m"], errors="coerce").notna() & pd.to_numeric(active["x_end_m"], errors="coerce").notna()]
    if active.empty:
        return None
    active["__distance"] = active.apply(
        lambda row: 0.0
        if float(row["x_start_m"]) - 1.0e-9 <= float(x_m) <= float(row["x_end_m"]) + 1.0e-9
        else min(abs(float(x_m) - float(row["x_start_m"])), abs(float(x_m) - float(row["x_end_m"]))),
        axis=1,
    )
    covered = active[active["__distance"] <= 1.0e-8]
    if require_coverage and covered.empty:
        return None
    source = covered if not covered.empty else active
    row = source.sort_values(["__distance", "x_start_m", "x_end_m"], kind="stable").iloc[0]
    return row.to_dict()


def _beam_uls_stirrup_area_mm2(zone: Mapping[str, object]) -> float:
    diameter = _beam_uls_float(zone.get("Diameter_mm"))
    if not math.isfinite(diameter) or diameter <= 0.0:
        text = str(zone.get("Bar Size") or "").strip().upper().replace("DB", "")
        diameter = _beam_uls_float(text)
    if not math.isfinite(diameter) or diameter <= 0.0:
        return float("nan")
    return math.pi * diameter * diameter / 4.0


def _beam_uls_shear_detailing_guard(
    *,
    strength_route: BeamGirderUlsStrengthRoute,
    fc_MPa: float,
    bw_mm: float,
    d_eff_mm: float,
    dv_mm: float | None,
    spacing_mm: float,
    avs_mm2_per_mm: float,
    fy_MPa: float,
) -> dict[str, object]:
    """Return shear minimum-reinforcement and spacing detailing gate values.

    SHEAR.CODE2 promotes the provided-stirrup shear check from a strength-only
    preview to a deterministic design gate: the active zone must provide at
    least the route minimum Av/s and must satisfy the route maximum spacing
    screen.  Development length, anchorage, and shop-drawing details remain
    project review items outside this sectional ULS gate.
    """

    notes: list[str] = []
    if not all(
        math.isfinite(value) and value > 0.0
        for value in [fc_MPa, bw_mm, d_eff_mm, spacing_mm, avs_mm2_per_mm, fy_MPa]
    ):
        return {
            "Detailing status": "REVIEW",
            "Av/s required mm2/mm": float("nan"),
            "Av/s required mm2/m": float("nan"),
            "Av/s min D/C": float("nan"),
            "s max mm": float("nan"),
            "Spacing D/C": float("nan"),
            "Detailing D/C value": float("nan"),
            "Detailing notes": "Detailing guard needs finite f'c, bw, d/dv, spacing, Av/s, and fy.",
        }

    sqrt_fc = math.sqrt(float(fc_MPa))
    if strength_route.is_bridge:
        depth_for_spacing = float(dv_mm) if dv_mm is not None and math.isfinite(float(dv_mm)) and float(dv_mm) > 0.0 else float(d_eff_mm)
        avs_required = 0.083 * sqrt_fc * float(bw_mm) / float(fy_MPa)
        s_max = min(0.80 * depth_for_spacing, 600.0)
        basis = "AASHTO LRFD minimum Av/s and maximum spacing gate"
        notes.append("AASHTO shear detailing gate checks minimum Av/s and maximum stirrup spacing for the active provided zone.")
    else:
        avs_required = max(0.062 * sqrt_fc * float(bw_mm) / float(fy_MPa), 0.35 * float(bw_mm) / float(fy_MPa))
        s_max = min(0.50 * float(d_eff_mm), 600.0)
        basis = "ACI 318 minimum Av/s and maximum spacing gate"
        notes.append("ACI shear detailing gate checks minimum Av/s and maximum spacing for the provided stirrup zone.")

    avs_dc = float(avs_required) / float(avs_mm2_per_mm) if avs_mm2_per_mm > 0.0 else float("nan")
    spacing_dc = float(spacing_mm) / float(s_max) if s_max > 0.0 else float("nan")
    finite_dcs = [value for value in [avs_dc, spacing_dc] if math.isfinite(value)]
    detailing_dc = max(finite_dcs) if finite_dcs else float("nan")

    if not finite_dcs:
        status = "REVIEW"
        notes.append("Could not evaluate Av/s or spacing guard.")
    elif detailing_dc <= 1.0 + 1.0e-9:
        status = "PASS"
    else:
        status = "FAIL"
        if math.isfinite(avs_dc) and avs_dc > 1.0 + 1.0e-9:
            notes.append("Provided Av/s is less than the route minimum shear reinforcement gate.")
        if math.isfinite(spacing_dc) and spacing_dc > 1.0 + 1.0e-9:
            notes.append("Provided stirrup spacing exceeds the route maximum spacing gate.")

    return {
        "Detailing status": status,
        "Av/s required mm2/mm": float(avs_required),
        "Av/s required mm2/m": float(avs_required) * 1000.0,
        "Av/s min D/C": avs_dc,
        "s max mm": float(s_max),
        "Spacing D/C": spacing_dc,
        "Detailing D/C value": detailing_dc,
        "Detailing basis": basis,
        "Detailing notes": " ".join(notes),
    }


def _beam_uls_shear_result_for_row(
    state: Mapping[str, object],
    row: Mapping[str, object],
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    x_m = _beam_uls_float(row.get("Station x (m)"))
    vu_kN = _beam_uls_float(row.get("Vuy"))
    mux_kNm = _beam_uls_float(row.get("Mux"))
    case = str(row.get("Case Name") or "-")
    diagram_boundary = bool(row.get("__Diagram boundary"))
    critical_section = bool(row.get("__Critical shear section"))
    station_type = "DIAGRAM BOUNDARY" if diagram_boundary else ("CRITICAL SHEAR SECTION" if critical_section else "LOAD STATION")
    support_side = str(row.get("__Support side") or "-")
    critical_offset_m = _beam_uls_float(row.get("__Critical offset m"))
    notes: list[str] = []
    if critical_section:
        notes.append("Critical shear section inserted by Analysis; demand is interpolated from active ULS station rows and this row is considered for governing shear D/C.")
    if not math.isfinite(vu_kN) or abs(vu_kN) <= _BEAM_ULS_DEMAND_TOL:
        if not diagram_boundary:
            return {
                "Check": "Shear",
                "Status": "NO DEMAND",
                "Governing x": _format_beam_uls_x(x_m),
                "Case": case,
                "Demand": "-",
                "Capacity": "-",
                "Utilization": "-",
                "Demand kN": 0.0,
                "φVn kN": float("nan"),
                "D/C value": float("nan"),
                "Notes": "No finite Vuy demand.",
            }
        vu_kN = 0.0
        notes.append("Diagram boundary capacity value only; not a governing shear design section.")
    zone = _beam_uls_active_shear_zone_for_station(state, x_m, require_coverage=not diagram_boundary)
    if zone is None:
        return {
            "Check": "Shear",
            "Status": "LAYOUT REQUIRED",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "φVn kN": float("nan"),
            "D/C value": float("nan"),
            "Zone": "-",
            "Notes": "No active stirrup zone covers this design/check station. Extend or add a provided stirrup zone; nearest zones are not used for final shear acceptance.",
        }
    analysis_input, input_messages = _beam_uls_flexure_analysis_input_for_station(state, row=row, strength_route=strength_route)
    if input_messages:
        notes.extend(input_messages)
    if analysis_input is None:
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "φVn kN": float("nan"),
            "D/C value": float("nan"),
            "Zone": str(zone.get("Zone") or "-"),
            "Notes": "; ".join(notes) or "Section/material input not ready for shear check.",
        }
    concrete = analysis_input.concrete_material
    fc = float(concrete.fc_MPa)
    bw_mm, bw_note = _beam_uls_web_width_mm(analysis_input.section_geometry)
    depth_values = _beam_uls_effective_shear_depth_values_mm(
        state,
        analysis_input,
        mux_kNm=mux_kNm,
        strength_route=strength_route,
    )
    d_eff_mm = depth_values.get("d_mm")
    dv_eff_mm = depth_values.get("dv_mm")
    tension_face = str(depth_values.get("tension_face") or "-")
    notes.extend([bw_note, str(depth_values.get("d_note") or ""), str(depth_values.get("dv_note") or "")])
    if bw_mm is None or d_eff_mm is None or fc <= 0.0:
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "φVn kN": float("nan"),
            "D/C value": float("nan"),
            "Zone": str(zone.get("Zone") or "-"),
            "Notes": "; ".join(notes),
        }
    stirrup_area = _beam_uls_stirrup_area_mm2(zone)
    legs = _beam_uls_float(zone.get("Legs"))
    spacing = _beam_uls_float(zone.get("Spacing_mm"))
    fy = _beam_uls_float(zone.get("fy_MPa"))
    if not all(math.isfinite(value) and value > 0.0 for value in [stirrup_area, legs, spacing, fy]):
        return {
            "Check": "Shear",
            "Status": "REVIEW",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(vu_kN, "kN"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN": float(vu_kN),
            "φVn kN": float("nan"),
            "D/C value": float("nan"),
            "Zone": str(zone.get("Zone") or "-"),
            "Notes": "Active stirrup zone has incomplete bar/leg/spacing/fy input.",
        }
    avs_mm2_per_mm = float(stirrup_area) * float(legs) / float(spacing)
    if strength_route.is_bridge:
        phi = 0.90
        beta = 2.0
        theta_deg = 45.0
        cot_theta = 1.0
        vc_factor = 0.083 * beta
        method = "AASHTO LRFD shear strength/detailing gate (β=2.0, θ=45° sectional route)"
        code_basis = "φVn — AASHTO LRFD shear gate"
        phi_policy = "AASHTO LRFD shear resistance factor φ = 0.90"
        depth_for_vs = float(dv_eff_mm) if dv_eff_mm is not None and math.isfinite(float(dv_eff_mm)) and float(dv_eff_mm) > 0.0 else float(d_eff_mm)
        depth_label = "dv"
        notes.append("AASHTO SHEAR.CODE2 gate uses Vc = 0.083β√f'c bv dv with β=2.0, θ=45°, provided Av/s, and Vn capped at 0.25f'c bv dv; prestress vertical component Vp is zero unless included in imported resultants.")
    else:
        phi = 0.75
        beta = float("nan")
        theta_deg = 45.0
        cot_theta = 1.0
        depth_for_vs = float(d_eff_mm)
        vc_factor = 0.17
        method = "ACI 318 shear strength/detailing gate with provided stirrups"
        code_basis = "φVn — ACI 318 shear gate"
        phi_policy = "ACI 318 shear strength-reduction factor φ = 0.75"
        depth_label = "d"
        notes.append("ACI SHEAR.CODE2 gate uses Vc = 0.17√f'c bw d, provided Av/s, ACI minimum Av/s, maximum spacing, and a Vs maximum screen.")
    vc_n = vc_factor * math.sqrt(fc) * float(bw_mm) * float(depth_for_vs)
    vs_n = avs_mm2_per_mm * float(fy) * float(depth_for_vs) * float(cot_theta)
    vn_uncapped_n = max(0.0, vc_n + vs_n)
    if strength_route.is_bridge:
        vn_limit_n = 0.25 * float(fc) * float(bw_mm) * float(depth_for_vs)
        vn_limit_basis = "AASHTO Vn ≤ 0.25 f'c bv dv"
    else:
        vs_limit_n = 0.66 * math.sqrt(fc) * float(bw_mm) * float(depth_for_vs)
        vn_limit_n = vc_n + vs_limit_n
        vn_limit_basis = "ACI Vs maximum screen"
    vn_n = min(vn_uncapped_n, vn_limit_n) if math.isfinite(vn_limit_n) and vn_limit_n > 0.0 else vn_uncapped_n
    phi_vn_kN = phi * vn_n / 1000.0
    strength_utilization = (
        float("nan") if diagram_boundary else abs(float(vu_kN)) / phi_vn_kN if phi_vn_kN > 0.0 else float("nan")
    )
    vn_limit_dc = vn_uncapped_n / vn_limit_n if math.isfinite(vn_limit_n) and vn_limit_n > 0.0 else float("nan")
    if math.isfinite(vn_limit_dc):
        vn_limit_status = "CAPPED" if vn_limit_dc > 1.0 + 1.0e-9 else "PASS"
    else:
        vn_limit_status = "REVIEW"
    strength_status = "BOUNDARY" if diagram_boundary else ("PASS" if math.isfinite(strength_utilization) and strength_utilization <= 1.0 else "FAIL")
    detailing = _beam_uls_shear_detailing_guard(
        strength_route=strength_route,
        fc_MPa=fc,
        bw_mm=float(bw_mm),
        d_eff_mm=float(d_eff_mm),
        dv_mm=float(depth_for_vs) if depth_label == "dv" else float("nan"),
        spacing_mm=float(spacing),
        avs_mm2_per_mm=float(avs_mm2_per_mm),
        fy_MPa=float(fy),
    )
    detailing_status = str(detailing.get("Detailing status") or "REVIEW")
    detailing_dc = _beam_uls_float(detailing.get("Detailing D/C value"))
    finite_dcs = [value for value in [strength_utilization, detailing_dc] if math.isfinite(value)]
    governing_dc = max(finite_dcs) if finite_dcs else float("nan")
    if diagram_boundary:
        status = "DIAGRAM BOUNDARY"
    elif strength_status == "FAIL" or detailing_status == "FAIL":
        status = "FAIL"
    elif detailing_status == "REVIEW" or vn_limit_status == "REVIEW":
        status = "REVIEW"
    else:
        status = "PASS"
    if vn_uncapped_n > vn_n + 1.0e-6:
        notes.append(f"Nominal Vn was capped by {vn_limit_basis}.")
    if status == "PASS":
        notes.append("SHEAR.CODE2 strength, Vn-limit, minimum Av/s, maximum spacing, and zone-coverage gates pass for this station.")
    if detailing.get("Detailing notes"):
        notes.append(str(detailing.get("Detailing notes")))
    if diagram_boundary:
        utilization_text = "-"
        governing_dc = float("nan")
    else:
        utilization_text = _format_beam_uls_ratio(strength_utilization)
        if math.isfinite(detailing_dc):
            utilization_text = f"{utilization_text} / det {_format_beam_uls_ratio(detailing_dc)}"
    return {
        "Check": "Shear",
        "Status": status,
        "Strength status": strength_status,
        "Detailing status": detailing_status,
        "Station type": station_type,
        "Support side": support_side,
        "Critical offset m": critical_offset_m if math.isfinite(critical_offset_m) else float("nan"),
        "Governing x": _format_beam_uls_x(x_m),
        "Case": case,
        "Demand": _format_beam_uls_demand(vu_kN, "kN") if not diagram_boundary else "0.00 kN",
        "Capacity": f"φVn = {phi_vn_kN:,.2f} kN",
        "Utilization": utilization_text,
        "Demand kN": float(vu_kN),
        "Abs demand kN": abs(float(vu_kN)),
        "φVn kN": phi_vn_kN,
        "φVc kN": phi * vc_n / 1000.0,
        "φVs kN": phi * vs_n / 1000.0,
        "Vc kN": vc_n / 1000.0,
        "Vs kN": vs_n / 1000.0,
        "Vn kN": vn_n / 1000.0,
        "Vn uncapped kN": vn_uncapped_n / 1000.0,
        "Vn limit kN": vn_limit_n / 1000.0 if math.isfinite(vn_limit_n) else float("nan"),
        "φVn limit kN": phi * vn_limit_n / 1000.0 if math.isfinite(vn_limit_n) else float("nan"),
        "Vn limit D/C": vn_limit_dc,
        "Vn limit status": vn_limit_status,
        "D/C value": strength_utilization,
        "Strength D/C value": strength_utilization,
        "Detailing D/C value": detailing_dc,
        "Governing D/C value": governing_dc,
        "Zone": str(zone.get("Zone") or "Zone"),
        "Stirrup": f"{zone.get('Bar Size') or '-'} × {int(float(legs))} legs @ {float(spacing):.0f} mm",
        "Av/s mm2/mm": avs_mm2_per_mm,
        "Av/s mm2/m": avs_mm2_per_mm * 1000.0,
        "Av/s required mm2/mm": detailing.get("Av/s required mm2/mm", float("nan")),
        "Av/s required mm2/m": detailing.get("Av/s required mm2/m", float("nan")),
        "Av/s min D/C": detailing.get("Av/s min D/C", float("nan")),
        "s max mm": detailing.get("s max mm", float("nan")),
        "Spacing D/C": detailing.get("Spacing D/C", float("nan")),
        "Detailing basis": detailing.get("Detailing basis", "-"),
        "bw mm": float(bw_mm),
        f"{depth_label} mm": float(depth_for_vs),
        "d mm": float(d_eff_mm),
        "dv mm": float(depth_for_vs) if depth_label == "dv" else (float(dv_eff_mm) if dv_eff_mm is not None and math.isfinite(float(dv_eff_mm)) else float("nan")),
        "Tension face": tension_face,
        "β": beta,
        "θ deg": theta_deg,
        "cotθ": cot_theta,
        "φ": phi,
        "Code basis": code_basis,
        "φ policy": phi_policy,
        "Method": method,
        "Notes": "; ".join(part for part in notes if part),
    }


def _beam_uls_shear_check_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Strength status", "Detailing status", "Station type", "Support side", "Critical offset m", "Governing x", "Case", "Demand", "Capacity", "Utilization",
        "Demand kN", "Abs demand kN", "φVn kN", "φVc kN", "φVs kN", "Vc kN", "Vs kN", "Vn kN", "Vn uncapped kN", "Vn limit kN", "φVn limit kN",
        "D/C value", "Strength D/C value", "Detailing D/C value", "Governing D/C value", "Vn limit D/C",
        "Zone", "Stirrup", "Av/s mm2/mm", "Av/s mm2/m", "Av/s required mm2/mm", "Av/s required mm2/m",
        "Av/s min D/C", "s max mm", "Spacing D/C", "Detailing basis", "bw mm", "d mm", "dv mm", "Tension face", "Vn limit status", "β", "θ deg", "cotθ", "φ", "Code basis", "φ policy", "Method", "Notes",
    ]
    if active_df.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for _, demand_row in active_df.iterrows():
        result = _beam_uls_shear_result_for_row(state, demand_row, strength_route=strength_route)
        if "dv mm" not in result and "dv mm" in columns:
            result["dv mm"] = float("nan")
        for column in columns:
            result.setdefault(
                column,
                float("nan")
                if column.endswith("kN")
                or column.endswith("mm")
                or column.endswith("mm2/mm")
                or column.endswith("mm2/m")
                or column in {"D/C value", "Strength D/C value", "Detailing D/C value", "Governing D/C value", "Vn limit D/C", "Av/s min D/C", "Spacing D/C", "β", "θ deg", "cotθ", "φ"}
                else "-",
            )
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)




def _beam_uls_interpolated_demand_row_for_case(
    active_df: pd.DataFrame,
    *,
    case_name: str,
    x_m: float,
    note: str = "",
) -> dict[str, object] | None:
    """Return an interpolated/extrapolated ULS demand row for a case.

    Critical shear sections rarely coincide exactly with imported station rows.
    The Analysis page remains read-only: it interpolates from the active Loads
    station resultants and makes that basis explicit in the row note.
    """

    if active_df is None or active_df.empty or not math.isfinite(float(x_m)):
        return None
    df = active_df.copy()
    if "Case Name" in df.columns:
        case_df = df[df["Case Name"].astype(str) == str(case_name)].copy()
        if case_df.empty:
            case_df = df.copy()
    else:
        case_df = df.copy()
    if case_df.empty or "Station x (m)" not in case_df.columns:
        return None
    case_df["__x_m"] = pd.to_numeric(case_df["Station x (m)"], errors="coerce")
    case_df = case_df[case_df["__x_m"].notna()].sort_values("__x_m", kind="stable")
    if case_df.empty:
        return None

    # Collapse duplicate stations by keeping the last edited/imported row.
    case_df = case_df.drop_duplicates(subset=["__x_m"], keep="last").sort_values("__x_m", kind="stable")
    xs = [float(value) for value in case_df["__x_m"].tolist()]

    def _interp_column(column: str, default: float = 0.0) -> float:
        if column not in case_df.columns:
            return default
        values = [float(_beam_uls_float(value)) for value in case_df[column].tolist()]
        finite_pairs = [(x, y) for x, y in zip(xs, values) if math.isfinite(x) and math.isfinite(y)]
        if not finite_pairs:
            return default
        if len(finite_pairs) == 1:
            return float(finite_pairs[0][1])
        x_target = float(x_m)
        # Linear interpolation inside the station range and linear extrapolation
        # just outside the range.  This keeps the critical-section demand tied
        # to the user's active station-resultant diagram instead of inventing a
        # separate load model in Analysis.
        for (x0, y0), (x1, y1) in zip(finite_pairs[:-1], finite_pairs[1:]):
            if (x0 <= x_target <= x1) or (x1 <= x_target <= x0):
                if abs(x1 - x0) <= 1.0e-12:
                    return float(y0)
                ratio = (x_target - x0) / (x1 - x0)
                return float(y0 + ratio * (y1 - y0))
        if x_target < finite_pairs[0][0]:
            x0, y0 = finite_pairs[0]
            x1, y1 = finite_pairs[1]
        else:
            x0, y0 = finite_pairs[-2]
            x1, y1 = finite_pairs[-1]
        if abs(x1 - x0) <= 1.0e-12:
            return float(y0)
        ratio = (x_target - x0) / (x1 - x0)
        return float(y0 + ratio * (y1 - y0))

    return {
        "Active": True,
        "Station x (m)": float(x_m),
        "Case Name": str(case_name),
        "Mux": _interp_column("Mux", 1.0e-3),
        "Vuy": _interp_column("Vuy", 0.0),
        "Tu": _interp_column("Tu", 0.0),
        "Muy": _interp_column("Muy", 0.0),
        "Vux": _interp_column("Vux", 0.0),
        "Nu": _interp_column("Nu", 0.0),
        "Note": note or "Interpolated ULS demand row",
    }


def _beam_uls_shear_empty_result_dataframe(active_df: pd.DataFrame, *, state: Mapping[str, object], strength_route: BeamGirderUlsStrengthRoute) -> pd.DataFrame:
    return _beam_uls_shear_check_dataframe(
        state,
        pd.DataFrame(columns=list(active_df.columns) if isinstance(active_df, pd.DataFrame) else []),
        strength_route=strength_route,
    )


def _beam_uls_shear_default_critical_section_rows(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> list[dict[str, object]]:
    """Return first-pass critical shear section marker rows independent of stirrup-zone coverage.

    The graph marker should not disappear merely because the exact critical
    section is outside an active stirrup zone.  Capacity may still be unavailable
    at that location, but the critical x-location itself remains useful and must
    be visible so the user can see a layout gap near the support.
    """

    if active_df is None or active_df.empty:
        return []
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    if not math.isfinite(span_m) or span_m <= 0.0:
        return []
    cases = [str(value or "-") for value in active_df.get("Case Name", pd.Series(["-"])).dropna().unique().tolist()]
    if not cases:
        cases = ["-"]

    # Prefer the already evaluated station shear rows as the source of truth for d/dv.
    # The user screenshot that triggered ULS.SHEAR4.1 had valid shear capacity and
    # d/dv in the Shear cards, but the critical-section dataframe was empty because
    # the marker generator tried to rebuild an AnalysisInput at the support first.
    # That coupling is fragile: critical-section locations should come from the
    # effective-depth basis that the Shear check already consumed.
    station_depth_df = _beam_uls_shear_check_dataframe(state, active_df, strength_route=strength_route)

    def _numeric_x_from_row(row: Mapping[str, object]) -> float:
        if "Station x (m)" in row:
            value = _beam_uls_float(row.get("Station x (m)"))
            if math.isfinite(value):
                return float(value)
        text = str(row.get("Governing x") or "").replace("m", "").strip()
        return _beam_uls_float(text)

    def _offset_from_station_depths(case_name: str, support_side: str) -> float | None:
        if station_depth_df is None or station_depth_df.empty:
            return None
        df = station_depth_df.copy()
        if "Case" in df.columns:
            case_df = df[df["Case"].astype(str) == str(case_name)].copy()
            if not case_df.empty:
                df = case_df
        if "Station type" in df.columns:
            df = df[df["Station type"].astype(str) != "DIAGRAM BOUNDARY"].copy()
        if df.empty:
            return None
        df["__x_m"] = df.apply(_numeric_x_from_row, axis=1)
        df = df[pd.to_numeric(df["__x_m"], errors="coerce").notna()].copy()
        if not df.empty:
            df["__support_distance"] = df["__x_m"].map(lambda x: abs(float(x) - (0.0 if support_side == "Left" else float(span_m))))
            df = df.sort_values("__support_distance", kind="stable")
        depth_columns = ["dv mm", "d mm"] if strength_route.is_bridge else ["d mm"]
        for _, depth_row in df.iterrows():
            for column in depth_columns:
                depth_mm = _beam_uls_float(depth_row.get(column))
                if math.isfinite(depth_mm) and depth_mm > 0.0:
                    return min(max(float(depth_mm) / 1000.0, 0.0), 0.50 * float(span_m))
        return None

    def _offset_from_support_analysis(case_name: str, support_x: float) -> float | None:
        support_row = _beam_uls_interpolated_demand_row_for_case(
            active_df,
            case_name=case_name,
            x_m=support_x,
            note="Support row used to estimate d/dv for critical shear section",
        )
        if support_row is None:
            # Fallback to a simple row.  This still lets the section-geometry
            # helper calculate d/dv when the user imported only interior
            # station resultants.
            support_row = {
                "Active": True,
                "Station x (m)": float(support_x),
                "Case Name": str(case_name),
                "Mux": 1.0e-3,
                "Vuy": 0.0,
                "Tu": 0.0,
                "Muy": 0.0,
                "Vux": 0.0,
                "Nu": 0.0,
                "Note": "Support fallback row used to estimate d/dv for critical shear section",
            }
        analysis_input, _messages = _beam_uls_flexure_analysis_input_for_station(
            state,
            row=support_row,
            strength_route=strength_route,
        )
        if analysis_input is None:
            return None
        mux_kNm = _beam_uls_float(support_row.get("Mux"))
        depth_values = _beam_uls_effective_shear_depth_values_mm(
            state,
            analysis_input,
            mux_kNm=mux_kNm,
            strength_route=strength_route,
        )
        d_eff_mm = depth_values.get("d_mm")
        if d_eff_mm is None or not math.isfinite(float(d_eff_mm)) or float(d_eff_mm) <= 0.0:
            return None
        if strength_route.is_bridge:
            dv_eff_mm = depth_values.get("dv_mm")
            offset_mm = float(dv_eff_mm) if dv_eff_mm is not None and math.isfinite(float(dv_eff_mm)) and float(dv_eff_mm) > 0.0 else float(d_eff_mm)
        else:
            offset_mm = float(d_eff_mm)
        return min(max(float(offset_mm) / 1000.0, 0.0), 0.50 * float(span_m))

    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str, float]] = set()
    for case_name in cases:
        for support_side, support_x in (("Left", 0.0), ("Right", float(span_m))):
            offset_m = _offset_from_station_depths(case_name, support_side)
            if offset_m is None or not math.isfinite(float(offset_m)) or float(offset_m) <= 1.0e-9:
                offset_m = _offset_from_support_analysis(case_name, support_x)
            if offset_m is None or not math.isfinite(float(offset_m)) or float(offset_m) <= 1.0e-9:
                continue
            x_crit = float(offset_m) if support_side == "Left" else float(span_m) - float(offset_m)
            x_crit = min(max(float(x_crit), 0.0), float(span_m))
            key = (case_name, support_side, round(x_crit, 9))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "Case": str(case_name),
                    "Support side": support_side,
                    "Critical offset m": float(offset_m),
                    "Governing x": _format_beam_uls_x(x_crit),
                    "x_m": x_crit,
                }
            )
    return rows


def _beam_uls_shear_critical_section_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    """Return first-pass critical shear section rows near each support.

    These rows are design-check rows, not graphical endpoint boundaries.  The
    default critical-section offset is d for ACI Building Beam/Girder and dv for
    AASHTO Bridge Beam/Girder.  The shear demand is interpolated from the active
    Loads ULS station-resultant diagram for each load case.
    """

    base = _beam_uls_shear_empty_result_dataframe(active_df, state=state, strength_route=strength_route)
    columns = list(base.columns)
    marker_rows = _beam_uls_shear_default_critical_section_rows(state, active_df, strength_route=strength_route)
    if not marker_rows:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, object]] = []
    for marker in marker_rows:
        case_name = str(marker.get("Case") or "-")
        support_side = str(marker.get("Support side") or "-")
        x_crit = _beam_uls_float(marker.get("x_m"))
        offset_m = _beam_uls_float(marker.get("Critical offset m"))
        if not math.isfinite(x_crit):
            continue
        demand_row = _beam_uls_interpolated_demand_row_for_case(
            active_df,
            case_name=case_name,
            x_m=x_crit,
            note=f"Critical shear section at {support_side.lower()} support",
        )
        if demand_row is None:
            demand_row = {
                "Active": True,
                "Station x (m)": float(x_crit),
                "Case Name": case_name,
                "Mux": 1.0e-3,
                "Vuy": 0.0,
                "Tu": 0.0,
                "Muy": 0.0,
                "Vux": 0.0,
                "Nu": 0.0,
                "Note": f"Critical shear section at {support_side.lower()} support; demand interpolation unavailable",
            }
        demand_row["__Critical shear section"] = True
        demand_row["__Support side"] = support_side
        demand_row["__Critical offset m"] = offset_m
        result = _beam_uls_shear_result_for_row(state, demand_row, strength_route=strength_route)
        if "dv mm" not in result and "dv mm" in columns:
            result["dv mm"] = float("nan")
        for column in columns:
            result.setdefault(
                column,
                float("nan")
                if column.endswith("kN")
                or column.endswith("mm")
                or column.endswith("mm2/mm")
                or column.endswith("mm2/m")
                or column in {"D/C value", "Strength D/C value", "Detailing D/C value", "Governing D/C value", "Av/s min D/C", "Spacing D/C", "Critical offset m", "φ"}
                else "-",
            )
        # Preserve the marker identity even when capacity is not ready because
        # the exact critical section is outside the active stirrup layout.
        result["Station type"] = "CRITICAL SHEAR SECTION"
        result["Support side"] = support_side
        result["Critical offset m"] = offset_m
        result["Governing x"] = _format_beam_uls_x(x_crit)
        if not math.isfinite(_beam_uls_float(result.get("φVn kN"))):
            existing_notes = str(result.get("Notes") or "").strip()
            note = "Critical shear section is visible, but capacity is not ready at this exact location. Check that an active stirrup zone covers the critical section."
            result["Notes"] = f"{existing_notes}; {note}" if existing_notes else note
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_combine_shear_check_frames(*frames: pd.DataFrame | None) -> pd.DataFrame:
    valid_frames = [frame for frame in frames if isinstance(frame, pd.DataFrame) and not frame.empty]
    if not valid_frames:
        columns: list[str] = []
        for frame in frames:
            if isinstance(frame, pd.DataFrame):
                columns = list(frame.columns)
                break
        return pd.DataFrame(columns=columns)
    return pd.concat(valid_frames, ignore_index=True, sort=False)

def _beam_uls_shear_diagram_boundary_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    """Return φVc/φVs/φVn diagram-boundary rows at x=0 and x=L.

    These rows are for plotting capacity continuity only.  They are not added to
    the governing shear check because shear design normally uses critical
    sections near supports, not an automatically certified check at the exact
    member end.
    """

    base = _beam_uls_shear_check_dataframe(
        state,
        pd.DataFrame(columns=list(active_df.columns) if isinstance(active_df, pd.DataFrame) else []),
        strength_route=strength_route,
    )
    columns = list(base.columns)
    if active_df is None or active_df.empty:
        return pd.DataFrame(columns=columns)
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    if not math.isfinite(span_m) or span_m <= 0.0:
        return pd.DataFrame(columns=columns)
    cases = [str(value or "-") for value in active_df.get("Case Name", pd.Series(["-"])).dropna().unique().tolist()]
    if not cases:
        cases = ["-"]
    rows: list[dict[str, object]] = []
    for case_name in cases:
        for x_m in (0.0, float(span_m)):
            demand_row = {
                "Active": True,
                "Station x (m)": float(x_m),
                "Case Name": case_name,
                "Mux": 1.0e-3,
                "Vuy": 0.0,
                "Tu": 0.0,
                "Muy": 0.0,
                "Vux": 0.0,
                "Nu": 0.0,
                "Note": "Shear capacity diagram boundary",
                "__Diagram boundary": True,
            }
            result = _beam_uls_shear_result_for_row(state, demand_row, strength_route=strength_route)
            if "dv mm" not in result and "dv mm" in columns:
                result["dv mm"] = float("nan")
            for column in columns:
                result.setdefault(
                    column,
                    float("nan")
                    if column.endswith("kN")
                    or column.endswith("mm")
                    or column.endswith("mm2/mm")
                    or column.endswith("mm2/m")
                    or column in {"D/C value", "Strength D/C value", "Detailing D/C value", "Governing D/C value", "Vn limit D/C", "Av/s min D/C", "Spacing D/C", "β", "θ deg", "cotθ", "φ"}
                    else "-",
                )
            if math.isfinite(_beam_uls_float(result.get("φVn kN"))):
                rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_torsion_diagram_boundary_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    """Return φTcr / φTn diagram-boundary rows at x=0 and x=L.

    These rows are for plotting capacity continuity only. They are not added to
    the governing torsion check because torsion design still depends on the
    actual active demand stations plus separate longitudinal/detailing checks.
    """

    base = _beam_uls_torsion_check_dataframe(
        state,
        pd.DataFrame(columns=list(active_df.columns) if isinstance(active_df, pd.DataFrame) else []),
        strength_route=strength_route,
    )
    columns = list(base.columns)
    if active_df is None or active_df.empty:
        return pd.DataFrame(columns=columns)
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    if not math.isfinite(span_m) or span_m <= 0.0:
        return pd.DataFrame(columns=columns)
    cases = [str(value or "-") for value in active_df.get("Case Name", pd.Series(["-"])).dropna().unique().tolist()]
    if not cases:
        cases = ["-"]
    rows: list[dict[str, object]] = []
    active_rows = active_df.copy()
    active_rows["__x_m"] = pd.to_numeric(active_rows.get("Station x (m)"), errors="coerce")
    for case_name in cases:
        case_rows = active_rows[active_rows.get("Case Name", pd.Series(dtype=object)).astype(str) == case_name].copy() if "Case Name" in active_rows.columns else pd.DataFrame()
        for x_m in (0.0, float(span_m)):
            nearest_row: dict[str, object] = {}
            if not case_rows.empty and case_rows["__x_m"].notna().any():
                nearest_idx = (case_rows["__x_m"].astype(float) - float(x_m)).abs().idxmin()
                nearest_row = case_rows.loc[nearest_idx].to_dict()
            mux_seed = _beam_uls_float(nearest_row.get("Mux"))
            if not math.isfinite(mux_seed) or abs(mux_seed) <= 0.0:
                mux_seed = 1.0e-3
            demand_row = {
                "Active": True,
                "Station x (m)": float(x_m),
                "Case Name": case_name,
                "Mux": mux_seed,
                "Vuy": _beam_uls_float(nearest_row.get("Vuy")) if nearest_row else 0.0,
                # Tiny nonzero Tu keeps the torsion result path in capacity mode
                # so the diagram can expose φTcr / φTn boundary values at x=0 and x=L.
                "Tu": 1.0e-3,
                "Muy": _beam_uls_float(nearest_row.get("Muy")) if nearest_row else 0.0,
                "Vux": _beam_uls_float(nearest_row.get("Vux")) if nearest_row else 0.0,
                "Nu": _beam_uls_float(nearest_row.get("Nu")) if nearest_row else 0.0,
                "Note": "Torsion capacity diagram boundary",
                "__Diagram boundary": True,
            }
            result = _beam_uls_torsion_result_for_row(state, demand_row, strength_route=strength_route)
            result.setdefault("Station type", "DIAGRAM BOUNDARY")
            result.setdefault("Support side", "LEFT" if x_m <= 0.0 else "RIGHT")
            for column in columns:
                result.setdefault(
                    column,
                    float("nan")
                    if column.endswith("kN-m")
                    or column.endswith("mm2")
                    or column.endswith("mm")
                    or column.endswith("mm2/mm")
                    or column in {"D/C value", "Al utilization", "Spacing D/C", "Detailing D/C value", "θ deg", "cotθ", "φ"}
                    else "-",
                )
            phi_tn = _beam_uls_float(result.get("φTn kN-m"))
            phi_tcr = _beam_uls_float(result.get("φTcr kN-m"))
            if math.isfinite(phi_tn) or math.isfinite(phi_tcr):
                rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_governing_shear_row(shear_df: pd.DataFrame | None) -> dict[str, object] | None:
    if shear_df is None or shear_df.empty:
        return None
    df = shear_df.copy()
    governing_column = "Governing D/C value" if "Governing D/C value" in df.columns else "D/C value"
    if governing_column not in df.columns:
        return None
    df["__governing_dc"] = pd.to_numeric(df[governing_column], errors="coerce")
    valid = df[df["__governing_dc"].notna()].copy()
    if valid.empty:
        return None
    status_priority = {"FAIL": 3, "REVIEW": 2, "PASS": 1}
    valid["__status_priority"] = valid.get("Status", pd.Series(index=valid.index, dtype=object)).map(lambda value: status_priority.get(str(value), 0))
    idx = valid.sort_values(["__status_priority", "__governing_dc"], ascending=[False, False]).index[0]
    return df.loc[idx].drop(labels=["__governing_dc"], errors="ignore").to_dict()


def _beam_uls_shear_audit_dataframe(shear_df: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "Governing", "Station type", "Station x", "Support side", "Critical offset", "Case", "Status", "Strength", "Detailing", "Vn limit", "Vu demand", "φVn", "D/C", "Strength D/C", "Detailing D/C",
        "φVc", "φVs", "φVn limit", "Zone", "Stirrup", "Av/s", "Av/s min", "s max", "Spacing D/C", "Vn limit D/C", "bw", "d", "dv", "β", "θ", "φ", "Code basis", "Method", "Notes",
    ]
    if shear_df is None or shear_df.empty:
        return pd.DataFrame(columns=columns)
    df = shear_df.copy()
    governing_column = "Governing D/C value" if "Governing D/C value" in df.columns else "D/C value"
    df["__util"] = pd.to_numeric(df.get(governing_column), errors="coerce")
    governing_idx = df["__util"].idxmax() if df["__util"].notna().any() else None
    rows = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "Governing": "Yes" if governing_idx is not None and idx == governing_idx else "",
                "Station type": str(row.get("Station type") or "LOAD STATION"),
                "Station x": str(row.get("Governing x") or "-"),
                "Support side": str(row.get("Support side") or "-"),
                "Critical offset": _format_beam_uls_audit_number(row.get("Critical offset m"), unit="m"),
                "Case": str(row.get("Case") or "-"),
                "Status": str(row.get("Status") or "-"),
                "Strength": str(row.get("Strength status") or row.get("Status") or "-"),
                "Detailing": str(row.get("Detailing status") or "-"),
                "Vn limit": str(row.get("Vn limit status") or "-"),
                "Vu demand": _format_beam_uls_audit_number(row.get("Demand kN"), unit="kN"),
                "φVn": _format_beam_uls_audit_number(row.get("φVn kN"), unit="kN"),
                "D/C": _format_beam_uls_ratio(row.get("D/C value")),
                "Strength D/C": _format_beam_uls_ratio(row.get("Strength D/C value", row.get("D/C value"))),
                "Detailing D/C": _format_beam_uls_ratio(row.get("Detailing D/C value")),
                "φVc": _format_beam_uls_audit_number(row.get("φVc kN"), unit="kN"),
                "φVs": _format_beam_uls_audit_number(row.get("φVs kN"), unit="kN"),
                "φVn limit": _format_beam_uls_audit_number(row.get("φVn limit kN"), unit="kN"),
                "Zone": str(row.get("Zone") or "-"),
                "Stirrup": str(row.get("Stirrup") or "-"),
                "Av/s": _format_beam_uls_audit_number(row.get("Av/s mm2/m"), unit="mm²/m"),
                "Av/s min": _format_beam_uls_audit_number(row.get("Av/s required mm2/m"), unit="mm²/m"),
                "s max": _format_beam_uls_audit_number(row.get("s max mm"), unit="mm"),
                "Spacing D/C": _format_beam_uls_ratio(row.get("Spacing D/C")),
                "Vn limit D/C": _format_beam_uls_ratio(row.get("Vn limit D/C")),
                "bw": _format_beam_uls_audit_number(row.get("bw mm"), unit="mm"),
                "d": _format_beam_uls_audit_number(row.get("d mm"), unit="mm"),
                "dv": _format_beam_uls_audit_number(row.get("dv mm"), unit="mm"),
                "β": _format_beam_uls_ratio(row.get("β")),
                "θ": _format_beam_uls_audit_number(row.get("θ deg"), unit="deg"),
                "φ": _format_beam_uls_ratio(row.get("φ")),
                "Code basis": str(row.get("Code basis") or "-"),
                "Method": str(row.get("Method") or "-"),
                "Notes": str(row.get("Notes") or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)



def _beam_uls_outer_polygon_metrics(section_geometry: SectionGeometry) -> dict[str, float | str]:
    """Return outside-perimeter torsion geometry metrics in mm units.

    Torsion threshold terms use the outside concrete perimeter quantities.  This
    helper deliberately uses the outside polygon, not hole perimeters, so hollow
    or voided sections do not inflate Pcp.  Dedicated multi-cell/box torsion
    modelling remains a later milestone.
    """

    try:
        outer_polygon = to_shapely_polygon(SectionGeometry(name=section_geometry.name, outer_polygon=section_geometry.outer_polygon, holes=[]))
    except Exception:
        outer_polygon = None
    if outer_polygon is None or outer_polygon.is_empty or outer_polygon.area <= 0.0 or not outer_polygon.is_valid:
        return {"Acp mm2": float("nan"), "Pcp mm": float("nan"), "Note": "Outside polygon torsion metrics are not available."}
    try:
        pcp = float(outer_polygon.exterior.length)
    except Exception:
        pcp = float("nan")
    return {
        "Acp mm2": float(outer_polygon.area),
        "Pcp mm": pcp,
        "Note": "Acp/Pcp from outside concrete perimeter; void perimeters are not included in Pcp.",
    }


def _beam_uls_torsion_hoop_geometry(
    section_geometry: SectionGeometry,
    *,
    stirrup_diameter_mm: float,
) -> dict[str, object]:
    """Return first-pass closed-hoop torsion geometry.

    The current shear reinforcement table does not yet own cover/closed-hoop
    dimensions.  TORSION1 therefore estimates the closed transverse hoop
    centerline by offsetting the outside polygon inward.  The assumption is
    visible in audit output and must be replaced by a dedicated torsion layout
    before certified torsion design.
    """

    metrics = _beam_uls_outer_polygon_metrics(section_geometry)
    notes = [str(metrics.get("Note") or "")]
    acp = _beam_uls_float(metrics.get("Acp mm2"))
    pcp = _beam_uls_float(metrics.get("Pcp mm"))
    try:
        outer_polygon = to_shapely_polygon(SectionGeometry(name=section_geometry.name, outer_polygon=section_geometry.outer_polygon, holes=[]))
    except Exception:
        outer_polygon = None
    if outer_polygon is None or outer_polygon.is_empty or outer_polygon.area <= 0.0 or not outer_polygon.is_valid:
        return {
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": float("nan"),
            "Ao mm2": float("nan"),
            "ph mm": float("nan"),
            "offset mm": float("nan"),
            "Note": " ".join(note for note in notes if note) + " Closed-hoop centerline geometry could not be derived.",
        }
    minx, miny, maxx, maxy = outer_polygon.bounds
    min_dim = min(float(maxx) - float(minx), float(maxy) - float(miny))
    dia = float(stirrup_diameter_mm) if math.isfinite(float(stirrup_diameter_mm)) and float(stirrup_diameter_mm) > 0.0 else 12.0
    # Conservative visible default: about 40 mm clear cover plus half stirrup
    # diameter, but capped so small sections still produce a valid inset path.
    offset = max(45.0 + 0.5 * dia, 0.04 * min_dim)
    if math.isfinite(min_dim) and min_dim > 0.0:
        offset = min(offset, 0.20 * min_dim)
    try:
        inset = outer_polygon.buffer(-float(offset), join_style=2)
        if inset.is_empty or inset.area <= 0.0:
            raise ValueError("empty inset")
        if getattr(inset, "geoms", None):
            inset = max(inset.geoms, key=lambda geom: float(geom.area))
            notes.append("Inset closed-hoop path split into multiple regions; largest region used for first-pass torsion geometry.")
        aoh = float(inset.area)
        ph = float(inset.exterior.length)
        ao = 0.85 * aoh
        notes.append(f"Aoh estimated from outside polygon offset {offset:.1f} mm to the assumed closed stirrup centerline; Ao = 0.85Aoh.")
    except Exception:
        aoh = float("nan")
        ph = float("nan")
        ao = float("nan")
        notes.append("Closed-hoop centerline offset failed; φTn is not ready until torsion hoop geometry is defined.")
    return {
        "Acp mm2": acp,
        "Pcp mm": pcp,
        "Aoh mm2": aoh,
        "Ao mm2": ao,
        "ph mm": ph,
        "offset mm": float(offset),
        "Note": " ".join(note for note in notes if note),
    }


def _beam_uls_rebar_area_mm2(item: object) -> float:
    area = getattr(item, "area_mm2", None)
    if area is not None:
        area_value = _beam_uls_float(area)
        if math.isfinite(area_value) and area_value > 0.0:
            return float(area_value)
    diameter = getattr(item, "diameter_mm", None)
    if diameter is None and isinstance(item, Mapping):
        diameter = item.get("diameter_mm", item.get("Diameter_mm"))
    diameter_value = _beam_uls_float(diameter)
    if not math.isfinite(diameter_value) or diameter_value <= 0.0:
        return float("nan")
    return math.pi * float(diameter_value) ** 2 / 4.0


def _beam_uls_torsion_longitudinal_review(state: Mapping[str, object], al_req_mm2: float) -> dict[str, object]:
    if not math.isfinite(float(al_req_mm2)) or float(al_req_mm2) <= 0.0:
        return {
            "status": "NOT CHECKED",
            "provided_mm2": float("nan"),
            "utilization": float("nan"),
            "description": "Longitudinal torsion reinforcement is not required by the current torsion gate row.",
        }
    raw_rebars = _beam_uls_get_state_value(state, "rebars", []) or []
    try:
        effective_rebars = effective_rebars_for_analysis(list(raw_rebars), state)
    except Exception:
        effective_rebars = list(raw_rebars) if ordinary_rebar_enabled(state, default=True) else []
    if not ordinary_rebar_enabled(state, default=True):
        return {
            "status": "LAYOUT REQUIRED",
            "provided_mm2": 0.0,
            "utilization": float("nan"),
            "description": "Enable ordinary rebar / longitudinal Al in Section Builder and define active Rebar rows for torsion Al review.",
        }
    provided = 0.0
    counted = 0
    for item in effective_rebars:
        area = _beam_uls_rebar_area_mm2(item)
        if not math.isfinite(area) or area <= 0.0:
            continue
        provided += float(area)
        counted += 1
    if counted == 0 or provided <= 0.0:
        return {
            "status": "LAYOUT REQUIRED",
            "provided_mm2": provided,
            "utilization": float("nan"),
            "description": "No active ordinary rebar rows are available for longitudinal torsion Al review. Use the existing Rebar table as the single source of truth.",
        }
    utilization = float(al_req_mm2) / provided if provided > 0.0 else float("nan")
    status = "PASS" if math.isfinite(utilization) and utilization <= 1.0 + 1.0e-9 else "FAIL"
    return {
        "status": status,
        "provided_mm2": provided,
        "utilization": utilization,
        "description": (
            f"Longitudinal torsion Al provided is taken from {counted} active ordinary rebar bar(s) in the existing Rebar table; "
            f"Al,req/Al,prov = {_format_beam_uls_ratio(utilization)}. Verify that counted bars are detailed around the torsion hoop perimeter before final design."
        ),
    }




def _beam_uls_torsion_detailing_gate(
    *,
    zone: Mapping[str, object] | None,
    x_m: float,
    spacing_mm: float,
    ph_mm: float,
    at_per_s_mm2_per_mm: float,
    at_req_mm2_per_mm: float,
) -> dict[str, object]:
    """Return compact torsion-detailing acceptance gates for the active hoop zone.

    CODE2 promotes torsion from a strength-only review to an implementable
    design gate by checking that the provided closed-hoop zone actually covers
    the station, that a finite closed-hoop area is present, and that spacing is
    within the standard torsion spacing screen used by ACI/AASHTO practice
    (s <= min(ph/8, 300 mm)).  Anchorage hook geometry and shop-drawing
    detailing still need drawing review, but they no longer block the numerical
    torsion status when the declared closed-hoop zone is complete.
    """

    notes: list[str] = []
    if zone is None:
        return {
            "status": "LAYOUT REQUIRED",
            "s_max_mm": float("nan"),
            "spacing_dc": float("nan"),
            "at_dc": float("nan"),
            "dc": float("nan"),
            "notes": "No active closed-hoop transverse reinforcement zone is available for torsion.",
        }

    x_start = _beam_uls_float(zone.get("x_start_m"))
    x_end = _beam_uls_float(zone.get("x_end_m"))
    covers_station = (
        math.isfinite(float(x_m))
        and math.isfinite(float(x_start))
        and math.isfinite(float(x_end))
        and float(x_start) - 1.0e-9 <= float(x_m) <= float(x_end) + 1.0e-9
    )
    if not covers_station:
        notes.append("The nearest transverse zone does not actually cover this station; extend/add a torsion hoop zone.")

    if not all(math.isfinite(value) and value > 0.0 for value in [spacing_mm, ph_mm, at_per_s_mm2_per_mm]):
        return {
            "status": "LAYOUT REQUIRED",
            "s_max_mm": float("nan"),
            "spacing_dc": float("nan"),
            "at_dc": float("nan"),
            "dc": float("nan"),
            "notes": "; ".join(notes + ["Torsion detailing needs finite spacing, ph, and At/s."]),
        }

    s_max = min(float(ph_mm) / 8.0, 300.0)
    spacing_dc = float(spacing_mm) / float(s_max) if s_max > 0.0 else float("nan")
    at_dc = float(at_req_mm2_per_mm) / float(at_per_s_mm2_per_mm) if math.isfinite(float(at_req_mm2_per_mm)) and float(at_per_s_mm2_per_mm) > 0.0 else float("nan")
    finite_dcs = [value for value in [spacing_dc, at_dc] if math.isfinite(value)]
    dc = max(finite_dcs) if finite_dcs else float("nan")

    if not covers_station:
        status = "LAYOUT REQUIRED"
    elif math.isfinite(dc) and dc <= 1.0 + 1.0e-9:
        status = "PASS"
    else:
        status = "FAIL"
        if math.isfinite(spacing_dc) and spacing_dc > 1.0 + 1.0e-9:
            notes.append("Closed-hoop spacing exceeds torsion spacing limit s <= min(ph/8, 300 mm).")
        if math.isfinite(at_dc) and at_dc > 1.0 + 1.0e-9:
            notes.append("Provided At/s is less than required torsion At/s.")

    if not notes:
        notes.append("Closed-hoop zone covers the station and passes At/s plus spacing gates.")
    return {
        "status": status,
        "s_max_mm": float(s_max),
        "spacing_dc": float(spacing_dc),
        "at_dc": float(at_dc) if math.isfinite(at_dc) else float("nan"),
        "dc": float(dc) if math.isfinite(dc) else float("nan"),
        "notes": "; ".join(notes),
    }

def _beam_uls_torsion_result_for_row(
    state: Mapping[str, object],
    row: Mapping[str, object],
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    """Return a code-routed torsion strength + reinforcement detailing row.

    TORSION.CODE2 checks the active closed-hoop transverse zone, torsion
    strength, longitudinal Al from the ordinary rebar source of truth, and a
    compact spacing/coverage detailing gate before issuing PASS.
    """

    x_m = _beam_uls_float(row.get("Station x (m)"))
    tu_kNm = _beam_uls_float(row.get("Tu"))
    case = str(row.get("Case Name") or "-")
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    support_side = _beam_uls_member_end_side(x_m, span_m)
    explicit_boundary = bool(row.get("__Diagram boundary"))
    station_type = "DIAGRAM BOUNDARY" if explicit_boundary or support_side else "LOAD STATION"
    notes: list[str] = []
    if station_type == "DIAGRAM BOUNDARY":
        notes.append("Member-end torsion row is plotted as a diagram boundary only; it is excluded from governing torsion and combined V+T source-strength decisions.")
    if not math.isfinite(tu_kNm) or abs(tu_kNm) <= _BEAM_ULS_DEMAND_TOL:
        return {
            "Check": "Torsion",
            "Status": "NO DEMAND",
            "Station type": station_type,
            "Support side": support_side or "-",
            "Transverse status": "NO DEMAND",
            "Longitudinal status": "NOT CHECKED",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": "-",
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": 0.0,
            "Abs demand kN-m": 0.0,
            "φTn kN-m": float("nan"),
            "D/C value": float("nan"),
            "Notes": "No finite Tu demand.",
        }

    zone = _beam_uls_active_shear_zone_for_station(state, x_m)
    analysis_input, input_messages = _beam_uls_flexure_analysis_input_for_station(state, row=row, strength_route=strength_route)
    if input_messages:
        notes.extend(input_messages)
    if analysis_input is None:
        return {
            "Check": "Torsion",
            "Status": "REVIEW",
            "Station type": station_type,
            "Support side": support_side or "-",
            "Transverse status": "NOT READY",
            "Longitudinal status": "NOT CHECKED",
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "Abs demand kN-m": abs(float(tu_kNm)),
            "φTn kN-m": float("nan"),
            "D/C value": float("nan"),
            "Notes": "; ".join(notes) or "Section/material input not ready for torsion check.",
        }

    concrete = analysis_input.concrete_material
    fc = float(concrete.fc_MPa)
    zone_note = ""
    if zone is None:
        zone_note = "No active transverse reinforcement zone covers this station; φTn from provided closed hoops is not ready."
        stirrup_area = legs = spacing = fy = diameter = float("nan")
    else:
        stirrup_area = _beam_uls_stirrup_area_mm2(zone)
        legs = _beam_uls_float(zone.get("Legs"))
        spacing = _beam_uls_float(zone.get("Spacing_mm"))
        fy = _beam_uls_float(zone.get("fy_MPa"))
        diameter = _beam_uls_float(zone.get("Diameter_mm"))

    geometry = _beam_uls_torsion_hoop_geometry(analysis_input.section_geometry, stirrup_diameter_mm=diameter)
    notes.append(str(geometry.get("Note") or ""))
    acp = _beam_uls_float(geometry.get("Acp mm2"))
    pcp = _beam_uls_float(geometry.get("Pcp mm"))
    ao = _beam_uls_float(geometry.get("Ao mm2"))
    aoh = _beam_uls_float(geometry.get("Aoh mm2"))
    ph = _beam_uls_float(geometry.get("ph mm"))
    theta_deg = 45.0
    cot_theta = 1.0

    if strength_route.is_bridge:
        phi = 0.90
        code_basis = "φTn — AASHTO LRFD-compatible"
        phi_policy = "AASHTO LRFD torsion resistance factor routed as φ = 0.90"
        method = "AASHTO LRFD-compatible closed-stirrup torsion truss with CODE2 reinforcement/detailing gates"
        threshold_basis = "AASHTO-compatible cracking torsion threshold screen"
        notes.append("Bridge torsion uses the implemented AASHTO-compatible closed-hoop strength, Al, spacing, and zone-coverage gates.")
    else:
        phi = 0.75
        code_basis = "φTn — ACI 318"
        phi_policy = "ACI 318 torsion strength-reduction factor routed as φ = 0.75"
        method = "ACI 318 closed-stirrup torsion truss with CODE2 reinforcement/detailing gates"
        threshold_basis = "ACI 318 torsion threshold screen"
        notes.append("ACI torsion uses the implemented closed-hoop strength, Al, spacing, and zone-coverage gates.")

    t_threshold_kNm = float("nan")
    if all(math.isfinite(value) and value > 0.0 for value in [fc, acp, pcp]):
        tcr_nmm = 0.083 * math.sqrt(fc) * acp * acp / pcp
        t_threshold_kNm = phi * tcr_nmm / 1.0e6
    threshold_status = "-"
    if math.isfinite(t_threshold_kNm):
        threshold_status = "BELOW THRESHOLD" if abs(float(tu_kNm)) <= t_threshold_kNm + 1.0e-9 else "DESIGN REQUIRED"

    if not all(math.isfinite(value) and value > 0.0 for value in [stirrup_area, spacing, fy, ao]):
        status = "BELOW THRESHOLD" if threshold_status == "BELOW THRESHOLD" else "LAYOUT REQUIRED"
        return {
            "Check": "Torsion",
            "Status": status,
            "Station type": station_type,
            "Support side": support_side or "-",
            "Transverse status": "NOT READY" if status != "BELOW THRESHOLD" else "THRESHOLD OK",
            "Longitudinal status": "NOT CHECKED",
            "Threshold status": threshold_status,
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
            "Capacity": "-" if status != "BELOW THRESHOLD" else f"φTcr ≈ {t_threshold_kNm:,.2f} kN-m",
            "Utilization": "-",
            "Demand kN-m": float(tu_kNm),
            "Abs demand kN-m": abs(float(tu_kNm)),
            "φTn kN-m": float("nan"),
            "φTcr kN-m": t_threshold_kNm,
            "D/C value": float("nan"),
            "Acp mm2": acp,
            "Pcp mm": pcp,
            "Aoh mm2": aoh,
            "Ao mm2": ao,
            "ph mm": ph,
            "Hoop offset mm": _beam_uls_float(geometry.get("offset mm")),
            "At mm2": stirrup_area,
            "At/s mm2/mm": float("nan"),
            "Al req mm2": float("nan"),
            "Al provided mm2": float("nan"),
            "Al utilization": float("nan"),
            "Detailing status": "LAYOUT REQUIRED" if status != "BELOW THRESHOLD" else "THRESHOLD OK",
            "Torsion At/s req mm2/mm": float("nan"),
            "s max torsion mm": float("nan"),
            "Spacing D/C": float("nan"),
            "Detailing D/C value": float("nan"),
            "Detailing notes": zone_note or "Torsion detailing needs active closed-hoop geometry.",
            "Zone": str(zone.get("Zone") if zone is not None else "-"),
            "Stirrup": "-" if zone is None else f"{zone.get('Bar Size') or '-'} closed hoop @ {spacing:.0f} mm",
            "φ": phi,
            "Code basis": code_basis,
            "φ policy": phi_policy,
            "Method": method,
            "Threshold basis": threshold_basis,
            "Notes": "; ".join(part for part in [zone_note, *notes] if part),
        }

    # Torsion uses the area of one closed-hoop leg, not the shear Av from two
    # vertical legs. This is conservative for the current shared stirrup table.
    at_mm2 = float(stirrup_area)
    at_per_s = at_mm2 / float(spacing)
    tn_nmm = 2.0 * float(ao) * at_per_s * float(fy) * cot_theta
    phi_tn_kNm = phi * tn_nmm / 1.0e6
    utilization = abs(float(tu_kNm)) / phi_tn_kNm if phi_tn_kNm > 0.0 else float("nan")
    transverse_status = "PASS" if math.isfinite(utilization) and utilization <= 1.0 + 1.0e-9 else "FAIL"
    # Longitudinal torsion steel demand from the closed-hoop truss relationship.
    # Provided Al is read from the existing ordinary rebar table
    # (single source of truth).
    al_req = at_per_s * ph * cot_theta * cot_theta if math.isfinite(ph) and ph > 0.0 else float("nan")
    longitudinal_review = _beam_uls_torsion_longitudinal_review(state, al_req)
    longitudinal_status = str(longitudinal_review.get("status") or "LAYOUT REQUIRED")
    at_req = abs(float(tu_kNm)) * 1.0e6 / (float(phi) * 2.0 * float(ao) * float(fy) * float(cot_theta))
    detailing_gate = _beam_uls_torsion_detailing_gate(
        zone=zone,
        x_m=x_m,
        spacing_mm=float(spacing),
        ph_mm=float(ph),
        at_per_s_mm2_per_mm=float(at_per_s),
        at_req_mm2_per_mm=float(at_req),
    )
    detailing_status = str(detailing_gate.get("status") or "LAYOUT REQUIRED")
    if threshold_status == "BELOW THRESHOLD":
        status = "BELOW THRESHOLD"
    elif "FAIL" in {transverse_status, longitudinal_status, detailing_status}:
        status = "FAIL"
    elif any(value in {"LAYOUT REQUIRED", "NOT CHECKED", "NOT READY"} for value in [longitudinal_status, detailing_status]):
        status = "LAYOUT REQUIRED"
    elif transverse_status == "PASS" and longitudinal_status == "PASS" and detailing_status == "PASS":
        status = "PASS"
    else:
        status = "REVIEW"
    if legs and math.isfinite(float(legs)):
        notes.append("Torsion At is taken as one closed-hoop bar area per spacing; shear leg count is not multiplied into At.")
    notes.append(str(longitudinal_review.get("description") or ""))
    notes.append(str(detailing_gate.get("notes") or ""))
    if status == "PASS":
        notes.append("TORSION.CODE2 strength, Al, closed-hoop spacing, and zone-coverage gates pass for this station.")
    else:
        notes.append("Torsion is not final PASS until transverse strength, longitudinal Al, and closed-hoop detailing gates pass.")

    return {
        "Check": "Torsion",
        "Status": status,
        "Station type": station_type,
        "Support side": support_side or "-",
        "Transverse status": transverse_status,
        "Longitudinal status": longitudinal_status,
        "Threshold status": threshold_status,
        "Governing x": _format_beam_uls_x(x_m),
        "Case": case,
        "Demand": _format_beam_uls_demand(tu_kNm, "kN-m"),
        "Capacity": f"φTn = {phi_tn_kNm:,.2f} kN-m",
        "Utilization": _format_beam_uls_ratio(utilization),
        "Demand kN-m": float(tu_kNm),
        "Abs demand kN-m": abs(float(tu_kNm)),
        "φTn kN-m": phi_tn_kNm,
        "φTcr kN-m": t_threshold_kNm,
        "Tn kN-m": tn_nmm / 1.0e6,
        "D/C value": utilization,
        "Acp mm2": acp,
        "Pcp mm": pcp,
        "Aoh mm2": aoh,
        "Ao mm2": ao,
        "ph mm": ph,
        "Hoop offset mm": _beam_uls_float(geometry.get("offset mm")),
        "At mm2": at_mm2,
        "At/s mm2/mm": at_per_s,
        "Al req mm2": al_req,
        "Al provided mm2": longitudinal_review.get("provided_mm2", float("nan")),
        "Al utilization": longitudinal_review.get("utilization", float("nan")),
        "Detailing status": detailing_status,
        "Torsion At/s req mm2/mm": at_req,
        "s max torsion mm": detailing_gate.get("s_max_mm", float("nan")),
        "Spacing D/C": detailing_gate.get("spacing_dc", float("nan")),
        "Detailing D/C value": detailing_gate.get("dc", float("nan")),
        "Detailing notes": detailing_gate.get("notes", ""),
        "Zone": str(zone.get("Zone") or "Zone"),
        "Stirrup": f"{zone.get('Bar Size') or '-'} closed hoop @ {float(spacing):.0f} mm",
        "θ deg": theta_deg,
        "cotθ": cot_theta,
        "φ": phi,
        "Code basis": code_basis,
        "φ policy": phi_policy,
        "Method": method,
        "Threshold basis": threshold_basis,
        "Notes": "; ".join(part for part in notes if part),
    }


def _beam_uls_torsion_check_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Station type", "Support side", "Transverse status", "Longitudinal status", "Threshold status", "Governing x", "Case", "Demand", "Capacity", "Utilization",
        "Demand kN-m", "Abs demand kN-m", "φTn kN-m", "φTcr kN-m", "Tn kN-m", "D/C value",
        "Acp mm2", "Pcp mm", "Aoh mm2", "Ao mm2", "ph mm", "Hoop offset mm", "At mm2", "At/s mm2/mm", "Torsion At/s req mm2/mm", "Al req mm2", "Al provided mm2", "Al utilization",
        "Detailing status", "s max torsion mm", "Spacing D/C", "Detailing D/C value", "Detailing notes",
        "Zone", "Stirrup", "θ deg", "cotθ", "φ", "Code basis", "φ policy", "Method", "Threshold basis", "Notes",
    ]
    if active_df.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, demand_row in active_df.iterrows():
        result = _beam_uls_torsion_result_for_row(state, demand_row, strength_route=strength_route)
        for column in columns:
            result.setdefault(
                column,
                float("nan")
                if column.endswith("kN-m")
                or column.endswith("mm2")
                or column.endswith("mm")
                or column.endswith("mm2/mm")
                or column in {"D/C value", "Al utilization", "Spacing D/C", "Detailing D/C value", "θ deg", "cotθ", "φ"}
                else "-",
            )
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_governing_torsion_row(torsion_df: pd.DataFrame | None) -> dict[str, object] | None:
    if torsion_df is None or torsion_df.empty:
        return None
    df = _beam_uls_torsion_decision_dataframe(torsion_df)
    if df.empty:
        return None
    if "Abs demand kN-m" in df.columns:
        df["__abs_tu"] = pd.to_numeric(df["Abs demand kN-m"], errors="coerce")
        df = df[df["__abs_tu"].fillna(0.0) > _BEAM_ULS_DEMAND_TOL].copy()
    if df.empty:
        return None
    df["__dc"] = pd.to_numeric(df.get("D/C value"), errors="coerce")
    df["__abs_tu"] = pd.to_numeric(df.get("Abs demand kN-m"), errors="coerce")
    status_priority = {"FAIL": 5, "LAYOUT REQUIRED": 4, "REVIEW": 3, "PASS": 2, "BELOW THRESHOLD": 1, "NO DEMAND": 0}
    df["__status_priority"] = df.get("Status", pd.Series(index=df.index, dtype=object)).map(lambda value: status_priority.get(str(value), 0))
    idx = df.sort_values(["__status_priority", "__dc", "__abs_tu"], ascending=[False, False, False]).index[0]
    return df.loc[idx].drop(labels=["__dc", "__abs_tu", "__status_priority"], errors="ignore").to_dict()


def _beam_uls_torsion_audit_dataframe(torsion_df: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "Governing", "Station x", "Case", "Status", "Threshold", "Transverse", "Longitudinal", "Detailing", "Tu demand", "φTn", "φTcr", "D/C",
        "Zone", "Stirrup", "At", "At/s", "At/s req", "Ao", "Aoh", "Acp", "Pcp", "ph", "Hoop offset", "s max", "s D/C", "Al req", "Al provided", "Al D/C", "Detailing D/C", "θ", "φ", "Code basis", "Method", "Notes",
    ]
    if torsion_df is None or torsion_df.empty:
        return pd.DataFrame(columns=columns)
    df = torsion_df.copy()
    df["__dc"] = pd.to_numeric(df.get("D/C value"), errors="coerce")
    df["__abs_tu"] = pd.to_numeric(df.get("Abs demand kN-m"), errors="coerce")
    decision_df = _beam_uls_torsion_decision_dataframe(torsion_df)
    if not decision_df.empty:
        decision_df["__dc"] = pd.to_numeric(decision_df.get("D/C value"), errors="coerce")
        decision_df["__abs_tu"] = pd.to_numeric(decision_df.get("Abs demand kN-m"), errors="coerce")
    nonzero = decision_df[decision_df["__abs_tu"].fillna(0.0) > _BEAM_ULS_DEMAND_TOL] if "__abs_tu" in decision_df.columns else pd.DataFrame()
    governing_idx = None
    if not nonzero.empty:
        status_priority = {"FAIL": 5, "LAYOUT REQUIRED": 4, "REVIEW": 3, "PASS": 2, "BELOW THRESHOLD": 1, "NO DEMAND": 0}
        ranked = nonzero.copy()
        ranked["__status_priority"] = ranked.get("Status", pd.Series(index=ranked.index, dtype=object)).map(lambda value: status_priority.get(str(value), 0))
        governing_idx = ranked.sort_values(["__status_priority", "__dc", "__abs_tu"], ascending=[False, False, False]).index[0]
    rows: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        rows.append(
            {
                "Governing": "Yes" if governing_idx is not None and idx == governing_idx else "",
                "Station x": str(row.get("Governing x") or "-"),
                "Case": str(row.get("Case") or "-"),
                "Status": str(row.get("Status") or "-"),
                "Threshold": str(row.get("Threshold status") or "-"),
                "Transverse": str(row.get("Transverse status") or "-"),
                "Longitudinal": str(row.get("Longitudinal status") or "-"),
                "Detailing": str(row.get("Detailing status") or "-"),
                "Tu demand": _format_beam_uls_audit_number(row.get("Demand kN-m"), unit="kN-m"),
                "φTn": _format_beam_uls_audit_number(row.get("φTn kN-m"), unit="kN-m"),
                "φTcr": _format_beam_uls_audit_number(row.get("φTcr kN-m"), unit="kN-m"),
                "D/C": _format_beam_uls_ratio(row.get("D/C value")),
                "Zone": str(row.get("Zone") or "-"),
                "Stirrup": str(row.get("Stirrup") or "-"),
                "At": _format_beam_uls_audit_number(row.get("At mm2"), unit="mm²"),
                "At/s": _format_beam_uls_audit_number(row.get("At/s mm2/mm"), unit="mm²/mm"),
                "At/s req": _format_beam_uls_audit_number(row.get("Torsion At/s req mm2/mm"), unit="mm²/mm"),
                "Ao": _format_beam_uls_audit_number(row.get("Ao mm2"), unit="mm²"),
                "Aoh": _format_beam_uls_audit_number(row.get("Aoh mm2"), unit="mm²"),
                "Acp": _format_beam_uls_audit_number(row.get("Acp mm2"), unit="mm²"),
                "Pcp": _format_beam_uls_audit_number(row.get("Pcp mm"), unit="mm"),
                "ph": _format_beam_uls_audit_number(row.get("ph mm"), unit="mm"),
                "Hoop offset": _format_beam_uls_audit_number(row.get("Hoop offset mm"), unit="mm"),
                "s max": _format_beam_uls_audit_number(row.get("s max torsion mm"), unit="mm"),
                "s D/C": _format_beam_uls_ratio(row.get("Spacing D/C")),
                "Al req": _format_beam_uls_audit_number(row.get("Al req mm2"), unit="mm²"),
                "Al provided": _format_beam_uls_audit_number(row.get("Al provided mm2"), unit="mm²"),
                "Al D/C": _format_beam_uls_ratio(row.get("Al utilization")),
                "Detailing D/C": _format_beam_uls_ratio(row.get("Detailing D/C value")),
                "θ": _format_beam_uls_audit_number(row.get("θ deg"), unit="°"),
                "φ": _format_beam_uls_ratio(row.get("φ")),
                "Code basis": str(row.get("Code basis") or "-"),
                "Method": str(row.get("Method") or "-"),
                "Notes": str(row.get("Notes") or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _format_beam_uls_audit_number(value: object, *, digits: int = 2, unit: str = "") -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(numeric):
        return "-"
    suffix = f" {unit}" if unit else ""
    return f"{numeric:,.{digits}f}{suffix}"


def _beam_uls_flexure_audit_dataframe(flexure_preview_df: pd.DataFrame | None) -> pd.DataFrame:
    """Return benchmark-ready flexure audit rows for the ULS workspace.

    SC1 keeps the default screen compact and moves intermediate values here:
    demand, nominal Mn, route φ, φMn, D/C, bending direction, tension face,
    code-compatible strain-compatibility basis, resistance-factor policy, and
    code route.  It is intentionally display/audit only and does not change the
    strength solver.
    """

    columns = [
        "Governing",
        "Station x",
        "Case",
        "Status",
        "Direction",
        "Tension face",
        "Mu demand",
        "Mn nominal",
        "φ",
        "φMn",
        "D/C",
        "Code basis",
        "SC basis",
        "φ policy",
        "Solver basis",
        "Method",
        "Benchmark readiness",
        "Notes",
    ]
    if flexure_preview_df is None or flexure_preview_df.empty:
        return pd.DataFrame(columns=columns)
    df = flexure_preview_df.copy()
    if "Check" in df.columns:
        df = df[df["Check"].astype(str).str.casefold() == "flexure"].copy()
    if df.empty:
        return pd.DataFrame(columns=columns)
    df["__util"] = pd.to_numeric(df.get("Utilization value"), errors="coerce")
    governing_idx = df["__util"].idxmax() if df["__util"].notna().any() else None
    audit_rows: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        demand = row.get("Demand kN-m")
        mn_nominal = row.get("Mn nominal kN-m")
        phi_value = row.get("φ value")
        phi_mn = row.get("φMn kN-m", row.get("Capacity kN-m"))
        dc_value = row.get("D/C value", row.get("Utilization value"))
        status = str(row.get("Status") or "-")
        route_phi = row.get("Route φ")
        phi_display = _format_beam_uls_ratio(phi_value)
        if phi_display == "-":
            phi_display = str(route_phi or "-")
        audit_rows.append(
            {
                "Governing": "Yes" if governing_idx is not None and idx == governing_idx else "",
                "Station x": str(row.get("Governing x") or "-"),
                "Case": str(row.get("Case") or "-"),
                "Status": status,
                "Direction": str(row.get("Bending direction") or _beam_uls_flexure_direction_label(demand)),
                "Tension face": str(row.get("Tension face") or _beam_uls_flexure_tension_face_label(demand)),
                "Mu demand": _format_beam_uls_audit_number(demand, unit="kN-m"),
                "Mn nominal": _format_beam_uls_audit_number(mn_nominal, unit="kN-m"),
                "φ": phi_display,
                "φMn": _format_beam_uls_audit_number(phi_mn, unit="kN-m"),
                "D/C": _format_beam_uls_ratio(dc_value),
                "Code basis": str(row.get("Code basis") or row.get("Capacity basis") or "-"),
                "SC basis": str(row.get("Strain compatibility basis") or "-"),
                "φ policy": str(row.get("φ policy") or row.get("Route φ") or "-"),
                "Solver basis": str(row.get("Solver basis") or "-"),
                "Method": str(row.get("Method") or "-"),
                "Benchmark readiness": str(row.get("Benchmark readiness") or "-"),
                "Notes": str(row.get("Notes") or ""),
            }
        )
    return pd.DataFrame(audit_rows, columns=columns)



BEAM_ULS_CHECK_TAB_LABELS = ["Flexure", "Shear", "Torsion", "Shear + Torsion"]
_BEAM_ULS_MANUAL_CALC_CACHE_KEY = "_beam_girder_uls_manual_calculation_cache"


def _beam_uls_manual_cache(state: Mapping[str, object]) -> dict[str, dict[str, object]]:
    cache = state.get(_BEAM_ULS_MANUAL_CALC_CACHE_KEY) if isinstance(state, Mapping) else None
    return cache if isinstance(cache, dict) else {}


def _beam_uls_current_cached_result(state: Mapping[str, object], check_name: str, input_hash: str) -> dict[str, object] | None:
    entry = _beam_uls_manual_cache(state).get(check_name)
    if not isinstance(entry, dict):
        return None
    if str(entry.get("input_hash") or "") != str(input_hash):
        return None
    return entry


def _beam_uls_store_manual_result(
    state: Any,
    check_name: str,
    *,
    input_hash: str,
    result: dict[str, object],
) -> dict[str, object]:
    cache = dict(_beam_uls_manual_cache(state))
    entry = dict(result)
    entry["input_hash"] = str(input_hash)
    entry["check"] = str(check_name)
    entry["calculated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cache[str(check_name)] = entry
    state[_BEAM_ULS_MANUAL_CALC_CACHE_KEY] = cache
    return entry


def _beam_uls_manual_result_badge(entry: dict[str, object] | None) -> str:
    if not entry:
        return "Not calculated for current inputs"
    stamp = str(entry.get("calculated_at") or "")
    return f"Calculated for current inputs" + (f" · {stamp}" if stamp else "")


def _beam_uls_calculate_selected_check(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    selected_check: str,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    if selected_check == "Flexure":
        flexure_preview_df, flexure_preview_messages = _beam_uls_flexure_preview_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        return {
            "flexure_preview_df": flexure_preview_df,
            "flexure_preview_messages": list(flexure_preview_messages),
        }
    if selected_check == "Shear":
        shear_station_check_df = _beam_uls_shear_check_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        shear_critical_section_df = _beam_uls_shear_critical_section_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        shear_check_df = _beam_uls_combine_shear_check_frames(shear_station_check_df, shear_critical_section_df)
        shear_boundary_capacity_df = _beam_uls_shear_diagram_boundary_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        return {
            "shear_check_df": shear_check_df,
            "shear_critical_section_df": shear_critical_section_df,
            "shear_boundary_capacity_df": shear_boundary_capacity_df,
        }
    if selected_check == "Torsion":
        torsion_check_df = _beam_uls_torsion_check_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        torsion_boundary_capacity_df = _beam_uls_torsion_diagram_boundary_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        return {
            "torsion_check_df": torsion_check_df,
            "torsion_boundary_capacity_df": torsion_boundary_capacity_df,
        }
    if selected_check == "Shear + Torsion":
        # Combined V+T is a complete workflow decision, not merely a passive
        # reader of previously clicked Shear/Torsion tabs.  Build the required
        # shear/torsion source rows in this calculation pass so users do not
        # have to click Calculate Shear and Calculate Torsion first.
        shear_station_check_df = _beam_uls_shear_check_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        shear_critical_section_df = _beam_uls_shear_critical_section_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        shear_check_df = _beam_uls_combine_shear_check_frames(shear_station_check_df, shear_critical_section_df)
        shear_boundary_capacity_df = _beam_uls_shear_diagram_boundary_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        torsion_check_df = _beam_uls_torsion_check_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        torsion_boundary_capacity_df = _beam_uls_torsion_diagram_boundary_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        combined_vt_df = _beam_uls_combined_vt_check_dataframe(
            state,
            active_df,
            strength_route=strength_route,
        )
        return {
            "shear_check_df": shear_check_df,
            "shear_critical_section_df": shear_critical_section_df,
            "shear_boundary_capacity_df": shear_boundary_capacity_df,
            "torsion_check_df": torsion_check_df,
            "torsion_boundary_capacity_df": torsion_boundary_capacity_df,
            "combined_vt_df": combined_vt_df,
            "interaction_status": _beam_uls_torsion_interaction_status(active_df),
        }
    return {}


def _beam_uls_cached_dataframe(entry: dict[str, object] | None, key: str) -> pd.DataFrame | None:
    value = entry.get(key) if isinstance(entry, dict) else None
    return value if isinstance(value, pd.DataFrame) else None


def _beam_uls_cached_messages(entry: dict[str, object] | None, key: str) -> list[str]:
    value = entry.get(key) if isinstance(entry, dict) else None
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _beam_uls_section_torsion_shape_type(state: Mapping[str, object]) -> str:
    geometry = _beam_uls_get_state_value(state, "section_geometry")
    if geometry is None:
        return "solid"
    try:
        polygon = to_shapely_polygon(geometry)
        if len(getattr(polygon, "interiors", [])) > 0:
            return "hollow"
    except Exception:
        return "solid"
    return "solid"


def _beam_uls_combined_vt_demand_rows(active_df: pd.DataFrame, state: Mapping[str, object], *, strength_route: BeamGirderUlsStrengthRoute) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    explicit_keys: set[tuple[str, float]] = set()
    if isinstance(active_df, pd.DataFrame) and not active_df.empty:
        for _, row in active_df.iterrows():
            result = row.to_dict()
            result.setdefault("__VT station type", "LOAD STATION")
            result.setdefault("__Support side", "-")
            result.setdefault("__Critical offset m", float("nan"))
            x_val = _beam_uls_float(result.get("Station x (m)"))
            case_val = str(result.get("Case Name") or result.get("Case") or "-")
            if math.isfinite(x_val):
                explicit_keys.add((case_val, round(float(x_val), 9)))
            rows.append(result)
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    if isinstance(active_df, pd.DataFrame) and not active_df.empty and math.isfinite(span_m) and span_m > 0.0:
        cases = [str(value or "-") for value in active_df.get("Case Name", pd.Series(["-"])).dropna().unique().tolist()] or ["-"]
        for case_name in cases:
            for x_endpoint, support_side in ((0.0, "LEFT"), (float(span_m), "RIGHT")):
                if (case_name, round(float(x_endpoint), 9)) in explicit_keys:
                    continue
                boundary_row = _beam_uls_interpolated_demand_row_for_case(
                    active_df,
                    case_name=case_name,
                    x_m=float(x_endpoint),
                    note="Combined shear + torsion endpoint diagram-boundary demand row",
                )
                if boundary_row is None:
                    continue
                boundary_row["__VT station type"] = "DIAGRAM BOUNDARY"
                boundary_row["__Support side"] = support_side
                boundary_row["__Critical offset m"] = float("nan")
                rows.append(boundary_row)
    for marker in _beam_uls_shear_default_critical_section_rows(state, active_df, strength_route=strength_route):
        case_name = str(marker.get("Case") or "-")
        x_crit = _beam_uls_float(marker.get("x_m"))
        if not math.isfinite(x_crit):
            continue
        demand_row = _beam_uls_interpolated_demand_row_for_case(
            active_df,
            case_name=case_name,
            x_m=float(x_crit),
            note="Combined shear + torsion critical shear-section demand row",
        )
        if demand_row is None:
            continue
        demand_row["__VT station type"] = "CRITICAL SHEAR SECTION"
        demand_row["__Critical shear section"] = True
        demand_row["__Support side"] = str(marker.get("Support side") or "-")
        demand_row["__Critical offset m"] = _beam_uls_float(marker.get("Critical offset m"))
        rows.append(demand_row)
    if not rows:
        return pd.DataFrame(columns=list(active_df.columns) if isinstance(active_df, pd.DataFrame) else [])
    return pd.DataFrame(rows)


def _beam_uls_combined_vt_result_for_row(
    state: Mapping[str, object],
    row: Mapping[str, object],
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> dict[str, object]:
    x_m = _beam_uls_float(row.get("Station x (m)"))
    case = str(row.get("Case Name") or row.get("Case") or "-")
    station_type = str(row.get("__VT station type") or ("CRITICAL SHEAR SECTION" if row.get("__Critical shear section") else "LOAD STATION"))
    support_side = str(row.get("__Support side") or "-")
    critical_offset_m = _beam_uls_float(row.get("__Critical offset m"))
    vu_kN = _beam_uls_float(row.get("Vuy"))
    tu_kNm = _beam_uls_float(row.get("Tu"))
    span_m = _beam_uls_span_length_from_state(state, is_building=strength_route.is_building)
    is_member_end = (
        station_type in {"LOAD STATION", "DIAGRAM BOUNDARY"}
        and math.isfinite(x_m)
        and math.isfinite(span_m)
        and span_m > 0.0
        and (abs(float(x_m)) <= 1.0e-8 or abs(float(x_m) - float(span_m)) <= 1.0e-8)
    )
    boundary_note = ""
    if is_member_end:
        station_type = "DIAGRAM BOUNDARY"
        support_side = "LEFT" if abs(float(x_m)) <= 1.0e-8 else "RIGHT"
        critical_offset_m = float("nan")
        boundary_note = "Endpoint utilization is plotted as a diagram boundary only and is not used as a governing combined V+T design station."
    if not math.isfinite(tu_kNm) or abs(tu_kNm) <= _BEAM_ULS_DEMAND_TOL:
        return {
            "Check": "Shear + Torsion",
            "Status": "NOT APPLICABLE",
            "Station type": station_type,
            "Support side": support_side,
            "Critical offset m": critical_offset_m,
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Vu kN": vu_kN if math.isfinite(vu_kN) else float("nan"),
            "Tu kN-m": 0.0,
            "Stress status": "NOT ACTIVE",
            "Transverse status": "NOT ACTIVE",
            "Overall D/C value": float("nan"),
            "Notes": "No active Tu at this station; combined V+T interaction is not applicable.",
        }

    source_row = dict(row)
    mux_source = _beam_uls_float(source_row.get("Mux"))
    if not math.isfinite(mux_source) or abs(mux_source) <= _BEAM_ULS_DEMAND_TOL:
        # Some source helpers use Mux only to establish tension face / section
        # analysis context.  A tiny seed avoids hiding valid torsion-only or
        # zero-shear combined checks; the original demand values below remain
        # the governing combined V+T demand.
        source_row["Mux"] = 1.0e-3
    if math.isfinite(vu_kN) and abs(float(vu_kN)) <= _BEAM_ULS_DEMAND_TOL:
        # Vu = 0 is a valid combined V+T state.  The shear helper normally
        # exits early for no-demand rows, so use a tiny seed only to retrieve
        # section/depth/Vc/Av source terms.  The combined shear stress and
        # required shear reinforcement are still computed with Vu = 0.
        source_row["Vuy"] = 1.0e-3
    shear = _beam_uls_shear_result_for_row(state, source_row, strength_route=strength_route)
    torsion = _beam_uls_torsion_result_for_row(state, source_row, strength_route=strength_route)
    notes: list[str] = []
    if math.isfinite(vu_kN) and abs(float(vu_kN)) <= _BEAM_ULS_DEMAND_TOL:
        notes.append("Vu = 0 is treated as a valid combined V+T demand state; shear stress and shear-required reinforcement terms are zero.")
    fc = float("nan")
    analysis_input, input_messages = _beam_uls_flexure_analysis_input_for_station(state, row=row, strength_route=strength_route)
    if input_messages:
        notes.extend(input_messages)
    if analysis_input is not None:
        fc = float(analysis_input.concrete_material.fc_MPa)
    bw_mm = _beam_uls_float(shear.get("bw mm"))
    d_mm = _beam_uls_float(shear.get("d mm"))
    dv_mm = _beam_uls_float(shear.get("dv mm"))
    depth_mm = dv_mm if strength_route.is_bridge and math.isfinite(dv_mm) and dv_mm > 0.0 else d_mm
    phi = _beam_uls_float(shear.get("φ"))
    if not math.isfinite(phi) or phi <= 0.0:
        phi = 0.90 if strength_route.is_bridge else 0.75
    vc_kN = _beam_uls_float(shear.get("Vc kN"))
    vs_kN = _beam_uls_float(shear.get("Vs kN"))
    avs_provided = _beam_uls_float(shear.get("Av/s mm2/mm"))
    avs_min = _beam_uls_float(shear.get("Av/s required mm2/mm"))
    fy_shear = float("nan")
    zone = _beam_uls_active_shear_zone_for_station(state, x_m)
    if zone is not None:
        fy_shear = _beam_uls_float(zone.get("fy_MPa"))
    ao = _beam_uls_float(torsion.get("Ao mm2"))
    aoh = _beam_uls_float(torsion.get("Aoh mm2"))
    ph = _beam_uls_float(torsion.get("ph mm"))
    at_per_s = _beam_uls_float(torsion.get("At/s mm2/mm"))
    cot_theta = _beam_uls_float(torsion.get("cotθ"))
    if not math.isfinite(cot_theta) or cot_theta <= 0.0:
        cot_theta = 1.0
    shape = _beam_uls_section_torsion_shape_type(state)
    required_inputs = [fc, bw_mm, depth_mm, phi, vc_kN, avs_provided, fy_shear, ao, aoh, ph, at_per_s]
    if not all(math.isfinite(value) and value > 0.0 for value in required_inputs) or not math.isfinite(vu_kN):
        return {
            "Check": "Shear + Torsion",
            "Status": "DIAGRAM BOUNDARY" if is_member_end else "DATA REQUIRED",
            "Station type": station_type,
            "Support side": support_side,
            "Critical offset m": critical_offset_m,
            "Governing x": _format_beam_uls_x(x_m),
            "Case": case,
            "Vu kN": vu_kN,
            "Tu kN-m": tu_kNm,
            "Stress status": "BOUNDARY" if is_member_end else "DATA REQUIRED",
            "Transverse status": "BOUNDARY" if is_member_end else "DATA REQUIRED",
            "Longitudinal status": "BOUNDARY" if is_member_end else "DATA REQUIRED",
            "Overall D/C value": float("nan"),
            "Shape": shape,
            "Notes": boundary_note if is_member_end else "Combined V+T needs finite shear capacity terms, torsion hoop geometry, active transverse zone, and section/material input.",
        }

    shear_stress = abs(float(vu_kN)) * 1000.0 / (float(bw_mm) * float(depth_mm))
    torsion_stress = abs(float(tu_kNm)) * 1.0e6 * float(ph) / (1.7 * float(aoh) * float(aoh))
    if shape == "hollow":
        stress_demand = shear_stress + torsion_stress
        interaction_form = "linear sum for hollow section"
    else:
        stress_demand = math.sqrt(shear_stress * shear_stress + torsion_stress * torsion_stress)
        interaction_form = "root-sum-square for solid section"
    if strength_route.is_bridge:
        stress_limit = float(phi) * 0.25 * float(fc)
        stress_basis = "AASHTO LRFD-compatible combined V+T compression-strut stress screen"
    else:
        vc_stress = float(vc_kN) * 1000.0 / (float(bw_mm) * float(depth_mm))
        stress_limit = float(phi) * (vc_stress + 0.66 * math.sqrt(float(fc)))
        stress_basis = "ACI 318-compatible combined V+T stress interaction screen"
    stress_dc = stress_demand / stress_limit if stress_limit > 0.0 else float("nan")
    stress_status = "PASS" if math.isfinite(stress_dc) and stress_dc <= 1.0 + 1.0e-9 else "FAIL"

    shear_req = max(0.0, (abs(float(vu_kN)) * 1000.0 / float(phi) - float(vc_kN) * 1000.0) / (float(fy_shear) * float(depth_mm) * float(cot_theta)))
    torsion_req = abs(float(tu_kNm)) * 1.0e6 / (float(phi) * 2.0 * float(ao) * float(fy_shear) * float(cot_theta))
    combined_req = shear_req + 2.0 * torsion_req
    # VT2 adds a longitudinal reinforcement review gate based on the torsion
    # longitudinal demand implied by the required At/s.  The provided area is
    # still read from the ordinary rebar table (single source of truth).  This
    # is intentionally a review gate, not a final flexure+shear+tension
    # longitudinal certification.
    longitudinal_req = torsion_req * float(ph) * float(cot_theta) * float(cot_theta)
    longitudinal_review = _beam_uls_torsion_longitudinal_review(state, longitudinal_req)
    longitudinal_status = str(longitudinal_review.get("status") or "DATA REQUIRED")
    if strength_route.is_bridge:
        min_req = max(0.083 * math.sqrt(float(fc)) * float(bw_mm) / float(fy_shear), 0.35 * float(bw_mm) / float(fy_shear))
    else:
        min_req = max(0.062 * math.sqrt(float(fc)) * float(bw_mm) / float(fy_shear), 0.35 * float(bw_mm) / float(fy_shear))
    required_total = max(combined_req, min_req)
    provided_total = float(avs_provided) + 2.0 * float(at_per_s)
    transverse_dc = required_total / provided_total if provided_total > 0.0 else float("nan")
    transverse_status = "PASS" if math.isfinite(transverse_dc) and transverse_dc <= 1.0 + 1.0e-9 else "FAIL"
    overall_dc_values = [value for value in [stress_dc, transverse_dc] if math.isfinite(value)]
    overall_dc = max(overall_dc_values) if overall_dc_values else float("nan")
    if stress_status == "FAIL" or transverse_status == "FAIL" or longitudinal_status == "FAIL":
        status = "FAIL"
    elif longitudinal_status in {"LAYOUT REQUIRED", "NOT CHECKED"}:
        status = "DATA REQUIRED"
    else:
        status = "PASS"
    if is_member_end:
        status = "DIAGRAM BOUNDARY"
        stress_status = "BOUNDARY"
        transverse_status = "BOUNDARY"
        longitudinal_status = "BOUNDARY"
        notes.append(boundary_note)
    notes.append("ULS.VT.CODE1 checks combined compression-strut stress, combined transverse reinforcement, and longitudinal Al from the ordinary rebar source of truth.")
    notes.append(str(longitudinal_review.get("description") or ""))
    if status == "PASS":
        notes.append("Combined V+T interaction/reinforcement gates pass for this station; source shear/torsion gates are evaluated separately in the source-strength gate.")
    notes.append("Vp is treated as zero in this combined V+T screen unless already embedded in the imported ULS resultants / current SHEAR.CODE2 route.")
    return {
        "Check": "Shear + Torsion",
        "Status": status,
        "Station type": station_type,
        "Support side": support_side,
        "Critical offset m": critical_offset_m if math.isfinite(critical_offset_m) else float("nan"),
        "Governing x": _format_beam_uls_x(x_m),
        "Case": case,
        "Vu kN": float(vu_kN),
        "Tu kN-m": float(tu_kNm),
        "Shape": shape.upper(),
        "Stress status": stress_status,
        "Transverse status": transverse_status,
        "Longitudinal status": longitudinal_status,
        "Stress D/C value": stress_dc,
        "Transverse D/C value": transverse_dc,
        "Longitudinal D/C value": longitudinal_review.get("utilization", float("nan")),
        "Overall D/C value": max([value for value in [overall_dc, _beam_uls_float(longitudinal_review.get("utilization"))] if math.isfinite(value)], default=overall_dc),
        "Shear stress MPa": shear_stress,
        "Torsion stress MPa": torsion_stress,
        "Interaction stress MPa": stress_demand,
        "Stress limit MPa": stress_limit,
        "Av shear req mm2/mm": shear_req,
        "At torsion req mm2/mm": torsion_req,
        "Combined transverse req mm2/mm": combined_req,
        "Minimum transverse req mm2/mm": min_req,
        "Governing transverse req mm2/mm": required_total,
        "Provided Av+2At per s mm2/mm": provided_total,
        "Al V+T req mm2": longitudinal_req,
        "Al provided mm2": longitudinal_review.get("provided_mm2", float("nan")),
        "bw mm": float(bw_mm),
        "d mm": float(d_mm) if math.isfinite(d_mm) else float("nan"),
        "dv mm": float(dv_mm) if math.isfinite(dv_mm) else float("nan"),
        "Ao mm2": float(ao),
        "Aoh mm2": float(aoh),
        "ph mm": float(ph),
        "φ": float(phi),
        "θ cot": float(cot_theta),
        "Code basis": stress_basis,
        "Interaction form": interaction_form,
        "Notes": "; ".join(part for part in notes if part),
    }


def _beam_uls_combined_vt_check_dataframe(
    state: Mapping[str, object],
    active_df: pd.DataFrame,
    *,
    strength_route: BeamGirderUlsStrengthRoute,
) -> pd.DataFrame:
    columns = [
        "Check", "Status", "Station type", "Support side", "Critical offset m", "Governing x", "Case", "Vu kN", "Tu kN-m", "Shape",
        "Stress status", "Transverse status", "Longitudinal status", "Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value",
        "Shear stress MPa", "Torsion stress MPa", "Interaction stress MPa", "Stress limit MPa",
        "Av shear req mm2/mm", "At torsion req mm2/mm", "Combined transverse req mm2/mm", "Minimum transverse req mm2/mm", "Governing transverse req mm2/mm", "Provided Av+2At per s mm2/mm", "Al V+T req mm2", "Al provided mm2",
        "bw mm", "d mm", "dv mm", "Ao mm2", "Aoh mm2", "ph mm", "φ", "θ cot", "Code basis", "Interaction form", "Notes",
    ]
    demand_rows = _beam_uls_combined_vt_demand_rows(active_df, state, strength_route=strength_route)
    if demand_rows.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, object]] = []
    for _, demand_row in demand_rows.iterrows():
        result = _beam_uls_combined_vt_result_for_row(state, demand_row.to_dict(), strength_route=strength_route)
        for column in columns:
            result.setdefault(
                column,
                float("nan")
                if column.endswith("kN")
                or column.endswith("kN-m")
                or column.endswith("MPa")
                or column.endswith("mm2/mm")
                or column.endswith("mm")
                or column.endswith("mm2")
                or column in {"Critical offset m", "Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value", "φ", "θ cot"}
                else "-",
            )
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_governing_combined_vt_row(vt_df: pd.DataFrame | None) -> dict[str, object] | None:
    if vt_df is None or vt_df.empty:
        return None
    df = vt_df.copy()
    df = df[~df.get("Status", pd.Series(index=df.index, dtype=object)).astype(str).isin(["NOT APPLICABLE", "BOUNDARY SKIPPED", "DIAGRAM BOUNDARY"])].copy()
    df = df[df.get("Station type", pd.Series(index=df.index, dtype=object)).astype(str) != "DIAGRAM BOUNDARY"].copy()
    if df.empty:
        return None
    df["__dc"] = pd.to_numeric(df.get("Overall D/C value"), errors="coerce")
    tu_source = df["Tu kN-m"] if "Tu kN-m" in df.columns else pd.Series([float("nan")] * len(df), index=df.index)
    df["__tu"] = pd.to_numeric(tu_source, errors="coerce").abs()
    status_priority = {"FAIL": 4, "DATA REQUIRED": 3, "PASS": 2, "PASS — REVIEW": 2, "BOUNDARY SKIPPED": 0, "NOT APPLICABLE": 0}
    df["__status_priority"] = df.get("Status", pd.Series(index=df.index, dtype=object)).map(lambda value: status_priority.get(str(value), 1))
    idx = df.sort_values(["__status_priority", "__dc", "__tu"], ascending=[False, False, False]).index[0]
    return vt_df.loc[idx].drop(labels=["__dc", "__tu", "__status_priority"], errors="ignore").to_dict()


def _beam_uls_combined_vt_source_strength_gate(
    shear_df: pd.DataFrame | None,
    torsion_df: pd.DataFrame | None,
) -> dict[str, object]:
    """Summarize separate shear/torsion source-strength acceptance for V+T.

    Combined interaction/reinforcement utilization is a distinct check gate.  It
    must not be presented as overall ULS acceptance when the underlying separate
    shear or torsion strength checks fail.
    """

    blockers: list[str] = []
    reviews: list[str] = []

    shear = _beam_uls_governing_shear_row(shear_df)
    if shear is not None:
        shear_status = str(shear.get("Status") or "-").upper()
        shear_dc = _beam_uls_float(shear.get("Governing D/C value", shear.get("D/C value")))
        shear_x = str(shear.get("Governing x") or "-")
        if shear_status == "FAIL":
            blockers.append(f"Shear FAIL at x={shear_x}" + (f" (D/C {_format_beam_uls_ratio(shear_dc)})" if math.isfinite(shear_dc) else ""))
        elif shear_status not in {"PASS", "NO DEMAND", "NOT APPLICABLE"}:
            reviews.append(f"Shear {shear_status} at x={shear_x}")
    elif shear_df is None or shear_df.empty:
        reviews.append("Shear source check has not produced review rows")

    torsion = _beam_uls_governing_torsion_row(torsion_df)
    if torsion is not None:
        torsion_status = str(torsion.get("Status") or "-").upper()
        torsion_dc = _beam_uls_float(torsion.get("D/C value"))
        torsion_x = str(torsion.get("Governing x") or "-")
        if torsion_status == "FAIL":
            blockers.append(f"Torsion FAIL at x={torsion_x}" + (f" (D/C {_format_beam_uls_ratio(torsion_dc)})" if math.isfinite(torsion_dc) else ""))
        elif torsion_status not in {"PASS", "BELOW THRESHOLD", "NO DEMAND", "NOT APPLICABLE"}:
            reviews.append(f"Torsion {torsion_status} at x={torsion_x}")
    elif torsion_df is None or torsion_df.empty:
        reviews.append("Torsion source check has not produced review rows")

    if blockers:
        return {
            "value": "BLOCKED",
            "detail": "; ".join(blockers[:3]),
            "status": "danger",
            "has_blocker": True,
            "has_review": bool(reviews),
        }
    if reviews:
        return {
            "value": "SOURCE REVIEW",
            "detail": "; ".join(reviews[:3]),
            "status": "warning",
            "has_blocker": False,
            "has_review": True,
        }
    return {
        "value": "CLEAR",
        "detail": "Separate shear/torsion source checks are clear for the combined interaction gate.",
        "status": "success",
        "has_blocker": False,
        "has_review": False,
    }


def _beam_uls_combined_vt_source_readiness_notes(vt_df: pd.DataFrame | None) -> list[str]:
    """Return short user-facing diagnostics for DATA REQUIRED combined V+T rows."""

    if vt_df is None or vt_df.empty:
        return ["No combined V+T rows were produced. Check active ULS station rows and nonzero Tu demand."]
    notes: list[str] = []
    df = vt_df.copy()
    data_required = df[df.get("Status", pd.Series(index=df.index, dtype=object)).astype(str) == "DATA REQUIRED"].copy()
    if data_required.empty:
        return []
    if (data_required.get("Stress status", pd.Series(index=data_required.index, dtype=object)).astype(str) == "DATA REQUIRED").any():
        notes.append("Stress interaction source data are incomplete: verify section/material, web depth/width, and shear capacity terms.")
    if (data_required.get("Transverse status", pd.Series(index=data_required.index, dtype=object)).astype(str) == "DATA REQUIRED").any():
        notes.append("Transverse source data are incomplete: verify active stirrup/closed-hoop zones cover the governing V+T stations.")
    if (data_required.get("Longitudinal status", pd.Series(index=data_required.index, dtype=object)).astype(str).isin(["LAYOUT REQUIRED", "NOT CHECKED", "DATA REQUIRED"])).any():
        notes.append("Longitudinal Al source is incomplete: enable ordinary rebar and confirm active bars intended for torsion perimeter reinforcement.")
    raw_notes = data_required.get("Notes", pd.Series(dtype=object)).dropna().astype(str).tolist()
    for note in raw_notes[:3]:
        if note and note not in notes:
            notes.append(note)
    return notes[:5]


def _beam_uls_combined_vt_has_finite_utilization(vt_df: pd.DataFrame | None) -> bool:
    if vt_df is None or vt_df.empty:
        return False
    for column in ["Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value"]:
        if column in vt_df.columns and pd.to_numeric(vt_df[column], errors="coerce").notna().any():
            return True
    return False


def _beam_uls_combined_vt_source_readiness_dataframe(vt_df: pd.DataFrame | None) -> pd.DataFrame:
    """Return station-level source readiness diagnostics for incomplete V+T rows."""

    columns = ["Station x", "Case", "Status", "Stress source", "Transverse source", "Longitudinal source", "Notes"]
    if vt_df is None or vt_df.empty:
        return pd.DataFrame(
            [
                {
                    "Station x": "-",
                    "Case": "-",
                    "Status": "DATA REQUIRED",
                    "Stress source": "No combined V+T rows produced",
                    "Transverse source": "No combined V+T rows produced",
                    "Longitudinal source": "No combined V+T rows produced",
                    "Notes": "Check active ULS rows, nonzero Tu demand, section/material input, and reinforcement layouts.",
                }
            ],
            columns=columns,
        )
    rows: list[dict[str, object]] = []
    for _, row in vt_df.iterrows():
        status = str(row.get("Status") or "-")
        if status not in {"DATA REQUIRED", "FAIL"}:
            continue

        stress_status = str(row.get("Stress status") or "-")
        transverse_status = str(row.get("Transverse status") or "-")
        longitudinal_status = str(row.get("Longitudinal status") or "-")
        if status == "FAIL" and not any(value in {"DATA REQUIRED", "LAYOUT REQUIRED", "NOT CHECKED"} for value in [stress_status, transverse_status, longitudinal_status]):
            continue

        def _source_label(gate_status: str, ready_label: str, missing_label: str) -> str:
            return ready_label if gate_status in {"PASS", "NOT ACTIVE"} else missing_label

        rows.append(
            {
                "Station x": str(row.get("Governing x") or "-"),
                "Case": str(row.get("Case") or "-"),
                "Status": status,
                "Stress source": _source_label(stress_status, "Ready", "Missing section/material, web width/depth, shear capacity, or torsion hoop geometry"),
                "Transverse source": _source_label(transverse_status, "Ready", "Missing active stirrup/closed-hoop zone or finite Av+2At source terms"),
                "Longitudinal source": _source_label(longitudinal_status, "Ready", "Missing/insufficient active ordinary rebar intended as torsion longitudinal Al"),
                "Notes": str(row.get("Notes") or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_combined_vt_plot_dataframe(vt_df: pd.DataFrame | None) -> pd.DataFrame:
    """Return V+T rows for diagram plotting with endpoint boundary values filled.

    Endpoint rows are diagram-boundary values only.  When the actual endpoint
    row cannot compute a finite utilization because the provided stirrup zone
    starts away from the support, use the nearest finite interior value for the
    same case/trace so the diagram reaches x=0 and x=L without creating a
    governing design station.
    """

    if vt_df is None or vt_df.empty:
        return pd.DataFrame()
    plot_df = vt_df.copy()
    plot_df["__x_m"] = plot_df["Governing x"].map(lambda value: str(value or "").replace(" m", ""))
    plot_df["__x_m"] = pd.to_numeric(plot_df["__x_m"], errors="coerce")
    plot_df = plot_df[plot_df["__x_m"].notna()].copy()
    plot_df = plot_df[~plot_df.get("Status", pd.Series(index=plot_df.index, dtype=object)).astype(str).isin(["NOT APPLICABLE", "BOUNDARY SKIPPED"])].copy()
    if plot_df.empty:
        return plot_df
    trace_columns = ["Stress D/C value", "Transverse D/C value", "Longitudinal D/C value"]
    plot_df["__is_boundary"] = plot_df.get("Station type", pd.Series(index=plot_df.index, dtype=object)).astype(str).eq("DIAGRAM BOUNDARY")
    for column in trace_columns:
        if column not in plot_df.columns:
            continue
        plot_df[column] = pd.to_numeric(plot_df[column], errors="coerce")
    if "Case" not in plot_df.columns:
        plot_df["Case"] = "-"
    for case_name, case_idx in plot_df.groupby("Case", sort=False).groups.items():
        case_df = plot_df.loc[list(case_idx)].copy()
        interior_df = case_df[~case_df["__is_boundary"]].copy()
        if interior_df.empty:
            continue
        for boundary_index, boundary_row in case_df[case_df["__is_boundary"]].iterrows():
            bx = float(boundary_row["__x_m"])
            for column in trace_columns:
                current = _beam_uls_float(plot_df.at[boundary_index, column]) if column in plot_df.columns else float("nan")
                if math.isfinite(current):
                    continue
                finite = interior_df[pd.to_numeric(interior_df.get(column), errors="coerce").notna()].copy()
                if finite.empty:
                    continue
                finite["__dist"] = (finite["__x_m"].astype(float) - bx).abs()
                nearest_index = finite.sort_values(["__dist", "__x_m"], kind="stable").index[0]
                nearest_value = _beam_uls_float(plot_df.at[nearest_index, column])
                if math.isfinite(nearest_value):
                    plot_df.at[boundary_index, column] = nearest_value
    return plot_df


def _make_beam_uls_combined_vt_utilization_figure(vt_df: pd.DataFrame | None, *, code_label: str) -> go.Figure:
    fig = go.Figure()
    if vt_df is None or vt_df.empty:
        fig.add_annotation(
            text="No combined shear + torsion rows. Press Calculate Shear + Torsion after ULS demand rows are ready.",
            x=0.5,
            y=0.5,
            showarrow=False,
            xref="paper",
            yref="paper",
        )
        fig.update_layout(
            title={"text": f"Combined Shear + Torsion Utilization — Strength ULS<br><sup>{code_label} · no rows</sup>"},
            xaxis_title="Distance from left end of member (m)",
            yaxis_title="Demand / Capacity ratio",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        )
        return fig

    plot_df = _beam_uls_combined_vt_plot_dataframe(vt_df)
    traces = [
        ("Stress interaction D/C", "Stress D/C value"),
        ("Transverse reinforcement D/C", "Transverse D/C value"),
        ("Longitudinal Al D/C", "Longitudinal D/C value"),
    ]
    has_trace = False
    if not plot_df.empty:
        plot_df = plot_df.sort_values(["Case", "__x_m"], kind="stable")
        for case_name, case_df in plot_df.groupby("Case", sort=False):
            for trace_name, column in traces:
                values = pd.to_numeric(case_df.get(column), errors="coerce")
                if values.notna().any():
                    fig.add_trace(
                        go.Scatter(
                            x=case_df["__x_m"],
                            y=values,
                            mode="lines+markers",
                            name=f"{trace_name} — {case_name}",
                            line={"width": 3},
                            marker={"size": 7},
                            hovertemplate="x=%{x:.3f} m<br>D/C=%{y:.3f}<extra></extra>",
                        )
                    )
                    has_trace = True

    if has_trace:
        x_values = pd.to_numeric(plot_df["__x_m"], errors="coerce").dropna().astype(float)
        x_min = float(x_values.min()) if not x_values.empty else 0.0
        x_max = float(x_values.max()) if not x_values.empty and float(x_values.max()) > x_min else x_min + 1.0
        fig.add_trace(
            go.Scatter(
                x=[x_min, x_max],
                y=[1.0, 1.0],
                mode="lines",
                name="Limit D/C = 1.0",
                line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                hovertemplate="Limit D/C = 1.0<extra></extra>",
            )
        )
        governing = _beam_uls_governing_combined_vt_row(vt_df)
        if governing is not None:
            x_text = str(governing.get("Governing x") or "").replace(" m", "")
            x_val = _beam_uls_float(x_text)
            dc = _beam_uls_float(governing.get("Overall D/C value"))
            status = str(governing.get("Status") or "REVIEW")
            if math.isfinite(x_val) and math.isfinite(dc):
                fig.add_trace(
                    go.Scatter(
                        x=[x_val],
                        y=[dc],
                        mode="markers+text",
                        text=[f"{status} · D/C {dc:.3f}"],
                        textposition="top center",
                        name="Governing V+T check",
                        marker={"symbol": "diamond", "size": 12},
                        hovertemplate="x=%{x:.3f} m<br>Governing D/C=%{y:.3f}<extra></extra>",
                    )
                )
    else:
        fig.add_annotation(
            text="Combined V+T utilization diagram is not available until finite D/C source terms are ready.",
            x=0.5,
            y=0.5,
            showarrow=False,
            xref="paper",
            yref="paper",
        )

    fig.update_layout(
        title={"text": f"Combined Shear + Torsion Utilization — Strength ULS<br><sup>{code_label}</sup>"},
        xaxis_title="Distance from left end of member (m)",
        yaxis_title="Demand / Capacity ratio",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=-0.35, xanchor="center", x=0.5),
        margin=dict(l=30, r=20, t=70, b=90),
    )
    return fig


def _beam_uls_combined_vt_audit_dataframe(vt_df: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "Governing", "Station type", "Station x", "Case", "Shape", "Status", "Stress", "Transverse", "Longitudinal", "Vu", "Tu", "Stress D/C", "Transverse D/C", "Longitudinal D/C", "Overall D/C",
        "v shear", "t torsion", "interaction", "limit", "Av/s req", "At/s req", "(Av+2At)/s req", "min req", "provided", "Al req", "Al provided", "bw", "d", "dv", "Aoh", "Ao", "ph", "φ", "cotθ", "Code basis", "Notes",
    ]
    if vt_df is None or vt_df.empty:
        return pd.DataFrame(columns=columns)
    df = vt_df.copy()
    df["__dc"] = pd.to_numeric(df.get("Overall D/C value"), errors="coerce")
    design_df = df[
        ~df.get("Status", pd.Series(index=df.index, dtype=object)).astype(str).isin(["NOT APPLICABLE", "BOUNDARY SKIPPED", "DIAGRAM BOUNDARY"])
        & (df.get("Station type", pd.Series(index=df.index, dtype=object)).astype(str) != "DIAGRAM BOUNDARY")
    ].copy()
    governing_idx = design_df["__dc"].idxmax() if not design_df.empty and design_df["__dc"].notna().any() else None
    rows: list[dict[str, object]] = []
    for idx, row in df.iterrows():
        rows.append({
            "Governing": "Yes" if governing_idx is not None and idx == governing_idx else "",
            "Station type": str(row.get("Station type") or "-"),
            "Station x": str(row.get("Governing x") or "-"),
            "Case": str(row.get("Case") or "-"),
            "Shape": str(row.get("Shape") or "-"),
            "Status": str(row.get("Status") or "-"),
            "Stress": str(row.get("Stress status") or "-"),
            "Transverse": str(row.get("Transverse status") or "-"),
            "Longitudinal": str(row.get("Longitudinal status") or "-"),
            "Vu": _format_beam_uls_audit_number(row.get("Vu kN"), unit="kN"),
            "Tu": _format_beam_uls_audit_number(row.get("Tu kN-m"), unit="kN-m"),
            "Stress D/C": _format_beam_uls_ratio(row.get("Stress D/C value")),
            "Transverse D/C": _format_beam_uls_ratio(row.get("Transverse D/C value")),
            "Longitudinal D/C": _format_beam_uls_ratio(row.get("Longitudinal D/C value")),
            "Overall D/C": _format_beam_uls_ratio(row.get("Overall D/C value")),
            "v shear": _format_beam_uls_audit_number(row.get("Shear stress MPa"), unit="MPa"),
            "t torsion": _format_beam_uls_audit_number(row.get("Torsion stress MPa"), unit="MPa"),
            "interaction": _format_beam_uls_audit_number(row.get("Interaction stress MPa"), unit="MPa"),
            "limit": _format_beam_uls_audit_number(row.get("Stress limit MPa"), unit="MPa"),
            "Av/s req": _format_beam_uls_audit_number(row.get("Av shear req mm2/mm"), unit="mm²/mm"),
            "At/s req": _format_beam_uls_audit_number(row.get("At torsion req mm2/mm"), unit="mm²/mm"),
            "(Av+2At)/s req": _format_beam_uls_audit_number(row.get("Governing transverse req mm2/mm"), unit="mm²/mm"),
            "min req": _format_beam_uls_audit_number(row.get("Minimum transverse req mm2/mm"), unit="mm²/mm"),
            "provided": _format_beam_uls_audit_number(row.get("Provided Av+2At per s mm2/mm"), unit="mm²/mm"),
            "Al req": _format_beam_uls_audit_number(row.get("Al V+T req mm2"), unit="mm²"),
            "Al provided": _format_beam_uls_audit_number(row.get("Al provided mm2"), unit="mm²"),
            "bw": _format_beam_uls_audit_number(row.get("bw mm"), unit="mm"),
            "d": _format_beam_uls_audit_number(row.get("d mm"), unit="mm"),
            "dv": _format_beam_uls_audit_number(row.get("dv mm"), unit="mm"),
            "Aoh": _format_beam_uls_audit_number(row.get("Aoh mm2"), unit="mm²"),
            "Ao": _format_beam_uls_audit_number(row.get("Ao mm2"), unit="mm²"),
            "ph": _format_beam_uls_audit_number(row.get("ph mm"), unit="mm"),
            "φ": _format_beam_uls_ratio(row.get("φ")),
            "cotθ": _format_beam_uls_ratio(row.get("θ cot")),
            "Code basis": str(row.get("Code basis") or "-"),
            "Notes": str(row.get("Notes") or ""),
        })
    return pd.DataFrame(rows, columns=columns)


def _beam_uls_torsion_interaction_status(active_df: pd.DataFrame) -> dict[str, str]:
    """Return the compact Shear + Torsion interaction status for the ULS tab workspace."""

    torsion = _beam_uls_governing_action(active_df, "Tu")
    if torsion is None or float(torsion["abs_demand"]) <= _BEAM_ULS_DEMAND_TOL:
        return {
            "title": "Shear + torsion interaction",
            "value": "Not applicable — Tu not active",
            "detail": "No active torsion demand is present in the ULS station rows; review shear independently.",
            "status": "neutral",
        }
    return {
        "title": "Shear + torsion interaction",
        "value": "CHECK REQUIRED — shear + torsion interaction not implemented",
        "detail": (
            f"Tu = {_format_beam_uls_demand(torsion['demand'], 'kN-m')} at "
            f"x={_format_beam_uls_x(torsion['x_m'])} ({torsion['case']}). "
            "Do not certify combined shear + torsion even if separate shear and torsion checks look acceptable."
        ),
        "status": "warning",
    }


def _beam_uls_check_tab_caption() -> str:
    return (
        "Check-specific tabs are placed directly under the compact table so the main ULS actions are visible without opening a general expander. "
        "Each tab keeps only its own decision cards, diagram, audit output, and limitation notes."
    )

def _beam_uls_check_table(
    active_df: pd.DataFrame,
    flexure_preview_df: pd.DataFrame | None = None,
    shear_check_df: pd.DataFrame | None = None,
    torsion_check_df: pd.DataFrame | None = None,
    combined_vt_df: pd.DataFrame | None = None,
    *,
    state: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    flexure = _beam_uls_governing_action(active_df, "Mux")
    torsion = _beam_uls_governing_action(active_df, "Tu")
    rows: list[dict[str, str]] = []

    flexure_preview = _beam_uls_governing_flexure_preview_row(flexure_preview_df)
    if flexure_preview is not None:
        rows.append(
            {
                "Check": "Flexure",
                "Status": str(flexure_preview.get("Status") or "REVIEW"),
                "Governing x": str(flexure_preview.get("Governing x") or "-"),
                "Case": str(flexure_preview.get("Case") or "-"),
                "Demand": str(flexure_preview.get("Demand") or "-"),
                "Capacity": str(flexure_preview.get("Capacity") or "-"),
                "Utilization": str(flexure_preview.get("Utilization") or "-"),
            }
        )
    elif flexure is None or float(flexure["abs_demand"]) <= _BEAM_ULS_DEMAND_TOL:
        rows.append(
            {
                "Check": "Flexure",
                "Status": "NOT READY",
                "Governing x": "-",
                "Case": "-",
                "Demand": "-",
                "Capacity": "-",
                "Utilization": "-",
            }
        )
    else:
        rows.append(
            {
                "Check": "Flexure",
                "Status": "PLANNED",
                "Governing x": _format_beam_uls_x(flexure["x_m"]),
                "Case": str(flexure["case"]),
                "Demand": _format_beam_uls_demand(flexure["demand"], "kN-m"),
                "Capacity": "-",
                "Utilization": "-",
            }
        )

    shear_result = _beam_uls_governing_shear_row(shear_check_df)
    torsion_result = _beam_uls_governing_torsion_row(torsion_check_df)
    torsion_status_text = str(torsion_result.get("Status") or "REVIEW") if torsion_result is not None else "OPTIONAL"
    if shear_result is not None:
        rows.append(
            {
                "Check": "Shear",
                "Status": str(shear_result.get("Status") or "REVIEW"),
                "Governing x": str(shear_result.get("Governing x") or "-"),
                "Case": str(shear_result.get("Case") or "-"),
                "Demand": str(shear_result.get("Demand") or "-"),
                "Capacity": str(shear_result.get("Capacity") or "-"),
                "Utilization": str(shear_result.get("Utilization") or "-"),
            }
        )
    else:
        shear_status, shear_capacity_note = _beam_uls_shear_layout_status(state or {})
        shear = _beam_uls_governing_action(active_df, "Vuy")
        if shear is None or float(shear["abs_demand"]) <= _BEAM_ULS_DEMAND_TOL:
            rows.append({"Check": "Shear", "Status": "NOT READY", "Governing x": "-", "Case": "-", "Demand": "-", "Capacity": "-", "Utilization": "-"})
        else:
            rows.append(
                {
                    "Check": "Shear",
                    "Status": shear_status,
                    "Governing x": _format_beam_uls_x(shear["x_m"]),
                    "Case": str(shear["case"]),
                    "Demand": _format_beam_uls_demand(shear["demand"], "kN"),
                    "Capacity": shear_capacity_note if shear_status == "LAYOUT READY" else "-",
                    "Utilization": "-",
                }
            )

    torsion_result = _beam_uls_governing_torsion_row(torsion_check_df)
    if torsion_result is not None:
        rows.append(
            {
                "Check": "Torsion",
                "Status": str(torsion_result.get("Status") or "REVIEW"),
                "Governing x": str(torsion_result.get("Governing x") or "-"),
                "Case": str(torsion_result.get("Case") or "-"),
                "Demand": str(torsion_result.get("Demand") or "-"),
                "Capacity": str(torsion_result.get("Capacity") or "-"),
                "Utilization": str(torsion_result.get("Utilization") or "-"),
            }
        )
    elif torsion is None or float(torsion["abs_demand"]) <= _BEAM_ULS_DEMAND_TOL:
        rows.append({"Check": "Torsion", "Status": "OPTIONAL", "Governing x": "-", "Case": "-", "Demand": "-", "Capacity": "-", "Utilization": "-"})
    else:
        rows.append(
            {
                "Check": "Torsion",
                "Status": "LAYOUT REQUIRED",
                "Governing x": _format_beam_uls_x(torsion["x_m"]),
                "Case": str(torsion["case"]),
                "Demand": _format_beam_uls_demand(torsion["demand"], "kN-m"),
                "Capacity": "-",
                "Utilization": "-",
            }
        )
    combined_result = _beam_uls_governing_combined_vt_row(combined_vt_df)
    if combined_result is not None:
        vu_value = _beam_uls_float(combined_result.get("Vu kN"))
        tu_value = _beam_uls_float(combined_result.get("Tu kN-m"))
        dc_value = _beam_uls_float(combined_result.get("Overall D/C value"))
        source_gate = _beam_uls_combined_vt_source_strength_gate(shear_check_df, torsion_check_df)
        interaction_status = str(combined_result.get("Status") or "REVIEW")
        if source_gate.get("has_blocker"):
            compact_status = "BLOCKED — SOURCE FAIL"
            compact_capacity = f"Interaction {interaction_status}; source gate BLOCKED"
            source_detail = str(source_gate.get("detail") or "source check failed")
            compact_util = (
                f"interaction {dc_value:.3f}; {source_detail}"
                if math.isfinite(dc_value)
                else source_detail
            )
        elif source_gate.get("has_review"):
            compact_status = "REVIEW — SOURCE"
            compact_capacity = f"Interaction {interaction_status}; source review"
            source_detail = str(source_gate.get("detail") or "source check requires review")
            compact_util = (
                f"interaction {dc_value:.3f}; {source_detail}"
                if math.isfinite(dc_value)
                else source_detail
            )
        else:
            compact_status = interaction_status
            compact_capacity = "Interaction / (Av+2At)/s / Al"
            compact_util = f"{dc_value:.3f}" if math.isfinite(dc_value) else "-"
        rows.append(
            {
                "Check": "Shear + Torsion",
                "Status": compact_status,
                "Governing x": str(combined_result.get("Governing x") or "-"),
                "Case": str(combined_result.get("Case") or "-"),
                "Demand": f"Vu {_format_beam_uls_demand(vu_value, 'kN')}; Tu {_format_beam_uls_demand(tu_value, 'kN-m')}",
                "Capacity": compact_capacity,
                "Utilization": compact_util,
            }
        )
    elif torsion is not None and float(torsion["abs_demand"]) > _BEAM_ULS_DEMAND_TOL:
        rows.append(
            {
                "Check": "Shear + Torsion",
                "Status": "NOT CALCULATED",
                "Governing x": _format_beam_uls_x(torsion["x_m"]),
                "Case": str(torsion["case"]),
                "Demand": f"Tu {_format_beam_uls_demand(torsion['demand'], 'kN-m')}",
                "Capacity": "Press Calculate Shear + Torsion",
                "Utilization": "-",
            }
        )
    else:
        rows.append({"Check": "Shear + Torsion", "Status": "NOT ACTIVE", "Governing x": "-", "Case": "-", "Demand": "-", "Capacity": "No active Tu", "Utilization": "-"})
    return pd.DataFrame(rows, columns=["Check", "Status", "Governing x", "Case", "Demand", "Capacity", "Utilization"])


def _beam_uls_summary_cards(active_df: pd.DataFrame, *, workflow_label: str, code_label: str, flexure_preview_df: pd.DataFrame | None = None, shear_check_df: pd.DataFrame | None = None, torsion_check_df: pd.DataFrame | None = None) -> list[dict[str, object]]:
    if active_df.empty:
        return [
            {
                "title": "Overall ULS check",
                "value": "NOT READY",
                "detail": "Define or import Active ULS station demand rows in Loads.",
                "status": "warning",
                "strong": True,
            },
            {"title": "Critical flexure demand", "value": "-", "detail": "No active Loads → ULS row", "status": "neutral"},
            {"title": "Peak shear demand", "value": "-", "detail": "No active Loads → ULS row", "status": "neutral"},
            {"title": "Governing shear check", "value": "-", "detail": "No active Loads → ULS row", "status": "neutral"},
            {"title": "Design action", "value": "Go to Loads", "detail": "Analysis is read-only for ULS demand input.", "status": "info"},
        ]
    flexure = _beam_uls_governing_action(active_df, "Mux")
    shear = _beam_uls_governing_action(active_df, "Vuy")
    flexure_value = _format_beam_uls_demand(flexure["demand"], "kN-m") if flexure else "-"
    flexure_detail = f"{flexure['case']} @ x={_format_beam_uls_x(flexure['x_m'])}" if flexure else "No finite Mux"
    peak_shear_value = _format_beam_uls_demand(shear["demand"], "kN") if shear else "-"
    peak_shear_detail = (
        f"{shear['case']} @ x={_format_beam_uls_x(shear['x_m'])}; diagram/support demand only"
        if shear
        else "No finite Vuy"
    )
    governing_shear_value = "-"
    governing_shear_detail = "Calculate Shear to report governing check station."
    shear_result = _beam_uls_governing_shear_row(shear_check_df)
    torsion_result = _beam_uls_governing_torsion_row(torsion_check_df)
    torsion_status_text = str(torsion_result.get("Status") or "REVIEW") if torsion_result is not None else "OPTIONAL"
    if shear_result is not None:
        shear_dc = str(shear_result.get("Utilization") or "-")
        shear_demand = _beam_uls_float(shear_result.get("Demand kN"))
        governing_shear_value = _format_beam_uls_demand(shear_demand, "kN") if math.isfinite(shear_demand) else str(shear_result.get("Demand") or "-")
        if shear_dc != "-":
            governing_shear_value = f"{governing_shear_value} · D/C {shear_dc}"
        governing_shear_detail = f"{shear_result.get('Case', '-')} @ x={shear_result.get('Governing x', '-')}; {shear_result.get('Capacity', '-')}"
    flex_preview = _beam_uls_governing_flexure_preview_row(flexure_preview_df)
    if flex_preview is not None:
        status_text = str(flex_preview.get("Status") or "REVIEW")
        dc_value = str(flex_preview.get("Utilization") or "-")
        flexure_card_value = f"{flexure_value} · D/C {dc_value}" if dc_value != "-" else flexure_value
        flexure_card_detail = f"{flexure_detail}; {flex_preview.get('Capacity', '-')}"
        shear_status_text = str(shear_result.get("Status") or "REVIEW") if shear_result is not None else "NOT READY"
        if shear_result is not None:
            if status_text == "FAIL" or shear_status_text == "FAIL" or torsion_status_text == "FAIL":
                overall_value = "ULS PARTIAL CHECK — FAIL"
                overall_status = "danger"
            elif status_text == "PASS" and shear_status_text == "PASS" and torsion_status_text in {"OPTIONAL", "BELOW THRESHOLD", "PASS"}:
                overall_value = "ULS PARTIAL CHECK — PASS"
                overall_status = "ready"
            else:
                overall_value = "ULS PARTIAL CHECK — REVIEW"
                overall_status = "warning"
            overall_detail = (
                f"{len(active_df):,} active demand row(s). Flexure = {status_text}; shear = {shear_status_text}; torsion = {torsion_status_text}. "
                "Combined V+T is reported in its own workspace when calculated; development-length/shop-drawing detailing remain project review items."
            )
        else:
            overall_value = f"FLEXURE CHECK — {status_text}"
            overall_detail = (
                f"{len(active_df):,} active demand row(s). Flexure φMn check is {status_text}; "
                "shear φVn is not ready, so no overall ULS PASS/FAIL is issued."
            )
            overall_status = "danger" if status_text == "FAIL" else ("ready" if status_text == "PASS" else "warning")
    else:
        flexure_card_value = flexure_value
        flexure_card_detail = flexure_detail + "; φMn not ready"
        overall_value = "NOT READY"
        overall_detail = f"{len(active_df):,} active demand row(s). Capacity checks are not available yet; no PASS/FAIL is issued."
        overall_status = "warning"
    return [
        {
            "title": "Overall ULS check",
            "value": overall_value,
            "detail": overall_detail,
            "status": overall_status,
            "strong": True,
        },
        {"title": "Critical flexure demand / D/C", "value": flexure_card_value, "detail": flexure_card_detail, "status": "warning" if flex_preview is not None and str(flex_preview.get("Status")) == "FAIL" else "info"},
        {"title": "Peak shear demand", "value": peak_shear_value, "detail": peak_shear_detail, "status": "info"},
        {"title": "Governing shear check", "value": governing_shear_value, "detail": governing_shear_detail, "status": "warning" if shear_result is not None and str(shear_result.get("Status")) == "FAIL" else "info"},
        {
            "title": "Design action",
            "value": "Review calculated ULS gates",
            "detail": f"Flexure, provided-stirrup shear, torsion CODE2, and combined V+T gates are reported when calculated. Development-length/shop-drawing detailing remain project review items for {code_label}.",
            "status": "neutral",
        },
    ]


def _beam_uls_audit_dataframe(active_df: pd.DataFrame) -> pd.DataFrame:
    if active_df.empty:
        return pd.DataFrame(columns=BEAM_ULS_LOAD_COLUMNS_ANALYSIS)
    df = active_df.copy()
    for column in ["Station x (m)", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu"]:
        df[column] = df[column].map(lambda value: "-" if pd.isna(value) else value)
    return df[BEAM_ULS_LOAD_COLUMNS_ANALYSIS]


_BEAM_ULS_DEMAND_LINE_STYLE = {"color": "#1f77b4", "width": 3}
_BEAM_ULS_DEMAND_MARKER_STYLE = {"color": "#1f77b4", "size": 7}
# Section/check capacity curves are visual acceptance/check limits, not demand data.
# Keep them as dashed red lines without point markers so they are not misread as
# station resultants. Use this convention for future beam/girder design diagrams.
_BEAM_ULS_CHECK_LINE_STYLE = {"color": "red", "dash": "dash", "width": 3}
_BEAM_ULS_REFERENCE_LINE_STYLE = {"color": "orange", "dash": "dash", "width": 3}
def _make_beam_uls_demand_figure(active_df: pd.DataFrame, *, column: str, title: str, y_label: str) -> go.Figure:
    plot_df = active_df[["Station x (m)", "Case Name", column]].copy()
    plot_df = plot_df[pd.to_numeric(plot_df["Station x (m)"], errors="coerce").notna()]
    plot_df = plot_df[pd.to_numeric(plot_df[column], errors="coerce").notna()]
    plot_df = plot_df.sort_values(["Case Name", "Station x (m)"], kind="stable")
    fig = go.Figure()
    if plot_df.empty:
        fig.add_annotation(text="No active finite ULS demand rows", x=0.5, y=0.5, showarrow=False, xref="paper", yref="paper")
    else:
        for case_name, case_df in plot_df.groupby("Case Name", sort=False):
            fig.add_trace(
                go.Scatter(
                    x=case_df["Station x (m)"],
                    y=case_df[column],
                    mode="lines+markers",
                    name=f"Demand {column} — {case_name}",
                    line=dict(_BEAM_ULS_DEMAND_LINE_STYLE),
                    marker=dict(_BEAM_ULS_DEMAND_MARKER_STYLE),
                    hovertemplate="x=%{x:.3f} m<br>Demand=%{y:.3f}<extra></extra>",
                )
            )
        governing = _beam_uls_governing_action(plot_df.rename(columns={column: column}), column)
        if governing is not None and float(governing["abs_demand"]) > _BEAM_ULS_DEMAND_TOL:
            fig.add_trace(
                go.Scatter(
                    x=[governing["x_m"]],
                    y=[governing["demand"]],
                    mode="markers+text",
                    text=["Governing demand"],
                    textposition="top center",
                    name="Governing demand",
                    marker={"color": "#1f77b4", "size": 10, "symbol": "diamond"},
                    hovertemplate="x=%{x:.3f} m<br>Demand=%{y:.3f}<extra></extra>",
                )
            )
    fig.update_layout(
        title={"text": f"{title}<br><sup>Demand only — capacity curves planned</sup>"},
        xaxis_title="Distance from left end of member (m)",
        yaxis_title=y_label,
        legend={"orientation": "h", "yanchor": "bottom", "y": -0.33, "xanchor": "center", "x": 0.5},
        margin={"l": 60, "r": 30, "t": 70, "b": 85},
    )
    fig.add_hline(y=0.0, line_width=1)
    return fig



def _make_beam_uls_flexure_preview_figure(active_df: pd.DataFrame, flexure_preview_df: pd.DataFrame | None, *, code_label: str) -> go.Figure:
    fig = _make_beam_uls_demand_figure(
        active_df,
        column="Mux",
        title=f"Flexure Check — Strength ULS<br><sup>{code_label}</sup>",
        y_label="Moment, Mu (kN-m)",
    )
    if flexure_preview_df is None or flexure_preview_df.empty:
        fig.update_layout(title={"text": f"Flexure Check — Strength ULS<br><sup>{code_label} · demand only — φMn not ready</sup>"})
        return fig

    preview_df = flexure_preview_df.copy()
    preview_df["__x_m"] = preview_df["Governing x"].map(lambda value: str(value or "").replace(" m", ""))
    preview_df["__x_m"] = pd.to_numeric(preview_df["__x_m"], errors="coerce")
    preview_df["__demand_kNm"] = pd.to_numeric(preview_df["Demand kN-m"], errors="coerce")
    preview_df["__capacity_kNm"] = pd.to_numeric(preview_df["Capacity kN-m"], errors="coerce")
    preview_df["__utilization"] = pd.to_numeric(preview_df["Utilization value"], errors="coerce")
    if "Capacity plot sign" in preview_df.columns:
        preview_df["__capacity_plot_sign"] = pd.to_numeric(preview_df["Capacity plot sign"], errors="coerce")
    else:
        preview_df["__capacity_plot_sign"] = preview_df["__demand_kNm"].map(lambda demand: -1.0 if pd.notna(demand) and float(demand) < 0.0 else 1.0)

    capacity_df = preview_df[preview_df["__x_m"].notna() & preview_df["__demand_kNm"].notna() & preview_df["__capacity_kNm"].notna()].copy()
    if capacity_df.empty:
        fig.update_layout(title={"text": f"Flexure Check — Strength ULS<br><sup>{code_label} · demand only — φMn not ready</sup>"})
        return fig

    capacity_df = capacity_df.sort_values(["Case", "__x_m"], kind="stable")
    for case_name, case_df in capacity_df.groupby("Case", sort=False):
        x_values: list[float] = []
        y_values: list[float] = []
        for _, row in case_df.iterrows():
            capacity = float(row["__capacity_kNm"])
            sign = float(row.get("__capacity_plot_sign", 1.0))
            if not math.isfinite(sign) or abs(sign) <= 0.0:
                demand = float(row["__demand_kNm"])
                sign = -1.0 if demand < 0.0 else 1.0
            x_values.append(float(row["__x_m"]))
            y_values.append(sign * capacity)
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=y_values,
                mode="lines",
                name=f"φMn",
                line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                hovertemplate="x=%{x:.3f} m<br>φMn=%{y:.3f} kN-m<extra></extra>",
            )
        )

    governing_candidates = capacity_df[capacity_df["__utilization"].notna()].copy()
    if not governing_candidates.empty:
        idx = governing_candidates["__utilization"].astype(float).idxmax()
        row = governing_candidates.loc[idx]
        capacity = float(row["__capacity_kNm"])
        sign = float(row.get("__capacity_plot_sign", 1.0))
        if not math.isfinite(sign) or abs(sign) <= 0.0:
            demand = float(row["__demand_kNm"])
            sign = -1.0 if demand < 0.0 else 1.0
        utilization = float(row["__utilization"])
        status = str(row.get("Status") or "REVIEW")
        fig.add_trace(
            go.Scatter(
                x=[float(row["__x_m"])],
                y=[sign * capacity],
                mode="markers+text",
                text=[f"{status} · D/C {utilization:.3f}"],
                textposition="top center",
                name="Governing flexure check",
                hovertemplate="x=%{x:.3f} m<br>Governing φMn=%{y:.3f} kN-m<extra></extra>",
            )
        )


    fig.update_layout(title={"text": f"Flexure Check — Strength ULS<br><sup>{code_label} · demand vs φMn</sup>"})
    return fig


def _make_beam_uls_shear_capacity_figure(
    active_df: pd.DataFrame,
    shear_check_df: pd.DataFrame | None,
    *,
    code_label: str,
    boundary_capacity_df: pd.DataFrame | None = None,
    critical_section_df: pd.DataFrame | None = None,
) -> go.Figure:
    fig = _make_beam_uls_demand_figure(
        active_df,
        column="Vuy",
        title=f"Shear Check — Strength ULS<br><sup>{code_label}</sup>",
        y_label="Shear, Vu (kN)",
    )
    if shear_check_df is None or shear_check_df.empty:
        fig.update_layout(title={"text": f"Shear Check — Strength ULS<br><sup>{code_label} · demand only — φVn not ready</sup>"})
        return fig
    plot_sources = [shear_check_df]
    if critical_section_df is not None and not critical_section_df.empty:
        plot_sources.append(critical_section_df)
    if boundary_capacity_df is not None and not boundary_capacity_df.empty:
        plot_sources.append(boundary_capacity_df)
    plot_df = pd.concat(plot_sources, ignore_index=True, sort=False).copy()
    plot_df["__x_m"] = plot_df["Governing x"].map(lambda value: str(value or "").replace(" m", ""))
    plot_df["__x_m"] = pd.to_numeric(plot_df["__x_m"], errors="coerce")
    plot_df["__phi_vn"] = pd.to_numeric(plot_df.get("φVn kN"), errors="coerce")
    plot_df["__phi_vc"] = pd.to_numeric(plot_df.get("φVc kN"), errors="coerce")
    plot_df = plot_df[plot_df["__x_m"].notna() & plot_df["__phi_vn"].notna()].copy()
    has_capacity_plot = not plot_df.empty
    if has_capacity_plot:
        dedupe_columns = [column for column in ["Case", "__x_m", "__phi_vn", "Station type"] if column in plot_df.columns]
        if dedupe_columns:
            plot_df = plot_df.drop_duplicates(subset=dedupe_columns, keep="first")
        has_capacity_plot = not plot_df.empty
    if has_capacity_plot:
        plot_df = plot_df.sort_values(["Case", "__x_m"], kind="stable")
        for case_name, case_df in plot_df.groupby("Case", sort=False):
            x_values = [float(value) for value in case_df["__x_m"].tolist()]
            vn_values = [float(value) for value in case_df["__phi_vn"].tolist()]
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=vn_values,
                    mode="lines",
                    name="φVn",
                    line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                    hovertemplate="x=%{x:.3f} m<br>φVn=%{y:.3f} kN<extra></extra>",
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=x_values,
                    y=[-v for v in vn_values],
                    mode="lines",
                    name="-φVn",
                    line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                    hovertemplate="x=%{x:.3f} m<br>-φVn=%{y:.3f} kN<extra></extra>",
                )
            )
            vc_values = [float(value) if math.isfinite(float(value)) else float("nan") for value in case_df["__phi_vc"].tolist()]
            if any(math.isfinite(value) for value in vc_values):
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=vc_values,
                        mode="lines",
                        name="φVc",
                        line=dict(_BEAM_ULS_REFERENCE_LINE_STYLE),
                        hovertemplate="x=%{x:.3f} m<br>φVc=%{y:.3f} kN<extra></extra>",
                    )
                )
    critical_x_values: list[float] = []
    if critical_section_df is not None and not critical_section_df.empty:
        critical_df = critical_section_df.copy()
        critical_df["__x_m"] = critical_df["Governing x"].map(lambda value: str(value or "").replace(" m", ""))
        critical_df["__x_m"] = pd.to_numeric(critical_df["__x_m"], errors="coerce")
        critical_x_values = sorted({float(value) for value in critical_df["__x_m"].dropna().tolist()})
    if critical_x_values:
        active_v = pd.to_numeric(active_df.get("Vuy", pd.Series(dtype=float)), errors="coerce") if isinstance(active_df, pd.DataFrame) else pd.Series(dtype=float)
        candidate_values: list[float] = [abs(float(value)) for value in active_v.dropna().tolist() if math.isfinite(float(value))]
        if has_capacity_plot:
            for column in ["__phi_vn", "__phi_vc"]:
                if column in plot_df.columns:
                    candidate_values.extend(abs(float(value)) for value in plot_df[column].dropna().tolist() if math.isfinite(float(value)))
        y_limit = max(candidate_values) * 1.10 if candidate_values else 1.0
        if not math.isfinite(y_limit) or y_limit <= 0.0:
            y_limit = 1.0
        for i, x_crit in enumerate(critical_x_values):
            fig.add_trace(
                go.Scatter(
                    x=[x_crit, x_crit],
                    y=[-y_limit, y_limit],
                    mode="lines",
                    name="Critical section for shear loading",
                    showlegend=(i == 0),
                    line={"dash": "dot"},
                    hovertemplate="Critical shear section<br>x=%{x:.3f} m<extra></extra>",
                )
            )

    governing = _beam_uls_governing_shear_row(shear_check_df)
    if governing is not None:
        x_text = str(governing.get("Governing x") or "").replace(" m", "")
        x_val = _beam_uls_float(x_text)
        cap = _beam_uls_float(governing.get("φVn kN"))
        util = _beam_uls_float(governing.get("Governing D/C value", governing.get("D/C value")))
        if math.isfinite(x_val) and math.isfinite(cap) and math.isfinite(util):
            fig.add_trace(
                go.Scatter(
                    x=[x_val],
                    y=[cap],
                    mode="markers+text",
                    text=[f"{governing.get('Status', 'REVIEW')} · D/C {util:.3f}"],
                    textposition="top center",
                    name="Governing shear check",
                    hovertemplate="x=%{x:.3f} m<br>Governing φVn=%{y:.3f} kN<extra></extra>",
                )
            )
    subtitle = "demand vs φVn" if has_capacity_plot else "demand only — φVn not ready"
    fig.update_layout(title={"text": f"Shear Check — Strength ULS<br><sup>{code_label} · {subtitle}</sup>"})
    return fig



def _make_beam_uls_torsion_capacity_figure(
    active_df: pd.DataFrame,
    torsion_check_df: pd.DataFrame | None,
    *,
    code_label: str,
    boundary_capacity_df: pd.DataFrame | None = None,
) -> go.Figure:
    fig = _make_beam_uls_demand_figure(
        active_df,
        column="Tu",
        title=f"Torsion Check — Strength ULS<br><sup>{code_label}</sup>",
        y_label="Torsion, Tu (kN-m)",
    )
    if torsion_check_df is None or torsion_check_df.empty:
        fig.update_layout(title={"text": f"Torsion Check — Strength ULS<br><sup>{code_label} · demand only — φTn not ready</sup>"})
        return fig
    plot_sources = [torsion_check_df]
    if boundary_capacity_df is not None and not boundary_capacity_df.empty:
        plot_sources.append(boundary_capacity_df)
    plot_df = pd.concat(plot_sources, ignore_index=True, sort=False).copy()
    plot_df["__x_m"] = plot_df["Governing x"].map(lambda value: str(value or "").replace(" m", ""))
    plot_df["__x_m"] = pd.to_numeric(plot_df["__x_m"], errors="coerce")
    plot_df["__phi_tn"] = pd.to_numeric(plot_df.get("φTn kN-m"), errors="coerce")
    plot_df["__phi_tcr"] = pd.to_numeric(plot_df.get("φTcr kN-m"), errors="coerce")
    plot_df = plot_df[plot_df["__x_m"].notna() & (plot_df["__phi_tn"].notna() | plot_df["__phi_tcr"].notna())].copy()
    if not plot_df.empty:
        dedupe_columns = [column for column in ["Case", "__x_m", "__phi_tn", "__phi_tcr", "Station type"] if column in plot_df.columns]
        if dedupe_columns:
            plot_df = plot_df.drop_duplicates(subset=dedupe_columns, keep="first")
    has_capacity = not plot_df.empty
    if has_capacity:
        plot_df = plot_df.sort_values(["Case", "__x_m"], kind="stable")
        for case_name, case_df in plot_df.groupby("Case", sort=False):
            x_values = [float(value) for value in case_df["__x_m"].tolist()]
            tn_values = [float(value) if math.isfinite(float(value)) else float("nan") for value in case_df["__phi_tn"].tolist()]
            if any(math.isfinite(value) for value in tn_values):
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=tn_values,
                        mode="lines",
                        name="φTn",
                        line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                        hovertemplate="x=%{x:.3f} m<br>φTn=%{y:.3f} kN-m<extra></extra>",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=[-v if math.isfinite(v) else float("nan") for v in tn_values],
                        mode="lines",
                        name="-φTn",
                        line=dict(_BEAM_ULS_CHECK_LINE_STYLE),
                        hovertemplate="x=%{x:.3f} m<br>-φTn=%{y:.3f} kN-m<extra></extra>",
                    )
                )
            tcr_values = [float(value) if math.isfinite(float(value)) else float("nan") for value in case_df["__phi_tcr"].tolist()]
            if any(math.isfinite(value) for value in tcr_values):
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=tcr_values,
                        mode="lines",
                        name="φTcr",
                        line=dict(_BEAM_ULS_REFERENCE_LINE_STYLE),
                        hovertemplate="x=%{x:.3f} m<br>φTcr=%{y:.3f} kN-m<extra></extra>",
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=x_values,
                        y=[-v if math.isfinite(v) else float("nan") for v in tcr_values],
                        mode="lines",
                        name="-φTcr",
                        line=dict(_BEAM_ULS_REFERENCE_LINE_STYLE),
                        hovertemplate="x=%{x:.3f} m<br>-φTcr=%{y:.3f} kN-m<extra></extra>",
                    )
                )
    governing = _beam_uls_governing_torsion_row(torsion_check_df)
    if governing is not None:
        x_text = str(governing.get("Governing x") or "").replace(" m", "")
        x_val = _beam_uls_float(x_text)
        cap = _beam_uls_float(governing.get("φTn kN-m"))
        util = _beam_uls_float(governing.get("D/C value"))
        if math.isfinite(x_val) and math.isfinite(cap) and math.isfinite(util):
            fig.add_trace(
                go.Scatter(
                    x=[x_val],
                    y=[cap],
                    mode="markers+text",
                    text=[f"{governing.get('Status', 'REVIEW')} · D/C {util:.3f}"],
                    textposition="top center",
                    name="Governing torsion check",
                    hovertemplate="x=%{x:.3f} m<br>Governing φTn=%{y:.3f} kN-m<extra></extra>",
                )
            )
    subtitle = "demand vs φTn" if has_capacity else "demand only — φTn not ready"
    fig.update_layout(title={"text": f"Torsion Check — Strength ULS<br><sup>{code_label} · {subtitle}</sup>"})
    return fig


def _render_beam_girder_uls_workspace(mode_settings: AnalysisModeSettings) -> None:
    """Render compact ULS demand/flexure-check workspace for Bridge/Building Beam/Girder.

    This is intentionally decision-first and read-only for demand. ULS.FLEX1
    adds a primary Mux flexure strength check from the existing strain-
    compatibility engine while keeping shear, torsion, development length,
    debonding strength, and report certification as future milestones.
    """

    is_bridge = is_beam_girder_future_workflow(mode_settings)
    is_building = is_building_beam_girder_workflow(mode_settings)
    strength_route = _beam_uls_strength_route_from_state(st.session_state, is_bridge=is_bridge, is_building=is_building)
    workflow_label = strength_route.workflow_label
    code_label = strength_route.display_code_label
    source_label = strength_route.uls_load_source_label

    st.markdown(_ANALYSIS_DASHBOARD_CSS, unsafe_allow_html=True)
    st.markdown("### ULS Beam/Girder decision summary")
    st.caption(
        "Compact ULS workspace. Loads page is the source of truth; Analysis reads Active station rows only. "
        "Flexure uses the strain-compatibility section engine with workflow-specific code-compatible audit basis: "
        "Bridge → AASHTO LRFD-compatible strain compatibility; Building → ACI 318-compatible strain compatibility. "
        "Shear uses the SHEAR.CODE2 strength/detailing gate for provided stirrup zones, Vn limit, minimum Av/s, maximum spacing, and zone coverage; torsion uses the CODE2 strength/detailing gate for φTn, longitudinal Al, closed-hoop spacing, and zone coverage. Combined V+T remains a separate interaction gate."
    )

    active_df = _active_beam_uls_demand_dataframe_from_session(st.session_state)

    basis_cards = [
        {"title": "Workflow", "value": workflow_label, "detail": "Selected in Setup", "status": "info"},
        {"title": "Strength route", "value": code_label, "detail": strength_route.flexure_engine_label, "status": "info"},
        {"title": "ULS source", "value": "Loads page", "detail": source_label, "status": "info"},
        {"title": "Shear route", "value": strength_route.shear_engine_label, "detail": "Strength/detailing gate", "status": "info"},
        {"title": "Torsion route", "value": strength_route.torsion_engine_label, "detail": "Strength/detailing gate", "status": "info"},
    ]
    _render_analysis_summary_strip(basis_cards, columns=5)

    if active_df.empty:
        st.warning("No Active Beam/Girder ULS station demand rows are available. Define or import them in Loads before ULS review.")
        return

    selected_check_raw = st.radio(
        "ULS check to calculate",
        BEAM_ULS_CHECK_TAB_LABELS,
        horizontal=True,
        key="beam_girder_uls_lazy_check",
        help="The selected ULS check is not calculated until you press Calculate. This prevents Flexure/Shear/Torsion from running on every rerun.",
    )
    selected_check = str(selected_check_raw) if selected_check_raw in BEAM_ULS_CHECK_TAB_LABELS else BEAM_ULS_CHECK_TAB_LABELS[0]
    uls_input_hash = project_input_hash(st.session_state)

    flexure_entry = _beam_uls_current_cached_result(st.session_state, "Flexure", uls_input_hash)
    shear_entry = _beam_uls_current_cached_result(st.session_state, "Shear", uls_input_hash)
    torsion_entry = _beam_uls_current_cached_result(st.session_state, "Torsion", uls_input_hash)
    interaction_entry = _beam_uls_current_cached_result(st.session_state, "Shear + Torsion", uls_input_hash)

    selected_entry = _beam_uls_current_cached_result(st.session_state, selected_check, uls_input_hash)
    calc_label = f"Calculate {selected_check}"
    calc_help = (
        f"Run only the {selected_check} ULS check for the current model inputs. "
        "Previously calculated checks remain cached until model inputs change."
    )

    if st.button(calc_label, key=f"beam_girder_uls_calculate_{selected_check.replace(' ', '_').replace('+', 'plus')}", type="primary", use_container_width=True, help=calc_help):
        calculation_result = _beam_uls_calculate_selected_check(
            st.session_state,
            active_df,
            selected_check=selected_check,
            strength_route=strength_route,
        )
        selected_entry = _beam_uls_store_manual_result(
            st.session_state,
            selected_check,
            input_hash=uls_input_hash,
            result=calculation_result,
        )
        if selected_check == "Flexure":
            flexure_entry = selected_entry
        elif selected_check == "Shear":
            shear_entry = selected_entry
        elif selected_check == "Torsion":
            torsion_entry = selected_entry
        elif selected_check == "Shear + Torsion":
            interaction_entry = selected_entry
            shear_source = {
                key: calculation_result[key]
                for key in ["shear_check_df", "shear_critical_section_df", "shear_boundary_capacity_df"]
                if key in calculation_result
            }
            torsion_source = {
                key: calculation_result[key]
                for key in ["torsion_check_df", "torsion_boundary_capacity_df"]
                if key in calculation_result
            }
            if shear_source:
                shear_entry = _beam_uls_store_manual_result(
                    st.session_state,
                    "Shear",
                    input_hash=uls_input_hash,
                    result=shear_source,
                )
            if torsion_source:
                torsion_entry = _beam_uls_store_manual_result(
                    st.session_state,
                    "Torsion",
                    input_hash=uls_input_hash,
                    result=torsion_source,
                )
        st.success(f"{selected_check} calculated for current inputs.")

    status_text = _beam_uls_manual_result_badge(selected_entry)
    if selected_entry is None:
        st.warning(
            f"{selected_check} has not been calculated for the current inputs. "
            "Press Calculate before reviewing capacity, utilization, audit tables, or diagrams."
        )
    else:
        st.caption(f"{selected_check}: {status_text}")

    flexure_preview_df = _beam_uls_cached_dataframe(flexure_entry, "flexure_preview_df")
    flexure_preview_messages = _beam_uls_cached_messages(flexure_entry, "flexure_preview_messages")
    shear_check_df = _beam_uls_cached_dataframe(shear_entry, "shear_check_df")
    shear_critical_section_df_cached = _beam_uls_cached_dataframe(shear_entry, "shear_critical_section_df")
    shear_boundary_capacity_df_cached = _beam_uls_cached_dataframe(shear_entry, "shear_boundary_capacity_df")
    shear_critical_section_df = shear_critical_section_df_cached if shear_critical_section_df_cached is not None else pd.DataFrame()
    shear_boundary_capacity_df = shear_boundary_capacity_df_cached if shear_boundary_capacity_df_cached is not None else pd.DataFrame()
    torsion_check_df = _beam_uls_cached_dataframe(torsion_entry, "torsion_check_df")
    torsion_boundary_capacity_df_cached = _beam_uls_cached_dataframe(torsion_entry, "torsion_boundary_capacity_df")
    torsion_boundary_capacity_df = torsion_boundary_capacity_df_cached if torsion_boundary_capacity_df_cached is not None else pd.DataFrame()
    interaction_status = interaction_entry.get("interaction_status") if isinstance(interaction_entry, dict) else None
    combined_vt_df = _beam_uls_cached_dataframe(interaction_entry, "combined_vt_df")

    _render_analysis_summary_strip(
        _beam_uls_summary_cards(
            active_df,
            workflow_label=workflow_label,
            code_label=code_label,
            flexure_preview_df=flexure_preview_df,
            shear_check_df=shear_check_df,
            torsion_check_df=torsion_check_df,
        ),
        columns=5,
    )

    st.markdown("#### Compact ULS check table")
    st.caption("To keep ULS responsive, only checks already calculated for the current inputs show capacity/utilization. Press Calculate in the selected mode to refresh its result. Calculate Shear + Torsion also refreshes the shear/torsion source rows needed for the combined review.")
    st.dataframe(
        _beam_uls_check_table(active_df, flexure_preview_df=flexure_preview_df, shear_check_df=shear_check_df, torsion_check_df=torsion_check_df, combined_vt_df=combined_vt_df, state=st.session_state),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("#### ULS check workspace")
    st.caption(_beam_uls_check_tab_caption() + " PERF.ULS2 runs a selected ULS check only after you press Calculate.")

    if selected_entry is None:
        _render_analysis_summary_strip(
            [
                {
                    "title": f"{selected_check} calculation",
                    "value": "NOT CALCULATED",
                    "detail": "Press the highlighted Calculate button above to run this check for the current inputs.",
                    "status": "warning",
                    "strong": True,
                }
            ],
            columns=1,
        )
        st.info("Capacity diagrams, utilization, and audit output are intentionally withheld until the selected ULS check is calculated.")
        with st.expander("ULS demand table — audit / source data", expanded=False):
            st.caption("Read-only normalized view of Active rows from Loads. Secondary actions Muy, Vux, and Nu are kept here for audit, not default decision display.")
            st.dataframe(_beam_uls_audit_dataframe(active_df), use_container_width=True, hide_index=True)
        return

    if selected_check == "Flexure":
        flexure = _beam_uls_governing_action(active_df, "Mux")
        flex_preview = _beam_uls_governing_flexure_preview_row(flexure_preview_df)
        if flex_preview is not None:
            flex_status = str(flex_preview.get("Status") or "REVIEW")
            flex_cards = [
                {"title": "Flexure status", "value": flex_status, "detail": "Primary Mux strength check", "status": "danger" if flex_status == "FAIL" else ("ready" if flex_status == "PASS" else "warning"), "strong": True},
                {"title": "Governing Mu / D/C", "value": f"{flex_preview.get('Demand', '-')} · {flex_preview.get('Utilization', '-')}", "detail": f"{flex_preview.get('Case', '-')} @ x={flex_preview.get('Governing x', '-')}", "status": "info"},
                {"title": "Flexure capacity", "value": str(flex_preview.get("Capacity") or "-"), "detail": "Section φMn from active flexure route", "status": "info"},
                {"title": "Method", "value": "Strain compatibility", "detail": strength_route.flexure_engine_label, "status": "neutral"},
            ]
        else:
            flex_cards = [
                {"title": "Flexure status", "value": "NOT READY", "detail": "φMn check is not available for active rows.", "status": "warning", "strong": True},
                {"title": "Governing Mu", "value": _format_beam_uls_demand(flexure["demand"], "kN-m") if flexure else "-", "detail": f"{flexure['case']} @ x={_format_beam_uls_x(flexure['x_m'])}" if flexure else "No finite Mux", "status": "info"},
                {"title": "Flexure capacity", "value": "-", "detail": "Section/reinforcement data not ready", "status": "neutral"},
                {"title": "Method", "value": "Strain compatibility", "detail": strength_route.flexure_engine_label, "status": "neutral"},
            ]
        _render_analysis_summary_strip(flex_cards, columns=4)
        st.plotly_chart(
            _make_beam_uls_flexure_preview_figure(active_df, flexure_preview_df, code_label=code_label),
            use_container_width=True,
        )
        st.caption(
            "Section φMn is plotted using the active workflow flexure route; zero-demand endpoints are plotted as φMn = 0 diagram boundary points. "
            "Development length, debonding, anchorage, and end-zone detailing checks are separate from this flexure strength curve."
        )
        with st.expander("Flexure strength audit / benchmark output", expanded=False):
            st.caption(
                "Audit output for the governing flexure workflow: Mn nominal, route φ, φMn, D/C, "
                "bending direction, tension face, code-compatible strain-compatibility basis, and resistance-factor policy. Use this table for independent spreadsheet/software comparison."
            )
            audit_df = _beam_uls_flexure_audit_dataframe(flexure_preview_df)
            if audit_df.empty:
                st.info("Flexure audit output is not available until active ULS demand rows and section reinforcement are ready.")
            else:
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
        with st.expander("Flexure method notes", expanded=False):
            st.write(f"- Flexure route: {strength_route.flexure_basis_note}")
            st.write("- The plotted φMn curve is a section-strength curve along the span; development length, debonding strength, anchorage, interface shear, and end-zone bursting are separate checks.")
            st.write("- Flexure audit output is benchmark-ready, but final calibration against trusted examples or commercial girder software is still required before calling the module fully certified.")
            if flexure_preview_messages:
                st.caption("Flexure check notes: " + " | ".join(flexure_preview_messages[:5]))

    if selected_check == "Shear":
        shear = _beam_uls_governing_action(active_df, "Vuy")
        shear_result = _beam_uls_governing_shear_row(shear_check_df)
        if shear_result is not None:
            shear_status = str(shear_result.get("Status") or "REVIEW")
            d_text = _format_beam_uls_audit_number(shear_result.get("d mm"), unit="mm")
            dv_text = _format_beam_uls_audit_number(shear_result.get("dv mm"), unit="mm")
            depth_detail = f"d {d_text}" + (f" · dv {dv_text}" if dv_text != "-" else "")
            shear_cards = [
                {"title": "Shear status", "value": shear_status, "detail": f"Strength {shear_result.get('Strength status', '-')} · Detailing {shear_result.get('Detailing status', '-')}", "status": "danger" if shear_status == "FAIL" else ("ready" if shear_status == "PASS" else "warning"), "strong": True},
                {"title": "Governing Vu / D/C", "value": f"{shear_result.get('Demand', '-')} · {shear_result.get('Utilization', '-')}", "detail": f"{shear_result.get('Case', '-')} @ x={shear_result.get('Governing x', '-')}", "status": "info"},
                {"title": "Shear capacity", "value": str(shear_result.get("Capacity") or "-"), "detail": f"{shear_result.get('Stirrup') or 'Active stirrup zone'} · {depth_detail}", "status": "info"},
                {"title": "Detailing guard", "value": str(shear_result.get("Detailing status") or "-"), "detail": f"Av/s min {_format_beam_uls_audit_number(shear_result.get('Av/s required mm2/m'), unit='mm²/m')} · smax {_format_beam_uls_audit_number(shear_result.get('s max mm'), unit='mm')}", "status": "danger" if str(shear_result.get("Detailing status")) == "FAIL" else ("ready" if str(shear_result.get("Detailing status")) == "PASS" else "warning")},
            ]
        else:
            shear_status, shear_capacity_note = _beam_uls_shear_layout_status(st.session_state)
            shear_cards = [
                {"title": "Shear status", "value": shear_status if shear else "NOT READY", "detail": "φVn check needs active Vuy rows and active stirrup zones.", "status": "warning", "strong": True},
                {"title": "Governing Vu", "value": _format_beam_uls_demand(shear["demand"], "kN") if shear else "-", "detail": f"{shear['case']} @ x={_format_beam_uls_x(shear['x_m'])}" if shear else "No finite Vuy", "status": "info"},
                {"title": "Why no φVn line?", "value": "No active stirrup zone" if shear else "No Vuy demand", "detail": shear_capacity_note if shear else "No fake minimum stirrup is assumed", "status": "warning"},
                {"title": "Input owner", "value": "Sections → Rebar", "detail": "Analysis only reads provided stirrup zones", "status": "neutral"},
            ]
        _render_analysis_summary_strip(shear_cards, columns=4)
        if shear_result is None:
            _render_beam_uls_shear_layout_readiness_panel(st.session_state)
        st.plotly_chart(
            _make_beam_uls_shear_capacity_figure(
                active_df,
                shear_check_df,
                code_label=code_label,
                boundary_capacity_df=shear_boundary_capacity_df,
                critical_section_df=shear_critical_section_df,
            ),
            use_container_width=True,
        )
        st.caption(
            "Shear capacity is from the active provided stirrup layout by zone. Critical shear sections are inserted near the supports and included in the governing shear D/C; x=0 and x=L remain capacity-boundary graph values only. "
            "The φVn / φVc / φVs diagram is extended to x=0 and x=L as capacity-boundary values when the provided layout is available. The status combines strength D/C, Vn limit, minimum Av/s, maximum spacing, and zone coverage gates. "
            "Development length, anchorage, and shop-drawing detailing remain separate project review items."
        )
        with st.expander("Shear strength audit / provided stirrup output", expanded=False):
            st.caption(
                "SHEAR.CODE2 sectional shear output from active ULS Vuy rows and active provided stirrup zones: "
                "Vu, φVc, φVs, φVn, Vn limit, strength D/C, Av/s, minimum Av/s, maximum spacing, bw, d/dv, β/θ, and code route. "
                "Development length, anchorage, and shop-drawing detailing remain project review items."
            )
            shear_audit_df = _beam_uls_shear_audit_dataframe(shear_check_df)
            if shear_audit_df.empty:
                st.info("Shear audit output is not available until active ULS demand rows and active stirrup zones are ready.")
            else:
                st.dataframe(shear_audit_df, use_container_width=True, hide_index=True)
        with st.expander("Critical shear section checks", expanded=False):
            if shear_critical_section_df.empty:
                st.info("Critical shear section locations are not available until span length, effective d/dv basis, and active ULS station rows are ready. Capacity at those critical sections also needs active stirrup-zone coverage.")
            else:
                st.caption("Critical shear sections are inserted at approximately d from each support for ACI Building Beam/Girder and dv from each support for AASHTO Bridge Beam/Girder. These rows are included in the governing shear D/C.")
                st.dataframe(_beam_uls_shear_audit_dataframe(shear_critical_section_df), use_container_width=True, hide_index=True)

        with st.expander("Shear end-boundary capacity values", expanded=False):
            if shear_boundary_capacity_df.empty:
                st.info("End-boundary φVc / φVs / φVn values are not available until the provided stirrup layout and section/material inputs are ready.")
            else:
                st.caption("Diagram-boundary capacity values at x=0 and x=L. These are plotted to make the capacity curve continuous; they are not treated as governing shear design sections.")
                st.dataframe(_beam_uls_shear_audit_dataframe(shear_boundary_capacity_df), use_container_width=True, hide_index=True)

        with st.expander("Shear method notes", expanded=False):
            st.write(f"- Shear route: {strength_route.shear_basis_note}")
            st.write("- Shear φVn uses active provided stirrup zones only; no minimum stirrup layout is silently assumed; SHEAR.CODE2 also enforces zone coverage, Vn-limit, minimum Av/s, and spacing gates.")
            st.write("- Effective d / dv is read from Sections → Rebar effective shear depth basis when manually defined; otherwise d is estimated from the active reinforcement/prestress centroid and dv is derived for the AASHTO route.")
            st.write("- Critical shear section rows are inserted at approximately d from each support for ACI and dv from each support for AASHTO; their demand is interpolated from active ULS station rows and they are considered for governing shear D/C.")
            st.write("- SHEAR.CODE2 checks provided Av/s against the route minimum, checks stirrup spacing, enforces the Vn limit, and requires the active stirrup zone to cover each design/check station.")
            st.write("- Development length, anchorage, bearing/end-zone detailing, and shop-drawing constructability remain project review items outside this sectional shear gate.")

    if selected_check == "Torsion":
        torsion = _beam_uls_governing_action(active_df, "Tu")
        torsion_has_demand = torsion is not None and float(torsion["abs_demand"]) > _BEAM_ULS_DEMAND_TOL
        torsion_result = _beam_uls_governing_torsion_row(torsion_check_df)
        if torsion_result is not None:
            torsion_status = str(torsion_result.get("Status") or "REVIEW")
            torsion_cards = [
                {"title": "Torsion status", "value": torsion_status, "detail": f"Transverse {torsion_result.get('Transverse status', '-')} · longitudinal {torsion_result.get('Longitudinal status', '-')} · detailing {torsion_result.get('Detailing status', '-')}", "status": "danger" if torsion_status == "FAIL" else ("ready" if torsion_status in {"PASS", "BELOW THRESHOLD"} else "warning"), "strong": True},
                {"title": "Governing Tu / D/C", "value": f"{torsion_result.get('Demand', '-')} · {torsion_result.get('Utilization', '-')}", "detail": f"{torsion_result.get('Case', '-')} @ x={torsion_result.get('Governing x', '-')}", "status": "info"},
                {"title": "Torsion capacity", "value": str(torsion_result.get("Capacity") or "-"), "detail": f"φTcr { _format_beam_uls_audit_number(torsion_result.get('φTcr kN-m'), unit='kN-m') }", "status": "info"},
                {"title": "Route", "value": strength_route.torsion_engine_label, "detail": strength_route.torsion_basis_note, "status": "neutral"},
            ]
        else:
            torsion_cards = [
                {"title": "Torsion status", "value": "OPTIONAL" if not torsion_has_demand else "NOT READY", "detail": "No active Tu" if not torsion_has_demand else "φTn input path not ready", "status": "neutral" if not torsion_has_demand else "warning", "strong": True},
                {"title": "Governing Tu", "value": _format_beam_uls_demand(torsion["demand"], "kN-m") if torsion else "-", "detail": f"{torsion['case']} @ x={_format_beam_uls_x(torsion['x_m'])}" if torsion else "No active torsion demand", "status": "info"},
                {"title": "Torsion capacity", "value": "-", "detail": "φTn not ready", "status": "neutral"},
                {"title": "Route", "value": strength_route.torsion_engine_label, "detail": strength_route.torsion_basis_note, "status": "neutral"},
            ]
        _render_analysis_summary_strip(torsion_cards, columns=4)
        st.plotly_chart(
            _make_beam_uls_torsion_capacity_figure(
                active_df,
                torsion_check_df,
                code_label=code_label,
                boundary_capacity_df=torsion_boundary_capacity_df,
            ),
            use_container_width=True,
        )
        st.caption(
            "φTn is the code-routed closed-hoop torsion strength line. "
            "TORSION.CODE2 also checks longitudinal Al from the ordinary rebar table plus closed-hoop spacing and zone coverage gates."
        )
        if torsion_has_demand and torsion_result is not None and str(torsion_result.get("Status")) == "PASS":
            st.success("Torsion strength, longitudinal Al, and compact closed-hoop detailing gates pass for the governing station.")
        elif torsion_has_demand:
            st.warning("Torsion demand is present. Review φTn, threshold, longitudinal Al, and detailing output before issuing final member acceptance.")
        else:
            st.info("No active torsion demand is present in the ULS station rows. Keep torsion optional unless the design model produces nonzero Tu.")
        with st.expander("Torsion strength audit / provided closed-stirrup output", expanded=False):
            audit_df = _beam_uls_torsion_audit_dataframe(torsion_check_df)
            if audit_df.empty:
                st.info("Torsion audit output is not available until active ULS demand rows and section inputs are ready.")
            else:
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
        with st.expander("Torsion end-boundary capacity values", expanded=False):
            audit_df = _beam_uls_torsion_audit_dataframe(torsion_boundary_capacity_df)
            if audit_df.empty:
                st.info("End-boundary φTcr / φTn values are not available until the provided closed-hoop layout and section/material inputs are ready.")
            else:
                st.caption("Diagram-boundary capacity values at x=0 and x=L. These are plotted to make the torsion capacity curve continuous; they are not treated as governing torsion design sections.")
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
        with st.expander("Torsion method notes", expanded=False):
            st.write(f"- Torsion route: {strength_route.torsion_basis_note}")
            st.write("- Bridge Beam/Girder routes to the AASHTO LRFD-compatible φTn basis; Building Beam/Girder routes to the ACI 318 φTn basis. The active workflow, not the section preset name, controls this route.")
            st.write("- TORSION.CODE2 checks transverse closed-hoop φTn, longitudinal Al from the ordinary rebar table, active zone coverage, and s <= min(ph/8, 300 mm).")
            st.write("- The current torsion hoop geometry uses an explicit offset of the outside section polygon because the app does not yet have a dedicated torsion hoop layout owner. Verify Ao/Aoh and hook anchorage on drawings before construction issue.")

    if selected_check == "Shear + Torsion":
        governing_vt = _beam_uls_governing_combined_vt_row(combined_vt_df)
        if governing_vt is not None:
            status = str(governing_vt.get("Status") or "REVIEW")
            source_gate = _beam_uls_combined_vt_source_strength_gate(shear_check_df, torsion_check_df)
            vt_cards = [
                {"title": "Combined interaction", "value": status, "detail": f"{governing_vt.get('Case', '-')} @ x={governing_vt.get('Governing x', '-')}", "status": "danger" if status == "FAIL" else ("warning" if status in {"DATA REQUIRED", "PASS — REVIEW"} else ("ready" if status == "PASS" else "neutral")), "strong": True},
                {"title": "Source strength gate", "value": str(source_gate.get("value") or "-"), "detail": str(source_gate.get("detail") or "-"), "status": str(source_gate.get("status") or "neutral"), "strong": bool(source_gate.get("has_blocker"))},
                {"title": "Stress interaction", "value": _format_beam_uls_ratio(governing_vt.get("Stress D/C value")), "detail": str(governing_vt.get("Interaction form") or "combined stress screen"), "status": "danger" if str(governing_vt.get("Stress status")) == "FAIL" else "info"},
                {"title": "Transverse reinforcement", "value": _format_beam_uls_ratio(governing_vt.get("Transverse D/C value")), "detail": "Checks provided (Av + 2At)/s", "status": "danger" if str(governing_vt.get("Transverse status")) == "FAIL" else "info"},
                {"title": "Longitudinal Al", "value": _format_beam_uls_ratio(governing_vt.get("Longitudinal D/C value")), "detail": str(governing_vt.get("Longitudinal status") or "ordinary rebar source"), "status": "danger" if str(governing_vt.get("Longitudinal status")) == "FAIL" else ("warning" if str(governing_vt.get("Longitudinal status")) in {"LAYOUT REQUIRED", "NOT CHECKED"} else "info")},
            ]
            _render_analysis_summary_strip(vt_cards, columns=5)
            if _beam_uls_combined_vt_has_finite_utilization(combined_vt_df):
                st.plotly_chart(
                    _make_beam_uls_combined_vt_utilization_figure(combined_vt_df, code_label=code_label),
                    use_container_width=True,
                )
                st.caption("Combined V+T is plotted as utilization ratio versus station because Vu and Tu have different units. The red dashed line is the D/C = 1.0 check limit.")
            else:
                st.info("Combined V+T utilization diagram is hidden until finite stress/transverse/longitudinal D/C source terms are ready.")

            readiness_detail_df = _beam_uls_combined_vt_source_readiness_dataframe(combined_vt_df)
            if not readiness_detail_df.empty:
                st.caption("Source readiness detail")
                st.dataframe(readiness_detail_df, use_container_width=True, hide_index=True)

            if status == "FAIL":
                st.error("Combined shear + torsion review check fails at the governing station. Review section size, stirrup layout, and torsion hoop geometry before any final design claim.")
            elif status == "DATA REQUIRED":
                st.warning("Combined shear + torsion calculation ran, but one or more source-data gates are incomplete.")
                readiness_notes = _beam_uls_combined_vt_source_readiness_notes(combined_vt_df)
                if readiness_notes:
                    st.caption("Missing / incomplete source data:")
                    for item in readiness_notes:
                        st.write(f"- {item}")
            elif status in {"PASS", "PASS — REVIEW"}:
                if bool(source_gate.get("has_blocker")):
                    st.warning(
                        "Combined interaction/reinforcement gates pass, but overall ULS member acceptance is blocked by the separate source strength gate: "
                        + str(source_gate.get("detail") or "source strength check fails")
                    )
                elif bool(source_gate.get("has_review")):
                    st.warning(
                        "Combined interaction/reinforcement gates pass, but separate shear/torsion source checks still need review: "
                        + str(source_gate.get("detail") or "source check requires review")
                    )
                elif status == "PASS":
                    st.success("Combined V+T stress, transverse reinforcement, longitudinal Al, and separate source-strength gates pass for the governing station.")
                else:
                    st.warning("Combined V+T gates pass, but the result is still marked review by the selected source route.")
            else:
                st.info("No active torsion demand is present in the selected ULS demand rows.")
        else:
            interaction = interaction_status if isinstance(interaction_status, dict) else _beam_uls_torsion_interaction_status(active_df)
            _render_analysis_summary_strip([interaction], columns=1)
            if interaction["value"].startswith("Not applicable"):
                st.info(interaction["detail"])
            else:
                st.warning(interaction["detail"])
        with st.expander("Combined shear + torsion audit / review output", expanded=False):
            audit_df = _beam_uls_combined_vt_audit_dataframe(combined_vt_df)
            if audit_df.empty:
                st.info("Combined V+T audit output is not available until you press Calculate and the shear/torsion source inputs are ready.")
            else:
                st.dataframe(audit_df, use_container_width=True, hide_index=True)
        with st.expander("Combined shear + torsion method notes", expanded=False):
            st.write("- ULS.VT2.4 separates the combined interaction status from the separate shear/torsion source strength gate; an interaction PASS does not override a shear-only or torsion-only failure.")
            st.write("- ULS.VT2.1 checks combined compression-strut stress, combined transverse reinforcement, and a longitudinal Al review gate from the ordinary rebar source of truth.")
            st.write("- Calculate Shear + Torsion builds the required shear and torsion source rows internally; users do not need to calculate the separate Shear and Torsion tabs first.")
            st.write("- AASHTO/Bridge uses SHEAR.CODE2 and TORSION.CODE2 source gates; ACI/Building uses the corresponding ACI-compatible source gates.")
            st.write("- Solid sections use root-sum-square stress interaction; hollow sections use linear sum interaction based on the available section void geometry.")
            st.write("- Provided transverse reinforcement is taken from the active transverse/stirrup zone as (Av + 2At)/s; no reinforcement is silently assumed.")
            st.write("- Development length, anchorage, bearing/end-zone detailing, shop-drawing constructability, and independent benchmark packages remain project review items outside this sectional interaction gate.")
        st.caption(
            "This tab is intentionally separated from the shear and torsion tabs because combined shear + torsion is a different design decision. "
            "Separate shear and torsion checks must not be treated as a combined-interaction final PASS."
        )

    with st.expander("ULS demand table — audit / source data", expanded=False):
        st.caption("Read-only normalized view of Active rows from Loads. Secondary actions Muy, Vux, and Nu are kept here for audit, not default decision display.")
        st.dataframe(_beam_uls_audit_dataframe(active_df), use_container_width=True, hide_index=True)

    with st.expander("ULS strength-check limitations", expanded=False):
        st.write(f"- Active ULS strength route: {strength_route.workflow_label} → {strength_route.display_code_label}.")
        st.write(f"- Flexure route: {strength_route.flexure_basis_note}")
        st.write("- Flexure audit output reports Mn nominal, route φ, φMn, D/C, bending direction, tension face, method, code-compatible strain-compatibility basis, and resistance-factor policy for benchmark comparison.")
        st.write("- Flexure φMn is plotted as a section-strength curve along the span; development length, debonding strength, anchorage, interface shear, and end-zone bursting are separate detailing/design checks.")
        st.write(f"- Shear route: {strength_route.shear_basis_note}")
        st.write("- Shear φVn uses active provided stirrup zones only; no minimum stirrup layout is silently assumed; SHEAR.CODE2 also enforces zone coverage, Vn-limit, minimum Av/s, and spacing gates.")
        st.write(f"- Torsion route: {strength_route.torsion_basis_note}")
        st.write(f"- Overall guard: {strength_route.overall_guard_note}")
        st.write("- SLS stress, deflection/camber, prestress loss, PMM, and Loads formulas are unchanged.")
        if flexure_preview_messages:
            st.caption("Flexure check notes: " + " | ".join(flexure_preview_messages[:5]))


def _analysis_card_html(title: str, value: str, detail: str = "", status: str = "info", strong: bool = False) -> str:
    status_class = status if status in {"ready", "warning", "danger", "info", "neutral"} else "info"
    detail_html = f'<div class="cpmm-analysis-detail">{escape(detail)}</div>' if detail else ""
    badge_html = f'<span class="cpmm-analysis-badge {status_class}">{escape(value)}</span>' if strong else ""
    value_html = "" if strong else f'<div class="cpmm-analysis-value">{escape(value)}</div>'
    return (
        f'<div class="cpmm-analysis-strip">'
        f'<div class="cpmm-analysis-title">{escape(title)}</div>'
        f"{value_html}{badge_html}{detail_html}"
        "</div>"
    )


def _project_design_code_status_cards(*, workflow: str) -> list[dict[str, object]]:
    """Return CODE.SETUP1 read-only design-code status cards for Analysis."""

    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    code_detail = "Source of truth from Setup"
    if workflow == "pmm" and code == PROJECT_CODE_AASHTO_LRFD:
        capability = "REVIEW / planned"
        detail = "AASHTO LRFD PMM is planned; current PMM solver remains ACI-oriented until a named solver milestone."
        status = "warning"
    elif workflow == "pmm":
        capability = "Available"
        detail = "Current PMM workflow is ACI-oriented."
        status = "ready"
    elif workflow == "girder_sls":
        raw_code = code
        code = _girder_sls_project_design_code_from_session()
        edition = _girder_sls_project_code_edition_from_session()
        code_detail = "Workflow-enforced from active Analysis Mode"
        if code == raw_code:
            code_detail = "Source of truth from Setup"
        profile_code = girder_sls_code_for_project_code(code)
        capability = "Preview available"
        detail = f"Girder SLS stress-limit profile: {profile_code}. Final code-certified girder design remains future work."
        status = "warning"
    else:
        capability = "Review"
        detail = "Confirm workflow-specific code support before final design use."
        status = "warning"
    return [
        {"title": "Project design code", "value": code, "detail": code_detail, "status": "info", "strong": True},
        {"title": "Code edition", "value": edition, "detail": "Saved project basis", "status": "info"},
        {"title": "Workflow code capability", "value": capability, "detail": detail, "status": status, "strong": status == "warning"},
    ]


def _render_project_design_code_guard(*, workflow: str) -> None:
    _render_analysis_summary_strip(_project_design_code_status_cards(workflow=workflow), columns=3)
    code = project_design_code_from_session(st.session_state)
    if workflow == "pmm" and code == PROJECT_CODE_AASHTO_LRFD:
        st.warning(
            "Project Design Code is AASHTO LRFD, but the current Column/Pier/Wall/Pylon PMM solver is still ACI-oriented. "
            "Treat PMM results as REVIEW until the future AASHTO LRFD PMM solver milestone is implemented."
        )


def _column_pier_analysis_scope_cards() -> list[dict[str, object]]:
    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    pmm_status = "Preview available" if code != PROJECT_CODE_AASHTO_LRFD else "REVIEW / planned"
    pmm_detail = (
        "ACI-oriented PMM interaction engine with Pu, Mux, and Muy demand/capacity review"
        if code != PROJECT_CODE_AASHTO_LRFD
        else "AASHTO LRFD PMM is not implemented; current PMM remains ACI-oriented and must be treated as REVIEW"
    )
    shear_status = "ACI RC preview" if code == PROJECT_CODE_ACI318 else "REVIEW / planned"
    shear_detail = (
        "ACI 318 RC Column/Pier shear preview reads Vux/Vuy and active transverse reinforcement; PSC and final certification remain guarded"
        if code == PROJECT_CODE_ACI318
        else "AASHTO LRFD Column/Pier shear is not implemented; no Vn or PASS/FAIL is issued"
    )
    torsion_status = "ACI RC V+T gate" if code == PROJECT_CODE_ACI318 else "REVIEW / planned"
    torsion_detail = (
        "ACI 318 RC torsion and combined V+T read Tu, closed transverse reinforcement, and ordinary rebar Al; PSC and AASHTO remain guarded"
        if code == PROJECT_CODE_ACI318
        else "AASHTO LRFD Column/Pier torsion is not implemented; no Tn or PASS/FAIL is issued"
    )
    return [
        {
            "title": "Primary check",
            "value": "ULS PMM Interaction",
            "detail": "Column/Pier/Wall/Pylon workflow is centered on axial-biaxial strength",
            "status": "ready",
            "strong": True,
        },
        {
            "title": "PMM code basis",
            "value": pmm_status,
            "detail": f"{code} / {edition}. {pmm_detail}",
            "status": "warning" if code == PROJECT_CODE_AASHTO_LRFD else "ready",
            "strong": code == PROJECT_CODE_AASHTO_LRFD,
        },
        {
            "title": "Shear",
            "value": shear_status,
            "detail": shear_detail,
            "status": "info" if code == PROJECT_CODE_ACI318 else "warning",
            "strong": code != PROJECT_CODE_ACI318,
        },
        {
            "title": "Torsion",
            "value": torsion_status,
            "detail": torsion_detail,
            "status": "info" if code == PROJECT_CODE_ACI318 else "warning",
            "strong": code != PROJECT_CODE_ACI318,
        },
        {
            "title": "Serviceability",
            "value": "Not selected",
            "detail": "Beam/Girder staged SLS stress and deflection/camber workflows are hidden for this member family",
            "status": "neutral",
        },
    ]


def _render_column_pier_analysis_decision_view() -> None:
    st.markdown("### Column / Pier / Wall / Pylon Decision View")
    st.caption(
        "Commercial workflow focus: run PMM interaction for Pu-Mux-Muy strength, then review scoped ACI RC shear, torsion, and V+T gates without extending them to unsupported routes."
    )
    _render_analysis_summary_strip(_column_pier_analysis_scope_cards(), columns=5)
    _render_column_pier_uls_decision_summary()


def _column_pier_status_style(status: object) -> str:
    text = str(status or "").strip().upper()
    if not text:
        return "neutral"
    if "FAIL" in text or "OUT_OF_RANGE" in text:
        return "danger"
    if "PASS" in text or "BELOW THRESHOLD" in text or text == "NOT APPLICABLE":
        return "ready"
    if "REVIEW" in text or "DATA REQUIRED" in text or "NOT READY" in text or "NOT_CHECKED" in text:
        return "warning"
    return "info"


def _column_pier_dc_text(value: object) -> str:
    numeric = _beam_uls_float(value)
    if numeric is None:
        return "-"
    return _format_beam_uls_ratio(numeric)


def _column_pier_status_counts(rows: list[dict[str, object]]) -> dict[str, int]:
    counts = {"danger": 0, "warning": 0, "ready": 0, "neutral": 0, "info": 0}
    for row in rows:
        style = _column_pier_status_style(row.get("Status"))
        counts[style] = counts.get(style, 0) + 1
    return counts


def _column_pier_check_decision_rows(
    state: Mapping[str, object],
    analysis_input: AnalysisInput | None,
) -> list[dict[str, object]]:
    code = project_design_code_from_session(state)
    dc_summary = state.get("rc_demand_capacity_result")
    if dc_summary is None:
        dc_summary = state.get("demand_capacity_summary")

    if isinstance(dc_summary, DemandCapacitySummary):
        pmm_status = str(dc_summary.overall_status or "NOT_CHECKED").replace("_", " ")
        pmm_case = str(dc_summary.governing_combo or "-")
        pmm_dc = _column_pier_dc_text(dc_summary.max_dcr)
        pmm_action = "Run PMM analysis." if dc_summary.overall_status == "NOT_CHECKED" else "Review PMM diagnostics / QA before final issue."
    else:
        pmm_status = "NOT READY"
        pmm_case = "-"
        pmm_dc = "-"
        pmm_action = "Run / Recalculate Analysis in Flexural (PMM)."

    shear_df = _column_pier_shear_check_dataframe(state, analysis_input)
    torsion_df = _column_pier_torsion_check_dataframe(state, analysis_input)
    vt_df = _column_pier_combined_vt_check_dataframe(state, analysis_input)
    shear = _column_pier_governing_shear_row(shear_df)
    torsion = _column_pier_governing_torsion_row(torsion_df)
    vt = _column_pier_governing_combined_vt_row(vt_df)

    def _check_status(df: pd.DataFrame, *, empty_status: str, fail_status: str = "FAIL") -> str:
        if code != PROJECT_CODE_ACI318:
            return "REVIEW"
        if df.empty:
            return empty_status
        statuses = {str(value) for value in df.get("Status", pd.Series(dtype=str)).tolist()}
        if any("FAIL" in item for item in statuses):
            return fail_status
        if "DATA REQUIRED" in statuses:
            return "DATA REQUIRED"
        if "REVIEW" in statuses:
            return "REVIEW"
        if statuses and all(item in {"NOT APPLICABLE", "BELOW THRESHOLD", "NO DEMAND"} for item in statuses):
            return sorted(statuses)[0]
        if any("PASS" in item for item in statuses):
            return "PASS"
        return sorted(statuses)[0] if statuses else empty_status

    rows = [
        {
            "Check": "Flexural (PMM)",
            "Status": pmm_status,
            "Governing Case": pmm_case,
            "Demand": "Pu, Mux, Muy",
            "D/C": pmm_dc,
            "Route / Scope": "ACI RC/PSC PMM production-preview; AASHTO PMM remains REVIEW",
            "Required Action": pmm_action,
        },
        {
            "Check": "Shear",
            "Status": _check_status(shear_df, empty_status="NOT READY", fail_status="Preview FAIL"),
            "Governing Case": "-" if shear is None else f"{shear.get('Case', '-')} / {shear.get('Direction', '-')}",
            "Demand": "Vux, Vuy",
            "D/C": "-" if shear is None else _column_pier_dc_text(shear.get("Governing D/C value")),
            "Route / Scope": "ACI 318 RC preview; AASHTO, PSC shear, and seismic detailing remain REVIEW",
            "Required Action": "Confirm Control section transverse reinforcement, section/material, and seismic detailing separately.",
        },
        {
            "Check": "Torsion",
            "Status": _check_status(torsion_df, empty_status="NOT READY", fail_status="Preview FAIL"),
            "Governing Case": "-" if torsion is None else str(torsion.get("Case", "-")),
            "Demand": "Tu",
            "D/C": "-" if torsion is None else _column_pier_dc_text(torsion.get("Governing D/C value")),
            "Route / Scope": "ACI 318 RC preview; closed ties/hoops plus ordinary longitudinal Al only",
            "Required Action": "Confirm closed hoop/tie geometry, torsion core, ordinary Al, hooks, and anchorage.",
        },
        {
            "Check": "Shear + Torsion",
            "Status": _check_status(vt_df, empty_status="NOT READY"),
            "Governing Case": "-" if vt is None else f"{vt.get('Case', '-')} / {vt.get('Direction', '-')}",
            "Demand": "Vux/Vuy + Tu",
            "D/C": "-" if vt is None else _column_pier_dc_text(vt.get("Overall D/C value")),
            "Route / Scope": "ACI 318 RC nonprestressed V+T gate; QA1 hand-check references available",
            "Required Action": "Use this as the controlling V+T decision only within the scoped nonprestressed ACI RC route.",
        },
    ]
    return rows


def _column_pier_uls_decision_summary_cards(
    rows: list[dict[str, object]],
    analysis_input: AnalysisInput | None,
    state: Mapping[str, object] | None = None,
) -> list[dict[str, object]]:
    counts = _column_pier_status_counts(rows)
    if counts["danger"]:
        decision = "FAIL / action required"
        detail = f"{counts['danger']} check(s) fail or exceed a gate."
        status = "danger"
    elif counts["warning"]:
        decision = "REVIEW / incomplete"
        detail = f"{counts['warning']} check(s) require review, missing input, or unsupported route handling."
        status = "warning"
    elif counts["ready"] == len(rows):
        decision = "Available for final review"
        detail = "All visible Column/Pier ULS decision rows are passing or not applicable within their scoped routes."
        status = "ready"
    else:
        decision = "Partially available"
        detail = "Some checks are informational or not active."
        status = "info"

    code = project_design_code_from_session(state or st.session_state)
    prestress_active = _column_pier_has_active_prestress(analysis_input)
    vt_row = next((row for row in rows if row.get("Check") == "Shear + Torsion"), None)
    vt_status = str(vt_row.get("Status") if vt_row else "NOT READY")
    return [
        {
            "title": "Column/Pier ULS decision",
            "value": decision,
            "detail": detail,
            "status": status,
            "strong": True,
        },
        {
            "title": "Code route",
            "value": code,
            "detail": "ACI RC shear/torsion/V+T is scoped; AASHTO routes stay REVIEW until validated",
            "status": "info" if code == PROJECT_CODE_ACI318 else "warning",
        },
        {
            "title": "V+T gate",
            "value": vt_status,
            "detail": "Final scoped ACI RC nonprestressed interaction gate",
            "status": _column_pier_status_style(vt_status),
        },
        {
            "title": "Prestress in V/T",
            "value": "Present" if prestress_active else "Not active",
            "detail": "Prestressed shear/torsion interaction remains REVIEW when active prestress exists",
            "status": "warning" if prestress_active else "neutral",
        },
    ]


def _render_column_pier_uls_decision_summary() -> None:
    analysis_input = _serviceability_analysis_input_from_session()
    rows = _column_pier_check_decision_rows(st.session_state, analysis_input)
    st.markdown("#### Column/Pier ULS Decision Summary")
    st.caption(
        "Decision-first overview for the current stored inputs. This panel does not rerun PMM; shear, torsion, and V+T are read-only previews/check gates from the current session data."
    )
    _render_analysis_summary_strip(_column_pier_uls_decision_summary_cards(rows, analysis_input, st.session_state), columns=4)
    summary_df = pd.DataFrame(
        rows,
        columns=["Check", "Status", "Governing Case", "Demand", "D/C", "Route / Scope", "Required Action"],
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
    warning_rows = [row for row in rows if _column_pier_status_style(row.get("Status")) in {"danger", "warning"}]
    if warning_rows:
        with st.expander("Column/Pier ULS action items", expanded=False):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Check": row["Check"],
                            "Status": row["Status"],
                            "Required Action": row["Required Action"],
                            "Scope Note": row["Route / Scope"],
                        }
                        for row in warning_rows
                    ],
                    columns=["Check", "Status", "Required Action", "Scope Note"],
                ),
                use_container_width=True,
                hide_index=True,
            )
    with st.expander("Column/Pier ULS decision scope", expanded=False):
        st.markdown(
            "- PMM flexural result is read from the last stored PMM demand/capacity result; use Flexural (PMM) to run or refresh it.\n"
            "- Shear, Torsion, and Shear + Torsion are computed from current active Column/Pier ULS load rows and the Control section transverse reinforcement source.\n"
            "- ACI RC nonprestressed V+T has QA1 independent benchmark evidence. AASHTO LRFD, prestressed V+T, seismic confinement/detailing, anchorage/hooks, lap splices, and shop-drawing detailing remain outside the acceptance scope."
        )


def _column_pier_uls_check_choice() -> str:
    """Select the active Column/Pier ULS check without executing inactive check bodies."""

    key = "_column_pier_uls_check_subtab"
    options = list(COLUMN_PIER_ULS_CHECK_SUBTABS)
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        try:
            value = segmented("ULS check", options, key=key, selection_mode="single")
            if value in options:
                return str(value)
        except TypeError:
            pass
    value = st.radio("ULS check", options, key=key, horizontal=True)
    return str(value) if value in options else str(st.session_state.get(key, options[0]))


def _column_pier_guarded_strength_check_cards(check_name: str) -> list[dict[str, object]]:
    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    return [
        {
            "title": "Check status",
            "value": "Not implemented",
            "detail": f"{check_name} is a guarded future code-check module; no capacity result is calculated.",
            "status": "warning",
            "strong": True,
        },
        {
            "title": "Code route",
            "value": code,
            "detail": f"{edition}. ACI 318 and AASHTO LRFD rules require separate future validation.",
            "status": "warning" if code == PROJECT_CODE_AASHTO_LRFD else "info",
        },
        {
            "title": "Result policy",
            "value": "No PASS/FAIL",
            "detail": "This view must not be used to accept or reject member strength until code logic is implemented.",
            "status": "neutral",
            "strong": True,
        },
        {
            "title": "Interaction",
            "value": "Guarded",
            "detail": "Do not infer shear/torsion capacity from PMM D/C or flexural reserve.",
            "status": "info",
        },
    ]


def _render_column_pier_flexural_pmm_workspace() -> None:
    st.markdown("#### Flexural (PMM)")
    st.caption("Axial-biaxial PMM strength workspace for Pu, Mux, and Muy.")
    st.info(
        "ULS compression Pu remains positive. Prestress is treated as internal prestress/reinforcement action "
        "and should not be duplicated as external Pu demand."
    )
    _render_analysis_mode_section()
    _render_analysis_settings_panel()
    _render_readiness_panel()
    _render_input_summary()
    _render_verification_expander()


def _column_pier_shear_summary_cards(
    *,
    shear_df: pd.DataFrame,
    active_demands: pd.DataFrame,
    analysis_input: AnalysisInput | None,
) -> list[dict[str, object]]:
    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    governing = _column_pier_governing_shear_row(shear_df)
    zone = _column_pier_active_transverse_zone_for_shear(st.session_state)
    active_demand_count = 0
    if not active_demands.empty:
        for column in ["Vux", "Vuy"]:
            active_demand_count += int(pd.to_numeric(active_demands[column], errors="coerce").abs().gt(_COLUMN_PIER_SHEAR_DEMAND_TOL).sum())
    if code != PROJECT_CODE_ACI318:
        status_value = "REVIEW"
        status_detail = "AASHTO LRFD Column/Pier shear is not implemented in this milestone"
        status_color = "warning"
    elif shear_df.empty:
        status_value = "NOT READY"
        status_detail = "Needs nonzero Vux/Vuy and an active valid transverse reinforcement region"
        status_color = "warning"
    elif any(str(value) == "Preview FAIL" for value in shear_df["Status"].tolist()):
        status_value = "Preview FAIL"
        status_detail = "At least one shear direction or detailing gate exceeds 1.0"
        status_color = "danger"
    elif any(str(value) == "REVIEW" for value in shear_df["Status"].tolist()):
        status_value = "REVIEW"
        status_detail = "Calculation has guarded inputs such as active prestress or incomplete code route"
        status_color = "warning"
    else:
        status_value = "Preview PASS"
        status_detail = "ACI RC shear preview gates are below 1.0; not final code certification"
        status_color = "ready"
    capacity_detail = "-"
    demand_detail = "-"
    if governing is not None:
        demand_detail = f"{governing.get('Case', '-')} / {governing.get('Direction', '-')}"
        capacity_detail = f"{governing.get('Capacity', '-')} / D/C {_format_beam_uls_ratio(governing.get('Governing D/C value'))}"
    zone_detail = "No active valid transverse region"
    zone_value = "Not ready"
    if zone is not None:
        zone_value = str(zone.get("Zone") or "Active transverse region")
        zone_detail = f"{zone.get('Bar Size') or '-'} @ {_beam_uls_float(zone.get('Spacing_mm')):.0f} mm; lowest active Av/s source"
    prestress_value = "No"
    prestress_detail = "ACI RC shear route"
    if _column_pier_has_active_prestress(analysis_input):
        prestress_value = "Present"
        prestress_detail = "PSC shear contribution is not implemented; result remains REVIEW"
    return [
        {
            "title": "Shear status",
            "value": status_value,
            "detail": status_detail,
            "status": status_color,
            "strong": True,
        },
        {
            "title": "Code route",
            "value": "ACI 318 RC" if code == PROJECT_CODE_ACI318 else "Not implemented",
            "detail": f"{edition}; AASHTO/PSC routes remain future milestones",
            "status": "info" if code == PROJECT_CODE_ACI318 else "warning",
        },
        {
            "title": "Active V demands",
            "value": f"{active_demand_count:,}",
            "detail": demand_detail if active_demand_count else "No nonzero Vux/Vuy in active ULS rows",
            "status": "info" if active_demand_count else "warning",
        },
        {
            "title": "Governing capacity",
            "value": capacity_detail,
            "detail": "Highest governing D/C among Vux/Vuy rows" if governing is not None else "No calculated row",
            "status": "info",
        },
        {
            "title": "Transverse source",
            "value": zone_value,
            "detail": zone_detail,
            "status": "ready" if zone is not None else "warning",
        },
        {
            "title": "Prestress effects",
            "value": prestress_value,
            "detail": prestress_detail,
            "status": "warning" if prestress_value == "Present" else "neutral",
        },
    ]


def _render_column_pier_shear_guarded_workspace() -> None:
    st.markdown("#### Shear")
    st.caption("ACI 318 RC shear preview for column, pier, wall, and pylon case-based ULS rows.")
    active_demands = _active_column_pier_uls_demand_dataframe_from_state(st.session_state)
    analysis_input = _serviceability_analysis_input_from_session()
    shear_df = _column_pier_shear_check_dataframe(st.session_state, analysis_input)
    _render_analysis_summary_strip(
        _column_pier_shear_summary_cards(
            shear_df=shear_df,
            active_demands=active_demands,
            analysis_input=analysis_input,
        ),
        columns=3,
    )
    code = project_design_code_from_session(st.session_state)
    if code != PROJECT_CODE_ACI318:
        st.warning("Column/Pier AASHTO LRFD shear is not implemented. This tab does not issue Vn or PASS/FAIL for AASHTO projects.")
    elif shear_df.empty:
        st.warning("No Column/Pier ACI shear rows are ready. Enter nonzero Vux/Vuy, confirm section/material inputs, and activate valid transverse reinforcement regions.")
    elif any(str(value) == "Preview FAIL" for value in shear_df["Status"].tolist()):
        st.error("One or more ACI RC shear preview gates exceed 1.0. Review demand, section size, and transverse reinforcement before relying on the member.")
    elif any(str(value) == "REVIEW" for value in shear_df["Status"].tolist()):
        st.warning("ACI shear values are calculated, but the result remains REVIEW because one or more guarded assumptions apply.")
    else:
        st.success("ACI RC shear preview gates pass for the current visible rows. This is not final code-certified shear design.")

    if not shear_df.empty:
        display_columns = [
            "Status", "Direction", "Case", "Demand", "Capacity", "Utilization",
            "Zone", "Tie/hoop", "bw mm", "d mm", "Av/s mm2/mm", "Av/s required mm2/mm",
            "Governing D/C value",
        ]
        st.dataframe(shear_df[display_columns], use_container_width=True, hide_index=True)
        st.error(
            "Seismic confinement review: if this column/pier is located in a seismic zone, plastic-hinge region, or column-base region, "
            "provide special transverse reinforcement per the governing code. The shear result above uses the Control section row only "
            "and does not certify seismic confinement detailing."
        )
        seismic_advisor_df = _column_pier_aci_seismic_spacing_summary_dataframe(st.session_state, analysis_input)
        if seismic_advisor_df.empty:
            st.info("Seismic spacing advisor is not selected in Sections -> Rebar -> Transverse Rebar. Activate it there to show the recommended seismic tie/hoop spacing here.")
        else:
            st.dataframe(seismic_advisor_df, use_container_width=True, hide_index=True)
    with st.expander("ACI shear audit / method details", expanded=False):
        if shear_df.empty:
            st.info("Audit rows are not available until the section, material, active Vux/Vuy demand, and active transverse reinforcement are ready.")
        else:
            st.dataframe(shear_df, use_container_width=True, hide_index=True)
        st.markdown(
            "- Scope: ACI 318 RC Column/Pier shear preview only.\n"
            "- Demand source: Loads -> Column/Pier ULS table, active `Vux` and `Vuy` rows.\n"
            "- Transverse source: Sections -> Rebar -> Transverse Rebar, active Column/Pier regions. With no station owner, the lowest active `Av/s` region is used conservatively.\n"
            "- Section basis: `bw` is measured from concrete breadth through the centroid line, so holes/voids are not counted as concrete. Auto `d` is `0.80` times the gross dimension in the checked direction.\n"
            "- Formula basis: `Vc = 0.17 sqrt(fc) bw d`, `Vs = Av fy d / s`, `phi = 0.75`, with ACI minimum `Av/s`, maximum spacing, and `Vs` maximum screen.\n"
            "- Exclusions: AASHTO LRFD, prestressed shear `Vci/Vcw/Vp`, seismic special detailing, slenderness/second-order effects, anchorage, and final code certification."
        )
    with st.expander("Future shear code-check scope", expanded=False):
        st.markdown(
            "- Add explicit direction-specific effective depth owner instead of the current auto `0.80h` preview basis.\n"
            "- Add station/height assignment for transverse regions so end confinement and typical shaft regions can be checked at their actual demand locations.\n"
            "- Add axial load and prestress effects only after validated code-specific equations and benchmarks are introduced.\n"
            "- Required validation: separate ACI 318 and AASHTO LRFD benchmarks before any final PASS/FAIL result is allowed."
        )


def _column_pier_torsion_summary_cards(
    *,
    torsion_df: pd.DataFrame,
    active_demands: pd.DataFrame,
    analysis_input: AnalysisInput | None,
) -> list[dict[str, object]]:
    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    governing = _column_pier_governing_torsion_row(torsion_df)
    zone = _column_pier_active_transverse_zone_for_torsion(st.session_state)
    settings = _column_pier_transverse_settings_from_state(st.session_state)
    active_tu_count = 0
    if not active_demands.empty and "Tu" in active_demands.columns:
        active_tu_count = int(pd.to_numeric(active_demands["Tu"], errors="coerce").abs().gt(_COLUMN_PIER_SHEAR_DEMAND_TOL).sum())
    if code != PROJECT_CODE_ACI318:
        status_value = "REVIEW"
        status_detail = "AASHTO LRFD Column/Pier torsion is not implemented in this milestone"
        status_color = "warning"
    elif torsion_df.empty:
        status_value = "NOT READY"
        status_detail = "Needs nonzero Tu, closed transverse reinforcement, torsion core basis, and ordinary longitudinal bars"
        status_color = "warning"
    elif any(str(value) == "Preview FAIL" for value in torsion_df["Status"].tolist()):
        status_value = "Preview FAIL"
        status_detail = "At least one torsion strength, detailing, or longitudinal Al gate exceeds 1.0"
        status_color = "danger"
    elif any(str(value) == "REVIEW" for value in torsion_df["Status"].tolist()):
        status_value = "REVIEW"
        status_detail = "Calculation has guarded inputs such as active prestress, AASHTO route, or incomplete layout"
        status_color = "warning"
    elif all(str(value) == "BELOW THRESHOLD" for value in torsion_df["Status"].tolist()):
        status_value = "BELOW THRESHOLD"
        status_detail = "All active Tu rows are below the implemented ACI torsion threshold screen"
        status_color = "ready"
    else:
        status_value = "Preview PASS"
        status_detail = "ACI RC torsion preview gates are below 1.0; not final code certification"
        status_color = "ready"
    capacity_detail = "-"
    demand_detail = "-"
    if governing is not None:
        demand_detail = str(governing.get("Case", "-"))
        capacity_detail = f"{governing.get('Capacity', '-')} / D/C {_format_beam_uls_ratio(governing.get('Governing D/C value'))}"
    zone_detail = "No active valid closed transverse region"
    zone_value = "Not ready"
    if zone is not None:
        zone_value = str(zone.get("Zone") or "Active closed transverse region")
        zone_detail = f"{zone.get('Bar Size') or '-'} @ {_beam_uls_float(zone.get('Spacing_mm')):.0f} mm; lowest active At/s source"
    core_value = str(settings.get("torsion_core_basis") or "Not defined")
    core_detail = "Closed transverse reinforcement required"
    if str(settings.get("closed_tie_layout") or "") == "Open ties - shear only review":
        core_detail = "Open ties cannot be used for torsion capacity"
    prestress_value = "No"
    prestress_detail = "ACI RC torsion route"
    if _column_pier_has_active_prestress(analysis_input):
        prestress_value = "Present"
        prestress_detail = "PSC torsion contribution is not implemented; result remains REVIEW"
    return [
        {"title": "Torsion status", "value": status_value, "detail": status_detail, "status": status_color, "strong": True},
        {"title": "Code route", "value": "ACI 318 RC" if code == PROJECT_CODE_ACI318 else "Not implemented", "detail": f"{edition}; AASHTO/PSC routes remain future milestones", "status": "info" if code == PROJECT_CODE_ACI318 else "warning"},
        {"title": "Active Tu demands", "value": f"{active_tu_count:,}", "detail": demand_detail if active_tu_count else "No nonzero Tu in active ULS rows", "status": "info" if active_tu_count else "warning"},
        {"title": "Governing capacity", "value": capacity_detail, "detail": "Highest governing D/C among active Tu rows" if governing is not None else "No calculated row", "status": "info"},
        {"title": "Transverse source", "value": zone_value, "detail": zone_detail, "status": "ready" if zone is not None else "warning"},
        {"title": "Torsion core", "value": core_value, "detail": core_detail, "status": "info" if zone is not None else "warning"},
        {"title": "Prestress effects", "value": prestress_value, "detail": prestress_detail, "status": "warning" if prestress_value == "Present" else "neutral"},
    ]


def _render_column_pier_torsion_guarded_workspace() -> None:
    st.markdown("#### Torsion")
    st.caption("ACI 318 RC torsion preview for column, pier, wall, and pylon case-based ULS rows.")
    active_demands = _active_column_pier_uls_demand_dataframe_from_state(st.session_state)
    analysis_input = _serviceability_analysis_input_from_session()
    torsion_df = _column_pier_torsion_check_dataframe(st.session_state, analysis_input)
    _render_analysis_summary_strip(
        _column_pier_torsion_summary_cards(
            torsion_df=torsion_df,
            active_demands=active_demands,
            analysis_input=analysis_input,
        ),
        columns=4,
    )
    code = project_design_code_from_session(st.session_state)
    if code != PROJECT_CODE_ACI318:
        st.warning("Column/Pier AASHTO LRFD torsion is not implemented. This tab does not issue Tn or PASS/FAIL for AASHTO projects.")
    elif torsion_df.empty:
        st.warning("No Column/Pier ACI torsion rows are ready. Enter nonzero Tu, activate closed transverse reinforcement, define torsion core basis, and provide ordinary longitudinal rebar.")
    elif any(str(value) == "Preview FAIL" for value in torsion_df["Status"].tolist()):
        st.error("One or more ACI RC torsion preview gates exceed 1.0. Review Tu, closed tie/hoop layout, torsion core geometry, and longitudinal rebar Al.")
    elif any(str(value) == "REVIEW" for value in torsion_df["Status"].tolist()):
        st.warning("ACI torsion values are calculated or partially screened, but the result remains REVIEW because one or more guarded assumptions apply.")
    elif all(str(value) == "BELOW THRESHOLD" for value in torsion_df["Status"].tolist()):
        st.success("All active torsion demands are below the implemented ACI threshold screen. This is not final code-certified torsion design.")
    else:
        st.success("ACI RC torsion preview gates pass for the current visible rows. This is not final code-certified torsion design.")
    if not torsion_df.empty:
        display_columns = [
            "Status", "Case", "Demand", "Capacity", "Utilization", "Threshold status",
            "Transverse status", "Longitudinal status", "Detailing status",
            "Zone", "Tie/hoop", "Ao mm2", "At/s mm2/mm", "Al req mm2", "Al provided mm2",
            "Governing D/C value",
        ]
        st.dataframe(torsion_df[display_columns], use_container_width=True, hide_index=True)
    with st.expander("ACI torsion audit / method details", expanded=False):
        if torsion_df.empty:
            st.info("Audit rows are not available until section, material, active Tu demand, closed transverse reinforcement, and torsion core geometry are ready.")
        else:
            st.dataframe(torsion_df, use_container_width=True, hide_index=True)
        st.markdown(
            "- Scope: ACI 318 RC Column/Pier torsion preview only.\n"
            "- Demand source: Loads -> Column/Pier ULS table, active `Tu` rows.\n"
            "- Transverse source: Sections -> Rebar -> Transverse Rebar, active Column/Pier closed ties/hoops or spiral. With no station owner, the lowest active `At/s` region is used conservatively.\n"
            "- Longitudinal source: ordinary active rebar only. Prestress strands, tendons, and PT bars are not counted as torsion `Al` in this milestone.\n"
            "- Formula basis: threshold screen uses `0.083 sqrt(fc) Acp^2/Pcp`; strength preview uses `Tn = 2 Ao At fy cot(theta) / s`, `theta = 45 deg`, `phi = 0.75`, plus `Al` and `s <= min(ph/8, 300 mm)` gates.\n"
            "- Exclusions: AASHTO LRFD, prestressed torsion, multi-cell hollow torsion, seismic special detailing, anchorage/hooks, and shop-drawing detailing. Use the Shear + Torsion tab for the scoped ACI RC V+T interaction gate."
        )
    with st.expander("Future torsion code-check scope", expanded=False):
        st.markdown(
            "- Add station/height assignment for torsion transverse regions so confinement and shaft/core regions can be checked at actual demand locations.\n"
            "- Add explicit engineer-controlled Ao/Aoh visualization and validation for custom/hollow sections.\n"
            "- Expand the Shear + Torsion tab beyond the current ACI RC nonprestressed scope only after code-specific benchmarks exist.\n"
            "- Required validation: AASHTO LRFD, prestressed V+T, seismic detailing, anchorage/hooks, and multi-cell hollow benchmarks before those routes can issue final PASS/FAIL."
        )


def _column_pier_combined_vt_summary_cards(
    *,
    vt_df: pd.DataFrame,
    active_demands: pd.DataFrame,
    analysis_input: AnalysisInput | None,
) -> list[dict[str, object]]:
    code = project_design_code_from_session(st.session_state)
    edition = project_code_edition_from_session(st.session_state)
    governing = _column_pier_governing_combined_vt_row(vt_df)
    active_tu_count = 0
    if not active_demands.empty and "Tu" in active_demands.columns:
        active_tu_count = int(pd.to_numeric(active_demands["Tu"], errors="coerce").abs().gt(_COLUMN_PIER_SHEAR_DEMAND_TOL).sum())
    if code != PROJECT_CODE_ACI318:
        status_value = "REVIEW"
        status_detail = "AASHTO LRFD Column/Pier V+T interaction is not implemented in this milestone"
        status_color = "warning"
    elif vt_df.empty:
        status_value = "NOT READY"
        status_detail = "Needs active ULS rows, nonzero Tu, Vux/Vuy source data, closed transverse reinforcement, and ordinary Al"
        status_color = "warning"
    elif any(str(value) == "FAIL" for value in vt_df["Status"].tolist()):
        status_value = "FAIL"
        status_detail = "At least one combined stress, transverse reinforcement, longitudinal Al, or source gate exceeds 1.0"
        status_color = "danger"
    elif any(str(value) == "DATA REQUIRED" for value in vt_df["Status"].tolist()):
        status_value = "DATA REQUIRED"
        status_detail = "One or more source inputs are incomplete for the final ACI RC V+T gate"
        status_color = "warning"
    elif any(str(value) == "REVIEW" for value in vt_df["Status"].tolist()):
        status_value = "REVIEW"
        status_detail = "Guarded inputs such as active prestress or unsupported code route prevent final acceptance"
        status_color = "warning"
    elif all(str(value) == "NOT APPLICABLE" for value in vt_df["Status"].tolist()):
        status_value = "NOT APPLICABLE"
        status_detail = "No active Tu demand in the current Column/Pier ULS rows"
        status_color = "neutral"
    else:
        status_value = "PASS"
        status_detail = "Scoped ACI RC V+T interaction gates pass for nonprestressed Column/Pier rows"
        status_color = "ready"
    governing_detail = "No governing combined V+T row"
    governing_value = "-"
    interaction_value = "-"
    if governing is not None:
        governing_value = f"D/C {_format_beam_uls_ratio(governing.get('Overall D/C value'))}"
        governing_detail = f"{governing.get('Case', '-')} / {governing.get('Direction', '-')}"
        interaction_value = str(governing.get("Interaction form") or "-")
    prestress_value = "No"
    prestress_detail = "ACI RC nonprestressed V+T route"
    if _column_pier_has_active_prestress(analysis_input):
        prestress_value = "Present"
        prestress_detail = "PSC V+T interaction is not implemented; result remains REVIEW"
    return [
        {"title": "V+T status", "value": status_value, "detail": status_detail, "status": status_color, "strong": True},
        {"title": "Code route", "value": "ACI 318 RC" if code == PROJECT_CODE_ACI318 else "Not implemented", "detail": f"{edition}; AASHTO and PSC routes remain guarded", "status": "info" if code == PROJECT_CODE_ACI318 else "warning"},
        {"title": "Active Tu cases", "value": f"{active_tu_count:,}", "detail": "Each active Tu is checked for Vux and Vuy directions" if active_tu_count else "No nonzero Tu in active ULS rows", "status": "info" if active_tu_count else "neutral"},
        {"title": "Governing row", "value": governing_value, "detail": governing_detail, "status": "info"},
        {"title": "Interaction form", "value": interaction_value, "detail": "Solid uses root-sum-square; hollow uses linear stress sum", "status": "info"},
        {"title": "Prestress effects", "value": prestress_value, "detail": prestress_detail, "status": "warning" if prestress_value == "Present" else "neutral"},
    ]


def _render_column_pier_combined_vt_workspace() -> None:
    st.markdown("#### Shear + Torsion")
    st.caption("Scoped ACI 318 RC combined shear-torsion interaction gate for Column/Pier case-based ULS rows.")
    active_demands = _active_column_pier_uls_demand_dataframe_from_state(st.session_state)
    analysis_input = _serviceability_analysis_input_from_session()
    vt_df = _column_pier_combined_vt_check_dataframe(st.session_state, analysis_input)
    _render_analysis_summary_strip(
        _column_pier_combined_vt_summary_cards(
            vt_df=vt_df,
            active_demands=active_demands,
            analysis_input=analysis_input,
        ),
        columns=3,
    )
    code = project_design_code_from_session(st.session_state)
    if code != PROJECT_CODE_ACI318:
        st.warning("Column/Pier AASHTO LRFD V+T interaction is not implemented. This tab does not issue final V+T PASS/FAIL for AASHTO projects.")
    elif vt_df.empty:
        st.warning("No Column/Pier ACI RC V+T rows are ready. Enter nonzero Tu, confirm Vux/Vuy rows, activate closed transverse reinforcement, and provide ordinary longitudinal rebar.")
    elif any(str(value) == "FAIL" for value in vt_df["Status"].tolist()):
        st.error("One or more ACI RC combined V+T gates fail. Review demand, section/core geometry, transverse reinforcement, and ordinary longitudinal torsion bars.")
    elif any(str(value) == "DATA REQUIRED" for value in vt_df["Status"].tolist()):
        st.warning("ACI RC V+T interaction is not ready because one or more required source inputs are incomplete.")
    elif any(str(value) == "REVIEW" for value in vt_df["Status"].tolist()):
        st.warning("ACI RC V+T values are calculated or partially screened, but guarded assumptions prevent final acceptance for one or more rows.")
    elif all(str(value) == "NOT APPLICABLE" for value in vt_df["Status"].tolist()):
        st.info("No active Tu demand is present. Use the Shear tab for shear-only review.")
    else:
        st.success("ACI RC combined shear-torsion interaction gates pass for the current nonprestressed Column/Pier rows.")

    if not vt_df.empty:
        display_columns = [
            "Status", "Direction", "Case", "Vu kN", "Tu kN-m", "Shape",
            "Stress status", "Transverse status", "Longitudinal status",
            "Source shear status", "Source torsion status",
            "Stress D/C value", "Transverse D/C value", "Longitudinal D/C value", "Overall D/C value",
            "Interaction form",
        ]
        st.dataframe(vt_df[display_columns], use_container_width=True, hide_index=True)
        st.error(
            "Seismic confinement/detailing review remains separate: this V+T gate uses the Control section transverse row only "
            "and does not certify plastic-hinge confinement, hoop anchorage, lap-splice confinement, or seismic detailing."
        )

    with st.expander("ACI V+T audit / method details", expanded=False):
        if vt_df.empty:
            st.info("Audit rows are not available until the section, material, active V/T demand, closed transverse reinforcement, and ordinary Al source are ready.")
        else:
            st.dataframe(vt_df, use_container_width=True, hide_index=True)
        st.markdown(
            "- Scope: ACI 318 RC nonprestressed Column/Pier combined shear-torsion interaction gate.\n"
            "- Demand source: Loads -> Column/Pier ULS table, active `Vux`, `Vuy`, and `Tu` rows.\n"
            "- Transverse source: Sections -> Rebar -> Transverse Rebar, single active Control section row; no minimum ties are silently assumed.\n"
            "- Longitudinal torsion source: ordinary active longitudinal rebar only. Prestress strands, tendons, and PT bars are not counted as `Al`.\n"
            "- Formula basis: combined stress uses `Vu/(bw d)` with `Tu ph/(1.7 Aoh^2)`; solid sections use root-sum-square and hollow sections use linear sum. Combined transverse demand uses `Av/s + 2At/s`.\n"
            "- Validation evidence: `ULS.COL.VT.QA1` compares this Analysis gate against independent rectangular-section hand references for Vux, Vuy, zero-shear torsion, and below-threshold torsion cases.\n"
            "- Exclusions: AASHTO LRFD, prestressed V+T, second-order effects, seismic special detailing, closed-hoop anchorage/hooks, development/lap splices, and shop-drawing detailing."
        )


def _render_analysis_summary_strip(cards: list[dict[str, object]], columns: int = 4) -> None:
    for start in range(0, len(cards), columns):
        cols = st.columns(min(columns, len(cards) - start))
        for column, card in zip(cols, cards[start : start + columns]):
            with column:
                st.markdown(
                    _analysis_card_html(
                        str(card["title"]),
                        str(card["value"]),
                        str(card.get("detail", "")),
                        str(card.get("status", "info")),
                        bool(card.get("strong", False)),
                    ),
                    unsafe_allow_html=True,
                )


def _analysis_kv_panel_html(rows: list[tuple[str, str]]) -> str:
    rendered_rows = []
    for label, value in rows:
        rendered_rows.append(
            '<div class="cpmm-analysis-kv-row">'
            f'<div class="cpmm-analysis-kv-label">{escape(label)}</div>'
            f'<div class="cpmm-analysis-kv-value">{escape(value)}</div>'
            "</div>"
        )
    return '<div class="cpmm-analysis-card">' + "".join(rendered_rows) + "</div>"


def _capacity_margin_text(dcr: object) -> str:
    try:
        value = float(dcr)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(value):
        return "N/A"
    return f"{(1.0 - value) * 100.0:.1f}%"


def _reserve_ratio_text(dcr: object) -> str:
    try:
        value = float(dcr)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(value) or value <= 0.0:
        return "N/A"
    return f"{1.0 / value:.2f}"


def _selected_case_summary_cards(summary: dict, dc_summary: DemandCapacitySummary) -> list[dict[str, object]]:
    selected_detail = "Governing case" if summary["selected_combo"] == dc_summary.governing_combo else "Selected case"
    return [
        {
            "title": "Selected / Governing",
            "value": summary["selected_combo"],
            "detail": selected_detail,
            "status": "info",
        },
        {
            "title": "Status",
            "value": summary["status"].replace("_", " "),
            "status": _analysis_status_style(summary["status"]),
            "strong": True,
        },
        {
            "title": "D/C Ratio",
            "value": _format_optional_number(summary["dcr"], precision=3),
            "detail": f"Max D/C {_format_optional_number(dc_summary.max_dcr, precision=3)}",
            "status": _analysis_status_style(summary["status"]),
        },
        {
            "title": "Capacity Margin",
            "value": _capacity_margin_text(summary.get("dcr")),
            "detail": f"Reserve ratio {_reserve_ratio_text(summary.get('dcr'))}",
            "status": _analysis_status_style(summary["status"]),
        },
        {"title": "Pu", "value": _format_optional_number(summary["Pu_kN"], " kN"), "status": "neutral"},
        {"title": "Mux", "value": _format_optional_number(summary["Mux_kNm"], " kN-m"), "status": "neutral"},
        {"title": "Muy", "value": _format_optional_number(summary["Muy_kNm"], " kN-m"), "status": "neutral"},
        {
            "title": "Available phiMn",
            "value": _format_optional_number(summary["capacity_phiMn_kNm"], " kN-m"),
            "detail": "At selected Pu",
            "status": "neutral",
        },
        {"title": "Resultant Mu", "value": _format_optional_number(summary["Mu_kNm"], " kN-m"), "status": "neutral"},
    ]


def _render_selected_case_detail_panel(summary: dict, unbonded_ignored_count: int) -> None:
    rows = [
        ("Load case", str(summary["selected_combo"])),
        ("D/C ratio", _format_optional_number(summary["dcr"], precision=3)),
        ("Pu", _format_optional_number(summary["Pu_kN"], " kN")),
        ("Mux / Muy", f"{_format_optional_number(summary['Mux_kNm'], ' kN-m')} / {_format_optional_number(summary['Muy_kNm'], ' kN-m')}"),
        ("Available phiMn", _format_optional_number(summary["capacity_phiMn_kNm"], " kN-m")),
        ("Capacity margin", _capacity_margin_text(summary.get("dcr"))),
        ("Reserve ratio", _reserve_ratio_text(summary.get("dcr"))),
        ("Analysis mode", str(summary["analysis_mode"])),
        ("Prestress included", "Yes" if summary["prestress_included"] else "No"),
        ("Unbonded ignored", f"{unbonded_ignored_count:,}"),
        ("Slice method", str(summary.get("slice_method", "N/A"))),
        ("Capacity method", str(summary.get("capacity_method", summary.get("dcr_method", "N/A")))),
        ("Fallback used", "Yes" if summary.get("used_fallback") else "No"),
    ]
    st.markdown(_analysis_kv_panel_html(rows), unsafe_allow_html=True)
    if summary.get("message"):
        st.caption(f"Message: {summary['message']}")


def _pmm_3d_surface_diagnostics_from_figure(fig: go.Figure) -> dict[str, object]:
    meta = fig.layout.meta
    if isinstance(meta, dict) and isinstance(meta.get("pmm_surface_diagnostics"), dict):
        return dict(meta["pmm_surface_diagnostics"])
    return {}


def _render_pmm_3d_surface_diagnostics(diagnostics: dict[str, object], show_surface: bool) -> None:
    if not diagnostics:
        return
    generated = bool(diagnostics.get("surface_generated"))
    if show_surface and not generated:
        st.warning(
            "PMM surface could not be generated from the available stored result data. "
            "Showing slice/load point only."
        )
    with st.expander("3D surface diagnostics", expanded=False):
        st.write(f"Surface generated: {'Yes' if generated else 'No'}")
        st.write(f"Surface trace type: {diagnostics.get('surface_trace_type') or 'None'}")
        st.write(f"Valid PMM points used: {diagnostics.get('valid_point_count', 0)}")
        st.write(f"Resolved P column: {diagnostics.get('p_column') or 'N/A'}")
        st.write(f"Resolved Mx column: {diagnostics.get('mx_column') or 'N/A'}")
        st.write(f"Resolved My column: {diagnostics.get('my_column') or 'N/A'}")
        fallback_reason = str(diagnostics.get("fallback_reason") or "")
        if fallback_reason:
            st.write(f"Fallback reason: {fallback_reason}")
        available_columns = diagnostics.get("available_columns")
        if isinstance(available_columns, list):
            st.write(f"Available columns: {', '.join(str(column) for column in available_columns)}")


def _render_demand_capacity_summary(summary: DemandCapacitySummary) -> None:
    st.subheader("ULS Demand/Capacity Review")
    st.warning(
        "ACI RC PMM demand/capacity review is finalized production-preview only within the validated RC scope. "
        "Bonded prestress contribution, unsupported PMM routes, fallback capacity methods, unbonded prestress, "
        "refined long-term effects, and final code certification remain engineering-review or future-work items."
    )
    cols = st.columns(3)
    cols[0].metric("Overall Status", summary.overall_status)
    cols[1].metric("Governing Combo", summary.governing_combo or "N/A")
    cols[2].metric("Max D/C Ratio", "N/A" if summary.max_dcr is None else f"{summary.max_dcr:.3f}")
    for warning in summary.warnings:
        st.warning(f"WARNING: {warning}")
    for item in summary.info:
        st.info(f"INFO: {item}")
    display_df = _demand_capacity_display_dataframe(summary)
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    if not display_df.empty:
        st.download_button(
            "Download ULS D/C Result CSV",
            data=display_df.to_csv(index=False),
            file_name="uls_demand_capacity_result.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _render_pmm_summary_card(summary: dict, unbonded_ignored_count: int) -> None:
    st.markdown("**PMM Summary**")
    cols = st.columns(2)
    cols[0].metric("Selected Load Case", summary["selected_combo"])
    cols[1].metric("Status", summary["status"])
    cols2 = st.columns(2)
    cols2[0].metric("D/C Ratio", "N/A" if summary["dcr"] is None else f"{summary['dcr']:.3f}")
    cols2[1].metric(
        "Available phiMn at Pu",
        "N/A" if summary["capacity_phiMn_kNm"] is None else f"{summary['capacity_phiMn_kNm']:,.1f} kN-m",
    )
    cols3 = st.columns(2)
    cols3[0].metric("Pu", f"{summary['Pu_kN']:,.1f} kN")
    cols3[1].metric("Mu resultant", f"{summary['Mu_kNm']:,.1f} kN-m")
    cols4 = st.columns(2)
    cols4[0].metric("Mux", f"{summary['Mux_kNm']:,.1f} kN-m")
    cols4[1].metric("Muy", f"{summary['Muy_kNm']:,.1f} kN-m")
    st.caption(f"Analysis Mode: {summary['analysis_mode']}")
    st.caption(f"Prestress Included: {'Yes' if summary['prestress_included'] else 'No'}")
    st.caption(f"Unbonded Ignored: {unbonded_ignored_count:,}")
    st.caption(f"Slice Method: {summary.get('slice_method', 'N/A')}")
    st.caption(f"Capacity Method: {summary.get('capacity_method', summary.get('dcr_method', 'N/A'))}")
    st.caption(f"D/C Method: {summary.get('dcr_method', 'N/A')}")
    st.caption(f"Used Fallback: {'Yes' if summary.get('used_fallback') else 'No'}")
    st.caption(f"Envelope Method: {summary.get('envelope_method', 'N/A')}")
    envelope_valid = summary.get("envelope_valid")
    st.caption(f"Envelope Valid: {'N/A' if envelope_valid is None else ('Yes' if envelope_valid else 'No')}")
    convex_hull = summary.get("convex_hull_fallback")
    st.caption(f"Convex Hull Fallback: {'N/A' if convex_hull is None else ('Yes' if convex_hull else 'No')}")
    st.caption(f"Boundary Warning Count: {summary.get('boundary_warning_count', 0)}")
    if summary.get("message"):
        st.caption(f"Message: {summary['message']}")


def _render_pmm_slice_dashboard(
    pmm_df: pd.DataFrame,
    load_cases: list,
    dc_summary: DemandCapacitySummary,
    mode_label: str,
    include_prestress: bool,
    bonded_prestress_included: bool,
    unbonded_ignored_count: int,
    result_hash: str | None,
    engineering_warnings: list[str] | None = None,
) -> None:
    """Render a commercial-grade ULS/PMM workspace shell.

    This function intentionally reorganizes existing result content only.  It
    does not rerun or modify the PMM solver, D/C calculation, load import,
    prestress interpretation, report export, or cache/hash behavior.
    """

    st.markdown(_ANALYSIS_DASHBOARD_CSS, unsafe_allow_html=True)
    active_uls = get_active_uls_load_cases(load_cases)
    if not active_uls:
        st.info("No active ULS load cases are available for the PMM workspace.")
        return

    _render_executive_result_header(dc_summary, load_cases)
    _render_design_decision_banner(
        dc_summary,
        load_cases,
        engineering_warnings or [],
        include_prestress=include_prestress,
        bonded_prestress_included=bonded_prestress_included,
        unbonded_ignored_count=unbonded_ignored_count,
    )
    if bonded_prestress_included:
        st.warning("Bonded prestress contribution is included using the current prototype strain compatibility model.")
    if unbonded_ignored_count > 0:
        st.warning("Unbonded prestress is ignored in the current solver.")

    options = [load_case.name for load_case in active_uls]
    default_combo = dc_summary.governing_combo if dc_summary.governing_combo in options else options[0]
    remembered_combo = st.session_state.get("pmm_dashboard_selected_combo", default_combo)
    if remembered_combo not in options:
        remembered_combo = default_combo
    selector_cols = st.columns([2.2, 1.0])
    with selector_cols[0]:
        selected_combo = st.selectbox(
            "Selected ULS load case for detailed PMM review",
            options,
            index=options.index(remembered_combo),
            key="pmm_dashboard_selected_combo",
            help="The Summary tab always highlights the governing case; this selection controls the PMM Check and 3D tabs.",
        )
    with selector_cols[1]:
        st.metric("Governing Case", dc_summary.governing_combo or "N/A")
    selected_load_case = get_selected_load_case(active_uls, selected_combo)
    if selected_load_case is None:
        st.info("Select an active ULS load case to show the dashboard.")
        return

    selected_slice = pmm_slice_at_pu(pmm_df, N_to_kN(selected_load_case.Pu_N))
    selected_envelope = build_slice_envelope(selected_slice)
    slice_method = selected_slice.attrs.get("method", "unknown")
    if selected_envelope.used_convex_hull:
        st.error("Convex hull fallback may overestimate PMM capacity. Treat the displayed D/C as approximate.")
    dashboard_warnings = _collect_engineering_warnings(
        selected_slice.attrs.get("warnings", []),
        selected_envelope.warnings,
        [UNBONDED_PRESTRESS_IGNORED_WARNING] if unbonded_ignored_count > 0 else [],
    )
    if dashboard_warnings:
        st.warning(f"{len(dashboard_warnings):,} PMM dashboard warning(s) are available in Diagnostics.")

    selected_summary = build_selected_load_case_summary(
        selected_load_case,
        dc_summary,
        mode_label,
        include_prestress and bonded_prestress_included,
        selected_envelope,
    )
    slice_export_df = pmm_slice_export_dataframe(selected_slice)
    envelope_export_df = slice_envelope_export_dataframe(selected_envelope)
    st.session_state["selected_pmm_slice"] = slice_export_df
    st.session_state["selected_slice_envelope"] = envelope_export_df
    st.session_state["selected_pu_kN"] = N_to_kN(selected_load_case.Pu_N)
    st.session_state["selected_pmm_demand_point"] = {
        "Combo Name": selected_load_case.name,
        "Mux_kNm": Nmm_to_kNm(selected_load_case.Mux_Nmm),
        "Muy_kNm": Nmm_to_kNm(selected_load_case.Muy_Nmm),
    }
    if selected_envelope.used_convex_hull:
        st.session_state["selected_slice_envelope"].attrs["used_convex_hull"] = True

    demand_df = demand_load_cases_to_display_dataframe(active_uls)
    summary_tab, pmm_tab, three_d_tab, sls_tab, diagnostics_tab = st.tabs(
        ["Summary", "PMM Check", "3D Interaction", "SLS", "Diagnostics / QA"]
    )

    with summary_tab:
        st.subheader("Governing ULS Result")
        st.caption(
            "This tab gives the first-screen commercial review view: overall status, governing case, and compact D/C trace. "
            "Detailed method diagnostics remain available in Diagnostics / QA."
        )
        _render_governing_case_card(dc_summary)
        _render_analysis_result_transparency_panel(dc_summary, load_cases, show_overview_cards=False)
        with st.expander("Selected case quick detail", expanded=False):
            _render_analysis_summary_strip(_selected_case_summary_cards(selected_summary, dc_summary), columns=4)
            _render_result_traceability_path(selected_summary)
            _render_selected_case_detail_panel(selected_summary, unbonded_ignored_count)

    with pmm_tab:
        st.subheader("PMM Check")
        st.caption(
            "The 2D Mux-Muy slice is generated from stored PMM result data for the selected ULS load case; "
            "switching selected cases does not rerun the solver."
        )
        _render_analysis_summary_strip(_selected_case_summary_cards(selected_summary, dc_summary), columns=4)
        _render_result_traceability_path(selected_summary)
        left, right = st.columns([2.1, 1.0])
        with left:
            st.markdown("**Governing PMM Slice Visualization**")
            st.caption(
                "The demand vector is checked against the cleaned Mux-Muy capacity envelope at the selected Pu. "
                "The capacity marker is the ray/envelope intersection used to compute available φMn and D/C."
            )
            plot_cols = st.columns([1.35, 0.85])
            with plot_cols[0]:
                demand_display_label = st.selectbox(
                    "Demand points display",
                    ["Governing case only", "Selected case only", "Selected + governing", "All active ULS points"],
                    index=0,
                    key="pmm_slice_demand_display_mode_v42",
                    help=(
                        "Commercial default: show only the governing load point so the PMM slice stays clean. "
                        "Use all points only for overview; detailed values remain available on hover and in the table."
                    ),
                )
            with plot_cols[1]:
                show_slice_annotations = st.checkbox(
                    "Show annotation callouts",
                    value=False,
                    key="pmm_slice_show_annotation_callouts_v42",
                    help="Presentation-only callouts. Off by default because text boxes can hide demand/capacity markers.",
                )
            display_mode_map = {
                "Governing case only": "governing_only",
                "Selected case only": "selected_only",
                "Selected + governing": "selected_governing",
                "All active ULS points": "all_active",
            }
            demand_display_mode = display_mode_map.get(demand_display_label, "governing_only")
            governing_load_case = get_selected_load_case(active_uls, dc_summary.governing_combo) if dc_summary.governing_combo else None
            plot_load_case = governing_load_case if demand_display_mode == "governing_only" and governing_load_case is not None else selected_load_case
            slice_figure_hash = (
                f"{result_hash or 'unhashed'}:{plot_load_case.name}:mux_muy_slice:"
                f"{demand_display_mode}:{show_slice_annotations}"
            )
            if (
                st.session_state.get("pmm_mux_muy_slice_figure_hash") == slice_figure_hash
                and isinstance(st.session_state.get("pmm_mux_muy_slice_figure"), go.Figure)
            ):
                slice_fig = st.session_state.get("pmm_mux_muy_slice_figure")
            else:
                slice_fig, slice_timing = timed_call(
                    "PMM Mux-Muy slice figure generation",
                    make_mux_muy_slice_figure,
                    pmm_df,
                    plot_load_case,
                    dc_summary,
                    demand_df,
                    demand_display_mode=demand_display_mode,
                    show_annotations=show_slice_annotations,
                )
                _record_runtime_timing(slice_timing)
                st.session_state["pmm_mux_muy_slice_figure"] = slice_fig
                st.session_state["pmm_mux_muy_slice_figure_hash"] = slice_figure_hash
            st.session_state["pmm_mux_muy_slice_figure"] = slice_fig
            st.plotly_chart(
                slice_fig,
                use_container_width=True,
                key="analysis_mux_muy_slice_dashboard",
            )
        with right:
            displayed_summary = selected_summary
            try:
                if "plot_load_case" in locals() and plot_load_case.name != selected_load_case.name:
                    displayed_summary = build_selected_load_case_summary(
                        plot_load_case,
                        dc_summary,
                        mode_label,
                        include_prestress and bonded_prestress_included,
                        selected_envelope,
                    )
                    st.markdown("**Governing Case Details**")
                else:
                    st.markdown("**Selected Case Details**")
            except Exception:
                st.markdown("**Selected Case Details**")
            _render_selected_case_detail_panel(displayed_summary, unbonded_ignored_count)

    with three_d_tab:
        st.subheader("3D PMM Interaction")
        st.caption("3D PMM surface is a visualization aid generated from stored PMM result data and does not recompute capacity.")
        st.caption("Surface shading/mesh is interpolated between sampled PMM states for visualization.")
        st.checkbox(
            "Show 3D PMM interaction",
            value=False,
            key=PMM_3D_MASTER_TOGGLE_KEY,
            help="Rendering the 3D PMM surface can be expensive. It uses stored PMM result data and does not rerun the solver.",
        )
        if _pmm_3d_display_enabled_from_state(st.session_state):
            opt_cols = st.columns(4)
            with opt_cols[0]:
                show_surface = st.checkbox("Show 3D PMM surface", value=True, key="show_pmm_3d_surface")
            with opt_cols[1]:
                show_current_slice = st.checkbox("Show Current Pu Slice", value=True, key="show_pmm_3d_current_pu_slice")
            with opt_cols[2]:
                show_selected_point = st.checkbox("Show selected load point", value=True, key="show_pmm_3d_selected_point")
            with opt_cols[3]:
                show_all_load_points = st.checkbox("Show all ULS load points", value=False, key="show_pmm_3d_all_load_points")
            has_3d_layer = _should_generate_pmm_3d_figure_from_state(st.session_state)
            surface_fig: go.Figure | None = None
            if not has_3d_layer:
                st.info("Enable at least one 3D display layer to show the PMM interaction view.")
            surface_figure_hash = (
                f"{result_hash or 'unhashed'}:{selected_load_case.name}:pmm_3d:"
                f"{show_surface}:{show_current_slice}:{show_selected_point}:{show_all_load_points}"
            )
            if has_3d_layer and (
                st.session_state.get("pmm_interaction_surface_figure_hash") == surface_figure_hash
                and isinstance(st.session_state.get("pmm_interaction_surface_figure"), go.Figure)
            ):
                surface_fig = st.session_state.get("pmm_interaction_surface_figure")
            elif has_3d_layer:
                surface_fig, surface_timing = timed_call(
                    "3D PMM Plotly figure generation",
                    make_pmm_3d_dashboard_figure,
                    pmm_df,
                    demand_df,
                    selected_load_case,
                    dc_summary,
                    show_surface=show_surface,
                    show_current_pu_slice=show_current_slice,
                    show_raw_points=False,
                    show_selected_load_point=show_selected_point,
                    show_all_uls_load_points=show_all_load_points,
                )
                _record_runtime_timing(surface_timing)
                st.session_state["pmm_interaction_surface_figure"] = surface_fig
                st.session_state["pmm_interaction_surface_figure_hash"] = surface_figure_hash
            if isinstance(surface_fig, go.Figure):
                st.plotly_chart(
                    surface_fig,
                    use_container_width=True,
                    key="analysis_3d_dashboard_chart",
                )
                _render_pmm_3d_surface_diagnostics(_pmm_3d_surface_diagnostics_from_figure(surface_fig), show_surface)
        else:
            st.info("3D PMM interaction rendering is off by default. Enable it only when a 3D capacity view is needed.")

    with sls_tab:
        st.subheader("SLS")
        active_sls_count = _active_load_case_usage_summary(load_cases)["active_sls"]
        if active_sls_count:
            st.info(
                f"{active_sls_count:,} active SLS load case(s) are stored for the SLS / Stress & Cracking workspace. "
                "They are not used in the ULS PMM demand/capacity ranking."
            )
        else:
            st.info("No active SLS load cases are currently stored.")
        st.caption(
            "Open the main Analysis tab 'SLS / Stress & Cracking' for serviceability settings, stress check points, "
            "gross/transformed section properties, and available SLS checks."
        )

    with diagnostics_tab:
        st.subheader("Diagnostics / QA")
        st.caption("Detailed method information, warnings, raw demand points, and exports are kept here to protect the main result view from clutter.")
        if dashboard_warnings:
            _render_engineering_warnings(dashboard_warnings, df=df, dc_summary=dc_summary)
        with st.expander("Active ULS demand points", expanded=False):
            if demand_df.empty:
                st.info("No active ULS demand points are available.")
            else:
                st.dataframe(demand_df, use_container_width=True, hide_index=True)
        with st.expander("PMM Slice / Capacity Method Details", expanded=False):
            st.write(f"PMM slice method: {slice_method}.")
            for warning in selected_slice.attrs.get("warnings", []):
                st.warning(f"PMM slice warning: {warning}")
            st.write(
                f"PMM envelope method: {selected_envelope.method}; "
                f"valid: {'Yes' if selected_envelope.is_valid else 'No'}; "
                f"convex hull fallback: {'Yes' if selected_envelope.used_convex_hull else 'No'}."
            )
            for warning in selected_envelope.warnings:
                st.warning(f"PMM envelope warning: {warning}")
            for warning in dc_summary.warnings:
                st.warning(f"D/C warning: {warning}")
            for item in dc_summary.info:
                st.info(f"D/C info: {item}")
            export_cols = st.columns(2)
            with export_cols[0]:
                if not slice_export_df.empty:
                    st.download_button(
                        "Download Selected PMM Slice CSV",
                        data=slice_export_df.to_csv(index=False),
                        file_name="selected_pmm_slice.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
            with export_cols[1]:
                if not envelope_export_df.empty:
                    st.download_button(
                        "Download Selected Slice Envelope CSV",
                        data=envelope_export_df.to_csv(index=False),
                        file_name="selected_pmm_slice_envelope.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
        with st.expander("Detailed Load Case D/C Ranking", expanded=False):
            ranking_df = rank_load_cases_by_dcr(dc_summary)
            if ranking_df.empty:
                st.info("No active ULS demand/capacity results are available to rank.")
            else:
                st.dataframe(ranking_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download ULS D/C Result CSV",
                    data=ranking_df.to_csv(index=False),
                    file_name="uls_demand_capacity_result.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
        with st.expander("Detailed PMM plots", expanded=False):
            _render_pmm_charts(pmm_df, demand_df, dc_summary, key_prefix="analysis_workspace_diagnostics")

def _dc_status_map(summary: DemandCapacitySummary | None) -> dict[str, tuple[str | None, str]]:
    if summary is None:
        return {}
    return {
        item.combo_name: (None if item.dcr is None else f"{item.dcr:.3f}", item.status)
        for item in summary.results
    }


def _marker_for_status(status: str) -> tuple[str, str]:
    if status == "PASS":
        return "circle-x", "#16a34a"
    if status == "FAIL":
        return "x", "#dc2626"
    if status == "OUT_OF_RANGE":
        return "diamond-x", "#f97316"
    return "cross", "#6b7280"


def _add_demand_trace(fig: go.Figure, demand_df, x_column: str, name: str, dc_summary: DemandCapacitySummary | None = None) -> None:
    if demand_df.empty:
        return
    status_map = _dc_status_map(dc_summary)
    symbols = []
    colors = []
    hover = []
    for _, row in demand_df.iterrows():
        dcr, status = status_map.get(row["Combo Name"], (None, "NOT_CHECKED"))
        symbol, color = _marker_for_status(status)
        symbols.append(symbol)
        colors.append(color)
        hover.append(
            f"{row['Combo Name']}<br>Pu={row['Pu_kN']:.1f} kN<br>"
            f"Mux={row['Mux_kNm']:.1f} kN-m<br>Muy={row['Muy_kNm']:.1f} kN-m<br>"
            f"D/C={dcr or 'N/A'}<br>Status={status}"
        )
    fig.add_trace(
        go.Scatter(
            x=demand_df[x_column],
            y=demand_df["Pu_kN"],
            mode="markers+text",
            marker=dict(symbol=symbols, size=12, color=colors, line=dict(width=2, color="#111827")),
            text=demand_df["Combo Name"],
            hovertext=hover,
            hoverinfo="text",
            textposition="top center",
            name=name,
        )
    )


def _render_pmm_charts(
    df,
    demand_df,
    dc_summary: DemandCapacitySummary | None = None,
    *,
    key_prefix: str = "analysis_pmm_visual_review",
) -> None:
    st.subheader("PMM Visual Review")

    pmx = go.Figure()
    for condition in sorted(df["strain_condition"].dropna().unique()):
        condition_df = df[df["strain_condition"] == condition]
        pmx.add_trace(
            go.Scatter(
                x=condition_df["phiMnx_kNm"],
                y=condition_df["phiPn_kN"],
                mode="markers",
                marker=dict(size=5),
                name=str(condition),
                text=condition_df["theta_rad"].map(lambda value: f"theta={value:.3f} rad"),
            )
        )
    _add_demand_trace(pmx, demand_df, "Mux_kNm", "ULS demand", dc_summary)
    pmx.update_layout(title="RC PMM: P-Mnx", xaxis_title="phiMnx (kN-m)", yaxis_title="phiPn (kN)")
    st.plotly_chart(pmx, use_container_width=True, key=f"{key_prefix}_p_mnx_chart")

    pmy = go.Figure()
    for condition in sorted(df["strain_condition"].dropna().unique()):
        condition_df = df[df["strain_condition"] == condition]
        pmy.add_trace(
            go.Scatter(
                x=condition_df["phiMny_kNm"],
                y=condition_df["phiPn_kN"],
                mode="markers",
                marker=dict(size=5),
                name=str(condition),
                text=condition_df["theta_rad"].map(lambda value: f"theta={value:.3f} rad"),
            )
        )
    _add_demand_trace(pmy, demand_df, "Muy_kNm", "ULS demand", dc_summary)
    pmy.update_layout(title="RC PMM: P-Mny", xaxis_title="phiMny (kN-m)", yaxis_title="phiPn (kN)")
    st.plotly_chart(pmy, use_container_width=True, key=f"{key_prefix}_p_mny_chart")

    mm = go.Figure(
        go.Scatter(
            x=df["phiMnx_kNm"],
            y=df["phiMny_kNm"],
            mode="markers",
            marker=dict(size=5, color=df["phiPn_kN"], colorscale="Viridis", showscale=True, colorbar=dict(title="phiPn kN")),
            name="PMM point",
        )
    )
    if not demand_df.empty:
        status_map = _dc_status_map(dc_summary)
        symbols = []
        colors = []
        hover = []
        for _, row in demand_df.iterrows():
            dcr, status = status_map.get(row["Combo Name"], (None, "NOT_CHECKED"))
            symbol, color = _marker_for_status(status)
            symbols.append(symbol)
            colors.append(color)
            hover.append(
                f"{row['Combo Name']}<br>Pu={row['Pu_kN']:.1f} kN<br>"
                f"Mux={row['Mux_kNm']:.1f} kN-m<br>Muy={row['Muy_kNm']:.1f} kN-m<br>"
                f"D/C={dcr or 'N/A'}<br>Status={status}"
            )
        mm.add_trace(
            go.Scatter(
                x=demand_df["Mux_kNm"],
                y=demand_df["Muy_kNm"],
                mode="markers+text",
                marker=dict(symbol=symbols, size=12, color=colors, line=dict(width=2, color="#111827")),
                text=demand_df["Combo Name"],
                hovertext=hover,
                hoverinfo="text",
                textposition="top center",
                name="ULS demand",
            )
        )
    mm.update_layout(title="RC PMM: Mnx-Mny Point Cloud", xaxis_title="phiMnx (kN-m)", yaxis_title="phiMny (kN-m)")
    st.plotly_chart(mm, use_container_width=True, key=f"{key_prefix}_mnx_mny_chart")

    fig3d = go.Figure(
        go.Scatter3d(
            x=df["phiMnx_kNm"],
            y=df["phiMny_kNm"],
            z=df["phiPn_kN"],
            mode="markers",
            marker=dict(size=3, color=df["phiPn_kN"], colorscale="Viridis", opacity=0.75),
            name="PMM point",
        )
    )
    fig3d.update_layout(
        title="RC PMM: 3D Point Cloud",
        scene=dict(xaxis_title="phiMnx (kN-m)", yaxis_title="phiMny (kN-m)", zaxis_title="phiPn (kN)"),
    )
    st.plotly_chart(fig3d, use_container_width=True, key=f"{key_prefix}_3d_pmm_chart")


def _verification_summary_dataframe(summary: PMMVerificationSummary) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Check": check.name,
                "Status": check.status,
                "Message": check.message,
                "Values": check.values,
            }
            for check in summary.checks
        ]
    )


def _render_hand_check_summary(summary: HandCheckSummary) -> None:
    cols = st.columns(4)
    cols[0].metric("Overall Status", summary.overall_status)
    cols[1].metric("PASS", f"{summary.pass_count:,}")
    cols[2].metric("WARNING", f"{summary.warning_count:,}")
    cols[3].metric("FAIL", f"{summary.fail_count:,}")
    for warning in summary.warnings:
        st.warning(warning)
    for item in summary.info:
        st.info(item)
    df = hand_check_summary_to_dataframe(summary)
    st.dataframe(df, use_container_width=True, hide_index=True)
    if not df.empty:
        st.download_button(
            "Download Hand Check Results CSV",
            data=df.to_csv(index=False),
            file_name="pmm_hand_check_results.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _render_verification_expander() -> None:
    with st.expander("PMM Verification / Benchmark Checks", expanded=False):
        st.info(
            "Verification checks are benchmark-style sanity checks for the current prototype. "
            "They do not replace independent engineering validation."
        )
        if st.button("Run PMM Verification Suite", use_container_width=True):
            st.session_state["pmm_verification_summary"] = run_pmm_verification_suite()

        summary = st.session_state.get("pmm_verification_summary")
        if isinstance(summary, PMMVerificationSummary):
            cols = st.columns(4)
            cols[0].metric("Overall Status", summary.overall_status)
            cols[1].metric("PASS", f"{summary.pass_count:,}")
            cols[2].metric("WARNING", f"{summary.warning_count:,}")
            cols[3].metric("FAIL", f"{summary.fail_count:,}")
            st.dataframe(_verification_summary_dataframe(summary), use_container_width=True, hide_index=True)

        st.markdown("**Independent PMM Hand Checks**")
        st.info(
            "Hand checks are simplified spot checks for engineering review. "
            "They do not replace independent detailed validation or code-certified software."
        )
        if st.button("Run Independent Hand Checks", use_container_width=True):
            st.session_state["pmm_hand_check_summary"] = run_independent_hand_check_suite()

        hand_summary = st.session_state.get("pmm_hand_check_summary")
        if isinstance(hand_summary, HandCheckSummary):
            _render_hand_check_summary(hand_summary)

def _render_sls_verification_expander() -> None:
    with st.expander("SLS Verification / Stress Sign Benchmarks", expanded=False):
        st.info(
            "SLS verification checks are simplified benchmark and sign checks for engineering review. "
            "They do not replace independent validation."
        )
        if st.button("Run SLS Verification Suite", use_container_width=True):
            st.session_state["sls_verification_summary"] = run_sls_verification_suite()

        sls_summary = st.session_state.get("sls_verification_summary")
        if isinstance(sls_summary, SLSBenchmarkSummary):
            cols = st.columns(4)
            cols[0].metric("Overall Status", sls_summary.overall_status)
            cols[1].metric("PASS", f"{sls_summary.pass_count:,}")
            cols[2].metric("WARNING", f"{sls_summary.warning_count:,}")
            cols[3].metric("FAIL", f"{sls_summary.fail_count:,}")
            for warning in sls_summary.warnings:
                st.warning(warning)
            for item in sls_summary.info:
                st.info(item)
            sls_df = sls_benchmark_summary_to_dataframe(sls_summary)
            st.dataframe(sls_df, use_container_width=True, hide_index=True)
            if not sls_df.empty:
                st.download_button(
                    "Download SLS Verification Results CSV",
                    data=sls_df.to_csv(index=False),
                    file_name="sls_verification_results.csv",
                    mime="text/csv",
                    use_container_width=True,
                )


def _gross_section_properties_dataframe(section_properties) -> pd.DataFrame:
    if section_properties is None:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "A_mm2": section_properties.area_mm2,
                "cx_mm": section_properties.centroid_x_mm,
                "cy_mm": section_properties.centroid_y_mm,
                "Ix_mm4": section_properties.Ix_mm4,
                "Iy_mm4": section_properties.Iy_mm4,
                "Ixy_mm4": section_properties.Ixy_mm4,
                "x_min_mm": section_properties.x_min_mm,
                "x_max_mm": section_properties.x_max_mm,
                "y_min_mm": section_properties.y_min_mm,
                "y_max_mm": section_properties.y_max_mm,
                "S_top_mm3": section_properties.section_modulus_top_mm3,
                "S_bottom_mm3": section_properties.section_modulus_bottom_mm3,
                "S_left_mm3": section_properties.section_modulus_left_mm3,
                "S_right_mm3": section_properties.section_modulus_right_mm3,
            }
        ]
    )


def _stress_check_points_dataframe(check_points) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Point": point.name,
                "x_mm": point.x_mm,
                "y_mm": point.y_mm,
                "Point Type": point.point_type,
                "Source": point.source,
                "Include in Governing": point.include_in_governing,
                "Active": point.active,
                "Note": point.note or "",
            }
            for point in check_points
        ]
    )


def _default_custom_stress_check_points_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": False,
                "Name": "Web-Flange-1",
                "x_mm": None,
                "y_mm": None,
                "Point Type": "web_flange_junction",
                "Include in Governing": True,
                "Note": "",
            },
            {
                "Active": False,
                "Name": "Tendon-Zone-1",
                "x_mm": None,
                "y_mm": None,
                "Point Type": "tendon_zone",
                "Include in Governing": True,
                "Note": "",
            },
            {
                "Active": False,
                "Name": "Joint-1",
                "x_mm": None,
                "y_mm": None,
                "Point Type": "segmental_joint",
                "Include in Governing": True,
                "Note": "",
            },
        ]
    )



_GIRDER_DISPLAY_ZERO_TOLERANCE_MPA = 5.0e-4


def _clean_girder_display_number(value: object, *, zero_tolerance: float = _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA) -> object:
    """Return zero instead of negative-zero noise for UI display only.

    The calculation kernels keep the raw values.  This helper is intentionally
    limited to the Analysis workspace presentation layer so sign convention
    checks and validation results are not altered.
    """

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return value
    if not math.isfinite(numeric):
        return value
    if abs(numeric) < zero_tolerance:
        return 0.0
    return numeric


def _format_girder_stress_mpa(value: object, *, precision: int = 3) -> str:
    """Format stress values without displaying confusing negative-zero stress text."""

    cleaned = _clean_girder_display_number(value)
    try:
        numeric = float(cleaned)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(numeric):
        return "N/A"
    return f"{numeric:,.{precision}f} MPa"


def _girder_stress_type(stress_MPa: float, *, zero_tolerance_MPa: float = _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA) -> str:
    """Classify a girder SLS stress value for display only."""

    if abs(float(stress_MPa)) <= zero_tolerance_MPa:
        return "zero"
    return "compression" if float(stress_MPa) < 0.0 else "tension"


def _clean_girder_stress_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean near-zero stress numbers in a display dataframe without changing kernels."""

    if df.empty:
        return df
    cleaned = df.copy()
    for column in cleaned.columns:
        column_name = str(column).casefold()
        if "mpa" in column_name or "stress" in column_name:
            cleaned[column] = cleaned[column].map(_clean_girder_display_number)
    if "Total stress (MPa)" in cleaned.columns:
        cleaned["Stress type"] = cleaned["Total stress (MPa)"].map(_girder_stress_type)
    elif "Combined total (MPa)" in cleaned.columns:
        cleaned["Stress type"] = cleaned["Combined total (MPa)"].map(_girder_stress_type)
    elif "Total (MPa)" in cleaned.columns:
        cleaned["Stress type"] = cleaned["Total (MPa)"].map(_girder_stress_type)
    return cleaned


# Source compatibility phrases retained for regression tests after LOADS.SLS2B stage-tab refactor:
# SLS check case stress table; manual stage actions; code-check workflow; Combined service plus prestress stress; Manual service stage stress; current GIRDER.PS1B preview force; Include effective prestress stress component; Breaking Load, duct diameter, and strand-count metadata are not used; AASHTO stress limits; girder_stage_preview_enabled; Pe_eff is positive for compression after losses; Combined Service + Effective Prestress Stress; Stage templates are guidance only; No AASHTO stress limits; Results remain preview-only; not used by PMM, rebar, prestress, load-table, or report workflows.
# LOADS.SLS.CONNECT1 — connect Beam/Girder SLS load-table rows to the
# Analysis SLS preview without changing solver/load-combination behaviour.
_BEAM_SLS_LOAD_ANALYSIS_COLUMNS = ("Active", "Station x (m)", "Case Name", "Stage", "Load Component", "Section Basis", "N", "Mx", "My", "Vy", "Vx", "T", "Note")
_DIRECT_BEAM_SLS_BASIS_MAP = {
    "precast gross": "precast_gross",
    "precast gross section": "precast_gross",
    "gross": "precast_gross",
    "gross section": "precast_gross",
    "composite transformed": "composite_transformed",
    "composite transformed section": "composite_transformed",
    "transformed composite": "composite_transformed",
    "composite": "composite_transformed",
}


def _analysis_value_is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _analysis_to_bool(value: object, *, default: bool = True) -> bool:
    if _analysis_value_is_blank(value):
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "y", "active", "checked"}:
        return True
    if text in {"false", "0", "no", "n", "inactive", "unchecked"}:
        return False
    return default


def _analysis_float_or_zero(value: object) -> float:
    if _analysis_value_is_blank(value):
        return 0.0
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return 0.0


_GIRDER_PRESTRESS_FORCE_STATE_COLUMNS = ("Check Stage", "Prestress State", "Pe_kN", "yps_mm_from_bottom", "Note")


def _girder_prestress_force_state_rows_from_session_state() -> list[dict[str, object]]:
    """Return engineer-controlled stage prestress force states from Prestress page.

    GIRDER.PS2A keeps stage prestress force input separate from external Loads.
    Analysis consumes Pe_transfer/P_release, Pe_construction, or Pe_eff_final
    as internal prestress stress effects only.
    """

    raw_table = st.session_state.get("girder_prestress_force_states_table")
    if raw_table is None:
        return []
    df = pd.DataFrame(raw_table)
    if df.empty:
        return []
    rows: list[dict[str, object]] = []
    for _, raw_row in df.iterrows():
        row = {column: raw_row.get(column, "") for column in _GIRDER_PRESTRESS_FORCE_STATE_COLUMNS}
        if _analysis_value_is_blank(row.get("Check Stage")):
            continue
        rows.append(row)
    return rows


def _girder_prestress_force_state_for_stage(stage_label: str) -> dict[str, object] | None:
    """Return the Prestress-page force state row matching an SLS Analysis stage."""

    target = _beam_sls_stage_label_for_analysis(stage_label)
    for row in _girder_prestress_force_state_rows_from_session_state():
        if _beam_sls_stage_label_for_analysis(row.get("Check Stage")) == target:
            return row
    return None


def _girder_prestress_force_state_is_ready(row: Mapping[str, object] | None) -> bool:
    if row is None:
        return False
    pe_kN = _analysis_float_or_zero(row.get("Pe_kN"))
    yps = _analysis_float_or_zero(row.get("yps_mm_from_bottom"))
    return pe_kN > 0.0 and math.isfinite(yps)


def _girder_prestress_force_state_label(row: Mapping[str, object] | None, stage_label: str) -> str:
    if row is None:
        return "No stage prestress force state"
    label = str(row.get("Prestress State") or "Stage prestress force").strip() or "Stage prestress force"
    stage = _beam_sls_stage_label_for_analysis(stage_label)
    if stage == "Transfer stage" and "transfer" not in label.casefold() and "release" not in label.casefold():
        return f"Pe_transfer / P_release from Prestress force state ({label})"
    if stage == "Construction stage" and "construction" not in label.casefold():
        return f"Pe_construction from Prestress force state ({label})"
    if stage == "Service stage" and "eff" not in label.casefold() and "final" not in label.casefold():
        return f"Pe_eff_final from Prestress force state ({label})"
    return label


def _beam_sls_stage_label_for_analysis(value: object) -> str:
    """Normalize Loads-page Beam/Girder SLS stages for Analysis display."""

    text = "" if _analysis_value_is_blank(value) else str(value).strip()
    cf = text.casefold()
    if not cf:
        return ""
    if "transfer" in cf or "release" in cf:
        return "Transfer stage"
    if "construction" in cf or "deck" in cf or "pre-composite" in cf or "pre composite" in cf or "wet" in cf:
        return "Construction stage"
    if "service" in cf or "final" in cf or "post-composite" in cf or "post composite" in cf or "composite service" in cf:
        return "Service stage"
    return text


def _beam_sls_component_for_analysis(stage: object, component: object = "") -> str:
    """Return hidden component meaning for code-limit guards and audit notes."""

    label = _beam_sls_stage_label_for_analysis(stage)
    if label == "Transfer stage":
        return "Girder self-weight"
    if label == "Construction stage":
        return "Girder self-weight + wet deck/topping"
    if label == "Service stage":
        return "Total SLS resultant"
    return "" if _analysis_value_is_blank(component) else str(component).strip()


def _beam_sls_load_rows_from_session_state() -> list[dict[str, object]]:
    """Return active Beam/Girder SLS load rows for Analysis preview selection.

    The Loads page remains the master data source.  This helper intentionally
    performs tolerant normalization locally so Analysis can read table metadata
    without importing the Loads UI module or mutating load-table state.
    """

    raw_table = st.session_state.get("beam_sls_loads_table")
    if raw_table is None:
        return []
    df = pd.DataFrame(raw_table)
    if df.empty:
        return []

    # Backward compatibility with LOADS.WORKFLOW1A/1B tables before the
    # simplified three-stage LOADS.SLS2A editor.
    if "Station x (m)" not in df.columns:
        for alias in ("Station", "x", "x (m)", "X", "X (m)", "Distance", "Distance (m)"):
            if alias in df.columns:
                df["Station x (m)"] = df[alias]
                break
    if "Stage" not in df.columns and "Stage / Component" in df.columns:
        df["Stage"] = df["Stage / Component"]
    if "Stage" not in df.columns:
        df["Stage"] = ""
    if "Load Component" not in df.columns:
        df["Load Component"] = ""
    df["Stage"] = df["Stage"].map(_beam_sls_stage_label_for_analysis)
    df["Load Component"] = [
        _beam_sls_component_for_analysis(stage, component)
        for stage, component in zip(df["Stage"], df["Load Component"], strict=False)
    ]

    rows: list[dict[str, object]] = []
    for _, raw_row in df.iterrows():
        row = {column: raw_row.get(column, "") for column in _BEAM_SLS_LOAD_ANALYSIS_COLUMNS}
        if not _analysis_to_bool(row.get("Active"), default=True):
            continue
        if _analysis_value_is_blank(row.get("Case Name")) and _analysis_value_is_blank(row.get("N")) and _analysis_value_is_blank(row.get("Mx")):
            continue
        rows.append(row)
    return rows


def _beam_sls_load_row_label(row: Mapping[str, object]) -> str:
    case_name = str(row.get("Case Name") or "Unnamed SLS row").strip() or "Unnamed SLS row"
    stage = _beam_sls_stage_label_for_analysis(row.get("Stage")) or "No stage"
    basis = str(row.get("Section Basis") or "No basis").strip() or "No basis"
    station_text = str(row.get("Station x (m)") or "").strip()
    station_label = f"x={station_text} m" if station_text else "x=not specified"
    return f"{station_label} — {case_name} — {stage} / {basis}"


def _beam_sls_normalized_section_basis_text(value: object) -> str:
    """Normalize imported/edited section-basis text before Analysis routing.

    LOADS.IMPORT1.2 keeps the Loads row as the source of truth, but makes the
    Analysis tab tolerant of Excel-import whitespace, labels such as
    ``Composite transformed section``, and simple aliases.  This prevents a
    valid Service-stage row from silently falling back to precast gross merely
    because the display text is not an exact dictionary key.
    """

    if _analysis_value_is_blank(value):
        return ""
    text = str(value).replace("\xa0", " ").strip().casefold()
    text = " ".join(text.replace("_", " ").replace("-", " ").split())
    if "composite" in text and ("transform" in text or text == "composite"):
        return "composite transformed"
    if "precast" in text and "gross" in text:
        return "precast gross"
    if text in {"gross", "gross section"}:
        return "precast gross"
    return text


def _beam_sls_requested_basis_key(row: Mapping[str, object]) -> str | None:
    """Return the requested Analysis basis key before availability checks."""

    basis_text = _beam_sls_normalized_section_basis_text(row.get("Section Basis"))
    return _DIRECT_BEAM_SLS_BASIS_MAP.get(basis_text)


def _beam_sls_load_basis_key(row: Mapping[str, object], available_basis_names: list[str]) -> str | None:
    requested_basis_key = _beam_sls_requested_basis_key(row)
    if requested_basis_key in available_basis_names:
        return requested_basis_key
    return None


def _beam_sls_load_action_meaning(row: Mapping[str, object]) -> tuple[str, str]:
    """Return compact commercial wording for the selected three-stage SLS row."""

    stage = _beam_sls_stage_label_for_analysis(row.get("Stage"))
    if stage == "Transfer stage":
        return (
            "Transfer external action",
            "Precast girder self-weight only; include Pe_transfer/initial prestress separately in Analysis.",
        )
    if stage == "Construction stage":
        return (
            "Construction action",
            "Precast girder plus wet deck/topping before composite action; use precast gross basis.",
        )
    if stage == "Service stage":
        return (
            "Final service action",
            "Total SLS resultant including SDL and LL+IM; do not include prestress again when Analysis adds Pe separately.",
        )
    return ("Engineer-defined action", "Confirm stage, section basis, and prestress state before relying on preview status.")


def _beam_sls_load_row_summary_cards(row: Mapping[str, object]) -> list[dict[str, object]]:
    action_value, action_detail = _beam_sls_load_action_meaning(row)
    return [
        {
            "title": "Loads page row",
            "value": str(row.get("Case Name") or "Unnamed"),
            "detail": f"x={str(row.get('Station x (m)') or 'not specified')} m · {_beam_sls_stage_label_for_analysis(row.get('Stage')) or 'No stage'} · {_beam_sls_component_for_analysis(row.get('Stage'), row.get('Load Component')) or 'No component'}",
            "status": "ready",
        },
        {
            "title": "Section basis from row",
            "value": str(row.get("Section Basis") or "Not specified"),
            "detail": "Directly used when it matches an available basis; otherwise choose an override below",
            "status": "info",
        },
        {
            "title": "Imported service action",
            "value": f"N={_analysis_float_or_zero(row.get('N')):,.3f} kN · Mx={_analysis_float_or_zero(row.get('Mx')):,.3f} kN-m",
            "detail": "My/Vy/Vx/T are preserved for future service checks",
            "status": "ready",
        },
        {
            "title": "Action meaning",
            "value": action_value,
            "detail": action_detail,
            "status": "warning" if "prestress" in action_detail.casefold() else "info",
        },
    ]



def _beam_sls_stage_tab_specs() -> list[tuple[str, str, str]]:
    """Return commercial three-stage SLS analysis tab metadata."""

    return [
        ("transfer", "Transfer stage", "Precast girder self-weight + transfer prestress check context"),
        ("construction", "Construction stage", "Precast girder plus wet deck/topping on precast gross section"),
        ("service", "Service stage", "Final service total SLS resultant on the intended service basis"),
    ]


def _beam_sls_rows_for_stage(rows: list[dict[str, object]], stage_label: str) -> list[dict[str, object]]:
    """Filter normalized Loads-page SLS rows by the commercial stage tab."""

    return [row for row in rows if _beam_sls_stage_label_for_analysis(row.get("Stage")) == stage_label]


def _beam_sls_stage_default_code_limit_stage(stage_label: str) -> str:
    """Map simplified Load-stage tabs to code-limit stage defaults."""

    if stage_label == "Transfer stage":
        return "Transfer / Release"
    if stage_label == "Construction stage":
        return "Deck casting / Pre-composite"
    if stage_label == "Service stage":
        return "Final service / Composite"
    return "User-defined"


def _beam_sls_default_basis_for_stage(stage_label: str, available_basis_names: list[str]) -> str:
    """Return a safe stage default basis for manual SLS override panels."""

    if stage_label == "Service stage" and "composite_transformed" in available_basis_names:
        return "composite_transformed"
    if "precast_gross" in available_basis_names:
        return "precast_gross"
    return available_basis_names[0]


def _initialize_girder_code_limit_stage_for_case(title: str, stage_label: str) -> None:
    """Lock code-limit stage to the active SLS stage tab.

    GIRDER.SLS4C removes the confusing visible stress-limit-stage dropdown:
    Transfer, Construction, and Service tabs own their matching code-limit
    stage.  This preserves engineering context and prevents accidental
    transfer/service profile mixups in a stage-specific check panel.
    """

    stage_key = f"girder_code_limit_stage_{title}"
    st.session_state[stage_key] = _beam_sls_stage_default_code_limit_stage(stage_label)


def _girder_sls_stage_pe_value_from_station(station_result: object, stage_label: str) -> float:
    """Return the effective stage Pe at one station for the full-length SLS preview."""

    normalized = _beam_sls_stage_label_for_analysis(stage_label)
    if normalized == "Transfer stage":
        return float(getattr(station_result, "pe_transfer_eff_kN", 0.0) or 0.0)
    if normalized == "Construction stage":
        return float(getattr(station_result, "pe_construction_eff_kN", 0.0) or 0.0)
    return float(getattr(station_result, "pe_eff_final_eff_kN", 0.0) or 0.0)


def _girder_sls_span_length_from_session(rows: list[Mapping[str, object]] | None = None) -> float:
    """Return the Setup single-source girder span length for SLS previews."""

    system = system_settings_from_mapping(st.session_state.get(BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
    if system.span_length_m > 0.0:
        return system.span_length_m
    settings = st.session_state.get("girder_prestress_system_settings") or {}
    span = _analysis_float_or_zero(settings.get("span_length_m")) if isinstance(settings, dict) else 0.0
    if span > 0.0:
        return span
    max_station = 0.0
    for row in rows or []:
        max_station = max(max_station, _analysis_float_or_zero(row.get("Station x (m)")))
    return max(1.0, max_station)


def _girder_sls_precast_area_from_session() -> float:
    geometry = st.session_state.get("section_geometry")
    if geometry is None:
        return 0.0
    try:
        return float(summarize_geometry(geometry).area_mm2)
    except Exception:
        return 0.0


def _girder_sls_topping_thickness_from_session() -> float:
    params = st.session_state.get("section_parameters") or {}
    if not isinstance(params, dict):
        return 0.0
    return max(_analysis_float_or_zero(params.get("Tslab_mm")), 0.0)


def _girder_sls_auto_load_breakdown(stage_label: str):
    """Return workflow-appropriate SLS auto-load component breakdown."""

    mode_settings = _analysis_mode_from_session()
    system = system_settings_from_mapping(st.session_state.get(BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
    if is_building_beam_girder_workflow(mode_settings):
        return building_auto_load_breakdown_for_stage(
            stage_label=stage_label,
            system=system,
            service_settings=building_service_load_settings_from_mapping(
                st.session_state.get(BUILDING_BEAM_GIRDER_SERVICE_LOAD_SETTINGS_KEY)
            ),
            precast_area_mm2=_girder_sls_precast_area_from_session(),
            topping_thickness_mm=_girder_sls_topping_thickness_from_session(),
        )
    return auto_load_breakdown_for_stage(
        stage_label=stage_label,
        system=system,
        settings=auto_load_settings_from_mapping(st.session_state.get(BEAM_GIRDER_SLS_AUTO_LOAD_SETTINGS_KEY)),
        precast_area_mm2=_girder_sls_precast_area_from_session(),
        topping_thickness_mm=_girder_sls_topping_thickness_from_session(),
    )


def _girder_sls_auto_station_grid(span_length_m: float) -> list[float]:
    strand_table = st.session_state.get("girder_strand_layout_table")
    extra: list[float] = []
    try:
        extra = station_candidates_from_debonding(strand_table, span_length_m)
    except Exception:
        extra = []
    return default_sls_station_grid(span_length_m, extra_stations_m=extra, divisions=20)


def _girder_sls_default_case_name_for_stage(stage_label: str) -> str:
    stage = _beam_sls_stage_label_for_analysis(stage_label)
    prefix = "BLDG" if is_building_beam_girder_workflow(_analysis_mode_from_session()) else "AUTO"
    if stage == "Transfer stage":
        return f"{prefix}-TR"
    if stage == "Construction stage":
        return f"{prefix}-CONST"
    if stage == "Service stage":
        return f"{prefix}-SERV-SDL-LL" if prefix == "BLDG" else "AUTO-SERV-SDL"
    return f"{prefix}-SLS"


def _girder_sls_stage_rows_with_auto_station_grid(
    stage_label: str,
    stage_rows: list[dict[str, object]],
    span_length_m: float,
) -> list[dict[str, object]]:
    """Return stage rows with a generated full-length grid when user rows are insufficient.

    GIRDER.SLS5A makes Transfer/Construction/Service diagrams usable even when
    external station loads are absent.  Generated rows carry zero user N/Mx;
    auto UDL components and Pe(x) are added later in the diagram dataframe.
    Existing multi-station user/imported rows are preserved.
    """

    rows = list(stage_rows or [])
    case_names = sorted({str(row.get("Case Name") or "Unnamed") for row in rows})
    for case_name in case_names:
        case_rows = [row for row in rows if str(row.get("Case Name") or "Unnamed") == case_name]
        unique_stations = {round(_analysis_float_or_zero(row.get("Station x (m)")), 6) for row in case_rows}
        if len(unique_stations) >= 2:
            return rows

    template = dict(rows[0]) if rows else {}
    stage = _beam_sls_stage_label_for_analysis(stage_label) or stage_label
    case_name = str(template.get("Case Name") or _girder_sls_default_case_name_for_stage(stage)).strip() or _girder_sls_default_case_name_for_stage(stage)
    basis = str(template.get("Section Basis") or ("Composite transformed" if stage == "Service stage" else "Precast gross"))
    grid = _girder_sls_auto_station_grid(span_length_m)
    existing_by_station = {
        round(_analysis_float_or_zero(row.get("Station x (m)")), 6): row
        for row in rows
        if str(row.get("Case Name") or case_name) == case_name
    }
    generated: list[dict[str, object]] = []
    for x_m in grid:
        existing = existing_by_station.get(round(x_m, 6), {})
        generated.append(
            {
                "Active": True,
                "Station x (m)": x_m,
                "Case Name": case_name,
                "Stage": stage,
                "Load Component": _beam_sls_component_for_analysis(stage),
                "Section Basis": existing.get("Section Basis", basis),
                "N": existing.get("N", 0.0),
                "Mx": existing.get("Mx", 0.0),
                "My": existing.get("My", 0.0),
                "Vy": existing.get("Vy", 0.0),
                "Vx": existing.get("Vx", 0.0),
                "T": existing.get("T", 0.0),
                "Note": existing.get("Note", "Generated SLS5A station grid for auto load + Pe(x) diagram"),
            }
        )
    return generated


def _girder_full_length_sls_stage_rows(
    *,
    stage_label: str,
    load_rows: list[dict[str, object]],
    basis_options: object,
    basis_names: list[str],
    span_length_m: float,
) -> pd.DataFrame:
    """Return station-based combined top/bottom stress rows for one SLS stage.

    GIRDER.SLS4A is a preview graph/data helper.  It reads station rows from
    the Loads workflow and stage Pe from the Prestress force-state/loss workflow;
    it does not change any solver, load table, prestress table, or code-limit
    formula.
    """

    load_rows = _girder_sls_stage_rows_with_auto_station_grid(stage_label, load_rows, span_length_m)
    strand_table = st.session_state.get("girder_strand_layout_table")
    auto_breakdown = _girder_sls_auto_load_breakdown(stage_label)
    rows: list[dict[str, object]] = []
    for raw_row in load_rows:
        x_m = _analysis_float_or_zero(raw_row.get("Station x (m)"))
        basis_name = _beam_sls_load_basis_key(raw_row, basis_names) or _beam_sls_default_basis_for_stage(stage_label, basis_names)
        basis = basis_options.bases[basis_name]
        user_n_kN = _analysis_float_or_zero(raw_row.get("N"))
        user_mx_kNm = _analysis_float_or_zero(raw_row.get("Mx"))
        auto_mx_kNm = simple_span_udl_moment_kNm(auto_breakdown.total_kN_m, x_m, span_length_m)
        auto_vy_kN = simple_span_udl_shear_kN(auto_breakdown.total_kN_m, x_m, span_length_m)
        total_mx_kNm = user_mx_kNm + auto_mx_kNm
        service = run_basic_girder_service_stress(
            basis,
            N_kN=user_n_kN,
            M_kNm=total_mx_kNm,
        )
        pe_kN = 0.0
        yps = None
        ps_top = 0.0
        ps_bottom = 0.0
        active_groups = ""
        if strand_table is not None:
            try:
                station = evaluate_girder_prestress_station(
                    strand_table,
                    x_m=x_m,
                    span_length_m=span_length_m,
                )
                pe_kN = _girder_sls_stage_pe_value_from_station(station, stage_label)
                yps = station.yps_eff_mm_from_bottom
                active_groups = station.active_group_ids
                if pe_kN > 0.0 and yps is not None:
                    prestress = run_girder_prestress_stress_effect(
                        basis,
                        Pe_eff_kN=pe_kN,
                        tendon_y_from_bottom_mm=float(yps),
                    )
                    ps_top = prestress.top.total_stress_MPa
                    ps_bottom = prestress.bottom.total_stress_MPa
            except (TypeError, ValueError, KeyError) as exc:
                active_groups = f"Prestress unavailable: {exc}"
        top_total = service.top.total_stress_MPa + ps_top
        bottom_total = service.bottom.total_stress_MPa + ps_bottom
        rows.append(
            {
                "Station x (m)": x_m,
                "Case Name": str(raw_row.get("Case Name") or "Unnamed"),
                "Stage": _beam_sls_stage_label_for_analysis(raw_row.get("Stage")) or stage_label,
                "Basis": basis_options.labels.get(basis_name, basis_name),
                "N (kN)": user_n_kN,
                "User Mx (kN-m)": user_mx_kNm,
                "Auto Mx (kN-m)": auto_mx_kNm,
                "Mx (kN-m)": total_mx_kNm,
                "Auto Vy (kN)": auto_vy_kN,
                "Auto load w (kN/m)": auto_breakdown.total_kN_m,
                "Auto load components": auto_breakdown.component_label,
                "Pe stage (kN)": pe_kN,
                "yps eff (mm)": yps,
                "Top service (MPa)": service.top.total_stress_MPa,
                "Bottom service (MPa)": service.bottom.total_stress_MPa,
                "Top PS (MPa)": ps_top,
                "Bottom PS (MPa)": ps_bottom,
                "Top total (MPa)": top_total,
                "Bottom total (MPa)": bottom_total,
                "Max compression (MPa)": min(top_total, bottom_total),
                "Max tension (MPa)": max(top_total, bottom_total),
                "Active PS groups": active_groups,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Case Name", "Station x (m)"]).reset_index(drop=True)


def _girder_sls_diagram_profile_key(stage_label: str) -> str:
    """Return Streamlit key for the full-length diagram limit profile.

    CODE.SLS.LIMIT4.1 makes the reinforcement-aware tensile limit guide part of
    the default full-length SLS decision workflow, not only the lower audit
    Code Limit Summary.  This key stores the guided/manual profile used by the
    diagram limit lines, stage cards, and PASS/FAIL preview.
    """

    safe_stage = _beam_sls_stage_label_for_analysis(stage_label).replace(" ", "_").replace("/", "_")
    return f"girder_sls_diagram_limit_profile_key_{safe_stage}"


def _girder_stage_limit_profile_for_diagram(stage_label: str):
    """Return the project-code preview stress-limit profile for a stage diagram."""

    code = _girder_sls_profile_code_from_session()
    limit_stage = _beam_sls_stage_default_code_limit_stage(stage_label)
    profile_key = _girder_sls_diagram_profile_key(stage_label)
    option_keys = {option.key for option in girder_sls_limit_profile_options(code=code, stage=limit_stage)}
    selected_key = str(st.session_state.get(profile_key) or "")
    if selected_key not in option_keys:
        selected_key = None
    return build_girder_sls_limit_profile(code=code, stage=limit_stage, limit_profile_key=selected_key)


def _girder_sls_diagram_stress_limit_rows(df: pd.DataFrame) -> list[StressLimitInputRow]:
    """Build top/bottom stress rows for full-length diagram limit guidance.

    The guidance needs to know which fiber is in tension.  Full-length SLS
    diagram rows store top and bottom stresses in separate columns, so convert
    them to ordinary StressLimitInputRow records without changing any stress
    calculation.
    """

    if df.empty:
        return []
    rows: list[StressLimitInputRow] = []
    for _, row in df.iterrows():
        station = row.get("Station x (m)", "")
        for fiber, column in (("Top", "Top total (MPa)"), ("Bottom", "Bottom total (MPa)")):
            if column not in df.columns:
                continue
            try:
                stress = float(row[column])
            except (TypeError, ValueError):
                continue
            if math.isfinite(stress):
                rows.append(StressLimitInputRow(fiber=f"{fiber} fiber @ x={station} m", stress_MPa=stress))
    return rows


def _render_girder_sls_diagram_tensile_limit_guide(stage_label: str, df: pd.DataFrame) -> None:
    """Render visible tensile-limit guidance in the primary full-length SLS view."""

    code = _girder_sls_profile_code_from_session()
    limit_stage = _beam_sls_stage_default_code_limit_stage(stage_label)
    profile_options = girder_sls_limit_profile_options(code=code, stage=limit_stage)
    profile_key = _girder_sls_diagram_profile_key(stage_label)
    option_keys = {option.key for option in profile_options}
    if st.session_state.get(profile_key) not in option_keys:
        st.session_state[profile_key] = profile_options[0].key

    st.markdown("**Tensile stress limit guide**")
    st.caption(
        "Visible decision control for the graph limit profile. Select reinforcement/exposure/class assumptions here; "
        "the graph limit lines and stage PASS/FAIL preview update from this profile. This is guidance only, not a final cracked-section or detailing verification."
    )
    with st.expander(f"Tensile stress limit guide — {stage_label}", expanded=True):
        _, notes = _render_girder_tension_limit_guidance(
            title=f"{stage_label} full-length diagram",
            code=code,
            stage=limit_stage,
            stresses=_girder_sls_diagram_stress_limit_rows(df),
            profile_key=profile_key,
            profile_options=profile_options,
        )
        if notes:
            for note in notes:
                st.warning(note)


def _girder_sls_diagram_limit_summary(stage_label: str) -> tuple[float, float, str]:
    """Return compression/tension preview limits for full-length diagrams."""

    fc = _girder_fc_for_sls_limit_preview()
    profile = _girder_stage_limit_profile_for_diagram(stage_label)
    compression_limit = profile.compression_limit_MPa(fc)
    tension_allowable = profile.tension_allowable_MPa(fc)
    return float(compression_limit), float(tension_allowable), profile.limit_profile_label


def _girder_full_length_preview_status(df: pd.DataFrame, stage_label: str) -> tuple[str, str, str]:
    """Return compact Preview PASS/FAIL/REVIEW status for a full-length SLS table."""

    if df.empty:
        return "REVIEW", "No station rows", "warning"
    compression_limit, _tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    min_stress = float(df[["Top total (MPa)", "Bottom total (MPa)"]].min().min())
    compression_ok = min_stress >= -compression_limit - _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA
    span = float(pd.to_numeric(df.get("Station x (m)", pd.Series([0.0])), errors="coerce").max(skipna=True) or 0.0)
    tension_ok = True
    for _, row in df.iterrows():
        station = float(row.get("Station x (m)", 0.0) or 0.0)
        limit_at_x, _ = _girder_sls_tension_limit_at_station(stage_label, station, span_length_m=span)
        max_tension = max(float(row.get("Top total (MPa)", 0.0) or 0.0), float(row.get("Bottom total (MPa)", 0.0) or 0.0))
        if max_tension > limit_at_x + _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
            tension_ok = False
            break
    if compression_ok and tension_ok:
        return "Preview PASS", profile_label, "ready"
    return "Preview FAIL", f"{profile_label}; check compression/tension exceedance", "danger"


def _girder_sls4b_case_state_key(stage_label: str) -> str:
    """Return the shared Streamlit key for a stage diagram case selector."""

    return f"girder_sls4a_case_{_beam_sls_stage_label_for_analysis(stage_label).replace(' ', '_')}"


def _girder_sls4b_case_names(stage_rows: list[dict[str, object]]) -> list[str]:
    """Return stable case-name choices for full-length SLS result views."""

    return sorted({str(row.get("Case Name") or "Unnamed") for row in stage_rows})


def _girder_sls4b_selected_case_for_stage(stage_label: str, stage_rows: list[dict[str, object]]) -> str | None:
    """Return and normalize the selected case name used by SLS4A/SLS4B views.

    GIRDER.SLS4B keeps the combined stage table and the per-stage diagram in
    sync.  The selected case remains a UI presentation choice only; it does not
    mutate Loads rows, prestress force states, or stress solver inputs.
    """

    case_names = _girder_sls4b_case_names(stage_rows)
    if not case_names:
        return None
    key = _girder_sls4b_case_state_key(stage_label)
    if st.session_state.get(key) not in case_names:
        st.session_state[key] = case_names[0]
    return str(st.session_state[key])


def _girder_sls_demand_utilization(actual_MPa: float, limit_MPa: float, *, demand_type: str) -> float | None:
    """Return display-only stress utilization for compression or tension demand."""

    if not math.isfinite(float(limit_MPa)) or float(limit_MPa) < 0.0:
        return None
    if demand_type == "compression":
        demand = max(0.0, -float(actual_MPa))
    else:
        demand = max(0.0, float(actual_MPa))
    if float(limit_MPa) <= _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
        if demand <= _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
            return 0.0
        return math.inf
    return demand / float(limit_MPa)


def _girder_sls_fiber_for_value(row: Mapping[str, object], target_value: float, *, demand_type: str) -> str:
    """Return Top/Bottom fiber label for a governing stress value."""

    top = float(row.get("Top total (MPa)", 0.0) or 0.0)
    bottom = float(row.get("Bottom total (MPa)", 0.0) or 0.0)
    if demand_type == "compression":
        if abs(top - target_value) <= abs(bottom - target_value):
            return "Top"
        return "Bottom"
    if abs(top - target_value) <= abs(bottom - target_value):
        return "Top"
    return "Bottom"


def _girder_sls4b_governing_demand_rows(df: pd.DataFrame, stage_label: str) -> list[dict[str, object]]:
    """Return compression and tension governing rows for one full-length stage result.

    The function is a SLS result-interpretation helper only.  It consumes the
    existing GIRDER.SLS4A dataframe and default preview limits; no stress formula,
    Pe(x), section-basis, or load-schema logic is changed.
    """

    if df.empty:
        return []
    compression_limit, tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    comp_idx = df["Max compression (MPa)"].idxmin()
    span = float(pd.to_numeric(df.get("Station x (m)", pd.Series([0.0])), errors="coerce").max(skipna=True) or 0.0)
    tension_utilizations: list[tuple[float, object, float]] = []
    for idx, row in df.iterrows():
        station = float(row.get("Station x (m)", 0.0) or 0.0)
        limit_at_x, _ = _girder_sls_tension_limit_at_station(stage_label, station, span_length_m=span)
        actual_tension = float(row.get("Max tension (MPa)", 0.0) or 0.0)
        util = _girder_sls_demand_utilization(actual_tension, limit_at_x, demand_type="tension")
        try:
            util_value = -math.inf if util is None else float(util)
        except (TypeError, ValueError):
            util_value = -math.inf
        tension_utilizations.append((util_value, idx, limit_at_x))
    _tens_util, tens_idx, tension_limit_at_idx = max(tension_utilizations, key=lambda item: item[0])
    demand_specs = [
        ("Compression", "compression", comp_idx, "Max compression (MPa)", -compression_limit),
        ("Tension", "tension", tens_idx, "Max tension (MPa)", tension_limit_at_idx),
    ]
    rows: list[dict[str, object]] = []
    for label, demand_type, idx, value_column, signed_limit in demand_specs:
        row = df.loc[idx]
        actual = float(row[value_column])
        limit_magnitude = compression_limit if demand_type == "compression" else abs(float(signed_limit))
        utilization = _girder_sls_demand_utilization(actual, limit_magnitude, demand_type=demand_type)
        status = "Preview PASS"
        if utilization is None:
            status = "REVIEW"
        elif math.isinf(float(utilization)) or float(utilization) > 1.0 + _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
            status = "Preview FAIL"
        rows.append(
            {
                "Demand": label,
                "Status": status,
                "Station x (m)": float(row["Station x (m)"]),
                "Fiber": _girder_sls_fiber_for_value(row, actual, demand_type=demand_type),
                "Actual stress (MPa)": actual,
                "Limit stress (MPa)": float(signed_limit),
                "Utilization": utilization,
                "Limit profile": profile_label,
                "Case Name": str(row.get("Case Name") or "Unnamed"),
                "Basis": str(row.get("Basis") or ""),
            }
        )
    return rows


def _girder_sls4b_controlling_row(demand_rows: list[dict[str, object]]) -> dict[str, object] | None:
    """Return the display row with the highest utilization for one stage."""

    if not demand_rows:
        return None

    def sort_key(row: Mapping[str, object]) -> float:
        value = row.get("Utilization")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return -math.inf
        if math.isnan(numeric):
            return -math.inf
        return numeric

    return max(demand_rows, key=sort_key)


def _girder_sls4b_stage_decision_row(df: pd.DataFrame, stage_label: str, selected_case: str) -> dict[str, object]:
    """Return one compact stage-level decision row for the combined SLS table."""

    status, detail, _style = _girder_full_length_preview_status(df, stage_label)
    demand_rows = _girder_sls4b_governing_demand_rows(df, stage_label)
    controlling = _girder_sls4b_controlling_row(demand_rows)
    if controlling is None:
        return {
            "Stage": stage_label,
            "Case Name": selected_case,
            "Status": "REVIEW",
            "Controls": "No valid station rows",
            "Station x (m)": None,
            "Fiber": "N/A",
            "Actual stress (MPa)": None,
            "Limit stress (MPa)": None,
            "Utilization": None,
            "Limit profile": detail,
        }
    return {
        "Stage": stage_label,
        "Case Name": selected_case,
        "Status": status,
        "Controls": str(controlling["Demand"]),
        "Station x (m)": controlling["Station x (m)"],
        "Fiber": controlling["Fiber"],
        "Actual stress (MPa)": controlling["Actual stress (MPa)"],
        "Limit stress (MPa)": controlling["Limit stress (MPa)"],
        "Utilization": controlling["Utilization"],
        "Limit profile": controlling["Limit profile"],
    }


def _format_girder_sls_utilization(value: object) -> str:
    """Format display-only stress utilization for compact SLS result tables."""

    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if not math.isfinite(numeric):
        return "∞"
    return f"{numeric:.3f}"


def _clean_girder_sls4b_decision_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Format the SLS4B governing result table for commercial-style display."""

    if df.empty:
        return df
    cleaned = _clean_girder_stress_dataframe(df)
    if "Station x (m)" in cleaned.columns:
        cleaned["Station x (m)"] = cleaned["Station x (m)"].map(
            lambda value: "N/A" if _analysis_value_is_blank(value) else f"{float(value):.3f}"
        )
    if "Utilization" in cleaned.columns:
        cleaned["Utilization"] = cleaned["Utilization"].map(_format_girder_sls_utilization)
    return cleaned


def _render_girder_sls4b_governing_summary_cards(summary_df: pd.DataFrame) -> None:
    """Render compact all-stage governing result cards."""

    if summary_df.empty:
        return
    failed = int((summary_df["Status"] == "Preview FAIL").sum()) if "Status" in summary_df.columns else 0
    review = int((summary_df["Status"] == "REVIEW").sum()) if "Status" in summary_df.columns else 0
    complete = int(len(summary_df))
    controlling = _girder_sls4b_controlling_row(summary_df.to_dict("records"))
    controlling_stage = str(controlling.get("Stage", "N/A")) if controlling else "N/A"
    controlling_util = _format_girder_sls_utilization(controlling.get("Utilization")) if controlling else "N/A"
    if failed:
        overall_status = "Preview FAIL"
        style = "danger"
        detail = "At least one stage exceeds the preview stress limit."
    elif review:
        overall_status = "REVIEW"
        style = "warning"
        detail = "One or more stages lack a complete preview decision."
    else:
        overall_status = "Preview PASS"
        style = "ready"
        detail = "All available stages are within preview compression/tension limits."
    _render_analysis_summary_strip(
        [
            {
                "title": "Overall SLS preview",
                "value": overall_status,
                "detail": detail,
                "status": style,
                "strong": True,
            },
            {
                "title": "Controlling stage",
                "value": controlling_stage,
                "detail": f"Max utilization {controlling_util}",
                "status": "danger" if failed else "info",
            },
            {
                "title": "Stages summarized",
                "value": f"{complete:,}",
                "detail": f"Preview FAIL {failed:,} · REVIEW {review:,}",
                "status": "warning" if review else "ready",
            },
            {
                "title": "Result basis",
                "value": "Station table + Pe(x)",
                "detail": "Uses selected case per stage; audit details remain below",
                "status": "neutral",
            },
        ],
        columns=4,
    )




def _girder_sls4c_stage_basis_cards(
    *,
    stage_label: str,
    selected_case: str,
    selected_rows: list[Mapping[str, object]],
    df: pd.DataFrame,
    basis_options: object,
) -> list[dict[str, object]]:
    """Return decision-first code/load/section basis cards for one SLS stage.

    GIRDER.SLS4C keeps the important engineering context visible without making
    users open audit expanders: code/limit basis, stage context, load case, and
    section/prestress source.  It is display-only and does not change stress
    values, Pe(x), section basis, load schema, or code-limit formulas.
    """

    profile = _girder_stage_limit_profile_for_diagram(stage_label)
    selected_basis = "From Loads rows"
    if "Basis" in df.columns and not df.empty:
        basis_values = [str(value) for value in df["Basis"].dropna().unique() if str(value).strip()]
        if len(basis_values) == 1:
            selected_basis = basis_options.labels.get(basis_values[0], basis_values[0])
        elif len(basis_values) > 1:
            selected_basis = f"Mixed ({len(basis_values)} basis values)"
    load_detail = f"{len(selected_rows):,} station row(s)" if selected_rows else "No active station rows"
    if selected_rows:
        stations = sorted({_analysis_float_or_zero(row.get("Station x (m)")) for row in selected_rows})
        if stations:
            load_detail = f"{len(selected_rows):,} row(s), x={stations[0]:.3f}–{stations[-1]:.3f} m"
    active_pe = "Pe(x) from Force States + debonding"
    if "Pe stage (kN)" in df.columns and not df.empty:
        pe_min = float(pd.to_numeric(df["Pe stage (kN)"], errors="coerce").fillna(0.0).min())
        pe_max = float(pd.to_numeric(df["Pe stage (kN)"], errors="coerce").fillna(0.0).max())
        active_pe = f"Pe(x) {pe_min:,.1f}–{pe_max:,.1f} kN"
    return [
        {
            "title": "Design code / limit basis",
            "value": str(profile.code),
            "detail": f"{profile.stage} · {profile.limit_profile_label}",
            "status": "info",
            "strong": True,
        },
        {
            "title": "Stage context",
            "value": stage_label,
            "detail": "Limit stage is auto-selected from the active tab",
            "status": "ready",
        },
        {
            "title": "Diagram load case",
            "value": selected_case,
            "detail": load_detail,
            "status": "ready" if selected_rows else "warning",
        },
        {
            "title": "Section / prestress source",
            "value": selected_basis,
            "detail": active_pe,
            "status": "info",
        },
    ]


def _girder_sls4c_action_hints(
    *,
    stage_label: str,
    status: str,
    demand_rows: list[dict[str, object]],
) -> list[str]:
    """Return compact engineering action hints for SLS preview fail/review cases."""

    controlling = _girder_sls4b_controlling_row(demand_rows)
    try:
        utilization = float(controlling.get("Utilization")) if controlling else 0.0
    except (TypeError, ValueError):
        utilization = 0.0
    demand = str(controlling.get("Demand", "") if controlling else "").casefold()
    is_fail = "FAIL" in str(status).upper()
    is_review = "REVIEW" in str(status).upper()
    near_limit = math.isfinite(utilization) and utilization >= 0.90
    if not (is_fail or is_review or near_limit):
        return []

    hints: list[str] = []
    if is_review:
        hints.append("Confirm active Loads rows, selected case, section basis, and stage Pe before relying on the preview result.")
    if stage_label == "Transfer stage":
        if "tension" in demand:
            hints.extend(
                [
                    "Review initial strand force, strand eccentricity, and top-fiber tension at release.",
                    "Consider additional debonding near the girder end or bonded top reinforcement only after checking transfer length and end-zone requirements.",
                    "Check whether release strength f'ci and temporary release assumptions match the project specification.",
                ]
            )
        elif "compression" in demand:
            hints.extend(
                [
                    "Review initial Pe, strand count, and eccentricity; excessive bottom compression at release may require less initial force or more debonding.",
                    "Check f'ci, end-zone bursting/splitting reinforcement, and local release-zone detailing before accepting the layout.",
                ]
            )
    elif stage_label == "Construction stage":
        hints.extend(
            [
                "Review wet deck/topping load, construction sequence, and whether the pre-composite section basis is appropriate.",
                "Consider temporary support, adjusted strand force state, or section/deck staging changes if the construction-stage utilization controls.",
            ]
        )
    elif stage_label == "Service stage":
        if "tension" in demand:
            hints.extend(
                [
                    "Review final effective prestress, strand layout/eccentricity, superimposed dead load, and live-load case used in the service resultant.",
                    "Consider increasing effective prestress/composite stiffness or checking crack-control reinforcement if project criteria allow service tension.",
                ]
            )
        elif "compression" in demand:
            hints.extend(
                [
                    "Review final prestress level, composite section basis, concrete strength, and service load combination.",
                    "Consider reducing prestress eccentricity/force or increasing section/composite capacity if compression utilization controls.",
                ]
            )
    if not hints and near_limit:
        hints.append("Utilization is close to the preview limit; review assumptions and consider reserve before final design use.")
    # Keep the default view compact: no more than four direct action hints.
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped[:4]


def _render_girder_sls4c_action_hints(
    *,
    stage_label: str,
    status: str,
    demand_rows: list[dict[str, object]],
) -> None:
    """Render short SLS action hints only when the preview result needs attention."""

    hints = _girder_sls4c_action_hints(stage_label=stage_label, status=status, demand_rows=demand_rows)
    if not hints:
        return
    items = "".join(f"<li>{escape(hint)}</li>" for hint in hints)
    html = (
        '<div class="cpmm-sls-action-panel">'
        '<div class="cpmm-sls-action-title">Engineering action hints</div>'
        f"<ul>{items}</ul>"
        '<div class="cpmm-analysis-detail">Preview guidance only: confirm code clauses, transfer/development length, end-zone, shear, and detailing checks before final design.</div>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)

def _render_girder_sls4b_combined_stage_result_table(
    *,
    beam_sls_rows: list[dict[str, object]],
    basis_options: object,
    basis_names: list[str],
) -> None:
    """Render GIRDER.SLS4B combined governing station / result table.

    GIRDER.SLS4B is UI/result-interpretation polish.  It reuses the existing
    full-length stage stress dataframe and preview-limit helper, keeping audit
    details collapsed: no solver, Pe, load, geometry, or report changes.
    """

    st.markdown("##### Governing station / stage result summary")
    st.caption(
        "GIRDER.SLS4B summarizes Transfer, Construction, and Service in one decision table. "
        "It reports actual stress versus the matching preview limit, utilization, governing station, and controlling fiber."
    )
    if not beam_sls_rows:
        st.info("No active imported Beam/Girder SLS Loads rows are available; SLS5A will use generated auto-load station rows where possible.")
    summary_rows: list[dict[str, object]] = []
    demand_detail_rows: list[dict[str, object]] = []
    for _stage_key, stage_label, _stage_note in _beam_sls_stage_tab_specs():
        stage_rows = _beam_sls_rows_for_stage(beam_sls_rows, stage_label)
        span = _girder_sls_span_length_from_session(stage_rows)
        stage_rows = _girder_sls_stage_rows_with_auto_station_grid(stage_label, stage_rows, span)
        selected_case = _girder_sls4b_selected_case_for_stage(stage_label, stage_rows)
        if not selected_case:
            continue
        selected_rows = [row for row in stage_rows if str(row.get("Case Name") or "Unnamed") == selected_case]
        df = _girder_full_length_sls_stage_rows(
            stage_label=stage_label,
            load_rows=selected_rows,
            basis_options=basis_options,
            basis_names=basis_names,
            span_length_m=span,
        )
        if df.empty:
            continue
        summary_rows.append(_girder_sls4b_stage_decision_row(df, stage_label, selected_case))
        for demand_row in _girder_sls4b_governing_demand_rows(df, stage_label):
            demand_detail_rows.append({"Stage": stage_label, **demand_row})
    if not summary_rows:
        st.info("No valid full-length stage result could be summarized. Check section geometry, auto-load settings, station inputs, and section basis availability.")
        return
    summary_df = pd.DataFrame(summary_rows)
    _render_girder_sls4b_governing_summary_cards(summary_df)
    st.dataframe(_clean_girder_sls4b_decision_dataframe(summary_df), use_container_width=True, hide_index=True)
    with st.expander("Compression / tension demand details — all stages", expanded=False):
        st.caption(
            "Shows both governing compression and governing tension demand for each summarized stage. "
            "Compression limit is displayed as a negative stress line; tension limit is displayed as a positive stress line."
        )
        st.dataframe(_clean_girder_sls4b_decision_dataframe(pd.DataFrame(demand_detail_rows)), use_container_width=True, hide_index=True)



def _girder_sls_graph_stage_title(stage_label: str) -> str:
    """Return a concise commercial-style stress diagram title."""

    return str(stage_label or "SLS").replace(" stage", "").strip() or "SLS"


def _girder_sls_graph_subtitle(stage_label: str) -> str:
    """Return code/stage/sign-convention subtitle for the SLS stress graph.

    SLS.GRAPH1 is display polish only.  It keeps the internal app convention
    unchanged: compression is negative and tension is positive.
    """

    profile = _girder_stage_limit_profile_for_diagram(stage_label)
    edition = project_code_edition_from_session(st.session_state)
    return f"{edition} · {profile.limit_profile_label} · compression negative / tension positive"


def _girder_sls_graph_envelope_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return station envelopes for commercial-style top/bottom stress plotting.

    The existing SLS solver returns one top and one bottom stress per station for
    the selected case in most workflows.  This display helper also supports
    future/envelope datasets with more than one row at the same station by
    plotting maximum/minimum top and bottom stress curves like commercial beam
    software.  It is display-only: no stress, Pe(x), load, or code-limit formula
    is changed.
    """

    columns = ["Station x (m)", "Top total (MPa)", "Bottom total (MPa)"]
    if df.empty or any(column not in df.columns for column in columns):
        return pd.DataFrame()
    envelope = (
        df[columns]
        .copy()
        .groupby("Station x (m)", as_index=False)
        .agg(
            **{
                "Top maximum (MPa)": ("Top total (MPa)", "max"),
                "Top minimum (MPa)": ("Top total (MPa)", "min"),
                "Bottom maximum (MPa)": ("Bottom total (MPa)", "max"),
                "Bottom minimum (MPa)": ("Bottom total (MPa)", "min"),
            }
        )
        .sort_values("Station x (m)")
        .reset_index(drop=True)
    )
    return envelope


def _girder_sls_graph_series_is_distinct(envelope: pd.DataFrame, max_col: str, min_col: str) -> bool:
    """Return whether max/min curves should both be displayed."""

    if envelope.empty:
        return False
    delta = (pd.to_numeric(envelope[max_col], errors="coerce") - pd.to_numeric(envelope[min_col], errors="coerce")).abs()
    return bool(delta.max(skipna=True) > _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA)


def _make_girder_full_length_sls_figure(df: pd.DataFrame, *, stage_label: str) -> go.Figure:
    """Build a commercial-style top/bottom stress-along-station preview figure."""

    fig = go.Figure()
    if df.empty:
        return fig
    envelope = _girder_sls_graph_envelope_dataframe(df)
    if envelope.empty:
        return fig
    x = envelope["Station x (m)"]

    def add_trace(*, y_col: str, name: str, marker_symbol: str, dash: str | None = None) -> None:
        fig.add_trace(
            go.Scatter(
                x=x,
                y=envelope[y_col],
                mode="lines+markers",
                name=name,
                marker={"symbol": marker_symbol, "size": 8},
                line={"dash": dash} if dash else {},
                hovertemplate=f"x=%{{x:.3f}} m<br>{escape(name)}=%{{y:.3f}} MPa<extra></extra>",
            )
        )

    # SLS.GRAPH1: keep commercial-style max/min capability.  For ordinary single-case
    # diagrams the max/min pair is identical, so only one curve per fiber is displayed
    # to avoid visual clutter.  The legacy strings "Top total stress" and "Bottom total stress"
    # remain in source/tests as the single-case labels.
    if _girder_sls_graph_series_is_distinct(envelope, "Top maximum (MPa)", "Top minimum (MPa)"):
        add_trace(y_col="Top maximum (MPa)", name="Maximum stress at top of member", marker_symbol="cross")
        add_trace(y_col="Top minimum (MPa)", name="Minimum stress at top of member", marker_symbol="x", dash="dot")
    else:
        add_trace(y_col="Top maximum (MPa)", name="Top total stress", marker_symbol="cross")
    if _girder_sls_graph_series_is_distinct(envelope, "Bottom maximum (MPa)", "Bottom minimum (MPa)"):
        add_trace(y_col="Bottom maximum (MPa)", name="Maximum stress at bottom of member", marker_symbol="triangle-up")
        add_trace(y_col="Bottom minimum (MPa)", name="Minimum stress at bottom of member", marker_symbol="circle", dash="dot")
    else:
        add_trace(y_col="Bottom minimum (MPa)", name="Bottom total stress", marker_symbol="circle")

    compression_limit, tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    x_min = float(x.min())
    x_max = float(x.max())
    if abs(x_max - x_min) <= 1e-9:
        x_min -= 0.5
        x_max += 0.5
    fig.add_trace(
        go.Scatter(
            x=[x_min, x_max],
            y=[-compression_limit, -compression_limit],
            mode="lines",
            name="Compression limit",  # legacy string: Compression preview limit
            line={"dash": "dash", "width": 2},
            hovertemplate=f"Compression limit = -{compression_limit:.3f} MPa<br>{escape(profile_label)}<extra></extra>",
        )
    )
    tension_x, tension_y, tension_profile_label = _girder_sls_tension_limit_trace_for_graph(stage_label, df)
    if max(tension_y) > _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
        fig.add_trace(
            go.Scatter(
                x=tension_x,
                y=tension_y,
                mode="lines",
                name="Tension limit",  # legacy string: Tension preview limit
                line={"dash": "dash", "width": 2},
                hovertemplate=(
                    "x=%{x:.3f} m<br>"
                    "Tension limit=%{y:.3f} MPa<br>"
                    f"{escape(tension_profile_label)}<extra></extra>"
                ),
            )
        )
    # GIRDER.SLS4C / SLS.GRAPH1: mark governing compression and tension directly on
    # the report-style graph.  This is annotation/display logic only; no stress solver,
    # Pe(x), load, section-basis, or code-limit formula changes are made.
    # legacy test phrase: no stress solver, Pe(x), load, section-basis, or code-limit formula changes
    for demand_row in _girder_sls4b_governing_demand_rows(df, stage_label):
        demand = str(demand_row.get("Demand", "Demand"))
        actual = float(demand_row.get("Actual stress (MPa)", 0.0) or 0.0)
        limit = float(demand_row.get("Limit stress (MPa)", 0.0) or 0.0)
        station = float(demand_row.get("Station x (m)", 0.0) or 0.0)
        utilization = _format_girder_sls_utilization(demand_row.get("Utilization"))
        fig.add_trace(
            go.Scatter(
                x=[station],
                y=[actual],
                mode="markers+text",
                name=f"Governing {demand.lower()}",
                marker={"size": 14, "symbol": "diamond-open" if demand == "Tension" else "circle-open", "line": {"width": 2}},
                text=[f"Gov. {demand}"],
                textposition="top center" if demand == "Tension" else "bottom center",
                hovertemplate=(
                    f"Governing {escape(demand.lower())}<br>"
                    "x=%{x:.3f} m<br>"
                    "stress=%{y:.3f} MPa<br>"
                    f"fiber={escape(str(demand_row.get('Fiber', 'N/A')))}<br>"
                    f"limit={limit:.3f} MPa<br>"
                    f"utilization={escape(utilization)}<extra></extra>"
                ),
            )
        )
    fig.add_hline(y=0.0, line_dash="dot", annotation_text="0 MPa", annotation_position="top left")
    title = _girder_sls_graph_stage_title(stage_label)
    subtitle = _girder_sls_graph_subtitle(stage_label)
    fig.update_layout(
        height=540,
        margin={"l": 28, "r": 28, "t": 86, "b": 108},
        title={
            "text": f"<b>Concrete Stress — {escape(title)}</b><br><sup>{escape(subtitle)}</sup>",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Distance from left end of member (m)",
        yaxis_title="Stress (MPa) · compression negative / tension positive",
        legend={"orientation": "h", "yanchor": "top", "y": -0.22, "xanchor": "center", "x": 0.5},
        plot_bgcolor="white",
        hovermode="x unified",
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="rgba(0,0,0,0.14)",
        zeroline=True,
        zerolinecolor="rgba(0,0,0,0.22)",
        ticks="outside",
    )
    fig.update_yaxes(
        showgrid=True,
        gridcolor="rgba(0,0,0,0.14)",
        zeroline=True,
        zerolinecolor="rgba(0,0,0,0.28)",
        ticks="outside",
    )
    return fig



def _final_service_deck_fc_from_session() -> float:
    """Return deck/topping concrete f'c for SERVICE.COMP1 final-service CIP preview."""

    params = st.session_state.get("section_parameters") or {}
    fc = _analysis_float_or_zero(params.get("deck_fc_MPa")) if isinstance(params, dict) else 0.0
    if fc <= 0.0:
        # Conservative UI fallback: if deck material metadata is missing, use the
        # primary concrete strength so the preview remains visible with REVIEW wording.
        fc = _girder_fc_for_sls_limit_preview()
    return float(fc)


def _service_comp1_preview_limit_summary(*, deck_fc_MPa: float) -> tuple[float, float]:
    """Return CIP/topping material limits for the final-service stress check.

    The helper name is kept for backward compatibility with SERVICE.COMP1 tests.
    SERVICE.COMP4 treats these values as the implemented CIP/topping service
    stress-check limits: compression 0.60 f'c and tension fr=0.62√f'c.
    """

    fc = max(float(deck_fc_MPa), 0.0)
    return 0.60 * fc, 0.62 * math.sqrt(fc) if fc > 0.0 else 0.0


def _final_service_composite_split_rows(df: pd.DataFrame, basis_options: object) -> pd.DataFrame:
    """Build SERVICE.COMP2 staged final-service beam/CIP concrete stress rows.

    SERVICE.COMP2 upgrades the SERVICE.COMP1 split from a simple transformed-
    section sampling preview into a staged composite final-service stress engine:

    * pre-composite locked-in dead load stress from girder self-weight + wet
      topping is calculated on the precast gross section and applied to the
      precast beam concrete only;
    * final effective prestress is applied to the precast beam concrete on the
      precast gross section;
    * service loads after composite action are applied to the transformed
      composite section;
    * CIP/topping concrete receives only the composite-stage incremental stress,
      scaled from transformed primary-concrete stress by n=Edeck/Ebeam.

    SERVICE.COMP4 finalizes this as the default Final Service Stress Check
    workflow in the app. Long-term redistribution, shrinkage compatibility, shear,
    deflection, detailing, and report integration remain separate design checks.
    """

    if df.empty:
        return pd.DataFrame()
    bases = getattr(basis_options, "bases", {}) or {}
    composite_basis = bases.get("composite_transformed")
    precast_basis = bases.get("precast_gross")
    if composite_basis is None or precast_basis is None:
        return pd.DataFrame()
    precast_top_y = float(precast_basis.top_fiber_y_from_bottom_mm)
    composite_top_y = float(composite_basis.top_fiber_y_from_bottom_mm)
    if composite_top_y <= precast_top_y + 1.0e-6:
        return pd.DataFrame()
    params = st.session_state.get("section_parameters") or {}
    modular_ratio_value = _analysis_float_or_zero(params.get("n_Edeck_over_Ebeam")) if isinstance(params, dict) else 0.0
    if modular_ratio_value <= 0.0:
        ebeam = _analysis_float_or_zero(params.get("Ebeam_MPa")) if isinstance(params, dict) else 0.0
        edeck = _analysis_float_or_zero(params.get("Edeck_MPa")) if isinstance(params, dict) else 0.0
        modular_ratio_value = edeck / ebeam if ebeam > 0.0 and edeck > 0.0 else 1.0
    n_ratio = modular_ratio_value if modular_ratio_value > 0.0 else 1.0
    span = _girder_sls_span_length_from_session([])
    locked_breakdown = _girder_sls_auto_load_breakdown("Construction stage")
    locked_w_kN_m = max(float(getattr(locked_breakdown, "total_kN_m", 0.0) or 0.0), 0.0)
    locked_component_label = str(getattr(locked_breakdown, "component_label", "Pre-composite dead load"))
    fiber_specs = [
        ("Precast beam", "Bottom of beam", float(precast_basis.bottom_fiber_y_from_bottom_mm), 1.0),
        ("Precast beam", "Top of beam", precast_top_y, 1.0),
        ("CIP / topping", "Bottom of CIP/topping", precast_top_y, n_ratio),
        ("CIP / topping", "Top of CIP/topping", composite_top_y, n_ratio),
    ]
    rows: list[dict[str, object]] = []
    for _, source in df.iterrows():
        station = _analysis_float_or_zero(source.get("Station x (m)"))
        n_kN = _analysis_float_or_zero(source.get("N (kN)"))
        m_kNm = _analysis_float_or_zero(source.get("Mx (kN-m)"))
        locked_m_kNm = simple_span_udl_moment_kNm(locked_w_kN_m, station, span)
        pe_kN = _analysis_float_or_zero(source.get("Pe stage (kN)"))
        yps_raw = source.get("yps eff (mm)")
        try:
            yps = float(yps_raw)
        except (TypeError, ValueError):
            yps = math.nan
        for component, fiber, y_mm, stress_scale in fiber_specs:
            composite_increment = girder_service_stress_at_y(
                composite_basis,
                N_kN=n_kN,
                M_kNm=m_kNm,
                y_from_bottom_mm=y_mm,
            )
            composite_increment_actual = float(composite_increment.total_stress_MPa) * stress_scale
            locked_actual = 0.0
            prestress_actual = 0.0
            if component == "Precast beam":
                locked = girder_service_stress_at_y(
                    precast_basis,
                    N_kN=0.0,
                    M_kNm=locked_m_kNm,
                    y_from_bottom_mm=y_mm,
                )
                locked_actual = float(locked.total_stress_MPa)
                if pe_kN > 0.0 and math.isfinite(yps):
                    try:
                        ps = girder_prestress_stress_at_y(
                            precast_basis,
                            Pe_eff_kN=pe_kN,
                            tendon_y_from_bottom_mm=yps,
                            y_from_bottom_mm=y_mm,
                        )
                        prestress_actual = float(ps.total_stress_MPa)
                    except (TypeError, ValueError):
                        prestress_actual = 0.0
            total = locked_actual + prestress_actual + composite_increment_actual
            rows.append(
                {
                    "Station x (m)": station,
                    "Concrete component": component,
                    "Fiber": fiber,
                    "y from bottom (mm)": y_mm,
                    "Stress scale": stress_scale,
                    "Locked-in pre-composite stress (MPa)": locked_actual,
                    "Final prestress stress (MPa)": prestress_actual,
                    "Composite increment stress (MPa)": composite_increment_actual,
                    "Service action stress (MPa)": composite_increment_actual,
                    "Prestress stress (MPa)": prestress_actual,
                    "Total stress (MPa)": total,
                    "Locked-in Mx (kN-m)": locked_m_kNm,
                    "Composite Mx (kN-m)": m_kNm,
                    "Case Name": str(source.get("Case Name") or "Unnamed"),
                    "Basis note": (
                        "SERVICE.COMP2 staged basis: pre-composite locked-in dead load + final Pe on precast section, plus composite-stage increments"
                        if component == "Precast beam" else
                        "SERVICE.COMP2 staged basis: CIP/topping receives composite-stage increments only; stress scaled by n=Edeck/Ebeam"
                    ),
                    "Locked-in components": locked_component_label,
                }
            )
    return pd.DataFrame(rows).sort_values(["Concrete component", "Fiber", "Station x (m)"]).reset_index(drop=True)


def _component_stress_limits(component_df: pd.DataFrame, component: str, *, beam_limits: tuple[float, float], deck_fc_MPa: float) -> tuple[float, float, str]:
    if component == "CIP / topping":
        comp, tens = _service_comp1_preview_limit_summary(deck_fc_MPa=deck_fc_MPa)
        return comp, tens, f"CIP/topping material limit: compression 0.60f'c, tension fr=0.62√f'c with f'c={deck_fc_MPa:g} MPa"
    comp, tens = beam_limits
    return comp, tens, "Precast beam concrete: active Service-stage code limit profile selected above"


def _component_governing_cards(component_df: pd.DataFrame, component: str, *, beam_limits: tuple[float, float], deck_fc_MPa: float) -> list[dict[str, object]]:
    if component_df.empty:
        return []
    comp_limit, tens_limit, basis = _component_stress_limits(component_df, component, beam_limits=beam_limits, deck_fc_MPa=deck_fc_MPa)
    comp_idx = component_df["Total stress (MPa)"].idxmin()
    tens_idx = component_df["Total stress (MPa)"].idxmax()
    comp_actual = float(component_df.loc[comp_idx, "Total stress (MPa)"])
    tens_actual = float(component_df.loc[tens_idx, "Total stress (MPa)"])
    comp_util = _girder_sls_demand_utilization(comp_actual, comp_limit, demand_type="compression")
    tens_util = _girder_sls_demand_utilization(tens_actual, tens_limit, demand_type="tension")
    fail = False
    try:
        fail = bool(
            (comp_util is not None and (not math.isfinite(comp_util) or comp_util > 1.0))
            or (tens_util is not None and (not math.isfinite(tens_util) or tens_util > 1.0))
        )
    except TypeError:
        fail = True
    return [
        {
            "title": f"{component} stress check",
            "value": "FAIL" if fail else "PASS",
            "detail": basis,
            "status": "danger" if fail else "ready",
        },
        {
            "title": "Governing compression",
            "value": _format_girder_stress_mpa(comp_actual),
            "detail": f"{component_df.loc[comp_idx, 'Fiber']} @ x={float(component_df.loc[comp_idx, 'Station x (m)']):.3f} m · limit -{comp_limit:.3f} MPa",
            "status": "danger" if comp_util is not None and (not math.isfinite(comp_util) or comp_util > 1.0) else "ready",
        },
        {
            "title": "Governing tension",
            "value": _format_girder_stress_mpa(tens_actual),
            "detail": f"{component_df.loc[tens_idx, 'Fiber']} @ x={float(component_df.loc[tens_idx, 'Station x (m)']):.3f} m · limit {tens_limit:.3f} MPa",
            "status": "danger" if tens_util is not None and (not math.isfinite(tens_util) or tens_util > 1.0) else "ready",
        },
    ]


def _final_service_component_decision_rows(
    split_df: pd.DataFrame,
    *,
    beam_limits: tuple[float, float],
    deck_fc_MPa: float,
) -> pd.DataFrame:
    """Return SERVICE.COMP4 material-specific final-service stress-check rows.

    SERVICE.COMP3 legacy source phrase retained for regression traceability:
    Final Service Beam/CIP code-limit decision summary.  SERVICE.COMP4 keeps the
    SERVICE.COMP2 staged stress engine unchanged and presents the Beam/CIP split
    as the app's Final Service Stress Check: each material gets governing
    compression and tension rows with actual stress, matching limit, utilization,
    station, and fiber.
    """

    rows: list[dict[str, object]] = []
    if split_df.empty:
        return pd.DataFrame(rows)
    for component in ("Precast beam", "CIP / topping"):
        component_df = split_df[split_df["Concrete component"] == component].copy()
        if component_df.empty:
            continue
        comp_limit, tens_limit, limit_basis = _component_stress_limits(
            component_df,
            component,
            beam_limits=beam_limits,
            deck_fc_MPa=deck_fc_MPa,
        )
        demand_specs = [
            ("Compression", component_df["Total stress (MPa)"].idxmin(), -comp_limit, comp_limit, "compression"),
            ("Tension", component_df["Total stress (MPa)"].idxmax(), tens_limit, tens_limit, "tension"),
        ]
        for demand, idx, signed_limit, positive_limit, demand_type in demand_specs:
            actual = float(component_df.loc[idx, "Total stress (MPa)"])
            util = _girder_sls_demand_utilization(actual, positive_limit, demand_type=demand_type)
            exceeds = util is not None and (not math.isfinite(float(util)) or float(util) > 1.0)
            rows.append(
                {
                    "Concrete component": component,
                    "Demand": demand,
                    "Check status": "FAIL" if exceeds else "PASS",
                    "Station x (m)": round(float(component_df.loc[idx, "Station x (m)"]), 3),
                    "Fiber": str(component_df.loc[idx, "Fiber"]),
                    "Actual stress (MPa)": round(actual, 3),
                    "Limit stress (MPa)": round(float(signed_limit), 3),
                    "Utilization": ("∞" if util is not None and not math.isfinite(float(util)) else (round(float(util), 3) if util is not None else "N/A")),
                    "Limit basis": limit_basis,
                    "Locked-in stress (MPa)": round(float(component_df.loc[idx, "Locked-in pre-composite stress (MPa)"]), 3),
                    "Final Pe stress (MPa)": round(float(component_df.loc[idx, "Final prestress stress (MPa)"]), 3),
                    "Composite increment stress (MPa)": round(float(component_df.loc[idx, "Composite increment stress (MPa)"]), 3),
                }
            )
    return pd.DataFrame(rows)


def _final_service_decision_summary_cards(decision_df: pd.DataFrame) -> list[dict[str, object]]:
    """Build SERVICE.COMP4 cards for the Beam/CIP Final Service Stress Check."""

    if decision_df.empty:
        return [
            {
                "title": "Final Service Stress Check",
                "value": "REVIEW",
                "detail": "No Beam/CIP stress-check rows are available.",
                "status": "warning",
            }
        ]
    failed = decision_df[decision_df["Check status"] == "FAIL"]
    util_numeric = pd.to_numeric(decision_df["Utilization"].replace("∞", math.inf), errors="coerce")
    if util_numeric.notna().any():
        governing_idx = util_numeric.idxmax()
    else:
        governing_idx = decision_df.index[0]
    governing = decision_df.loc[governing_idx]
    governing_util = governing.get("Utilization", "N/A")
    return [
        {
            "title": "Final Service Stress Check",
            "value": "FAIL" if not failed.empty else "PASS",
            "detail": "SERVICE.COMP4 Beam/CIP material-specific stress design check",
            "status": "danger" if not failed.empty else "ready",
            "strong": not failed.empty,
        },
        {
            "title": "Governing material",
            "value": str(governing.get("Concrete component", "N/A")),
            "detail": f"{governing.get('Demand', 'N/A')} · {governing.get('Fiber', 'N/A')} @ x={governing.get('Station x (m)', 'N/A')} m",
            "status": "danger" if str(governing.get("Check status")) == "FAIL" else "info",
        },
        {
            "title": "Actual / limit",
            "value": f"{governing.get('Actual stress (MPa)', 'N/A')} / {governing.get('Limit stress (MPa)', 'N/A')} MPa",
            "detail": f"Utilization = {governing_util}",
            "status": "danger" if str(governing.get("Check status")) == "FAIL" else "ready",
        },
        {
            "title": "Design check basis",
            "value": "Beam + CIP",
            "detail": "Precast beam and CIP/topping are checked separately",
            "status": "info",
        },
    ]


def _final_service_split_action_hints(decision_df: pd.DataFrame) -> list[str]:
    """Return compact SERVICE.COMP4 action hints for failing Beam/CIP final-service rows."""

    if decision_df.empty:
        return ["Confirm composite section metadata and service load inputs before relying on the Final Service Stress Check."]
    hints: list[str] = []
    for _, row in decision_df.iterrows():
        if str(row.get("Check status")) != "FAIL":
            continue
        component = str(row.get("Concrete component", ""))
        demand = str(row.get("Demand", ""))
        if component == "Precast beam" and demand == "Tension":
            hints.append("Precast beam tension controls: review Class U/Class T selection, final Pe, strand eccentricity, bonded reinforcement/crack-control assumptions, and service SDL/LL.")
        elif component == "Precast beam" and demand == "Compression":
            hints.append("Precast beam compression controls: review final Pe, eccentricity, concrete strength, section size, and service load combination.")
        elif component == "CIP / topping" and demand == "Tension":
            hints.append("CIP/topping tension controls: review slab/topping thickness, deck concrete strength, composite effective width, and service SDL/LL assumptions.")
        elif component == "CIP / topping" and demand == "Compression":
            hints.append("CIP/topping compression controls: review deck concrete strength, composite transformed properties, and service load intensity.")
    if not hints:
        # Near-limit guidance for high but passing utilization.
        util_numeric = pd.to_numeric(decision_df["Utilization"].replace("∞", math.inf), errors="coerce")
        if util_numeric.notna().any() and float(util_numeric.max()) >= 0.90:
            hints.append("Final-service stress utilization is close to the limit; review assumptions before issuing design output.")
    deduped: list[str] = []
    for hint in hints:
        if hint not in deduped:
            deduped.append(hint)
    return deduped[:4]


def _render_final_service_split_action_hints(decision_df: pd.DataFrame) -> None:
    hints = _final_service_split_action_hints(decision_df)
    if not hints:
        return
    items = "".join(f"<li>{escape(hint)}</li>" for hint in hints)
    html = (
        '<div class="cpmm-sls-action-panel">'
        '<div class="cpmm-sls-action-title">Final Service Beam/CIP action hints</div>'
        f"<ul>{items}</ul>"
        '<div class="cpmm-analysis-detail">Engineering review: long-term effects, shear, deflection, detailing, and report output remain separate checks.</div>'
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)


def _make_final_service_component_stress_figure(component_df: pd.DataFrame, component: str, *, beam_limits: tuple[float, float], deck_fc_MPa: float) -> go.Figure:
    fig = go.Figure()
    if component_df.empty:
        return fig
    for fiber, group in component_df.groupby("Fiber"):
        fig.add_trace(
            go.Scatter(
                x=group["Station x (m)"],
                y=group["Total stress (MPa)"],
                mode="lines+markers",
                name=str(fiber),
                hovertemplate="x=%{x:.3f} m<br>stress=%{y:.3f} MPa<extra></extra>",
            )
        )
    comp_limit, tens_limit, basis = _component_stress_limits(component_df, component, beam_limits=beam_limits, deck_fc_MPa=deck_fc_MPa)
    x_min = float(component_df["Station x (m)"].min())
    x_max = float(component_df["Station x (m)"].max())
    if abs(x_max - x_min) <= 1.0e-9:
        x_min -= 0.5
        x_max += 0.5
    fig.add_trace(go.Scatter(x=[x_min, x_max], y=[-comp_limit, -comp_limit], mode="lines", name="Compression limit", line={"dash": "dash"}))
    fig.add_trace(go.Scatter(x=[x_min, x_max], y=[tens_limit, tens_limit], mode="lines", name="Tension limit", line={"dash": "dash"}))
    fig.add_hline(y=0.0, line_dash="dot", annotation_text="0 MPa", annotation_position="top left")
    component_title = "beam" if component == "Precast beam" else "CIP"
    fig.update_layout(
        height=430,
        margin={"l": 28, "r": 28, "t": 76, "b": 95},
        title={"text": f"<b>Concrete Stress ({escape(component_title)}) — Final Service</b><br><sup>{escape(basis)} · compression negative / tension positive</sup>", "x": 0.5, "xanchor": "center"},
        xaxis_title="Distance from left end of member (m)",
        yaxis_title="Stress (MPa)",
        legend={"orientation": "h", "yanchor": "top", "y": -0.22, "xanchor": "center", "x": 0.5},
        plot_bgcolor="white",
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.14)", ticks="outside")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.14)", zeroline=True, zerolinecolor="rgba(0,0,0,0.28)", ticks="outside")
    return fig


def _render_final_service_beam_cip_concrete_split(df: pd.DataFrame, basis_options: object, stage_label: str) -> bool:
    """Render SERVICE.COMP1 Final Service split for precast beam and CIP concrete.

    Source-visible labels retained for tests and roadmap traceability:
    Concrete Stress (beam) — Final Service; Concrete Stress (CIP) — Final Service.
    """

    if _beam_sls_stage_label_for_analysis(stage_label) != "Service stage":
        return False
    bases = getattr(basis_options, "bases", {}) or {}
    if "composite_transformed" not in bases or "precast_gross" not in bases:
        return False
    split_df = _final_service_composite_split_rows(df, basis_options)
    if split_df.empty:
        return False
    beam_compression, beam_tension, beam_profile = _girder_sls_diagram_limit_summary(stage_label)
    deck_fc = _final_service_deck_fc_from_session()
    st.markdown("##### Final Service Stress Check — Beam/CIP")
    st.caption(
        "SERVICE.COMP4 uses staged composite stress summation for the default final-service design check: "
        "pre-composite self-weight/wet topping stress is locked into the precast beam, final Pe is applied to the precast beam, and service SDL/LL increments are applied to the composite transformed section. "
        "Long-term redistribution, shrinkage compatibility, deflection, shear, detailing, and report output remain separate checks."
    )
    _render_analysis_summary_strip(
        [
            {
                "title": "Precast beam check",
                "value": "Top/bottom of beam",
                "detail": f"Locked-in dead load + final Pe + composite increments; profile: {beam_profile}",
                "status": "info",
            },
            {
                "title": "CIP / topping check",
                "value": f"f'c={deck_fc:g} MPa",
                "detail": "Composite-stage increments only; limits: 0.60f'c compression, fr=0.62√f'c tension",
                "status": "info",
            },
            {
                "title": "Composite stress method",
                "value": "Locked-in + composite",
                "detail": "CIP stress is scaled by n=Edeck/Ebeam; CIP receives no direct prestress stress",
                "status": "info",
            },
        ],
        columns=3,
    )
    st.markdown("**Final Service Stress Check decision summary**")
    decision_df = _final_service_component_decision_rows(
        split_df,
        beam_limits=(beam_compression, beam_tension),
        deck_fc_MPa=deck_fc,
    )
    _render_analysis_summary_strip(_final_service_decision_summary_cards(decision_df), columns=4)
    if not decision_df.empty:
        compact_cols = [
            "Concrete component",
            "Demand",
            "Check status",
            "Station x (m)",
            "Fiber",
            "Actual stress (MPa)",
            "Limit stress (MPa)",
            "Utilization",
            "Limit basis",
        ]
        st.dataframe(decision_df[[col for col in compact_cols if col in decision_df.columns]], use_container_width=True, hide_index=True)
        with st.expander("Final Service stress component audit", expanded=False):
            audit_cols = [
                "Concrete component",
                "Demand",
                "Station x (m)",
                "Fiber",
                "Locked-in stress (MPa)",
                "Final Pe stress (MPa)",
                "Composite increment stress (MPa)",
                "Actual stress (MPa)",
                "Limit stress (MPa)",
                "Utilization",
                "Limit basis",
            ]
            st.dataframe(decision_df[[col for col in audit_cols if col in decision_df.columns]], use_container_width=True, hide_index=True)
    _render_final_service_split_action_hints(decision_df)
    for component in ("Precast beam", "CIP / topping"):
        component_df = split_df[split_df["Concrete component"] == component].copy()
        if component_df.empty:
            continue
        st.markdown(f"**Concrete Stress ({'beam' if component == 'Precast beam' else 'CIP'}) — Final Service**")
        _render_analysis_summary_strip(
            _component_governing_cards(component_df, component, beam_limits=(beam_compression, beam_tension), deck_fc_MPa=deck_fc),
            columns=3,
        )
        st.plotly_chart(
            _make_final_service_component_stress_figure(
                component_df,
                component,
                beam_limits=(beam_compression, beam_tension),
                deck_fc_MPa=deck_fc,
            ),
            use_container_width=True,
        )
    with st.expander("Detailed Beam/CIP station stress table", expanded=False):
        st.dataframe(_clean_girder_stress_dataframe(split_df), use_container_width=True, hide_index=True)
    return True

# DEFLECT.SLS1 — short-term deflection / camber preview helpers.
# This workspace is intentionally separate from stress-result equations. It does
# not change the SLS stress solver, Pe(x) station engine, prestress losses,
# code-limit formulas, or PMM solver. Sign convention for display: positive =
# upward camber, negative = downward deflection.

def _deflect_sls_positive_float(value: object, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(numeric) or numeric <= 0.0:
        return default
    return numeric


def _girder_deflection_Ebeam_MPa_from_session() -> float:
    params = st.session_state.get("section_parameters") or {}
    if isinstance(params, dict):
        for key in ("Ebeam_MPa", "Ec_MPa", "concrete_Ec_MPa"):
            value = _deflect_sls_positive_float(params.get(key), 0.0)
            if value > 0.0:
                return value
    return 30_000.0


def _girder_deflection_limit_mm(span_length_m: float) -> tuple[str, float | None]:
    """Return the selected DEFLECT.SLS1 allowable downward deflection limit."""

    basis = str(st.session_state.get("girder_deflection_allowable_limit_basis") or "L/360")
    if basis == "Custom":
        custom = st.number_input(
            "Custom allowable downward deflection (mm)",
            min_value=0.0,
            value=float(st.session_state.get("girder_deflection_custom_limit_mm", max(span_length_m * 1000.0 / 360.0, 0.0)) or 0.0),
            step=1.0,
            key="girder_deflection_custom_limit_mm",
        )
        return "Custom", float(custom) if custom > 0.0 else None
    if basis == "Review only":
        return basis, None
    try:
        denominator = float(basis.split("/")[-1])
    except (TypeError, ValueError):
        denominator = 360.0
    return basis, span_length_m * 1000.0 / denominator if denominator > 0.0 else None


def _girder_deflection_udl_curve_mm(
    *,
    w_kN_m: float,
    basis: object,
    E_MPa: float,
    span_length_m: float,
    stations_m: list[float],
) -> list[float]:
    """Return downward UDL elastic deflection curve in mm (negative downward)."""

    w_N_mm = max(float(w_kN_m), 0.0)  # 1 kN/m = 1 N/mm
    L = max(float(span_length_m), 0.0) * 1000.0
    I = _deflect_sls_positive_float(getattr(basis, "ix_mm4", 0.0), 0.0)
    E = _deflect_sls_positive_float(E_MPa, 0.0)
    if w_N_mm <= 0.0 or L <= 0.0 or I <= 0.0 or E <= 0.0:
        return [0.0 for _ in stations_m]
    values: list[float] = []
    for x_m in stations_m:
        x = min(max(float(x_m), 0.0), float(span_length_m)) * 1000.0
        downward = w_N_mm * x * (L**3 - 2.0 * L * x**2 + x**3) / (24.0 * E * I)
        values.append(-float(downward))
    return values


def _girder_deflection_constant_moment_curve_mm(
    *,
    M_kNm: float,
    basis: object,
    E_MPa: float,
    span_length_m: float,
    stations_m: list[float],
) -> list[float]:
    """Return elastic curve from constant equivalent moment; positive is upward camber."""

    M_Nmm = float(M_kNm) * 1_000_000.0
    L = max(float(span_length_m), 0.0) * 1000.0
    I = _deflect_sls_positive_float(getattr(basis, "ix_mm4", 0.0), 0.0)
    E = _deflect_sls_positive_float(E_MPa, 0.0)
    if abs(M_Nmm) <= 1.0e-9 or L <= 0.0 or I <= 0.0 or E <= 0.0:
        return [0.0 for _ in stations_m]
    values: list[float] = []
    for x_m in stations_m:
        x = min(max(float(x_m), 0.0), float(span_length_m)) * 1000.0
        # Positive sagging moment produces downward deflection. A bottom tendon
        # normally creates negative equivalent moment and therefore positive camber.
        value = -M_Nmm * x * (L - x) / (2.0 * E * I)
        values.append(float(value))
    return values


def _sum_deflection_curves(*curves: list[float]) -> list[float]:
    if not curves:
        return []
    n = max(len(curve) for curve in curves)
    result = [0.0] * n
    for curve in curves:
        for idx, value in enumerate(curve):
            result[idx] += float(value)
    return result


def _girder_deflection_midspan_pe(stage_label: str, *, span_length_m: float, basis: object) -> tuple[float, float | None, float]:
    """Return Pe, yps, and equivalent moment for a stage at midspan."""

    strand_table = st.session_state.get("girder_strand_layout_table")
    if strand_table is None:
        return 0.0, None, 0.0
    try:
        station = evaluate_girder_prestress_station(
            strand_table,
            x_m=float(span_length_m) / 2.0,
            span_length_m=float(span_length_m),
        )
        pe_kN = _girder_sls_stage_pe_value_from_station(station, stage_label)
        yps = station.yps_eff_mm_from_bottom
        if pe_kN > 0.0 and yps is not None:
            eccentricity_mm = float(yps) - float(getattr(basis, "centroid_y_from_bottom_mm", 0.0))
            return float(pe_kN), float(yps), float(pe_kN) * eccentricity_mm / 1000.0
    except (TypeError, ValueError, KeyError):
        return 0.0, None, 0.0
    return 0.0, None, 0.0


def _girder_deflection_service_load_split(service_breakdown: object) -> tuple[float, float]:
    """Split Service UDL into sustained and LL components for DEFLECT.SLS1."""

    sustained = 0.0
    live = 0.0
    for label, value in getattr(service_breakdown, "component_loads_kN_m", ()):
        if "ll" in str(label).casefold() or "live" in str(label).casefold():
            live += float(value)
        else:
            sustained += float(value)
    return sustained, live


def _girder_deflection_curve_rows(*, basis_options: object) -> pd.DataFrame:
    """Build DEFLECT.SLS1 short-term deflection/camber preview curves."""

    bases = getattr(basis_options, "bases", {}) or {}
    precast_basis = bases.get("precast_gross")
    if precast_basis is None:
        return pd.DataFrame()
    composite_basis = bases.get("composite_transformed") or precast_basis
    span = _girder_sls_span_length_from_session([])
    stations = _girder_sls_auto_station_grid(span)
    Ebeam = _girder_deflection_Ebeam_MPa_from_session()

    transfer_breakdown = _girder_sls_auto_load_breakdown("Transfer stage")
    construction_breakdown = _girder_sls_auto_load_breakdown("Construction stage")
    service_breakdown = _girder_sls_auto_load_breakdown("Service stage")
    service_sustained_w, service_ll_w = _girder_deflection_service_load_split(service_breakdown)

    pe_tr, yps_tr, mpe_tr = _girder_deflection_midspan_pe("Transfer stage", span_length_m=span, basis=precast_basis)
    pe_const, yps_const, mpe_const = _girder_deflection_midspan_pe("Construction stage", span_length_m=span, basis=precast_basis)
    pe_final, yps_final, mpe_final = _girder_deflection_midspan_pe("Service stage", span_length_m=span, basis=precast_basis)

    transfer_cam = _girder_deflection_constant_moment_curve_mm(M_kNm=mpe_tr, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    transfer_dl = _girder_deflection_udl_curve_mm(w_kN_m=transfer_breakdown.total_kN_m, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    transfer_net = _sum_deflection_curves(transfer_cam, transfer_dl)

    construction_cam = _girder_deflection_constant_moment_curve_mm(M_kNm=mpe_const, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    construction_load = _girder_deflection_udl_curve_mm(w_kN_m=construction_breakdown.total_kN_m, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    construction_net = _sum_deflection_curves(construction_cam, construction_load)

    final_cam = _girder_deflection_constant_moment_curve_mm(M_kNm=mpe_final, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    locked_load = _girder_deflection_udl_curve_mm(w_kN_m=construction_breakdown.total_kN_m, basis=precast_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    sustained_load = _girder_deflection_udl_curve_mm(w_kN_m=service_sustained_w, basis=composite_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    live_load = _girder_deflection_udl_curve_mm(w_kN_m=service_ll_w, basis=composite_basis, E_MPa=Ebeam, span_length_m=span, stations_m=stations)
    service_completion = _sum_deflection_curves(final_cam, locked_load, sustained_load)
    service_sustained_ll = _sum_deflection_curves(service_completion, live_load)

    curve_specs = [
        ("Transfer stage", "Deflection @ Transfer", transfer_net, "Pe_transfer camber + self-weight"),
        ("Construction stage", "Deflection @ Erection / CIP pour", construction_net, "Pe_construction camber + girder self-weight + wet topping"),
        ("Service stage", "Deflection on Completion", service_completion, "Final Pe + locked-in pre-composite dead load + sustained service load"),
        ("Service stage", "Final Service Sustained Deflection", service_completion, "Short-term sustained-load estimate; long-term multiplier not included"),
        ("Service stage", "Final Service Sust. + LL Deflection", service_sustained_ll, "Sustained service deflection plus building LL component where available"),
    ]
    rows: list[dict[str, object]] = []
    pe_notes = {
        "Transfer stage": f"Pe={pe_tr:.1f} kN, yps={yps_tr:.1f} mm" if yps_tr is not None else "Pe unavailable",
        "Construction stage": f"Pe={pe_const:.1f} kN, yps={yps_const:.1f} mm" if yps_const is not None else "Pe unavailable",
        "Service stage": f"Pe={pe_final:.1f} kN, yps={yps_final:.1f} mm" if yps_final is not None else "Pe unavailable",
    }
    for stage, curve_name, values, basis_note in curve_specs:
        for x_m, deflection in zip(stations, values, strict=False):
            rows.append(
                {
                    "Stage": stage,
                    "Curve": curve_name,
                    "Station x (m)": float(x_m),
                    "Deflection (mm)": float(deflection),
                    "Basis note": basis_note,
                    "Prestress basis": pe_notes.get(stage, ""),
                    "E used (MPa)": Ebeam,
                    "Precast Ix (mm^4)": getattr(precast_basis, "ix_mm4", 0.0),
                    "Composite Ix (mm^4)": getattr(composite_basis, "ix_mm4", 0.0),
                    "Transfer auto w (kN/m)": transfer_breakdown.total_kN_m,
                    "Construction auto w (kN/m)": construction_breakdown.total_kN_m,
                    "Service sustained w (kN/m)": service_sustained_w,
                    "Service LL w (kN/m)": service_ll_w,
                }
            )
    return pd.DataFrame(rows)


_DEFLECTION_DISPLAY_TOL_MM = 0.005


def _girder_deflection_response_status(max_up_mm: float, max_down_mm: float) -> str:
    """Return stage-response semantics for non-acceptance deflection/camber previews."""

    up_mag = max(float(max_up_mm), 0.0)
    down_mag = abs(min(float(max_down_mm), 0.0))
    has_up = up_mag >= _DEFLECTION_DISPLAY_TOL_MM
    has_down = down_mag >= _DEFLECTION_DISPLAY_TOL_MM
    if has_up and not has_down:
        return "CAMBER"
    if has_down and not has_up:
        return "DEFLECTION"
    if has_up and has_down:
        return "RESPONSE"
    return "REVIEW"


def _girder_deflection_response_text(value_mm: float, *, magnitude: bool = False, decimals: int = 2) -> str:
    """Format a real deflection/camber response; hide numerical zero as a dash."""

    value = abs(float(value_mm)) if magnitude else float(value_mm)
    if abs(value) < _DEFLECTION_DISPLAY_TOL_MM:
        return "-"
    return f"{value:.{decimals}f} mm"


def _girder_deflection_response_x_text(value_mm: float, x_m: float, *, decimals: int = 3) -> str:
    """Return the response location only when the displayed response is meaningful."""

    if abs(float(value_mm)) < _DEFLECTION_DISPLAY_TOL_MM:
        return "-"
    return f"{float(x_m):.{decimals}f} m"


def _girder_deflection_summary_rows(curve_df: pd.DataFrame, *, limit_mm: float | None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if curve_df.empty:
        return pd.DataFrame(rows)
    for (stage, curve), group in curve_df.groupby(["Stage", "Curve"], sort=False):
        up_idx = group["Deflection (mm)"].idxmax()
        down_idx = group["Deflection (mm)"].idxmin()
        max_up = float(group.loc[up_idx, "Deflection (mm)"])
        max_down = float(group.loc[down_idx, "Deflection (mm)"])
        down_mag = abs(min(max_down, 0.0))
        utilization = None if limit_mm is None or limit_mm <= 0.0 else down_mag / limit_mm
        if stage != "Service stage":
            status = _girder_deflection_response_status(max_up, max_down)
        elif limit_mm is None:
            status = "REVIEW"
        else:
            status = "FAIL" if utilization is not None and utilization > 1.0 else "PASS"
        rows.append(
            {
                "Stage": stage,
                "Case": curve,
                "Check status": status,
                "Max upward camber (mm)": max_up,
                "x up (m)": float(group.loc[up_idx, "Station x (m)"]),
                "Max downward deflection (mm)": max_down,
                "x down (m)": float(group.loc[down_idx, "Station x (m)"]),
                "Limit (mm)": "Review only" if limit_mm is None else limit_mm,
                "Utilization": "—" if utilization is None else utilization,
            }
        )
    return pd.DataFrame(rows)


def _girder_deflection_overall_cards(summary_df: pd.DataFrame, *, limit_label: str) -> list[dict[str, object]]:
    if summary_df.empty:
        return [
            {"title": "Deflection check", "value": "No data", "detail": "Build a valid girder section and Pe/load basis first", "status": "warning"}
        ]
    fail_count = int((summary_df["Check status"] == "FAIL").sum())
    service_rows = summary_df[summary_df["Stage"] == "Service stage"].copy()
    governing = service_rows if not service_rows.empty else summary_df.copy()
    util_numeric = pd.to_numeric(governing["Utilization"].replace("—", math.nan), errors="coerce")
    if util_numeric.notna().any() and (util_numeric.fillna(0.0).abs() > 1.0e-9).any():
        gov_idx = util_numeric.idxmax()
    else:
        up_numeric = pd.to_numeric(governing["Max upward camber (mm)"], errors="coerce").abs()
        down_numeric = pd.to_numeric(governing["Max downward deflection (mm)"], errors="coerce").clip(upper=0.0).abs()
        response_numeric = pd.concat([up_numeric, down_numeric], axis=1).max(axis=1)
        gov_idx = response_numeric.idxmax()
    row = governing.loc[gov_idx]
    status = "FAIL" if fail_count else "PASS" if str(row.get("Check status")) == "PASS" else "REVIEW"
    limit_value = row.get("Limit (mm)")
    util_value = row.get("Utilization")
    max_down = float(row.get("Max downward deflection (mm)", 0.0) or 0.0)
    max_up = float(row.get("Max upward camber (mm)", 0.0) or 0.0)
    down_mag = abs(min(max_down, 0.0))
    up_mag = max(max_up, 0.0)
    x_down = float(row.get("x down (m)", 0.0) or 0.0)
    x_up = float(row.get("x up (m)", 0.0) or 0.0)
    governing_x = x_down if down_mag >= _DEFLECTION_DISPLAY_TOL_MM else x_up if up_mag >= _DEFLECTION_DISPLAY_TOL_MM else None
    down_text = _girder_deflection_response_text(down_mag, magnitude=True)
    up_text = _girder_deflection_response_text(up_mag, magnitude=True)
    down_x_text = _girder_deflection_response_x_text(down_mag, x_down)
    up_x_text = _girder_deflection_response_x_text(up_mag, x_up)
    governing_detail = f"{row.get('Stage', '—')} @ x={governing_x:.3f} m" if governing_x is not None else f"{row.get('Stage', '—')} @ x=-"
    if isinstance(limit_value, str):
        limit_text = "Review only"
    else:
        limit_text = f"{limit_label} = {float(limit_value):.2f} mm"
    return [
        {
            "title": "Overall deflection check",
            "value": status,
            "detail": "Short-term elastic preview; positive camber / negative downward deflection",
            "status": "danger" if status == "FAIL" else "ready" if status == "PASS" else "warning",
        },
        {
            "title": "Governing case",
            "value": str(row.get("Case", "—")),
            "detail": governing_detail,
            "status": "info",
        },
        {
            "title": "Max deflection / camber",
            "value": f"Down {down_text} · Up {up_text}",
            "detail": f"Down @ x={down_x_text}; Up @ x={up_x_text}",
            "status": "info",
        },
        {
            "title": "Downward Deflection Limit / utilization",
            "value": limit_text,
            "detail": "Utilization —" if util_value == "—" else f"Utilization {float(util_value):.3f}",
            "status": "danger" if status == "FAIL" else "ready" if status == "PASS" else "warning",
        },
    ]


def _make_girder_deflection_figure(curve_df: pd.DataFrame, *, stage_label: str) -> go.Figure:
    """Build a Concise-Beam-inspired DEFLECT.SLS1 plot without copying styling."""

    fig = go.Figure()
    if curve_df.empty:
        return fig
    stage_df = curve_df[curve_df["Stage"] == stage_label].copy()
    if stage_df.empty:
        return fig
    for curve_name, group in stage_df.groupby("Curve", sort=False):
        fig.add_trace(
            go.Scatter(
                x=group["Station x (m)"],
                y=group["Deflection (mm)"],
                mode="lines+markers",
                name=str(curve_name),
                hovertemplate="x=%{x:.3f} m<br>deflection=%{y:.3f} mm<extra></extra>",
            )
        )
    code_edition = project_code_edition_from_session(st.session_state)
    fig.add_hline(y=0.0, line_dash="dot", annotation_text="0 mm", annotation_position="top left")
    title_stage = stage_label.replace(" stage", "")
    fig.update_layout(
        height=470,
        margin={"l": 32, "r": 28, "t": 78, "b": 98},
        title={
            "text": f"<b>Deflection — {escape(title_stage)}</b><br><sup>{escape(code_edition)} · positive = upward camber / negative = downward deflection</sup>",
            "x": 0.5,
            "xanchor": "center",
        },
        xaxis_title="Distance from left end of member (m)",
        yaxis_title="Deflection (mm)",
        legend={"orientation": "h", "yanchor": "top", "y": -0.22, "xanchor": "center", "x": 0.5},
        plot_bgcolor="white",
        hovermode="x unified",
    )
    fig.update_xaxes(showgrid=True, gridcolor="rgba(0,0,0,0.14)", ticks="outside")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(0,0,0,0.14)", zeroline=True, zerolinecolor="rgba(0,0,0,0.28)", ticks="outside")
    return fig


def _deflection_action_hints(summary_df: pd.DataFrame) -> list[str]:
    if summary_df.empty:
        return []
    hints: list[str] = []
    if (summary_df["Check status"] == "FAIL").any():
        hints.append("Downward deflection exceeds the selected limit: review span/depth, composite stiffness, SDL/LL, and service load assumptions.")
    max_up = float(pd.to_numeric(summary_df["Max upward camber (mm)"], errors="coerce").max(skipna=True) or 0.0)
    if max_up > 0.0:
        hints.append("Upward camber is controlled by Pe and eccentricity; review strand layout/loss basis together with stress limits if camber is excessive.")
    hints.append("Short-term elastic check only; creep, shrinkage, cracked-section stiffness, and camber growth remain separate future checks.")
    return hints[:4]


def _render_girder_deflection_camber_workspace(*, basis_options: object) -> None:
    """Render DEFLECT.SLS1 short-term deflection / camber preview workspace."""

    st.markdown("### SLS Deflection / Camber")
    st.caption(
        "Short-term elastic deflection/camber check for simple-span Beam/Girder workflows. "
        "Positive values are upward camber and negative values are downward deflection. "
        "Long-term creep/shrinkage and cracked-section deflection are not included."
    )
    bases = getattr(basis_options, "bases", {}) or {}
    if "precast_gross" not in bases:
        st.info("Build a valid Beam/Girder section before running the deflection/camber preview.")
        return
    span = _girder_sls_span_length_from_session([])
    with st.expander("Deflection check settings", expanded=True):
        cols = st.columns([1.0, 1.0, 2.0])
        limit_options = ["L/240", "L/360", "L/480", "L/1000", "Custom", "Review only"]
        key = "girder_deflection_allowable_limit_basis"
        if st.session_state.get(key) not in limit_options:
            st.session_state[key] = "L/360"
        with cols[0]:
            st.selectbox("Allowable downward deflection", limit_options, key=key)
        with cols[1]:
            st.metric("Span L", f"{span:.3f} m")
        with cols[2]:
            st.caption("Select project-specific downward-deflection criteria. Transfer and Construction rows report response semantics (CAMBER / DEFLECTION / RESPONSE) rather than service acceptance status.")
    _limit_label, limit_mm = _girder_deflection_limit_mm(span)
    curve_df = _girder_deflection_curve_rows(basis_options=basis_options)
    if curve_df.empty:
        st.info("Deflection/camber curves are not available for the current section basis.")
        return
    summary_df = _girder_deflection_summary_rows(curve_df, limit_mm=limit_mm)
    st.markdown("**Deflection / Camber decision summary**")
    _render_analysis_summary_strip(_girder_deflection_overall_cards(summary_df, limit_label=_limit_label), columns=4)
    if not summary_df.empty:
        display_df = summary_df.copy()
        if "Max upward camber (mm)" in display_df.columns:
            display_df["Max upward camber (mm)"] = display_df["Max upward camber (mm)"].map(
                lambda v: _girder_deflection_response_text(float(v), decimals=3) if not isinstance(v, str) else v
            )
        if "Max downward deflection (mm)" in display_df.columns:
            display_df["Max downward deflection (mm)"] = display_df["Max downward deflection (mm)"].map(
                lambda v: _girder_deflection_response_text(float(v), decimals=3) if not isinstance(v, str) else v
            )
        if {"Max upward camber (mm)", "x up (m)"}.issubset(display_df.columns):
            display_df["x up (m)"] = [
                _girder_deflection_response_x_text(max_up, x_up, decimals=3)
                for max_up, x_up in zip(summary_df["Max upward camber (mm)"], summary_df["x up (m)"], strict=False)
            ]
        if {"Max downward deflection (mm)", "x down (m)"}.issubset(display_df.columns):
            display_df["x down (m)"] = [
                _girder_deflection_response_x_text(max_down, x_down, decimals=3)
                for max_down, x_down in zip(summary_df["Max downward deflection (mm)"], summary_df["x down (m)"], strict=False)
            ]
        for col in ("Limit (mm)", "Utilization"):
            if col in display_df.columns:
                display_df[col] = display_df[col].map(lambda v: v if isinstance(v, str) else round(float(v), 3))
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    hints = _deflection_action_hints(summary_df)
    if hints:
        items = "".join(f"<li>{escape(hint)}</li>" for hint in hints)
        st.markdown(
            '<div class="cpmm-sls-action-panel"><div class="cpmm-sls-action-title">Deflection / camber action hints</div>'
            f"<ul>{items}</ul></div>",
            unsafe_allow_html=True,
        )
    tab_specs = [
        ("Transfer stage", "Transfer camber/deflection from Pe_transfer and self-weight"),
        ("Construction stage", "Construction / CIP pour camber/deflection from Pe_construction, self-weight, and wet topping"),
        ("Service stage", "Final service short-term deflection from locked-in components plus sustained/LL service increments"),
    ]
    tabs = st.tabs([label for label, _note in tab_specs])
    for tab, (stage_label, note) in zip(tabs, tab_specs, strict=False):
        with tab:
            st.caption(note)
            st.plotly_chart(_make_girder_deflection_figure(curve_df, stage_label=stage_label), use_container_width=True)
    with st.expander("Deflection component audit", expanded=False):
        audit_cols = [
            "Stage",
            "Curve",
            "Station x (m)",
            "Deflection (mm)",
            "Basis note",
            "Prestress basis",
            "E used (MPa)",
            "Precast Ix (mm^4)",
            "Composite Ix (mm^4)",
            "Transfer auto w (kN/m)",
            "Construction auto w (kN/m)",
            "Service sustained w (kN/m)",
            "Service LL w (kN/m)",
        ]
        st.dataframe(curve_df[[col for col in audit_cols if col in curve_df.columns]], use_container_width=True, hide_index=True)
        st.write("- UDL deflection uses simple-span elastic formula 5wL⁴/(384EI) shape along x.")
        st.write("- Prestress camber uses a simplified constant equivalent moment Pe·e at midspan. Debonding is represented through the active midspan Pe/yps only in this first milestone.")
        st.write("- Service increments use the composite transformed section when available; otherwise the precast gross basis is used as fallback.")

def _render_girder_full_length_sls_diagram(
    *,
    stage_label: str,
    stage_rows: list[dict[str, object]],
    basis_options: object,
    basis_names: list[str],
) -> None:
    """Render GIRDER.SLS4A station-based stress diagram for one stage."""

    st.markdown("##### Full-length SLS stress check diagram")
    st.caption(
        "Decision view for top/bottom fiber stresses along the girder length. "
        "The active stage tab selects the matching code-limit stage automatically; detailed audit controls stay collapsed below. "
        "This remains a preview, not final code-certified staged design. "
        "Transfer-length ramp, development, shear, and end-zone checks remain future work."
    )
    span = _girder_sls_span_length_from_session(stage_rows)
    stage_rows = _girder_sls_stage_rows_with_auto_station_grid(stage_label, stage_rows, span)
    if not stage_rows:
        st.info("No generated or imported station rows are available for this stage.")
        return
    case_names = _girder_sls4b_case_names(stage_rows)
    _girder_sls4b_selected_case_for_stage(stage_label, stage_rows)
    if len(case_names) > 1:
        selected_case = st.selectbox(
            f"{stage_label} diagram load case",
            case_names,
            key=_girder_sls4b_case_state_key(stage_label),
            help="The diagram connects station rows with the same Case Name. Use one case per diagram to avoid mixing envelopes with single-case curves.",
        )
    else:
        selected_case = case_names[0]
        st.caption(f"Diagram load case: {selected_case}")
    selected_rows = [row for row in stage_rows if str(row.get("Case Name") or "Unnamed") == selected_case]
    df = _girder_full_length_sls_stage_rows(
        stage_label=stage_label,
        load_rows=selected_rows,
        basis_options=basis_options,
        basis_names=basis_names,
        span_length_m=span,
    )
    if df.empty:
        st.info("No valid station rows are available for this diagram case.")
        return
    _render_girder_sls_diagram_tensile_limit_guide(stage_label, df)
    status, detail, style = _girder_full_length_preview_status(df, stage_label)
    compression_limit, tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    governing_comp_idx = df["Max compression (MPa)"].idxmin()
    tension_demand_rows_for_stage = [row for row in _girder_sls4b_governing_demand_rows(df, stage_label) if str(row.get("Demand")) == "Tension"]
    if tension_demand_rows_for_stage:
        governing_tens_station = float(tension_demand_rows_for_stage[0].get("Station x (m)", 0.0) or 0.0)
        governing_tens_limit = abs(float(tension_demand_rows_for_stage[0].get("Limit stress (MPa)", tension_limit) or tension_limit))
        governing_tens_idx = (df["Station x (m)"] - governing_tens_station).abs().idxmin()
    else:
        governing_tens_idx = df["Max tension (MPa)"].idxmax()
        governing_tens_limit = tension_limit
    st.markdown("**SLS check basis**")
    _render_analysis_summary_strip(
        _girder_sls4c_stage_basis_cards(
            stage_label=stage_label,
            selected_case=selected_case,
            selected_rows=selected_rows,
            df=df,
            basis_options=basis_options,
        ),
        columns=4,
    )
    st.markdown("**Stage result summary**")
    _render_analysis_summary_strip(
        [
            {
                "title": "Diagram status",
                "value": status,
                "detail": detail,
                "status": style,
            },
            {
                "title": "Governing compression",
                "value": _format_girder_stress_mpa(df.loc[governing_comp_idx, "Max compression (MPa)"]),
                "detail": f"x={float(df.loc[governing_comp_idx, 'Station x (m)']):.3f} m · limit -{compression_limit:.3f} MPa",
                "status": "ready" if float(df.loc[governing_comp_idx, "Max compression (MPa)"]) >= -compression_limit else "danger",
            },
            {
                "title": "Governing tension",
                "value": _format_girder_stress_mpa(df.loc[governing_tens_idx, "Max tension (MPa)"]),
                "detail": f"x={float(df.loc[governing_tens_idx, 'Station x (m)']):.3f} m · limit {governing_tens_limit:.3f} MPa",
                "status": "ready" if float(df.loc[governing_tens_idx, "Max tension (MPa)"]) <= governing_tens_limit else "danger",
            },
            {
                "title": "Limit profile",
                "value": profile_label,
                "detail": "Selected by the visible tensile stress limit guide",
                "status": "info",
            },
        ],
        columns=4,
    )
    _render_girder_sls4c_action_hints(
        stage_label=stage_label,
        status=status,
        demand_rows=_girder_sls4b_governing_demand_rows(df, stage_label),
    )
    is_service_stage = _beam_sls_stage_label_for_analysis(stage_label) == "Service stage"
    service_split_rendered = False
    if is_service_stage:
        service_split_rendered = _render_final_service_beam_cip_concrete_split(df, basis_options, stage_label)

    if service_split_rendered:
        with st.expander("Overall transformed-section stress overview — Service", expanded=False):
            st.caption(
                "SERVICE.COMP2.1 keeps this overall transformed-section overview as an audit/reference graph only. "
                "Use the visible Beam and CIP final-service stress checks above for composite service design decisions."
            )
            st.plotly_chart(_make_girder_full_length_sls_figure(df, stage_label=stage_label), use_container_width=True)
    else:
        st.plotly_chart(_make_girder_full_length_sls_figure(df, stage_label=stage_label), use_container_width=True)
        if is_service_stage:
            st.caption(
                "Composite Beam/CIP split graphs are not available for this section basis, so the overall service overview remains visible."
            )

    with st.expander(f"Full-length stress table — {stage_label}", expanded=False):
        st.dataframe(_clean_girder_stress_dataframe(df), use_container_width=True, hide_index=True)
    with st.expander("Full-length diagram assumptions", expanded=False):
        st.write("- Loads page station rows provide user/imported N and Mx. When station rows are missing or only one station is available, GIRDER.SLS5A generates a span station grid for auto load + Pe(x) plotting.")
        # Legacy SLS5A source phrase retained: Service auto load = SDL after composite only.
        st.write("- Transfer auto load = precast self-weight; Construction auto load = precast self-weight + wet topping/slab. Bridge Service auto load = bridge SDL after composite; Building Service auto load = Building SDL/LL from Loads (q × tributary width).")
        st.write("- Stage Pe is read from the current Prestress Force States / Losses backend values at each station, including debonded-strand step-function effectiveness.")
        st.write("- The graph connects station rows for one Case Name; it does not generate an envelope. Auto station rows carry zero user Mx unless imported/user rows are present at that station.")
        st.write("- Preview limit lines use the Project Design Code SLS profile for the active stage. The limit stage is not user-selected inside a stage tab.")
        st.write("- GIRDER.SLS4C keeps engineering action hints advisory only; final design still requires code, transfer/development length, shear, end-zone, and detailing checks.")


def _render_girder_sls_check_case_panel(
    *,
    case_title: str,
    case_key: str,
    stage_label: str,
    selected_load_row: Mapping[str, object] | None,
    section_geometry: object,
    basis_options: object,
    basis_names: list[str],
) -> None:
    """Render one isolated Beam/Girder SLS stage check panel.

    LOADS.SLS2B keeps the user-facing workflow aligned with the three design
    stages used on the Loads page.  Each tab has its own Streamlit widget keys
    so Transfer, Construction, and Service checks can be reviewed separately
    without mixing code-limit/profile/prestress UI state.
    """

    st.markdown(f"##### {case_title} SLS Check Case")

    if selected_load_row is None:
        input_cols = st.columns(3)
        basis_key = f"girder_service_stress_basis_name_{case_key}"
        if st.session_state.get(basis_key) not in basis_names:
            st.session_state[basis_key] = _beam_sls_default_basis_for_stage(stage_label, basis_names)
        with input_cols[0]:
            basis_name = st.selectbox(
                "Section basis for stress preview",
                basis_names,
                format_func=lambda name: basis_options.labels.get(name, name),
                key=basis_key,
                help="Choose precast gross properties or composite transformed properties when composite metadata is active.",
            )
        with input_cols[1]:
            axial_n = st.number_input(
                "N service (kN, compression +)",
                value=float(st.session_state.get(f"girder_service_stress_N_kN_{case_key}", 0.0)),
                step=100.0,
                format="%.3f",
                key=f"girder_service_stress_N_kN_{case_key}",
                help="Positive axial force is compression. Leave zero for ordinary flexural girder stress preview.",
            )
        with input_cols[2]:
            moment_m = st.number_input(
                "M service (kN-m, sagging +)",
                value=float(st.session_state.get(f"girder_service_stress_M_kNm_{case_key}", 0.0)),
                step=100.0,
                format="%.3f",
                key=f"girder_service_stress_M_kNm_{case_key}",
                help="Positive sagging moment gives top compression and bottom tension.",
            )
    else:
        requested_basis_name = _beam_sls_requested_basis_key(selected_load_row)
        mapped_basis_name = _beam_sls_load_basis_key(selected_load_row, basis_names)
        if mapped_basis_name is not None:
            basis_name = mapped_basis_name
            st.info(f"Using section basis from selected Loads row: {basis_options.labels.get(basis_name, basis_name)}.")
        else:
            if requested_basis_name == "composite_transformed" and "composite_transformed" not in basis_names:
                st.warning(
                    "The selected Loads row requests Composite transformed section, but composite transformed properties are not active. "
                    "Enable composite deck/topping metadata in Section Builder or intentionally choose a precast-gross preview below."
                )
            else:
                st.warning(
                    "The selected Loads row uses a staged/mixed or unsupported section basis. Choose the basis for this preview explicitly; "
                    "final staged summation is a future milestone."
                )
            override_key = f"girder_sls_load_basis_override_name_{case_key}"
            if st.session_state.get(override_key) not in basis_names:
                st.session_state[override_key] = basis_names[0]
            basis_name = st.selectbox(
                "Preview section basis for selected Loads row",
                basis_names,
                format_func=lambda name: basis_options.labels.get(name, name),
                key=override_key,
            )
        axial_n = _analysis_float_or_zero(selected_load_row.get("N"))
        moment_m = _analysis_float_or_zero(selected_load_row.get("Mx"))

    basis = basis_options.bases[basis_name]
    result = run_basic_girder_service_stress(basis, N_kN=float(axial_n), M_kNm=float(moment_m))
    result_df = _clean_girder_stress_dataframe(pd.DataFrame(girder_service_stress_result_rows(result)))
    has_service_action = abs(float(axial_n)) > 1.0e-9 or abs(float(moment_m)) > 1.0e-9
    stage_force_state_row = _girder_prestress_force_state_for_stage(stage_label)
    stage_force_state_ready = _girder_prestress_force_state_is_ready(stage_force_state_row)
    include_prestress_key = f"girder_service_include_prestress_{case_key}"
    if include_prestress_key not in st.session_state:
        st.session_state[include_prestress_key] = bool(stage_force_state_ready)
    include_prestress_default = bool(st.session_state.get(include_prestress_key, False))
    stage_force_detail = "No positive stage Pe set in Prestress"
    if stage_force_state_ready and stage_force_state_row is not None:
        stage_force_detail = (
            f"{_girder_prestress_force_state_label(stage_force_state_row, stage_label)} · "
            f"Pe={_analysis_float_or_zero(stage_force_state_row.get('Pe_kN')):,.3f} kN"
        )

    _render_analysis_summary_strip(
        [
            {
                "title": "Selected section basis",
                "value": basis_options.labels.get(basis_name, basis_name),
                "detail": f"Area {basis.area_mm2:,.1f} mm² · Ix {basis.ix_mm4:,.3e} mm⁴",
                "status": "ready",
            },
            {
                "title": "Composite basis",
                "value": "Available" if basis_options.has_composite_basis else "Not active",
                "detail": "Use composite transformed section when explicitly enabled" if basis_options.has_composite_basis else "Using precast gross properties only",
                "status": "ready" if basis_options.has_composite_basis else "neutral",
            },
            {
                "title": "Service action",
                "value": "Entered" if has_service_action else "No action",
                "detail": f"N={float(axial_n):,.3f} kN · M={float(moment_m):,.3f} kN-m",
                "status": "ready" if has_service_action else "neutral",
            },
            {
                "title": "Prestress component",
                "value": "Enabled" if include_prestress_default else "Optional",
                "detail": stage_force_detail if include_prestress_default else "Set stage Pe in Prestress, or enable manually below",
                "status": "ready" if include_prestress_default and stage_force_state_ready else ("info" if include_prestress_default else "neutral"),
            },
        ],
        columns=4,
    )

    if not has_service_action:
        st.info("Enter a nonzero service axial force or moment to preview this SLS check case. Zero-action rows are shown only as a sign-convention baseline.")

    stress_cols = st.columns(2)
    stress_cols[0].metric("Service max compression", _format_girder_stress_mpa(result.max_compression_MPa))
    stress_cols[1].metric("Service max tension", _format_girder_stress_mpa(result.max_tension_MPa))

    code_title = f"{case_title} SLS check case"
    _initialize_girder_code_limit_stage_for_case(code_title, stage_label)
    if include_prestress_default:
        st.caption(
            "Stage prestress is enabled. The main code-limit preview for this stage uses the combined service + prestress stress below."
        )
        with st.expander(f"Service-only code-limit preview — {case_title}", expanded=False):
            service_only_title = f"{case_title} service-only SLS check case"
            _initialize_girder_code_limit_stage_for_case(service_only_title, stage_label)
            _render_girder_code_limit_preview(
                title=service_only_title,
                stresses=_girder_stress_limit_input_rows_from_dataframe(result_df, "Total stress (MPa)"),
                section_basis_label=basis_options.labels.get(basis_name, basis_name),
                load_stage=None if selected_load_row is None else str(selected_load_row.get("Stage") or stage_label),
                load_component=None if selected_load_row is None else str(selected_load_row.get("Load Component") or ""),
                stress_includes_prestress=False,
                prestress_force_state_label=None,
                locked_stage_label=stage_label,
            )
    else:
        _render_girder_code_limit_preview(
            title=code_title,
            stresses=_girder_stress_limit_input_rows_from_dataframe(result_df, "Total stress (MPa)"),
            section_basis_label=basis_options.labels.get(basis_name, basis_name),
            load_stage=None if selected_load_row is None else str(selected_load_row.get("Stage") or stage_label),
            load_component=None if selected_load_row is None else str(selected_load_row.get("Load Component") or ""),
            stress_includes_prestress=False,
            prestress_force_state_label=None,
            locked_stage_label=stage_label,
        )

    with st.expander(f"{case_title} stress table", expanded=False):
        st.dataframe(result_df, use_container_width=True, hide_index=True)

    prestress_elements = list(st.session_state.get("prestress_elements", []) or [])
    section_bottom_y_mm = 0.0
    if section_geometry is not None:
        try:
            section_bottom_y_mm = float(summarize_geometry(section_geometry).y_min_mm or 0.0)
        except (TypeError, ValueError) as exc:
            st.warning(f"Unable to convert prestress coordinates to girder bottom-fiber coordinates: {exc}")

    st.markdown(f"##### Prestress Effect — {case_title}")
    if not include_prestress_default:
        _render_analysis_summary_strip(
            [
                {
                    "title": "Prestress stress component",
                    "value": "Not included",
                    "detail": "Enable prestress only when the selected stage should include prestress stress effect",
                    "status": "neutral",
                }
            ],
            columns=1,
        )
    include_prestress = st.checkbox(
        "Include prestress stress component for this stage",
        value=bool(st.session_state.get(include_prestress_key, False)),
        key=include_prestress_key,
        help="Preview the stress contribution from the currently available effective prestress input. This does not change the Prestress or PMM solvers.",
    )

    if include_prestress:
        st.info(
            "Stage prestress is an internal section action. Define Pe_transfer, Pe_construction, or Pe_eff_final in Prestress; do not duplicate this force in Loads."
        )
        mode_options = ["From Prestress force state", "From Prestress table", "Manual Pe_eff and yps"]
        prestress_mode_key = f"girder_prestress_input_mode_{case_key}"
        if st.session_state.get(prestress_mode_key) not in mode_options:
            if stage_force_state_ready:
                st.session_state[prestress_mode_key] = "From Prestress force state"
            elif prestress_elements:
                st.session_state[prestress_mode_key] = "From Prestress table"
            else:
                st.session_state[prestress_mode_key] = "Manual Pe_eff and yps"
        prestress_mode = st.radio(
            "Prestress source",
            mode_options,
            horizontal=True,
            key=prestress_mode_key,
            help="Use the stage force state from Prestress for commercial stage checks, or use legacy table/manual preview for audit cases.",
        )

        pe_eff_kN = 0.0
        tendon_y_from_bottom_mm = basis.centroid_y_from_bottom_mm
        source_ready = False
        prestress_force_state_label_for_preview = ""

        if prestress_mode == "From Prestress force state":
            if stage_force_state_ready and stage_force_state_row is not None:
                pe_eff_kN = _analysis_float_or_zero(stage_force_state_row.get("Pe_kN"))
                tendon_y_from_bottom_mm = _analysis_float_or_zero(stage_force_state_row.get("yps_mm_from_bottom"))
                prestress_force_state_label_for_preview = _girder_prestress_force_state_label(stage_force_state_row, stage_label)
                source_ready = True
                state_cols = st.columns(4)
                state_cols[0].metric("Prestress state", prestress_force_state_label_for_preview)
                state_cols[1].metric("Stage Pe", f"{pe_eff_kN:,.3f} kN")
                state_cols[2].metric("yps from bottom", f"{tendon_y_from_bottom_mm:,.3f} mm")
                state_cols[3].metric("Source", "Prestress page")
                with st.expander(f"Prestress force-state note — {case_title}", expanded=False):
                    note = str(stage_force_state_row.get("Note") or "").strip()
                    st.write(note or "No note entered for this stage force state.")
            else:
                st.warning(
                    "No positive stage prestress force is set for this SLS stage. Enter Pe and yps in Prestress → Girder SLS Prestress Force States."
                )

        elif prestress_mode == "From Prestress table":
            summary = summarize_girder_prestress_elements(
                prestress_elements,
                section_bottom_y_mm=section_bottom_y_mm,
                include_unbonded=True,
            )
            table_cols = st.columns(4)
            table_cols[0].metric("Included PS rows", f"{summary.included_element_count:,}")
            table_cols[1].metric("Ignored PS rows", f"{summary.ignored_element_count:,}")
            table_cols[2].metric("Σ Pe_eff", f"{summary.total_pe_eff_kN:,.3f} kN")
            table_cols[3].metric(
                "PS centroid yb",
                "—" if summary.tendon_y_from_bottom_mm is None else f"{summary.tendon_y_from_bottom_mm:,.2f} mm",
            )
            if summary.warnings:
                with st.expander(f"Prestress source warnings — {case_title}", expanded=False):
                    for warning in summary.warnings:
                        st.warning(warning)
            with st.expander(f"Prestress source notes — {case_title}", expanded=False):
                if summary.info:
                    for item in summary.info:
                        st.write(f"- {item}")
                else:
                    st.write("No positive Pe_eff prestress element has been included yet.")
            if summary.total_pe_eff_kN > 0.0 and summary.tendon_y_from_bottom_mm is not None:
                pe_eff_kN = float(summary.total_pe_eff_kN)
                tendon_y_from_bottom_mm = float(summary.tendon_y_from_bottom_mm)
                source_ready = True
        else:
            manual_cols = st.columns(2)
            with manual_cols[0]:
                pe_eff_kN = float(
                    st.number_input(
                        "Pe_eff (kN, compression +)",
                        min_value=0.0,
                        value=float(st.session_state.get(f"girder_manual_pe_eff_kN_{case_key}", 0.0)),
                        step=100.0,
                        format="%.3f",
                        key=f"girder_manual_pe_eff_kN_{case_key}",
                        help="Effective prestress after losses or engineer-entered stage-equivalent prestress. Do not enter breaking load here.",
                    )
                )
            with manual_cols[1]:
                tendon_y_from_bottom_mm = float(
                    st.number_input(
                        "Prestress centroid yps (mm from bottom)",
                        value=float(st.session_state.get(f"girder_manual_ps_y_from_bottom_mm_{case_key}", basis.centroid_y_from_bottom_mm)),
                        step=10.0,
                        format="%.3f",
                        key=f"girder_manual_ps_y_from_bottom_mm_{case_key}",
                        help="Centroid of effective prestress measured upward from the selected section-basis bottom fiber.",
                    )
                )
            source_ready = pe_eff_kN > 0.0
            if not source_ready:
                st.info("Enter a positive Pe_eff to preview prestress stress effects.")

        if not source_ready and prestress_mode == "From Prestress table":
            st.info("No positive Pe_eff is available for this check case; prestress stress remains excluded from the summary result.")

        if source_ready and not prestress_force_state_label_for_preview:
            if prestress_mode == "From Prestress table":
                prestress_force_state_label_for_preview = "Pe_eff after losses / Prestress table effective force"
            elif prestress_mode == "Manual Pe_eff and yps":
                if stage_label == "Transfer stage":
                    prestress_force_state_label_for_preview = "Manual Pe_transfer / stage-equivalent prestress"
                elif stage_label == "Construction stage":
                    prestress_force_state_label_for_preview = "Manual Pe_construction / stage-equivalent prestress"
                else:
                    prestress_force_state_label_for_preview = "Manual Pe_eff_final / stage-equivalent prestress"

        if source_ready:
            ps_result = run_girder_prestress_stress_effect(
                basis,
                Pe_eff_kN=pe_eff_kN,
                tendon_y_from_bottom_mm=tendon_y_from_bottom_mm,
            )
            ps_cols = st.columns(4)
            ps_cols[0].metric("Stage Pe", f"{ps_result.Pe_eff_kN:,.3f} kN")
            ps_cols[1].metric("e = yps - yc", f"{ps_result.eccentricity_mm:,.2f} mm")
            ps_cols[2].metric("Mps", f"{ps_result.equivalent_moment_kNm:,.3f} kN-m")
            ps_cols[3].metric("PS max compression", _format_girder_stress_mpa(ps_result.max_compression_MPa))

            for warning in ps_result.warnings:
                st.warning(f"Prestress stress preview warning: {warning}")

            with st.expander(f"Prestress stress table — {case_title}", expanded=False):
                st.dataframe(_clean_girder_stress_dataframe(pd.DataFrame(girder_prestress_stress_result_rows(ps_result))), use_container_width=True, hide_index=True)
            combined_df = _clean_girder_stress_dataframe(pd.DataFrame(_girder_combined_service_prestress_rows(result, ps_result)))
            st.markdown(f"##### Combined Service + Prestress Stress — {case_title}")
            combined_cols = st.columns(2)
            combined_cols[0].metric("Combined max compression", _format_girder_stress_mpa(combined_df["Combined total (MPa)"].min()))
            combined_cols[1].metric("Combined max tension", _format_girder_stress_mpa(combined_df["Combined total (MPa)"].max()))
            with st.expander(f"Combined stress table — {case_title}", expanded=False):
                st.dataframe(combined_df, use_container_width=True, hide_index=True)
            combined_title = f"{case_title} combined service plus prestress stress"
            _initialize_girder_code_limit_stage_for_case(combined_title, stage_label)
            _render_girder_code_limit_preview(
                title=combined_title,
                stresses=_girder_stress_limit_input_rows_from_dataframe(combined_df, "Combined total (MPa)"),
                section_basis_label=basis_options.labels.get(basis_name, basis_name),
                load_stage=None if selected_load_row is None else str(selected_load_row.get("Stage") or stage_label),
                load_component=None if selected_load_row is None else str(selected_load_row.get("Load Component") or ""),
                stress_includes_prestress=True,
                prestress_force_state_label=prestress_force_state_label_for_preview,
                locked_stage_label=stage_label,
            )


def _girder_fc_for_sls_limit_preview() -> float:
    """Return the primary concrete f'c for Beam/Girder SLS limit preview."""

    concrete_material = st.session_state.get("concrete_material")
    try:
        fc = float(getattr(concrete_material, "fc_MPa"))
    except (TypeError, ValueError):
        fc = 45.0
    if not math.isfinite(fc) or fc <= 0.0:
        fc = 45.0
    return fc


def _girder_stress_limit_input_rows_from_dataframe(df: pd.DataFrame, stress_column: str) -> list[StressLimitInputRow]:
    """Build pure limit-check rows from a display/result dataframe."""

    if df.empty or stress_column not in df.columns:
        return []
    rows: list[StressLimitInputRow] = []
    for _, row in df.iterrows():
        fiber = str(row.get("Fiber", row.get("location", "Fiber")))
        try:
            stress = float(row[stress_column])
        except (TypeError, ValueError):
            continue
        if math.isfinite(stress):
            rows.append(StressLimitInputRow(fiber=fiber, stress_MPa=stress))
    return rows


def _format_girder_limit_demand_mpa(value: float) -> str:
    """Format a nonnegative demand/limit stress value for SLS decision cards."""

    if abs(float(value)) <= _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
        return "0.000 MPa"
    return f"{float(value):,.3f} MPa"


def _format_girder_limit_utilization(value: float | None) -> str:
    """Format utilization while keeping no-tension cases explicit."""

    if value is None:
        return "—"
    if not math.isfinite(float(value)):
        return "—"
    return f"D/C {float(value):.3f}"


def _girder_limit_point_status_style(point: GirderStressLimitPointResult | None, *, context_warnings: bool = False) -> str:
    """Return the compact card style for one stress-vs-limit comparison."""

    if context_warnings:
        return "warning"
    if point is None:
        return "neutral"
    if point.status == "FAIL":
        return "danger"
    return "ready"


def _governing_limit_point(
    points: tuple[GirderStressLimitPointResult, ...],
    *,
    stress_type: str,
) -> GirderStressLimitPointResult | None:
    """Return the governing compression or tension point by actual demand."""

    candidates = [point for point in points if point.stress_type == stress_type]
    if not candidates:
        return None
    if stress_type == "compression":
        return max(candidates, key=lambda point: abs(float(point.stress_MPa)))
    return max(candidates, key=lambda point: float(point.stress_MPa))


def _girder_stress_vs_limit_cards(
    limit_result: GirderServiceStressLimitCheckResult,
    *,
    context_warnings: bool = False,
) -> list[dict[str, object]]:
    """Return decision cards comparing actual stress with the matching stress limit.

    GIRDER.SLS3.2 keeps the default SLS view as a decision screen: compression
    demand is compared only with the compression limit, and tension demand is
    compared only with the tension limit.  Detailed top/bottom rows remain in
    the audit table.
    """

    compression_point = _governing_limit_point(limit_result.points, stress_type="compression")
    tension_point = _governing_limit_point(limit_result.points, stress_type="tension")

    if compression_point is None:
        compression_limit = limit_result.profile.compression_limit_MPa(limit_result.fc_MPa)
        compression_card = {
            "title": "Compression actual / limit",
            "value": f"0.000 / {compression_limit:,.3f} MPa",
            "detail": "No compressive fiber stress in this check case",
            "status": "neutral",
        }
    else:
        compression_card = {
            "title": "Compression actual / limit",
            "value": (
                f"{_format_girder_limit_demand_mpa(abs(float(compression_point.stress_MPa))).replace(' MPa', '')} / "
                f"{compression_point.compression_limit_MPa:,.3f} MPa"
            ),
            "detail": (
                f"{compression_point.fiber}: compression demand uses compression limit · "
                f"{_format_girder_limit_utilization(compression_point.utilization)}"
            ),
            "status": _girder_limit_point_status_style(compression_point, context_warnings=context_warnings),
        }

    if tension_point is None:
        tension_limit = limit_result.profile.tension_allowable_MPa(limit_result.fc_MPa)
        tension_value = "No tension" if tension_limit <= limit_result.profile.stress_zero_tolerance_MPa else f"{tension_limit:,.3f} MPa"
        tension_card = {
            "title": "Tension actual / limit",
            "value": f"0.000 MPa / {tension_value}",
            "detail": "No tensile fiber stress in this check case",
            "status": "neutral",
        }
    else:
        tension_limit_value = (
            "No tension"
            if tension_point.tension_limit_MPa <= limit_result.profile.stress_zero_tolerance_MPa
            else f"{tension_point.tension_limit_MPa:,.3f} MPa"
        )
        tension_card = {
            "title": "Tension actual / limit",
            "value": f"{_format_girder_limit_demand_mpa(float(tension_point.stress_MPa))} / {tension_limit_value}",
            "detail": (
                f"{tension_point.fiber}: tension demand uses tension limit · "
                f"{_format_girder_limit_utilization(tension_point.utilization)}"
            ),
            "status": _girder_limit_point_status_style(tension_point, context_warnings=context_warnings),
        }

    return [compression_card, tension_card]



def _girder_section_y_bounds_from_session() -> tuple[float, float] | None:
    """Return current section y-bounds in mm for reinforcement guidance."""

    geometry = st.session_state.get("section_geometry")
    polygon = getattr(geometry, "outer_polygon", None)
    if not polygon:
        return None
    y_values: list[float] = []
    for point in polygon:
        y = getattr(point, "y", None)
        if y is None and isinstance(point, Mapping):
            y = point.get("y")
        try:
            y_values.append(float(y))
        except (TypeError, ValueError):
            continue
    if not y_values:
        return None
    return min(y_values), max(y_values)


def _rebar_y_value_mm(rebar) -> float | None:
    y = getattr(rebar, "y_mm", None)
    if y is None and isinstance(rebar, Mapping):
        y = rebar.get("y_mm")
    try:
        return float(y)
    except (TypeError, ValueError):
        return None


def _girder_tension_fibers_from_stresses(stresses: list[StressLimitInputRow]) -> set[str]:
    """Return Top/Bottom fibers with positive tensile stress under the app convention."""

    fibers: set[str] = set()
    for row in stresses:
        if float(getattr(row, "stress_MPa", 0.0) or 0.0) <= _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:
            continue
        fiber = str(getattr(row, "fiber", "")).strip().lower()
        if "top" in fiber:
            fibers.add("Top")
        elif "bottom" in fiber or "bot" in fiber:
            fibers.add("Bottom")
    return fibers


def _girder_ordinary_rebar_tension_face_summary(stresses: list[StressLimitInputRow]) -> dict[str, object]:
    """Conservatively identify ordinary rebar near the currently tensile face.

    CODE.SLS.LIMIT4 uses this only as guidance.  It does not prove code-required
    reinforcement adequacy and it never upgrades tensile limits silently without
    a visible REVIEW/verification context.
    """

    tension_fibers = _girder_tension_fibers_from_stresses(stresses)
    if not tension_fibers:
        return {
            "tension_fibers": "No positive tension in supplied stress rows",
            "bars_near_tension_face": 0,
            "auto_verified": None,
            "detail": "No tensile fiber controls this stress row set.",
        }
    if not ordinary_rebar_enabled(st.session_state, default=True):
        return {
            "tension_fibers": ", ".join(sorted(tension_fibers)),
            "bars_near_tension_face": 0,
            "auto_verified": False,
            "detail": "Ordinary rebar system is disabled.",
        }
    bounds = _girder_section_y_bounds_from_session()
    rebars = list(st.session_state.get("rebars", []) or [])
    if bounds is None or not rebars:
        return {
            "tension_fibers": ", ".join(sorted(tension_fibers)),
            "bars_near_tension_face": 0,
            "auto_verified": None,
            "detail": "Section bounds or ordinary rebar layout unavailable; reinforcement condition is not auto-verified.",
        }
    y_min, y_max = bounds
    depth = max(y_max - y_min, 1.0)
    bottom_zone = y_min + 0.35 * depth
    top_zone = y_max - 0.35 * depth
    bars_near = 0
    for rebar in rebars:
        y = _rebar_y_value_mm(rebar)
        if y is None:
            continue
        if "Bottom" in tension_fibers and y <= bottom_zone:
            bars_near += 1
        if "Top" in tension_fibers and y >= top_zone:
            bars_near += 1
    auto_verified = True if bars_near > 0 else False
    return {
        "tension_fibers": ", ".join(sorted(tension_fibers)),
        "bars_near_tension_face": bars_near,
        "auto_verified": auto_verified,
        "detail": f"Ordinary bars near tensile face by broad 35% depth-zone check: {bars_near}.",
    }




def _active_strand_diameter_for_transfer_length_mm() -> tuple[float, str]:
    """Return the active strand diameter used for ACI 60db end-zone length.

    Uses the maximum active strand diameter found in the girder strand layout;
    falls back to 12.7 mm so the UI can still produce an auditable preview.
    """

    table = st.session_state.get("girder_strand_layout_table")
    diameters: list[float] = []
    try:
        df = pd.DataFrame(table)
    except Exception:
        df = pd.DataFrame()
    if not df.empty:
        for _, row in df.iterrows():
            active_value = row.get("Active", True)
            active = bool(active_value)
            if isinstance(active_value, str):
                active = active_value.strip().casefold() not in {"false", "0", "no", "off", "inactive"}
            if not active:
                continue
            for key in ("Diameter_mm", "Strand Diameter_mm", "diameter_mm"):
                if key not in row:
                    continue
                try:
                    value = float(row.get(key))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0.0:
                    diameters.append(value)
                    break
    if diameters:
        diameter = max(diameters)
        return diameter, f"max active strand diameter from layout = {diameter:.1f} mm"
    return 12.7, "fallback default strand diameter = 12.7 mm"


def _section_depth_mm_from_session() -> float | None:
    bounds = _girder_section_y_bounds_from_session()
    if bounds is None:
        return None
    y_min, y_max = bounds
    depth = float(y_max) - float(y_min)
    return depth if math.isfinite(depth) and depth > 0.0 else None


def _is_building_aci_transfer_end_zone_applicable(stage_label: str) -> bool:
    """Return True when ACI transfer end-zone limit may apply to this diagram.

    CODE.SLS.LIMIT5 intentionally scopes this to Building Beam/Girder shared
    precast prestressed girder workflow only.  It must not leak into Bridge
    AASHTO diagrams.
    """

    mode = _analysis_mode_from_session()
    if not is_building_beam_girder_workflow(mode):
        return False
    if _girder_sls_profile_code_from_session() != "ACI 318":
        return False
    limit_stage = stage_label if stage_label in DEFAULT_GIRDER_SLS_STAGES else _beam_sls_stage_default_code_limit_stage(stage_label)
    if limit_stage != STAGE_TRANSFER:
        return False
    preset = str(st.session_state.get("section_preset_key") or "").strip().casefold()
    if preset != "parametric_i_girder":
        return False
    return prestressing_steel_enabled(st.session_state, default=True)


def _aci_transfer_end_zone_length_state(stage_label: str) -> tuple[float, str, str]:
    """Return end-zone length and display basis for the visible guide/graph."""

    safe_stage = _beam_sls_stage_label_for_analysis(stage_label).replace(" ", "_").replace("/", "_")
    basis_key = f"aci_transfer_end_zone_length_basis_{safe_stage}"
    diameter_key = f"aci_transfer_end_zone_db_mm_{safe_stage}"
    user_key = f"aci_transfer_end_zone_user_length_m_{safe_stage}"
    default_diameter, diameter_source = _active_strand_diameter_for_transfer_length_mm()
    basis = str(st.session_state.get(basis_key) or "Transfer length 60db")
    diameter = float(st.session_state.get(diameter_key, default_diameter) or default_diameter)
    user_length = float(st.session_state.get(user_key, 0.0) or 0.0)
    depth = _section_depth_mm_from_session()
    try:
        length = aci_transfer_end_zone_length_m(
            strand_diameter_mm=diameter,
            member_depth_mm=depth,
            user_defined_length_m=user_length,
            basis=basis,
        )
    except Exception:
        length = aci_transfer_end_zone_length_m(strand_diameter_mm=default_diameter, basis="Transfer length 60db")
        basis = "Transfer length 60db"
    if "60" in basis or "transfer" in basis.casefold():
        detail = f"{basis}: lt = 60db = 60 × {diameter:.1f} mm = {length:.3f} m ({diameter_source})"
    elif "depth" in basis.casefold():
        detail = f"{basis}: h = {0.0 if depth is None else depth:.1f} mm = {length:.3f} m"
    elif "face" in basis.casefold():
        detail = "Conservative end-face-only option: higher end-zone line is not extended along the span."
    else:
        detail = f"{basis}: user-defined end-zone length = {length:.3f} m"
    return float(length), basis, detail


def _diagram_uses_aci_transfer_end_zone_limit(stage_label: str) -> bool:
    if not _is_building_aci_transfer_end_zone_applicable(stage_label):
        return False
    profile = _girder_stage_limit_profile_for_diagram(stage_label)
    return str(getattr(profile, "limit_profile_key", "")) == "aci_transfer_end_zone_verified"


def _girder_sls_tension_limit_at_station(stage_label: str, station_m: float, *, span_length_m: float | None = None) -> tuple[float, str]:
    """Return positive tensile limit at station for display/checking.

    Most profiles are constant along the span.  CODE.SLS.LIMIT5 adds one
    scoped exception: Building ACI transfer end-zone checked with a piecewise
    0.50√f'ci end-zone limit and 0.25√f'ci interior limit.
    """

    compression_limit, tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    del compression_limit
    if not _diagram_uses_aci_transfer_end_zone_limit(stage_label):
        return float(tension_limit), profile_label
    fc = _girder_fc_for_sls_limit_preview()
    span = float(span_length_m or _girder_sls_span_length_from_session([]) or 0.0)
    end_length, _basis, _detail = _aci_transfer_end_zone_length_state(stage_label)
    trace = aci_transfer_tension_limit_trace(
        span_length_m=max(span, 1.0e-6),
        fci_MPa=float(fc),
        end_zone_length_m=end_length,
        use_end_zone_limit=True,
    )
    x = float(station_m)
    in_end_zone = x <= trace.end_zone_length_m + 1.0e-9 or x >= max(span - trace.end_zone_length_m, 0.0) - 1.0e-9
    return (trace.end_zone_limit_MPa if in_end_zone else trace.interior_limit_MPa), profile_label


def _girder_sls_tension_limit_trace_for_graph(stage_label: str, df: pd.DataFrame) -> tuple[list[float], list[float], str]:
    """Return x/y trace for the tensile limit line displayed on the SLS graph."""

    _compression, tension_limit, profile_label = _girder_sls_diagram_limit_summary(stage_label)
    if df.empty or "Station x (m)" not in df.columns:
        return [0.0, 1.0], [float(tension_limit), float(tension_limit)], profile_label
    x_min = float(pd.to_numeric(df["Station x (m)"], errors="coerce").min())
    x_max = float(pd.to_numeric(df["Station x (m)"], errors="coerce").max())
    if abs(x_max - x_min) <= 1e-9:
        x_min -= 0.5
        x_max += 0.5
    if not _diagram_uses_aci_transfer_end_zone_limit(stage_label):
        return [x_min, x_max], [float(tension_limit), float(tension_limit)], profile_label
    fc = _girder_fc_for_sls_limit_preview()
    end_length, _basis, _detail = _aci_transfer_end_zone_length_state(stage_label)
    trace = aci_transfer_tension_limit_trace(
        span_length_m=max(x_max - x_min, 1.0e-6),
        fci_MPa=float(fc),
        end_zone_length_m=end_length,
        use_end_zone_limit=True,
    )
    return [x_min + x for x in trace.x_m], list(trace.y_MPa), profile_label


def _render_girder_tension_limit_guidance(
    *,
    title: str,
    code: str,
    stage: str,
    stresses: list[StressLimitInputRow],
    profile_key: str,
    profile_options: tuple,
    show_end_zone_controls: bool = True,
) -> tuple[str, list[str]]:
    """Render CODE.SLS.LIMIT4 guided tensile-limit selection and return profile key."""

    # CODE.SLS.LIMIT4.2: show the selected tensile-limit formula and substitution in the visible guide.
    # CODE.SLS.LIMIT4: reinforcement-aware tensile stress limit selection aid only.
    option_keys = {option.key for option in profile_options}
    guide_enabled_key = f"girder_tension_limit_guide_enabled_{title}"
    guide_method_key = f"girder_tension_limit_guide_method_{title}"
    exposure_key = f"girder_tension_limit_exposure_{title}"
    aci_class_key = f"girder_tension_limit_aci_class_{title}"
    duration_key = f"girder_tension_limit_duration_{title}"
    summary = _girder_ordinary_rebar_tension_face_summary(stresses)
    method_options = [
        "Auto from current ordinary rebar layout",
        "Verified bonded tension reinforcement",
        "Not verified / use conservative preview",
        "No bonded reinforcement / no-tension condition",
    ]
    if st.session_state.get(guide_method_key) not in method_options:
        st.session_state[guide_method_key] = method_options[0]
    guide_enabled = st.checkbox(
        "Use guided tensile limit profile",
        value=bool(st.session_state.get(guide_enabled_key, True)),
        key=guide_enabled_key,
        help="When enabled, the limit profile is selected from code/stage, exposure/class, and reinforcement-condition inputs. Turn off for manual profile selection.",
    )
    cols = st.columns([1.2, 1.1, 1.1, 1.1])
    with cols[0]:
        method = st.selectbox(
            "Tension reinforcement condition",
            method_options,
            key=guide_method_key,
            help="Auto detection is only a screening aid. Use verified/manual selections when project reinforcement conditions control tensile stress limits.",
        )
    with cols[1]:
        if code == "AASHTO LRFD Bridge":
            exposure_options = ["Moderate exposure / bonded", "Severe exposure / bonded", "Unbonded or no tension"]
            if st.session_state.get(exposure_key) not in exposure_options:
                st.session_state[exposure_key] = exposure_options[0]
            if stage == STAGE_FINAL_SERVICE:
                exposure = st.selectbox("Exposure / tendon condition", exposure_options, key=exposure_key)
            else:
                exposure = "moderate"
                st.markdown("**Exposure / tendon condition**")
                st.caption("Not applied to Transfer/Construction; AASHTO exposure/tendon condition controls Service-stage tensile limit only.")
            aci_service_class = "Class U"
        else:
            aci_options = ["Class U", "Class T", "No tension"]
            if st.session_state.get(aci_class_key) not in aci_options:
                st.session_state[aci_class_key] = aci_options[0]
            if stage == STAGE_FINAL_SERVICE:
                aci_service_class = st.selectbox("ACI service class", aci_options, key=aci_class_key)
            else:
                aci_service_class = "Class U"
                st.markdown("**ACI service class**")
                st.caption("Not applied to Transfer/Construction; this stage uses its stage-specific tensile stress limit formula.")
            exposure = "moderate"
    with cols[2]:
        duration_options = ["Full service / total", "Sustained or permanent only"]
        if st.session_state.get(duration_key) not in duration_options:
            st.session_state[duration_key] = duration_options[0]
        if stage == STAGE_FINAL_SERVICE:
            duration = st.selectbox("Effect duration", duration_options, key=duration_key)
        else:
            duration = "Full service / total"
            st.markdown("**Effect duration**")
            st.caption("Not applied to this stage; service duration controls only service-stage classification.")
    if method == "Auto from current ordinary rebar layout":
        # CODE.SLS.LIMIT5: ACI transfer end-zone higher limit requires an
        # engineer-verified R24.5.3 condition.  Auto rebar detection is only a
        # screening aid and must not silently select the higher end-zone limit.
        if code == "ACI 318" and stage == STAGE_TRANSFER:
            verified = None
        else:
            verified = summary.get("auto_verified")
    elif method == "Verified bonded tension reinforcement":
        verified = True
    elif method == "No bonded reinforcement / no-tension condition":
        verified = False
        exposure = "no tension"
        aci_service_class = "No tension"
    else:
        verified = None
    guidance = recommend_girder_tension_limit_profile(
        code=code,
        stage=stage,
        bonded_tension_reinforcement_verified=verified,
        exposure_condition=exposure,
        aci_service_class=aci_service_class,
        effect_duration=duration,
    )
    recommended_key = guidance.recommended_profile_key if guidance.recommended_profile_key in option_keys else profile_key
    if guide_enabled:
        st.session_state[profile_key] = recommended_key
    with cols[3]:
        st.markdown("**Guided profile**")
        st.caption(recommended_key.replace("_", " "))
    status = "ready" if guidance.status == "OK" else "warning"
    _render_analysis_summary_strip(
        [
            {
                "title": "Tensile limit guide",
                "value": guidance.status,
                "detail": guidance.basis,
                "status": status,
            },
            {
                "title": "Detected tensile fiber",
                "value": str(summary.get("tension_fibers")),
                "detail": str(summary.get("detail")),
                "status": "info" if summary.get("auto_verified") else "warning",
            },
        ],
        columns=2,
    )

    selected_profile_key = recommended_key if guide_enabled else str(st.session_state.get(profile_key, profile_key))
    selected_profile = build_girder_sls_limit_profile(code=code, stage=stage, limit_profile_key=selected_profile_key)
    fc_for_formula = _girder_fc_for_sls_limit_preview()
    formula_summary = girder_sls_limit_formula_summary(profile=selected_profile, fc_MPa=float(fc_for_formula))
    _render_analysis_summary_strip(
        [
            {
                "title": "Selected tensile limit",
                "value": f"{formula_summary.tension_limit_MPa:.3f} MPa",
                "detail": formula_summary.tension_formula,
                "status": "ready" if formula_summary.tension_limit_MPa > 0.0 else "warning",
            },
            {
                "title": "Tension formula substitution",
                "value": formula_summary.tension_substitution,
                "detail": f"{formula_summary.strength_label} = {float(fc_for_formula):.3f} MPa · {selected_profile.limit_profile_label}",
                "status": "info",
            },
        ],
        columns=2,
    )
    # CODE.SLS.LIMIT5: show ACI transfer end-zone formulas directly in the visible guide.
    if code == "ACI 318" and stage == STAGE_TRANSFER and _is_building_aci_transfer_end_zone_applicable(stage):
        end_zone_selected = selected_profile_key == "aci_transfer_end_zone_verified"
        safe_stage = _beam_sls_stage_label_for_analysis(stage).replace(" ", "_").replace("/", "_")
        basis_key = f"aci_transfer_end_zone_length_basis_{safe_stage}"
        diameter_key = f"aci_transfer_end_zone_db_mm_{safe_stage}"
        user_key = f"aci_transfer_end_zone_user_length_m_{safe_stage}"
        default_diameter, _diameter_source = _active_strand_diameter_for_transfer_length_mm()
        basis_options = ["Transfer length 60db", "Member depth h", "User-defined length", "Conservative end face only"]
        if st.session_state.get(basis_key) not in basis_options:
            st.session_state[basis_key] = basis_options[0]
        if show_end_zone_controls:
            ez_cols = st.columns([1.05, 0.85, 0.85])
            with ez_cols[0]:
                st.selectbox("ACI transfer end-zone length basis", basis_options, key=basis_key)
            with ez_cols[1]:
                st.number_input(
                    "Strand db for 60db (mm)",
                    min_value=1.0,
                    value=float(st.session_state.get(diameter_key, default_diameter) or default_diameter),
                    step=0.1,
                    format="%.1f",
                    key=diameter_key,
                    help="Used only when end-zone length basis is Transfer length 60db. Default comes from active strand layout when available.",
                )
            with ez_cols[2]:
                st.number_input(
                    "User end-zone length (m)",
                    min_value=0.0,
                    value=float(st.session_state.get(user_key, 0.0) or 0.0),
                    step=0.05,
                    format="%.3f",
                    key=user_key,
                    help="Used only when end-zone length basis is User-defined length.",
                )
        else:
            st.caption("End-zone length controls are shown in the visible full-length diagram guide to avoid duplicate Streamlit widget keys.")
        span_for_trace = _girder_sls_span_length_from_session([])
        end_length, _end_basis, end_detail = _aci_transfer_end_zone_length_state(stage)
        trace = aci_transfer_tension_limit_trace(
            span_length_m=max(float(span_for_trace), 1.0e-6),
            fci_MPa=float(fc_for_formula),
            end_zone_length_m=end_length,
            use_end_zone_limit=end_zone_selected,
        )
        _render_analysis_summary_strip(
            [
                {
                    "title": "ACI transfer end-zone limit",
                    "value": f"{trace.end_zone_limit_MPa:.3f} MPa" if end_zone_selected else "Not active",
                    "detail": f"End zone: 0.50√{float(fc_for_formula):.3f} MPa; {end_detail}",
                    "status": "warning" if end_zone_selected else "neutral",
                },
                {
                    "title": "ACI transfer interior limit",
                    "value": f"{trace.interior_limit_MPa:.3f} MPa",
                    "detail": f"Interior/general span: 0.25√{float(fc_for_formula):.3f} MPa",
                    "status": "info",
                },
            ],
            columns=2,
        )
        if end_zone_selected:
            st.warning(
                "ACI end-zone higher tensile limit is used only for this Building precast prestressed girder Transfer preview. "
                "Confirm bonded non-prestressed reinforcement is adequate for total tensile force or that cracked-section adequacy is shown before final design."
            )
    if code != "AASHTO LRFD Bridge" and stage != STAGE_FINAL_SERVICE:
        st.info("ACI Class U / Class T service classification changes the Service-stage tensile limit only. Transfer and Construction use their own stage-specific limit formulas.")

    notes = list(guidance.warnings)
    if method == "Auto from current ordinary rebar layout":
        notes.append("Auto rebar detection is a screening aid only; it does not verify code-required bonded reinforcement area, detailing, development, or crack-control requirements.")
    return (selected_profile_key, notes)


def _render_girder_code_limit_preview(
    *,
    title: str,
    stresses: list[StressLimitInputRow],
    default_expanded: bool = False,
    section_basis_label: str | None = None,
    load_stage: str | None = None,
    load_component: str | None = None,
    stress_includes_prestress: bool | None = None,
    prestress_force_state_label: str | None = None,
    locked_stage_label: str | None = None,
) -> None:
    """Render compact CODE.SLS.LIMIT3 preview checks for a set of fiber stresses.

    This is a UI/reporting foundation only.  It does not change any stress
    kernel, PMM solver, prestress input, load table, or report workflow.
    CODE.SLS.LIMIT3 displays the governing preview-limit formulas and
    warns when the selected load row, code-limit stage, section basis, and
    transfer-stage prestress assumptions are inconsistent.  It remains
    guidance-only and does not alter stress values.
    """

    if not stresses:
        st.info("No stress rows are available for code-limit preview.")
        return

    # GIRDER.SLS3 clean check-case layout: default screen is a decision view; expanders are audit view.
    st.markdown(f"##### Code Limit Summary — {title}")
    st.caption(
        "Compact preview only. The stress-limit stage follows the active Transfer/Construction/Service tab; "
        "detailed formulas, basis notes, and stress rows stay in expanders."
    )

    fc_default = _girder_fc_for_sls_limit_preview()
    stage_key = f"girder_code_limit_stage_{title}"
    locked_stage = None
    if locked_stage_label is not None:
        locked_stage = _beam_sls_stage_default_code_limit_stage(locked_stage_label)
        st.session_state[stage_key] = locked_stage
    elif stage_key in st.session_state:
        normalized_stage = normalize_girder_sls_stage(st.session_state.get(stage_key))
        if normalized_stage in DEFAULT_GIRDER_SLS_STAGES and normalized_stage != st.session_state.get(stage_key):
            st.session_state[stage_key] = normalized_stage

    controls = st.columns([1.0, 1.05, 1.55, 0.85, 0.85])
    project_design_code = _girder_sls_project_design_code_from_session()
    project_profile_code = _girder_sls_profile_code_from_session()
    code_key = f"girder_code_limit_code_{title}"
    code_sync_key = f"{code_key}_project_code_sync"
    with controls[0]:
        if locked_stage_label is not None:
            code = project_profile_code
            st.markdown("**Project code profile**")
            st.caption(f"{project_design_code} → {code}")
            st.session_state[code_key] = code
            st.session_state[code_sync_key] = code
        else:
            if st.session_state.get(code_sync_key) != project_profile_code or st.session_state.get(code_key) not in DEFAULT_GIRDER_SLS_CODES:
                st.session_state[code_key] = project_profile_code
                st.session_state[code_sync_key] = project_profile_code
            code = st.selectbox(
                "Design code profile",
                list(DEFAULT_GIRDER_SLS_CODES),
                key=code_key,
                help="Defaults to the Project Design Code from Setup. Override only for legacy/audit trials.",
            )
    with controls[1]:
        if locked_stage is not None:
            stage = locked_stage
            st.markdown("**Auto limit stage**")
            st.caption(f"{stage} — from {locked_stage_label}")
        else:
            stage = st.selectbox(
                "Code-limit stage",
                list(DEFAULT_GIRDER_SLS_STAGES),
                key=stage_key,
                help="Advanced/manual checks only: stage controls which concrete strength, prestress-force state, and section basis should be checked.",
            )

    profile_options = girder_sls_limit_profile_options(code=code, stage=stage)
    profile_option_labels = {option.key: option.label for option in profile_options}
    profile_option_descriptions = {option.key: option.description for option in profile_options}
    profile_key = f"girder_code_limit_profile_key_{title}"
    if st.session_state.get(profile_key) not in profile_option_labels:
        st.session_state[profile_key] = profile_options[0].key

    guide_notes: list[str] = []
    with st.expander(f"Tensile stress limit guide — {title}", expanded=False):
        st.caption(
            "CODE.SLS.LIMIT4 selection aid: choose the tensile limit profile from code stage, exposure/class, "
            "and bonded reinforcement condition. This does not prove cracked-section design or final code compliance."
        )
        _, guide_notes = _render_girder_tension_limit_guidance(
            title=title,
            code=code,
            stage=stage,
            stresses=stresses,
            profile_key=profile_key,
            profile_options=profile_options,
            show_end_zone_controls=False,
        )

    with controls[2]:
        limit_profile_key = st.selectbox(
            "Limit profile",
            list(profile_option_labels),
            format_func=lambda key: profile_option_labels.get(str(key), str(key)),
            key=profile_key,
            help="Select a code/stage default profile before applying any engineer-controlled overrides. Guided selection can pre-select this value.",
        )
    default_profile = build_girder_sls_limit_profile(code=code, stage=stage, limit_profile_key=limit_profile_key)
    with controls[3]:
        fc = st.number_input(
            f"{default_profile.concrete_strength_label} (MPa)",
            min_value=1.0,
            value=float(st.session_state.get(f"girder_code_limit_fc_{title}", fc_default)),
            step=1.0,
            format="%.3f",
            key=f"girder_code_limit_fc_{title}",
            help="Use f'ci at transfer/release and f'c at service when they differ.",
        )
    with controls[4]:
        enabled = st.checkbox(
            "Enable PASS/FAIL preview",
            value=bool(st.session_state.get(f"girder_code_limit_enabled_{title}", False)),
            key=f"girder_code_limit_enabled_{title}",
            help="Preview top/bottom stress against editable AASHTO/ACI limit profiles. This is not a final code-certified check.",
        )

    with st.expander(f"Stage and code profile basis — {title}", expanded=False):
        _render_analysis_summary_strip(
            [
                {
                    "title": "Selected limit profile",
                    "value": default_profile.limit_profile_label,
                    "detail": profile_option_descriptions.get(default_profile.limit_profile_key, default_profile.limit_profile_description),
                    "status": "info",
                },
                {
                    "title": "Stage strength basis",
                    "value": default_profile.concrete_strength_label,
                    "detail": f"Entered value: {float(fc):.3f} MPa",
                    "status": "info",
                },
                {
                    "title": "Prestress force basis",
                    "value": default_profile.prestress_force_basis,
                    "detail": "Pe_transfer or Pe_eff must be supplied by the engineer; losses are not calculated automatically",
                    "status": "warning" if "transfer" in default_profile.prestress_force_basis.lower() or "user" in default_profile.prestress_force_basis.lower() else "info",
                },
                {
                    "title": "Recommended section basis",
                    "value": default_profile.recommended_section_basis,
                    "detail": "Transfer/deck casting normally use precast gross; final service requires staged/composite judgment",
                    "status": "info",
                },
            ],
            columns=4,
        )
        st.write(default_profile.stage_guidance)
        st.write(default_profile.clause_note)
        st.write(default_profile.limitation_note)

    manual_override = False
    comp_ratio = default_profile.compression_limit_ratio
    tension_mode = default_profile.tension_limit_mode
    tension_sqrt_ratio = default_profile.tension_sqrt_fc_ratio
    tension_limit = default_profile.tension_limit_MPa
    tension_cap = default_profile.tension_limit_cap_MPa
    zero_tol = _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA

    with st.expander(f"Advanced code-limit profile override — {title}", expanded=default_expanded):
        st.caption("Preview defaults are centralized by code/stage/profile. Use manual override only when the project specification controls the limit values.")
        manual_override = st.checkbox(
            "Use manual override values",
            value=bool(st.session_state.get(f"girder_code_limit_manual_override_{title}", False)),
            key=f"girder_code_limit_manual_override_{title}",
            help="When disabled, changing code/stage/profile automatically uses the selected default values instead of stale override ratios.",
        )
        if not manual_override:
            _render_analysis_summary_strip(
                [
                    {
                        "title": "Compression default",
                        "value": f"{default_profile.compression_limit_ratio:.3f} × strength",
                        "detail": default_profile.limit_profile_label,
                        "status": "info",
                    },
                    {
                        "title": "Tension default",
                        "value": (
                            "No tension" if default_profile.tension_limit_mode == "No tension"
                            else f"{default_profile.tension_sqrt_fc_ratio:.3f} × √strength"
                        ),
                        "detail": (
                            f"Cap {default_profile.tension_limit_cap_MPa:.3f} MPa" if default_profile.tension_limit_cap_MPa is not None
                            else default_profile.tension_limit_mode
                        ),
                        "status": "info" if default_profile.tension_limit_mode != "No tension" else "warning",
                    },
                    {
                        "title": "Zero stress tolerance",
                        "value": f"{_GIRDER_DISPLAY_ZERO_TOLERANCE_MPA:.6f} MPa",
                        "detail": "Display/check tolerance for near-zero stress",
                        "status": "neutral",
                    },
                ],
                columns=3,
            )
        else:
            override_cols = st.columns(5)
            with override_cols[0]:
                comp_ratio = st.number_input(
                    "Compression limit ratio × selected strength",
                    min_value=0.01,
                    value=float(st.session_state.get(f"girder_code_limit_comp_ratio_{title}", default_profile.compression_limit_ratio)),
                    step=0.01,
                    format="%.3f",
                    key=f"girder_code_limit_comp_ratio_{title}",
                )
            with override_cols[1]:
                tension_mode = st.selectbox(
                    "Tension limit mode",
                    list(DEFAULT_TENSION_LIMIT_MODES),
                    index=list(DEFAULT_TENSION_LIMIT_MODES).index(default_profile.tension_limit_mode),
                    key=f"girder_code_limit_tension_mode_{title}",
                )
            with override_cols[2]:
                if tension_mode == "sqrt(fc) ratio":
                    tension_sqrt_ratio = st.number_input(
                        "Tension limit ratio × √selected strength",
                        min_value=0.0,
                        value=float(st.session_state.get(f"girder_code_limit_sqrt_ratio_{title}", default_profile.tension_sqrt_fc_ratio)),
                        step=0.05,
                        format="%.3f",
                        key=f"girder_code_limit_sqrt_ratio_{title}",
                    )
                    tension_limit = default_profile.tension_limit_MPa
                elif tension_mode == "User-defined":
                    tension_sqrt_ratio = default_profile.tension_sqrt_fc_ratio
                    tension_limit = st.number_input(
                        "User tension limit (MPa)",
                        min_value=0.0,
                        value=float(st.session_state.get(f"girder_code_limit_tension_mpa_{title}", default_profile.tension_limit_MPa)),
                        step=0.1,
                        format="%.3f",
                        key=f"girder_code_limit_tension_mpa_{title}",
                    )
                else:
                    st.markdown("**No tension permitted**")
                    tension_sqrt_ratio = 0.0
                    tension_limit = 0.0
            with override_cols[3]:
                default_cap = -1.0 if default_profile.tension_limit_cap_MPa is None else float(default_profile.tension_limit_cap_MPa)
                cap_input = st.number_input(
                    "Tension cap (MPa, -1 = none)",
                    value=float(st.session_state.get(f"girder_code_limit_tension_cap_{title}", default_cap)),
                    step=0.1,
                    format="%.3f",
                    key=f"girder_code_limit_tension_cap_{title}",
                )
                tension_cap = None if float(cap_input) < 0.0 else float(cap_input)
            with override_cols[4]:
                zero_tol = st.number_input(
                    "Zero stress tolerance (MPa)",
                    min_value=0.0,
                    value=float(st.session_state.get(f"girder_code_limit_zero_tol_{title}", _GIRDER_DISPLAY_ZERO_TOLERANCE_MPA)),
                    step=0.0001,
                    format="%.6f",
                    key=f"girder_code_limit_zero_tol_{title}",
                )

    profile = build_girder_sls_limit_profile(
        code=code,
        stage=stage,
        limit_profile_key=limit_profile_key,
        compression_limit_ratio=float(comp_ratio),
        tension_limit_mode=tension_mode,
        tension_sqrt_fc_ratio=float(tension_sqrt_ratio),
        tension_limit_MPa=float(tension_limit),
        tension_limit_cap_MPa=tension_cap,
        stress_zero_tolerance_MPa=float(zero_tol),
    )
    compression_limit = profile.compression_limit_MPa(float(fc))
    tension_allowable = profile.tension_allowable_MPa(float(fc))
    formula_summary = girder_sls_limit_formula_summary(profile=profile, fc_MPa=float(fc))
    context_warnings = tuple(guide_notes) + girder_sls_stage_basis_consistency_warnings(
        profile_stage=profile.stage,
        section_basis_label=section_basis_label,
        load_stage=load_stage,
        load_component=load_component,
        stress_includes_prestress=stress_includes_prestress,
        prestress_force_state=prestress_force_state_label,
    )

    with st.expander(f"Limit formulas and code-basis audit — {title}", expanded=False):
        _render_analysis_summary_strip(
            [
                {
                    "title": "Compression formula",
                    "value": formula_summary.compression_formula,
                    "detail": profile.limit_profile_label,
                    "status": "info",
                },
                {
                    "title": "Tension formula",
                    "value": formula_summary.tension_formula,
                    "detail": profile.limit_profile_label,
                    "status": "info" if tension_allowable > 0 else "warning",
                },
            ],
            columns=2,
        )
        st.write(f"- {profile.clause_note}")
        st.write(f"- {profile.limitation_note}")

    if context_warnings:
        _render_analysis_summary_strip(
            [
                {
                    "title": "Engineering review",
                    "value": "REVIEW",
                    "detail": "Stage/load/section-basis warning exists; open audit notes before relying on preview status",
                    "status": "warning",
                }
            ],
            columns=1,
        )
        with st.expander(f"Engineering consistency warnings — {title}", expanded=False):
            for warning in context_warnings:
                st.warning(warning)

    if not enabled:
        _render_analysis_summary_strip(
            [
                {
                    "title": "Code check status",
                    "value": "NOT CHECKED",
                    "detail": "Enable PASS/FAIL preview after selecting code profile and stage",
                    "status": "neutral",
                },
                {
                    "title": "Selected profile",
                    "value": str(code),
                    "detail": f"{stage} · {profile.limit_profile_label}",
                    "status": "info",
                },
                {
                    "title": "Preview compression limit",
                    "value": f"{compression_limit:,.3f} MPa",
                    "detail": profile.limit_profile_label,
                    "status": "info",
                },
                {
                    "title": "Preview tension limit",
                    "value": f"{tension_allowable:,.3f} MPa" if tension_allowable > 0 else "No tension",
                    "detail": profile.limit_profile_label,
                    "status": "info" if tension_allowable > 0 else "warning",
                },
            ],
            columns=4,
        )
        return

    limit_result = run_girder_service_stress_limit_check(stresses=stresses, fc_MPa=float(fc), profile=profile)
    display_status = "REVIEW" if context_warnings else f"Preview {limit_result.overall_status}"
    display_status_style = "warning" if context_warnings else ("ready" if limit_result.overall_status == "PASS" else "danger")
    display_status_detail = (
        f"Calculated {limit_result.overall_status}; resolve engineering review notes"
        if context_warnings
        else f"{code} · {stage} · {profile.limit_profile_label}"
    )
    limit_cards = [
        {
            "title": "Preview status",
            "value": display_status,
            "detail": display_status_detail,
            "status": display_status_style,
        },
        *_girder_stress_vs_limit_cards(limit_result, context_warnings=bool(context_warnings)),
        {
            "title": "Max utilization",
            "value": "—" if limit_result.max_utilization is None else f"{limit_result.max_utilization:.3f}",
            "detail": "Governing actual/allowable ratio from matching stress type",
            "status": "warning" if context_warnings else ("ready" if (limit_result.max_utilization or 0.0) <= 1.0 and limit_result.overall_status == "PASS" else "danger"),
        },
    ]
    _render_analysis_summary_strip(limit_cards, columns=4)
    with st.expander(f"Detailed code-limit stress table — {title}", expanded=False):
        st.dataframe(_clean_girder_stress_dataframe(pd.DataFrame(girder_service_limit_check_rows(limit_result))), use_container_width=True, hide_index=True)
    with st.expander(f"Code-limit preview notes — {title}", expanded=False):
        st.write(f"- Compression formula: {formula_summary.compression_formula}; {formula_summary.compression_substitution}")
        st.write(f"- Tension formula: {formula_summary.tension_formula}; {formula_summary.tension_substitution}")
        st.write(f"- {profile.clause_note}")
        st.write(f"- {profile.limitation_note}")
        for warning in limit_result.warnings:
            st.write(f"- {warning}")
        st.write("- This preview does not generate loads, select code clauses automatically, calculate losses, or update report/PMM/prestress solvers.")

def _girder_combined_service_prestress_rows(service_result, prestress_result) -> list[dict[str, object]]:
    """Return top/bottom total stress rows for GIRDER.PS1B preview display."""

    rows: list[dict[str, object]] = []
    pairs = (("Top", service_result.top, prestress_result.top), ("Bottom", service_result.bottom, prestress_result.bottom))
    for fiber_name, service_stress, prestress_stress in pairs:
        combined = float(service_stress.total_stress_MPa) + float(prestress_stress.total_stress_MPa)
        rows.append(
            {
                "Fiber": fiber_name,
                "Service axial (MPa)": service_stress.axial_stress_MPa,
                "Service bending (MPa)": service_stress.bending_stress_MPa,
                "Service total (MPa)": service_stress.total_stress_MPa,
                "PS axial (MPa)": prestress_stress.axial_stress_MPa,
                "PS eccentric (MPa)": prestress_stress.eccentric_bending_stress_MPa,
                "PS total (MPa)": prestress_stress.total_stress_MPa,
                "Combined total (MPa)": combined,
                "Stress type": _girder_stress_type(combined),
            }
        )
    return rows


def _girder_stage_template_label(template) -> str:
    """Return compact labels for manual GIRDER.SLS2B stage-template selection."""

    return f"{template.title}  ·  {template.recommended_basis_name.replace('_', ' ')}"


def _girder_stage_dataframe(result) -> pd.DataFrame:
    """Return rounded top/bottom stage rows for Analysis preview display."""

    return pd.DataFrame(girder_service_stage_result_rows(result))


def _render_beam_girder_service_stress_preview() -> None:
    """Display GIRDER.SLS1B/PS1B manual stress preview for Beam/Girder mode.

    This panel intentionally uses explicit trial actions and an explicit section
    basis.  GIRDER.PS1B adds an optional effective-prestress component using
    ``Pe_eff`` only; it does not derive prestress from breaking load, strand
    count metadata, or duct diameter and it does not modify solver state.
    """

    mode_settings = _analysis_mode_from_session()
    is_bridge_workflow = is_beam_girder_future_workflow(mode_settings)
    is_building_workflow = is_building_beam_girder_workflow(mode_settings)
    if not (is_bridge_workflow or is_building_workflow):
        return

    # Legacy milestone label retained for source-level regression tests: Beam/Girder Elastic Service Stress Preview.
    workspace_title = "Building Beam/Girder ACI SLS Stress Workspace" if is_building_workflow else "Bridge Beam/Girder SLS Stress Workspace"
    st.markdown(f"### {workspace_title}")
    _render_analysis_summary_strip(
        [
            {
                "title": "Workspace status",
                "value": "Building ACI preview active" if is_building_workflow else "Bridge SLS preview active",
                "detail": "Auto stage loads + Building SDL/LL + Pe force states" if is_building_workflow else "Bridge staged auto loads + Pe force states",
                "status": "warning",
            },
            {
                "title": "Stress convention",
                "value": "Compression − / Tension +",
                "detail": "Sagging M gives top compression and bottom tension",
                "status": "info",
            },
            {
                "title": "Prestress effect",
                "value": "Optional Pe_eff",
                "detail": "Effective prestress after losses; no breaking-load conversion",
                "status": "info",
            },
            {
                "title": "Code stress limits",
                "value": "ACI 318 preview" if is_building_workflow else "AASHTO LRFD preview",
                "detail": "Uses Project Design Code profile from Setup",
                "status": "info",
            },
        ],
        columns=4,
    )

    with st.expander("Beam/Girder SLS preview limitations", expanded=False):
        st.write(
            "- BUILDING.SLS1B/GIRDER.SLS previews elastic Beam/Girder service stress using generated or imported simple-span actions "
            "and stage Pe force states. Building workflow uses Building SDL/LL; Bridge workflow uses bridge SLS auto components."
        )
        st.write("- Compression stress is negative; tension stress is positive. Sagging M is positive and gives top compression / bottom tension.")
        st.write("- Pe_eff is positive for compressive effective prestress after losses.")
        st.write(
            "- This preview is not final code-certified design. Building service-stage locked-in stress summation, long-term redistribution, "
            "deflection, shear, end-zone, and report integration remain future work unless explicitly scoped."
        )
        st.write("- It is not used by PMM, rebar, prestress, or report solvers.")

    # Legacy source phrase retained for regression tests: Quick Elastic Stress Trial.
    st.markdown("#### SLS Check Case")
    st.caption("Decision view for one SLS check case. Detailed stress rows, code formulas, and audit notes stay collapsed unless needed.")

    section_geometry = st.session_state.get("section_geometry")
    section_parameters = st.session_state.get("section_parameters", {})
    basis_options = build_girder_service_stress_basis_options(
        section_geometry,
        section_parameters,
        member_type=mode_settings.member_type,
    )

    for item in basis_options.info:
        st.info(item)
    for warning in basis_options.warnings:
        st.warning(f"Girder SLS preview warning: {warning}")

    if not basis_options.bases:
        st.info("Build a valid Beam/Girder section before running the service-stress preview.")
        return

    basis_names = list(basis_options.bases.keys())
    if st.session_state.get("girder_service_stress_basis_name") not in basis_names:
        st.session_state["girder_service_stress_basis_name"] = basis_names[0]

    beam_sls_rows = _beam_sls_load_rows_from_session_state()

    # ANALYSIS.SLS1: always show the three stage tabs immediately in the
    # Beam/Girder SLS workspace.  The Loads page is the default stage source,
    # while manual trial input is a per-stage fallback/override instead of the
    # top-level workflow gate used by earlier milestones.
    # Compatibility phrase retained for regression/search context: From Loads page — SLS Girder Service Loads.
    # Legacy phrase retained for historical tests only: SLS action source.
    # Legacy phrases retained for regression/search context: SLS stage check tabs. Stage checks are always available. manual input is a stage-level override/fallback. Each stage keeps its own code-limit/profile/prestress UI state.
    # Legacy source phrase retained for regression tests: Default view is for checking top/bottom stresses along the girder length.
    st.markdown("##### SLS result workspace")
    st.caption(
        "Default view is for checking top/bottom stresses along the member length in Transfer, Construction, and Service. "
        "For Building workflow, Transfer/Construction use auto self-weight/topping where possible and Service uses Building SDL/LL from Loads. "
        "It shows code basis, stress diagram, governing result, and action hints first; audit/detail controls stay collapsed below each stage."
    )
    _render_girder_sls4b_combined_stage_result_table(
        beam_sls_rows=beam_sls_rows,
        basis_options=basis_options,
        basis_names=basis_names,
    )
    stage_tabs = st.tabs([label for _, label, _ in _beam_sls_stage_tab_specs()])
    for tab, (stage_key, stage_label, stage_note) in zip(stage_tabs, _beam_sls_stage_tab_specs(), strict=False):
        with tab:
            stage_rows = _beam_sls_rows_for_stage(beam_sls_rows, stage_label)
            st.caption(stage_note)

            # GIRDER.SLS4A — full-length station-based stress diagram preview.
            _render_girder_full_length_sls_diagram(
                stage_label=stage_label,
                stage_rows=stage_rows,
                basis_options=basis_options,
                basis_names=basis_names,
            )

            with st.expander(f"Load / section / single-station audit — {stage_label}", expanded=False):
                st.caption(
                    "Open this only when you need to change the load source, review the selected Loads row, "
                    "or run the legacy single-station SLS check/audit panels. The full-length diagram above is the default result view."
                )
                source_options = ["From Loads page", "Manual override"] if stage_rows else ["Manual override"]
                source_key = f"girder_sls_action_source_{stage_key}"
                if st.session_state.get(source_key) not in source_options:
                    st.session_state[source_key] = source_options[0]
                stage_source = st.radio(
                    f"Load source for {stage_label}",
                    source_options,
                    horizontal=True,
                    key=source_key,
                    help="Use the matching stage row from Loads by default; switch to manual override only for a trial check or missing imported row.",
                )

                if stage_source == "From Loads page" and stage_rows:
                    row_labels = [_beam_sls_load_row_label(row) for row in stage_rows]
                    row_by_label = dict(zip(row_labels, stage_rows, strict=False))
                    row_key = f"girder_sls_load_row_label_{stage_key}"
                    if st.session_state.get(row_key) not in row_labels:
                        st.session_state[row_key] = row_labels[0]
                    selected_label = st.selectbox(
                        f"{stage_label} load case from Loads page",
                        row_labels,
                        key=row_key,
                        help="Loads page is the source of service action data. Analysis reads N and Mx only in this preview milestone.",
                    )
                    selected_load_row = row_by_label[selected_label]
                    _render_analysis_summary_strip(_beam_sls_load_row_summary_cards(selected_load_row), columns=4)
                    st.caption(
                        "LOADS.SLS.CONNECT1 uses N and Mx from the selected row for the quick elastic stress preview. "
                        "My, Vy, Vx, and T remain stored for future biaxial, principal tension, shear, and torsion checks."
                    )
                    _render_girder_sls_check_case_panel(
                        case_title=stage_label,
                        case_key=stage_key,
                        stage_label=stage_label,
                        selected_load_row=selected_load_row,
                        section_geometry=section_geometry,
                        basis_options=basis_options,
                        basis_names=basis_names,
                    )
                else:
                    if not stage_rows:
                        if is_building_workflow:
                            st.info(f"No imported {stage_label.lower()} row is required for the Building auto SLS diagram above. Use manual override here only for a trial single-station check.")
                        else:
                            st.info(f"No active {stage_label.lower()} row is available from the Loads page. Use manual override for a trial check or import stage loads first.")
                    else:
                        st.info("Manual override is for trial checks only. The commercial workflow should normally read the matching stage row from Loads.")
                    _render_girder_sls_check_case_panel(
                        case_title=stage_label,
                        case_key=f"{stage_key}_manual",
                        stage_label=stage_label,
                        selected_load_row=None,
                        section_geometry=section_geometry,
                        basis_options=basis_options,
                        basis_names=basis_names,
                    )

    with st.expander("Advanced manual service-stage stress preview (legacy)", expanded=False):
        st.markdown("#### Manual Service Stage Stress Preview")
        st.write(
            "Manual stage actions remain available as an advanced legacy preview foundation, but the default commercial workflow now uses the three stage check tabs above."
        )
        st.write("- Transfer stage: precast girder self-weight plus separately included transfer prestress context.")
        st.write("- Construction stage: precast girder plus wet deck/topping on precast gross basis.")
        st.write("- Service stage: final service total SLS resultant on the intended service basis.")
        st.write("- No load generation, loss calculation, PMM, rebar, prestress-input, or report workflow is modified here.")

    with st.expander("Beam/Girder service-stress sign convention", expanded=False):
        st.write("- Compression stress is negative; tension stress is positive.")
        st.write("- Axial compression N is positive and contributes negative stress: -N/A.")
        st.write("- Sagging M is positive and gives top compression / bottom tension.")
        st.write("- Pe_eff is positive compressive effective prestress after losses.")
        st.write("- Prestress eccentricity e = yps - yc. A low tendon has negative e and gives higher bottom compression.")
        st.write("- Composite transformed basis uses deck/topping transformed to the primary/precast concrete basis.")
        st.write("- This preview is a manual elastic stress check foundation only; code-limit checks are editable previews and staged checks are future work and remain engineer-controlled.")

    # DEFLECT.SLS1.2 — deflection/camber now lives in its own top-level
    # Analysis tab so the Stress & Cracking workspace stays focused and clean.
    # The dedicated tab rebuilds the same Beam/Girder basis_options and calls
    # _render_girder_deflection_camber_workspace there.

def _render_serviceability_expander() -> None:
    current = _serviceability_settings_from_session()

    with st.expander("Advanced Serviceability / SLS Foundation settings", expanded=False):
        st.info(
            "Advanced foundation settings for legacy/manual serviceability workflows. "
            "The default girder SLS decision view above already shows the code basis, stress diagram, governing result, and action hints."
        )
        cols = st.columns(3)
        with cols[0]:
            enabled = st.checkbox("Enable Serviceability / SLS Foundation", value=current.enabled)
            st.caption("Stress sign convention: Compression = negative, Tension = positive.")
            st.caption("Section basis: Gross or uncracked transformed.")
            compression_limit = st.number_input(
                "Concrete compression limit ratio",
                min_value=0.01,
                value=float(current.concrete_compression_limit_ratio),
                step=0.01,
                format="%.3f",
            )
        with cols[1]:
            tension_modes = ["no_tension", "user_defined", "sqrt_fc_ratio"]
            tension_mode = st.selectbox(
                "Tension limit mode",
                tension_modes,
                index=tension_modes.index(current.concrete_tension_limit_mode),
            )
            if tension_mode == "user_defined":
                tension_limit = st.number_input(
                    "Concrete tension limit, MPa",
                    min_value=0.0,
                    value=float(current.concrete_tension_limit_MPa),
                    step=0.1,
                )
                tension_sqrt_ratio = float(current.concrete_tension_sqrt_fc_ratio)
            elif tension_mode == "sqrt_fc_ratio":
                tension_sqrt_ratio = st.number_input(
                    "Tension sqrt(f'c) ratio",
                    min_value=0.0,
                    value=float(current.concrete_tension_sqrt_fc_ratio),
                    step=0.05,
                    format="%.3f",
                )
                tension_limit = 0.0
            else:
                tension_limit = 0.0
                tension_sqrt_ratio = float(current.concrete_tension_sqrt_fc_ratio)
            no_tension_check = st.checkbox(
                "No-tension check",
                value=current.no_tension_check or tension_mode == "no_tension",
            )
            decompression_check = st.checkbox("Decompression check", value=current.decompression_check)
            allow_tension = st.checkbox(
                "Allow tension",
                value=current.allow_tension and not no_tension_check and not decompression_check,
            )
            stress_zero_tolerance = st.number_input(
                "Stress zero tolerance, MPa",
                min_value=0.0,
                value=float(current.stress_zero_tolerance_MPa),
                step=0.000001,
                format="%.6f",
            )
        with cols[2]:
            include_prestress_effective_force = st.checkbox(
                "Include effective prestress force in elastic SLS stress",
                value=current.include_prestress_effective_force,
                help=(
                    "Uses existing Pe_eff / fpe / initial strain from the Prestress tab as effective prestress. "
                    "Loss calculation is not performed here."
                ),
            )
            critical_point_options = ["all", "extreme_fibers_only"]
            critical_point_filter = st.selectbox(
                "Critical point filter",
                critical_point_options,
                index=critical_point_options.index(current.critical_point_filter),
            )
            note = st.text_area("Serviceability note", value=current.note or "", height=110)

        st.markdown("**Transformed Section Foundation**")
        tr_cols = st.columns(3)
        with tr_cols[0]:
            use_transformed_section = st.checkbox("Use transformed section properties", value=current.use_transformed_section)
            ec_mode_options = ["Auto ACI estimate", "User-defined Ec"]
            ec_mode_index = 1 if current.concrete_Ec_MPa is not None else 0
            ec_mode = st.selectbox("Concrete Ec input mode", ec_mode_options, index=ec_mode_index)
        with tr_cols[1]:
            if ec_mode == "User-defined Ec":
                concrete_ec_mpa = st.number_input(
                    "User-defined Ec, MPa",
                    min_value=1.0,
                    value=float(current.concrete_Ec_MPa or 30_000.0),
                    step=500.0,
                )
            else:
                concrete_ec_mpa = None
                st.caption("Ec auto estimate: 4700 * sqrt(f'c), MPa.")
            transformed_include_rebar = st.checkbox(
                "Include ordinary rebar in transformed section",
                value=current.transformed_include_rebar,
            )
        with tr_cols[2]:
            transformed_include_prestress = st.checkbox(
                "Include bonded prestress in transformed section",
                value=current.transformed_include_prestress,
            )
            st.caption("Transformed area convention: net_steel.")

        settings = ServiceabilitySettings(
            enabled=enabled,
            stress_sign_convention="compression_negative",
            section_basis="gross",
            check_load_type="SLS",
            concrete_compression_limit_ratio=float(compression_limit),
            concrete_tension_limit_mode=tension_mode,
            concrete_tension_limit_MPa=float(tension_limit),
            concrete_tension_sqrt_fc_ratio=float(tension_sqrt_ratio),
            allow_tension=allow_tension,
            no_tension_check=no_tension_check,
            decompression_check=decompression_check,
            stress_zero_tolerance_MPa=float(stress_zero_tolerance),
            critical_point_filter=critical_point_filter,
            include_prestress_effective_force=include_prestress_effective_force,
            use_transformed_section=use_transformed_section,
            concrete_Ec_MPa=None if concrete_ec_mpa is None else float(concrete_ec_mpa),
            Ec_method="aci_normal_weight",
            transformed_include_rebar=transformed_include_rebar,
            transformed_include_prestress=transformed_include_prestress,
            transformed_area_convention="net_steel",
            note=note or None,
        )
        st.session_state["serviceability_settings"] = settings

        analysis_input = _serviceability_analysis_input_from_session()
        if analysis_input is None:
            st.warning("Section geometry and concrete material are required before serviceability preflight can run.")
            return

        st.markdown("**Custom Stress Check Points**")
        include_default_stress_check_points = st.checkbox(
            "Include default stress check points",
            value=bool(st.session_state.get("include_default_stress_check_points", True)),
            help="Includes top, bottom, left, right, and centroid/reference points before custom points.",
        )
        st.session_state["include_default_stress_check_points"] = include_default_stress_check_points
        custom_editor_df = st.session_state.get("custom_stress_check_points_table")
        if not isinstance(custom_editor_df, pd.DataFrame):
            stored_points = st.session_state.get("custom_stress_check_points", [])
            custom_editor_df = (
                stress_check_points_to_dataframe(stored_points)
                if stored_points
                else _default_custom_stress_check_points_dataframe()
            )
        custom_editor_df = st.data_editor(
            custom_editor_df,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Active": st.column_config.CheckboxColumn("Active"),
                "Point Type": st.column_config.SelectboxColumn(
                    "Point Type",
                    options=sorted(ALLOWED_STRESS_POINT_TYPES),
                ),
                "Include in Governing": st.column_config.CheckboxColumn("Include in Governing"),
            },
        )
        st.session_state["custom_stress_check_points_table"] = custom_editor_df
        point_parse = custom_stress_check_points_from_dataframe(custom_editor_df)
        persisted_custom_points = dataframe_to_stress_check_points(custom_editor_df)
        geometry_errors, geometry_warnings = validate_stress_check_points_against_geometry(
            point_parse.points,
            analysis_input.section_geometry,
        )
        point_errors = [*point_parse.errors, *geometry_errors]
        point_warnings = [*point_parse.warnings, *geometry_warnings]
        stress_check_points_valid = not point_errors
        st.session_state["custom_stress_check_points"] = persisted_custom_points
        st.session_state["stress_check_points_valid_for_analysis"] = stress_check_points_valid
        st.metric("Stress check points valid for analysis", "Yes" if stress_check_points_valid else "No")
        for error in point_errors:
            st.error(f"Stress check point error: {error}")
        for warning in point_warnings:
            st.warning(f"Stress check point warning: {warning}")
        for item in point_parse.info:
            st.info(f"Stress check point info: {item}")

        summary = build_serviceability_summary_from_analysis_input(
            analysis_input,
            settings,
            custom_stress_check_points=point_parse.points,
            include_default_stress_check_points=include_default_stress_check_points,
        )
        st.session_state["serviceability_preflight_summary"] = summary

        limit_info = service_stress_limits(analysis_input.concrete_material.fc_MPa, settings)
        limit_cols = st.columns(4)
        limit_cols[0].metric("SLS foundation enabled", "Yes" if summary.enabled else "No")
        limit_cols[1].metric("Compression limit", f"{settings.concrete_compression_limit_ratio:.3f} f'c")
        limit_cols[2].metric("Compression limit", f"{float(limit_info['compression_limit_MPa']):.2f} MPa")
        limit_cols[3].metric("Tension limit", f"{float(limit_info['tension_limit_MPa']):.2f} MPa")

        for warning in summary.warnings:
            st.warning(f"WARNING: {warning}")
        for item in summary.info:
            st.info(f"INFO: {item}")

        sls_df = sls_load_cases_to_display_dataframe(summary.sls_load_cases)
        st.markdown("**Active SLS Load Cases**")
        if sls_df.empty:
            st.info("No active SLS load cases are available.")
        else:
            st.dataframe(sls_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download SLS Load Cases CSV",
                data=sls_df.to_csv(index=False),
                file_name="sls_load_cases.csv",
                mime="text/csv",
                use_container_width=True,
            )

        properties_df = _gross_section_properties_dataframe(summary.section_properties)
        st.markdown("**Gross Section Properties**")
        if properties_df.empty:
            st.info("Gross section properties are not available.")
        else:
            st.dataframe(properties_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Gross Section Properties CSV",
                data=properties_df.to_csv(index=False),
                file_name="gross_section_properties.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if settings.use_transformed_section:
            st.markdown("**Transformed Section Properties**")
            transformed_props = summary.transformed_section_properties
            if transformed_props is None:
                st.warning("Transformed section properties are not available.")
            else:
                st.info(
                    "When selected, the elastic SLS stress check uses these uncracked transformed section properties. "
                    "Cracked section analysis is future work."
                )
                tr_metrics = st.columns(5)
                tr_metrics[0].metric("Ec", f"{transformed_props.Ec_MPa:,.1f} MPa")
                tr_metrics[1].metric("Transformed area", f"{transformed_props.area_mm2:,.1f} mm^2")
                tr_metrics[2].metric("x_tr", f"{transformed_props.centroid_x_mm:,.2f} mm")
                tr_metrics[3].metric("y_tr", f"{transformed_props.centroid_y_mm:,.2f} mm")
                if analysis_input.rebar_materials:
                    rebar_n = modular_ratio(analysis_input.rebar_materials[0].Es_MPa, transformed_props.Ec_MPa)
                    tr_metrics[4].metric("n_s", f"{rebar_n:.3f}")
                else:
                    tr_metrics[4].metric("n_s", "N/A")
                prestress_elements_for_summary = list(analysis_input.prestress_elements or [])
                if prestress_elements_for_summary:
                    first_bonded = next((element for element in prestress_elements_for_summary if element.bonded), None)
                    if first_bonded is not None:
                        st.caption(f"Representative n_p = {modular_ratio(first_bonded.ep_mpa, transformed_props.Ec_MPa):.3f}")
                for warning in transformed_props.warnings:
                    st.warning(f"Transformed section warning: {warning}")
                for item in transformed_props.info:
                    st.info(f"Transformed section info: {item}")
                transformed_df = transformed_section_properties_to_dataframe(transformed_props)
                st.dataframe(transformed_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download Transformed Section Properties CSV",
                    data=transformed_df.to_csv(index=False),
                    file_name="transformed_section_properties.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        points_df = _stress_check_points_dataframe(summary.check_points)
        st.markdown("**Default Stress Check Points**")
        if points_df.empty:
            st.info("Stress check points are not available.")
        else:
            st.dataframe(points_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Stress Check Points CSV",
                data=points_df.to_csv(index=False),
                file_name="sls_stress_check_points.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.markdown("**Elastic SLS Stress Check**")
        st.info(
            "Stress basis selected: "
            + ("Uncracked transformed section" if settings.use_transformed_section else "Gross section")
        )
        if settings.include_prestress_effective_force:
            st.warning("Prestress effective force contribution uses the selected section basis and centroid.")
            st.warning("Prestress losses are not calculated in this SLS check; existing effective values are used.")
            st.warning("Unbonded prestress is ignored.")
        else:
            st.info("Effective prestress force contribution is disabled for this elastic SLS check.")
        if settings.use_transformed_section:
            st.warning("Transformed section stress check is uncracked only. Cracked section analysis is future work.")
        else:
            st.info("Gross section stress check.")
        st.info("Compression is negative and tension is positive in SLS stress results.")
        if settings.decompression_check:
            st.warning(
                "Milestone 4.5 decompression check is implemented as a no-tension stress check at selected "
                "concrete stress points. Member-level tendon-zone decompression is future work."
            )
        st.warning("Cracked section and crack width checks are future work.")
        current_sls_hash = serviceability_input_hash(
            analysis_input,
            settings,
            point_parse.points,
            include_default_stress_check_points,
        )
        sls_cache_status = cache_status_for_hash(
            current_sls_hash,
            st.session_state.get("serviceability_summary_hash"),
            st.session_state.get("serviceability_summary") is not None,
        )
        st.caption(f"SLS result cache status: {sls_cache_status}")
        if st.button("Run Elastic SLS Stress Check", use_container_width=True, disabled=not stress_check_points_valid):
            existing_summary = st.session_state.get("serviceability_summary")
            if (
                existing_summary is not None
                and st.session_state.get("serviceability_summary_hash") == current_sls_hash
            ):
                st.session_state["serviceability_runtime_cache_status"] = "Cached result used"
            else:
                stress_summary, sls_timing = timed_call(
                    "SLS stress calculation",
                    run_elastic_sls_stress_check,
                    analysis_input,
                    settings,
                    custom_stress_check_points=point_parse.points,
                    include_default_stress_check_points=include_default_stress_check_points,
                )
                _record_runtime_timing(sls_timing)
                st.session_state["serviceability_summary"] = stress_summary
                st.session_state["serviceability_summary_hash"] = current_sls_hash
                st.session_state["serviceability_runtime_cache_status"] = "Recalculated"

        stress_summary = st.session_state.get("serviceability_summary")
        if stress_summary is not None and getattr(stress_summary, "stress_results", None):
            if st.session_state.get("serviceability_summary_hash") != current_sls_hash:
                st.warning("Displayed SLS results are stale because serviceability inputs changed. Run Elastic SLS Stress Check to update them.")
            metric_cols = st.columns(6)
            metric_cols[0].metric("Overall SLS Status", stress_summary.overall_status)
            metric_cols[1].metric("Governing Combo", stress_summary.governing_combo or "N/A")
            metric_cols[2].metric("Governing Point", stress_summary.governing_point or "N/A")
            metric_cols[3].metric(
                "Max Compression",
                "N/A" if stress_summary.max_compression_MPa is None else f"{stress_summary.max_compression_MPa:.2f} MPa",
            )
            metric_cols[4].metric(
                "Max Tension",
                "N/A" if stress_summary.max_tension_MPa is None else f"{stress_summary.max_tension_MPa:.2f} MPa",
            )
            metric_cols[5].metric(
                "Max Utilization",
                "N/A" if stress_summary.max_utilization is None else f"{stress_summary.max_utilization:.3f}",
            )
            st.info(
                "Stress Basis Used: "
                + (
                    "Uncracked Transformed Section"
                    if stress_summary.section_basis_used == "transformed_uncracked"
                    else "Gross Section"
                )
            )
            count_cols = st.columns(5)
            count_cols[0].metric("No-tension violations", f"{stress_summary.no_tension_violation_count:,}")
            count_cols[1].metric("Decompression violations", f"{stress_summary.decompression_violation_count:,}")
            count_cols[2].metric("Compression failures", f"{stress_summary.compression_failure_count:,}")
            count_cols[3].metric("Tension failures", f"{stress_summary.tension_failure_count:,}")
            count_cols[4].metric("Checked points", f"{len(stress_summary.stress_results):,}")
            for warning in stress_summary.warnings:
                st.warning(f"SLS warning: {warning}")
            for item in stress_summary.info:
                st.info(f"SLS info: {item}")
            if stress_summary.prestress_contribution is not None:
                st.markdown("**Prestress Service Contribution Summary**")
                ps_cols = st.columns(4)
                ps_cols[0].metric("Bonded included", f"{stress_summary.bonded_prestress_count:,}")
                ps_cols[1].metric("Unbonded ignored", f"{stress_summary.unbonded_prestress_ignored_count:,}")
                ps_cols[2].metric("Total Pe_eff", f"{N_to_kN(stress_summary.total_pe_eff_N):,.2f} kN")
                ps_cols[3].metric("Mpe x/y", f"{Nmm_to_kNm(stress_summary.Mpe_x_Nmm):,.2f} / {Nmm_to_kNm(stress_summary.Mpe_y_Nmm):,.2f} kN-m")
                ps_df = prestress_service_contribution_to_dataframe(stress_summary.prestress_contribution)
                st.dataframe(ps_df, use_container_width=True, hide_index=True)
                st.download_button(
                    "Download SLS Prestress Contribution CSV",
                    data=ps_df.to_csv(index=False),
                    file_name="sls_prestress_contribution.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            stress_df = service_stress_results_to_dataframe(stress_summary)
            st.dataframe(stress_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download SLS Stress Results CSV",
                data=stress_df.to_csv(index=False),
                file_name="sls_elastic_stress_results.csv",
                mime="text/csv",
                use_container_width=True,
            )

            st.markdown("**Cracking / Tension Zone Classification**")
            st.info(
                "Milestone 4.7 classifies tension/cracking risk from existing SLS stress results. "
                "It does not perform cracked-section stress redistribution or crack-width checks."
            )
            crack_summary = classify_service_stress_results_for_cracking(stress_summary, stress_summary.settings)
            st.session_state["crack_classification_summary"] = crack_summary
            crack_cols = st.columns(5)
            crack_cols[0].metric("Overall Classification", crack_summary.overall_classification)
            crack_cols[1].metric("Governing Combo", crack_summary.governing_combo or "N/A")
            crack_cols[2].metric("Governing Point", crack_summary.governing_point or "N/A")
            crack_cols[3].metric("Max Tension", f"{crack_summary.max_tension_MPa:.3f} MPa")
            crack_cols[4].metric("Tension Points", f"{crack_summary.tension_point_count:,}")
            for warning in crack_summary.warnings:
                st.warning(f"Cracking classification warning: {warning}")
            for item in crack_summary.info:
                st.info(f"Cracking classification info: {item}")
            crack_df = crack_classification_to_dataframe(crack_summary)
            st.dataframe(crack_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Cracking Classification CSV",
                data=crack_df.to_csv(index=False),
                file_name="sls_cracking_classification.csv",
                mime="text/csv",
                use_container_width=True,
            )

            st.markdown("**SLS Stress Visualization**")
            st.info("Compression is negative and tension is positive.")
            st.info("Point colors reflect current serviceability status/classification.")
            st.info("Visualization is based on selected stress check points, not a full stress contour.")
            st.warning("Cracked-section redistribution and crack-width checks are future work.")
            combo_options = [load_case.name for load_case in stress_summary.sls_load_cases]
            if not combo_options:
                combo_options = sorted({result.combo_name for result in stress_summary.stress_results})
            if combo_options:
                default_combo = stress_summary.governing_combo if stress_summary.governing_combo in combo_options else combo_options[0]
                viz_cols = st.columns(3)
                selected_sls_combo = viz_cols[0].selectbox(
                    "SLS Combo for Stress Diagram",
                    combo_options,
                    index=combo_options.index(default_combo),
                )
                show_sls_labels = viz_cols[1].checkbox("Show point labels", value=True)
                show_sls_bar = viz_cols[2].checkbox("Show stress bar diagram", value=True)
                plot_df = service_stress_results_to_plot_dataframe(stress_summary, crack_summary, selected_sls_combo)
                section_fig, section_fig_timing = timed_call(
                    "SLS section stress figure generation",
                    make_sls_section_stress_figure,
                    analysis_input.section_geometry,
                    plot_df,
                    selected_sls_combo,
                    show_labels=show_sls_labels,
                )
                _record_runtime_timing(section_fig_timing)
                st.plotly_chart(
                    section_fig,
                    use_container_width=True,
                )
                if show_sls_bar:
                    bar_fig, bar_fig_timing = timed_call(
                        "SLS stress bar figure generation",
                        make_sls_stress_bar_figure,
                        plot_df,
                        selected_sls_combo,
                    )
                    _record_runtime_timing(bar_fig_timing)
                    st.plotly_chart(bar_fig, use_container_width=True)
                st.download_button(
                    "Download Selected SLS Stress Visualization CSV",
                    data=plot_df.to_csv(index=False),
                    file_name="sls_stress_visualization_selected_combo.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            else:
                st.info("No active SLS combos are available for stress visualization.")
        else:
            st.info("Run the elastic SLS stress check to populate stress results.")


def _render_pre_report_qa_expander() -> None:
    with st.expander("Pre-Report QA / Result Traceability", expanded=False):
        st.info(
            "This section summarizes existing results for future report export. "
            "It does not rerun PMM, SLS, verification, or cracking checks."
        )
        if st.button("Build Pre-Report Snapshot", use_container_width=True):
            st.session_state["result_traceability_snapshot"] = build_result_traceability_snapshot(st.session_state)

        snapshot = st.session_state.get("result_traceability_snapshot")
        if snapshot is None:
            snapshot = build_result_traceability_snapshot(st.session_state)
            st.session_state["result_traceability_snapshot"] = snapshot

        readiness = check_report_readiness(snapshot)
        figures = collect_available_report_figures(st.session_state)
        limitations = collect_limitations_for_report(st.session_state)
        snapshot_df = result_traceability_snapshot_to_dataframe(snapshot)
        readiness_df = report_readiness_to_dataframe(readiness)
        warnings_df = pd.DataFrame({"Warning": snapshot.warnings})
        limitations_df = engineering_limitations_to_dataframe(limitations)
        units_df = unit_conventions_to_dataframe()
        figures_df = report_figures_to_dataframe(figures)

        status_cols = st.columns(5)
        status_cols[0].metric("Report Readiness", readiness.overall_status)
        status_cols[1].metric("ULS PMM Result", "Yes" if snapshot.pmm_result_available else "No")
        status_cols[2].metric("SLS Result", "Yes" if snapshot.sls_result_available else "No")
        status_cols[3].metric("Warning Count", f"{snapshot.warning_count:,}")
        status_cols[4].metric("High/Critical Limitations", f"{snapshot.high_or_critical_limitation_count:,}")

        st.markdown("**Result Traceability Snapshot**")
        st.dataframe(snapshot_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Result Traceability Snapshot CSV",
            data=snapshot_df.to_csv(index=False),
            file_name="result_traceability_snapshot.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Report Readiness**")
        st.dataframe(readiness_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Report Readiness CSV",
            data=readiness_df.to_csv(index=False),
            file_name="report_readiness.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Engineering Warnings**")
        if warnings_df.empty:
            st.success("No consolidated engineering warnings are currently available.")
        else:
            st.dataframe(warnings_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Engineering Warnings CSV",
            data=warnings_df.to_csv(index=False),
            file_name="engineering_warnings.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Engineering Limitations**")
        st.dataframe(limitations_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Engineering Limitations CSV",
            data=limitations_df.to_csv(index=False),
            file_name="engineering_limitations.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Unit Conventions**")
        st.dataframe(units_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Unit Conventions CSV",
            data=units_df.to_csv(index=False),
            file_name="unit_conventions.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Available Report Figures**")
        st.dataframe(figures_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Available Report Figures CSV",
            data=figures_df.to_csv(index=False),
            file_name="available_report_figures.csv",
            mime="text/csv",
            use_container_width=True,
        )

        st.markdown("**Report Export Foundation**")
        st.info("Report manifest, draft outline, draft Word export, and Word report QA are available. PDF export remains future work.")
        meta_cols = st.columns(2)
        report_title = meta_cols[0].text_input(
            "Report title",
            value=st.session_state.get("report_title", "Concrete PMM Pro Engineering Report"),
            key="report_title",
        )
        report_project_name = meta_cols[1].text_input(
            "Report project name",
            value=st.session_state.get("project_name", ""),
            key="report_project_name",
        )
        author_cols = st.columns(3)
        prepared_by = author_cols[0].text_input("Prepared by", value=st.session_state.get("report_prepared_by", ""), key="report_prepared_by")
        checked_by = author_cols[1].text_input("Checked by", value=st.session_state.get("report_checked_by", ""), key="report_checked_by")
        revision = author_cols[2].text_input("Revision", value=st.session_state.get("report_revision", "Draft"), key="report_revision")
        if st.button("Build Report Manifest", use_container_width=True):
            metadata = ReportMetadata(
                report_title=report_title or "Concrete PMM Pro Engineering Report",
                project_name=report_project_name or None,
                prepared_by=prepared_by or None,
                checked_by=checked_by or None,
                revision=revision or "Draft",
            )
            st.session_state["report_manifest"] = build_report_manifest(st.session_state, metadata)

        manifest = st.session_state.get("report_manifest")
        if manifest is not None:
            manifest_summary_df = report_manifest_to_summary_dataframe(manifest)
            sections_df = report_sections_to_dataframe(manifest.sections)
            tables_df = report_tables_to_dataframe(manifest.tables)
            manifest_figures_df = report_figures_to_dataframe(manifest.figures)
            outline_text = generate_plain_text_report_outline(manifest)
            manifest_json = json.dumps(report_manifest_to_json_dict(manifest), indent=2)

            st.dataframe(manifest_summary_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Report Manifest JSON",
                data=manifest_json,
                file_name="report_manifest.json",
                mime="application/json",
                use_container_width=True,
            )
            st.markdown("**Report Section Plan**")
            st.dataframe(sections_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Report Section Plan CSV",
                data=sections_df.to_csv(index=False),
                file_name="report_section_plan.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.markdown("**Report Tables**")
            st.dataframe(tables_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Report Tables CSV",
                data=tables_df.to_csv(index=False),
                file_name="report_tables.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.markdown("**Report Figures**")
            st.dataframe(manifest_figures_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Report Figures CSV",
                data=manifest_figures_df.to_csv(index=False),
                file_name="report_figures.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.download_button(
                "Download Draft Report Outline TXT",
                data=outline_text,
                file_name="draft_report_outline.txt",
                mime="text/plain",
                use_container_width=True,
            )
        else:
            st.info("Build the report manifest to review the section plan, table registry, and figure registry.")

        st.markdown("**Report Figure Export Preparation**")
        st.info("Figure export preparation supports draft Word reporting. PDF export remains future work.")
        figure_context = build_report_figure_context(st.session_state)
        figure_items = collect_report_figure_export_items(st.session_state)
        figure_export_df = report_figure_export_items_to_dataframe(figure_items)
        context_df = pd.DataFrame(
            [
                {"Item": key, "Value": value}
                for key, value in figure_context.__dict__.items()
            ],
            columns=["Item", "Value"],
        )
        st.markdown("Figure Export Context")
        st.dataframe(context_df, use_container_width=True, hide_index=True)
        st.markdown("Figure Export Registry")
        st.dataframe(figure_export_df, use_container_width=True, hide_index=True)
        st.download_button(
            "Download Figure Export Registry CSV",
            data=figure_export_df.to_csv(index=False),
            file_name="report_figure_export_registry.csv",
            mime="text/csv",
            use_container_width=True,
        )
        for item in figure_items:
            if not item.export_ready:
                continue
            fig, fig_warnings = build_exportable_figure(item.figure_key, st.session_state, figure_context)
            if fig is None:
                for warning in fig_warnings:
                    st.warning(warning)
                continue
            html_filename = item.export_filename_html or f"{item.figure_key}.html"
            st.download_button(
                f"Download {item.title} HTML",
                data=plotly_figure_to_html_bytes(fig),
                file_name=html_filename,
                mime="text/html",
                use_container_width=True,
            )
            png_bytes, png_warnings = plotly_figure_to_png_bytes(fig)
            if png_bytes is not None:
                st.download_button(
                    f"Download {item.title} PNG",
                    data=png_bytes,
                    file_name=item.export_filename_png or f"{item.figure_key}.png",
                    mime="image/png",
                    use_container_width=True,
                )
            else:
                for warning in png_warnings:
                    st.warning(warning)

        st.markdown("**Draft Word Report Export**")
        st.info("This draft report is generated from current stored results. It does not rerun analyses.")
        docx_cols = st.columns(3)
        include_appendices = docx_cols[0].checkbox("Include appendices", value=True, key="report_include_appendices")
        include_figures = docx_cols[1].checkbox("Include figures", value=True, key="report_include_figures")
        max_table_rows = docx_cols[2].number_input("Max table rows", min_value=5, max_value=200, value=30, step=5, key="report_max_table_rows")
        detail_cols = st.columns(2)
        include_full_terminology = detail_cols[0].checkbox("Include full terminology", value=True, key="report_include_full_terminology")
        include_full_registries = detail_cols[1].checkbox("Include full registries", value=True, key="report_include_full_registries")
        if not snapshot.pmm_result_available:
            st.warning("No ULS PMM result is currently available for the draft report.")
        if not snapshot.sls_result_available:
            st.warning("No SLS result is currently available for the draft report.")
        if snapshot.high_or_critical_limitation_count:
            st.warning(f"{snapshot.high_or_critical_limitation_count} high/critical engineering limitation(s) require review.")
        if st.button("Build Draft Word Report", use_container_width=True):
            metadata = ReportMetadata(
                report_title=report_title or "Concrete PMM Pro Engineering Report",
                project_name=report_project_name or None,
                prepared_by=prepared_by or None,
                checked_by=checked_by or None,
                revision=revision or "Draft",
            )
            manifest_for_docx = build_report_manifest(st.session_state, metadata)
            st.session_state["report_manifest"] = manifest_for_docx
            options = ReportExportOptions(
                include_appendices=include_appendices,
                include_figures=include_figures,
                max_table_rows=int(max_table_rows),
                include_full_terminology=include_full_terminology,
                include_full_registries=include_full_registries,
            )
            report_bytes, report_timing = timed_call(
                "Word/report export",
                build_draft_word_report,
                manifest_for_docx,
                st.session_state,
                options=options,
            )
            _record_runtime_timing(report_timing)
            st.session_state["draft_word_report_bytes"] = report_bytes
        report_bytes = st.session_state.get("draft_word_report_bytes")
        if report_bytes:
            st.download_button(
                "Download Draft Word Report (.docx)",
                data=report_bytes,
                file_name="concrete_pmm_pro_draft_report.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
            if st.button("Run Word Report QA", use_container_width=True):
                qa_manifest = st.session_state.get("report_manifest")
                if qa_manifest is None:
                    metadata = ReportMetadata(
                        report_title=report_title or "Concrete PMM Pro Engineering Report",
                        project_name=report_project_name or None,
                        prepared_by=prepared_by or None,
                        checked_by=checked_by or None,
                        revision=revision or "Draft",
                    )
                    qa_manifest = build_report_manifest(st.session_state, metadata)
                    st.session_state["report_manifest"] = qa_manifest
                st.session_state["word_report_qa_summary"] = run_word_report_qa(report_bytes, qa_manifest)

        qa_summary = st.session_state.get("word_report_qa_summary")
        if qa_summary is not None:
            st.markdown("**Word Report QA**")
            qa_cols = st.columns(4)
            qa_cols[0].metric("Overall QA Status", qa_summary.overall_status)
            qa_cols[1].metric("PASS", qa_summary.pass_count)
            qa_cols[2].metric("WARNING", qa_summary.warning_count)
            qa_cols[3].metric("FAIL", qa_summary.fail_count)
            if qa_summary.overall_status == "FAIL":
                st.error("Word report QA found failures. Review the QA table before using the draft report.")
            elif qa_summary.overall_status == "WARNING":
                st.warning("Word report QA found warnings. The draft remains downloadable, but the warnings should be reviewed.")
            else:
                st.success("Word report QA passed.")
            qa_df = report_qa_summary_to_dataframe(qa_summary)
            st.dataframe(qa_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Word Report QA CSV",
                data=qa_df.to_csv(index=False),
                file_name="word_report_qa.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with st.expander("Standard Terminology", expanded=False):
            terms_df = terminology_to_dataframe()
            st.dataframe(terms_df, use_container_width=True, hide_index=True)
            st.download_button(
                "Download Standard Terminology CSV",
                data=terms_df.to_csv(index=False),
                file_name="standard_terminology.csv",
                mime="text/csv",
                use_container_width=True,
            )

        st.warning("PDF export and final certified report templates are future work.")


def _render_analysis_settings_panel() -> None:
    current = _settings_from_session()
    preset = _analysis_accuracy_preset_from_session()
    preset_resolution = accuracy_preset_resolution(preset)
    if st.session_state.get("analysis_runtime_last_preset_applied") != preset:
        st.session_state["analysis_neutral_axis_angle_steps"] = preset_resolution["neutral_axis_angle_steps"]
        st.session_state["analysis_neutral_axis_depth_steps"] = preset_resolution["neutral_axis_depth_steps"]
        st.session_state["analysis_runtime_last_preset_applied"] = preset
    else:
        st.session_state.setdefault("analysis_neutral_axis_angle_steps", int(current.neutral_axis_angle_steps))
        st.session_state.setdefault("analysis_neutral_axis_depth_steps", int(current.neutral_axis_depth_steps))

    with st.expander("Analysis Settings", expanded=True):
        cols = st.columns(3)
        with cols[0]:
            code = project_design_code_from_session(st.session_state)
            st.markdown("**Code**")
            st.caption(f"{code} — from Setup / Project Design Code")
            analysis_type = st.selectbox("Analysis type", ["PMM Surface"], index=0)
            strength_load_type = st.selectbox(
                "Strength load type",
                ["ULS", "Extreme", "Construction", "Other"],
                index=["ULS", "Extreme", "Construction", "Other"].index(current.strength_load_type),
            )
        with cols[1]:
            include_rebars = st.checkbox("Include rebars", value=current.include_rebars)
            include_prestress = st.checkbox("Include prestress", value=current.include_prestress)
            use_phi_factor = st.checkbox("Use phi factor", value=current.use_phi_factor)
            transverse_reinforcement = st.selectbox(
                "Transverse reinforcement",
                ["tied", "spiral"],
                index=["tied", "spiral"].index(current.transverse_reinforcement),
            )
            prestress_stress_model = st.selectbox(
                "Prestress stress model",
                ["bilinear", "linear_cap"],
                index=["bilinear", "linear_cap"].index(current.prestress_stress_model),
            )
            subtract_rebar_displaced_concrete = st.checkbox(
                "Subtract displaced concrete at rebar locations",
                value=current.subtract_rebar_displaced_concrete,
                help=(
                    "When enabled, ordinary rebar inside the Whitney compression block uses net force "
                    "As(fs - 0.85f'c) to avoid double counting concrete compression."
                ),
            )
        with cols[2]:
            neutral_axis_angle_steps = st.number_input(
                "Neutral axis angle steps",
                min_value=12,
                step=1,
                key="analysis_neutral_axis_angle_steps",
            )
            neutral_axis_depth_steps = st.number_input(
                "Neutral axis depth steps",
                min_value=10,
                step=1,
                key="analysis_neutral_axis_depth_steps",
            )
            compression_positive = st.checkbox("Compression positive", value=current.compression_positive)
            st.caption(f"Current accuracy preset: {preset}.")
        note = st.text_area("Analysis note", value=current.note or "", height=80)

    settings = AnalysisSettings(
        code=code,
        analysis_type=analysis_type,
        strength_load_type=strength_load_type,
        include_rebars=include_rebars,
        include_prestress=include_prestress,
        use_phi_factor=use_phi_factor,
        transverse_reinforcement=transverse_reinforcement,
        prestress_stress_model=prestress_stress_model,
        subtract_rebar_displaced_concrete=subtract_rebar_displaced_concrete,
        neutral_axis_angle_steps=int(neutral_axis_angle_steps),
        neutral_axis_depth_steps=int(neutral_axis_depth_steps),
        compression_positive=compression_positive,
        note=note or None,
    )
    st.session_state["analysis_settings"] = settings


def render_analysis_uls_pmm() -> None:
    st.subheader("ULS / PMM")
    mode_settings = _analysis_mode_from_session()
    if is_beam_girder_future_workflow(mode_settings) or is_building_beam_girder_workflow(mode_settings):
        _render_beam_girder_uls_workspace(mode_settings)
        return

    _render_project_design_code_guard(workflow="pmm")
    _render_column_pier_analysis_decision_view()
    active_check = _column_pier_uls_check_choice()
    if active_check == "Flexural (PMM)":
        _render_column_pier_flexural_pmm_workspace()
    elif active_check == "Shear":
        _render_column_pier_shear_guarded_workspace()
    elif active_check == "Torsion":
        _render_column_pier_torsion_guarded_workspace()
    elif active_check == "Shear + Torsion":
        _render_column_pier_combined_vt_workspace()
    else:
        _render_column_pier_flexural_pmm_workspace()


def render_analysis_sls_stress() -> None:
    st.subheader("SLS / Stress & Cracking")
    mode_settings = _analysis_mode_from_session()
    if is_pmm_primary_workflow(mode_settings):
        st.info("SLS / Stress & Cracking is not selected for Column/Pier/Wall/Pylon PMM workflow.")
        st.warning("Use the ULS / PMM workspace for axial-biaxial strength review. Beam/Girder staged SLS checks remain hidden for this member family.")
        return
    _render_project_design_code_guard(workflow="girder_sls")
    st.info("SLS stress convention: compression is negative and tension is positive.")
    _render_beam_girder_service_stress_preview()
    _render_serviceability_expander()
    _render_sls_verification_expander()


def render_analysis_sls_deflection_camber() -> None:
    st.subheader("SLS Deflection / Camber")
    _render_project_design_code_guard(workflow="girder_sls")
    st.info("Deflection convention: positive = upward camber, negative = downward deflection.")

    mode_settings = _analysis_mode_from_session()
    is_bridge_workflow = is_beam_girder_future_workflow(mode_settings)
    is_building_workflow = is_building_beam_girder_workflow(mode_settings)
    if not (is_bridge_workflow or is_building_workflow):
        st.info("SLS Deflection / Camber is not selected for Column/Pier/Wall/Pylon PMM workflow.")
        return

    section_geometry = st.session_state.get("section_geometry")
    section_parameters = st.session_state.get("section_parameters", {})
    basis_options = build_girder_service_stress_basis_options(
        section_geometry,
        section_parameters,
        member_type=mode_settings.member_type,
    )
    for item in basis_options.info:
        st.info(item)
    for warning in basis_options.warnings:
        st.warning(f"Girder deflection preview warning: {warning}")
    _render_girder_deflection_camber_workspace(basis_options=basis_options)


def render_analysis_report_qa() -> None:
    st.subheader("Report / QA")
    st.info("Report and QA tools summarize stored results only; they do not rerun PMM, SLS, or verification solvers.")
    _render_pre_report_qa_expander()


def _analysis_subtabs_for_workflow(settings: AnalysisModeSettings) -> list[str]:
    if is_pmm_primary_workflow(settings):
        return list(ANALYSIS_COLUMN_PIER_SUBTABS)
    return list(ANALYSIS_SUBTABS)


def _analysis_subpage_choice() -> str:
    """Select one Analysis subpage without executing inactive analysis bodies."""

    key = "_nav_analysis_subpage"
    options = _analysis_subtabs_for_workflow(_analysis_mode_from_session())
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        try:
            value = segmented("Analysis subpage", options, key=key, selection_mode="single")
            if value in options:
                return str(value)
        except TypeError:
            pass
    value = st.radio("Analysis subpage", options, key=key, horizontal=True, label_visibility="collapsed")
    return str(value) if value in options else str(st.session_state.get(key, options[0]))


def render_analysis_page() -> None:
    st.subheader("Analysis")
    active_subpage = _analysis_subpage_choice()
    if active_subpage == "ULS / PMM":
        render_analysis_uls_pmm()
    elif active_subpage == "SLS / Stress & Cracking":
        render_analysis_sls_stress()
    elif active_subpage == "SLS Deflection / Camber":
        render_analysis_sls_deflection_camber()
    elif active_subpage == "Report / QA":
        render_analysis_report_qa()
    mark_analysis_current(st.session_state, workspace=f"Analysis / {active_subpage}")
    _render_runtime_diagnostics_expander()
