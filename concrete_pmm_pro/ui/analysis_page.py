"""Analysis readiness page."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from datetime import datetime
from html import escape

import plotly.graph_objects as go
import pandas as pd
import streamlit as st

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
    is_pmm_primary_workflow,
)
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm
from concrete_pmm_pro.geometry.summary import summarize_geometry
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
    GirderServiceStageCase,
    GirderServiceStressLimitCheckResult,
    GirderStressLimitPointResult,
    StressLimitInputRow,
    build_girder_sls_limit_profile,
    default_girder_service_stage_templates,
    girder_prestress_stress_result_rows,
    girder_service_limit_check_rows,
    girder_sls_limit_formula_summary,
    girder_sls_limit_profile_options,
    girder_sls_stage_basis_consistency_warnings,
    normalize_girder_sls_stage,
    girder_service_stage_result_rows,
    girder_service_stress_result_rows,
    prestress_service_contribution_to_dataframe,
    run_girder_service_stage_stress,
    run_girder_service_stress_limit_check,
    run_basic_girder_service_stress,
    run_girder_prestress_stress_effect,
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

ANALYSIS_SUBTABS = ["ULS / PMM", "SLS / Stress & Cracking", "Report / QA"]
PMM_3D_MASTER_TOGGLE_KEY = "show_pmm_3d_interaction"
PMM_3D_LAYER_DEFAULTS = {
    "show_pmm_3d_surface": True,
    "show_pmm_3d_current_pu_slice": True,
    "show_pmm_3d_selected_point": True,
    "show_pmm_3d_all_load_points": False,
}

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
    with st.expander("Runtime Diagnostics", expanded=False):
        st.info(
            "Timing diagnostics measure UI-triggered expensive operations only. "
            "They do not change PMM/SLS formulas, sign conventions, or engineering results."
        )
        timings_df = _runtime_timings_dataframe()
        if timings_df.empty:
            st.info("No timed operations have been recorded in this session.")
        else:
            st.dataframe(timings_df, use_container_width=True, hide_index=True)


def _analysis_mode_from_session() -> AnalysisModeSettings:
    value = st.session_state.get("analysis_mode_settings")
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


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
        st.error("Readiness errors are present. Open the diagnostics below and correct them before relying on results.")
    elif result.warnings:
        st.warning("Readiness warnings are present. Analysis can run, but the warnings should be reviewed.")
    else:
        st.success("No readiness errors. Detailed readiness information is available below if needed.")

    with st.expander("Readiness diagnostics", expanded=False):
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
        mode_cols[2].metric("SLS Workflow", "Available" if settings.allow_sls_workflow else "Unavailable")
        mode_cols[3].metric(
            "Beam/Girder Workflow",
            "Future / not implemented" if settings.allow_beam_girder_placeholder else "Not selected",
        )

        if settings.member_type == "column_pier_pmm":
            st.success("Current workflow uses Pu, Mux, and Muy with PMM interaction and prototype ULS D/C review.")
            st.info("SLS stress checks remain available for selected service load cases.")
            st.info("Prestress is treated as internal prestress/reinforcement action, not duplicated as Pu demand.")
        elif settings.member_type == "beam_girder":
            st.info("Beam/Girder mode is a future workflow placeholder; PMM is not applicable as the primary girder design workflow.")
            st.info("Future inputs will include Mu, Vu, Tu, service/transfer stages, Pe/e, and tendon profile.")
            st.info("Existing SLS stress checks can still be used for section stress review.")
            st.info("Do not enter prestress Pe again as Pu if prestress elements are already defined.")
            st.info("Beam/Girder flexure, shear, torsion, and transfer-stage checks are not implemented yet.")
        else:
            st.info("General section mode keeps PMM and SLS tools available.")
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

    base_warnings: list[object] = [PMM_PROTOTYPE_WARNING, SERVICEABILITY_NOT_IMPLEMENTED_WARNING, DCR_PROTOTYPE_WARNING]
    if result_has_bonded_prestress:
        base_warnings.extend(
            [
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

    warnings = _deduplicate_diagnostic_messages(base_warnings + list(result_warnings or []) + list(numeric_warnings or []))
    info_items = list(result_info or [])
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
            "value": "ACI strain compatibility",
            "detail": "See validation table and QA notes",
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
    prototype_label: str,
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
            help=f"Runs or reuses the cached {prototype_label} result depending on the engineering input hash.",
            use_container_width=True,
        )

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
    prototype_label = "RC + Bonded Prestress PMM Prototype" if settings.include_prestress and prestress_system_enabled and bonded_prestress_elements else "RC PMM Prototype"
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
            "value": prototype_label,
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

        st.info("PMM prototype status: RC-only or RC + bonded prestress depending on analysis settings.")
        st.info(f"Current solver mode: {prototype_label}.")
        if is_beam_girder_future_workflow(mode_settings):
            st.warning("PMM interaction is not the primary design method for typical beam/girder flexural design. Beam/Girder design checks are future work.")
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
        prototype_label,
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
        st.caption("Method: ACI strain compatibility. Validation status is summarized below; QA diagnostics remain available for final engineering review.")
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
                    "Demand points are shown for visual reference. Prototype D/C results are shown below; "
                    "formal production demand/capacity checks will be implemented in a future milestone."
                )
                st.dataframe(demand_df, use_container_width=True, hide_index=True)

            engineering_warnings = _collect_engineering_warnings(
                result.warnings,
                prestress_check_summary.errors,
                prestress_check_summary.warnings,
                dc_summary.warnings,
                numeric_summary["warnings"],
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
    st.subheader("ULS Demand/Capacity Prototype")
    st.warning(
        "This PMM demand/capacity workflow remains under staged validation. Bonded prestress contribution is still being validated; "
        "the axial cap now uses the QA.PO1-validated prestress-aware Po helper with bonded prestress steel. "
        "Unbonded prestress, refined long-term effects, and full production validation remain future work."
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
    """Initialize code-limit stage to match the active SLS stage tab without overriding user edits."""

    stage_key = f"girder_code_limit_stage_{title}"
    default_stage = _beam_sls_stage_default_code_limit_stage(stage_label)
    if st.session_state.get(stage_key) not in DEFAULT_GIRDER_SLS_STAGES:
        st.session_state[stage_key] = default_stage


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
        "Compact preview only. Select code/stage/profile here; detailed formulas, basis notes, and stress rows stay in expanders."
    )

    fc_default = _girder_fc_for_sls_limit_preview()
    stage_key = f"girder_code_limit_stage_{title}"
    if stage_key in st.session_state:
        normalized_stage = normalize_girder_sls_stage(st.session_state.get(stage_key))
        if normalized_stage in DEFAULT_GIRDER_SLS_STAGES and normalized_stage != st.session_state.get(stage_key):
            st.session_state[stage_key] = normalized_stage

    controls = st.columns([1.0, 1.05, 1.55, 0.85, 0.85])
    with controls[0]:
        code = st.selectbox(
            "Design code profile",
            list(DEFAULT_GIRDER_SLS_CODES),
            key=f"girder_code_limit_code_{title}",
            help="AASHTO is generally the bridge-girder default; ACI is available for building/general prestressed members.",
        )
    with controls[1]:
        stage = st.selectbox(
            "Stress limit stage",
            list(DEFAULT_GIRDER_SLS_STAGES),
            key=stage_key,
            help="Stage controls which concrete strength, prestress-force state, and section basis should be checked.",
        )

    profile_options = girder_sls_limit_profile_options(code=code, stage=stage)
    profile_option_labels = {option.key: option.label for option in profile_options}
    profile_option_descriptions = {option.key: option.description for option in profile_options}
    profile_key = f"girder_code_limit_profile_key_{title}"
    if st.session_state.get(profile_key) not in profile_option_labels:
        st.session_state[profile_key] = profile_options[0].key
    with controls[2]:
        limit_profile_key = st.selectbox(
            "Limit profile",
            list(profile_option_labels),
            format_func=lambda key: profile_option_labels.get(str(key), str(key)),
            key=profile_key,
            help="Select a code/stage default profile before applying any engineer-controlled overrides.",
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
    context_warnings = girder_sls_stage_basis_consistency_warnings(
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
    if not is_beam_girder_future_workflow(mode_settings):
        return

    # Legacy milestone label retained for source-level regression tests: Beam/Girder Elastic Service Stress Preview.
    st.markdown("### Beam/Girder SLS Stress Workspace")
    _render_analysis_summary_strip(
        [
            {
                "title": "Workspace status",
                "value": "Manual preview only",
                "detail": "Elastic stress foundation; not a final code check",
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
                "value": "Optional preview",
                "detail": "AASHTO + ACI editable limit profiles",
                "status": "info",
            },
        ],
        columns=4,
    )

    with st.expander("Beam/Girder SLS preview limitations", expanded=False):
        st.write(
            "- GIRDER.SLS1B/PS1B previews elastic Beam/Girder service stress using manual trial actions "
            "and optional effective-prestress stress effect."
        )
        st.write("- Compression stress is negative; tension stress is positive. Sagging M is positive and gives top compression / bottom tension.")
        st.write("- Pe_eff is positive for compressive effective prestress after losses.")
        st.write(
            "- This preview is not a staged prestressed girder design check yet. It does not include transfer/final stage automation, "
            "creep/shrinkage, final AASHTO/ACI clause calibration, shear, or report integration."
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
    st.markdown("##### SLS stage check tabs")
    st.caption(
        "Stage checks are always available. Each stage defaults to the matching Loads page row when available; "
        "manual input is a stage-level override/fallback. Each stage keeps its own code-limit/profile/prestress UI state."
    )
    stage_tabs = st.tabs([label for _, label, _ in _beam_sls_stage_tab_specs()])
    for tab, (stage_key, stage_label, stage_note) in zip(stage_tabs, _beam_sls_stage_tab_specs(), strict=False):
        with tab:
            stage_rows = _beam_sls_rows_for_stage(beam_sls_rows, stage_label)
            st.caption(stage_note)

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

def _render_serviceability_expander() -> None:
    current = _serviceability_settings_from_session()
    with st.expander("Serviceability / SLS Foundation", expanded=False):
        st.info(
            "This section prepares serviceability settings, SLS load cases, gross section properties, "
            "transformed section properties, stress check points, and elastic SLS stress checks."
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
            code = st.text_input("Code", value=current.code)
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
    st.info(
        "ULS compression Pu remains positive. Prestress is treated as internal prestress/reinforcement action "
        "and should not be duplicated as external Pu demand."
    )
    _render_analysis_mode_section()
    _render_analysis_settings_panel()
    _render_readiness_panel()
    _render_input_summary()
    _render_verification_expander()


def render_analysis_sls_stress() -> None:
    st.subheader("SLS / Stress & Cracking")
    st.info("SLS stress convention: compression is negative and tension is positive.")
    _render_beam_girder_service_stress_preview()
    _render_serviceability_expander()
    _render_sls_verification_expander()


def render_analysis_report_qa() -> None:
    st.subheader("Report / QA")
    st.info("Report and QA tools summarize stored results only; they do not rerun PMM, SLS, or verification solvers.")
    _render_pre_report_qa_expander()


def render_analysis_page() -> None:
    st.subheader("Analysis")
    uls_tab, sls_tab, report_tab = st.tabs(ANALYSIS_SUBTABS)
    with uls_tab:
        render_analysis_uls_pmm()
    with sls_tab:
        render_analysis_sls_stress()
    with report_tab:
        render_analysis_report_qa()
    _render_runtime_diagnostics_expander()
