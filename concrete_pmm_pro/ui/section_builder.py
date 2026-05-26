"""Metadata-driven Streamlit section builder."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import streamlit as st

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


def _format_parameter_value(value: Any) -> str:
    if isinstance(value, float):
        return _format_float(value, 2).rstrip("0").rstrip(".")
    return str(value)


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
        loaded_preset_key = st.session_state.get("section_preset_key")
        loaded_category = next((preset.get("category") for preset in presets if preset.get("key") == loaded_preset_key), None)
        category_index = categories.index(loaded_category) if loaded_category in categories else 0
        selected_category = st.selectbox("Category", categories, index=category_index)
        category_presets = [preset for preset in presets if preset.get("category") == selected_category]
        if not category_presets:
            st.info("No section presets are available in this category yet.")
            return None

        labels = [preset["display_name"] for preset in category_presets]
        loaded_label = next((preset["display_name"] for preset in category_presets if preset.get("key") == loaded_preset_key), None)
        label_index = labels.index(loaded_label) if loaded_label in labels else 0
        st.markdown("##### Preset / Labeling")
        selected_label = st.selectbox("Section preset", labels, index=label_index)
        preset = category_presets[labels.index(selected_label)]

        label_mode_label = st.selectbox("Dimension label mode", ["Symbol + Value", "Symbol only", "Value only"], index=0)
        label_mode = {"Symbol + Value": "symbol_value", "Symbol only": "symbol", "Value only": "value"}[label_mode_label]

        st.markdown("##### Geometry Parameters")
        params: dict[str, Any] = {}
        parameter_columns = st.columns(2)
        for index, parameter in enumerate(preset["parameters"]):
            with parameter_columns[index % len(parameter_columns)]:
                if parameter.get("type", "number") == "number":
                    params[parameter["name"]] = _number_input(parameter, preset["key"])
                else:
                    st.warning(f"Unsupported parameter type: {parameter.get('type')}")

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
    st.subheader("Section Properties")

    if geometry is None or not validation.is_valid:
        st.markdown(
            _property_strip_html(
                [
                    SectionMetric("Gross Area", "N/A"),
                    SectionMetric("Centroid", "N/A"),
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
    st.markdown(
        _property_strip_html(
            [
                SectionMetric("Gross Area", f"{summary.area_mm2:,.1f} mm^2"),
                SectionMetric(
                    "Centroid",
                    f"x {_format_float(summary.centroid_x_mm, 2)} / y {_format_float(summary.centroid_y_mm, 2)} mm",
                ),
                SectionMetric("Ix", _inertia_display(summary.ix_display)),
                SectionMetric("Iy", _inertia_display(summary.iy_display)),
                SectionMetric("Holes / Voids", f"{len(geometry.holes):,}"),
                SectionMetric("Active Preset", preset["display_name"]),
                SectionMetric("Category", str(preset.get("category", "N/A"))),
                SectionMetric("Readiness", _readiness_label(validation), "", _validation_status(validation), True),
            ]
        ),
        unsafe_allow_html=True,
    )

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
