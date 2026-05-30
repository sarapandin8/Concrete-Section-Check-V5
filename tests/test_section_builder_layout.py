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
    assert preset_map["parametric_i_girder"]["display_name"] == "Parametric I-Girder"
    assert label_map["parametric_i_girder"].startswith("Parametric I-Girder")
    assert label_map["parametric_i_girder"] == "Parametric I-Girder  ·  Girder"


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
    assert "Beam/Girder mode is active" in source
    assert "Column / Pier / Wall / Pylon PMM" in source
    assert "MEMBER.TYPE1 routes the workflow only" in source


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
        ["Basic Solid", "Girder", "Box Girder", "Custom"],
        [rectangle],
    )

    assert categories == ["Basic Solid"]

    categories = section_builder._categories_for_filtered_presets(
        ["Basic Solid", "Girder", "Box Girder", "Custom"],
        [i_girder],
    )

    assert categories == ["Girder"]


def test_section_builder_source_contains_member_type_preset_filter_notice() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "Section Type / Preset is filtered" in source
    assert "workflow-specific categories" in source
    assert "_filter_presets_for_member_type" in source
    assert "available_presets" in source
    assert "Custom PMM section presets" in source
    assert "Custom Girder section presets" in source


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
    assert geometry.name == "Parametric Plank Girder — Interior"
    assert len(dimensions) > 0


def test_composite1c_enables_i_girder_composite_metadata_display() -> None:
    source = (REPO_ROOT / "concrete_pmm_pro" / "ui" / "section_builder.py").read_text(encoding="utf-8")

    assert "SECTION.COMPOSITE1C" in source
    assert "Composite Deck / Topping Metadata" in source
    assert "parametric_i_girder_Tslab_mm" in source or "Tslab Deck/topping thickness" in source
    assert "_render_i_girder_composite_metadata_inputs" in source


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
    assert geometry.name == "Parametric I-Girder"
    assert len(dimensions) > 0
    assert "Tslab_mm" not in geometry.metadata["parameters"]
    assert "Be_mm" not in geometry.metadata["parameters"]
