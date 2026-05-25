"""Rebar tab UI and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class RebarParseResult:
    rebars: list[Rebar]
    errors: list[str]
    warnings: list[str]
    info: list[str]


def load_rebar_database(path: Path | str = DEFAULT_REBAR_DB_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def _default_rebar_table(rebar_db: pd.DataFrame) -> pd.DataFrame:
    default_size = "DB20" if "DB20" in set(rebar_db["name"]) else str(rebar_db.iloc[0]["name"])
    default_diameter = float(rebar_db.loc[rebar_db["name"] == default_size, "diameter_mm"].iloc[0])
    return pd.DataFrame(
        [
            {"Active": True, "Label": "B1", "x_mm": -150.0, "y_mm": -250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": "SD40", "Count": 1, "Note": ""},
            {"Active": True, "Label": "B2", "x_mm": 150.0, "y_mm": -250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": "SD40", "Count": 1, "Note": ""},
            {"Active": True, "Label": "B3", "x_mm": 150.0, "y_mm": 250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": "SD40", "Count": 1, "Note": ""},
            {"Active": True, "Label": "B4", "x_mm": -150.0, "y_mm": 250.0, "Bar Size": default_size, "Diameter_mm": default_diameter, "Material": "SD40", "Count": 1, "Note": ""},
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


def _resolve_diameter(row: pd.Series, rebar_db: pd.DataFrame, row_number: int) -> tuple[float | None, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    bar_size = "" if _is_blank(row.get("Bar Size")) else str(row.get("Bar Size")).strip()
    manual_diameter = _to_float(row.get("Diameter_mm"))

    if bar_size and bar_size != "Custom":
        database_diameter = _diameter_from_database(bar_size, rebar_db)
        if database_diameter is not None:
            return database_diameter, errors, warnings
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


def _render_validation(result: RebarParseResult, geometry_errors: list[str], geometry_available: bool, valid_for_analysis: bool) -> None:
    st.subheader("Rebar Validation")
    all_errors = [*result.errors, *geometry_errors]
    if all_errors:
        for error in all_errors:
            st.error(f"ERROR: {error}")
    else:
        st.success("No validation errors")

    warnings = list(result.warnings)
    if not geometry_available:
        warnings.append("Section geometry is not available yet; geometry validation will run after a valid section is generated.")
    if warnings:
        for warning in warnings:
            st.warning(f"WARNING: {warning}")
    else:
        st.info("WARNING: none")

    for info in result.info:
        st.info(f"INFO: {info}")
    st.info(f"INFO: Rebars valid for analysis: {'Yes' if valid_for_analysis else 'No'}")


def render_rebar_page() -> None:
    st.subheader("Rebar")
    rebar_db = load_rebar_database()
    bar_size_options = ["", "Custom"] + [str(name) for name in rebar_db["name"].tolist()]
    input_mode = st.selectbox("Rebar input mode", ["Manual table", "Rectangular perimeter layout", "Circular layout"])
    st.info("If Bar Size is selected, database diameter is used. Leave Bar Size blank or choose Custom to use manual Diameter_mm.")
    st.info("Future milestones will allow rebar selection from project-defined material lists. This tab continues to use the rebar database for bar sizes.")

    if input_mode != "Manual table":
        st.info("Automatic rebar layouts are planned for a later milestone. Use Manual table for now.")
        return

    if "rebar_table" not in st.session_state:
        st.session_state["rebar_table"] = _default_rebar_table(rebar_db)

    edited_df = st.data_editor(
        st.session_state["rebar_table"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active"),
            "Label": st.column_config.TextColumn("Label"),
            "x_mm": st.column_config.NumberColumn("x_mm"),
            "y_mm": st.column_config.NumberColumn("y_mm"),
            "Bar Size": st.column_config.SelectboxColumn("Bar Size", options=bar_size_options),
            "Diameter_mm": st.column_config.NumberColumn("Diameter_mm"),
            "Material": st.column_config.TextColumn("Material"),
            "Count": st.column_config.NumberColumn("Count", min_value=1, step=1),
            "Note": st.column_config.TextColumn("Note"),
        },
        key="rebar_data_editor",
    )
    st.session_state["rebar_table"] = edited_df

    result = rebars_from_dataframe(edited_df, rebar_db)
    geometry = st.session_state.get("section_geometry")
    geometry_errors = validate_rebars_against_geometry(result.rebars, geometry)
    valid_for_analysis = rebars_valid_for_analysis(result, geometry_errors)
    st.session_state["rebars"] = result.rebars
    st.session_state["rebars_valid_for_analysis"] = valid_for_analysis

    _render_validation(result, geometry_errors, geometry is not None, valid_for_analysis)

    total_as = sum(rebar.area_mm2 for rebar in st.session_state["rebars"])
    metric_cols = st.columns(2)
    metric_cols[0].metric("Active bars", f"{len(st.session_state['rebars']):,}")
    metric_cols[1].metric("Total As", f"{total_as:,.1f} mm^2")

    st.subheader("Rebar Summary")
    st.dataframe(rebar_summary_dataframe(st.session_state["rebars"]), use_container_width=True, hide_index=True)

    if geometry is not None:
        st.subheader("Section Preview with Rebar")
        st.plotly_chart(
            create_section_preview(
                geometry,
                st.session_state.get("section_dimensions", []),
                "symbol_value",
                st.session_state["rebars"],
                st.session_state.get("prestress_elements", []),
            ),
            use_container_width=True,
            key="rebar_section_preview",
        )
