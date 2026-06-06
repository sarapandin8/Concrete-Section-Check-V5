from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_analysis_page_has_full_length_sls_diagram_preview() -> None:
    assert "GIRDER.SLS4A" in SOURCE
    assert "Full-length SLS stress check diagram" in SOURCE
    assert "_render_girder_full_length_sls_diagram" in SOURCE
    assert "_make_girder_full_length_sls_figure" in SOURCE
    assert "Station x (m)" in SOURCE
    assert "Top total stress" in SOURCE
    assert "Bottom total stress" in SOURCE


def test_full_length_sls_diagram_uses_loads_and_stage_pe_without_solver_changes() -> None:
    assert "evaluate_girder_prestress_station" in SOURCE
    assert "Pe stage (kN)" in SOURCE
    assert "pe_transfer_eff_kN" in SOURCE
    assert "pe_construction_eff_kN" in SOURCE
    assert "pe_eff_final_eff_kN" in SOURCE
    assert "Loads page station rows provide user/imported N and Mx" in SOURCE
    assert "not final code-certified staged design" in SOURCE
    assert "Transfer-length ramp, development, shear, and end-zone checks remain future work" in SOURCE


def test_full_length_sls_diagram_has_preview_limit_lines_and_governing_cards() -> None:
    assert "Compression preview limit" in SOURCE
    assert "Tension preview limit" in SOURCE
    assert "Governing compression" in SOURCE
    assert "Governing tension" in SOURCE
    assert "Preview PASS" in SOURCE
    assert "Preview FAIL" in SOURCE
    assert "Design code / limit basis" in SOURCE


def test_full_length_sls_diagram_groups_one_case_name_at_a_time() -> None:
    assert "diagram load case" in SOURCE
    assert "The diagram connects station rows with the same Case Name" in SOURCE
    assert "GIRDER.SLS5A generates a span station grid" in SOURCE


def test_sls4a1_decision_workspace_collapses_audit_controls() -> None:
    assert "SLS result workspace" in SOURCE
    assert "Default view is for checking top/bottom stresses along the girder length" in SOURCE
    assert "Load / section / single-station audit" in SOURCE
    assert "expanded=False" in SOURCE
    assert "legacy single-station SLS check/audit panels" in SOURCE


def test_sls4b_has_combined_governing_stage_result_summary() -> None:
    assert "GIRDER.SLS4B" in SOURCE
    assert "Governing station / stage result summary" in SOURCE
    assert "_render_girder_sls4b_combined_stage_result_table" in SOURCE
    assert "actual stress versus the matching preview limit" in SOURCE
    assert "controlling fiber" in SOURCE
    assert "Overall SLS preview" in SOURCE
    assert "Controlling stage" in SOURCE


def test_sls4b_result_table_reports_utilization_without_solver_changes() -> None:
    assert "_girder_sls4b_governing_demand_rows" in SOURCE
    assert "_girder_sls4b_stage_decision_row" in SOURCE
    assert "Utilization" in SOURCE
    assert "Limit stress (MPa)" in SOURCE
    assert "Compression / tension demand details" in SOURCE
    assert "no stress formula" in SOURCE
    assert "no solver, Pe, load, geometry, or report" in SOURCE



def test_sls4c_stage_decision_workflow_hides_nonessential_controls() -> None:
    assert "GIRDER.SLS4C" in SOURCE
    assert "Full-length SLS stress check diagram" in SOURCE
    assert "SLS check basis" in SOURCE
    assert "Stage result summary" in SOURCE
    assert "Design code / limit basis" in SOURCE
    assert "Limit stage is auto-selected from the active tab" in SOURCE
    assert "Engineering action hints" in SOURCE
    assert "Advanced Serviceability / SLS Foundation settings" in SOURCE


def test_sls4c_code_limit_stage_is_locked_to_active_stage_tab() -> None:
    assert "locked_stage_label" in SOURCE
    assert "Auto limit stage" in SOURCE
    assert "active Transfer/Construction/Service tab" in SOURCE
    assert 'st.selectbox(\n                "Stress limit stage"' not in SOURCE
    assert "The limit stage is not user-selected inside a stage tab" in SOURCE


def test_sls4c_graph_marks_governing_demands_without_solver_changes() -> None:
    assert "Governing compression" in SOURCE
    assert "Governing tension" in SOURCE
    assert "Governing {demand.lower()}" in SOURCE
    assert "no stress solver, Pe(x), load, section-basis, or code-limit formula changes" in SOURCE



