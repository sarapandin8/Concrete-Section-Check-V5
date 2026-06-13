from __future__ import annotations

from pathlib import Path

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.geometry.presets import preset_by_key
from concrete_pmm_pro.ui import section_builder


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_section_builder_professional_layout_sections_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Definition" in source
    assert "Concrete Material Assignment" in source
    assert "Live Section Preview" in source
    assert "Section Properties" in source
    assert "cpmm-section-property-grid" in source
    assert "Geometry Parameters" in source
    assert "st.sidebar" not in source


def test_section_builder_keeps_rectangle_geometry_generation_path() -> None:
    preset = preset_by_key("rectangle")

    geometry, dimensions, validation = section_builder._build_geometry(preset, {"width_mm": 400.0, "height_mm": 600.0})

    assert validation.is_valid
    assert validation.errors == []
    assert geometry is not None
    assert geometry.name == "Rectangle"
    assert len(dimensions) > 0


def test_rectangle_width_height_remain_section_builder_parameters() -> None:
    rectangle = preset_by_key("rectangle")
    labels = [parameter["label"] for parameter in rectangle["parameters"]]

    assert "Width B (mm)" in labels
    assert "Height H (mm)" in labels


def test_rectangular_chamfered_uses_separate_x_y_chamfer_parameters() -> None:
    preset = preset_by_key("rectangular_chamfered")
    labels = [parameter["label"] for parameter in preset["parameters"]]
    names = [parameter["name"] for parameter in preset["parameters"]]

    assert "Chamfer x cx (mm)" in labels
    assert "Chamfer y cy (mm)" in labels
    assert "chamfer_x_mm" in names
    assert "chamfer_y_mm" in names
    assert "chamfer_mm" not in names


def test_section_builder_rectangular_chamfered_builds_asymmetric_chamfer() -> None:
    preset = preset_by_key("rectangular_chamfered")

    geometry, dimensions, validation = section_builder._build_geometry(
        preset,
        {"width_mm": 500.0, "height_mm": 700.0, "chamfer_x_mm": 80.0, "chamfer_y_mm": 40.0},
    )

    assert validation.is_valid
    assert geometry is not None
    assert geometry.metadata["chamfer_x_mm"] == 80.0
    assert geometry.metadata["chamfer_y_mm"] == 40.0
    assert [item.symbol for item in dimensions] == ["B", "H", "cx", "cy"]


def test_section_builder_rectangular_chamfered_legacy_chamfer_mm_params_still_build() -> None:
    preset = preset_by_key("rectangular_chamfered")

    geometry, dimensions, validation = section_builder._build_geometry(
        preset,
        {"width_mm": 500.0, "height_mm": 700.0, "chamfer_mm": 50.0},
    )

    assert validation.is_valid
    assert geometry is not None
    assert geometry.metadata["chamfer_x_mm"] == 50.0
    assert geometry.metadata["chamfer_y_mm"] == 50.0
    assert [item.symbol for item in dimensions] == ["B", "H", "cx", "cy"]


def test_section_builder_status_panel_helper_escapes_values() -> None:
    html = section_builder._status_panel_html(
        [section_builder.SectionMetric("Area <gross>", "400 > 300", "safe & escaped", "info", strong=True)]
    )

    assert "Area &lt;gross&gt;" in html
    assert "400 &gt; 300" in html


def test_section_builder_property_strip_helper_escapes_values() -> None:
    html = section_builder._property_strip_html(
        [section_builder.SectionMetric("Preset <A>", "Rect > Box", "quiet & compact")]
    )

    assert "cpmm-section-property-grid" in html
    assert "Preset &lt;A&gt;" in html
    assert "Rect &gt; Box" in html
    assert "quiet &amp; compact" in html


def test_section_builder_properties_are_compact_strip_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "_property_strip_html" in source
    assert "Gross Area" in source
    assert "Centroid" in source
    assert "Holes / Voids" in source
    assert "Readiness" in source
    assert "Key Properties" not in source
    assert "Geometry Context" not in source


