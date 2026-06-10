from __future__ import annotations

from concrete_pmm_pro.state.dirty_state import (
    ANALYSIS_STATUS_KEY,
    LAST_ANALYSIS_HASH_KEY,
    CHANGED_GROUPS_KEY,
    current_project_dirty_status,
    mark_analysis_current,
    update_dirty_state_from_session,
)


def test_perf_rerun1_first_update_does_not_mark_clean_project_dirty() -> None:
    state = {"project_name": "A", "design_code": "ACI 318"}

    status = update_dirty_state_from_session(state)

    assert status.analysis_status == "Not run"
    assert state[CHANGED_GROUPS_KEY] == []


def test_perf_rerun1_input_change_marks_analysis_out_of_date_after_analysis_run() -> None:
    state = {"project_name": "A", "design_code": "ACI 318"}
    update_dirty_state_from_session(state)
    mark_analysis_current(state, workspace="Analysis / ULS")

    state["design_code"] = "AASHTO LRFD"
    status = update_dirty_state_from_session(state)

    assert status.analysis_status == "Out of date"
    assert state[ANALYSIS_STATUS_KEY] == "Out of date"
    assert "Setup" in status.changed_groups
    assert "ULS" in status.affected_checks


def test_perf_rerun1_current_material_keys_mark_analysis_out_of_date() -> None:
    state = {"prestress_materials": [{"name": "PT Bar 32", "fpu_MPa": 1230.0}]}
    update_dirty_state_from_session(state)
    mark_analysis_current(state, workspace="Analysis / ULS")

    state["prestress_materials"] = [{"name": "PT Bar 32", "fpu_MPa": 1860.0}]
    status = update_dirty_state_from_session(state)

    assert status.analysis_status == "Out of date"
    assert "Materials" in status.changed_groups


def test_perf_rerun1_current_prestress_table_marks_analysis_out_of_date() -> None:
    state = {"prestress_table": [{"Active": True, "Label": "PS1", "Pe_eff_kN": 120.0}]}
    update_dirty_state_from_session(state)
    mark_analysis_current(state, workspace="Analysis / SLS")

    state["prestress_table"] = [{"Active": True, "Label": "PS1", "Pe_eff_kN": 150.0}]
    status = update_dirty_state_from_session(state)

    assert status.analysis_status == "Out of date"
    assert "Prestress" in status.changed_groups


def test_perf_rerun1_current_beam_sls_load_table_marks_analysis_out_of_date() -> None:
    state = {"beam_sls_loads_table": [{"Active": True, "Case Name": "SLS-1", "Mx": 500.0}]}
    update_dirty_state_from_session(state)
    mark_analysis_current(state, workspace="Analysis / SLS")

    state["beam_sls_loads_table"] = [{"Active": True, "Case Name": "SLS-1", "Mx": 650.0}]
    status = update_dirty_state_from_session(state)

    assert status.analysis_status == "Out of date"
    assert "Loads" in status.changed_groups


def test_perf_rerun1_mark_analysis_current_clears_changed_groups() -> None:
    state = {"project_name": "A", "design_code": "ACI 318"}
    update_dirty_state_from_session(state)
    mark_analysis_current(state, workspace="Analysis / ULS")
    state["beam_uls_loads_table"] = [{"Active": True, "Station x (m)": 1.0, "Mux": 10.0}]
    update_dirty_state_from_session(state)

    status = mark_analysis_current(state, workspace="Analysis / ULS")

    assert status.analysis_status == "Current"
    assert state[CHANGED_GROUPS_KEY] == []
    assert state[LAST_ANALYSIS_HASH_KEY] == status.current_hash


def test_perf_rerun1_current_status_reports_not_run_without_analysis_hash() -> None:
    state = {"project_name": "A"}
    update_dirty_state_from_session(state)

    status = current_project_dirty_status(state)

    assert status.analysis_status == "Not run"
    assert status.recommended_action.startswith("Open Analysis")
