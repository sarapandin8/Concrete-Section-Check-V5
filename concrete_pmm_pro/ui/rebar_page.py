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
from concrete_pmm_pro.core.reinforcement_system import ordinary_rebar_enabled, prestressing_steel_enabled
from concrete_pmm_pro.geometry.rebar_layout import PerimeterRebarLayoutResult, generate_perimeter_rebar_layout
from concrete_pmm_pro.geometry.summary import to_shapely_polygon
from concrete_pmm_pro.serviceability.girder_sls_load_components import BEAM_GIRDER_SYSTEM_SETTINGS_KEY, system_settings_from_mapping
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

# Keep the editor column contract centralized.  The same ordered column list is
# used when creating the default table, normalizing data_editor output, comparing
# edited rows, and feeding the Rebar parser.  This avoids subtle Streamlit rerun
# bugs caused by missing columns or inconsistent column order.


# SHEAR.REINF1 — Beam/Girder transverse reinforcement layout used by future
# ULS shear design.  It is deliberately zone-based because commercial girder
# design is detailed by stirrup regions, not by per-station manual entries.
SHEAR_REINFORCEMENT_TABLE_KEY = "beam_girder_shear_reinforcement_table"
SHEAR_REINFORCEMENT_VALID_KEY = "beam_girder_shear_reinforcement_valid"
SHEAR_DEPTH_SETTINGS_KEY = "beam_girder_shear_depth_settings"
COLUMN_PIER_TRANSVERSE_TABLE_KEY = "column_pier_transverse_reinforcement_table"
COLUMN_PIER_TRANSVERSE_VALID_KEY = "column_pier_transverse_reinforcement_valid"
COLUMN_PIER_TRANSVERSE_SETTINGS_KEY = "column_pier_transverse_reinforcement_settings"
SHEAR_DEPTH_MODE_AUTO = "Auto from reinforcement centroid"
SHEAR_DEPTH_MODE_MANUAL = "Manual effective d / dv"
SHEAR_REINFORCEMENT_COLUMNS = [
    "Active",
    "Zone",
    "x_start_m",
    "x_end_m",
    "Bar Size",
    "Diameter_mm",
    "Legs",
    "Spacing_mm",
    "fy_MPa",
    "Note",
]
SHEAR_STIRRUP_BAR_OPTIONS = ["DB10", "DB12", "DB16", "DB20", "DB25"]
DEFAULT_SHEAR_STIRRUP_BAR = "DB12"
DEFAULT_SHEAR_STIRRUP_LEGS = 2
DEFAULT_SHEAR_STIRRUP_SPACING_MM = 150.0
DEFAULT_SHEAR_STIRRUP_FY_MPA = 400.0
COLUMN_PIER_WORKFLOW_MEMBER_TYPE = "column_pier_pmm"
COLUMN_PIER_CLOSED_TIE_OPTIONS = ["Closed ties / hoops", "Spiral reinforcement", "Open ties - shear only review"]
COLUMN_PIER_TORSION_CORE_OPTIONS = ["Auto from section and tie offset", "Manual core dimensions", "Not defined yet"]

REBAR_TABLE_COLUMNS = [
    "Active",
    "Label",
    "x_mm",
    "y_mm",
    "Bar Size",
    "Diameter_mm",
    "Material",
    "Count",
    "Note",
]


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