def test_sls_graph1_has_commercial_style_stress_diagram_polish() -> None:
    assert "SLS.GRAPH1" in SOURCE
    assert "Concrete Stress —" in SOURCE
    assert "Distance from left end of member (m)" in SOURCE
    assert "Stress (MPa) · compression negative / tension positive" in SOURCE
    assert "Maximum stress at top of member" in SOURCE
    assert "Minimum stress at bottom of member" in SOURCE
    assert "Compression limit" in SOURCE
    assert "Tension limit" in SOURCE
    assert "Gov. {demand}" in SOURCE
    assert "legend={\"orientation\": \"h\"" in SOURCE


def test_sls_graph1_preserves_internal_sign_convention() -> None:
    assert "keeps the internal app convention" in SOURCE
    assert "compression is negative and tension is positive" in SOURCE
    assert "display-only" in SOURCE
    assert "no stress solver, Pe(x), load, section-basis, or code-limit formula changes" in SOURCE


def test_sls_limit4_has_reinforcement_aware_tension_limit_guide() -> None:
    assert "CODE.SLS.LIMIT4" in SOURCE
    assert "Tensile stress limit guide" in SOURCE
    assert "Use guided tensile limit profile" in SOURCE
    assert "Auto from current ordinary rebar layout" in SOURCE
    assert "Verified bonded tension reinforcement" in SOURCE
    assert "Auto rebar detection is a screening aid only" in SOURCE


def test_sls_limit4_1_tensile_limit_guide_is_visible_in_full_length_diagram() -> None:
    assert "CODE.SLS.LIMIT4.1" in SOURCE
    assert "_render_girder_sls_diagram_tensile_limit_guide" in SOURCE
    assert "expanded=True" in SOURCE
    assert "Selected by the visible tensile stress limit guide" in SOURCE
    assert "graph limit lines and stage PASS/FAIL preview update from this profile" in SOURCE


def test_sls_limit4_2_visible_guide_shows_formula_and_non_service_aci_note() -> None:
    assert "CODE.SLS.LIMIT4.2" in SOURCE
    assert "Selected tensile limit" in SOURCE
    assert "Tension formula substitution" in SOURCE
    assert "ACI Class U / Class T service classification changes the Service-stage tensile limit only" in SOURCE
    assert "Not applied to Transfer/Construction" in SOURCE


def test_sls_limit5_adds_aci_transfer_end_zone_piecewise_limit() -> None:
    assert "CODE.SLS.LIMIT5" in SOURCE
    assert "aci_transfer_end_zone_verified" in SOURCE
    assert "ACI transfer end-zone limit" in SOURCE
    assert "0.50√f'ci" in SOURCE
    assert "0.25√f'ci" in SOURCE
    assert "Transfer length 60db" in SOURCE
    assert "Building precast prestressed girder Transfer preview" in SOURCE


def test_sls_limit5_2_aci_end_zone_controls_render_once_to_avoid_duplicate_keys() -> None:
    assert "show_end_zone_controls: bool = True" in SOURCE
    assert "show_end_zone_controls=False" in SOURCE
    assert "End-zone length controls are shown in the visible full-length diagram guide" in SOURCE


def test_service_comp1_splits_final_service_beam_and_cip_concrete_stress() -> None:
    assert "SERVICE.COMP1" in SOURCE
    assert "Final Service concrete stress split" in SOURCE
    assert "Concrete Stress (beam) — Final Service" in SOURCE
    assert "Concrete Stress (CIP) — Final Service" in SOURCE
    assert "_render_final_service_beam_cip_concrete_split" in SOURCE
    assert "CIP stress is scaled by n=Edeck/Ebeam" in SOURCE
    assert "0.60f'c compression, fr=0.62√f'c tension" in SOURCE


def test_service_comp2_adds_staged_composite_final_service_engine() -> None:
    assert "SERVICE.COMP2" in SOURCE
    assert "staged composite final-service stress engine" in SOURCE
    assert "Locked-in pre-composite stress (MPa)" in SOURCE
    assert "Final prestress stress (MPa)" in SOURCE
    assert "Composite increment stress (MPa)" in SOURCE
    assert "CIP/topping receives composite-stage increments only" in SOURCE
    assert "CIP receives no direct prestress stress" in SOURCE
    assert "long-term redistribution, shrinkage compatibility, deflection, shear, and detailing checks remain future milestones" in SOURCE


def test_service_comp2_1_hides_service_overview_behind_split_graphs() -> None:
    assert "SERVICE.COMP2.1" in SOURCE
    assert "Overall transformed-section stress overview — Service" in SOURCE
    assert "audit/reference graph only" in SOURCE
    assert "Use the visible Beam and CIP final-service stress checks above" in SOURCE
    assert "service_split_rendered" in SOURCE
