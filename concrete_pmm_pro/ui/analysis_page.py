"""Analysis readiness page."""

from __future__ import annotations

import json
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
from concrete_pmm_pro.core.analysis_modes import (
    analysis_mode_description,
    analysis_mode_label,
    analysis_mode_warnings,
    is_beam_girder_future_workflow,
    is_pmm_primary_workflow,
)
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm
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
    build_serviceability_summary_from_analysis_input,
    classify_service_stress_results_for_cracking,
    crack_classification_to_dataframe,
    custom_stress_check_points_from_dataframe,
    dataframe_to_stress_check_points,
    prestress_service_contribution_to_dataframe,
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
    return AnalysisInput(
        section_geometry=section_geometry,
        concrete_material=concrete_material,
        rebar_materials=list(st.session_state.get("rebar_materials", []) or []),
        prestress_materials=list(st.session_state.get("prestress_materials", []) or []),
        rebars=list(st.session_state.get("rebars", []) or []),
        prestress_elements=list(st.session_state.get("prestress_elements", []) or []),
        load_cases=list(st.session_state.get("load_cases", []) or []),
        settings=_settings_from_session(),
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
    current = _analysis_mode_from_session()
    options = {
        "Column / Pier / Wall / Pylon - PMM Mode": "column_pier_pmm",
        "Beam / Girder - Flexure Mode Future": "beam_girder",
        "General Section": "general_section",
    }
    labels = list(options.keys())
    current_label = next(label for label, member_type in options.items() if member_type == current.member_type)

    with st.expander("Analysis Mode / Member Type", expanded=True):
        selected_label = st.selectbox("Member Type", labels, index=labels.index(current_label))
        note = st.text_area("Analysis mode note", value=current.note or "", height=80)
        settings = AnalysisModeSettings(member_type=options[selected_label], note=note or None)
        st.session_state["analysis_mode_settings"] = settings

        st.markdown(f"**{analysis_mode_label(settings)}**")
        st.info(analysis_mode_description(settings))
        mode_cols = st.columns(4)
        mode_cols[0].metric("Analysis Workflow", settings.analysis_workflow)
        mode_cols[1].metric("PMM Workflow", "Available" if settings.allow_pmm_workflow else "Caution / not primary")
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
            st.warning("Beam/Girder mode is a future workflow placeholder.")
            st.info("Future inputs will include Mu, Vu, Tu, service/transfer stages, Pe/e, and tendon profile.")
            st.info("Existing SLS stress checks can still be used for section stress review.")
            st.warning("Do not enter prestress Pe again as Pu if prestress elements are already defined.")
            st.warning("Beam/Girder flexure, shear, torsion, and transfer-stage checks are not implemented yet.")
        else:
            st.info("General section mode keeps PMM and SLS tools available.")
            st.warning("Use carefully and verify load interpretation.")

        for warning in analysis_mode_warnings(settings):
            st.warning(warning)

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
        st.caption("Deduplicated solver messages are grouped by severity, action priority, meaning, likely cause, recommended action, governing impact, and where to check.")
        st.dataframe(_diagnostics_to_dataframe(warnings, df=df, dc_summary=dc_summary), use_container_width=True, hide_index=True)
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

    def row(area: str, case_id: str | None, evidence: str, remaining: str) -> dict[str, str]:
        case = cases.get(case_id) if case_id else None
        status = case.status if case is not None else "planned"
        return {
            "Area": area,
            "Validation Status": _validation_status_badge(status),
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
        ),
        row(
            "ACI phi transition",
            "VALID.RC2",
            "Compression-controlled, transition, and tension-controlled phi checks are covered.",
            "Document published-code examples for final validation notes.",
        ),
        row(
            "Directional PMM D/C extraction",
            "VALID.PMM.DC1",
            "Cleaned Pu slice envelope with ray-intersection capacity benchmark.",
            "Add reference biaxial demand/capacity examples before retiring all D/C limitation notes.",
        ),
        row(
            "Prestress-aware axial cap",
            "QA.PO1",
            "QA.PO1 validates Po, Aps, count handling, fpu fallback, and capped phiPn,max.",
            "Review project/code-specific axial-compression limits before final design.",
        ),
    ]

    if result_has_passive_prestress:
        rows.append(
            row(
                "Passive PS / high-strength steel",
                "SOLVER.PS.PASSIVE1",
                "Passive Pe_eff=0/fpe=0 rows are separated from active-prestress warnings.",
                "Review detailing/minimum reinforcement requirements separately.",
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
                ),
                row(
                    "Prestress stress-state region policy",
                    "VALID.PS2",
                    "fpu-cap and compression-reversal metadata are traceable by PMM region.",
                    "Stress-strain reference cases for compression-side behavior remain future validation work.",
                ),
                row(
                    "Prestress fpu-cap warning policy",
                    "SOLVER.PS.STRESS1",
                    "fpu-cap events are retained as PMM metadata unless governing-region evidence requires escalation.",
                    "Keep reviewing governing-region diagnostics for final design cases.",
                ),
                row(
                    "Prestress compression-reversal policy",
                    "SOLVER.PS.COMP1",
                    "Compression-reversal events are escalated only when detected near the governing PMM region.",
                    "A refined compression-side prestress material model is still a future solver milestone.",
                ),
            ]
        )
    if include_sls:
        rows.append(
            {
                "Area": "SLS / Stress & Cracking",
                "Validation Status": "Planned / not implemented",
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
            "detail": "Not part of current ULS PMM result",
            "status": "neutral",
        },
        {
            "title": "Method Basis",
            "value": "ACI strain compatibility",
            "detail": "See validation table and QA notes",
            "status": "info",
        },
    ]


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
            "This panel separates validated/implemented method areas from validation-in-progress items. "
            "It does not hide QA diagnostics; it explains why remaining notes are retained before final design use."
        )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

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


