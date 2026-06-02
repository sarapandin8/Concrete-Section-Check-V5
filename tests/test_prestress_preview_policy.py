from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRESTRESS_SOURCE = (ROOT / "concrete_pmm_pro" / "ui" / "prestress_page.py").read_text()
REBAR_SOURCE = (ROOT / "concrete_pmm_pro" / "ui" / "rebar_page.py").read_text()


def test_prestress_page_default_preview_hides_ordinary_rebar():
    assert "Section Preview with Prestress" in PRESTRESS_SOURCE
    assert "Default preview shows prestressing steel only" in PRESTRESS_SOURCE
    assert "prestress_only_section_preview" in PRESTRESS_SOURCE
    assert "create_section_preview(\n            geometry,\n            dimensions,\n            \"symbol_value\",\n            [],\n            active_prestress" in PRESTRESS_SOURCE


def test_rebar_page_default_preview_hides_prestressing_steel():
    assert "Section Preview with Rebar" in REBAR_SOURCE
    assert "Default preview shows ordinary rebar only" in REBAR_SOURCE
    assert "rebar_section_preview" in REBAR_SOURCE
    assert "create_section_preview(\n                geometry,\n                st.session_state.get(\"section_dimensions\", []),\n                \"symbol_value\",\n                st.session_state[\"rebars\"],\n                []," in REBAR_SOURCE


def test_combined_reinforcement_preview_is_explicit_and_collapsed():
    assert "Combined Reinforcement Preview" in PRESTRESS_SOURCE
    assert "Combined Reinforcement Preview" in REBAR_SOURCE
    assert "Coordination view only" in PRESTRESS_SOURCE
    assert "Coordination view only" in REBAR_SOURCE
    assert "prestress_combined_reinforcement_preview" in PRESTRESS_SOURCE
    assert "rebar_combined_reinforcement_preview" in REBAR_SOURCE