def _ensure_rebar_table_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the full editor column contract and stable order."""
    table = df.copy()
    for column in REBAR_TABLE_COLUMNS:
        if column not in table.columns:
            table[column] = None
    return table[REBAR_TABLE_COLUMNS]


def _editor_cell_equal(left: Any, right: Any, numeric: bool = False, boolean: bool = False) -> bool:
    """Compare data_editor cells without false mismatches from type coercion.

    Streamlit may round-trip ``32`` as ``32.0`` or preserve blank cells as
    ``None``/``NaN`` depending on the edit path.  This comparator keeps the
    immediate-sync guard from triggering an unnecessary rerun loop while still
    detecting real Bar Size → Diameter/Material updates.
    """
    if _is_blank(left) and _is_blank(right):
        return True
    if boolean:
        return _to_bool(left) == _to_bool(right)
    if numeric:
        left_number = _to_float(left)
        right_number = _to_float(right)
        if left_number is None or right_number is None:
            return left_number is right_number
        return abs(left_number - right_number) <= 1e-9
    return str(left).strip() == str(right).strip()


def rebar_editor_tables_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    """Return True when two editor tables are equivalent for the visible UI.

    This is intentionally stricter than object identity and looser than
    ``DataFrame.equals``.  It prevents rerun loops caused only by pandas/Streamlit
    dtype differences, while still detecting when the auto-sync has changed
    Diameter_mm or Material after a Bar Size edit.
    """
    left_table = _ensure_rebar_table_columns(left).reset_index(drop=True)
    right_table = _ensure_rebar_table_columns(right).reset_index(drop=True)
    if left_table.shape != right_table.shape:
        return False

    numeric_columns = {"x_mm", "y_mm", "Diameter_mm", "Count"}
    for row_index in range(len(left_table)):
        for column in REBAR_TABLE_COLUMNS:
            if not _editor_cell_equal(
                left_table.at[row_index, column],
                right_table.at[row_index, column],
                numeric=column in numeric_columns,
                boolean=column == "Active",
            ):
                return False
    return True


def normalize_rebar_table_for_bar_size_sync(edited_df: pd.DataFrame, previous_df: pd.DataFrame | None, rebar_db: pd.DataFrame) -> pd.DataFrame:
    """Apply database defaults only when Bar Size changes or dependent cells are blank.

    This keeps Streamlit data_editor manual Diameter_mm/Material overrides stable
    across reruns while still making size dropdown changes immediately consistent
    with the engineering database/default material rules.
    """
    normalized = _ensure_rebar_table_columns(edited_df)

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


def _render_validation(
    result: RebarParseResult,
    geometry_errors: list[str],
    geometry_available: bool,
    valid_for_analysis: bool,
    active_prestress_count: int = 0,
) -> None:
    st.markdown("#### Rebar Status")
    all_errors = [*result.errors, *geometry_errors]
    warnings = list(result.warnings)
    contextual_notes: list[str] = []
    if not result.rebars and active_prestress_count > 0:
        contextual_notes.append(
            "No active ordinary rebar is defined. Analysis will rely on active bonded prestress elements; check minimum ordinary reinforcement and detailing requirements separately."
        )
    elif not result.rebars:
        warnings.append("No active longitudinal reinforcement is defined. Activate ordinary rebar or prestress before final analysis.")
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

    for note in contextual_notes:
        st.info(f"INFO: {note}")

    if result.info and (all_errors or warnings or contextual_notes):
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


def _rebar_bar_size_options(rebar_db: pd.DataFrame) -> list[str]:
    return [""] + [str(name) for name in rebar_db["name"].tolist()]


def _render_auto_perimeter_controls(rebar_db: pd.DataFrame, geometry: SectionGeometry | None) -> PerimeterRebarLayoutResult:
    """Render preview/apply controls for generated perimeter reinforcement.

    The generator is deliberately opt-in: it never overwrites the engineering
    rebar table until the user presses Apply.  This keeps manual layouts safe
    while making perimeter reinforcement fast for column/pier/wall/pylon PMM
    sections.
    """
    st.markdown("##### Auto perimeter layout")
    st.caption(
        "Preview ordinary bars offset from the current section perimeter, then apply the generated coordinates to the Rebar table. "
        "This does not silently overwrite manual bars."
    )
    control_cols = st.columns([1.05, 1.0, 1.0, 1.0, 0.9], gap="small")
    with control_cols[0]:
        bar_size = st.selectbox(
            "Bar size",
            _rebar_bar_size_options(rebar_db),
            index=max(0, _rebar_bar_size_options(rebar_db).index("DB20") if "DB20" in set(rebar_db["name"]) else 0),
            key="rebar_perimeter_bar_size",
        )
    defaults = bar_size_defaults(bar_size, rebar_db) if bar_size else None
    diameter_mm = defaults[0] if defaults else 20.0
    default_material = defaults[1] if defaults else "SD40"
    with control_cols[1]:
        material = st.text_input("Material", value=default_material, key="rebar_perimeter_material")
    with control_cols[2]:
        edge_offset_mm = st.number_input(
            "Bar center offset (mm)",
            min_value=1.0,
            value=75.0,
            step=5.0,
            key="rebar_perimeter_edge_offset_mm",
        )
    with control_cols[3]:
        target_spacing_mm = st.number_input(
            "Target spacing (mm)",
            min_value=1.0,
            value=150.0,
            step=10.0,
            key="rebar_perimeter_target_spacing_mm",
        )
    with control_cols[4]:
        min_bars = st.number_input(
            "Minimum bars",
            min_value=1,
            value=4,
            step=1,
            key="rebar_perimeter_min_bars",
        )

    prefix_cols = st.columns([0.35, 1.65], gap="small")
    with prefix_cols[0]:
        label_prefix = st.text_input("Label prefix", value="B", key="rebar_perimeter_label_prefix")
    with prefix_cols[1]:
        st.caption(
            "Default controls: 75 mm to bar center and 150 mm target spacing. Use the preview as an engineering starting layout, then adjust manually if needed."
        )

    result = generate_perimeter_rebar_layout(
        geometry,
        bar_size=bar_size or "DB20",
        diameter_mm=float(diameter_mm),
        material=material or default_material,
        edge_offset_mm=float(edge_offset_mm),
        target_spacing_mm=float(target_spacing_mm),
        min_bars=int(min_bars),
        label_prefix=label_prefix,
    )

    if result.errors:
        for error in result.errors:
            st.error(f"ERROR: {error}")
    if result.warnings:
        for warning in result.warnings:
            st.warning(f"WARNING: {warning}")
    if result.info:
        for info in result.info:
            st.info(f"INFO: {info}")

    if result.ok and not result.table.empty:
        metric_cols = st.columns(3)
        metric_cols[0].metric("Generated bars", f"{len(result.table):,}")
        metric_cols[1].metric("Actual spacing", f"{(result.actual_spacing_mm or 0.0):.1f} mm")
        metric_cols[2].metric("Offset", f"{edge_offset_mm:.1f} mm")
        st.dataframe(result.table, use_container_width=True, hide_index=True)
        if st.button("Apply generated perimeter layout to Rebar table", type="primary", key="rebar_apply_perimeter_layout"):
            st.session_state["rebar_table"] = _ensure_rebar_table_columns(result.table)
            st.session_state["rebar_editor_revision"] = int(st.session_state.get("rebar_editor_revision", 0)) + 1
            st.rerun()
    else:
        st.caption("No generated perimeter layout is available yet.")

    return result


def _render_rebar_editor(table: pd.DataFrame, bar_size_options: list[str], editor_key: str) -> pd.DataFrame:
    return st.data_editor(
        _ensure_rebar_table_columns(table),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=_rebar_column_config(bar_size_options),
        key=editor_key,
    )




def _beam_girder_span_length_for_shear_layout() -> float:
    settings = system_settings_from_mapping(st.session_state.get(BEAM_GIRDER_SYSTEM_SETTINGS_KEY))
    try:
        span = float(settings.span_length_m)
    except (TypeError, ValueError):
        span = 20.0
    return span if span > 0.0 else 20.0


def _default_shear_reinforcement_table(span_length_m: float | None = None) -> pd.DataFrame:
    span = float(span_length_m or 20.0)
    if span <= 0.0:
        span = 20.0
    # Keep the default compact and safe.  The rows are inactive until the
    # engineer confirms the provided layout.  DB12 is the default bar as
    # requested, with symmetric support/transition/midspan zones.
    left_support = min(0.15 * span, 3.0)
    left_transition = min(0.30 * span, max(left_support, 6.0))
    right_transition = span - left_transition
    right_support = span - left_support
    if right_transition < left_transition:
        left_transition = 0.40 * span
        right_transition = 0.60 * span
    rows = [
        ("Left support", 0.0, left_support, 100.0, "Template zone — verify support shear demand before activating."),
        ("Left transition", left_support, left_transition, 150.0, "Template zone — adjust spacing after shear design."),
        ("Midspan", left_transition, right_transition, 250.0, "Template zone — usually governed by minimum transverse reinforcement."),
        ("Right transition", right_transition, right_support, 150.0, "Template zone — adjust spacing after shear design."),
        ("Right support", right_support, span, 100.0, "Template zone — verify support shear demand before activating."),
    ]
    return pd.DataFrame(
        [
            {
                "Active": False,
                "Zone": zone,
                "x_start_m": round(float(x0), 3),
                "x_end_m": round(float(x1), 3),
                "Bar Size": DEFAULT_SHEAR_STIRRUP_BAR,
                "Diameter_mm": 12.0,
                "Legs": DEFAULT_SHEAR_STIRRUP_LEGS,
                "Spacing_mm": float(spacing),
                "fy_MPa": DEFAULT_SHEAR_STIRRUP_FY_MPA,
                "Note": note,
            }
            for zone, x0, x1, spacing, note in rows
        ],
        columns=SHEAR_REINFORCEMENT_COLUMNS,
    )


def _default_column_pier_transverse_reinforcement_table() -> pd.DataFrame:
    rows = [
        ("End confinement A", 0.0, 1.0, 100.0, "Template region - closed ties/hoops near member end; verify confinement and shear/torsion demand before activating."),
        ("Typical shaft/core", 1.0, 5.0, 150.0, "Template region - adjust spacing after shear/torsion design; active rows are provided reinforcement only."),
        ("End confinement B", 5.0, 6.0, 100.0, "Template region - closed ties/hoops near member end; verify confinement and shear/torsion demand before activating."),
    ]
    return pd.DataFrame(
        [
            {
                "Active": False,
                "Zone": region,
                "x_start_m": float(start),
                "x_end_m": float(end),
                "Bar Size": DEFAULT_SHEAR_STIRRUP_BAR,
                "Diameter_mm": 12.0,
                "Legs": DEFAULT_SHEAR_STIRRUP_LEGS,
                "Spacing_mm": float(spacing),
                "fy_MPa": DEFAULT_SHEAR_STIRRUP_FY_MPA,
                "Note": note,
            }
            for region, start, end, spacing, note in rows
        ],
        columns=SHEAR_REINFORCEMENT_COLUMNS,
    )


def _ensure_shear_reinforcement_columns(df: pd.DataFrame) -> pd.DataFrame:
    table = df.copy()
    for column in SHEAR_REINFORCEMENT_COLUMNS:
        if column not in table.columns:
            table[column] = None
    return table[SHEAR_REINFORCEMENT_COLUMNS]


def _shear_stirrup_bar_area_mm2(bar_size: str, rebar_db: pd.DataFrame) -> float | None:
    matches = rebar_db.loc[rebar_db["name"] == str(bar_size).strip(), "area_mm2"]
    if matches.empty:
        return None
    try:
        return float(matches.iloc[0])
    except (TypeError, ValueError):
        return None


def _normalize_shear_reinforcement_table(edited_df: pd.DataFrame, previous_df: pd.DataFrame | None, rebar_db: pd.DataFrame) -> pd.DataFrame:
    table = _ensure_shear_reinforcement_columns(edited_df)
    previous = _ensure_shear_reinforcement_columns(previous_df) if previous_df is not None else pd.DataFrame(columns=SHEAR_REINFORCEMENT_COLUMNS)
    for index, row in table.iterrows():
        bar_size = _normalized_bar_size(row.get("Bar Size")) or DEFAULT_SHEAR_STIRRUP_BAR
        if bar_size not in SHEAR_STIRRUP_BAR_OPTIONS:
            bar_size = DEFAULT_SHEAR_STIRRUP_BAR
            table.at[index, "Bar Size"] = bar_size
        default_diameter = _diameter_from_database(bar_size, rebar_db) or 12.0
        previous_bar = _previous_bar_size(previous, index)
        if bar_size != previous_bar or _is_blank(row.get("Diameter_mm")):
            table.at[index, "Diameter_mm"] = default_diameter
        if _is_blank(row.get("Legs")):
            table.at[index, "Legs"] = DEFAULT_SHEAR_STIRRUP_LEGS
        if _is_blank(row.get("Spacing_mm")):
            table.at[index, "Spacing_mm"] = DEFAULT_SHEAR_STIRRUP_SPACING_MM
        if _is_blank(row.get("fy_MPa")):
            table.at[index, "fy_MPa"] = DEFAULT_SHEAR_STIRRUP_FY_MPA
        if _is_blank(row.get("Active")):
            table.at[index, "Active"] = False
    return table


def _shear_reinforcement_preview_dataframe(df: pd.DataFrame, rebar_db: pd.DataFrame) -> tuple[pd.DataFrame, list[str], list[str]]:
    table = _ensure_shear_reinforcement_columns(df)
    rows: list[dict[str, object]] = []
    errors: list[str] = []
    warnings: list[str] = []
    active_count = 0
    for index, row in table.iterrows():
        row_number = int(index) + 1
        if all(_is_blank(row.get(column)) for column in ["Zone", "x_start_m", "x_end_m", "Bar Size", "Legs", "Spacing_mm", "Note"]):
            continue
        active = _to_bool(row.get("Active"))
        if active:
            active_count += 1
        x0 = _to_float(row.get("x_start_m"))
        x1 = _to_float(row.get("x_end_m"))
        legs = _to_count(row.get("Legs"))
        spacing = _to_float(row.get("Spacing_mm"))
        fy = _to_float(row.get("fy_MPa"))
        bar_size = str(row.get("Bar Size") or DEFAULT_SHEAR_STIRRUP_BAR).strip()
        area = _shear_stirrup_bar_area_mm2(bar_size, rebar_db)
        row_errors: list[str] = []
        if x0 is None or x1 is None:
            row_errors.append("x start/end must be numeric")
        elif x1 <= x0:
            row_errors.append("x end must be greater than x start")
        if bar_size not in SHEAR_STIRRUP_BAR_OPTIONS:
            row_errors.append("bar size must be DB10, DB12, DB16, DB20, or DB25")
        if area is None:
            row_errors.append("bar area not found")
        if legs is None or legs < 1:
            row_errors.append("legs must be an integer ≥ 1")
        if spacing is None or spacing <= 0:
            row_errors.append("spacing must be positive")
        if fy is None or fy <= 0:
            row_errors.append("fy must be positive")
        if row_errors:
            errors.append(f"Row {row_number}: " + "; ".join(row_errors) + ".")
            avs_mm2_per_mm = None
            avs_mm2_per_m = None
        else:
            avs_mm2_per_mm = float(area) * float(legs) / float(spacing)
            avs_mm2_per_m = avs_mm2_per_mm * 1000.0
        rows.append(
            {
                "Active": active,
                "Zone": str(row.get("Zone") or f"Zone {row_number}"),
                "x start (m)": x0 if x0 is not None else "-",
                "x end (m)": x1 if x1 is not None else "-",
                "Stirrup": f"{bar_size} × {legs or '-'} legs @ {spacing if spacing is not None else '-'} mm",
                "fy (MPa)": fy if fy is not None else "-",
                "Av/s (mm²/mm)": avs_mm2_per_mm if avs_mm2_per_mm is not None else "-",
                "Av/s (mm²/m)": avs_mm2_per_m if avs_mm2_per_m is not None else "-",
                "Note": str(row.get("Note") or ""),
            }
        )
    if active_count == 0:
        warnings.append("No active shear reinforcement zones are confirmed yet. Future φVn check will remain NOT READY until provided stirrup zones are activated.")
    return pd.DataFrame(rows), errors, warnings


def _shear_reinforcement_column_config() -> dict[str, Any]:
    return {
        "Active": st.column_config.CheckboxColumn("Active", width="small", help="Activate only after the zone is verified as provided reinforcement."),
        "Zone": st.column_config.TextColumn("Zone", width="medium"),
        "x_start_m": st.column_config.NumberColumn("x start (m)", min_value=0.0, step=0.1, format="%.3f", width="small"),
        "x_end_m": st.column_config.NumberColumn("x end (m)", min_value=0.0, step=0.1, format="%.3f", width="small"),
        "Bar Size": st.column_config.SelectboxColumn("Bar Size", options=SHEAR_STIRRUP_BAR_OPTIONS, width="small"),
        "Diameter_mm": st.column_config.NumberColumn("Diameter (mm)", min_value=1.0, step=1.0, format="%.1f", width="small", help="Auto-filled from selected bar size."),
        "Legs": st.column_config.NumberColumn("Legs", min_value=1, step=1, width="small"),
        "Spacing_mm": st.column_config.NumberColumn("Spacing (mm)", min_value=1.0, step=25.0, format="%.1f", width="small"),
        "fy_MPa": st.column_config.NumberColumn("fy (MPa)", min_value=1.0, step=10.0, format="%.1f", width="small"),
        "Note": st.column_config.TextColumn("Note", width="large"),
    }


def _column_pier_transverse_column_config() -> dict[str, Any]:
    return {
        "Active": st.column_config.CheckboxColumn("Active", width="small", help="Activate only after the transverse reinforcement region is confirmed as provided reinforcement."),
        "Zone": st.column_config.TextColumn("Region", width="medium"),
        "x_start_m": st.column_config.NumberColumn("Region start (m)", min_value=0.0, step=0.1, format="%.3f", width="small"),
        "x_end_m": st.column_config.NumberColumn("Region end (m)", min_value=0.0, step=0.1, format="%.3f", width="small"),
        "Bar Size": st.column_config.SelectboxColumn("Tie / hoop size", options=SHEAR_STIRRUP_BAR_OPTIONS, width="small"),
        "Diameter_mm": st.column_config.NumberColumn("Diameter (mm)", min_value=1.0, step=1.0, format="%.1f", width="small", help="Auto-filled from selected tie/hoop size."),
        "Legs": st.column_config.NumberColumn("Effective legs", min_value=1, step=1, width="small", help="Effective transverse legs for shear. Torsion At uses the closed hoop/tie bar area, not prestress."),
        "Spacing_mm": st.column_config.NumberColumn("Spacing (mm)", min_value=1.0, step=25.0, format="%.1f", width="small"),
        "fy_MPa": st.column_config.NumberColumn("fy (MPa)", min_value=1.0, step=10.0, format="%.1f", width="small"),
        "Note": st.column_config.TextColumn("Confinement / torsion note", width="large"),
    }


def _analysis_mode_member_type_from_session() -> str:
    settings = st.session_state.get("analysis_mode_settings")
    if hasattr(settings, "member_type"):
        return str(getattr(settings, "member_type") or COLUMN_PIER_WORKFLOW_MEMBER_TYPE)
    if isinstance(settings, dict):
        return str(settings.get("member_type") or COLUMN_PIER_WORKFLOW_MEMBER_TYPE)
    return COLUMN_PIER_WORKFLOW_MEMBER_TYPE


def _is_column_pier_workflow() -> bool:
    return _analysis_mode_member_type_from_session() in {COLUMN_PIER_WORKFLOW_MEMBER_TYPE, "general_section"}


def _column_pier_transverse_settings_from_state() -> dict[str, Any]:
    raw = st.session_state.get(COLUMN_PIER_TRANSVERSE_SETTINGS_KEY)
    if raw is None:
        raw = (st.session_state.get("project_metadata", {}) or {}).get(COLUMN_PIER_TRANSVERSE_SETTINGS_KEY)
    if not isinstance(raw, dict):
        raw = {}
    closed_tie_layout = str(raw.get("closed_tie_layout") or COLUMN_PIER_CLOSED_TIE_OPTIONS[0])
    if closed_tie_layout not in COLUMN_PIER_CLOSED_TIE_OPTIONS:
        closed_tie_layout = COLUMN_PIER_CLOSED_TIE_OPTIONS[0]
    torsion_core_basis = str(raw.get("torsion_core_basis") or COLUMN_PIER_TORSION_CORE_OPTIONS[0])
    if torsion_core_basis not in COLUMN_PIER_TORSION_CORE_OPTIONS:
        torsion_core_basis = COLUMN_PIER_TORSION_CORE_OPTIONS[0]

    def _num(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if pd.notna(numeric) and numeric > 0.0 else None

    return {
        "closed_tie_layout": closed_tie_layout,
        "torsion_core_basis": torsion_core_basis,
        "tie_center_offset_mm": _num(raw.get("tie_center_offset_mm")) or 50.0,
        "manual_core_width_mm": _num(raw.get("manual_core_width_mm")),
        "manual_core_depth_mm": _num(raw.get("manual_core_depth_mm")),
        "note": str(raw.get("note") or "").strip(),
    }


def _store_column_pier_transverse_settings_metadata(settings: dict[str, Any]) -> None:
    clean = {
        "closed_tie_layout": str(settings.get("closed_tie_layout") or COLUMN_PIER_CLOSED_TIE_OPTIONS[0]),
        "torsion_core_basis": str(settings.get("torsion_core_basis") or COLUMN_PIER_TORSION_CORE_OPTIONS[0]),
        "tie_center_offset_mm": settings.get("tie_center_offset_mm"),
        "manual_core_width_mm": settings.get("manual_core_width_mm"),
        "manual_core_depth_mm": settings.get("manual_core_depth_mm"),
        "note": str(settings.get("note") or "").strip(),
    }
    st.session_state[COLUMN_PIER_TRANSVERSE_SETTINGS_KEY] = clean
    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    metadata[COLUMN_PIER_TRANSVERSE_SETTINGS_KEY] = clean
    st.session_state["project_metadata"] = metadata


def _store_column_pier_transverse_metadata(table: pd.DataFrame) -> None:
    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    metadata[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = _ensure_shear_reinforcement_columns(table).to_dict(orient="records")
    st.session_state["project_metadata"] = metadata


def _column_pier_transverse_readiness_cards(
    table: pd.DataFrame,
    settings: dict[str, Any],
    rebar_count: int,
    preview_errors: list[str],
) -> list[RebarMetric]:
    active_regions = int(sum(_to_bool(value) for value in table.get("Active", []))) if not table.empty else 0
    closed_layout = str(settings.get("closed_tie_layout") or "")
    closed_ready = closed_layout in {"Closed ties / hoops", "Spiral reinforcement"}
    torsion_basis = str(settings.get("torsion_core_basis") or "")
    torsion_ready = closed_ready and active_regions > 0 and torsion_basis != "Not defined yet" and not preview_errors
    shear_ready = active_regions > 0 and not preview_errors
    longitudinal_status = "Available" if rebar_count > 0 else "Missing"
    return [
        RebarMetric("Shear input", "Ready" if shear_ready else "REVIEW", f"{active_regions} active transverse region(s)", "ready" if shear_ready else "warning", strong=not shear_ready),
        RebarMetric("Torsion input", "Ready" if torsion_ready else "REVIEW", "Needs closed ties/hoops or spiral plus torsion core basis", "ready" if torsion_ready else "warning", strong=not torsion_ready),
        RebarMetric("Closed transverse reinforcement", closed_layout or "Not defined", "Do not use open ties for torsion capacity", "ready" if closed_ready else "warning"),
        RebarMetric("Longitudinal torsion bars", longitudinal_status, "Ordinary active rebar only; prestress is not counted as Al", "ready" if rebar_count > 0 else "warning"),
        RebarMetric("Capability", "Input owner only", "No shear/torsion PASS/FAIL issued in this milestone", "neutral"),
    ]


def _render_column_pier_transverse_settings() -> dict[str, Any]:
    current = _column_pier_transverse_settings_from_state()
    st.markdown("#### Column/Pier Shear and Torsion Reinforcement")
    st.caption(
        "Define transverse reinforcement regions for column-type members. These inputs are the future source for shear reinforcement, "
        "closed tie/hoop torsion reinforcement, and confinement review; no shear or torsion capacity is certified from this page yet."
    )
    col_a, col_b, col_c = st.columns([1.0, 1.0, 1.0], gap="small")
    with col_a:
        closed_tie_layout = st.selectbox(
            "Transverse reinforcement type",
            COLUMN_PIER_CLOSED_TIE_OPTIONS,
            index=COLUMN_PIER_CLOSED_TIE_OPTIONS.index(current["closed_tie_layout"]),
            key="column_pier_transverse_closed_tie_layout",
            help="Torsion capacity requires closed transverse reinforcement. Open ties are retained for shear-only review and are guarded for torsion.",
        )
    with col_b:
        torsion_core_basis = st.selectbox(
            "Torsion core basis",
            COLUMN_PIER_TORSION_CORE_OPTIONS,
            index=COLUMN_PIER_TORSION_CORE_OPTIONS.index(current["torsion_core_basis"]),
            key="column_pier_transverse_torsion_core_basis",
            help="Future torsion checks will need Ao/Aoh or equivalent core geometry. This milestone records the owner and guard state only.",
        )
    with col_c:
        tie_center_offset_mm = st.number_input(
            "Tie/hoop center offset (mm)",
            min_value=1.0,
            value=float(current["tie_center_offset_mm"] or 50.0),
            step=5.0,
            format="%.1f",
            key="column_pier_transverse_tie_offset_mm",
        )
    manual_disabled = torsion_core_basis != "Manual core dimensions"
    col_w, col_d, col_note = st.columns([1.0, 1.0, 2.0], gap="small")
    with col_w:
        manual_core_width_mm = st.number_input(
            "Manual core width bo (mm)",
            min_value=0.0,
            value=float(current.get("manual_core_width_mm") or 0.0),
            step=10.0,
            format="%.1f",
            disabled=manual_disabled,
            key="column_pier_transverse_core_width_mm",
        )
    with col_d:
        manual_core_depth_mm = st.number_input(
            "Manual core depth ho (mm)",
            min_value=0.0,
            value=float(current.get("manual_core_depth_mm") or 0.0),
            step=10.0,
            format="%.1f",
            disabled=manual_disabled,
            key="column_pier_transverse_core_depth_mm",
        )
    with col_note:
        note = st.text_input(
            "Transverse reinforcement note",
            value=str(current.get("note") or ""),
            key="column_pier_transverse_note",
            placeholder="e.g. closed hoops with seismic confinement zone at member ends",
        )
    settings = {
        "closed_tie_layout": closed_tie_layout,
        "torsion_core_basis": torsion_core_basis,
        "tie_center_offset_mm": float(tie_center_offset_mm) if float(tie_center_offset_mm) > 0.0 else None,
        "manual_core_width_mm": float(manual_core_width_mm) if not manual_disabled and float(manual_core_width_mm) > 0.0 else None,
        "manual_core_depth_mm": float(manual_core_depth_mm) if not manual_disabled and float(manual_core_depth_mm) > 0.0 else None,
        "note": note,
    }
    _store_column_pier_transverse_settings_metadata(settings)
    if closed_tie_layout == "Open ties - shear only review":
        st.warning("Open ties are guarded for torsion. Future torsion capacity must remain REVIEW/NOT READY unless closed hoops/ties or spiral reinforcement are provided.")
    else:
        st.info("Closed transverse reinforcement is recorded as the future torsion transverse source. Verify hooks, anchorage, spacing, and confinement requirements before final design.")
    return settings


def _shear_depth_settings_from_state() -> dict[str, Any]:
    """Return Beam/Girder effective shear-depth settings stored in metadata.

    Analysis remains read-only.  These settings live with the section/rebar
    definition because d and dv are section/detailing design parameters, not ULS
    load inputs.
    """

    raw = st.session_state.get(SHEAR_DEPTH_SETTINGS_KEY)
    if raw is None:
        raw = (st.session_state.get("project_metadata", {}) or {}).get(SHEAR_DEPTH_SETTINGS_KEY)
    if not isinstance(raw, dict):
        raw = {}
    mode = str(raw.get("mode") or SHEAR_DEPTH_MODE_AUTO)
    if mode not in {SHEAR_DEPTH_MODE_AUTO, SHEAR_DEPTH_MODE_MANUAL}:
        mode = SHEAR_DEPTH_MODE_AUTO
    def _num(value: Any) -> float | None:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return None
        return numeric if pd.notna(numeric) and numeric > 0.0 else None
    return {
        "mode": mode,
        "d_mm": _num(raw.get("d_mm")),
        "dv_mm": _num(raw.get("dv_mm")),
        "note": str(raw.get("note") or "").strip(),
    }


def _store_shear_depth_settings_metadata(settings: dict[str, Any]) -> None:
    clean = {
        "mode": str(settings.get("mode") or SHEAR_DEPTH_MODE_AUTO),
        "d_mm": settings.get("d_mm"),
        "dv_mm": settings.get("dv_mm"),
        "note": str(settings.get("note") or "").strip(),
    }
    st.session_state[SHEAR_DEPTH_SETTINGS_KEY] = clean
    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    metadata[SHEAR_DEPTH_SETTINGS_KEY] = clean
    st.session_state["project_metadata"] = metadata


def _render_effective_shear_depth_settings() -> None:
    st.markdown("#### Beam/Girder Effective Shear Depth Basis")
    st.caption(
        "Define the source of effective d / dv used by Analysis → ULS Shear. "
        "Auto mode derives d from the active reinforcement/strand centroid and derives dv for the AASHTO route; manual mode lets the engineer lock audited design-depth values."
    )
    current = _shear_depth_settings_from_state()
    mode_options = [SHEAR_DEPTH_MODE_AUTO, SHEAR_DEPTH_MODE_MANUAL]
    mode = st.radio(
        "Effective depth input mode",
        options=mode_options,
        index=mode_options.index(current["mode"]),
        horizontal=True,
        key="beam_girder_shear_depth_mode",
        help="Use manual mode only when d/dv has been checked from the section detailing. Analysis reads this setting but does not own the input.",
    )
    col_d, col_dv, col_note = st.columns([1.0, 1.0, 2.0], gap="small")
    with col_d:
        d_mm = st.number_input(
            "Manual d (mm)",
            min_value=0.0,
            value=float(current.get("d_mm") or 0.0),
            step=10.0,
            format="%.1f",
            disabled=mode != SHEAR_DEPTH_MODE_MANUAL,
            key="beam_girder_shear_depth_d_mm",
            help="Effective depth to tension reinforcement/strand centroid. Used directly for ACI shear and as the d basis for bridge dv derivation when dv is not manually supplied.",
        )
    with col_dv:
        dv_mm = st.number_input(
            "Manual dv (mm)",
            min_value=0.0,
            value=float(current.get("dv_mm") or 0.0),
            step=10.0,
            format="%.1f",
            disabled=mode != SHEAR_DEPTH_MODE_MANUAL,
            key="beam_girder_shear_depth_dv_mm",
            help="Effective shear depth for AASHTO/bridge shear. Leave as 0 to let the app derive dv from d and section depth in auto/bridge route.",
        )
    with col_note:
        note = st.text_input(
            "Depth basis note",
            value=str(current.get("note") or ""),
            disabled=mode != SHEAR_DEPTH_MODE_MANUAL,
            key="beam_girder_shear_depth_note",
            placeholder="e.g. d from centroid of bottom strand group; dv per project design basis",
        )
    settings = {
        "mode": mode,
        "d_mm": float(d_mm) if mode == SHEAR_DEPTH_MODE_MANUAL and float(d_mm) > 0.0 else None,
        "dv_mm": float(dv_mm) if mode == SHEAR_DEPTH_MODE_MANUAL and float(dv_mm) > 0.0 else None,
        "note": note if mode == SHEAR_DEPTH_MODE_MANUAL else "",
    }
    _store_shear_depth_settings_metadata(settings)
    if mode == SHEAR_DEPTH_MODE_AUTO:
        st.info("Auto mode: Analysis will calculate d from active longitudinal reinforcement/prestress centroid at the local tension face and derive dv for the bridge/AASHTO route. Review the d/dv values in the Shear audit table.")
    else:
        if not settings["d_mm"]:
            st.warning("Manual mode is selected but manual d is not defined. Analysis will fall back to the auto d basis until a positive d is entered.")
        elif settings["dv_mm"]:
            st.success(f"Manual effective depth basis stored: d = {settings['d_mm']:.1f} mm, dv = {settings['dv_mm']:.1f} mm.")
        else:
            st.warning(f"Manual d = {settings['d_mm']:.1f} mm is stored, but manual dv is blank. Bridge/AASHTO shear will derive dv from d and section depth.")


def _store_shear_reinforcement_metadata(table: pd.DataFrame) -> None:
    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    metadata[SHEAR_REINFORCEMENT_TABLE_KEY] = _ensure_shear_reinforcement_columns(table).to_dict(orient="records")
    st.session_state["project_metadata"] = metadata


def _render_shear_reinforcement_layout(rebar_db: pd.DataFrame) -> None:
    st.markdown("#### Beam/Girder Shear Reinforcement Layout")
    st.caption(
        "Define provided stirrup zones along the member for the Analysis → ULS Shear tab. "
        "Analysis reads Active zones as the provided stirrup layout for φVn; inactive zones are shown here but are not used for capacity."
    )
    span_m = _beam_girder_span_length_for_shear_layout()
    if SHEAR_REINFORCEMENT_TABLE_KEY not in st.session_state:
        existing = (st.session_state.get("project_metadata", {}) or {}).get(SHEAR_REINFORCEMENT_TABLE_KEY)
        if isinstance(existing, list):
            st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = _ensure_shear_reinforcement_columns(pd.DataFrame(existing))
        else:
            st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = _default_shear_reinforcement_table(span_m)
    st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = _ensure_shear_reinforcement_columns(pd.DataFrame(st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY]))
    if "beam_girder_shear_reinforcement_editor_revision" not in st.session_state:
        st.session_state["beam_girder_shear_reinforcement_editor_revision"] = 0

    cards = [
        RebarMetric("Input method", "Zone table", "Commercial girder detailing"),
        RebarMetric("Default stirrup", DEFAULT_SHEAR_STIRRUP_BAR, "Dropdown: DB10/DB12/DB16/DB20/DB25"),
        RebarMetric("Span basis", f"{span_m:.3f} m", "From Setup when available"),
        RebarMetric("Shear check", "Analysis ULS", "Active zones feed provided-stirrup φVn"),
        RebarMetric("Final use", "Provided layout", "Auto minimum will be a design aid only"),
    ]
    st.markdown(_strip_html(cards), unsafe_allow_html=True)

    _render_effective_shear_depth_settings()

    action_cols = st.columns([1.0, 1.0, 3.0], gap="small")
    with action_cols[0]:
        if st.button("Reset to DB12 zone template", use_container_width=True, key="shear_reinf_reset_template"):
            st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = _default_shear_reinforcement_table(span_m)
            st.session_state["beam_girder_shear_reinforcement_editor_revision"] += 1
            _store_shear_reinforcement_metadata(st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY])
            st.rerun()
    with action_cols[1]:
        if st.button("Activate all zones", use_container_width=True, key="shear_reinf_activate_all"):
            table = _ensure_shear_reinforcement_columns(pd.DataFrame(st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY]))
            table["Active"] = True
            st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = table
            st.session_state["beam_girder_shear_reinforcement_editor_revision"] += 1
            _store_shear_reinforcement_metadata(table)
            st.rerun()
    with action_cols[2]:
        st.info(
            "Use Active only for reinforcement that is actually provided/accepted. "
            "Future shear analysis will read active zones as the provided stirrup layout; it will not silently assume minimum stirrups."
        )

    previous = st.session_state.get(SHEAR_REINFORCEMENT_TABLE_KEY)
    shear_editor_key = f"beam_girder_shear_reinforcement_editor_{st.session_state['beam_girder_shear_reinforcement_editor_revision']}"
    edited = st.data_editor(
        _ensure_shear_reinforcement_columns(pd.DataFrame(previous)),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=_shear_reinforcement_column_config(),
        key=shear_editor_key,
    )
    normalized = _normalize_shear_reinforcement_table(edited, pd.DataFrame(previous), rebar_db)
    st.session_state[SHEAR_REINFORCEMENT_TABLE_KEY] = normalized
    _store_shear_reinforcement_metadata(normalized)

    preview_df, errors, warnings = _shear_reinforcement_preview_dataframe(normalized, rebar_db)
    st.session_state[SHEAR_REINFORCEMENT_VALID_KEY] = not errors and not warnings

    with st.expander("Shear reinforcement status", expanded=bool(errors or warnings)):
        active_rows = int(sum(_to_bool(value) for value in normalized.get("Active", []))) if not normalized.empty else 0
        cols = st.columns(4)
        cols[0].metric("Zones", f"{len(normalized):,}")
        cols[1].metric("Active zones", f"{active_rows:,}")
        cols[2].metric("Errors", f"{len(errors):,}")
        cols[3].metric("Default bar", DEFAULT_SHEAR_STIRRUP_BAR)
        for error in errors:
            st.error(error)
        for warning in warnings:
            st.warning(warning)
        if not errors and not warnings:
            st.success("Shear reinforcement layout is ready as provided-zone input for the future φVn engine.")

    st.markdown("##### Av/s provided preview")
    st.caption("Analysis ULS reads this table for SHEAR.CODE2 φVn, φVc, φVs, minimum Av/s, maximum spacing, and active-zone coverage gates.")
    if preview_df.empty:
        st.info("No shear reinforcement zones are defined yet.")
    else:
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

    with st.expander("Shear reinforcement workflow notes", expanded=False):
        st.write("- Provided stirrup layout is the source of truth for SHEAR.CODE2 φVn checks.")
        st.write("- DB12 is the default stirrup size; users can select DB10, DB12, DB16, DB20, or DB25 by zone.")
        st.write("- Auto required/minimum stirrup design should be a design assistant only; the final check must use the provided active layout.")
        st.write("- No shear strength formula is calculated in SHEAR.REINF1.")


def _render_column_pier_transverse_reinforcement_layout(rebar_db: pd.DataFrame) -> None:
    settings = _render_column_pier_transverse_settings()
    existing = st.session_state.get(COLUMN_PIER_TRANSVERSE_TABLE_KEY)
    if existing is None:
        existing = (st.session_state.get("project_metadata", {}) or {}).get(COLUMN_PIER_TRANSVERSE_TABLE_KEY)
    if isinstance(existing, list):
        st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = _ensure_shear_reinforcement_columns(pd.DataFrame(existing))
    elif COLUMN_PIER_TRANSVERSE_TABLE_KEY not in st.session_state:
        st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = _default_column_pier_transverse_reinforcement_table()
    st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = _ensure_shear_reinforcement_columns(pd.DataFrame(st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY]))
    if "column_pier_transverse_reinforcement_editor_revision" not in st.session_state:
        st.session_state["column_pier_transverse_reinforcement_editor_revision"] = 0

    previous = st.session_state.get(COLUMN_PIER_TRANSVERSE_TABLE_KEY)
    preview_df, preview_errors, preview_warnings = _shear_reinforcement_preview_dataframe(pd.DataFrame(previous), rebar_db)
    active_rebars = list(st.session_state.get("rebars", []) or [])
    st.markdown(_strip_html(_column_pier_transverse_readiness_cards(pd.DataFrame(previous), settings, len(active_rebars), preview_errors)), unsafe_allow_html=True)
    st.info(
        "Longitudinal torsion reinforcement will be read from active ordinary rebar only. Prestress strands, tendons, and PT bars are not counted as Al in this guarded column/pier workflow."
    )

    action_cols = st.columns([1.0, 1.0, 3.0], gap="small")
    with action_cols[0]:
        if st.button("Reset column/pier template", use_container_width=True, key="column_pier_transverse_reset_template"):
            table = _default_column_pier_transverse_reinforcement_table()
            st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = table
            st.session_state["column_pier_transverse_reinforcement_editor_revision"] += 1
            _store_column_pier_transverse_metadata(table)
            st.rerun()
    with action_cols[1]:
        if st.button("Activate all regions", use_container_width=True, key="column_pier_transverse_activate_all"):
            table = _ensure_shear_reinforcement_columns(pd.DataFrame(st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY]))
            table["Active"] = True
            st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = table
            st.session_state["column_pier_transverse_reinforcement_editor_revision"] += 1
            _store_column_pier_transverse_metadata(table)
            st.rerun()
    with action_cols[2]:
        st.info(
            "Use Active only for transverse reinforcement that is actually provided/accepted. Future column/pier shear and torsion checks must not assume minimum ties silently."
        )

    editor_key = f"column_pier_transverse_reinforcement_editor_{st.session_state['column_pier_transverse_reinforcement_editor_revision']}"
    edited = st.data_editor(
        _ensure_shear_reinforcement_columns(pd.DataFrame(previous)),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=_column_pier_transverse_column_config(),
        key=editor_key,
    )
    normalized = _normalize_shear_reinforcement_table(edited, pd.DataFrame(previous), rebar_db)
    st.session_state[COLUMN_PIER_TRANSVERSE_TABLE_KEY] = normalized
    _store_column_pier_transverse_metadata(normalized)

    preview_df, errors, warnings = _shear_reinforcement_preview_dataframe(normalized, rebar_db)
    if settings.get("closed_tie_layout") == "Open ties - shear only review":
        warnings.append("Open ties are not accepted as torsion transverse reinforcement; torsion must remain REVIEW until closed ties/hoops or spiral reinforcement are defined.")
    if settings.get("torsion_core_basis") == "Manual core dimensions" and not (settings.get("manual_core_width_mm") and settings.get("manual_core_depth_mm")):
        warnings.append("Manual torsion core basis is selected, but bo/ho are not both defined.")
    st.session_state[COLUMN_PIER_TRANSVERSE_VALID_KEY] = not errors

    with st.expander("Column/Pier transverse reinforcement status", expanded=bool(errors or warnings)):
        active_rows = int(sum(_to_bool(value) for value in normalized.get("Active", []))) if not normalized.empty else 0
        cols = st.columns(5)
        cols[0].metric("Regions", f"{len(normalized):,}")
        cols[1].metric("Active regions", f"{active_rows:,}")
        cols[2].metric("Errors", f"{len(errors):,}")
        cols[3].metric("Warnings", f"{len(warnings):,}")
        cols[4].metric("Default tie", DEFAULT_SHEAR_STIRRUP_BAR)
        for error in errors:
            st.error(error)
        for warning in warnings:
            st.warning(warning)
        if not errors and not warnings:
            st.success("Column/Pier transverse reinforcement input is ready for future shear/torsion solver milestones.")

    st.markdown("##### Transverse reinforcement provided preview")
    st.caption("This preview computes provided Av/s from active/inactive regions only. It does not issue shear or torsion PASS/FAIL.")
    if preview_df.empty:
        st.info("No transverse reinforcement regions are defined yet.")
    else:
        st.dataframe(preview_df, use_container_width=True, hide_index=True)

    with st.expander("Column/Pier shear and torsion workflow notes", expanded=False):
        st.write("- Shear will use active transverse regions as provided Av/s; no minimum tie layout is silently assumed.")
        st.write("- Torsion requires closed ties/hoops or spiral reinforcement plus a defined torsion core basis before any future capacity result can be accepted.")
        st.write("- Longitudinal torsion Al comes from active ordinary rebar rows. Prestress strands, tendons, and PT bars are not counted as Al in this milestone.")
        st.write("- This UI milestone records and validates input ownership only; it does not certify ACI 318 or AASHTO LRFD shear/torsion capacity.")

def _render_longitudinal_rebar_tab(
    rebar_db: pd.DataFrame,
    bar_size_options: list[str],
    active_material_name: str | None,
    member_type: str,
) -> None:
    """Render ordinary longitudinal reinforcement inputs and preview.

    This tab owns the existing ordinary Rebar table.  Beam/Girder torsion Al
    review intentionally reads this same table so users do not maintain a
    duplicate longitudinal-torsion table that can drift away from the actual
    section reinforcement.
    """

    if member_type == COLUMN_PIER_WORKFLOW_MEMBER_TYPE:
        st.caption(
            "Ordinary longitudinal reinforcement used by Column/Pier PMM and future shear/torsion checks. "
            "Active ordinary bars are the future longitudinal torsion Al source; prestress strands, tendons, and PT bars are not counted as Al in this guarded workflow."
        )
    else:
        st.caption(
            "Ordinary longitudinal reinforcement used by PMM / SLS / flexure checks. "
            "For Beam/Girder torsion, active ordinary bars are also the review-only Al source; do not duplicate Al in a separate table."
        )
    if not ordinary_rebar_enabled(st.session_state, default=True):
        st.info(
            "Ordinary rebar is disabled for the current section in Section Builder. "
            "Stored Rebar table data is preserved, but ordinary rebar and torsion Al are ignored by analysis until you enable it again."
        )
        with st.expander("Stored Rebar table preview", expanded=False):
            table = st.session_state.get("rebar_table")
            if table is None:
                st.caption("No stored Rebar table is available yet.")
            else:
                st.dataframe(_ensure_rebar_table_columns(pd.DataFrame(table)), use_container_width=True, hide_index=True)
        st.session_state["rebars_valid_for_analysis"] = True
        return

    if "rebar_table" not in st.session_state:
        st.session_state["rebar_table"] = _default_rebar_table(rebar_db)
    st.session_state["rebar_table"] = _ensure_rebar_table_columns(st.session_state["rebar_table"])
    if "rebar_editor_revision" not in st.session_state:
        st.session_state["rebar_editor_revision"] = 0

    input_mode = "Manual table"
    edited_df = st.session_state["rebar_table"]

    input_col, status_col = st.columns([1.45, 0.85], gap="large")
    summary_slot = None
    with input_col:
        with st.container(border=True):
            st.markdown("#### Longitudinal Rebar Input")
            # Keep the summary visually above the editor. The placeholder is
            # filled after data_editor returns so the metrics still use the
            # normalized table from the current rerun instead of stale pre-edit
            # values.
            summary_slot = st.empty()
            input_mode = st.selectbox("Rebar input mode", ["Manual table", "Auto perimeter layout"])
            st.markdown(
                '<div class="cpmm-rebar-note">Selecting a database bar size fills Diameter and default Material. Diameter and Material remain editable for project-specific overrides.</div>',
                unsafe_allow_html=True,
            )
            if input_mode == "Auto perimeter layout":
                _render_auto_perimeter_controls(rebar_db, st.session_state.get("section_geometry"))

            # The editable table is always shown. Auto perimeter layout is a
            # preview/apply workflow, so the main table remains the single
            # source of truth for PMM/SLS/torsion-Al review after generated bars
            # are applied.
            editor_key = f"rebar_data_editor_{st.session_state['rebar_editor_revision']}"
            edited_df = _render_rebar_editor(st.session_state["rebar_table"], bar_size_options, editor_key)

    previous_table = st.session_state.get("rebar_table")
    normalized_df = normalize_rebar_table_for_bar_size_sync(edited_df, previous_table, rebar_db)

    if not rebar_editor_tables_equal(normalized_df, edited_df):
        # A database Bar Size edit changed dependent cells such as Diameter_mm
        # or Material. Updating only the backing dataframe after the widget has
        # rendered leaves the visible data_editor one rerun behind. Bump the
        # editor key and rerun once so the user sees DB25→25/SD40 or
        # DB32→32/SD50 immediately, while manual overrides remain stable when
        # Bar Size is unchanged.
        st.session_state["rebar_table"] = normalized_df
        st.session_state["rebar_editor_revision"] += 1
        st.rerun()

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
            _render_validation(
                result,
                geometry_errors,
                geometry is not None,
                valid_for_analysis,
                active_prestress_count=(len(st.session_state.get("prestress_elements", []) or []) if prestressing_steel_enabled(st.session_state, default=True) else 0),
            )
            st.markdown(
                '<div class="cpmm-rebar-note">Coordinates are in mm. x is positive to the right; y is positive upward in the section preview.</div>',
                unsafe_allow_html=True,
            )

        if geometry is not None:
            st.subheader("Section Preview with Rebar — Longitudinal")
            st.caption("Default preview shows ordinary rebar only. Bars are drawn at true diameter scale; prestressing steel is intentionally hidden on the Rebar page.")
            preview_fig = create_section_preview(
                geometry,
                st.session_state.get("section_dimensions", []),
                "symbol_value",
                st.session_state["rebars"],
                [],
            )
            preview_fig.update_layout(height=430, margin=dict(l=10, r=10, t=36, b=10))
            st.plotly_chart(
                preview_fig,
                use_container_width=True,
                key="rebar_section_preview",
            )
            if prestressing_steel_enabled(st.session_state, default=True):
                prestress_elements = list(st.session_state.get("prestress_elements", []) or [])
                if prestress_elements:
                    with st.expander("Combined Reinforcement Preview", expanded=False):
                        st.caption(
                            "Coordination view only: ordinary rebar and prestressing steel are shown together. "
                            "Default page previews remain separated to avoid mixing rebar and prestress workflows."
                        )
                        combined_fig = create_section_preview(
                            geometry,
                            st.session_state.get("section_dimensions", []),
                            "symbol_value",
                            st.session_state["rebars"],
                            prestress_elements,
                        )
                        combined_fig.update_layout(height=430, margin=dict(l=10, r=10, t=36, b=10))
                        st.plotly_chart(
                            combined_fig,
                            use_container_width=True,
                            key="rebar_combined_reinforcement_preview",
                        )

    st.subheader("Longitudinal Rebar Summary")
    st.dataframe(rebar_summary_dataframe(st.session_state["rebars"]), use_container_width=True, hide_index=True)

    with st.expander("Longitudinal rebar / torsion Al workflow notes", expanded=False):
        st.write("- This ordinary Rebar table remains the single source of truth for longitudinal bars in PMM/SLS/flexure analysis.")
        if member_type == COLUMN_PIER_WORKFLOW_MEMBER_TYPE:
            st.write("- Column/Pier torsion will read active ordinary rebar from this same table as the longitudinal Al source.")
            st.write("- Prestress strands, tendons, and PT bars are not counted as longitudinal torsion Al in this milestone.")
        else:
            st.write("- Beam/Girder torsion reads active ordinary bars from this same table as the review-only Al provided source.")
        st.write("- Do not count flexural bars as torsion perimeter Al unless they are intentionally detailed around the closed-hoop perimeter.")


def _render_beam_girder_transverse_rebar_tab(rebar_db: pd.DataFrame) -> None:
    """Render Beam/Girder transverse reinforcement and effective d/dv inputs."""

    st.caption(
        "Transverse reinforcement and effective shear-depth inputs used by Analysis → ULS Shear and Torsion. "
        "Active stirrup zones are the provided layout for SHEAR.CODE2 φVn and the closed-hoop source for TORSION.CODE2 φTn."
    )
    _render_shear_reinforcement_layout(rebar_db)


def _render_transverse_rebar_tab(rebar_db: pd.DataFrame) -> None:
    """Render workflow-aware transverse reinforcement inputs."""

    if _is_column_pier_workflow():
        st.caption(
            "Transverse reinforcement for Column/Pier/Wall/Pylon shear, torsion, and confinement workflow. "
            "Active regions are provided reinforcement only; future checks must not count prestress as longitudinal torsion Al."
        )
        _render_column_pier_transverse_reinforcement_layout(rebar_db)
    else:
        st.caption(
            "Transverse reinforcement and effective shear-depth inputs used by Analysis -> ULS Shear and Torsion. "
            "Active stirrup zones are the provided layout for SHEAR.CODE2 phi Vn and the closed-hoop source for TORSION.CODE2 phi Tn."
        )
        _render_beam_girder_transverse_rebar_tab(rebar_db)


def render_rebar_page() -> None:
    st.markdown(_REBAR_PAGE_CSS, unsafe_allow_html=True)
    st.subheader("Rebar")
    rebar_db = load_rebar_database()
    bar_size_options = ["", "Custom"] + [str(name) for name in rebar_db["name"].tolist()]
    active_material_name = st.session_state.get("active_rebar_material_name")
    member_type = _analysis_mode_member_type_from_session()

    st.caption(
        "Define reinforcement used by the active section analysis. "
        "Longitudinal bars and transverse reinforcement regions are separated so PMM, shear, torsion, and confinement inputs stay readable and are not duplicated."
    )

    longitudinal_tab, transverse_tab = st.tabs(["Longitudinal Rebar", "Transverse Rebar"])
    with longitudinal_tab:
        _render_longitudinal_rebar_tab(rebar_db, bar_size_options, active_material_name, member_type)
    with transverse_tab:
        _render_transverse_rebar_tab(rebar_db)
