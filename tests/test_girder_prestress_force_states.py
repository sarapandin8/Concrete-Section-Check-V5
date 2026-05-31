from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESTRESS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "prestress_page.py").read_text(encoding="utf-8")
ANALYSIS_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")
PROJECT_IO_SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "io" / "project_io.py").read_text(encoding="utf-8")


def test_prestress_page_exposes_three_stage_force_state_inputs() -> None:
    assert "Girder SLS Prestress Force States" in PRESTRESS_SOURCE
    assert "Pe_transfer / P_release" in PRESTRESS_SOURCE
    assert "Pe_construction" in PRESTRESS_SOURCE
    assert "Pe_eff_final" in PRESTRESS_SOURCE
    assert "girder_prestress_force_states_table" in PRESTRESS_SOURCE
    assert "No automatic loss calculation is performed" in PRESTRESS_SOURCE


def test_analysis_page_uses_stage_force_state_before_legacy_pe_eff_sources() -> None:
    assert "From Prestress force state" in ANALYSIS_SOURCE
    assert "_girder_prestress_force_state_for_stage" in ANALYSIS_SOURCE
    assert "Pe_transfer / P_release from Prestress force state" in ANALYSIS_SOURCE
    assert "Pe_construction from Prestress force state" in ANALYSIS_SOURCE
    assert "Pe_eff_final from Prestress force state" in ANALYSIS_SOURCE
    assert "Stage prestress is an internal section action" in ANALYSIS_SOURCE


def test_project_io_preserves_girder_prestress_force_state_metadata() -> None:
    assert "girder_prestress_force_states_table" in PROJECT_IO_SOURCE
    assert "_girder_prestress_force_states_metadata_from_session" in PROJECT_IO_SOURCE
