from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_analysis_page_exposes_code_limit_preview_without_solver_coupling() -> None:
    assert "CODE.SLS.LIMIT3" in SOURCE
    assert "Enable PASS/FAIL preview" in SOURCE
    assert "Design code profile" in SOURCE
    assert "Limit profile" in SOURCE
    assert "Use manual override values" in SOURCE
    assert "girder_sls_limit_profile_options" in SOURCE
    assert "Compact preview only" in SOURCE
    assert "DEFAULT_GIRDER_SLS_CODES" in SOURCE
    assert "This is not a final code-certified check" in SOURCE
    assert "Code Limit Summary" in SOURCE
    assert "Code check status" in SOURCE
    assert "Preview status" in SOURCE
    assert "REVIEW" in SOURCE
    assert "NOT CHECKED" in SOURCE
    assert "does not alter stress values" in SOURCE


def test_analysis_page_code_limit_preview_checks_quick_combined_and_stage_results() -> None:
    assert "SLS check case" in SOURCE
    assert "Combined service plus prestress stress" in SOURCE
    assert "Manual service stage stress" in SOURCE
    assert "_girder_stress_limit_input_rows_from_dataframe" in SOURCE
    assert "run_girder_service_stress_limit_check" in SOURCE
    assert "girder_service_limit_check_rows" in SOURCE


def test_analysis_page_code_limit_status_card_is_no_longer_future_only() -> None:
    assert '"value": "Optional preview"' in SOURCE
    assert "AASHTO + ACI editable limit profiles" in SOURCE


def test_analysis_page_exposes_stage_aware_code_limit_controls() -> None:
    assert "Stage strength basis" in SOURCE
    assert "Prestress force basis" in SOURCE
    assert "Recommended section basis" in SOURCE
    assert "f'ci" in SOURCE
    assert "Pe_eff" in SOURCE
    assert "losses are not calculated automatically" in SOURCE.lower()


def test_analysis_page_routes_girder_code_limit_preview_from_workflow_code() -> None:
    preview_block = SOURCE[SOURCE.find("def _render_girder_code_limit_preview"):SOURCE.find("def _render_beam_girder_service_stress_preview")]

    assert "_girder_sls_project_design_code_from_session()" in preview_block
    assert "_girder_sls_profile_code_from_session()" in preview_block
    assert "project_design_code = project_design_code_from_session(st.session_state)" not in preview_block


def test_analysis_page_shows_limit_formulas_and_consistency_warnings() -> None:
    assert "Compression formula" in SOURCE
    assert "Tension formula" in SOURCE
    assert "Limit formulas and code-basis audit" in SOURCE
    assert "Engineering consistency warnings" in SOURCE
    assert "girder_sls_stage_basis_consistency_warnings" in SOURCE
    assert "girder_sls_limit_formula_summary" in SOURCE
    assert "section_basis_label" in SOURCE
    assert "load_stage" in SOURCE
    assert "load_component" in SOURCE


def test_analysis_page_compares_actual_stress_against_matching_limits() -> None:
    assert "_girder_stress_vs_limit_cards" in SOURCE
    assert "Compression actual / limit" in SOURCE
    assert "Tension actual / limit" in SOURCE
    assert "compression demand uses compression limit" in SOURCE
    assert "tension demand uses tension limit" in SOURCE
    assert "matching stress type" in SOURCE


def test_analysis_page_threads_transfer_prestress_requirement_context_into_limit_preview() -> None:
    assert "stress_includes_prestress" in SOURCE
    assert "prestress_force_state_label" in SOURCE
    assert "Transfer / Release checks normally require Pe_transfer" in SOURCE or "Pe_eff after losses" in SOURCE
    assert "current GIRDER.PS1B preview force" in SOURCE
