"""Rebar tab UI and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from shapely.geometry import Point, Polygon

from concrete_pmm_pro.core.models import Rebar, SectionGeometry
from concrete_pmm_pro.geometry.summary import to_shapely_polygon
from concrete_pmm_pro.visualization import create_section_preview

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REBAR_DB_PATH = REPO_ROOT / "data" / "rebar_database.csv"
REBAR_DEFAULT_MATERIAL_BY_SIZE = {
    "DB10": "SD40",
    "DB12": "SD40",
    "DB16": "SD40",
    "DB20": "SD40",
    "DB25": "SD40",
    "DB28": "SD40",
    "DB32": "SD50",
}


@dataclass(frozen=True)
class RebarParseResult:
    rebars: list[Rebar]
    errors: list[str]
    warnings: list[str]
    info: list[str]


@dataclass(frozen=True)
class RebarMetric:
    title: str
    value: str
    detail: str = ""
    status: str = "neutral"
    strong: bool = False


_REBAR_PAGE_CSS = """
<style>
.cpmm-rebar-strip {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 0.55rem;
  margin-bottom: 0.75rem;
}
.cpmm-rebar-chip {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.58rem 0.7rem;
  min-height: 76px;
}
.cpmm-rebar-chip-label {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.18rem;
}
.cpmm-rebar-chip-value {
  color: #101828;
  font-size: 0.96rem;
  font-weight: 720;
  line-height: 1.22;
  overflow-wrap: anywhere;
}
.cpmm-rebar-chip-detail {
  color: #667085;
  font-size: 0.74rem;
  line-height: 1.25;
  margin-top: 0.16rem;
}
.cpmm-rebar-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.12rem 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0;
}
.cpmm-rebar-badge.ready { color: #1f5f2a; background: #e7f5e8; }
.cpmm-rebar-badge.warning { color: #7a4b00; background: #fff4d6; }
.cpmm-rebar-badge.danger { color: #9f1f17; background: #fde8e7; }
.cpmm-rebar-badge.info { color: #1849a9; background: #e8f1ff; }
.cpmm-rebar-badge.neutral { color: #475467; background: #eef1f5; }
.cpmm-rebar-kv-panel {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.64rem 0.84rem;
}
.cpmm-rebar-kv-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.8rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.32rem 0;
}
.cpmm-rebar-kv-row:last-child { border-bottom: 0; }
.cpmm-rebar-kv-label {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 600;
}
.cpmm-rebar-kv-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 650;
  text-align: right;
  overflow-wrap: anywhere;
}
.cpmm-rebar-note {
  color: #667085;
  font-size: 0.82rem;
  line-height: 1.35;
}
.cpmm-rebar-message-list {
  border: 1px solid #edf0f5;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 0.62rem 0.78rem;
  margin-top: 0.55rem;
}
.cpmm-rebar-message-item {
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.35;
  padding: 0.18rem 0;
}
@media (max-width: 1250px) {
  .cpmm-rebar-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .cpmm-rebar-strip { grid-template-columns: minmax(0, 1fr); }
}
</style>
"""


def load_rebar_database(path: Path | str = DEFAULT_REBAR_DB_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def _default_rebar_table(rebar_db: pd.DataFrame) -> pd.DataFrame:
    default_size = "DB20" if "DB20" in set(rebar_db["name"]) else str(rebar_db.iloc[0]["name"])
    default_diameter = float(rebar_db.loc[rebar_db["name"] == default_size, "diameter_mm"].iloc[0])
    default_material = default_material_for_bar_size(default_size)
    return pd.DataFrame(
        [
            {"Active": True, "Label": "B1", "x_mm": -150.0, "y_mm": -250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": default_material, "Count": 1, "Note": ""},
            {"Active": True, "Label": "B2", "x_mm": 150.0, "y_mm": -250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": default_material, "Count": 1, "Note": ""},
            {"Active": True, "Label": "B3", "x_mm": 150.0, "y_mm": 250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": default_material, "Count": 1, "Note": ""},
            {"Active": True, "Label": "B4", "x_mm": -150.0, "y_mm": 250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": default_material, "Count": 1, "Note": ""},
        ]
    )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _row_is_blank(row: pd.Series) -> bool:
    return all(_is_blank(row.get(column)) for column in ["Label", "x_mm", "y_mm", "Bar Size", "Diameter_mm", "Material", "Count", "Note"])


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if _is_blank(value):
        return False
    if str(value).strip().lower() in {"true", "1", "yes"}:
        return True
    if str(value).strip().lower() in {"false", "0", "no"}:
        return False
    return bool(value)


def _to_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_count(value: Any) -> int | None:
    parsed = _to_float(value)
    if parsed is None:
        return 1
    if parsed < 1 or int(parsed) != parsed:
        return None
    return int(parsed)


def _diameter_from_database(bar_size: str, rebar_db: pd.DataFrame) -> float | None:
    if _is_blank(bar_size):
        return None
    matches = rebar_db.loc[rebar_db["name"] == str(bar_size).strip(), "diameter_mm"]
    if matches.empty:
        return None
    return float(matches.iloc[0])


def default_material_for_bar_size(bar_size: str) -> str:
    return REBAR_DEFAULT_MATERIAL_BY_SIZE.get(str(bar_size).strip(), "SD40")


def bar_size_defaults(bar_size: str, rebar_db: pd.DataFrame) -> tuple[float, str] | None:
    diameter = _diameter_from_database(bar_size, rebar_db)
    if diameter is None:
        return None
    return diameter, default_material_for_bar_size(bar_size)


def _normalized_bar_size(value: Any) -> str:
    return "" if _is_blank(value) else str(value).strip()


def _previous_bar_size(previous_df: pd.DataFrame | None, index: Any) -> str:
    if previous_df is None or index not in previous_df.index:
        return ""
    return _normalized_bar_size(previous_df.at[index, "Bar Size"] if "Bar Size" in previous_df.columns else "")


def normalize_rebar_table_for_bar_size_sync(edited_df: pd.DataFrame, previous_df: pd.DataFrame | None, rebar_db: pd.DataFrame) -> pd.DataFrame:
    """Apply database defaults only when Bar Size changes or dependent cells are blank.

    This keeps Streamlit data_editor manual Diameter_mm/Material overrides stable
    across reruns while still making size dropdown changes immediately consistent
    with the engineering database/default material rules.
    """
    normalized = edited_df.copy()
    for column in ["Active", "Label", "x_mm", "y_mm", "Bar Size", "Diameter_mm", "Material", "Count", "Note"]:
        if column not in normalized.columns:
            normalized[column] = None

    for index, row in normalized.iterrows():
        bar_size = _normalized_bar_size(row.get("Bar Size"))
        if not bar_size or bar_size == "Custom":
            continue
        defaults = bar_size_defaults(bar_size, rebar_db)
        if defaults is None:
            continue
        default_diameter, default_material = defaults
        previous_bar_size = _previous_bar_size(previous_df, index)
        bar_size_changed = bar_size != previous_bar_size

        if bar_size_changed or _is_blank(row.get("Diameter_mm")):
            normalized.at[index, "Diameter_mm"] = default_diameter
        if bar_size_changed or _is_blank(row.get("Material")):
            normalized.at[index, "Material"] = default_material

    return normalized


def _resolve_diameter(row: pd.Series, rebar_db: pd.DataFrame, row_number: int) -> tuple[float | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    bar_size = "" if _is_blank(row.get("Bar Size")) else str(row.get("Bar Size")).strip()
    manual_diameter = _to_float(row.get("Diameter_mm"))

    if bar_size and bar_size != "Custom":
        database_diameter = _diameter_from_database(bar_size, rebar_db)
        if database_diameter is not None:
            if manual_diameter is None:
                return database_diameter, errors, warnings
            if manual_diameter <= 0:
                errors.append(f"Row {row_number}: Diameter_mm must be positive.")
                return None, errors, warnings
            return manual_diameter, errors, warnings
        if manual_diameter is not None:
            warnings.append(f"Row {row_number}: Bar Size '{bar_size}' is not in the database; using manual Diameter_mm as custom.")
            if manual_diameter <= 0:
                errors.append(f"Row {row_number}: Diameter_mm must be positive.")
                return None, errors, warnings
            return manual_diameter, errors, warnings
        errors.append(f"Row {row_number}: Bar Size '{bar_size}' is not in the database and Diameter_mm is blank.")
        return None, errors, warnings

    if manual_diameter is None:
        if bar_size == "Custom":
            errors.append(f"Row {row_number}: Custom Bar Size requires Diameter_mm.")
        else:
            errors.append(f"Row {row_number}: Bar Size or Diameter_mm is required.")
        return None, errors, warnings
    if manual_diameter <= 0:
        errors.append(f"Row {row_number}: Diameter_mm must be positive.")
        return None, errors, warnings
    if bar_size == "Custom":
        warnings.append(f"Row {row_number}: Custom Bar Size is using manual Diameter_mm.")
    return manual_diameter, errors, warnings


def rebars_from_dataframe(df: pd.DataFrame, rebar_db: pd.DataFrame) -> RebarParseResult:
    errors: list[str] = []
    warnings: list[str] = []
    rebars: list[Rebar] = []

    for index, row in df.iterrows():
        row_number = int(index) + 1
        if _row_is_blank(row):
            continue
        if not _to_bool(row.get("Active")):
            continue

        x_mm = _to_float(row.get("x_mm"))
        y_mm = _to_float(row.get("y_mm"))
        if x_mm is None:
            errors.append(f"Row {row_number}: x_mm must be numeric.")
        if y_mm is None:
            errors.append(f"Row {row_number}: y_mm must be numeric.")

        diameter_mm, diameter_errors, diameter_warnings = _resolve_diameter(row, rebar_db, row_number)
        errors.extend(diameter_errors)
        warnings.extend(diameter_warnings)

        count = _to_count(row.get("Count"))
        if count is None:
            errors.append(f"Row {row_number}: Count must be an integer greater than or equal to 1.")
            count = 1

        if any(error.startswith(f"Row {row_number}:") for error in errors):
            continue

        base_label = str(row.get("Label")).strip() if not _is_blank(row.get("Label")) else f"R{len(rebars) + 1}"
        material_name = str(row.get("Material")).strip() if not _is_blank(row.get("Material")) else "SD40"
        for item in range(count):
            label = base_label if count == 1 else f"{base_label}-{item + 1}"
            rebars.append(Rebar(x_mm=float(x_mm), y_mm=float(y_mm), diameter_mm=float(diameter_mm), material_name=material_name, label=label))

    total_as = sum(rebar.area_mm2 for rebar in rebars)
    info = [f"{len(rebars)} active rebar object(s).", f"Total As = {total_as:,.1f} mm^2."]
    if not rebars:
        warnings.append("No active rebars are defined.")
    return RebarParseResult(rebars=rebars, errors=errors, warnings=warnings, info=info)


def validate_rebars_against_geometry(rebars: list[Rebar], geometry: SectionGeometry | None) -> list[str]:
    if geometry is None:
        return []
    section = to_shapely_polygon(geometry)
    hole_polygons = [Polygon([point.as_tuple() for point in hole]) for hole in geometry.holes]
    errors: list[str] = []
    for index, rebar in enumerate(rebars, start=1):
        label = rebar.label or f"Rebar {index}"
        point = Point(rebar.x_mm, rebar.y_mm)
        if any(hole.covers(point) for hole in hole_polygons):
            errors.append(f"{label}: rebar is inside a void/hole.")
        elif not section.covers(point):
            errors.append(f"{label}: rebar is outside concrete.")
    return errors


def rebars_valid_for_analysis(parse_result: RebarParseResult, geometry_errors: list[str]) -> bool:
    return not parse_result.errors and not geometry_errors


def rebar_summary_dataframe(rebars: list[Rebar]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Label": rebar.label,
                "x_mm": rebar.x_mm,
                "y_mm": rebar.y_mm,
                "diameter_mm": rebar.diameter_mm,
                "area_mm2": rebar.area_mm2,
                "material_name": rebar.material_name,
            }
            for rebar in rebars
        ]
    )


def _safe_status(status: str) -> str:
    return status if status in {"ready", "warning", "danger", "info", "neutral"} else "neutral"


def _strip_html(metrics: list[RebarMetric]) -> str:
    chips: list[str] = []
    for metric in metrics:
        status = _safe_status(metric.status)
        value_html = (
            f'<span class="cpmm-rebar-badge {status}">{escape(metric.value)}</span>'
            if metric.strong
            else escape(metric.value)
        )
        detail_html = f'<div class="cpmm-rebar-chip-detail">{escape(metric.detail)}</div>' if metric.detail else ""
        chips.append(
            '<div class="cpmm-rebar-chip">'
            f'<div class="cpmm-rebar-chip-label">{escape(metric.title)}</div>'
            f'<div class="cpmm-rebar-chip-value">{value_html}</div>'
            f"{detail_html}"
            "</div>"
        )
    return '<div class="cpmm-rebar-strip">' + "".join(chips) + "</div>"


def _kv_panel_html(rows: list[tuple[str, str]]) -> str:
    row_html = []
    for label, value in rows:
        row_html.append(
            '<div class="cpmm-rebar-kv-row">'
            f'<div class="cpmm-rebar-kv-label">{escape(label)}</div>'
            f'<div class="cpmm-rebar-kv-value">{escape(value)}</div>'
            "</div>"
        )
    return '<div class="cpmm-rebar-kv-panel">' + "".join(row_html) + "</div>"


def _message_list_html(messages: list[str]) -> str:
    items = "".join(f'<div class="cpmm-rebar-message-item">{escape(message)}</div>' for message in messages)
    return f'<div class="cpmm-rebar-message-list">{items}</div>'


def _total_as_mm2(rebars: list[Rebar]) -> float:
    return sum(rebar.area_mm2 for rebar in rebars)


def _dominant_material_label(rebars: list[Rebar], fallback: str | None = None) -> str:
    if not rebars:
        return fallback or "N/A"
    materials = sorted({rebar.material_name for rebar in rebars if rebar.material_name})
    if not materials:
        return fallback or "N/A"
    if len(materials) == 1:
        return materials[0]
    return f"{len(materials)} materials"


def _reinforcement_ratio_label(total_as_mm2: float, geometry: SectionGeometry | None) -> str:
    if geometry is None:
        return "N/A"
    area_mm2 = float(to_shapely_polygon(geometry).area)
    if area_mm2 <= 0:
        return "N/A"
    return f"{100.0 * total_as_mm2 / area_mm2:.3f}%"


def _valid_status(valid_for_analysis: bool) -> str:
    return "ready" if valid_for_analysis else "danger"


def _render_summary_strip(
    result: RebarParseResult,
    geometry: SectionGeometry | None,
    input_mode: str,
    valid_for_analysis: bool,
    active_material_name: str | None,
) -> None:
    total_as = _total_as_mm2(result.rebars)
    st.markdown(
        _strip_html(
            [
                RebarMetric("Active Bars", f"{len(result.rebars):,}", "Expanded by Count"),
                RebarMetric("Total As", f"{total_as:,.1f} mm^2"),
                RebarMetric("Valid for Analysis", "Yes" if valid_for_analysis else "No", "", _valid_status(valid_for_analysis), True),
                RebarMetric("Material", _dominant_material_label(result.rebars, active_material_name)),
                RebarMetric("Rebar Ratio", _reinforcement_ratio_label(total_as, geometry), "As / concrete area"),
                RebarMetric("Input Mode", input_mode),
            ]
        ),
        unsafe_allow_html=True,
    )


def _render_validation(result: RebarParseResult, geometry_errors: list[str], geometry_available: bool, valid_for_analysis: bool) -> None:
    st.markdown("#### Rebar Status")
    all_errors = [*result.errors, *geometry_errors]
    warnings = list(result.warnings)
    if not geometry_available:
        warnings.append("Section geometry is not available yet; geometry validation will run after a valid section is generated.")
    st.markdown(
        _kv_panel_html(
            [
                ("Validation", "OK" if not all_errors else "Error"),
                ("Warnings", f"{len(warnings):,}"),
                ("Active bars", f"{len(result.rebars):,}"),
                ("Total As", f"{_total_as_mm2(result.rebars):,.1f} mm^2"),
                ("Valid for analysis", "Yes" if valid_for_analysis else "No"),
                ("Material", _dominant_material_label(result.rebars)),
            ]
        ),
        unsafe_allow_html=True,
    )

    if all_errors:
        for error in all_errors:
            st.error(f"ERROR: {error}")

    if warnings:
        for warning in warnings:
            st.warning(f"WARNING: {warning}")

    if result.info and (all_errors or warnings):
        st.markdown(_message_list_html([f"INFO: {info}" for info in result.info]), unsafe_allow_html=True)


def _rebar_column_config(bar_size_options: list[str]) -> dict[str, Any]:
    return {
        "Active": st.column_config.CheckboxColumn("Active", width="small"),
        "Label": st.column_config.TextColumn("Label", width="small"),
        "x_mm": st.column_config.NumberColumn("x_mm", help="x coordinate in section axes, mm", width="small"),
        "y_mm": st.column_config.NumberColumn("y_mm", help="y coordinate in section axes, mm", width="small"),
        "Bar Size": st.column_config.SelectboxColumn("Bar Size", options=bar_size_options, width="medium"),
        "Diameter_mm": st.column_config.NumberColumn("Diameter_mm", help="Used for Custom or blank Bar Size.", width="small"),
        "Material": st.column_config.TextColumn("Material", width="small"),
        "Count": st.column_config.NumberColumn("Count", min_value=1, step=1, width="small"),
        "Note": st.column_config.TextColumn("Note", width="medium"),
    }


def _render_rebar_editor(table: pd.DataFrame, bar_size_options: list[str]) -> pd.DataFrame:
    return st.data_editor(
        table,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=_rebar_column_config(bar_size_options),
        key="rebar_data_editor",
    )


def render_rebar_page() -> None:
    st.markdown(_REBAR_PAGE_CSS, unsafe_allow_html=True)
    st.subheader("Rebar")
    rebar_db = load_rebar_database()
    bar_size_options = ["", "Custom"] + [str(name) for name in rebar_db["name"].tolist()]
    active_material_name = st.session_state.get("active_rebar_material_name")

    st.caption("Define ordinary reinforcement coordinates, bar sizes, and materials used by the active section analysis.")

    if "rebar_table" not in st.session_state:
        st.session_state["rebar_table"] = _default_rebar_table(rebar_db)

    input_mode = "Manual table"
    edited_df = st.session_state["rebar_table"]

    input_col, status_col = st.columns([1.45, 0.85], gap="large")
    summary_slot = None
    with input_col:
        with st.container(border=True):
            st.markdown("#### Rebar Input")
            # Keep the summary visually above the editor.  The placeholder is filled
            # after data_editor returns so the metrics still use the normalized table
            # from the current rerun instead of stale pre-edit values.
            summary_slot = st.empty()
            input_mode = st.selectbox("Rebar input mode", ["Manual table", "Rectangular perimeter layout", "Circular layout"])
            st.markdown(
                '<div class="cpmm-rebar-note">Selecting a database bar size fills Diameter and default Material. Diameter and Material remain editable for project-specific overrides.</div>',
                unsafe_allow_html=True,
            )
            if input_mode != "Manual table":
                st.info("Automatic rebar layouts are planned for a later milestone. The editable Manual table remains active for engineering traceability.")

            # The editable table is always shown.  Until automatic generators exist,
            # hiding this table would hide the actual reinforcement model sent to
            # PMM/SLS analysis and make bar-size synchronization hard to verify.
            edited_df = _render_rebar_editor(st.session_state["rebar_table"], bar_size_options)

    normalized_df = normalize_rebar_table_for_bar_size_sync(edited_df, st.session_state.get("rebar_table"), rebar_db)
    st.session_state["rebar_table"] = normalized_df

    result = rebars_from_dataframe(normalized_df, rebar_db)
    geometry = st.session_state.get("section_geometry")
    geometry_errors = validate_rebars_against_geometry(result.rebars, geometry)
    valid_for_analysis = rebars_valid_for_analysis(result, geometry_errors)
    st.session_state["rebars"] = result.rebars
    st.session_state["rebars_valid_for_analysis"] = valid_for_analysis

    if summary_slot is not None:
        with summary_slot:
            _render_summary_strip(result, geometry, input_mode, valid_for_analysis, active_material_name)

    with status_col:
        with st.container(border=True):
            _render_validation(result, geometry_errors, geometry is not None, valid_for_analysis)
            st.markdown(
                '<div class="cpmm-rebar-note">Coordinates are in mm. x is positive to the right; y is positive upward in the section preview.</div>',
                unsafe_allow_html=True,
            )

    summary_col, preview_col = st.columns([0.58, 0.42], gap="large")
    with summary_col:
        st.subheader("Rebar Summary")
        st.dataframe(rebar_summary_dataframe(st.session_state["rebars"]), use_container_width=True, hide_index=True)

    if geometry is not None:
        with preview_col:
            st.subheader("Section Preview with Rebar")
            preview_fig = create_section_preview(
                geometry,
                st.session_state.get("section_dimensions", []),
                "symbol_value",
                st.session_state["rebars"],
                st.session_state.get("prestress_elements", []),
            )
            preview_fig.update_layout(height=430, margin=dict(l=10, r=10, t=36, b=10))
            st.plotly_chart(
                preview_fig,
                use_container_width=True,
                key="rebar_section_preview",
            )
