from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_analysis_page_has_full_length_sls_diagram_preview() -> None:
    assert "GIRDER.SLS4A" in SOURCE
    assert "Full-length SLS stress diagram preview" in SOURCE
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
    assert "Loads page station rows are the source of N and Mx" in SOURCE
    assert "not final code-certified staged design" in SOURCE
    assert "Transfer-length ramp, development, shear, and end-zone checks remain future work" in SOURCE


def test_full_length_sls_diagram_has_preview_limit_lines_and_governing_cards() -> None:
    assert "Compression preview limit" in SOURCE
    assert "Tension preview limit" in SOURCE
    assert "Governing compression" in SOURCE
    assert "Governing tension" in SOURCE
    assert "Preview PASS" in SOURCE
    assert "Preview FAIL" in SOURCE
    assert "AASHTO default preview line" in SOURCE


def test_full_length_sls_diagram_groups_one_case_name_at_a_time() -> None:
    assert "diagram load case" in SOURCE
    assert "The diagram connects station rows with the same Case Name" in SOURCE
    assert "it does not generate an envelope or interpolate missing load effects" in SOURCE


def test_sls4a1_decision_workspace_collapses_audit_controls() -> None:
    assert "SLS result workspace" in SOURCE
    assert "Default view shows the full-length decision diagram" in SOURCE
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