def _render_engineering_warnings(
    warnings: list[str],
    *,
    df: pd.DataFrame | None = None,
    dc_summary: DemandCapacitySummary | None = None,
) -> None:
    st.subheader("Actionable Engineering Review Guidance")
    st.info("Each diagnostic is translated into meaning, possible cause, recommended action, governing impact, action priority, and where to check. Limitation and numerical notes are retained for QA but are not treated as ULS readiness failures.")
    if not warnings:
        st.success("No engineering review messages are currently reported.")
        return

    counts = _diagnostic_counts(warnings)
    cols = st.columns(3)
    cols[0].metric("Review warnings", f"{counts.get('Engineering review warning', 0):,}")
    cols[1].metric("Limitation notes", f"{counts.get('Solver limitation note', 0):,}")
    cols[2].metric("Numerical notes", f"{counts.get('Numerical note', 0):,}")
    guidance_df = _diagnostics_to_dataframe(warnings, df=df, dc_summary=dc_summary)
    priority_counts = guidance_df["Action Priority"].value_counts().to_dict() if not guidance_df.empty and "Action Priority" in guidance_df else {}
    priority_cols = st.columns(3)
    priority_cols[0].metric("Governing-related", f"{priority_counts.get('Check before relying on governing result', 0):,}")
    priority_cols[1].metric("Review before final", f"{priority_counts.get('Review before final design', 0) + priority_counts.get('Review for final design', 0):,}")
    priority_cols[2].metric("QA / usually no action", f"{priority_counts.get('QA note', 0) + priority_counts.get('Usually no action', 0):,}")
    st.dataframe(guidance_df, use_container_width=True, hide_index=True)