def test_section_builder_validation_summary_is_compact_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "No validation errors" not in source
    assert "WARNING: none" not in source
    assert "_status_panel_html" in source


def test_section_property_clarity_labels_are_present() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Precast Gross Section Properties" in source
    assert "Composite slab/topping properties are metadata" in source
    assert "Centroid yb" in source
    assert "from bottom fiber" in source
    assert "ctop" in source
    assert "cbottom" in source
    assert "Section property convention" in source
    assert "Tslab, Be, n, and Btransformed are not merged" in source
    assert "Deck/topping material is used for composite metadata" in source



def test_section_type_selector_uses_stable_preset_keys() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "section_preset_selector_key" in source
    assert "selected_preset_key = st.selectbox" in source
    assert "format_func=lambda key" in source
    assert 'st.session_state["section_preset_key"] = str(selected_preset_key)' in source


def test_preset_option_label_keeps_display_name_and_category() -> None:
    rectangle = preset_by_key("rectangle")

    assert section_builder._preset_option_label(rectangle) == "Rectangle  ·  Basic Solid"


def test_preset_maps_are_key_based_and_labelled() -> None:
    rectangle = preset_by_key("rectangle")
    i_girder = preset_by_key("parametric_i_girder")

    keys, preset_map, label_map = section_builder._preset_maps([rectangle, i_girder])

    assert keys == ["rectangle", "parametric_i_girder"]
    assert preset_map["parametric_i_girder"]["display_name"] == "Precast I-Girder"
    assert label_map["parametric_i_girder"].startswith("Precast I-Girder")
    assert label_map["parametric_i_girder"] == "Precast I-Girder  ·  Precast Composite Girder"


def test_plank_material_modulus_inputs_are_hidden_from_normal_geometry_editor() -> None:
    plank = preset_by_key("parametric_plank_girder_interior")

    assert section_builder._hidden_material_parameter_names(plank) == {"Ebeam_MPa", "Edeck_MPa"}


def test_plank_material_assignment_source_includes_transformed_width_metadata() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "DEFAULT_DECK_TOPPING_MATERIAL" in source
    assert "n = Edeck/Ebeam" in source
    assert "Btransformed = n x Be" in source


def test_material_assignment_uses_canonical_session_keys() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert 'key="active_concrete_material_name"' in source
    assert 'key="deck_topping_material_name"' in source
    assert 'key="section_primary_concrete_material_name"' not in source
    assert 'key="section_deck_topping_material_name"' not in source


def test_member_type_guidance_source_is_present_in_section_builder() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Member Workflow Guidance" in source
    assert "Bridge Beam/Girder workflow is active" in source
    assert "Building Beam/Girder under ACI 318" in source
    assert "Column / Pier / Wall / Pylon PMM" in source
    assert "WORKFLOW.TYPE3: same physical section geometry can be reused" in source


def test_column_pier_member_type_filters_out_girder_presets() -> None:
    rectangle = preset_by_key("rectangle")
    circular_hollow = preset_by_key("circular_hollow")
    i_girder = preset_by_key("parametric_i_girder")
    box_girder = preset_by_key("single_cell_box_girder")
    custom_preset = {"key": "custom_polygon", "display_name": "Custom Polygon", "category": "Custom"}

    filtered = section_builder._filter_presets_for_member_type(
        [rectangle, circular_hollow, i_girder, box_girder, custom_preset],
        AnalysisModeSettings(member_type="column_pier_pmm"),
    )
    keys = {preset["key"] for preset in filtered}

    assert "rectangle" in keys
    assert "circular_hollow" in keys
    assert "custom_polygon" in keys
    assert "parametric_i_girder" not in keys
    assert "single_cell_box_girder" not in keys


