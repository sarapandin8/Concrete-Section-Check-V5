"""Lightweight dirty-state and input-hash helpers.

PERF.RERUN1 does not try to stop Streamlit's normal rerun behavior.  Instead,
it makes reruns cheap and explicit: input pages persist edits immediately,
mark downstream analysis/report outputs as stale, and heavy checks are rendered
only when the relevant workspace/subpage is opened.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping

CURRENT_INPUT_HASH_KEY = "_perf_current_input_hash"
PREVIOUS_INPUT_HASH_KEY = "_perf_previous_input_hash"
LAST_ANALYSIS_HASH_KEY = "_perf_last_analysis_input_hash"
CHANGED_GROUPS_KEY = "_perf_changed_input_groups"
ANALYSIS_STATUS_KEY = "_perf_analysis_status"
REPORT_STATUS_KEY = "_perf_report_status"
LAST_REFRESHED_WORKSPACE_KEY = "_perf_last_refreshed_workspace"

# Keep this list intentionally small and source-of-truth oriented.  Hashing the
# whole session_state would make navigation widgets and temporary diagnostics
# invalidate analysis, which is exactly what PERF.RERUN1 must avoid.
INPUT_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    "Setup": (
        "project_name",
        "designer",
        "description",
        "analysis_mode_settings",
        "design_code",
        "code_edition",
        "beam_girder_system_settings",
        "building_beam_girder_service_load_settings",
    ),
    "Materials": (
        "concrete_material",
        "concrete_materials",
        "rebar_materials",
        "prestress_materials",
        "prestress_steel_materials",
        "active_concrete_material_name",
        "active_rebar_material_name",
        "active_prestress_material_name",
        "deck_topping_material_name",
        "deck_material",
        "topping_material",
    ),
    "Section": (
        "section_preset_key",
        "section_parameters",
        "section_geometry",
        "composite_section_settings",
        "effective_width_settings",
        "include_rebars",
        "include_prestress",
    ),
    "Rebar": (
        "rebars",
        "rebars_valid_for_analysis",
        "rebar_input_mode",
        "beam_girder_shear_reinforcement_table",
        "beam_girder_shear_depth_settings",
    ),
    "Prestress": (
        "prestress_table",
        "prestress_elements",
        "prestress_valid_for_analysis",
        "girder_strand_layout_table",
        "girder_prestress_system_settings",
        "girder_prestress_force_states_table",
        "girder_prestress_code_loss_settings",
        "prestress_loss_settings",
    ),
    "Loads": (
        "load_cases",
        "column_uls_loads_table",
        "column_sls_loads_table",
        "beam_uls_loads_table",
        "beam_sls_loads_table",
        "beam_sls_transfer_loads_table",
        "beam_sls_construction_loads_table",
        "beam_sls_service_loads_table",
        "girder_sls_load_components",
        "beam_girder_sls_auto_load_settings",
        "building_beam_girder_service_load_settings",
        "building_beam_girder_sls_load_settings",
    ),
    "Analysis settings": (
        "analysis_settings",
        "include_default_stress_check_points",
        "custom_stress_check_points",
        "girder_sls_limit_settings",
        "girder_deflection_settings",
    ),
}


@dataclass(frozen=True)
class ProjectDirtyStatus:
    model_status: str
    analysis_status: str
    report_status: str
    current_hash: str
    last_analysis_hash: str | None
    changed_groups: tuple[str, ...]
    affected_checks: tuple[str, ...]
    recommended_action: str
    last_refreshed_workspace: str | None = None


def _stable_value(value: Any) -> Any:
    """Return a JSON-stable representation for hashing project inputs."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _stable_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, (list, tuple, set)):
        return [_stable_value(item) for item in value]
    if hasattr(value, "model_dump"):
        try:
            return _stable_value(value.model_dump(mode="json"))
        except Exception:
            try:
                return _stable_value(value.model_dump())
            except Exception:
                pass
    if hasattr(value, "as_metadata"):
        try:
            return _stable_value(value.as_metadata())
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        public = {key: val for key, val in vars(value).items() if not key.startswith("_")}
        return _stable_value(public)
    return repr(value)


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(_stable_value(payload), sort_keys=True, separators=(",", ":"), default=repr).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def input_group_hashes(state: Mapping[str, Any]) -> dict[str, str]:
    return {
        group: _hash_payload({key: state.get(key) for key in keys})
        for group, keys in INPUT_GROUP_KEYS.items()
    }


def project_input_hash(state: Mapping[str, Any]) -> str:
    return _hash_payload(input_group_hashes(state))


