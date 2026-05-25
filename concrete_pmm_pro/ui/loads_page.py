"""Loads tab UI and conversion helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import kN_to_N, kNm_to_Nmm, tonf_to_N, tonfm_to_Nmm

LOAD_TYPE_OPTIONS = ["ULS", "SLS", "Extreme", "Construction", "Other"]
FORCE_UNIT_OPTIONS = ["kN", "N", "tonf"]
MOMENT_UNIT_OPTIONS = ["kN-m", "N-mm", "tonf-m"]


@dataclass(frozen=True)
class LoadParseResult:
    load_cases: list[LoadCase]
    errors: list[str]
    warnings: list[str]
    info: list[str]


def _default_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Combo Name": "ULS-01", "Pu": 1000.0, "Mux": 100.0, "Muy": 50.0, "Load Type": "ULS", "Note": ""},
            {"Active": True, "Combo Name": "ULS-02", "Pu": 1200.0, "Mux": 120.0, "Muy": 60.0, "Load Type": "ULS", "Note": ""},
            {"Active": True, "Combo Name": "SLS-01", "Pu": 700.0, "Mux": 70.0, "Muy": 35.0, "Load Type": "SLS", "Note": ""},
        ]
    )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _row_is_blank(row: pd.Series) -> bool:
    columns = ["Combo Name", "Pu", "Mux", "Muy", "Mx", "My", "Load Type", "Note"]
    return all(_is_blank(row.get(column)) for column in columns)


def _to_float(value: Any) -> float | None:
    if _is_blank(value):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _force_to_N(value: float, unit: str) -> float:
    if unit == "kN":
        return kN_to_N(value)
    if unit == "N":
        return float(value)
    if unit == "tonf":
        return tonf_to_N(value)
    raise ValueError(f"Unsupported force unit: {unit}")


def _moment_to_Nmm(value: float, unit: str) -> float:
    if unit == "kN-m":
        return kNm_to_Nmm(value)
    if unit == "N-mm":
        return float(value)
    if unit == "tonf-m":
        return tonfm_to_Nmm(value)
    raise ValueError(f"Unsupported moment unit: {unit}")


def _load_value(row: pd.Series, primary_column: str, legacy_column: str | None = None) -> Any:
    if primary_column in row.index and not _is_blank(row.get(primary_column)):
        return row.get(primary_column)
    if legacy_column and legacy_column in row.index:
        return row.get(legacy_column)
    return row.get(primary_column)


def parse_load_cases_from_dataframe(df: pd.DataFrame, force_unit: str, moment_unit: str) -> LoadParseResult:
    errors: list[str] = []
    load_cases: list[LoadCase] = []

    for index, row in df.iterrows():
        row_number = int(index) + 1
        if _row_is_blank(row):
            continue

        name_value = row.get("Combo Name")
        if _is_blank(name_value):
            errors.append(f"Row {row_number}: Combo Name cannot be blank.")
            continue
        name = str(name_value).strip()

        column_sources = {
            "Pu": ("Pu", None),
            "Mux": ("Mux", "Mx"),
            "Muy": ("Muy", "My"),
        }
        numeric_values: dict[str, float] = {}
        for column, (primary_column, legacy_column) in column_sources.items():
            parsed = _to_float(_load_value(row, primary_column, legacy_column))
            if parsed is None:
                errors.append(f"Row {row_number}: {column} must be numeric.")
                numeric_values[column] = 0.0
            else:
                numeric_values[column] = parsed

        load_type = str(row.get("Load Type") or "ULS").strip()
        if load_type not in LOAD_TYPE_OPTIONS:
            errors.append(f"Row {row_number}: Load Type must be one of {', '.join(LOAD_TYPE_OPTIONS)}.")
            load_type = "Other"

        active = _to_bool(row.get("Active"))
        note_value = row.get("Note")
        note = None if _is_blank(note_value) else str(note_value)

        if any(error.startswith(f"Row {row_number}:") for error in errors):
            continue

        load_cases.append(
            LoadCase(
                name=name,
                Pu_N=_force_to_N(numeric_values["Pu"], force_unit),
                Mux_Nmm=_moment_to_Nmm(numeric_values["Mux"], moment_unit),
                Muy_Nmm=_moment_to_Nmm(numeric_values["Muy"], moment_unit),
                load_type=load_type,
                active=active,
                note=note,
            )
        )

    warnings: list[str] = []
    active_count = sum(1 for load_case in load_cases if load_case.active)
    if load_cases and active_count == 0:
        warnings.append("No active load case is selected.")

    info = [f"{active_count} active load case(s)."]
    return LoadParseResult(load_cases=load_cases, errors=errors, warnings=warnings, info=info)


def load_cases_from_dataframe(df: pd.DataFrame, force_unit: str, moment_unit: str) -> list[LoadCase]:
    result = parse_load_cases_from_dataframe(df, force_unit, moment_unit)
    if result.errors:
        raise ValueError("\n".join(result.errors))
    return result.load_cases


def _preview_dataframe(load_cases: list[LoadCase]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Combo Name": load_case.name,
                "Pu_N": load_case.Pu_N,
                "Mux_Nmm": load_case.Mux_Nmm,
                "Muy_Nmm": load_case.Muy_Nmm,
                "Load Type": load_case.load_type,
                "Active": load_case.active,
            }
            for load_case in load_cases
        ]
    )


def _render_validation_panel(result: LoadParseResult) -> None:
    st.subheader("Load Validation")
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

    for info in result.info:
        st.info(f"INFO: {info}")


def render_loads_page() -> None:
    st.subheader("Loads")
    st.info(
        "Primary PMM capacity checks will use ULS demand values: Pu, Mux, and Muy. "
        "SLS load cases are stored for future serviceability checks but are not checked yet."
    )
    st.info("For current PMM capacity development, use Load Type = ULS.")

    unit_cols = st.columns(2)
    with unit_cols[0]:
        force_unit = st.selectbox("Force unit", FORCE_UNIT_OPTIONS, index=0)
    with unit_cols[1]:
        moment_unit = st.selectbox("Moment unit", MOMENT_UNIT_OPTIONS, index=0)

    if "loads_table" not in st.session_state:
        st.session_state["loads_table"] = _default_load_table()

    edited_df = st.data_editor(
        st.session_state["loads_table"],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active"),
            "Combo Name": st.column_config.TextColumn("Combo Name"),
            "Pu": st.column_config.NumberColumn("Pu (compression +)"),
            "Mux": st.column_config.NumberColumn("Mux"),
            "Muy": st.column_config.NumberColumn("Muy"),
            "Load Type": st.column_config.SelectboxColumn("Load Type", options=LOAD_TYPE_OPTIONS),
            "Note": st.column_config.TextColumn("Note"),
        },
        key="loads_data_editor",
    )
    st.session_state["loads_table"] = edited_df

    result = parse_load_cases_from_dataframe(edited_df, force_unit, moment_unit)
    st.session_state["load_cases"] = result.load_cases if not result.errors else []

    _render_validation_panel(result)

    with st.expander("Sign Convention", expanded=True):
        st.write("- Pu is axial force demand. Compression is positive.")
        st.write("- Mux is moment demand about the x-axis.")
        st.write("- Muy is moment demand about the y-axis.")
        st.write("- x-axis is positive to the right in the section preview.")
        st.write("- y-axis is positive upward in the section preview.")
        st.write("- Positive moments follow the right-hand rule.")
        st.write("- For PMM strength checks, use ULS load combinations.")
        st.write("- SLS load cases are stored for future serviceability checks.")

    st.subheader("Internal Units Preview")
    st.dataframe(_preview_dataframe(st.session_state["load_cases"]), use_container_width=True, hide_index=True)
