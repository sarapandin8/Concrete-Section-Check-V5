"""Metadata-driven Streamlit section builder."""

from __future__ import annotations

from typing import Any

import streamlit as st

from concrete_pmm_pro.geometry import default_registry
from concrete_pmm_pro.geometry.presets import load_section_categories, load_section_presets
from concrete_pmm_pro.geometry.summary import summarize_geometry
from concrete_pmm_pro.geometry.validation import ValidationResult, validate_section_geometry
from concrete_pmm_pro.visualization import create_section_preview


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


def _render_validation_panel(result: ValidationResult) -> None:
    st.subheader("Validation")
    if result.errors:
        for error in result.errors:
            st.error(f"ERROR: {error}")
    else:
        st.success("No validation errors")

    if result.warnings:
        for warning in result.warnings:
            st.warning(f"WARNING: {warning}")
    else:
        st.info("WARNING: none")

    if result.info:
        for info in result.info:
            st.info(f"INFO: {info}")
    else:
        st.info("INFO: Geometry checks completed.")


def render_section_builder() -> None:
    st.subheader("Section Builder")
    presets = load_section_presets()
    categories = load_section_categories()
    loaded_preset_key = st.session_state.get("section_preset_key")
    loaded_category = next((preset.get("category") for preset in presets if preset.get("key") == loaded_preset_key), None)
    category_index = categories.index(loaded_category) if loaded_category in categories else 0
    selected_category = st.selectbox("Category", categories, index=category_index)
    category_presets = [preset for preset in presets if preset.get("category") == selected_category]
    if not category_presets:
        st.info("No section presets are available in this category yet.")
        return
    labels = [preset["display_name"] for preset in category_presets]
    loaded_label = next((preset["display_name"] for preset in category_presets if preset.get("key") == loaded_preset_key), None)
    label_index = labels.index(loaded_label) if loaded_label in labels else 0
    selected_label = st.selectbox("Section preset", labels, index=label_index)
    preset = category_presets[labels.index(selected_label)]
    label_mode_label = st.selectbox("Dimension label mode", ["Symbol + Value", "Symbol only", "Value only"], index=0)
    label_mode = {"Symbol + Value": "symbol_value", "Symbol only": "symbol", "Value only": "value"}[label_mode_label]

    st.subheader("Geometry Parameters")
    params: dict[str, Any] = {}
    parameter_columns = st.columns(2)
    for index, parameter in enumerate(preset["parameters"]):
        with parameter_columns[index % len(parameter_columns)]:
            if parameter.get("type", "number") == "number":
                params[parameter["name"]] = _number_input(parameter, preset["key"])
            else:
                st.warning(f"Unsupported parameter type: {parameter.get('type')}")

    generator_name = preset["generator"]
    try:
        geometry = default_registry.geometry(generator_name)(**params, name=preset["display_name"])
        dimensions = default_registry.dimensions(preset["dimensions_generator"])(**params)
    except ValueError as exc:
        st.session_state["section_geometry"] = None
        st.session_state["section_dimensions"] = []
        _render_validation_panel(ValidationResult(is_valid=False, errors=[str(exc)], info=["Preview is paused until geometry inputs are valid."]))
        return

    validation = validate_section_geometry(geometry)
    if not validation.is_valid:
        st.session_state["section_geometry"] = None
        st.session_state["section_dimensions"] = []
        _render_validation_panel(validation)
        with st.expander("Generated SectionGeometry"):
            st.json(geometry.model_dump())
        return

    st.session_state["section_preset_key"] = preset["key"]
    st.session_state["section_preset_name"] = preset["display_name"]
    st.session_state["section_parameters"] = params
    st.session_state["section_geometry"] = geometry
    st.session_state["section_dimensions"] = dimensions

    left, right = st.columns([2, 1])
    with left:
        st.plotly_chart(
            create_section_preview(
                geometry,
                dimensions,
                label_mode,
                st.session_state.get("rebars", []),
                st.session_state.get("prestress_elements", []),
            ),
            use_container_width=True,
            key="section_builder_preview",
        )
    with right:
        summary = summarize_geometry(geometry)
        st.metric("Area", f"{summary.area_mm2:,.1f} mm^2")
        st.metric("Centroid x", f"{summary.centroid_x_mm:,.2f} mm")
        st.metric("Centroid y", f"{summary.centroid_y_mm:,.2f} mm")
        st.metric("Ix", summary.ix_display)
        st.metric("Iy", summary.iy_display)
        _render_validation_panel(validation)

    with st.expander("Generated SectionGeometry"):
        st.json(geometry.model_dump())
