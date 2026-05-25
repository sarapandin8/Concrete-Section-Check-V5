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
    result = check_analysis_readiness(st.session_state)
    st.subheader("Analysis Readiness")
    st.metric("Ready for future analysis", "Yes" if result.ready else "No")

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

    for item in result.info:
        st.info(f"INFO: {item}")


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


def _render_prestress_check_panel(summary: PrestressCheckSummary, include_prestress: bool) -> None:
    st.subheader("Prestress Analysis Check Table")
    if not summary.checks:
        st.info("No prestress elements are defined.")
        return

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
    collected: list[str] = []
    for group in warning_groups:
        collected.extend(group)
    return deduplicate_warnings(collected)


def _render_engineering_warnings(warnings: list[str]) -> None:
    st.subheader("Engineering Warnings")
    st.info("Warnings are part of the engineering review workflow and should not be ignored.")
    if not warnings:
        st.success("No engineering warnings are currently reported.")
        return
    for warning in warnings:
        st.warning(warning)


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

    st.subheader("Analysis Input Summary")
    cols = st.columns(4)
    cols[0].metric("Section available", "Yes" if section_geometry is not None else "No")
    cols[1].metric("Strength load cases", f"{len(load_cases):,}")
    cols[2].metric("Rebars", f"{len(rebars):,}")
    cols[3].metric("Prestress elements", f"{len(prestress_elements):,}")

    ps_count_cols = st.columns(2)
    ps_count_cols[0].metric("Bonded prestress elements", f"{len(bonded_prestress_elements):,}")
    ps_count_cols[1].metric("Unbonded prestress elements ignored", f"{len(unbonded_prestress_elements):,}")
    if unbonded_prestress_elements:
        st.warning("Unbonded prestress elements are present and are ignored by the current PMM/SLS solvers.")

    cols2 = st.columns(4)
    if concrete_material is not None:
        beta1 = concrete_material.beta1 if concrete_material.beta1 is not None else aci_beta1(concrete_material.fc_MPa)
        cols2[0].metric("Concrete material", f"{concrete_material.name}")
        cols2[1].metric("Concrete f'c", f"{concrete_material.fc_MPa:g} MPa")
        cols2[2].metric("beta1", f"{beta1:.3g}")
    else:
        cols2[0].metric("Concrete material", "Missing")
        cols2[1].metric("Concrete f'c", "N/A")
        cols2[2].metric("beta1", "N/A")
    cols2[3].metric("Include prestress", "Yes" if settings.include_prestress else "No")

    cols3 = st.columns(3)
    cols3[0].metric("Total As", f"{total_as:,.1f} mm^2")
    cols3[1].metric("Total Aps", f"{total_aps:,.1f} mm^2")
    cols3[2].metric("Total Pe_eff", f"{total_pe:,.1f} N")

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
    if not settings.subtract_rebar_displaced_concrete:
        st.warning("Displaced concrete at ordinary rebar locations is not subtracted. Compression capacity may be overestimated.")
    st.info(
        SERVICEABILITY_NOT_IMPLEMENTED_WARNING
        if not settings.include_prestress
        else f"{BONDED_PRESTRESS_PROTOTYPE_WARNING} {SERVICEABILITY_NOT_IMPLEMENTED_WARNING}"
    )
    if analysis_input is not None:
        st.success("AnalysisInput can be built from the current session data.")
    else:
        st.info("AnalysisInput will be built after readiness errors are resolved.")

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
        result_has_bonded_prestress = any(point.bonded_prestress_count > 0 for point in result.points)
        result_label = "RC + Bonded Prestress PMM Prototype" if result_has_bonded_prestress else "RC PMM Prototype"
        st.subheader(f"{result_label} Result")
        st.warning(PMM_PROTOTYPE_WARNING)
        if result_has_bonded_prestress:
            st.warning(BONDED_PRESTRESS_PROTOTYPE_WARNING)
            st.warning("PT Bar / Prestressing Bar material is supported through PrestressElement.")
            st.warning(RC_AXIAL_CAP_LIMITATION_WARNING)
        else:
            st.warning("Prestress contribution is not included in this result.")
        st.warning(SERVICEABILITY_NOT_IMPLEMENTED_WARNING)
        if result.points and any(point.rebar_displaced_concrete_subtracted_N > 0.0 for point in result.points):
            st.info("This refinement reduces double counting of concrete compression at ordinary rebar locations.")
        elif not settings.subtract_rebar_displaced_concrete:
            st.warning("Displaced concrete at ordinary rebar locations is not subtracted. Compression capacity may be overestimated.")
        st.warning(DCR_PROTOTYPE_WARNING)
        for warning in result.warnings:
            st.warning(f"WARNING: {warning}")
        for item in result.info:
            st.info(f"INFO: {item}")

        df = pmm_result_to_display_dataframe(result)
        if not df.empty:
            summary = summarize_pmm_result(result)
            numeric_summary = check_pmm_dataframe_numerics(df)
            if numeric_summary["warnings"]:
                for warning in numeric_summary["warnings"]:
                    st.warning(f"PMM numeric warning: {warning}")
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

            dc_summary = _get_or_compute_demand_capacity_summary(
                result,
                st.session_state.get("load_cases", []),
                result_hash,
            )
            _render_engineering_warnings(
                _collect_engineering_warnings(
                    result.warnings,
                    prestress_check_summary.errors,
                    prestress_check_summary.warnings,
                    dc_summary.warnings,
                    numeric_summary["warnings"],
                )
            )

            unbonded_ignored_count = int(df["unbonded_prestress_ignored_count"].max()) if "unbonded_prestress_ignored_count" in df else 0
            _render_pmm_slice_dashboard(
                df,
                st.session_state.get("load_cases", []),
                dc_summary,
                result_label,
                settings.include_prestress,
                result_has_bonded_prestress,
                unbonded_ignored_count,
                result_hash,
            )

            with st.expander("Detailed PMM Plots", expanded=False):
                _render_pmm_charts(df, demand_df, dc_summary)
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