def test_building_beam_girder_allows_basic_beams_and_shared_precast_i_girder_only() -> None:
    rectangle = preset_by_key("rectangle")
    circular_hollow = preset_by_key("circular_hollow")
    i_girder = preset_by_key("parametric_i_girder")
    plank = preset_by_key("parametric_plank_girder_interior")
    box_beam = preset_by_key("box_section_fillet")
    u_girder = preset_by_key("u_girder")
    psc_i = preset_by_key("psc_i_girder")
    custom_preset = {"key": "custom_polygon", "display_name": "Custom Polygon", "category": "Custom"}

    filtered = section_builder._filter_presets_for_member_type(
        [rectangle, circular_hollow, i_girder, plank, box_beam, u_girder, psc_i, custom_preset],
        AnalysisModeSettings(member_type="building_beam_girder"),
    )
    keys = {preset["key"] for preset in filtered}

    assert "rectangle" in keys
    assert "circular_hollow" in keys
    assert "custom_polygon" in keys
    assert "psc_i_girder" in keys
    assert "parametric_i_girder" in keys
    assert "parametric_plank_girder_interior" not in keys
    assert "box_section_fillet" not in keys
    assert "u_girder" not in keys


def test_building_beam_girder_enables_shared_i_girder_composite_metadata_but_not_aashto_helper() -> None:
    i_girder = preset_by_key("parametric_i_girder")

    assert section_builder._composite_metadata_enabled_for_workflow(
        i_girder, AnalysisModeSettings(member_type="beam_girder")
    )
    assert section_builder._composite_metadata_enabled_for_workflow(
        i_girder, AnalysisModeSettings(member_type="building_beam_girder")
    )
    assert section_builder._aashto_effective_width_helper_enabled(
        i_girder, AnalysisModeSettings(member_type="beam_girder")
    )
    assert not section_builder._aashto_effective_width_helper_enabled(
        i_girder, AnalysisModeSettings(member_type="building_beam_girder")
    )


def test_building_beam_girder_filter_description_mentions_shared_geometry_guard() -> None:
    text = section_builder._member_type_filter_description(
        AnalysisModeSettings(member_type="building_beam_girder")
    )

    assert "shared precast girder geometry" in text
    assert "Bridge-specific load/stage/AASHTO Be tools stay hidden" in text


def test_beam_girder_member_type_filters_out_column_basic_presets() -> None:
    rectangle = preset_by_key("rectangle")
    circular_hollow = preset_by_key("circular_hollow")
    i_girder = preset_by_key("parametric_i_girder")
    box_girder = preset_by_key("single_cell_box_girder")
    custom_preset = {"key": "custom_polygon", "display_name": "Custom Polygon", "category": "Custom"}

    filtered = section_builder._filter_presets_for_member_type(
        [rectangle, circular_hollow, i_girder, box_girder, custom_preset],
        AnalysisModeSettings(member_type="beam_girder"),
    )
    keys = {preset["key"] for preset in filtered}

    assert "parametric_i_girder" in keys
    assert "single_cell_box_girder" in keys
    assert "custom_polygon" in keys
    assert "rectangle" not in keys
    assert "circular_hollow" not in keys


