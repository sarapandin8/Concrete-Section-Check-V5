"""Analysis preparation helpers."""

from concrete_pmm_pro.analysis.capacity_check import (
    DemandCapacityResult,
    DemandCapacitySummary,
    check_uls_demands_against_rc_pmm,
    estimate_directional_capacity,
)
from concrete_pmm_pro.analysis.preflight import (
    AnalysisReadinessResult,
    build_analysis_input_from_session_state,
    check_analysis_readiness,
)
from concrete_pmm_pro.analysis.prestress_checks import (
    PrestressCheckSummary,
    PrestressElementCheck,
    check_prestress_elements_for_analysis,
    compare_rc_vs_prestress_pmm,
    summarize_prestress_contribution,
)
from concrete_pmm_pro.analysis.pmm_solver import run_rc_pmm_solver
from concrete_pmm_pro.analysis.prestress_stress import prestress_stress_mpa, prestress_total_tensile_strain
from concrete_pmm_pro.analysis.result_models import (
    PMMPoint,
    PMMSolverResult,
    active_load_cases_to_display_dataframe,
    check_pmm_dataframe_numerics,
    pmm_result_to_display_dataframe,
    summarize_pmm_result,
)
from concrete_pmm_pro.analysis.runtime import (
    ACCURACY_PRESET_RESOLUTIONS,
    AnalysisRuntimeMetadata,
    RuntimeTiming,
    accuracy_preset_resolution,
    analysis_input_hash,
    apply_accuracy_preset_to_settings,
    cache_status_for_hash,
    demand_capacity_input_hash,
    recalculation_required,
    serviceability_input_hash,
    stable_hash_from_payload,
    timed_call,
)
from concrete_pmm_pro.analysis.slice_envelope import (
    SliceEnvelopeResult,
    build_convex_hull_envelope,
    build_slice_envelope,
    compute_polar_angle_and_radius,
    estimate_directional_capacity_from_envelope,
    remove_near_duplicate_slice_points,
)
from concrete_pmm_pro.analysis.strain_compatibility import is_point_inside_compression_block, rebar_net_force_n

__all__ = [
    "AnalysisReadinessResult",
    "ACCURACY_PRESET_RESOLUTIONS",
    "AnalysisRuntimeMetadata",
    "DemandCapacityResult",
    "DemandCapacitySummary",
    "PMMPoint",
    "PMMSolverResult",
    "PrestressCheckSummary",
    "PrestressElementCheck",
    "SliceEnvelopeResult",
    "RuntimeTiming",
    "active_load_cases_to_display_dataframe",
    "accuracy_preset_resolution",
    "analysis_input_hash",
    "apply_accuracy_preset_to_settings",
    "build_convex_hull_envelope",
    "build_analysis_input_from_session_state",
    "build_slice_envelope",
    "check_prestress_elements_for_analysis",
    "check_uls_demands_against_rc_pmm",
    "check_analysis_readiness",
    "check_pmm_dataframe_numerics",
    "cache_status_for_hash",
    "demand_capacity_input_hash",
    "compare_rc_vs_prestress_pmm",
    "compute_polar_angle_and_radius",
    "estimate_directional_capacity_from_envelope",
    "estimate_directional_capacity",
    "pmm_result_to_display_dataframe",
    "prestress_stress_mpa",
    "prestress_total_tensile_strain",
    "is_point_inside_compression_block",
    "rebar_net_force_n",
    "remove_near_duplicate_slice_points",
    "recalculation_required",
    "run_rc_pmm_solver",
    "serviceability_input_hash",
    "stable_hash_from_payload",
    "summarize_prestress_contribution",
    "summarize_pmm_result",
    "timed_call",
]
