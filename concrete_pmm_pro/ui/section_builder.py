"""Metadata-driven Streamlit section builder."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import streamlit as st

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import (
    analysis_mode_label,
    is_bridge_beam_girder_workflow,
    is_building_beam_girder_workflow,
)
from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    c45_precast_material,
    concrete_materials_by_name,
    ensure_concrete_material_library,
)
from concrete_pmm_pro.core.models import ConcreteMaterial
from concrete_pmm_pro.core.reinforcement_system import (
    ORDINARY_REBAR_FLAG_KEY,
    PRESTRESSING_STEEL_FLAG_KEY,
    REINFORCEMENT_FLAGS_PRESET_KEY,
    default_section_reinforcement_flags,
    ordinary_rebar_enabled,
    prestressing_steel_enabled,
)
from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.effective_width import (
    EffectiveWidthInput,
    EffectiveWidthResult,
    calculate_aashto_effective_slab_width,
)
from concrete_pmm_pro.geometry.composite import (
    calculate_composite_transformed_section_from_geometry,
    composite_deck_input_from_parameters,
    composite_deck_is_active,
)
from concrete_pmm_pro.geometry.presets import load_section_categories, load_section_presets
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import ValidationResult, validate_section_geometry
from concrete_pmm_pro.serviceability.girder_sls_load_components import (
    BEAM_GIRDER_SYSTEM_SETTINGS_KEY,
    DEFAULT_SPAN_LENGTH_M,
    system_settings_from_mapping,
)
from concrete_pmm_pro.visualization import create_section_preview


@dataclass(frozen=True)
class SectionMetric:
    title: str
    value: str
    detail: str = ""
    status: str = "neutral"
    strong: bool = False


_SECTION_BUILDER_CSS = """
<style>
.cpmm-section-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.12rem 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0;
  margin-top: 0.45rem;
}
.cpmm-section-badge.ready { color: #1f5f2a; background: #e7f5e8; }
.cpmm-section-badge.warning { color: #7a4b00; background: #fff4d6; }
.cpmm-section-badge.danger { color: #9f1f17; background: #fde8e7; }
.cpmm-section-badge.info { color: #1849a9; background: #e8f1ff; }
.cpmm-section-badge.neutral { color: #475467; background: #eef1f5; }
.cpmm-section-kv-panel {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.64rem 0.84rem;
}
.cpmm-section-kv-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.32rem 0;
}
.cpmm-section-kv-row:last-child { border-bottom: 0; }
.cpmm-section-kv-label {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 600;
}
.cpmm-section-kv-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 650;
  text-align: right;
  overflow-wrap: anywhere;
}
.cpmm-section-note {
  color: #667085;
  font-size: 0.82rem;
  line-height: 1.35;
  margin-top: -0.2rem;
}
.cpmm-section-status-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.34rem 0;
}
.cpmm-section-status-row:last-child { border-bottom: 0; }
.cpmm-section-status-title {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 650;
}
.cpmm-section-status-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 700;
  text-align: right;
}
.cpmm-section-message-list {
  border: 1px solid #edf0f5;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 0.62rem 0.78rem;
  margin-top: 0.55rem;
}
.cpmm-section-message-item {
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.35;
  padding: 0.18rem 0;
}
.cpmm-section-property-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.55rem;
  margin-bottom: 0.45rem;
}
.cpmm-section-property-chip {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.56rem 0.68rem;
  min-height: 72px;
}
.cpmm-section-property-label {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.18rem;
}
.cpmm-section-property-value {
  color: #101828;
  font-size: 0.94rem;
  font-weight: 720;
  line-height: 1.22;
  overflow-wrap: anywhere;
}
.cpmm-section-property-detail {
  color: #667085;
  font-size: 0.74rem;
  line-height: 1.25;
  margin-top: 0.16rem;
}
@media (max-width: 1200px) {
  .cpmm-section-property-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .cpmm-section-property-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
"""


def _number_input(parameter: dict[str, Any], key_prefix: str) -> float:
    return float(
        st.number_input(
            parameter.get("label", parameter["name"]),
            min_value=float(parameter.get("min", 0.0)),
            max_value=float(parameter.get("max", 1.0e9)),
            value=float(parameter.get("default", parameter.get("min", 0.0))),
            step=float(parameter.get("step", 1.0)),
            help=parameter.get("description"),
            key=f"{key_prefix}_{parameter['name']}",
        )
    )


def _legacy_rectangular_chamfer_value() -> float | None:
    params = st.session_state.get("section_parameters", {})
    legacy_value = None
    if isinstance(params, dict):
        legacy_value = params.get("chamfer_mm")
    if legacy_value is None:
        legacy_value = st.session_state.get("rectangular_chamfered_chamfer_mm")
    try:
        return None if legacy_value is None else float(legacy_value)
    except (TypeError, ValueError):
        return None


def _sync_rectangular_chamfered_legacy_widget_defaults(preset: dict[str, Any]) -> None:
    if str(preset.get("key", "")) != "rectangular_chamfered":
        return
    legacy = _legacy_rectangular_chamfer_value()
    if legacy is None:
        return
    for name in ("chamfer_x_mm", "chamfer_y_mm"):
        key = f"rectangular_chamfered_{name}"
        if key not in st.session_state:
            st.session_state[key] = legacy


def _safe_status(status: str) -> str:
    return status if status in {"ready", "warning", "danger", "info", "neutral"} else "neutral"


def _validation_status(result: ValidationResult) -> str:
    if result.errors:
        return "danger"
    if result.warnings:
        return "warning"
    return "ready"


def _kv_panel_html(rows: list[tuple[str, str]]) -> str:
    row_html = []
    for label, value in rows:
        row_html.append(
            '<div class="cpmm-section-kv-row">'
            f'<div class="cpmm-section-kv-label">{escape(label)}</div>'
            f'<div class="cpmm-section-kv-value">{escape(value)}</div>'
            "</div>"
        )
    return '<div class="cpmm-section-kv-panel">' + "".join(row_html) + "</div>"


def _status_panel_html(rows: list[SectionMetric]) -> str:
    row_html = []
    for row in rows:
        status = _safe_status(row.status)
        if row.strong:
            value_html = f'<span class="cpmm-section-badge {status}">{escape(row.value)}</span>'
        else:
            value_html = escape(row.value)
        row_html.append(
            '<div class="cpmm-section-status-row">'
            f'<div class="cpmm-section-status-title">{escape(row.title)}</div>'
            f'<div class="cpmm-section-status-value">{value_html}</div>'
            "</div>"
        )
    return '<div class="cpmm-section-kv-panel">' + "".join(row_html) + "</div>"


def _message_list_html(messages: list[str]) -> str:
    items = "".join(f'<div class="cpmm-section-message-item">{escape(message)}</div>' for message in messages)
    return f'<div class="cpmm-section-message-list">{items}</div>'


def _property_strip_html(properties: list[SectionMetric]) -> str:
    chips: list[str] = []
    for property_item in properties:
        status = _safe_status(property_item.status)
        value_html = (
            f'<span class="cpmm-section-badge {status}">{escape(property_item.value)}</span>'
            if property_item.strong
            else escape(property_item.value)
        )
        detail_html = (
            f'<div class="cpmm-section-property-detail">{escape(property_item.detail)}</div>'
            if property_item.detail
            else ""
        )
        chips.append(
            '<div class="cpmm-section-property-chip">'
            f'<div class="cpmm-section-property-label">{escape(property_item.title)}</div>'
            f'<div class="cpmm-section-property-value">{value_html}</div>'
            f"{detail_html}"
            "</div>"
        )
    return '<div class="cpmm-section-property-grid">' + "".join(chips) + "</div>"


def _format_float(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}"


def _format_optional_mm(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:,.{decimals}f} mm"


def _signed_mm(value: float | None, decimals: int = 1) -> str:
    if value is None:
        return "N/A"
    return f"{value:+,.{decimals}f} mm"


def _format_parameter_value(value: Any) -> str:
    if isinstance(value, float):
        return _format_float(value, 2).rstrip("0").rstrip(".")
    return str(value)


def _format_ec(value: float) -> str:
    return f"{value:,.0f} MPa"


def _ensure_concrete_material_session() -> list[ConcreteMaterial]:
    library_state = ensure_concrete_material_library(
        concrete_material=st.session_state.get("concrete_material", c45_precast_material()),
        concrete_materials=st.session_state.get("concrete_materials", []),
        active_concrete_material_name=st.session_state.get("active_concrete_material_name"),
        deck_topping_material_name=st.session_state.get("deck_topping_material_name"),
        preserve_existing_primary=not bool(st.session_state.get("concrete_materials", [])),
    )
    st.session_state["concrete_materials"] = library_state.materials
    st.session_state["active_concrete_material_name"] = library_state.active_concrete_material_name
    st.session_state["primary_concrete_material_name"] = library_state.active_concrete_material_name
    st.session_state["deck_topping_material_name"] = library_state.deck_topping_material_name
    st.session_state["concrete_material"] = library_state.active_material
    return library_state.materials


def _material_select_index(names: list[str], preferred_name: str | None, fallback_index: int = 0) -> int:
    if preferred_name in names:
        return names.index(preferred_name)
    return min(max(fallback_index, 0), max(len(names) - 1, 0))


def _hidden_material_parameter_names(preset: dict[str, Any]) -> set[str]:
    if _is_parametric_plank_girder(preset):
        return {"Ebeam_MPa", "Edeck_MPa"}
    return set()


def _is_building_shared_precast_girder_preset(preset: dict[str, Any]) -> bool:
    """Return True for shared prestressed girder geometry in Building workflow."""

    return str(preset.get("key", "")).strip() in _BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS


def _composite_metadata_enabled_for_workflow(
    preset: dict[str, Any], settings: AnalysisModeSettings | None = None
) -> bool:
    """Return True when composite deck/topping metadata controls should show.

    Bridge Beam/Girder exposes the full bridge composite metadata workflow,
    including the AASHTO effective-width helper.  Building Beam/Girder may reuse
    shared precast I-Girder geometry under ACI 318 and still needs generic
    deck/topping metadata and transformed-property display.  Bridge-only load
    components, staged SLS, and AASHTO Be automation remain hidden outside the
    Bridge workflow.
    """

    active_settings = settings or _analysis_mode_from_session_state()
    if not _is_composite_capable_preset(preset):
        return False
    if is_bridge_beam_girder_workflow(active_settings):
        return True
    return is_building_beam_girder_workflow(active_settings) and _is_building_shared_precast_girder_preset(preset)


def _aashto_effective_width_helper_enabled(
    preset: dict[str, Any], settings: AnalysisModeSettings | None = None
) -> bool:
    """Return True only for Bridge workflow AASHTO Be helper controls."""

    active_settings = settings or _analysis_mode_from_session_state()
    return _is_composite_capable_preset(preset) and is_bridge_beam_girder_workflow(active_settings)


def _render_concrete_material_assignment(preset: dict[str, Any]) -> dict[str, Any]:
    materials = _ensure_concrete_material_session()
    material_map = concrete_materials_by_name(materials)
    material_names = list(material_map)
    active_name = st.session_state.get("active_concrete_material_name")
    default_primary_index = _material_select_index(material_names, active_name)
    if active_name not in material_map:
        st.session_state["active_concrete_material_name"] = material_names[default_primary_index]

    st.markdown("##### Concrete Material Assignment")
    selected_primary = st.selectbox(
        "Primary / section concrete material",
        material_names,
        index=default_primary_index,
        help="Material for the main concrete polygon. This is the concrete material used by PMM analysis.",
        key="active_concrete_material_name",
    )
    primary_material = material_map[selected_primary]
    # Do not assign to st.session_state["active_concrete_material_name"] here.
    # The selectbox owns that widget key; assigning to the same key after widget
    # instantiation raises StreamlitAPIException on Streamlit Cloud.
    st.session_state["primary_concrete_material_name"] = selected_primary
    st.session_state["concrete_material"] = primary_material

    bridge_composite_metadata = _composite_metadata_enabled_for_workflow(preset)
    assignment: dict[str, Any] = {
        "primary_material_name": selected_primary,
        "primary_fc_MPa": primary_material.fc_MPa,
        "Ebeam_MPa": primary_material.effective_Ec_MPa,
        "is_composite_applicable": bridge_composite_metadata,
    }

    if bridge_composite_metadata:
        deck_name = st.session_state.get("deck_topping_material_name", DEFAULT_DECK_TOPPING_MATERIAL)
        deck_index = _material_select_index(material_names, deck_name, fallback_index=min(1, len(material_names) - 1))
        if deck_name not in material_map:
            st.session_state["deck_topping_material_name"] = material_names[deck_index]
        selected_deck = st.selectbox(
            "Deck / topping concrete material",
            material_names,
            index=deck_index,
            help="Used for Edeck, modular ratio n, and transformed-width metadata only in this milestone.",
            key="deck_topping_material_name",
        )
        deck_material = material_map[selected_deck]
        # The deck selectbox owns st.session_state["deck_topping_material_name"].
        # Do not reassign it after widget creation.
        assignment.update(
            {
                "deck_topping_material_name": selected_deck,
                "deck_fc_MPa": deck_material.fc_MPa,
                "Edeck_MPa": deck_material.effective_Ec_MPa,
            }
        )
        n_ratio = deck_material.effective_Ec_MPa / primary_material.effective_Ec_MPa
        assignment["n_Edeck_over_Ebeam"] = n_ratio
        st.markdown(
            _kv_panel_html(
                [
                    ("Primary material", f"{selected_primary} | f'c {primary_material.fc_MPa:g} MPa | Ec {_format_ec(primary_material.effective_Ec_MPa)}"),
                    ("Deck/topping material", f"{selected_deck} | f'c {deck_material.fc_MPa:g} MPa | Ec {_format_ec(deck_material.effective_Ec_MPa)}"),
                    ("n = Edeck/Ebeam", _format_float(n_ratio, 3)),
                    ("Composite scope", "Metadata only; slab/topping is not merged into gross properties or PMM"),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="cpmm-section-note">Deck/topping material is used for composite metadata and transformed-width '
            "calculation only in this milestone. Composite slab/topping is not yet merged into gross section properties "
            "or PMM solver.</div>",
            unsafe_allow_html=True,
        )
    else:
        settings = _analysis_mode_from_session_state()
        if _is_composite_capable_preset(preset) and is_building_beam_girder_workflow(settings):
            st.caption(
                "Deck / topping material: Hidden unless the preset is an explicitly shared prestressed girder geometry. "
                "Bridge AASHTO Be automation and staged bridge load workflows remain hidden under Building Beam/Girder."
            )
        else:
            st.caption("Deck / topping material: Not applicable for this section type.")
        st.markdown(
            _kv_panel_html(
                [
                    ("Primary material", f"{selected_primary} | f'c {primary_material.fc_MPa:g} MPa"),
                    ("Primary Ec", _format_ec(primary_material.effective_Ec_MPa)),
                    ("Solver material", "Primary / section concrete only"),
                ]
            ),
            unsafe_allow_html=True,
        )
    return assignment


def _render_section_builder_status_strip(preset: dict[str, Any], material_assignment: dict[str, Any]) -> None:
    """Render the compact default context strip for the definition workspace."""

    settings = _analysis_mode_from_session_state()
    primary = str(material_assignment.get("primary_material_name", "N/A"))
    deck = str(material_assignment.get("deck_topping_material_name", "N/A"))
    material_detail = f"Precast {primary}"
    if _composite_metadata_enabled_for_workflow(preset, settings):
        material_detail += f" / topping {deck}"

    rebar_status = "Enabled" if ordinary_rebar_enabled(st.session_state) else "Disabled"
    prestress_status = "Enabled" if prestressing_steel_enabled(st.session_state) else "Disabled"

    st.markdown("##### Section Workspace Status")
    st.markdown(
        _property_strip_html(
            [
                SectionMetric("Section", str(preset.get("display_name", "N/A")), str(preset.get("category", "General")), "info", True),
                SectionMetric("Workflow", analysis_mode_label(settings), _girder_section_family_label(preset), "ready", True),
                SectionMetric("Axis", "x/y/z", "x horizontal, y vertical, z longitudinal", "neutral"),
                SectionMetric("Rebar / Prestress", f"{rebar_status} / {prestress_status}", "stored reinforcement is previewed on its own page", "ready" if prestress_status == "Enabled" or rebar_status == "Enabled" else "neutral"),
                SectionMetric("Concrete", material_detail, "material controls are in the details expander", "info"),
            ]
        ),
        unsafe_allow_html=True,
    )


def _preset_option_label(preset: dict[str, Any]) -> str:
    """Return the user-facing label for a section preset selector option."""
    return f"{preset['display_name']}  ·  {preset.get('category', 'General')}"


def _preset_maps(presets: list[dict[str, Any]]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, str]]:
    """Build stable key-based selector maps for Streamlit widgets.

    The Section Type / Preset selectbox must be keyed by immutable preset keys,
    not by display labels or a dynamically changing index. Otherwise Streamlit
    can require two user selections: the first rerun updates the stored preset,
    and the next rerun rebuilds the widget with a different default index.
    """
    preset_keys = [str(preset.get("key", "")) for preset in presets]
    preset_map = {str(preset.get("key", "")): preset for preset in presets}
    label_map = {key: _preset_option_label(preset_map[key]) for key in preset_keys}
    return preset_keys, preset_map, label_map


def _initial_preset_selector_key(preset_keys: list[str]) -> str:
    """Resolve the initial section preset selector value from session state."""
    if not preset_keys:
        return ""

    current_widget_value = st.session_state.get("section_preset_selector_key")
    if current_widget_value in preset_keys:
        return str(current_widget_value)

    loaded_preset_key = st.session_state.get("section_preset_key")
    if loaded_preset_key in preset_keys:
        return str(loaded_preset_key)

    return preset_keys[0]

def _is_parametric_i_girder(preset: dict[str, Any]) -> bool:
    return str(preset.get("key", "")) == "parametric_i_girder"


def _is_precast_u_girder(preset: dict[str, Any]) -> bool:
    return str(preset.get("key", "")) == "u_girder"


def _is_precast_box_beam(preset: dict[str, Any]) -> bool:
    return str(preset.get("key", "")) in {"box_section_fillet", "precast_box_beam_exterior"}


def _is_parametric_plank_girder(preset: dict[str, Any]) -> bool:
    return str(preset.get("key", "")).startswith("parametric_plank_girder_")


def _is_interior_plank_girder_key(preset_key: str) -> bool:
    return str(preset_key) in {"parametric_plank_girder_interior", "parametric_plank_girder_voided_interior"}


def _geometry_parameter_names(preset: dict[str, Any]) -> set[str]:
    """Return parameter names accepted by the section geometry generator.

    Section Builder may store additional analysis metadata, such as
    ``composite_enabled``, in ``section_parameters``.  Those metadata fields
    must not be passed into geometry/dimension generator functions because the
    accepted section polygons are intentionally unchanged.
    """

    return {str(parameter.get("name", "")) for parameter in preset.get("parameters", [])}


def _is_composite_capable_preset(preset: dict[str, Any]) -> bool:
    """Return whether the current preset has explicit deck/topping metadata."""

    # SECTION.COMPOSITE1C enables display-only transformed composite properties
    # for the Precast I-Girder as well as Precast Plank Girder presets.  The deck
    # metadata is still explicit UI input and remains separate from gross
    # section properties and all PMM/prestress solver paths.
    return (
        _is_parametric_i_girder(preset)
        or _is_precast_u_girder(preset)
        or _is_precast_box_beam(preset)
        or _is_parametric_plank_girder(preset)
    )


def _girder_section_family(preset: dict[str, Any]) -> str:
    """Classify the Beam/Girder section intent used by service-stage UI routing."""

    category = str(preset.get("category", "")).casefold()
    if _is_composite_capable_preset(preset) or category == "precast composite girder":
        return "precast_composite_girder"
    if "girder" in category:
        return "general_non_composite_girder"
    return "non_girder"


def _girder_section_family_label(preset: dict[str, Any]) -> str:
    """Return the user-facing section family label for Beam/Girder workflow."""

    family = _girder_section_family(preset)
    if family == "precast_composite_girder":
        return "Precast Composite Girder"
    if family == "general_non_composite_girder":
        return "General / Non-composite Girder"
    return "Column/Pier/Wall/Pylon section"


def _recommended_service_basis_for_preset(preset: dict[str, Any]) -> str:
    """Return the default Service-stage basis implied by the selected section family."""

    if _girder_section_family(preset) == "precast_composite_girder":
        return "Composite transformed"
    return "Precast gross"


def _default_reinforcement_flags_for_preset(preset: dict[str, Any]) -> tuple[bool, bool]:
    settings = _analysis_mode_from_session_state()
    return default_section_reinforcement_flags(
        member_type=settings.member_type,
        section_category=str(preset.get("category", "")),
        section_preset_key=str(preset.get("key", "")),
        girder_section_family=_girder_section_family(preset),
    )


def _ensure_reinforcement_flags_for_preset(preset: dict[str, Any]) -> None:
    preset_key = str(preset.get("key", ""))
    default_rebar, default_prestress = _default_reinforcement_flags_for_preset(preset)
    if (
        st.session_state.get(REINFORCEMENT_FLAGS_PRESET_KEY) != preset_key
        or ORDINARY_REBAR_FLAG_KEY not in st.session_state
        or PRESTRESSING_STEEL_FLAG_KEY not in st.session_state
    ):
        st.session_state[ORDINARY_REBAR_FLAG_KEY] = default_rebar
        st.session_state[PRESTRESSING_STEEL_FLAG_KEY] = default_prestress
        st.session_state[REINFORCEMENT_FLAGS_PRESET_KEY] = preset_key


def _store_reinforcement_flags_metadata() -> None:
    """Mirror section-level steel-system switches into project metadata.

    The checkbox widget keys remain owned by Streamlit.  This helper only copies
    their current values so save/load round-trip and downstream pages see the
    same include-rebar/include-prestress decision immediately.
    """

    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    for flag_name in (ORDINARY_REBAR_FLAG_KEY, PRESTRESSING_STEEL_FLAG_KEY, REINFORCEMENT_FLAGS_PRESET_KEY):
        if flag_name in st.session_state:
            metadata[flag_name] = st.session_state[flag_name]
    st.session_state["project_metadata"] = metadata


def _render_reinforcement_prestress_system_panel(preset: dict[str, Any]) -> None:
    """Render visible section-level rebar/prestress participation switches."""

    _ensure_reinforcement_flags_for_preset(preset)
    default_rebar, default_prestress = _default_reinforcement_flags_for_preset(preset)
    family_label = _girder_section_family_label(preset)
    st.markdown("##### Section Steel Systems")
    st.markdown(
        '<div class="cpmm-section-note">Choose which internal steel systems are included in this section analysis. '
        'Disabling a system preserves existing Rebar/Prestress input tables but excludes that system from analysis input assembly. '
        'For precast girders, enable ordinary rebar when mild longitudinal bars or torsion Al are part of the design model.</div>',
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.checkbox(
            "Include ordinary rebar / longitudinal Al",
            value=ordinary_rebar_enabled(st.session_state, default=default_rebar),
            key=ORDINARY_REBAR_FLAG_KEY,
            help=(
                "When disabled, stored ordinary Rebar rows are kept but ignored by PMM/SLS analysis. "
                "Enable this for precast girders when mild longitudinal bars should participate in flexure/effective d or torsion Al review."
            ),
        )
    with col2:
        st.checkbox(
            "Include prestressing steel",
            value=prestressing_steel_enabled(st.session_state, default=default_prestress),
            key=PRESTRESSING_STEEL_FLAG_KEY,
            help="When disabled, stored Prestress rows/strand layout data are kept but ignored by analysis and hidden from the default section preview.",
        )

    _store_reinforcement_flags_metadata()

    rebar_status = "Enabled" if ordinary_rebar_enabled(st.session_state, default=default_rebar) else "Disabled"
    ps_status = "Enabled" if prestressing_steel_enabled(st.session_state, default=default_prestress) else "Disabled"
    st.markdown(
        _kv_panel_html(
            [
                ("Selected section family", family_label),
                ("Ordinary rebar / longitudinal Al", rebar_status),
                ("Prestressing steel", ps_status),
                ("Default for this preset", f"Rebar {'ON' if default_rebar else 'OFF'} / Prestress {'ON' if default_prestress else 'OFF'}"),
            ]
        ),
        unsafe_allow_html=True,
    )


_COLUMN_PIER_SECTION_CATEGORIES = frozenset({"Basic Solid", "Hollow / Voided", "Pier / Column", "Custom"})
_BRIDGE_BEAM_GIRDER_SECTION_CATEGORIES = frozenset(
    {"Precast Composite Girder", "General / Non-composite Girder", "Girder", "Box Girder", "Custom"}
)
_BUILDING_BEAM_GIRDER_SECTION_CATEGORIES = frozenset(
    {"Basic Solid", "Hollow / Voided", "General / Non-composite Girder", "Custom"}
)
_BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS = frozenset(
    {
        # Shared geometry only: available under Building Beam/Girder ACI workflow
        # without enabling bridge-specific AASHTO Be, staged SLS, or SDL tools.
        "parametric_i_girder",
    }
)


def _section_categories_for_member_type(settings: AnalysisModeSettings) -> set[str]:
    """Return the section preset categories allowed by the active member workflow.

    WORKFLOW.TYPE3 separates physical section geometry from design-code context.
    Bridge Beam/Girder exposes bridge girder categories under AASHTO LRFD.
    Building Beam/Girder exposes building beam categories under ACI 318 plus
    explicitly shared precast girder geometry such as Precast I-Girder.  Shared
    geometry does not activate bridge-only load/stage/effective-width tools.
    """

    if is_bridge_beam_girder_workflow(settings):
        return set(_BRIDGE_BEAM_GIRDER_SECTION_CATEGORIES)
    if is_building_beam_girder_workflow(settings):
        return set(_BUILDING_BEAM_GIRDER_SECTION_CATEGORIES | {"Precast Composite Girder"})
    return set(_COLUMN_PIER_SECTION_CATEGORIES)


def _preset_matches_member_type(preset: dict[str, Any], settings: AnalysisModeSettings) -> bool:
    """Return whether a section preset should be shown for the active workflow."""

    category = str(preset.get("category", "General"))
    preset_key = str(preset.get("key", ""))
    if is_building_beam_girder_workflow(settings):
        return category in _BUILDING_BEAM_GIRDER_SECTION_CATEGORIES or preset_key in _BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS
    allowed_categories = _section_categories_for_member_type(settings)
    return category in allowed_categories


def _filter_presets_for_member_type(
    presets: list[dict[str, Any]], settings: AnalysisModeSettings
) -> list[dict[str, Any]]:
    """Filter section presets by active member workflow without changing presets."""

    filtered = [preset for preset in presets if _preset_matches_member_type(preset, settings)]
    return filtered or list(presets)


def _categories_for_filtered_presets(
    configured_categories: list[str], filtered_presets: list[dict[str, Any]]
) -> list[str]:
    """Keep the Section Category browser consistent with filtered presets."""

    visible_preset_categories = {str(preset.get("category", "General")) for preset in filtered_presets}
    categories = [category for category in configured_categories if category in visible_preset_categories]
    for category in visible_preset_categories:
        if category not in categories:
            categories.append(category)
    return categories or list(configured_categories)


def _member_type_filter_description(settings: AnalysisModeSettings) -> str:
    """Human-readable description of the active Section Type / Preset filter."""

    if is_building_beam_girder_workflow(settings):
        shared = ", ".join(sorted(_BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS))
        return (
            "Section Type / Preset includes ACI building beam categories plus shared precast girder geometry "
            f"({shared}). Bridge-specific load/stage/AASHTO Be tools stay hidden."
        )
    allowed_categories = _section_categories_for_member_type(settings)
    category_text = ", ".join(sorted(allowed_categories))
    return f"Section Type / Preset is filtered to workflow-specific categories: {category_text}."



def _analysis_mode_from_session_state() -> AnalysisModeSettings:
    value = st.session_state.get("analysis_mode_settings")
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


def _axis_convention_rows() -> list[tuple[str, str]]:
    """Return the shared axis/action convention used by Section Builder and Loads."""

    return [
        ("x-axis", "Horizontal section width direction in the section preview"),
        ("y-axis", "Vertical section depth direction; positive upward in the section preview"),
        ("z-axis", "Member / girder longitudinal axis"),
        ("Mux", "Moment about x-axis; main vertical bending for typical girders"),
        ("Muy", "Moment about y-axis; lateral/minor bending for typical girders"),
        ("Vux", "Shear force in x-direction; lateral shear"),
        ("Vuy", "Shear force in y-direction; vertical shear"),
        ("Tu", "Torsion about the member longitudinal axis"),
    ]


def _render_axis_convention_card() -> None:
    """Display the section-axis basis before users enter Mux/Muy/Vux/Vuy loads."""

    st.markdown("##### Axis Convention")
    st.markdown(
        '<div class="cpmm-section-note">LOADS.WORKFLOW1A uses explicit x/y/z-axis action names. '
        "Confirm these axes against the live section preview before entering loads; major/minor labels are intentionally avoided.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_kv_panel_html(_axis_convention_rows()), unsafe_allow_html=True)


def _render_member_type_section_guidance(preset: dict[str, Any]) -> None:
    """Show non-invasive Section Builder guidance for the active member workflow."""
    settings = _analysis_mode_from_session_state()
    preset_key = str(preset.get("key", ""))
    is_girder_preset = "girder" in str(preset.get("category", "")).casefold() or "girder" in preset_key

    rows = [("Active member workflow", analysis_mode_label(settings))]
    if is_bridge_beam_girder_workflow(settings):
        family_label = _girder_section_family_label(preset)
        service_basis = _recommended_service_basis_for_preset(preset)
        rows.extend(
            [
                ("Design context", "Bridge Beam/Girder under AASHTO LRFD"),
                ("Selected girder family", family_label),
                ("Service-stage basis default", service_basis),
                ("Recommended section family", "Precast Composite Girder or General / Non-composite Girder presets"),
                ("Custom category", "Custom Girder section presets remain under this workflow"),
                ("Current geometry status", "Gross section polygon only; composite properties remain explicit metadata"),
                ("Girder design checks", "Stage-based SLS preview uses the selected family to guide service basis"),
                ("Current preset fit", "Good for Bridge Beam/Girder" if is_girder_preset else "Review: selected preset is not a girder preset"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        if not is_girder_preset:
            st.warning("Bridge Beam/Girder workflow is active, but the selected preset is not a dedicated girder preset. Use only with engineering judgment.")
        st.caption("WORKFLOW.TYPE3 routes shared geometry separately from design-code context. Bridge tools remain AASHTO LRFD / engineering-review previews until full engines are implemented.")
    elif is_building_beam_girder_workflow(settings):
        is_shared_precast = preset_key in _BUILDING_SHARED_PRECAST_GIRDER_PRESET_KEYS
        rows.extend(
            [
                ("Design context", "Building Beam/Girder under ACI 318"),
                ("Geometry availability", "Building beam categories plus shared precast girder geometry"),
                ("Shared geometry preset", "Yes — ACI building context" if is_shared_precast else "No"),
                ("Bridge-specific tools", "Hidden: bridge staged SLS, barrier/sidewalk/wearing surface, CSiBridge LL+IM"),
                ("Current preset fit", "Good for Building Beam/Girder" if (is_shared_precast or not is_girder_preset) else "Review: bridge-only girder preset"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        if is_shared_precast:
            st.info(
                "Precast I-Girder is available here as shared section geometry for ACI 318 building work. "
                "Bridge load components, AASHTO effective-width helper, and staged bridge SLS tools are intentionally not active; prestressed girder layout/loss tools remain available as shared detailing workflow."
            )
        st.caption("WORKFLOW.TYPE3: same physical section geometry can be reused; design checks and load workflows remain workflow-specific.")
    else:
        rows.extend(
            [
                ("Primary analysis meaning", "Column / Pier / Wall / Pylon PMM"),
                ("PMM demand inputs", "Pu, Mux, Muy"),
                ("Custom category", "Custom PMM section presets remain under this workflow"),
                ("Concrete material used by PMM", "Primary / section concrete only"),
                ("Deck/topping material", "Ignored by PMM"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)

def _setup_span_length_mm_for_section_builder() -> float:
    """Return the Setup span length as the single source for girder span metadata."""

    system = system_settings_from_mapping(st.session_state.get(BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
    span_m = float(system.span_length_m or DEFAULT_SPAN_LENGTH_M)
    if span_m <= 0.0:
        span_m = DEFAULT_SPAN_LENGTH_M
    return span_m * 1000.0


def _render_locked_setup_span_metadata(preset_key: str) -> float:
    """Show read-only girder span metadata sourced from Setup and mirror legacy keys."""

    span_mm = _setup_span_length_mm_for_section_builder()
    # Keep the legacy metadata key synchronized for effective-width helpers,
    # prestress previews, project save/load metadata, and old project files.
    st.session_state[f"{preset_key}_girder_length_mm"] = float(span_mm)
    st.session_state[f"{preset_key}_girder_length_mm_locked_from_setup"] = float(span_mm)
    st.number_input(
        "Girder length / span (mm)",
        min_value=1.0,
        max_value=1000000.0,
        value=float(span_mm),
        step=100.0,
        format="%.1f",
        disabled=True,
        key=f"{preset_key}_girder_length_mm_locked_from_setup",
        help="Read-only value from Setup → Span length L. Change the span in Setup, not in Section Builder.",
    )
    st.caption("Locked to Setup → 🟨 Span length L (m). Section Builder no longer owns girder span input.")
    return float(span_mm)


def _render_metadata_number_input(
    *,
    name: str,
    label: str,
    preset_key: str,
    default: float,
    min_value: float,
    max_value: float,
    step: float,
    help_text: str,
) -> float:
    """Render a metadata input that is intentionally not a geometry parameter."""

    return float(
        st.number_input(
            label,
            min_value=float(min_value),
            max_value=float(max_value),
            value=float(default),
            step=float(step),
            help=help_text,
            key=f"{preset_key}_{name}",
        )
    )



def _selectbox_with_safe_index(label: str, options: list[str], *, key: str, default: str, help_text: str | None = None) -> str:
    """Render a selectbox with stable key handling and no post-widget mutation."""

    index = options.index(default) if default in options else 0
    return str(st.selectbox(label, options, index=index, key=key, help=help_text))


def _effective_width_top_w(preset: dict[str, Any], params: dict[str, Any]) -> float:
    """Resolve the physical precast top contact width for Be helper metadata.

    This is deliberately auto-derived from the selected section geometry so the
    user does not have to guess a code-helper input.  The value is used only by
    the AASHTO.BE1 effective slab-width helper; it never changes the generated
    precast polygon.
    """

    if _is_parametric_i_girder(preset):
        return float(params.get("B1_mm", 0.0) or 0.0)
    if _is_precast_u_girder(preset):
        return float(params.get("top_" + "width" + "_mm", 0.0) or params.get("B1_mm", 0.0) or 0.0)
    if _is_precast_box_beam(preset):
        return float(params.get("width" + "_mm", 0.0) or params.get("B_mm", 0.0) or 0.0)
    if _is_parametric_plank_girder(preset):
        b = float(params.get("B_mm", 0.0) or 0.0)
        b1 = float(params.get("b1_mm", 0.0) or 0.0)
        if _is_interior_plank_girder_key(str(preset.get("key", ""))):
            return max(b - 2.0 * b1, 0.0)
        return max(b - b1, 0.0)
    return float(params.get("B_mm", 0.0) or 0.0)


def _effective_width_top_width_basis_note(preset: dict[str, Any]) -> str:
    """Return the engineering basis for the auto top-contact width."""

    if _is_parametric_i_girder(preset):
        return "Auto from I-Girder top flange width B1."
    if _is_precast_u_girder(preset):
        return "Auto from U-Girder top width."
    if _is_precast_box_beam(preset):
        return "Auto from Box Beam top slab width."
    if _is_parametric_plank_girder(preset):
        if _is_interior_plank_girder_key(str(preset.get("key", ""))):
            return "Auto from Interior Plank top width B - 2b1."
        return "Auto from Exterior Plank top contact width B - b1."
    return "Auto from selected section top width metadata."


def _precast_composite_girder_metadata_defaults(preset: dict[str, Any]) -> dict[str, float]:
    """Return UI-only default metadata for precast composite girder presets.

    These defaults seed Streamlit number inputs only; user-entered/session values
    still take precedence through stable widget keys. They do not change solver
    equations or effective-width formulas.
    """

    if _is_precast_box_beam(preset):
        return {"Tslab_mm": 200.0, "Be_mm": 1000.0, "girder_length_mm": 20000.0}
    return {"Tslab_mm": 200.0, "Be_mm": 1000.0, "girder_length_mm": 30000.0}


def _effective_width_default_spacing(preset: dict[str, Any], manual_be: float, auto_top_width: float) -> float:
    """Return the default girder spacing for the Be helper controls."""

    if _is_precast_box_beam(preset) or _is_parametric_plank_girder(preset):
        return 1000.0
    return max(manual_be, auto_top_width, 1.0)


def _effective_width_default_position(preset: dict[str, Any]) -> str:
    preset_key = str(preset.get("key", ""))
    if preset_key.endswith("_exterior"):
        return "exterior"
    return "interior"


def _render_effective_width_candidates(result: EffectiveWidthResult) -> None:
    rows = [("Effective width method", result.method), ("Governing limit", result.governing_limit)]
    rows.extend((candidate.label, f"{_format_float(candidate.value_mm, 1)} mm") for candidate in result.candidates)
    if result.warnings:
        rows.extend(("Review note", warning) for warning in result.warnings)
    st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)


def _render_effective_width_helper(preset: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Render AASHTO.BE1 effective slab-width controls and return metadata.

    The returned Be is used only for composite metadata/transformed-section
    display in the current milestone.  It does not modify PMM, prestress, rebar,
    load, or report calculations.
    """

    if not _is_composite_capable_preset(preset):
        return params

    preset_key = str(preset.get("key", "section"))
    manual_be = float(params.get("Be_mm", 0.0) or 0.0)
    tslab = float(params.get("Tslab_mm", 0.0) or 0.0)
    span = float(params.get("girder_length_mm", 0.0) or 0.0)
    auto_top_width = _effective_width_top_w(preset, params)
    top_width_basis = _effective_width_top_width_basis_note(preset)

    st.markdown("##### Effective Slab Width Helper")
    st.markdown(
        '<div class="cpmm-section-note">AASHTO.BE1 adds a transparent effective slab-width helper for composite metadata. '
        "Manual Be remains available; calculated Be is not used by PMM or prestress solvers. "
        "The precast top contact width b<sub>top</sub> is auto-calculated from the selected section geometry, "
        "with manual override available only under Advanced effective-width override.</div>",
        unsafe_allow_html=True,
    )

    mode_key = f"{preset_key}_Be_mode"
    mode = _selectbox_with_safe_index(
        "Be calculation mode",
        ["Manual", "AASHTO helper"],
        key=mode_key,
        default=str(st.session_state.get(mode_key, "Manual")),
        help_text="Manual keeps the Be value entered above. AASHTO helper calculates a preliminary Be for composite metadata display.",
    )

    params["Be_mode"] = mode
    params["Be_manual_mm"] = manual_be
    params["Be_top_w_auto_mm"] = auto_top_width
    params["Be_top_w_mm"] = auto_top_width
    params["Be_top_w_source"] = "Auto from section geometry"

    if mode != "AASHTO helper":
        params["Be_effective_mm"] = manual_be
        params["Be_governing_limit"] = "Manual"
        st.markdown(
            _kv_panel_html(
                [
                    ("Be mode", "Manual"),
                    ("Manual Be", f"{_format_float(manual_be, 1)} mm"),
                    ("Auto precast top contact width b_top", f"{_format_float(auto_top_width, 1)} mm"),
                    ("b_top basis", top_width_basis),
                ]
            ),
            unsafe_allow_html=True,
        )
        return params

    position_default = _effective_width_default_position(preset)
    position_key = f"{preset_key}_Be_position"
    position_label = _selectbox_with_safe_index(
        "Girder position for Be helper",
        ["Interior", "Exterior"],
        key=position_key,
        default=str(st.session_state.get(position_key, position_default.title())),
        help_text="Interior uses spacing on both sides. Exterior also uses deck overhang metadata.",
    )
    position = "exterior" if position_label == "Exterior" else "interior"

    default_spacing = _effective_width_default_spacing(preset, manual_be, auto_top_width)
    columns = st.columns(2)
    with columns[0]:
        spacing = _render_metadata_number_input(
            name="girder_spacing_mm",
            label="Girder spacing S (mm)",
            preset_key=preset_key,
            default=default_spacing,
            min_value=1.0,
            max_value=100000.0,
            step=10.0,
            help_text="Center-to-center spacing to adjacent girder. Used only by Be helper.",
        )
    with columns[1]:
        overhang = _render_metadata_number_input(
            name="deck_overhang_mm",
            label="Exterior deck overhang (mm)",
            preset_key=preset_key,
            default=500.0 if position == "exterior" else 0.0,
            min_value=0.0,
            max_value=100000.0,
            step=10.0,
            help_text="Deck width from exterior girder centerline/reference to free edge. Used only when position is Exterior.",
        )

    top_width_used = auto_top_width
    top_width_source = "Auto from section geometry"
    with st.expander("Advanced effective-width override", expanded=False):
        st.caption(
            "Precast top contact width b_top is normally calculated from the selected section geometry. "
            "Override it only when the design effective-width reference is intentionally different from the generated section."
        )
        st.markdown(
            _kv_panel_html(
                [
                    ("Auto b_top", f"{_format_float(auto_top_width, 1)} mm"),
                    ("Auto basis", top_width_basis),
                    ("Scope", "Used only by AASHTO.BE1 helper; does not change section geometry"),
                ]
            ),
            unsafe_allow_html=True,
        )
        top_width_source_key = f"{preset_key}_Be_top_width_source"
        top_width_source = _selectbox_with_safe_index(
            "Precast top contact width b_top source",
            ["Auto from section geometry", "Manual override"],
            key=top_width_source_key,
            default=str(st.session_state.get(top_width_source_key, "Auto from section geometry")),
            help_text="Keep Auto for normal use. Manual override is only for special effective-width assumptions.",
        )
        if top_width_source == "Manual override":
            top_width_used = _render_metadata_number_input(
                name="Be_top_contact_width_override_mm",
                label="Manual b_top override (mm)",
                preset_key=preset_key,
                default=max(auto_top_width, 1.0),
                min_value=1.0,
                max_value=100000.0,
                step=10.0,
                help_text="Manual physical top contact width used by Be helper only. It does not change the generated section polygon.",
            )
        else:
            top_width_used = auto_top_width

    params["Be_top_w_mm"] = top_width_used
    params["Be_top_w_source"] = top_width_source

    try:
        result = calculate_aashto_effective_slab_width(
            EffectiveWidthInput(
                span,
                tslab,
                spacing,
                top_width_used,
                position=position,
                deck_overhang_mm=overhang if position == "exterior" else 0.0,
            )
        )
    except ValueError as exc:
        st.warning(f"Effective slab width helper is paused: {exc}")
        params["Be_effective_mm"] = manual_be
        params["Be_governing_limit"] = "Manual fallback"
        return params

    calculated_be = getattr(result, "effective_" + "width" + "_mm")
    params["Be_mm"] = calculated_be
    params["Be_effective_mm"] = calculated_be
    params["Be_calculated_mm"] = calculated_be
    params["Be_governing_limit"] = result.governing_limit
    params["Be_position"] = result.position
    params["girder_spacing_mm"] = spacing
    params["deck_overhang_mm"] = overhang if position == "exterior" else 0.0
    st.markdown(_property_strip_html([
        SectionMetric("Calculated Be", f"{_format_float(calculated_be, 1)} mm", "Used for transformed composite metadata only", "ready", True),
        SectionMetric("Governing limit", result.governing_limit, "Review before design use", "info"),
        SectionMetric("b_top used", f"{_format_float(top_width_used, 1)} mm", top_width_source, "neutral"),
        SectionMetric("Manual Be kept", f"{_format_float(manual_be, 1)} mm", "Available by switching mode to Manual", "neutral"),
    ]), unsafe_allow_html=True)
    with st.expander("Effective slab width candidate limits", expanded=False):
        _render_effective_width_candidates(result)
    return params


def _render_precast_composite_girder_metadata_inputs(preset: dict[str, Any]) -> dict[str, float]:
    """Render explicit deck/topping metadata for precast composite girder presets.

    These values are not part of the precast girder polygon generator. They are
    stored in section_parameters only for display-only transformed composite
    properties and Beam/Girder SLS service-basis routing.
    """

    preset_key = str(preset.get("key", "precast_girder"))
    display_name = str(preset.get("display_name", "Precast girder"))
    st.markdown("##### Composite Deck / Topping Metadata")
    st.markdown(
        f'<div class="cpmm-section-note">{display_name} deck/topping metadata is explicit and display-only. '
        "It is not merged into the precast polygon and is not used by PMM, prestress, or report logic.</div>",
        unsafe_allow_html=True,
    )
    defaults = _precast_composite_girder_metadata_defaults(preset)
    columns = st.columns(2)
    with columns[0]:
        tslab = _render_metadata_number_input(
            name="Tslab_mm",
            label="Tslab Deck/topping thickness (mm)",
            preset_key=preset_key,
            default=defaults["Tslab_mm"],
            min_value=0.0,
            max_value=3000.0,
            step=5.0,
            help_text="Composite deck/topping thickness metadata. Not merged into the precast girder polygon.",
        )
        girder_length = _render_locked_setup_span_metadata(preset_key)
    with columns[1]:
        be = _render_metadata_number_input(
            name="Be_mm",
            label="Be Effective slab width (mm)",
            preset_key=preset_key,
            default=defaults["Be_mm"],
            min_value=1.0,
            max_value=50000.0,
            step=10.0,
            help_text="Manual effective width. AASHTO.BE1 helper can calculate Be below when selected.",
        )
    return {"Tslab_mm": tslab, "Be_mm": be, "girder_length_mm": girder_length}


def _render_composite_metadata_panel(params: dict[str, Any], composite_active: bool) -> None:
    """Show common calculated composite metadata for composite-capable girders."""

    tslab = float(params.get("Tslab_mm", 0.0))
    be = float(params.get("Be_mm", 0.0))
    ebeam = float(params.get("Ebeam_MPa", 0.0))
    edeck = float(params.get("Edeck_MPa", 0.0))
    n_ratio = edeck / ebeam if ebeam > 0 else 0.0
    st.markdown("##### Calculated Composite Metadata")
    st.markdown(
        _kv_panel_html(
            [
                ("Composite transformed properties", "Active" if composite_active else "Not active"),
                ("Tslab", f"{_format_float(tslab, 1)} mm"),
                ("Be", f"{_format_float(be, 1)} mm"),
                ("Ebeam", _format_ec(ebeam)),
                ("Edeck", _format_ec(edeck)),
                ("n = Edeck/Ebeam", _format_float(n_ratio, 3)),
                ("Btransformed = n x Be", f"{_format_float(n_ratio * be, 1)} mm"),
                ("Be mode", str(params.get("Be_mode", "Manual"))),
                ("Be governing limit", str(params.get("Be_governing_limit", "Manual"))),
            ]
        ),
        unsafe_allow_html=True,
    )


def _render_parametric_i_girder_dimension_qa(params: dict[str, Any]) -> None:
    """Show concise engineering-oriented checks for the parametric I-girder preset."""
    b1 = float(params.get("B1_mm", 0.0))
    b2 = float(params.get("B2_mm", 0.0))
    d1 = float(params.get("D1_mm", 0.0))
    d2 = float(params.get("D2_mm", 0.0))
    d3 = float(params.get("D3_mm", 0.0))
    d5 = float(params.get("D5_mm", 0.0))
    d6 = float(params.get("D6_mm", 0.0))
    t1 = float(params.get("T1_mm", 0.0))
    t2 = float(params.get("T2_mm", 0.0))
    c1 = float(params.get("C1_mm", 0.0))
    web_zone = d1 - d2 - d3 - d5 - d6

    checks = [
        SectionMetric("Depth stack", "OK" if web_zone > 0 else "Invalid", f"Web clear zone = {_format_float(web_zone, 1)} mm", "ready" if web_zone > 0 else "danger", True),
        SectionMetric("Top transition", "OK" if 0 < t1 <= min(b1, b2) else "Review", "T1 must connect within both flange widths", "ready" if 0 < t1 <= min(b1, b2) else "warning", True),
        SectionMetric("Bottom transition", "OK" if 0 < t2 <= min(b1, b2) else "Review", "T2 must connect within both flange widths", "ready" if 0 < t2 <= min(b1, b2) else "warning", True),
        SectionMetric("Chamfer", "None" if c1 == 0 else f"{_format_float(c1, 1)} mm", "C1 is used only at external bottom/top corners in this preset", "neutral" if c1 == 0 else "info"),
    ]

    st.markdown("##### I-Girder Dimension QA")
    st.markdown(
        '<div class="cpmm-section-note">Precast I-Girder is symmetric about the vertical centerline. '
        "Composite deck/topping metadata can be defined below for transformed-section display, but the generated polygon remains precast-only.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_property_strip_html(checks), unsafe_allow_html=True)
    with st.expander("I-Girder zone breakdown", expanded=False):
        st.markdown(
            _kv_panel_html(
                [
                    ("Top flange zone", f"B1 {_format_float(b1, 1)} mm × D2 {_format_float(d2, 1)} mm"),
                    ("Top haunch / taper", f"D3 {_format_float(d3, 1)} mm; taper from B1 to T1"),
                    ("Web clear zone", f"{_format_float(web_zone, 1)} mm between haunches"),
                    ("Web widths", f"T1 {_format_float(t1, 1)} mm / T2 {_format_float(t2, 1)} mm"),
                    ("Bottom haunch / taper", f"D6 {_format_float(d6, 1)} mm; taper from T2 to B2"),
                    ("Bottom flange zone", f"B2 {_format_float(b2, 1)} mm × D5 {_format_float(d5, 1)} mm"),
                ]
            ),
            unsafe_allow_html=True,
        )



def _render_parametric_plank_girder_dimension_qa(preset: dict[str, Any], params: dict[str, Any]) -> None:
    """Show concise QA and transformed-width metadata for plank girder presets."""
    b = float(params.get("B_mm", 0.0))
    b1 = float(params.get("b1_mm", 0.0))
    b2 = float(params.get("b2_mm", 0.0))
    b3 = float(params.get("b3_mm", 0.0))
    h = float(params.get("H_mm", 0.0))
    h1 = float(params.get("h1_mm", 0.0))
    h2 = float(params.get("h2_mm", 0.0))
    tslab = float(params.get("Tslab_mm", 0.0))
    be = float(params.get("Be_mm", 0.0))
    ebeam = float(params.get("Ebeam_MPa", 0.0))
    edeck = float(params.get("Edeck_MPa", 0.0))
    girder_length = float(params.get("girder_length_mm", 0.0))
    n_ratio = edeck / ebeam if ebeam > 0 else 0.0
    btransformed = n_ratio * be
    is_interior = _is_interior_plank_girder_key(str(preset.get("key", "")))
    width_rule = b - b3 - (2.0 * b2 if is_interior else b2)
    width_ok = abs(width_rule) <= max(2.0, 0.005 * max(b, 1.0))
    side_label = "Interior" if is_interior else "Exterior"

    checks = [
        SectionMetric("Plank type", side_label, "Precast-only polygon; deck slab retained as composite metadata", "info", True),
        SectionMetric("Width stack", "OK" if width_ok else "Review", f"B - b3 - {'2b2' if is_interior else 'b2'} = {_format_float(width_rule, 1)} mm", "ready" if width_ok else "warning", True),
        SectionMetric("Depth stack", "OK" if 0 <= h1 <= h2 < h else "Invalid", f"h1 {_format_float(h1, 1)} mm / h2 {_format_float(h2, 1)} mm / H {_format_float(h, 1)} mm", "ready" if 0 <= h1 <= h2 < h else "danger", True),
        SectionMetric("Composite mode", "Metadata only", "Tslab/Be/n are not merged into the precast polygon in this milestone", "info"),
        SectionMetric("n = Edeck/Ebeam", _format_float(n_ratio, 3), f"Edeck {_format_float(edeck, 0)} / Ebeam {_format_float(ebeam, 0)} MPa", "ready" if n_ratio > 0 else "danger"),
        SectionMetric("Btransformed", f"{_format_float(btransformed, 1)} mm", "Auto = n × Be", "ready" if btransformed > 0 else "danger"),
    ]

    st.markdown("##### Plank Girder Dimension / Composite QA")
    st.markdown(
        '<div class="cpmm-section-note">Precast Plank Girder is generated as a precast-only section. '
        "Be can be manual or calculated by the AASHTO.BE1 helper; n and Btransformed are calculated automatically for composite metadata.</div>",
        unsafe_allow_html=True,
    )
    st.markdown(_property_strip_html(checks), unsafe_allow_html=True)
    with st.expander("Plank geometry / transformed-width breakdown", expanded=False):
        st.markdown(
            _kv_panel_html(
                [
                    ("Precast geometry", f"B {_format_float(b, 1)} mm, b3 {_format_float(b3, 1)} mm, H {_format_float(h, 1)} mm"),
                    ("Side offsets", f"b1 {_format_float(b1, 1)} mm, b2 {_format_float(b2, 1)} mm"),
                    ("Side transition", f"h1 {_format_float(h1, 1)} mm, h2 {_format_float(h2, 1)} mm"),
                    ("Deck/topping metadata", f"Tslab {_format_float(tslab, 1)} mm"),
                    ("Effective width", f"Be {_format_float(be, 1)} mm ({params.get('Be_mode', 'Manual')})"),
                    ("Modular ratio", f"n = {_format_float(n_ratio, 4)}"),
                    ("Transformed width", f"Btransformed = {_format_float(btransformed, 1)} mm"),
                    ("Girder length", f"{_format_float(girder_length, 1)} mm"),
                ]
            ),
            unsafe_allow_html=True,
        )

def _inertia_display(value: str) -> str:
    return "Not calculated" if value == "TODO" else value


def _validation_label(result: ValidationResult) -> str:
    if result.errors:
        return "Error"
    if result.warnings:
        return "Warning"
    return "OK"


def _readiness_label(result: ValidationResult) -> str:
    if result.errors:
        return "Not Ready"
    if result.warnings:
        return "Warning"
    return "Ready"


def _render_validation_panel(result: ValidationResult) -> None:
    st.markdown(
        _status_panel_html(
            [
                SectionMetric("Validation", _validation_label(result), "", _validation_status(result), True),
                SectionMetric("Errors", f"{len(result.errors):,}", "", "danger" if result.errors else "neutral"),
                SectionMetric("Warnings", f"{len(result.warnings):,}", "", "warning" if result.warnings else "neutral"),
            ]
        ),
        unsafe_allow_html=True,
    )

    if result.errors:
        for error in result.errors:
            st.error(f"ERROR: {error}")

    if result.warnings:
        for warning in result.warnings:
            st.warning(f"WARNING: {warning}")

    if result.info and (result.errors or result.warnings):
        st.markdown(_message_list_html([f"INFO: {info}" for info in result.info]), unsafe_allow_html=True)


def _render_section_definition_panel(
    presets: list[dict[str, Any]],
    categories: list[str],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Render the compact top context panel and return the active preset/materials."""

    analysis_mode_settings = _analysis_mode_from_session_state()
    available_presets = _filter_presets_for_member_type(presets, analysis_mode_settings)
    available_categories = _categories_for_filtered_presets(categories, available_presets)

    with st.container(border=True):
        st.markdown("#### Section Definition")
        st.markdown(
            '<div class="cpmm-section-note">Select the active concrete section. The main dimension editor is shown below beside the live section preview.</div>',
            unsafe_allow_html=True,
        )

        preset_keys, preset_map, label_map = _preset_maps(available_presets)
        if not preset_keys:
            st.error("No section presets are available.")
            return None

        st.caption(
            f"Active workflow: {analysis_mode_label(analysis_mode_settings)} · "
            f"{_member_type_filter_description(analysis_mode_settings)}"
        )

        selector_state_key = "section_preset_selector_key"
        selector_initial_key = _initial_preset_selector_key(preset_keys)
        if st.session_state.get(selector_state_key) not in preset_keys:
            st.session_state[selector_state_key] = selector_initial_key

        selected_preset_key = st.selectbox(
            "Section Type / Preset",
            preset_keys,
            index=preset_keys.index(selector_initial_key),
            format_func=lambda key: label_map.get(str(key), str(key)),
            key=selector_state_key,
            help=(
                "Select the actual section geometry directly. The geometry family/category is shown "
                "after the dot for reference only."
            ),
        )
        preset = preset_map[str(selected_preset_key)]
        selected_category = str(preset.get("category", "General"))

        # Sync the selected preset key immediately, before geometry generation.
        # This prevents the direct Section Type / Preset selector from snapping
        # back to the previous preset and requiring a second click on rerun.
        st.session_state["section_preset_key"] = str(selected_preset_key)
        st.session_state["section_preset_name"] = str(preset.get("display_name", selected_preset_key))

        st.caption(
            f"Geometry family: {selected_category} · "
            "Geometry inputs are edited in the definition workspace below."
        )

        with st.container(border=True):
            _render_reinforcement_prestress_system_panel(preset)

        with st.expander("Project / workflow / axis details", expanded=False):
            _render_member_type_section_guidance(preset)
            _render_axis_convention_card()

        with st.expander("Browse by geometry family", expanded=False):
            st.caption(
                "Optional helper for reviewing the section families available under the active member workflow. "
                "The direct selector above is the primary control."
            )
            loaded_category = preset.get("category")
            category_index = available_categories.index(loaded_category) if loaded_category in available_categories else 0
            browse_category = st.selectbox("Section Category", available_categories, index=category_index)
            family_presets = [item for item in available_presets if item.get("category") == browse_category]
            if family_presets:
                family_labels = [item["display_name"] for item in family_presets]
                st.caption("Available in this family: " + ", ".join(family_labels))
            else:
                st.caption("No presets are available in this family yet.")

        with st.expander("Concrete Material Assignment", expanded=False):
            material_assignment = _render_concrete_material_assignment(preset)

        _render_section_builder_status_strip(preset, material_assignment)

    return preset, material_assignment


def _render_geometry_parameters_workspace(
    preset: dict[str, Any],
    material_assignment: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Render the main geometry input workspace shown beside the live preview."""

    with st.container(border=True):
        st.markdown("#### Geometry Parameters")
        st.markdown(
            '<div class="cpmm-section-note">Primary section dimensions are kept at the same level as the live preview. '
            'Workflow, axis, reinforcement, and material details remain collapsed above.</div>',
            unsafe_allow_html=True,
        )

        label_mode_label = st.selectbox("Dimension labels", ["Symbol + Value", "Symbol only", "Value only"], index=0)
        label_mode = {"Symbol + Value": "symbol_value", "Symbol only": "symbol", "Value only": "value"}[label_mode_label]

        params: dict[str, Any] = {}
        _sync_rectangular_chamfered_legacy_widget_defaults(preset)
        hidden_material_parameters = _hidden_material_parameter_names(preset)
        visible_parameters = [
            parameter for parameter in preset["parameters"] if parameter["name"] not in hidden_material_parameters
        ]
        parameter_columns = st.columns(2)
        for index, parameter in enumerate(visible_parameters):
            with parameter_columns[index % len(parameter_columns)]:
                if parameter.get("type", "number") == "number":
                    params[parameter["name"]] = _number_input(parameter, preset["key"])
                else:
                    st.warning(f"Unsupported parameter type: {parameter.get('type')}")

        if _composite_metadata_enabled_for_workflow(preset):
            params["Ebeam_MPa"] = float(material_assignment["Ebeam_MPa"])
            params["Edeck_MPa"] = float(material_assignment.get("Edeck_MPa", material_assignment["Ebeam_MPa"]))
            if _is_parametric_i_girder(preset) or _is_precast_u_girder(preset) or _is_precast_box_beam(preset):
                params.update(_render_precast_composite_girder_metadata_inputs(preset))

            if _aashto_effective_width_helper_enabled(preset):
                params = _render_effective_width_helper(preset, params)
            else:
                params["Be_mode"] = "Manual"
                params["Be_manual_mm"] = float(params.get("Be_mm", 0.0) or 0.0)
                params["Be_effective_mm"] = float(params.get("Be_mm", 0.0) or 0.0)
                params["Be_governing_limit"] = "Manual / ACI building context"
                st.markdown(
                    '<div class="cpmm-section-note">Building Beam/Girder uses shared precast I-Girder composite metadata under ACI 318. '
                    "AASHTO effective-width helper and bridge staged SLS/load workflows remain hidden; enter the slab/effective width appropriate for the building design basis.</div>",
                    unsafe_allow_html=True,
                )

            composite_key = f"{preset['key']}_composite_enabled"
            params["composite_enabled"] = bool(
                st.checkbox(
                    "Enable composite deck/topping transformed properties",
                    value=bool(st.session_state.get(composite_key, True)),
                    help=(
                        "When enabled, Section Builder calculates transformed composite properties "
                        "from Tslab, Be, Ebeam, and Edeck. The result remains separate from gross "
                        "section properties and is not used by PMM in this milestone."
                    ),
                    key=composite_key,
                )
            )
            composite_active = composite_deck_is_active(
                params,
                member_type=_analysis_mode_from_session_state().member_type,
            )
            _render_composite_metadata_panel(params, composite_active)
        elif _is_composite_capable_preset(preset) and is_building_beam_girder_workflow(_analysis_mode_from_session_state()):
            st.info(
                "Shared precast girder geometry is active under the Building Beam/Girder ACI workflow. "
                "Bridge staged SLS inputs remain hidden for this workflow."
            )

        if _is_parametric_i_girder(preset):
            _render_parametric_i_girder_dimension_qa(params)
        if _is_parametric_plank_girder(preset):
            _render_parametric_plank_girder_dimension_qa(preset, params)

    return label_mode, params

def _build_geometry(
    preset: dict[str, Any],
    params: dict[str, Any],
) -> tuple[Any | None, list[Any], ValidationResult]:
    generator_name = preset["generator"]
    if generator_name == "rectangular_chamfered" and "chamfer_mm" in params:
        params = {
            **params,
            "chamfer_x_mm": params.get("chamfer_x_mm", params["chamfer_mm"]),
            "chamfer_y_mm": params.get("chamfer_y_mm", params["chamfer_mm"]),
        }
    generator_params = {name: params[name] for name in _geometry_parameter_names(preset) if name in params}
    try:
        geometry = default_registry.geometry(generator_name)(**generator_params, name=preset["display_name"])
        dimensions = default_registry.dimensions(preset["dimensions_generator"])(**generator_params)
    except ValueError as exc:
        return None, [], ValidationResult(
            is_valid=False,
            errors=[str(exc)],
            info=["Preview is paused until geometry inputs are valid."],
        )

    validation = validate_section_geometry(geometry)
    return geometry, dimensions, validation


def _store_valid_section_state(preset: dict[str, Any], params: dict[str, Any], geometry: Any, dimensions: list[Any]) -> None:
    st.session_state["section_preset_key"] = preset["key"]
    st.session_state["section_preset_name"] = preset["display_name"]
    st.session_state["section_category"] = str(preset.get("category", ""))
    st.session_state["girder_section_family"] = _girder_section_family(preset)
    st.session_state["girder_service_default_basis"] = _recommended_service_basis_for_preset(preset)
    # Do not write to Streamlit widget-owned reinforcement flag keys here.
    # The checkboxes in _render_reinforcement_prestress_system_panel already
    # initialize and own ORDINARY_REBAR_FLAG_KEY / PRESTRESSING_STEEL_FLAG_KEY.
    # Assigning those keys after widget creation raises StreamlitAPIException.
    if ORDINARY_REBAR_FLAG_KEY not in st.session_state or PRESTRESSING_STEEL_FLAG_KEY not in st.session_state:
        default_rebar, default_prestress = _default_reinforcement_flags_for_preset(preset)
        st.session_state.setdefault(ORDINARY_REBAR_FLAG_KEY, default_rebar)
        st.session_state.setdefault(PRESTRESSING_STEEL_FLAG_KEY, default_prestress)
    st.session_state["section_parameters"] = params
    st.session_state["section_geometry"] = geometry
    st.session_state["section_dimensions"] = dimensions


def _clear_section_geometry_state() -> None:
    st.session_state["section_geometry"] = None
    st.session_state["section_dimensions"] = []


def _geometry_status_rows(
    geometry: Any | None,
    dimensions: list[Any],
    validation: ValidationResult,
) -> list[tuple[str, str]]:
    geometry_ready = geometry is not None and validation.is_valid
    return [
        ("Geometry", "Ready" if geometry_ready else "Not Ready"),
        ("Preview", "Geometry only" if geometry_ready else "Not Available"),
        ("Validation", _validation_label(validation)),
        ("Dimension guides", f"{len(dimensions):,}"),
        ("Rebar/prestress display", "Hidden in Section Builder"),
    ]


def _render_section_preview_panel(
    geometry: Any | None,
    dimensions: list[Any],
    label_mode: str,
    validation: ValidationResult,
) -> None:
    # Section Builder is intentionally a geometry/section-definition workspace.
    # Rebar and prestressing steel are edited and previewed on their own pages.
    # Keeping this preview geometry-only avoids confusing stale reinforcement
    # layouts with the active section definition while still preserving stored
    # rebar/prestress data for analysis when enabled by section flags.
    preview_rebars: list[Any] = []
    preview_prestress_elements: list[Any] = []

    with st.container(border=True):
        st.markdown("#### Live Section Preview")
        if geometry is not None and validation.is_valid:
            st.plotly_chart(
                create_section_preview(
                    geometry,
                    dimensions,
                    label_mode,
                    preview_rebars,
                    preview_prestress_elements,
                ),
                use_container_width=True,
                key="section_builder_preview",
            )
        else:
            st.info("Preview is paused until geometry inputs are valid.")

        st.caption(
            "Section Builder preview is locked to geometry only. "
            "Ordinary rebar and prestressing steel are previewed on the Rebar and Prestress pages."
        )
        st.markdown(
            _kv_panel_html(_geometry_status_rows(geometry, dimensions, validation)),
            unsafe_allow_html=True,
        )
        _render_validation_panel(validation)


def _parameter_rows(preset: dict[str, Any], params: dict[str, Any]) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for parameter in preset["parameters"]:
        name = parameter["name"]
        label = parameter.get("label", name)
        if name in params:
            rows.append((label, _format_parameter_value(params[name])))
    return rows


def _render_composite_transformed_properties_summary(
    preset: dict[str, Any],
    params: dict[str, Any],
    geometry: Any | None,
    validation: ValidationResult,
) -> None:
    """Display transformed composite properties without changing gross/PMM properties."""

    settings = _analysis_mode_from_session_state()
    if not _composite_metadata_enabled_for_workflow(preset, settings):
        return

    st.subheader("Composite Transformed Section Properties")
    st.markdown(
        '<div class="cpmm-section-note">Transformed composite properties are calculated on the primary/precast concrete basis. '
        "The deck/topping rectangle is transformed by n = Edeck/Ebeam and placed above the precast top fiber. "
        "These values remain separate from PMM and from the Precast Gross Section Properties.</div>",
        unsafe_allow_html=True,
    )

    if geometry is None or not validation.is_valid:
        st.info("Composite transformed properties are paused until the precast geometry is valid.")
        return

    deck = composite_deck_input_from_parameters(params, member_type=settings.member_type)
    if not deck.enabled:
        st.info(
            "Composite deck/topping not active. Enable composite deck/topping and provide positive "
            "Tslab, Be, Ebeam, and Edeck values to calculate transformed composite properties."
        )
        return

    try:
        composite = calculate_composite_transformed_section_from_geometry(geometry, deck)
    except ValueError as exc:
        st.warning(f"Composite transformed properties could not be calculated: {exc}")
        return

    st.markdown(
        _property_strip_html(
            [
                SectionMetric("Composite Area", f"{composite.area_mm2:,.1f} mm^2", "precast + transformed deck area"),
                SectionMetric("Centroid yb", _format_optional_mm(composite.centroid_y_from_bottom_mm, 2), "from precast bottom fiber"),
                SectionMetric("Ix,tr", f"{composite.ix_mm4:,.3e} mm^4", "about transformed composite centroid"),
                SectionMetric("Iy,tr", f"{composite.iy_mm4:,.3e} mm^4", "about transformed composite centroid"),
                SectionMetric(
                    "Fiber distances",
                    f"ctop {_format_optional_mm(composite.c_top_mm, 1)} / cbottom {_format_optional_mm(composite.c_bottom_mm, 1)}",
                    "top fiber includes deck/topping; bottom fiber remains precast bottom",
                ),
                SectionMetric(
                    "Z top / bottom",
                    f"{composite.z_top_mm3:,.3e} / {composite.z_bottom_mm3:,.3e} mm^3"
                    if composite.z_top_mm3 and composite.z_bottom_mm3
                    else "N/A",
                    "transformed section modulus",
                ),
                SectionMetric("n = Edeck/Ebeam", _format_float(composite.modular_ratio, 4), "deck transformed to primary concrete basis", "info"),
                SectionMetric("Btransformed", f"{_format_float(getattr(composite, 'transformed_' + 'width' + '_mm'), 1)} mm", "n x Be", "info"),
                SectionMetric("Composite scope", "Display only", "not used by PMM/SLS solver yet", "info", True),
            ]
        ),
        unsafe_allow_html=True,
    )

    with st.expander("Composite transformed-section breakdown", expanded=False):
        st.markdown(
            _kv_panel_html(
                [
                    ("Basis", "Deck/topping transformed to primary/precast concrete"),
                    ("Precast area", f"{composite.precast_area_mm2:,.1f} mm^2"),
                    ("Precast centroid y", _format_optional_mm(composite.precast_centroid_y_mm, 2)),
                    ("Deck transformed area", f"{composite.deck_area_transformed_mm2:,.1f} mm^2"),
                    ("Deck centroid y", _format_optional_mm(composite.deck_centroid_y_mm, 2)),
                    ("Top fiber y", _format_optional_mm(composite.top_fiber_y_mm, 2)),
                    ("Bottom fiber y", _format_optional_mm(composite.bottom_fiber_y_mm, 2)),
                    ("Warning count", f"{len(composite.warnings):,}"),
                ]
            ),
            unsafe_allow_html=True,
        )
    if composite.warnings:
        st.markdown(_message_list_html([f"COMPOSITE WARNING: {warning}" for warning in composite.warnings]), unsafe_allow_html=True)


def _render_section_properties_summary(
    preset: dict[str, Any],
    params: dict[str, Any],
    geometry: Any | None,
    validation: ValidationResult,
) -> None:
    st.subheader("Precast Gross Section Properties")
    st.markdown(
        '<div class="cpmm-section-note">A, centroid, Ix, Iy, fiber distances, and section modulus shown here are based on the '
        'generated gross concrete polygon only. Composite slab/topping properties are metadata at this stage and are not included '
        'in the section properties below.</div>',
        unsafe_allow_html=True,
    )

    if geometry is None or not validation.is_valid:
        st.markdown(
            _property_strip_html(
                [
                    SectionMetric("Gross Area", "N/A", "Gross concrete polygon only"),
                    SectionMetric("Centroid", "N/A", "yb is measured upward from bottom fiber"),
                    SectionMetric("Ix", "Not calculated"),
                    SectionMetric("Iy", "Not calculated"),
                    SectionMetric("Holes / Voids", "N/A"),
                    SectionMetric("Active Preset", preset["display_name"], "", "info"),
                    SectionMetric("Category", str(preset.get("category", "N/A")), "", "neutral"),
                    SectionMetric("Readiness", "Not Ready", "", "danger", True),
                ]
            ),
            unsafe_allow_html=True,
        )
        if rows := _parameter_rows(preset, params):
            st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        return

    summary = summarize_geometry(geometry)
    c_top = summary.top_fiber_distance_mm
    c_bottom = summary.bottom_fiber_distance_mm
    yb = summary.centroid_y_from_bottom_mm
    y_mid_offset = summary.centroid_y_offset_from_mid_depth_mm
    x_mid_offset = getattr(summary, "centroid_x_offset_from_mid_" + "width" + "_mm")
    composite_detail = (
        "Tslab/Be/n/Btransformed excluded from gross A/I/Z"
        if _is_composite_capable_preset(preset)
        else "Concrete polygon only; no transformed deck/slab included"
    )

    st.markdown(
        _property_strip_html(
            [
                SectionMetric("Gross Area", f"{summary.area_mm2:,.1f} mm^2", "Precast/gross concrete polygon only"),
                SectionMetric(
                    "Centroid x",
                    _format_optional_mm(summary.centroid_x_mm, 2),
                    f"offset from mid-width = {_signed_mm(x_mid_offset, 2)}",
                ),
                SectionMetric(
                    "Centroid yb",
                    _format_optional_mm(yb, 2),
                    f"from bottom fiber; mid-depth offset = {_signed_mm(y_mid_offset, 2)}",
                ),
                SectionMetric("Ix", _inertia_display(summary.ix_display), "about centroidal x-axis"),
                SectionMetric("Iy", _inertia_display(summary.iy_display), "about centroidal y-axis"),
                SectionMetric(
                    "Fiber distances",
                    f"ctop {_format_optional_mm(c_top, 1)} / cbottom {_format_optional_mm(c_bottom, 1)}",
                    "Used directly for S = I / c stress checks",
                ),
                SectionMetric("Z top / bottom", f"{summary.z_top_display} / {summary.z_bottom_display}", "gross section modulus"),
                SectionMetric("Composite slab", "Excluded", composite_detail, "info"),
                SectionMetric("Holes / Voids", f"{len(geometry.holes):,}"),
                SectionMetric("Active Preset", preset["display_name"]),
                SectionMetric("Category", str(preset.get("category", "N/A"))),
                SectionMetric("ULS PMM", "Supported", "Current section-analysis workflow", "ready"),
                SectionMetric(
                    "Beam/Girder",
                    "Planned" if _is_composite_capable_preset(preset) else "N/A",
                    "Future station assignment",
                    "info" if _is_composite_capable_preset(preset) else "neutral",
                ),
                SectionMetric("Readiness", _readiness_label(validation), "", _validation_status(validation), True),
            ]
        ),
        unsafe_allow_html=True,
    )

    with st.expander("Section property convention", expanded=False):
        st.markdown(
            _kv_panel_html(
                [
                    ("Property basis", "Gross concrete / precast polygon only"),
                    ("Composite status", "Tslab, Be, n, and Btransformed are not merged into A, centroid, Ix, Iy, or Z"),
                    ("Coordinate y", "Positive upward in generated section coordinates"),
                    ("Centroid yb", f"{_format_optional_mm(yb, 2)} measured from bottom fiber"),
                    ("Mid-depth offset", _signed_mm(y_mid_offset, 2)),
                    ("Top fiber distance ctop", _format_optional_mm(c_top, 2)),
                    ("Bottom fiber distance cbottom", _format_optional_mm(c_bottom, 2)),
                    ("Section modulus", "Ztop = Ix / ctop; Zbottom = Ix / cbottom"),
                ]
            ),
            unsafe_allow_html=True,
        )

    if summary.warnings:
        st.markdown(_message_list_html([f"PROPERTY WARNING: {warning}" for warning in summary.warnings]), unsafe_allow_html=True)

    _render_composite_transformed_properties_summary(preset, params, geometry, validation)

    with st.expander("Geometry Inputs", expanded=False):
        st.markdown(
            _kv_panel_html(
                [
                    *_parameter_rows(preset, params),
                    ("Parameter count", f"{len(params):,}"),
                    ("Outer vertices", f"{len(geometry.outer_polygon):,}"),
                    ("Validation errors", f"{len(validation.errors):,}"),
                    ("Validation warnings", f"{len(validation.warnings):,}"),
                ]
            ),
            unsafe_allow_html=True,
        )


def render_section_builder() -> None:
    st.markdown(_SECTION_BUILDER_CSS, unsafe_allow_html=True)
    st.subheader("Section Builder")
    st.caption("Build the active concrete section geometry and review its live preview before running analysis.")

    presets = load_section_presets()
    categories = load_section_categories()

    selection = _render_section_definition_panel(presets, categories)

    if selection is None:
        return

    preset, material_assignment = selection

    parameter_col, preview_col = st.columns([0.92, 1.08], gap="large")
    with parameter_col:
        label_mode, params = _render_geometry_parameters_workspace(preset, material_assignment)

    geometry, dimensions, validation = _build_geometry(preset, params)

    if geometry is not None and validation.is_valid:
        _store_valid_section_state(preset, params, geometry, dimensions)
    else:
        _clear_section_geometry_state()

    with preview_col:
        _render_section_preview_panel(geometry, dimensions, label_mode, validation)

    _render_section_properties_summary(preset, params, geometry, validation)

    if geometry is not None:
        with st.expander("Generated SectionGeometry"):
            st.json(geometry.model_dump())