def _render_demand_capacity_summary(summary: DemandCapacitySummary) -> None:
    st.subheader("ULS Demand/Capacity Prototype")
    st.warning(
        "This is a prototype PMM demand/capacity check. Bonded prestress contribution is prototype when included; "
        "unbonded prestress, refined interpolation, and final validation are future work. Axial cap is applied "
        "only to axial compression summary/checks."
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
    st.markdown(_ANALYSIS_DASHBOARD_CSS, unsafe_allow_html=True)
    st.subheader("ULS / PMM Result Workspace")
    st.caption(
        "PMM slice, demand/capacity values, and 3D surface display are generated from stored PMM result data; "
        "this view does not rerun the solver."
    )
    if bonded_prestress_included:
        st.warning("Bonded prestress contribution is included using the current prototype strain compatibility model.")
    if unbonded_ignored_count > 0:
        st.warning("Unbonded prestress is ignored in the current solver.")

    active_uls = get_active_uls_load_cases(load_cases)
    if not active_uls:
        st.info("No active ULS load cases are available for the PMM Slice Dashboard.")
        return

    options = [load_case.name for load_case in active_uls]
    default_combo = dc_summary.governing_combo if dc_summary.governing_combo in options else options[0]
    remembered_combo = st.session_state.get("pmm_dashboard_selected_combo", default_combo)
    if remembered_combo not in options:
        remembered_combo = default_combo
    selected_combo = st.selectbox(
        "Load case",
        options,
        index=options.index(remembered_combo),
        key="pmm_dashboard_selected_combo",
    )
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
        _render_engineering_warnings(dashboard_warnings)

    selected_summary = build_selected_load_case_summary(
        selected_load_case,
        dc_summary,
        mode_label,
        include_prestress and bonded_prestress_included,
        selected_envelope,
    )
    _render_analysis_summary_strip(_selected_case_summary_cards(selected_summary, dc_summary), columns=4)

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

    st.subheader("3D PMM Interaction View")
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
    else:
        st.info("3D PMM interaction rendering is off. Enable it only when a 3D capacity view is needed.")

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

    st.subheader("Load Case D/C Ranking")
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


def _render_pmm_charts(df, demand_df, dc_summary: DemandCapacitySummary | None = None) -> None:
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
    pmx.update_layout(title="RC PMM Prototype: P-Mnx", xaxis_title="phiMnx (kN-m)", yaxis_title="phiPn (kN)")
    st.plotly_chart(pmx, use_container_width=True, key="analysis_p_mnx_chart")

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
    pmy.update_layout(title="RC PMM Prototype: P-Mny", xaxis_title="phiMny (kN-m)", yaxis_title="phiPn (kN)")
    st.plotly_chart(pmy, use_container_width=True, key="analysis_p_mny_chart")

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
    mm.update_layout(title="RC PMM Prototype: Mnx-Mny Point Cloud", xaxis_title="phiMnx (kN-m)", yaxis_title="phiMny (kN-m)")
    st.plotly_chart(mm, use_container_width=True, key="analysis_mnx_mny_chart")

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
        title="RC PMM Prototype: 3D Point Cloud",
        scene=dict(xaxis_title="phiMnx (kN-m)", yaxis_title="phiMny (kN-m)", zaxis_title="phiPn (kN)"),
    )
    st.plotly_chart(fig3d, use_container_width=True, key="analysis_3d_pmm_chart")


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
