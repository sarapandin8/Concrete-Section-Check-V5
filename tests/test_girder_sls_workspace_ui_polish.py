from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_girder_sls_workspace_has_readiness_cards_and_compact_headings() -> None:
    assert "Beam/Girder SLS Stress Workspace" in SOURCE
    assert "Workspace status" in SOURCE
    assert "Manual preview only" in SOURCE
    assert "Code stress limits" in SOURCE
    assert "AASHTO + ACI editable limit profiles" in SOURCE
    assert "Quick Elastic Stress Trial" in SOURCE
    assert "Manual Service Stage Stress Preview" in SOURCE


def test_girder_sls_workspace_formats_zero_stress_without_negative_zero() -> None:
    assert "_GIRDER_DISPLAY_ZERO_TOLERANCE_MPA" in SOURCE
    assert "_format_girder_stress_mpa" in SOURCE
    assert "-0.000 MPa" not in SOURCE
    assert "Quick elastic stress result table" in SOURCE
    assert "Code Stress Limit Preview" in SOURCE
    assert "Design code profile" in SOURCE
    assert "Selected limit profile" in SOURCE
    assert "Quick trial service stress" in SOURCE


def test_girder_sls_workspace_keeps_design_limits_as_future_work() -> None:
    assert "AASHTO/ACI clause calibration" in SOURCE
    assert "CODE.SLS.LIMIT1" in SOURCE
    assert "It is not used by PMM, rebar, prestress, or report solvers" in SOURCE
    assert "manual stage actions" in SOURCE
    assert "code-check workflow" in SOURCE
