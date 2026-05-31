from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_analysis_page_includes_prestress_preview_without_solver_coupling() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")

    assert "GIRDER.SLS1B/PS1B previews" in source
    assert "Prestress Effect" in source
    assert "girder_service_include_prestress" in source
    assert "From Prestress table" in source
    assert "Manual Pe_eff and yps" in source
    assert "Pe_eff is positive compressive effective prestress after losses" in source
    assert "Breaking Load, duct diameter, and strand-count metadata are not used" in source
    assert "Combined Service + Effective Prestress Stress" in source


def test_analysis_page_keeps_prestress_preview_manual_and_not_staged_design() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")

    assert "not a staged prestressed girder design check yet" in source
    assert "AASHTO stress limits" in source
    assert "It is not used by PMM, rebar, prestress, or report solvers" in source
    assert "staged checks are future work" in source
