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
.cpmm-section-card {
  border: 1px solid #d9dee7;
  border-left: 4px solid #7b8794;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.8rem 0.95rem;
  min-height: 104px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}
.cpmm-section-card.ready { border-left-color: #2e7d32; }
.cpmm-section-card.warning { border-left-color: #b7791f; }
.cpmm-section-card.danger { border-left-color: #b42318; }
.cpmm-section-card.info { border-left-color: #8ea3c8; }
.cpmm-section-card.neutral { border-left-color: #7b8794; }
.cpmm-section-card-title {
  color: #475467;
  font-size: 0.78rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.28rem;
}
.cpmm-section-card-value {
  color: #101828;
  font-size: 1.03rem;
  font-weight: 720;
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.cpmm-section-card-detail {
  color: #667085;
  font-size: 0.8rem;
  line-height: 1.34;
  margin-top: 0.32rem;
}
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
  padding: 0.72rem 0.9rem;
}
.cpmm-section-kv-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.36rem 0;
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


def _metric_card_html(metric: SectionMetric) -> str:
    status = _safe_status(metric.status)
    badge_html = f'<span class="cpmm-section-badge {status}">{escape(status.upper())}</span>' if metric.strong else ""
    detail_html = f'<div class="cpmm-section-card-detail">{escape(metric.detail)}</div>' if metric.detail else ""
    return (
        f'<div class="cpmm-section-card {status}">'
        f'<div class="cpmm-section-card-title">{escape(metric.title)}</div>'
        f'<div class="cpmm-section-card-value">{escape(metric.value)}</div>'
        f"{detail_html}"
        f"{badge_html}"
        "</div>"
    )


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


def _render_metric_cards(metrics: list[SectionMetric], columns: int = 4) -> None:
    for start in range(0, len(metrics), columns):
        cols = st.columns(min(columns, len(metrics) - start))
        for column, metric in zip(cols, metrics[start : start + columns]):
            with column:
                st.markdown(_metric_card_html(metric), unsafe_allow_html=True)


def _format_float(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}"


def _format_parameter_value(value: Any) -> str:
    if isinstance(value, float):
        return _format_float(value, 2).rstrip("0").rstrip(".")
    return str(value)


def _inertia_display(value: str) -> str:
    return "Not calculated" if value == "TODO" else value


def _render_validation_panel(result: ValidationResult) -> None:
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
        selected_label = st.selectbox("Section preset", labels, index=label_index)
        preset = category_presets[labels.index(selected_label)]

        label_mode_label = st.selectbox("Dimension label mode", ["Symbol + Value", "Symbol only", "Value only"], index=0)
        label_mode = {"Symbol + Value": "symbol_value", "Symbol only": "symbol", "Value only": "value"}[label_mode_label]

        st.markdown("#### Geometry Parameters")
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
        ("Geometry defined", "Yes" if geometry_ready else "No"),
        ("Section type valid", "Yes" if validation.is_valid else "No"),
        ("Preview available", "Yes" if geometry_ready else "No"),
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

        status = _validation_status(validation)
        st.markdown(
            _metric_card_html(
                SectionMetric(
                    "Geometry Validation",
                    "Valid" if validation.is_valid else "Needs Review",
                    "Preview and analysis use the generated section only after validation passes.",
                    status,
                    strong=True,
                )
            ),
            unsafe_allow_html=True,
        )
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
        _render_metric_cards(
            [
                SectionMetric("Active Preset", preset["display_name"], preset.get("category", ""), "info"),
                SectionMetric("Geometry Status", "Needs Review", "Properties are available after valid geometry is generated.", "danger", True),
            ],
            columns=2,
        )
        if rows := _parameter_rows(preset, params):
            st.markdown(_kv_panel_html(rows), unsafe_allow_html=True)
        return

    summary = summarize_geometry(geometry)
    metrics = [
        SectionMetric("Gross Area", f"{summary.area_mm2:,.1f} mm^2", "Concrete polygon area", "info"),
        SectionMetric(
            "Centroid",
            f"x {_format_float(summary.centroid_x_mm, 2)} mm, y {_format_float(summary.centroid_y_mm, 2)} mm",
            "Global section coordinates",
            "info",
        ),
        SectionMetric("Ix", _inertia_display(summary.ix_display), "Existing summary value", "neutral"),
        SectionMetric("Iy", _inertia_display(summary.iy_display), "Existing summary value", "neutral"),
        SectionMetric("Holes / Voids", f"{len(geometry.holes):,}", "Generated geometry openings", "ready" if not geometry.holes else "warning"),
        SectionMetric("Active Preset", preset["display_name"], preset.get("category", ""), "info"),
    ]
    _render_metric_cards(metrics, columns=3)

    detail_cols = st.columns([1, 1])
    with detail_cols[0]:
        st.markdown("##### Geometry Inputs")
        st.markdown(_kv_panel_html(_parameter_rows(preset, params)), unsafe_allow_html=True)
    with detail_cols[1]:
        st.markdown("##### Readiness")
        st.markdown(
            _kv_panel_html(
                [
                    ("Generated geometry", "Available"),
                    ("Validation errors", f"{len(validation.errors):,}"),
                    ("Validation warnings", f"{len(validation.warnings):,}"),
                    ("Outer vertices", f"{len(geometry.outer_polygon):,}"),
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