def test_girder_presets_are_split_into_composite_and_non_composite_families() -> None:
    i_girder = preset_by_key("parametric_i_girder")
    plank = preset_by_key("parametric_plank_girder_interior")
    general_i = preset_by_key("psc_i_girder")
    u_girder = preset_by_key("u_girder")
    box_beam = preset_by_key("box_section_fillet")
    exterior_box_beam = preset_by_key("precast_box_beam_exterior")

    assert i_girder["display_name"] == "Precast I-Girder"
    assert i_girder["category"] == "Precast Composite Girder"
    assert plank["display_name"] == "Precast Plank Girder — Interior"
    assert plank["category"] == "Precast Composite Girder"
    assert general_i["category"] == "General / Non-composite Girder"
    assert u_girder["display_name"] == "Precast U-Girder"
    assert u_girder["category"] == "Precast Composite Girder"
    assert box_beam["display_name"] == "Precast Box Beam – Interior"
    assert box_beam["category"] == "Precast Composite Girder"
    assert exterior_box_beam["display_name"] == "Precast Box Beam – Exterior"
    assert exterior_box_beam["category"] == "Precast Composite Girder"
    assert exterior_box_beam["dimensions_generator"] == "precast_box_beam_exterior"
    assert any(param["name"] == "h1_mm" and param.get("default") == 180 for param in exterior_box_beam["parameters"])
    assert any(param["name"] == "h3_mm" for param in exterior_box_beam["parameters"])
    assert any(param["name"] == "h8_mm" for param in exterior_box_beam["parameters"])
    assert any(param["name"] == "b4_mm" for param in exterior_box_beam["parameters"])
    assert any(param["name"] == "b3_mm" and param.get("default") == 360 for param in exterior_box_beam["parameters"])
    assert not any(param["name"] == "r_inner_mm" for param in exterior_box_beam["parameters"])
    assert any(param["name"] == "h1_mm" and param.get("default") == 180 for param in box_beam["parameters"])
    assert any(param["name"] == "h3_mm" for param in box_beam["parameters"])
    assert any(param["name"] == "h7_mm" for param in box_beam["parameters"])
    assert any(param["name"] == "b3_mm" for param in box_beam["parameters"])
    assert not any(param["name"] == "b2_start_from_left_mm" for param in box_beam["parameters"])
    assert not any(param["name"] == "r_inner_mm" for param in box_beam["parameters"])
    assert not any(param["name"] == "n_fillet" for param in box_beam["parameters"])
    assert section_builder._girder_section_family(i_girder) == "precast_composite_girder"
    assert section_builder._recommended_service_basis_for_preset(i_girder) == "Composite transformed"
    assert section_builder._girder_section_family(u_girder) == "precast_composite_girder"
    assert section_builder._recommended_service_basis_for_preset(u_girder) == "Composite transformed"
    assert section_builder._girder_section_family(box_beam) == "precast_composite_girder"
    assert section_builder._recommended_service_basis_for_preset(box_beam) == "Composite transformed"
    assert section_builder._girder_section_family(exterior_box_beam) == "precast_composite_girder"
    assert section_builder._recommended_service_basis_for_preset(exterior_box_beam) == "Composite transformed"
    assert section_builder._girder_section_family(general_i) == "general_non_composite_girder"
    assert section_builder._recommended_service_basis_for_preset(general_i) == "Precast gross"


def test_legacy_general_section_member_type_uses_column_pier_filter() -> None:
    rectangle = preset_by_key("rectangle")
    i_girder = preset_by_key("parametric_i_girder")

    filtered = section_builder._filter_presets_for_member_type(
        [rectangle, i_girder],
        AnalysisModeSettings(member_type="general_section"),
    )

    assert [preset["key"] for preset in filtered] == ["rectangle"]


def test_section_category_browser_uses_filtered_categories() -> None:
    rectangle = preset_by_key("rectangle")
    i_girder = preset_by_key("parametric_i_girder")

    categories = section_builder._categories_for_filtered_presets(
        ["Basic Solid", "Precast Composite Girder", "General / Non-composite Girder", "Custom"],
        [rectangle],
    )

    assert categories == ["Basic Solid"]

    categories = section_builder._categories_for_filtered_presets(
        ["Basic Solid", "Precast Composite Girder", "General / Non-composite Girder", "Custom"],
        [i_girder],
    )

    assert categories == ["Precast Composite Girder"]


def test_section_builder_source_contains_member_type_preset_filter_notice() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Type / Preset is filtered" in source
    assert "workflow-specific categories" in source
    assert "_filter_presets_for_member_type" in source
    assert "available_presets" in source
    assert "Custom PMM section presets" in source
    assert "Custom Girder section presets" in source
    assert "_BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS" in source
    assert "Bridge-specific load/stage/AASHTO Be tools stay hidden" in source


def test_composite1b_section_builder_source_displays_transformed_properties() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Composite Transformed Section Properties" in source
    assert "Enable composite deck/topping transformed properties" in source
    assert "calculate_composite_transformed_section_from_geometry" in source
    assert "Composite transformed-section breakdown" in source
    assert "not used by PMM/SLS solver yet" in source


