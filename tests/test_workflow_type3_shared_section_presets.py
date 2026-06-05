from __future__ import annotations

from concrete_pmm_pro.core.reinforcement_system import default_section_reinforcement_flags


def test_building_shared_precast_i_girder_defaults_to_prestressing_enabled() -> None:
    ordinary, prestress = default_section_reinforcement_flags(
        member_type="building_beam_girder",
        section_category="Precast Composite Girder",
        section_preset_key="parametric_i_girder",
        girder_section_family="precast_composite_girder",
    )

    assert ordinary is False
    assert prestress is True


def test_building_basic_beam_defaults_to_rc_rebar_enabled() -> None:
    ordinary, prestress = default_section_reinforcement_flags(
        member_type="building_beam_girder",
        section_category="Basic Solid",
        section_preset_key="rectangle",
        girder_section_family="general_non_composite_girder",
    )

    assert ordinary is True
    assert prestress is False