def _affected_checks_for_groups(groups: set[str]) -> tuple[str, ...]:
    if not groups:
        return ()
    affected: set[str] = {"Report"}
    if groups & {"Setup", "Materials", "Section", "Rebar", "Prestress", "Loads", "Analysis settings"}:
        affected.update({"ULS", "SLS", "Deflection"})
    if groups & {"Setup", "Loads"}:
        affected.add("Load take-down")
    if groups & {"Rebar", "Prestress", "Section"}:
        affected.add("Section preview")
    order = ["ULS", "SLS", "Deflection", "Load take-down", "Section preview", "Report"]
    return tuple(item for item in order if item in affected)


def update_dirty_state_from_session(state: MutableMapping[str, Any]) -> ProjectDirtyStatus:
    """Update dirty flags from current session input hashes and return status."""

    group_hashes = input_group_hashes(state)
    current_hash = _hash_payload(group_hashes)
    previous_hashes = state.get("_perf_input_group_hashes")
    changed_groups: set[str] = set(state.get(CHANGED_GROUPS_KEY, []) or [])
    if isinstance(previous_hashes, Mapping):
        for group, digest in group_hashes.items():
            if previous_hashes.get(group) != digest:
                changed_groups.add(group)
    else:
        changed_groups = set()

    state["_perf_input_group_hashes"] = dict(group_hashes)
    state[PREVIOUS_INPUT_HASH_KEY] = state.get(CURRENT_INPUT_HASH_KEY)
    state[CURRENT_INPUT_HASH_KEY] = current_hash

    last_analysis_hash = state.get(LAST_ANALYSIS_HASH_KEY)
    if last_analysis_hash and last_analysis_hash != current_hash:
        state[ANALYSIS_STATUS_KEY] = "Out of date"
        state[REPORT_STATUS_KEY] = "Out of date"
    elif last_analysis_hash == current_hash:
        state[ANALYSIS_STATUS_KEY] = "Current"
        state[REPORT_STATUS_KEY] = state.get(REPORT_STATUS_KEY, "Current")
    else:
        state[ANALYSIS_STATUS_KEY] = "Not run"
        state[REPORT_STATUS_KEY] = "Not run"

    state[CHANGED_GROUPS_KEY] = sorted(changed_groups)
    return current_project_dirty_status(state)


def mark_analysis_current(state: MutableMapping[str, Any], *, workspace: str = "Analysis") -> ProjectDirtyStatus:
    """Mark the current active analysis workspace as refreshed for current inputs."""

    current_hash = state.get(CURRENT_INPUT_HASH_KEY) or project_input_hash(state)
    state[CURRENT_INPUT_HASH_KEY] = current_hash
    state[LAST_ANALYSIS_HASH_KEY] = current_hash
    state[ANALYSIS_STATUS_KEY] = "Current"
    state[REPORT_STATUS_KEY] = "Out of date"
    state[LAST_REFRESHED_WORKSPACE_KEY] = workspace
    state[CHANGED_GROUPS_KEY] = []
    return current_project_dirty_status(state)


def current_project_dirty_status(state: Mapping[str, Any]) -> ProjectDirtyStatus:
    current_hash = str(state.get(CURRENT_INPUT_HASH_KEY) or project_input_hash(state))
    last_analysis_hash = state.get(LAST_ANALYSIS_HASH_KEY)
    analysis_status = str(state.get(ANALYSIS_STATUS_KEY) or ("Current" if last_analysis_hash == current_hash else "Out of date" if last_analysis_hash else "Not run"))
    report_status = str(state.get(REPORT_STATUS_KEY) or ("Current" if analysis_status == "Current" else analysis_status))
    changed_groups = tuple(str(item) for item in (state.get(CHANGED_GROUPS_KEY, []) or []))
    affected_checks = _affected_checks_for_groups(set(changed_groups))
    if analysis_status == "Current":
        model_status = "Current"
        action = "No action required. Continue editing or open Results/Report when ready."
    elif analysis_status == "Not run":
        model_status = "Ready"
        action = "Open Analysis when you are ready to run checks."
    else:
        model_status = "Modified"
        action = "Open the relevant Analysis subpage to refresh checks."
    return ProjectDirtyStatus(
        model_status=model_status,
        analysis_status=analysis_status,
        report_status=report_status,
        current_hash=current_hash,
        last_analysis_hash=str(last_analysis_hash) if last_analysis_hash else None,
        changed_groups=changed_groups,
        affected_checks=affected_checks,
        recommended_action=action,
        last_refreshed_workspace=state.get(LAST_REFRESHED_WORKSPACE_KEY),
    )