def test_build_geometry_ignores_non_geometry_composite_metadata() -> None:
    plank = preset_by_key("parametric_plank_girder_interior")
    params = {
        "B_mm": 990.0,
        "b1_mm": 45.0,
        "b2_mm": 70.0,
        "b3_mm": 850.0,
        "H_mm": 450.0,
        "h1_mm": 80.0,
        "h2_mm": 140.0,
        "Tslab_mm": 100.0,
        "Be_mm": 1000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
        "girder_length_mm": 12000.0,
        "composite_enabled": True,
    }

    geometry, dimensions, validation = section_builder._build_geometry(plank, params)

    assert validation.is_valid
    assert validation.errors == []
    assert geometry is not None
    assert geometry.name == "Precast Plank Girder — Interior"
    assert len(dimensions) > 0


def test_composite1c_enables_i_girder_composite_metadata_display() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "SECTION.COMPOSITE1C" in source
    assert "Composite Deck / Topping Metadata" in source
    assert "parametric_i_girder_Tslab_mm" in source or "Tslab Deck/topping thickness" in source
    assert "_render_precast_composite_girder_metadata_inputs" in source


def test_i_girder_is_composite_capable_but_geometry_ignores_metadata() -> None:
    i_girder = preset_by_key("parametric_i_girder")
    assert section_builder._is_composite_capable_preset(i_girder)

    params = {
        "B1_mm": 800.0,
        "B2_mm": 500.0,
        "D1_mm": 1400.0,
        "D2_mm": 200.0,
        "D3_mm": 150.0,
        "D5_mm": 250.0,
        "D6_mm": 150.0,
        "T1_mm": 200.0,
        "T2_mm": 200.0,
        "C1_mm": 0.0,
        "Tslab_mm": 200.0,
        "Be_mm": 2000.0,
        "Ebeam_MPa": 31529.0,
        "Edeck_MPa": 27806.0,
        "girder_length_mm": 30000.0,
        "composite_enabled": True,
    }

    geometry, dimensions, validation = section_builder._build_geometry(i_girder, params)

    assert validation.is_valid
    assert validation.errors == []
    assert geometry is not None
    assert geometry.name == "Precast I-Girder"
    assert len(dimensions) > 0
    assert "Tslab_mm" not in geometry.metadata["parameters"]
    assert "Be_mm" not in geometry.metadata["parameters"]


def test_aashto_be1_section_builder_source_contains_effective_width_helper() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "AASHTO.BE1" in source
    assert "Effective Slab Width Helper" in source
    assert "Be calculation mode" in source
    assert "AASHTO helper" in source
    assert "calculate_aashto_effective_slab_width" in source
    assert "Effective slab width candidate limits" in source
    assert "Auto precast top contact width b_top" in source
    assert "Advanced effective-width override" in source
    assert "Manual b_top override" in source


def test_aashto_be1_top_width_reference_helpers_are_workflow_specific() -> None:
    i_girder = preset_by_key("parametric_i_girder")
    plank = preset_by_key("parametric_plank_girder_interior")
    exterior_plank = preset_by_key("parametric_plank_girder_exterior")

    assert section_builder._effective_width_top_w(i_girder, {"B1_mm": 800.0}) == 800.0
    assert section_builder._effective_width_top_w(plank, {"B_mm": 990.0, "b1_mm": 45.0}) == 900.0
    assert section_builder._effective_width_top_w(exterior_plank, {"B_mm": 990.0, "b1_mm": 45.0}) == 945.0
    assert section_builder._effective_width_default_position(exterior_plank) == "exterior"
    assert section_builder._effective_width_default_position(i_girder) == "interior"
    assert "B1" in section_builder._effective_width_top_width_basis_note(i_girder)
    assert "B - 2b1" in section_builder._effective_width_top_width_basis_note(plank)
    assert "B - b1" in section_builder._effective_width_top_width_basis_note(exterior_plank)


