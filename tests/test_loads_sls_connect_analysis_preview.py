from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "analysis_page.py").read_text(encoding="utf-8")


def test_analysis_preview_can_read_beam_girder_sls_rows_from_loads_page() -> None:
    assert "LOADS.SLS.CONNECT1" in SOURCE
    assert "_beam_sls_load_rows_from_session_state" in SOURCE
    assert 'st.session_state.get("beam_sls_loads_table")' in SOURCE
    assert "From Loads page — SLS Girder Service Loads" in SOURCE
    assert "Load source for {stage_label}" in SOURCE
    assert "manual input is a stage-level override/fallback" in SOURCE


def test_loads_to_analysis_preview_uses_n_and_mx_without_double_counting_live_load() -> None:
    assert "_analysis_float_or_zero(selected_load_row.get(\"N\"))" in SOURCE
    assert "_analysis_float_or_zero(selected_load_row.get(\"Mx\"))" in SOURCE
    assert "My, Vy, Vx, and T remain stored for future" in SOURCE
    assert "Total SLS resultant including SDL and LL+IM" in SOURCE


def test_loads_to_analysis_preview_respects_direct_section_basis_only() -> None:
    assert "_DIRECT_BEAM_SLS_BASIS_MAP" in SOURCE
    assert '"precast gross": "precast_gross"' in SOURCE
    assert '"composite transformed": "composite_transformed"' in SOURCE
    assert "staged/mixed or unsupported section basis" in SOURCE
    assert "Preview section basis for selected Loads row" in SOURCE


def test_analysis_preview_groups_beam_girder_sls_rows_into_always_on_stage_tabs() -> None:
    assert "ANALYSIS.SLS1" in SOURCE
    assert "LOADS.SLS2B" in SOURCE
    assert "_beam_sls_stage_tab_specs" in SOURCE
    assert "SLS stage check tabs" in SOURCE
    assert "Stage checks are always available" in SOURCE
    assert "{stage_label} load case from Loads page" in SOURCE
    assert "Transfer stage" in SOURCE
    assert "Construction stage" in SOURCE
    assert "Service stage" in SOURCE
    assert "Each stage keeps its own code-limit/profile/prestress UI state" in SOURCE
    assert "Station x (m)" in SOURCE
    assert "x={station_text} m" in SOURCE


def test_analysis_stage_tabs_keep_manual_override_as_stage_fallback() -> None:
    assert "Manual override" in SOURCE
    assert "Use manual override for a trial check or import stage loads first" in SOURCE
    assert "commercial workflow should normally read the matching stage row from Loads" in SOURCE
    assert "_beam_sls_default_basis_for_stage" in SOURCE
    assert 'stage_label == "Service stage" and "composite_transformed" in available_basis_names' in SOURCE


def test_analysis_normalizes_imported_section_basis_text_before_routing() -> None:
    assert "LOADS.IMPORT1.2" in SOURCE
    assert "_beam_sls_normalized_section_basis_text" in SOURCE
    assert "Composite transformed section" in SOURCE
    assert "_beam_sls_requested_basis_key" in SOURCE
    assert '"composite transformed section": "composite_transformed"' in SOURCE


def test_analysis_warns_when_service_row_requests_composite_but_basis_is_not_active() -> None:
    assert "requests Composite transformed section, but composite transformed properties are not active" in SOURCE
    assert "Enable composite deck/topping metadata in Section Builder" in SOURCE
    assert "intentionally choose a precast-gross preview below" in SOURCE