def _render_prestress_verification_summary(
    check_summary: PrestressCheckSummary,
    contribution_summary: dict,
    comparison_summary: dict | None,
) -> None:
    st.subheader("Prestress Verification Summary")
    cols = st.columns(4)
    cols[0].metric("Bonded PS included", f"{contribution_summary['bonded_prestress_count']:,}")
    cols[1].metric("Unbonded PS ignored", f"{contribution_summary['unbonded_prestress_ignored_count']:,}")
    cols[2].metric("Total bonded Aps", f"{check_summary.total_area_mm2:,.1f} mm^2")
    cols[3].metric("Total bonded Pe_eff", f"{N_to_kN(check_summary.total_pe_eff_N):,.1f} kN")

    cols2 = st.columns(3)
    cols2[0].metric("Max |PS force|", f"{contribution_summary['max_abs_prestress_force_kN']:,.1f} kN")
    cols2[1].metric("Mean |PS force|", f"{N_to_kN(contribution_summary['mean_abs_prestress_force_N']):,.1f} kN")
    cols2[2].metric("PMM points with PS force", f"{contribution_summary['point_count_with_prestress']:,}")

    for warning in contribution_summary.get("warnings", []):
        st.warning(f"WARNING: {warning}")

    if comparison_summary is None:
        st.info("RC-only comparison is available after running with bonded prestress included.")
        return

    cols3 = st.columns(3)
    cols3[0].metric("RC-only max phiPn", f"{comparison_summary['rc_max_phiPn_kN']:,.1f} kN")
    cols3[1].metric("RC+PS max phiPn", f"{comparison_summary['ps_max_phiPn_kN']:,.1f} kN")
    cols3[2].metric("Delta max phiPn", f"{comparison_summary['delta_max_phiPn_kN']:,.1f} kN")

    cols4 = st.columns(3)
    cols4[0].metric("RC-only max |phiMnx|", f"{comparison_summary['rc_max_abs_phiMnx_kNm']:,.1f} kN-m")
    cols4[1].metric("RC+PS max |phiMnx|", f"{comparison_summary['ps_max_abs_phiMnx_kNm']:,.1f} kN-m")
    cols4[2].metric("Delta max |phiMnx|", f"{comparison_summary['delta_max_abs_phiMnx_kNm']:,.1f} kN-m")

    cols5 = st.columns(3)
    cols5[0].metric("RC-only max |phiMny|", f"{comparison_summary['rc_max_abs_phiMny_kNm']:,.1f} kN-m")
    cols5[1].metric("RC+PS max |phiMny|", f"{comparison_summary['ps_max_abs_phiMny_kNm']:,.1f} kN-m")
    cols5[2].metric("Delta max |phiMny|", f"{comparison_summary['delta_max_abs_phiMny_kNm']:,.1f} kN-m")

    for warning in comparison_summary.get("warnings", []):
        st.warning(f"WARNING: {warning}")


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
    rebars = st.session_state.get("rebars", [])
    prestress_elements = st.session_state.get("prestress_elements", [])
    total_as = sum(rebar.area_mm2 for rebar in rebars)
    total_aps = sum(element.total_area_mm2 for element in prestress_elements)
    total_pe = sum(element.pe_eff_n * element.count for element in prestress_elements)
    bonded_prestress_elements = [element for element in prestress_elements if element.bonded]
    unbonded_prestress_elements = [element for element in prestress_elements if not element.bonded]
    prototype_label = "RC + Bonded Prestress PMM Prototype" if settings.include_prestress and bonded_prestress_elements else "RC PMM Prototype"
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
            "detail": f"Bonded PS {len(bonded_prestress_elements):,}; unbonded ignored {len(unbonded_prestress_elements):,}",
            "status": "warning" if unbonded_prestress_elements else "neutral",
        },
        {
            "title": "Solver Mode",
            "value": prototype_label,
            "detail": f"f'c {concrete_material.fc_MPa:g} MPa, beta1 {beta1:.3g}" if concrete_material is not None and beta1 is not None else "Concrete material missing",
            "status": "ready" if concrete_material is not None else "danger",
        },
    ]
    _render_analysis_summary_strip(overview_cards, columns=4)

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
        cols[2].metric("Rebars", f"{len(rebars):,}")
        cols[3].metric("Prestress elements", f"{len(prestress_elements):,}")

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
        cols2[3].metric("Include prestress", "Yes" if settings.include_prestress else "No")

        cols3 = st.columns(3)
        cols3[0].metric("Total As", f"{total_as:,.1f} mm^2")
        cols3[1].metric("Total Aps", f"{total_aps:,.1f} mm^2")
        cols3[2].metric("Total Pe_eff", f"{N_to_kN(total_pe):,.1f} kN")

        st.info("PMM prototype status: RC-only or RC + bonded prestress depending on analysis settings.")
        st.info(f"Current solver mode: {prototype_label}.")
        if is_beam_girder_future_workflow(mode_settings):
            st.warning("PMM interaction is not the primary design method for typical beam/girder flexural design. Beam/Girder design checks are future work.")
        elif not is_pmm_primary_workflow(mode_settings):
            st.info("General Section mode is active; PMM and SLS tools remain available for engineering review.")
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
                cols = st.columns(4)
                cols[0].metric("PMM points", f"{summary['point_count']:,}")
                cols[1].metric("Max phiPn", f"{df['phiPn_kN'].max():,.1f} kN")
                cols[2].metric("Max capped phiPn", f"{df['phiPn_capped_kN'].max():,.1f} kN")
                cols[3].metric("Min phiPn", f"{df['phiPn_kN'].min():,.1f} kN")
                cols2 = st.columns(4)
                cols2[0].metric("Max |phiMnx|", f"{df['phiMnx_kNm'].abs().max():,.1f} kN-m")
                cols2[1].metric("Max |phiMny|", f"{df['phiMny_kNm'].abs().max():,.1f} kN-m")
                cols2[2].metric("Max nominal Pn", f"{df['Pn_kN'].max():,.1f} kN")
                cols2[3].metric("Max nominal |Mnx|", f"{df['Mnx_kNm'].abs().max():,.1f} kN-m")
                cols3 = st.columns(1)
                cols3[0].metric("Max nominal |Mny|", f"{df['Mny_kNm'].abs().max():,.1f} kN-m")
                cols4 = st.columns(4)
                cols4[0].metric("Bonded PS included", f"{int(df['bonded_prestress_count'].max()):,}")
                cols4[1].metric("Unbonded PS ignored", f"{int(df['unbonded_prestress_ignored_count'].max()):,}")
                cols4[2].metric("Max |PS force|", f"{df['prestress_force_kN'].abs().max():,.1f} kN")
                included_aps = sum(element.total_area_mm2 for element in bonded_prestress_elements) if result_has_bonded_prestress else 0.0
                included_pe = sum(element.pe_eff_n * element.count for element in bonded_prestress_elements) if result_has_bonded_prestress else 0.0
                cols4[3].metric("Included Aps / Pe", f"{included_aps:,.1f} mm^2 / {included_pe:,.0f} N")
                cols_disp = st.columns(3)
                cols_disp[0].metric(
                    "Rebar displacement subtraction",
                    "Enabled" if settings.subtract_rebar_displaced_concrete else "Disabled",
                )
                cols_disp[1].metric(
                    "Max concrete subtraction",
                    f"{df['rebar_displaced_concrete_subtracted_kN'].max():,.1f} kN",
                )
                cols_disp[2].metric(
                    "Max bars in block",
                    f"{int(df['rebar_inside_compression_count'].max()):,}",
                )
                if result_has_bonded_prestress and "max_prestress_stress_MPa" in df:
                    model_values = df["prestress_stress_model"].dropna()
                    model_label = str(model_values.iloc[0]) if not model_values.empty else settings.prestress_stress_model
                    cols5 = st.columns(4)
                    cols5[0].metric("Prestress stress model", model_label)
                    cols5[1].metric("Max fps", f"{df['max_prestress_stress_MPa'].max():,.1f} MPa")
                    cols5[2].metric("Stress warning count", f"{int(df['prestress_stress_warning_count'].sum()):,}")
                    cols5[3].metric("Reached fpu cap count", f"{int(df['prestress_reached_fpu_cap_count'].sum()):,}")
    
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
                warning_counts = _diagnostic_counts(engineering_warnings)
                review_warning_count = warning_counts.get("Engineering review warning", 0)
                limitation_count = warning_counts.get("Solver limitation note", 0)
                numerical_note_count = warning_counts.get("Numerical note", 0)
                if review_warning_count:
                    st.warning(
                        f"{review_warning_count:,} engineering review warning(s) need review in Diagnostics / QA with recommended actions. "
                        f"{limitation_count:,} solver limitation note(s) and {numerical_note_count:,} numerical note(s) are retained for QA."
                    )
                else:
                    st.info(
                        f"No engineering review warnings are active. "
                        f"{limitation_count:,} solver limitation note(s) and {numerical_note_count:,} numerical note(s) are retained for QA."
                    )
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


def _render_executive_result_header(dc_summary: DemandCapacitySummary, load_cases: list) -> None:
    usage = _active_load_case_usage_summary(load_cases)
    status = dc_summary.overall_status.replace("_", " ")
    governing = dc_summary.governing_combo or "No governing case"
    max_dcr = _format_optional_number(dc_summary.max_dcr, precision=3)
    status_class = _analysis_status_style(dc_summary.overall_status)
    html = (
        '<div class="cpmm-executive-header">'
        '<div class="cpmm-executive-eyebrow">ULS / PMM Analysis Workspace</div>'
        f'<div class="cpmm-executive-title">{escape(status)} · Governing: {escape(governing)} · D/C {escape(max_dcr)}</div>'
        '<div class="cpmm-executive-subtitle">'
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
            slice_figure_hash = f"{result_hash or 'unhashed'}:{selected_load_case.name}:mux_muy_slice"
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
                    selected_load_case,
                    dc_summary,
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
            st.markdown("**Selected Case Details**")
            _render_selected_case_detail_panel(selected_summary, unbonded_ignored_count)

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
