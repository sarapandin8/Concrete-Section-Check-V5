from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_analysis_page_includes_manual_service_stage_preview_without_solver_coupling() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")

    assert "Manual Service Stage Stress Preview" in source
    assert "girder_stage_preview_enabled" in source
    assert "default_girder_service_stage_templates" in source
    assert "GirderServiceStageCase" in source
    assert "run_girder_service_stage_stress" in source
    assert "girder_service_stage_result_rows" in source
    assert "Stage templates are guidance only" in source
    assert "Results remain preview-only" in source


def test_analysis_page_stage_preview_keeps_prestress_effective_force_guards() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")

    assert "Pe_eff is positive for compression after losses" in source
    assert "Breaking Load, duct diameter, and strand-count metadata are not used" in source
    assert "No AASHTO stress limits" in source
    assert "not used by PMM, rebar, prestress, load-table, or report workflows" in source
