"""Metadata-driven Streamlit section builder."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import streamlit as st

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import analysis_mode_label
from concrete_pmm_pro.core.concrete_materials import (
    DEFAULT_DECK_TOPPING_MATERIAL,
    c45_precast_material,
    concrete_materials_by_name,
    ensure_concrete_material_library,
)
from concrete_pmm_pro.core.models import ConcreteMaterial
from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.presets import load_section_categories, load_section_presets
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import ValidationResult, validate_section_geometry
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

    assignment: dict[str, Any] = {
        "primary_material_name": selected_primary,
        "primary_fc_MPa": primary_material.fc_MPa,
        "Ebeam_MPa": primary_material.effective_Ec_MPa,
        "is_composite_applicable": _is_parametric_plank_girder(preset),
    }

    if _is_parametric_plank_girder(preset):
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


def _is_parametric_plank_girder(preset: dict[str, Any]) -> bool:
    return str(preset.get("key", "")).startswith("parametric_plank_girder_")



def _analysis_mode_from_session_state() -> AnalysisModeSettings:
    value = st.session_state.get("analysis_mode_settings")
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


def _render_member_type_section_guidance(preset: dict[str, Any]) -> None:
    """Show non-invasive Section Builder guidance for the active member workflow."""
    settings = _analysis_mode_from_session_state()
    preset_key = str(preset.get("key", ""))
    is_girder_preset = preset_key == "parametric_i_girder" or preset_key.startswith("parametric_plank_girder_")

    rows = [("Active member workflow", analysis_mode_label(settings))]
    if settings.member_type == "beam_girder":
        rows.extend(
            [
                ("Recommended section family", "I-Girder / Plank Girder / future bridge girder presets"),
                ("Current geometry status", "Gross precast polygon only"),
                ("Girder design checks", "Future milestone; not implemented in MEMBER.TYPE1"),
                ("Current preset fit", "Good for Beam/Girder" if is_girder_preset else "Review: selected preset is not a girder preset"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        if not is_girder_preset:
            st.warning("Beam/Girder mode is active, but the selected preset is not a dedicated girder preset. Use only with engineering judgment.")
        st.caption("MEMBER.TYPE1 routes the workflow only. It does not add AASHTO girder SLS/ULS equations yet.")
    elif settings.member_type == "general_section":
        rows.extend(
            [
                ("Primary analysis meaning", "General section review"),
                ("PMM tools", "Available with user-controlled load interpretation"),
                ("Deck/topping material", "Not used unless a future composite workflow is explicitly added"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        st.caption("General Section mode is flexible but requires explicit engineering interpretation of Pu, Mux, and Muy.")
    else:
        rows.extend(
            [
                ("Primary analysis meaning", "Column / Pier / Wall / Pylon PMM"),
                ("PMM demand inputs", "Pu, Mux, Muy"),
                ("Concrete material used by PMM", "Primary / section concrete only"),
                ("Deck/topping material", "Ignored by PMM"),
            ]
        )
        st.markdown("##### Member Workflow Guidance")
        st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)

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
        '<div class="cpmm-section-note">Parametric I-Girder is symmetric about the vertical centerline. '
        "The generated polygon is analysis-ready for ULS PMM; SLS / Beam-Girder assignment are planned workflow extensions.</div>",
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
    is_interior = str(preset.get("key", "")) == "parametric_plank_girder_interior"
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
        '<div class="cpmm-section-note">Parametric Plank Girder is generated as a precast-only section. '
        "Be is currently manual/project-defined; n and Btransformed are calculated automatically for future AASHTO composite checks.</div>",
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
                    ("Effective width", f"Be {_format_float(be, 1)} mm (manual now; AASHTO auto planned)"),
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
) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    with st.container(border=True):
        st.markdown("#### Section Definition")
        st.markdown(
            '<div class="cpmm-section-note">Define the concrete section geometry used by downstream analysis.</div>',
            unsafe_allow_html=True,
        )

        st.markdown("##### Section Type")
        preset_keys, preset_map, label_map = _preset_maps(presets)
        if not preset_keys:
            st.error("No section presets are available.")
            return None

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
            "Select a parametric preset, then edit the dimensions below."
        )

        _render_member_type_section_guidance(preset)

        with st.expander("Browse by geometry family", expanded=False):
            st.caption("Optional helper for filtering presets by family. The direct selector above is the primary control.")
            loaded_category = preset.get("category")
            category_index = categories.index(loaded_category) if loaded_category in categories else 0
            browse_category = st.selectbox("Section Category", categories, index=category_index)
            family_presets = [item for item in presets if item.get("category") == browse_category]
            if family_presets:
                family_labels = [item["display_name"] for item in family_presets]
                st.caption("Available in this family: " + ", ".join(family_labels))
            else:
                st.caption("No presets are available in this family yet.")

        material_assignment = _render_concrete_material_assignment(preset)

        st.markdown("##### Dimension Labels")
        label_mode_label = st.selectbox("Dimension label mode", ["Symbol + Value", "Symbol only", "Value only"], index=0)
        label_mode = {"Symbol + Value": "symbol_value", "Symbol only": "symbol", "Value only": "value"}[label_mode_label]

        st.markdown("##### Geometry Parameters")
        params: dict[str, Any] = {}
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

        if _is_parametric_plank_girder(preset):
            params["Ebeam_MPa"] = float(material_assignment["Ebeam_MPa"])
            params["Edeck_MPa"] = float(material_assignment.get("Edeck_MPa", material_assignment["Ebeam_MPa"]))
            be = float(params.get("Be_mm", 0.0))
            ebeam = float(params["Ebeam_MPa"])
            edeck = float(params["Edeck_MPa"])
            n_ratio = edeck / ebeam if ebeam > 0 else 0.0
            st.markdown("##### Calculated Composite Metadata")
            st.markdown(
                _kv_panel_html(
                    [
                        ("Ebeam", _format_ec(ebeam)),
                        ("Edeck", _format_ec(edeck)),
                        ("n = Edeck/Ebeam", _format_float(n_ratio, 3)),
                        ("Btransformed = n x Be", f"{_format_float(n_ratio * be, 1)} mm"),
                    ]
                ),
                unsafe_allow_html=True,
            )

        if _is_parametric_i_girder(preset):
            _render_parametric_i_girder_dimension_qa(params)
        if _is_parametric_plank_girder(preset):
            _render_parametric_plank_girder_dimension_qa(preset, params)

    return preset, label_mode, params


def _build_geometry(
    preset: dict[str, Any],
    params: dict[str, Any],
) -> tuple[Any | None, list[Any], ValidationResult]:
    generator_name = preset["generator"]
    try:
        geometry = default_registry.geometry(generator_name)(**params, name=preset["display_name"])
        dimensions = default_registry.dimensions(preset["dimensions_generator"])(**params)
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
    rebar_count: int,
    prestress_count: int,
) -> list[tuple[str, str]]:
    geometry_ready = geometry is not None and validation.is_valid
    return [
        ("Geometry", "Ready" if geometry_ready else "Not Ready"),
        ("Preview", "Available" if geometry_ready else "Not Available"),
        ("Validation", _validation_label(validation)),
        ("Dimension guides", f"{len(dimensions):,}"),
        ("Rebars shown", f"{rebar_count:,}"),
        ("Prestress elements shown", f"{prestress_count:,}"),
    ]


def _render_section_preview_panel(
    geometry: Any | None,
    dimensions: list[Any],
    label_mode: str,
    validation: ValidationResult,
) -> None:
    rebars = st.session_state.get("rebars", [])
    prestress_elements = st.session_state.get("prestress_elements", [])

    with st.container(border=True):
        st.markdown("#### Live Section Preview")
        if geometry is not None and validation.is_valid:
            st.plotly_chart(
                create_section_preview(
                    geometry,
                    dimensions,
                    label_mode,
                    rebars,
                    prestress_elements,
                ),
                use_container_width=True,
                key="section_builder_preview",
            )
        else:
            st.info("Preview is paused until geometry inputs are valid.")

        st.markdown(
            _kv_panel_html(_geometry_status_rows(geometry, dimensions, validation, len(rebars), len(prestress_elements))),
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
        if _is_parametric_plank_girder(preset)
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
                    "Planned" if (_is_parametric_i_girder(preset) or _is_parametric_plank_girder(preset)) else "N/A",
                    "Future station assignment",
                    "info" if (_is_parametric_i_girder(preset) or _is_parametric_plank_girder(preset)) else "neutral",
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

    definition_col, preview_col = st.columns([0.92, 1.08], gap="large")
    with definition_col:
        selection = _render_section_definition_panel(presets, categories)

    if selection is None:
        return

    preset, label_mode, params = selection
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