def test_section_builder_source_contains_axis_convention_for_load_tables() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Axis Convention" in source
    assert "LOADS.WORKFLOW1A" in source
    assert "major/minor labels are intentionally avoided" in source
    assert "Mux" in source
    assert "Vuy" in source


def test_rebar_system_flags_are_not_reassigned_after_checkbox_creation() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Do not write to Streamlit widget-owned reinforcement flag keys here" in source
    assert 'st.session_state["section_has_ordinary_rebar"] = ordinary_rebar_enabled' not in source
    assert 'st.session_state["section_has_prestressing_steel"] = prestressing_steel_enabled' not in source


def test_section_builder_preview_is_geometry_only_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Builder preview is locked to geometry only" in source
    assert "preview_rebars: list[Any] = []" in source
    assert "preview_prestress_elements: list[Any] = []" in source
    assert "Rebar/prestress display" in source
    assert "Hidden in Section Builder" in source


def test_plank_and_box_beam_be_helper_defaults_match_user_request() -> None:
    interior_plank = preset_by_key("parametric_plank_girder_interior")
    exterior_plank = preset_by_key("parametric_plank_girder_exterior")
    interior_box = preset_by_key("box_section_fillet")
    exterior_box = preset_by_key("precast_box_beam_exterior")

    for preset in [interior_plank, exterior_plank, interior_box, exterior_box]:
        assert section_builder._effective_width_default_spacing(preset, manual_be=1000.0, auto_top_width=990.0) == 1000.0

    assert next(param for param in interior_plank["parameters"] if param["name"] == "Be_mm")["default"] == 1000
    assert next(param for param in exterior_plank["parameters"] if param["name"] == "Be_mm")["default"] == 1000
    assert section_builder._precast_composite_girder_metadata_defaults(interior_box)["Be_mm"] == 1000.0
    assert section_builder._precast_composite_girder_metadata_defaults(exterior_box)["Be_mm"] == 1000.0
    assert section_builder._precast_composite_girder_metadata_defaults(interior_box)["girder_length_mm"] == 20000.0
    assert section_builder._precast_composite_girder_metadata_defaults(exterior_box)["girder_length_mm"] == 20000.0


def test_section_builder_definition_workspace_layout_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Workspace Status" in source
    assert "Section Steel Systems" in source
    assert "Project / workflow / axis details" in source
    assert "Include ordinary rebar / longitudinal Al" in source
    assert "Primary section dimensions are kept at the same level as the live preview" in source
    assert "Dimension labels" in source
    assert "material controls are in the details expander" in source


def test_section_builder_status_strip_helper_includes_workflow_and_material(monkeypatch) -> None:
    import sys
    import types

    st = types.ModuleType("streamlit")
    st.session_state = {"analysis_mode_settings": AnalysisModeSettings(member_type="beam_girder")}
    rendered: list[str] = []
    st.markdown = lambda body, **kwargs: rendered.append(str(body))
    monkeypatch.setitem(sys.modules, "streamlit", st)

    from concrete_pmm_pro.ui import section_builder as sb  # noqa: PLC0415
    monkeypatch.setattr(sb, "st", st)

    preset = preset_by_key("parametric_plank_girder_voided_interior")
    sb._render_section_builder_status_strip(
        preset,
        {"primary_material_name": "C45_PRECAST", "deck_topping_material_name": "C35_TOPPING"},
    )

    output = "\n".join(rendered)
    assert "Section Workspace Status" in output
    assert "Precast Voided Plank Girder" in output
    assert "C45_PRECAST" in output
    assert "C35_TOPPING" in output


def test_span_setup1_section_builder_locks_girder_span_to_setup_source() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "_setup_span_length_mm_for_section_builder" in source
    assert "_render_locked_setup_span_metadata" in source
    assert "BEAM_GIRDER_SYSTEM_SETTINGS_KEY" in source
    assert "Locked to Setup" in source
    assert "disabled=True" in source
    assert "Change the span in Setup, not in Section Builder" in source
    assert "girder_length_mm_locked_from_setup" in source
