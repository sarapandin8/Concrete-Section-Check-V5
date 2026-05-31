from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_analysis_page_exposes_code_limit_preview_without_solver_coupling() -> None:
    assert "CODE.SLS.LIMIT1" in SOURCE
    assert "Enable code stress-limit preview" in SOURCE
    assert "Girder SLS code profile" in SOURCE
    assert "DEFAULT_GIRDER_SLS_CODES" in SOURCE
    assert "This is not a final code-certified check" in SOURCE
    assert "does not change any stress" in SOURCE


def test_analysis_page_code_limit_preview_checks_quick_combined_and_stage_results() -> None:
    assert "Quick trial service stress" in SOURCE
    assert "Combined service plus prestress stress" in SOURCE
    assert "Manual service stage stress" in SOURCE
    assert "_girder_stress_limit_input_rows_from_dataframe" in SOURCE
    assert "run_girder_service_stress_limit_check" in SOURCE
    assert "girder_service_limit_check_rows" in SOURCE


def test_analysis_page_code_limit_status_card_is_no_longer_future_only() -> None:
    assert '"value": "Optional preview"' in SOURCE
    assert "AASHTO + ACI editable limit profiles" in SOURCE
