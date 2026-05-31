"""Loads tab UI and conversion helpers.

The Loads tab is intentionally paste-friendly: engineers commonly copy factored
load combinations from Excel, CSiBridge, ETABS, or post-processing spreadsheets.
Parsing helpers therefore accept both the current column names and legacy aliases.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

import pandas as pd
import streamlit as st

from concrete_pmm_pro.core.analysis import AnalysisModeSettings
from concrete_pmm_pro.core.analysis_modes import analysis_mode_label
from concrete_pmm_pro.core.models import LoadCase
from concrete_pmm_pro.core.units import kN_to_N, kNm_to_Nmm, tonf_to_N, tonfm_to_Nmm

LOAD_TYPE_OPTIONS = ["ULS", "SLS", "Extreme", "Construction", "Other"]
FORCE_UNIT_OPTIONS = ["kN", "N", "tonf"]
MOMENT_UNIT_OPTIONS = ["kN-m", "N-mm", "tonf-m"]
EDITOR_COLUMNS = ["Active", "Case Name", "Limit State", "Pu", "Mux", "Muy", "Note"]

# LOADS.WORKFLOW1B — workflow-specific table schemas.
# These tables intentionally remain separate from the existing LoadCase PMM
# solver contract.  Column/Pier tables are mapped back to Pu/Mux/Muy for the
# existing PMM workflow; Beam/Girder tables are stored as future-ready data only.
COLUMN_ULS_LOAD_COLUMNS = ["Active", "Case Name", "Pu", "Mux", "Muy", "Vux", "Vuy", "Tu", "Note"]
COLUMN_SLS_LOAD_COLUMNS = ["Active", "Case Name", "P", "Mx", "My", "Note"]
BEAM_ULS_LOAD_COLUMNS = ["Active", "Case Name", "Mux", "Vuy", "Tu", "Muy", "Vux", "Nu", "Note"]
BEAM_SLS_LOAD_COLUMNS = ["Active", "Case Name", "Stage", "Load Component", "Section Basis", "N", "Mx", "My", "Vy", "Vx", "T", "Note"]
# LOADS.SLS2A keeps Load Component as internal/project metadata for backward
# compatibility, but the commercial Beam/Girder SLS editor exposes only the
# check stage.  The component meaning is derived from the selected stage.
BEAM_SLS_EDITOR_COLUMNS = ["Active", "Case Name", "Stage", "Section Basis", "N", "Mx", "My", "Vy", "Vx", "T", "Note"]
# LOADS.SLS2C presents the SLS inputs as stage sub-tabs while keeping one
# backend/project table.  Each tab edits only its own stage rows.
BEAM_SLS_STAGE_EDITOR_COLUMNS = ["Active", "Case Name", "Section Basis", "N", "Mx", "My", "Vy", "Vx", "T", "Note"]
BEAM_STAGE_OPTIONS = [
    "",
    "Transfer stage",
    "Construction stage",
    "Service stage",
    "User-defined",
]
BEAM_LOAD_COMPONENT_OPTIONS = [
    "",
    "Girder self-weight",
    "Girder self-weight + wet deck/topping",
    "Total SLS resultant",
    "User-defined",
]
BEAM_SECTION_BASIS_OPTIONS = ["", "Precast gross", "Composite transformed", "User-defined"]
WORKFLOW_LOAD_TABLE_KEYS = (
    "column_uls_loads_table",
    "column_sls_loads_table",
    "beam_uls_loads_table",
    "beam_sls_loads_table",
)
IMPORT_FILE_TYPES = ["xlsx", "csv"]
LEGACY_COLUMN_RENAMES = {
    "Combo Name": "Case Name",
    "Load Type": "Limit State",
    "Description": "Note",
    "Remarks": "Note",
    "P": "Pu",
    "Axial": "Pu",
    "Mx": "Mux",
    "My": "Muy",
}
LOAD_TYPE_ALIASES = {
    "u": "ULS",
    "uls": "ULS",
    "strength": "ULS",
    "s": "SLS",
    "sls": "SLS",
    "service": "SLS",
    "extreme": "Extreme",
    "ext": "Extreme",
    "construction": "Construction",
    "const": "Construction",
    "other": "Other",
}


@dataclass(frozen=True)
class LoadParseResult:
    load_cases: list[LoadCase]
    errors: list[str]
    warnings: list[str]
    info: list[str]


@dataclass(frozen=True)
class LoadCaseSummary:
    total_rows: int
    valid_rows: int
    active_rows: int
    active_uls_rows: int
    active_sls_rows: int
    inactive_rows: int
    excluded_rows: int



def _analysis_mode_from_session_state() -> AnalysisModeSettings:
    value = st.session_state.get("analysis_mode_settings")
    if isinstance(value, AnalysisModeSettings):
        return value
    if isinstance(value, dict):
        return AnalysisModeSettings.model_validate(value)
    return AnalysisModeSettings()


def _render_load_workflow_notice() -> None:
    settings = _analysis_mode_from_session_state()
    st.info(
        f"Active member workflow: {analysis_mode_label(settings)}. "
        "Loads are entered in workflow-specific ULS and SLS tables. "
        "Column/Pier PMM mode maps ULS/SLS force resultants to the existing Pu/Mux/Muy PMM table analysis contract."
    )
    if settings.member_type == "beam_girder":
        st.caption(
            "Beam/Girder SLS rows can be selected in Analysis for quick preview checks. "
            "ULS rows and full staged summation are stored for future final design checks. "
            "Do not duplicate live-load effects here if an SLS case already includes them."
        )


def _axis_convention_rows() -> list[tuple[str, str]]:
    """Shared section/load action convention for engineering UI text."""

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


def _render_axis_convention_panel() -> None:
    st.markdown("**Axis Convention for Load Tables**")
    st.caption(
        "LOADS.WORKFLOW1 uses explicit x/y/z-axis action names instead of major/minor labels so users do not "
        "have to reinterpret the design axes. Confirm these axes against the section preview before entering loads."
    )
    st.dataframe(pd.DataFrame(_axis_convention_rows(), columns=["Item", "Meaning"]), use_container_width=True, hide_index=True)


def _stringify_table(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    normalized = df.copy()
    for column in columns:
        if column not in normalized.columns:
            normalized[column] = True if column == "Active" else ""
    normalized = normalized[columns].copy()
    normalized["Active"] = normalized["Active"].map(lambda value: _to_bool(value, default=True)).astype(bool)
    for column in columns:
        if column == "Active":
            continue
        normalized[column] = normalized[column].map(lambda value: "" if _is_blank(value) else str(value))
    return normalized



def _dataframes_equal_for_editor(left: pd.DataFrame, right: pd.DataFrame, columns: list[str]) -> bool:
    """Return True when two editor tables are identical after normalization.

    Streamlit's data_editor keeps an internal widget state.  For SelectboxColumn
    cells, persisting the edited dataframe and immediately rerunning avoids the
    confusing behaviour where a dropdown change appears to require a second
    selection before the backing workflow table reflects the new value.
    """

    left_norm = _stringify_table(pd.DataFrame(left), columns).reset_index(drop=True)
    right_norm = _stringify_table(pd.DataFrame(right), columns).reset_index(drop=True)
    return left_norm.equals(right_norm)


def _store_editor_table_and_rerun_on_change(
    state_key: str,
    edited_table: pd.DataFrame,
    previous_table: pd.DataFrame,
    columns: list[str],
) -> None:
    """Persist edited load-table data and rerun once when it changed.

    This is deliberately small and UI-local. It does not change the load schema
    or solver mapping; it only makes dropdown edits in workflow-specific tables
    feel single-click by rebuilding the editor from the updated session state on
    the next run.
    """

    normalized = _stringify_table(pd.DataFrame(edited_table), columns)
    st.session_state[state_key] = normalized
    if not _dataframes_equal_for_editor(previous_table, normalized, columns):
        _sync_workflow_load_tables_metadata()
        st.rerun()

def _beam_sls_stage_label(value: object) -> str:
    """Normalize Beam/Girder SLS rows to the simplified three-stage model."""

    text = "" if _is_blank(value) else str(value).strip()
    cf = text.casefold()
    if not cf:
        return ""
    if "transfer" in cf or "release" in cf:
        return "Transfer stage"
    if "construction" in cf or "deck" in cf or "pre-composite" in cf or "pre composite" in cf or "wet" in cf:
        return "Construction stage"
    if "service" in cf or "final" in cf or "post-composite" in cf or "post composite" in cf or "composite service" in cf:
        return "Service stage"
    if "user" in cf:
        return "User-defined"
    return text


def _beam_sls_component_for_stage(stage: object, existing_component: object = "") -> str:
    """Return the internal component meaning derived from a three-stage SLS row."""

    label = _beam_sls_stage_label(stage)
    if label == "Transfer stage":
        return "Girder self-weight"
    if label == "Construction stage":
        return "Girder self-weight + wet deck/topping"
    if label == "Service stage":
        return "Total SLS resultant"
    if label == "User-defined" and not _is_blank(existing_component):
        return str(existing_component).strip()
    return "" if _is_blank(existing_component) else str(existing_component).strip()


def _beam_sls_basis_for_stage(stage: object, existing_basis: object = "") -> str:
    """Return recommended section basis when a row has no useful basis yet."""

    label = _beam_sls_stage_label(stage)
    existing = "" if _is_blank(existing_basis) else str(existing_basis).strip()
    if existing in {"Precast gross", "Composite transformed", "User-defined"}:
        return existing
    if label in {"Transfer stage", "Construction stage"}:
        return "Precast gross"
    if label == "Service stage":
        return "Composite transformed"
    return existing


def _normalize_beam_sls_load_table(df: pd.DataFrame) -> pd.DataFrame:
    """Return the current Beam/Girder SLS table schema.

    LOADS.SLS2A simplifies the user-facing Beam/Girder SLS workflow to three
    design stages: Transfer, Construction, and Service.  ``Load Component`` is
    retained as hidden/internal metadata so older projects and Analysis guards
    still understand what the row represents, but the editor no longer asks the
    engineer to choose component-by-component rows.
    """

    raw = pd.DataFrame(df).copy() if df is not None else pd.DataFrame(columns=BEAM_SLS_LOAD_COLUMNS)
    if "Stage" not in raw.columns and "Stage / Component" in raw.columns:
        raw["Stage"] = raw["Stage / Component"]
    if "Stage" not in raw.columns:
        raw["Stage"] = ""
    if "Load Component" not in raw.columns:
        raw["Load Component"] = raw.get("Component", "")
        if "Stage / Component" in raw.columns:
            raw["Load Component"] = raw["Load Component"].where(
                ~raw["Load Component"].map(_is_blank),
                "Total SLS resultant",
            )
    raw["Stage"] = raw["Stage"].map(_beam_sls_stage_label)
    raw["Load Component"] = [
        _beam_sls_component_for_stage(stage, component)
        for stage, component in zip(raw["Stage"], raw["Load Component"], strict=False)
    ]
    if "Section Basis" not in raw.columns:
        raw["Section Basis"] = ""
    raw["Section Basis"] = [
        _beam_sls_basis_for_stage(stage, basis)
        for stage, basis in zip(raw["Stage"], raw["Section Basis"], strict=False)
    ]
    return _stringify_table(raw, BEAM_SLS_LOAD_COLUMNS)


def _beam_sls_stage_key(stage_label: str) -> str:
    """Return a stable Streamlit key suffix for one Beam/Girder SLS stage tab."""

    label = _beam_sls_stage_label(stage_label)
    if label == "Transfer stage":
        return "transfer"
    if label == "Construction stage":
        return "construction"
    if label == "Service stage":
        return "service"
    return "user_defined"


def _beam_sls_stage_input_specs() -> list[dict[str, str]]:
    """Commercial three-stage Beam/Girder SLS load-input tabs.

    LOADS.SLS2C aligns Loads with Analysis: engineers input by design stage,
    while the project data remains one normalized SLS load table.
    """

    return [
        {
            "stage": "Transfer stage",
            "title": "Transfer stage",
            "case_name": "SLS-TR",
            "basis": "Precast gross",
            "action": "Precast girder self-weight only",
            "note": "Transfer external action: precast girder self-weight only; include Pe_transfer/initial prestress in Analysis.",
        },
        {
            "stage": "Construction stage",
            "title": "Construction stage",
            "case_name": "SLS-CONST",
            "basis": "Precast gross",
            "action": "Precast girder self-weight + wet deck/topping",
            "note": "Construction action: precast girder self-weight plus wet deck/topping before composite action.",
        },
        {
            "stage": "Service stage",
            "title": "Service stage",
            "case_name": "SLS-SERV",
            "basis": "Composite transformed",
            "action": "Total SLS resultant including SDL and LL+IM",
            "note": "Final service action: total SLS resultant including SDL and LL+IM. Do not include prestress again here.",
        },
    ]


def _beam_sls_stage_spec(stage_label: str) -> dict[str, str]:
    """Return stage-tab metadata, falling back to an engineer-defined stage."""

    normalized = _beam_sls_stage_label(stage_label)
    for spec in _beam_sls_stage_input_specs():
        if spec["stage"] == normalized:
            return spec
    return {
        "stage": normalized or "User-defined",
        "title": normalized or "User-defined",
        "case_name": "SLS-USER",
        "basis": "User-defined",
        "action": "Engineer-defined service action",
        "note": "Engineer-defined SLS action; confirm stage, section basis, and prestress state before relying on preview status.",
    }


def _beam_sls_default_row_for_stage(stage_label: str) -> dict[str, object]:
    """Return one default backend row for a Beam/Girder SLS stage."""

    spec = _beam_sls_stage_spec(stage_label)
    stage = spec["stage"]
    return {
        "Active": True,
        "Case Name": spec["case_name"],
        "Stage": stage,
        "Load Component": _beam_sls_component_for_stage(stage),
        "Section Basis": _beam_sls_basis_for_stage(stage, spec["basis"]),
        "N": 0.0,
        "Mx": 0.0,
        "My": 0.0,
        "Vy": 0.0,
        "Vx": 0.0,
        "T": 0.0,
        "Note": spec["note"],
    }


def _beam_sls_stage_editor_rows(table: pd.DataFrame, stage_label: str) -> pd.DataFrame:
    """Return the editor-visible rows for one Beam/Girder SLS stage tab."""

    normalized = _normalize_beam_sls_load_table(table)
    stage = _beam_sls_stage_label(stage_label)
    stage_rows = normalized[normalized["Stage"].map(_beam_sls_stage_label) == stage].copy()
    if stage_rows.empty:
        stage_rows = pd.DataFrame([_beam_sls_default_row_for_stage(stage)], columns=BEAM_SLS_LOAD_COLUMNS)
    return _stringify_table(stage_rows, BEAM_SLS_STAGE_EDITOR_COLUMNS).reset_index(drop=True)


def _beam_sls_table_after_stage_edit(table: pd.DataFrame, stage_label: str, edited_stage_rows: pd.DataFrame) -> pd.DataFrame:
    """Merge one stage-tab edit back into the single Beam/Girder SLS table.

    The UI is split by stage for clarity, but project storage intentionally
    remains the existing single-table schema so Analysis, save/load, and older
    tests do not need a risky data-model migration.
    """

    stage = _beam_sls_stage_label(stage_label)
    normalized = _normalize_beam_sls_load_table(table)
    keep_rows = normalized[normalized["Stage"].map(_beam_sls_stage_label) != stage].copy()
    edited = _stringify_table(pd.DataFrame(edited_stage_rows), BEAM_SLS_STAGE_EDITOR_COLUMNS)

    new_rows: list[dict[str, object]] = []
    for _, raw_row in edited.iterrows():
        has_case = not _is_blank(raw_row.get("Case Name"))
        has_action = any(not _is_blank(raw_row.get(column)) for column in ("N", "Mx", "My", "Vy", "Vx", "T"))
        has_note = not _is_blank(raw_row.get("Note"))
        if not has_case and not has_action and not has_note:
            continue
        row = {column: raw_row.get(column, "") for column in BEAM_SLS_STAGE_EDITOR_COLUMNS}
        row["Stage"] = stage
        row["Load Component"] = _beam_sls_component_for_stage(stage)
        row["Section Basis"] = _beam_sls_basis_for_stage(stage, row.get("Section Basis"))
        new_rows.append({column: row.get(column, "") for column in BEAM_SLS_LOAD_COLUMNS})

    if not new_rows:
        new_rows.append(_beam_sls_default_row_for_stage(stage))

    merged = pd.concat([keep_rows, pd.DataFrame(new_rows, columns=BEAM_SLS_LOAD_COLUMNS)], ignore_index=True)
    order = {"Transfer stage": 0, "Construction stage": 1, "Service stage": 2, "User-defined": 3}
    merged["__stage_order"] = merged["Stage"].map(lambda value: order.get(_beam_sls_stage_label(value), 99))
    merged = merged.sort_values(["__stage_order", "Case Name"], kind="stable").drop(columns=["__stage_order"])
    return _normalize_beam_sls_load_table(merged)




def _default_column_uls_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-01", "Pu": 1000.0, "Mux": 100.0, "Muy": 50.0, "Vux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Note": "PMM + shear design demand"},
            {"Active": True, "Case Name": "ULS-02", "Pu": 1200.0, "Mux": 120.0, "Muy": 60.0, "Vux": 0.0, "Vuy": 0.0, "Tu": 0.0, "Note": "Alternate ULS combo"},
        ],
        columns=COLUMN_ULS_LOAD_COLUMNS,
    )


def _default_column_sls_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Case Name": "SLS-01", "P": 700.0, "Mx": 70.0, "My": 35.0, "Note": "Service stress resultant"},
        ],
        columns=COLUMN_SLS_LOAD_COLUMNS,
    )


def _default_beam_uls_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-G1", "Mux": 1000.0, "Vuy": 250.0, "Tu": 0.0, "Muy": 0.0, "Vux": 0.0, "Nu": 0.0, "Note": "Flexure/shear/torsion design resultant"},
        ],
        columns=BEAM_ULS_LOAD_COLUMNS,
    )


def _default_beam_sls_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": True,
                "Case Name": "SLS-TR",
                "Stage": "Transfer stage",
                "Load Component": "Girder self-weight",
                "Section Basis": "Precast gross",
                "N": 0.0,
                "Mx": 0.0,
                "My": 0.0,
                "Vy": 0.0,
                "Vx": 0.0,
                "T": 0.0,
                "Note": "Transfer external action: precast girder self-weight only; include Pe_transfer/initial prestress in Analysis.",
            },
            {
                "Active": True,
                "Case Name": "SLS-CONST",
                "Stage": "Construction stage",
                "Load Component": "Girder self-weight + wet deck/topping",
                "Section Basis": "Precast gross",
                "N": 0.0,
                "Mx": 0.0,
                "My": 0.0,
                "Vy": 0.0,
                "Vx": 0.0,
                "T": 0.0,
                "Note": "Construction action: precast girder self-weight plus wet deck/topping before composite action.",
            },
            {
                "Active": True,
                "Case Name": "SLS-SERV",
                "Stage": "Service stage",
                "Load Component": "Total SLS resultant",
                "Section Basis": "Composite transformed",
                "N": 0.0,
                "Mx": 0.0,
                "My": 0.0,
                "Vy": 0.0,
                "Vx": 0.0,
                "T": 0.0,
                "Note": "Final service action: total SLS resultant including SDL and LL+IM. Do not include prestress again here.",
            },
        ],
        columns=BEAM_SLS_LOAD_COLUMNS,
    )


def _split_mixed_editor_table_to_column_tables(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    editor_df = _normalize_editor_dataframe(df)
    uls_rows: list[dict[str, Any]] = []
    sls_rows: list[dict[str, Any]] = []
    for _, row in editor_df.iterrows():
        if _row_is_blank(row):
            continue
        limit_state = _normalize_limit_state(row.get("Limit State")) or str(row.get("Limit State") or "").strip()
        if limit_state == "SLS":
            sls_rows.append(
                {
                    "Active": _to_bool(row.get("Active"), default=True),
                    "Case Name": row.get("Case Name", ""),
                    "P": row.get("Pu", ""),
                    "Mx": row.get("Mux", ""),
                    "My": row.get("Muy", ""),
                    "Note": row.get("Note", ""),
                }
            )
        else:
            uls_rows.append(
                {
                    "Active": _to_bool(row.get("Active"), default=True),
                    "Case Name": row.get("Case Name", ""),
                    "Pu": row.get("Pu", ""),
                    "Mux": row.get("Mux", ""),
                    "Muy": row.get("Muy", ""),
                    "Vux": 0.0,
                    "Vuy": 0.0,
                    "Tu": 0.0,
                    "Note": row.get("Note", ""),
                }
            )
    return (
        _stringify_table(pd.DataFrame(uls_rows) if uls_rows else _default_column_uls_load_table(), COLUMN_ULS_LOAD_COLUMNS),
        _stringify_table(pd.DataFrame(sls_rows) if sls_rows else _default_column_sls_load_table(), COLUMN_SLS_LOAD_COLUMNS),
    )


def _column_workflow_tables_to_legacy_editor_table(uls_df: pd.DataFrame, sls_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    uls_df = _stringify_table(uls_df, COLUMN_ULS_LOAD_COLUMNS)
    sls_df = _stringify_table(sls_df, COLUMN_SLS_LOAD_COLUMNS)
    for _, row in uls_df.iterrows():
        rows.append(
            {
                "Active": _to_bool(row.get("Active"), default=True),
                "Case Name": row.get("Case Name", ""),
                "Limit State": "ULS",
                "Pu": row.get("Pu", ""),
                "Mux": row.get("Mux", ""),
                "Muy": row.get("Muy", ""),
                "Note": row.get("Note", ""),
            }
        )
    for _, row in sls_df.iterrows():
        rows.append(
            {
                "Active": _to_bool(row.get("Active"), default=True),
                "Case Name": row.get("Case Name", ""),
                "Limit State": "SLS",
                "Pu": row.get("P", ""),
                "Mux": row.get("Mx", ""),
                "Muy": row.get("My", ""),
                "Note": row.get("Note", ""),
            }
        )
    return _normalize_editor_dataframe(pd.DataFrame(rows, columns=EDITOR_COLUMNS))


def _ensure_workflow_load_tables_initialized() -> None:
    if "column_uls_loads_table" not in st.session_state or "column_sls_loads_table" not in st.session_state:
        uls_df, sls_df = _split_mixed_editor_table_to_column_tables(st.session_state.get("loads_table", _default_load_table()))
        st.session_state.setdefault("column_uls_loads_table", uls_df)
        st.session_state.setdefault("column_sls_loads_table", sls_df)
    if "beam_uls_loads_table" not in st.session_state:
        st.session_state["beam_uls_loads_table"] = _default_beam_uls_load_table()
    if "beam_sls_loads_table" not in st.session_state:
        st.session_state["beam_sls_loads_table"] = _default_beam_sls_load_table()


def _sync_workflow_load_tables_metadata() -> None:
    metadata = dict(st.session_state.get("project_metadata", {}) or {})
    workflow_tables: dict[str, list[dict[str, Any]]] = {}
    for key in WORKFLOW_LOAD_TABLE_KEYS:
        value = st.session_state.get(key)
        if value is None:
            continue
        workflow_tables[key] = pd.DataFrame(value).to_dict(orient="records")
    if workflow_tables:
        metadata["workflow_load_tables"] = workflow_tables
        st.session_state["project_metadata"] = metadata


def _workflow_table_result(df: pd.DataFrame, *, table_name: str, numeric_columns: list[str]) -> LoadParseResult:
    errors: list[str] = []
    warnings: list[str] = []
    seen_names: set[str] = set()
    nonblank_rows = 0
    active_rows = 0
    valid_rows: list[LoadCase] = []
    for index, row in df.iterrows():
        row_number = int(index) + 1
        if _is_blank(row.get("Case Name")) and all(_is_blank(row.get(column)) for column in numeric_columns):
            continue
        nonblank_rows += 1
        name = str(row.get("Case Name") or "").strip()
        if not name:
            errors.append(f"{table_name} row {row_number}: Case Name cannot be blank.")
            continue
        name_key = name.lower()
        if name_key in seen_names:
            errors.append(f"{table_name} row {row_number}: Duplicate Case Name = {name}.")
            continue
        seen_names.add(name_key)
        for column in numeric_columns:
            if _to_float(row.get(column)) is None:
                errors.append(f"{table_name} row {row_number}: {column} must be numeric.")
        if _to_bool(row.get("Active"), default=True):
            active_rows += 1
        valid_rows.append(LoadCase(name=name, active=_to_bool(row.get("Active"), default=True), load_type="Other"))
    if nonblank_rows and active_rows == 0:
        warnings.append(f"{table_name}: no active rows are selected.")
    return LoadParseResult(
        load_cases=valid_rows,
        errors=errors,
        warnings=warnings,
        info=[f"{table_name}: {active_rows} active row(s), {nonblank_rows} non-blank row(s)."],
    )


def _beam_sls_stage_basis_warnings(df: pd.DataFrame) -> list[str]:
    """Return engineering guidance warnings for Beam/Girder SLS stage rows.

    LOADS.SLS2A uses a commercial three-stage input model rather than making
    the engineer choose detailed load components in the default editor.  The
    guard now checks whether each stage uses the expected section basis while
    treating the Service-stage Total SLS resultant as the normal intended input
    for quick/final-service preview.
    """

    table = _normalize_beam_sls_load_table(df)
    warnings: list[str] = []
    for index, row in table.iterrows():
        if not _to_bool(row.get("Active"), default=True):
            continue
        if _is_blank(row.get("Case Name")) and all(_is_blank(row.get(column)) for column in ("N", "Mx", "My", "Vy", "Vx", "T")):
            continue

        row_number = int(index) + 1
        case_name = str(row.get("Case Name") or f"Row {row_number}").strip() or f"Row {row_number}"
        stage = _beam_sls_stage_label(row.get("Stage"))
        basis = str(row.get("Section Basis") or "").strip()
        prefix = f"Beam/Girder SLS row {row_number} ({case_name})"

        if stage in {"Transfer stage", "Construction stage"} and basis == "Composite transformed":
            warnings.append(
                f"{prefix}: {stage} should normally use the Precast gross section basis. "
                "Composite transformed properties are normally for final service after composite action."
            )
        if stage == "Service stage" and basis == "Precast gross":
            warnings.append(
                f"{prefix}: Service stage normally uses the Composite transformed section basis when deck/topping composite metadata is active."
            )
        if stage == "Transfer stage":
            note = str(row.get("Note") or "").casefold()
            if "prestress" not in note and "pe_transfer" not in note:
                warnings.append(
                    f"{prefix}: transfer stress must include Pe_transfer / initial prestress in Analysis; "
                    "the Loads row should contain only external girder self-weight action."
                )

    return warnings


def _default_load_table() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-01", "Limit State": "ULS", "Pu": 1000.0, "Mux": 100.0, "Muy": 50.0, "Note": ""},
            {"Active": True, "Case Name": "ULS-02", "Limit State": "ULS", "Pu": 1200.0, "Mux": 120.0, "Muy": 60.0, "Note": ""},
            {"Active": True, "Case Name": "SLS-01", "Limit State": "SLS", "Pu": 700.0, "Mux": 70.0, "Muy": 35.0, "Note": ""},
        ],
        columns=EDITOR_COLUMNS,
    )


def _excel_template_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Active": True, "Case Name": "ULS-01", "Limit State": "ULS", "Pu": 2500, "Mux": 120, "Muy": -350, "Note": "Governing strength combo"},
            {"Active": True, "Case Name": "ULS-02", "Limit State": "ULS", "Pu": 1800, "Mux": -95, "Muy": 410, "Note": "Alternate biaxial combo"},
            {"Active": True, "Case Name": "SLS-01", "Limit State": "SLS", "Pu": 1500, "Mux": 70, "Muy": -220, "Note": "Service stress combo"},
        ],
        columns=EDITOR_COLUMNS,
    )


def _excel_template_bytes() -> bytes:
    """Return an XLSX load import template for users to fill in Excel."""
    output = BytesIO()
    template = _excel_template_dataframe()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        template.to_excel(writer, sheet_name="Load Cases", index=False)
        guide = pd.DataFrame(
            [
                {"Field": "Active", "Instruction": "TRUE/FALSE. Blank is treated as TRUE during import."},
                {"Field": "Case Name", "Instruction": "Required unique load case or combination name."},
                {"Field": "Limit State", "Instruction": "Use ULS or SLS. Aliases such as Strength/Service are normalized."},
                {"Field": "Pu", "Instruction": "Axial force in the selected Force unit. Compression is positive."},
                {"Field": "Mux", "Instruction": "Moment about x-axis in the selected Moment unit."},
                {"Field": "Muy", "Instruction": "Moment about y-axis in the selected Moment unit."},
                {"Field": "Note", "Instruction": "Optional. Not used in calculation."},
            ]
        )
        guide.to_excel(writer, sheet_name="Instructions", index=False)
    return output.getvalue()


def _read_uploaded_load_table(uploaded_file: Any) -> pd.DataFrame:
    """Read a CSV/XLSX upload into a raw dataframe for validation.

    The parser is intentionally tolerant about column aliases; validation happens
    later in ``parse_load_cases_from_dataframe`` so users can preview and fix
    errors before applying imported rows to the live table.
    """
    if uploaded_file is None:
        return pd.DataFrame(columns=EDITOR_COLUMNS)

    filename = str(getattr(uploaded_file, "name", "")).lower()
    if filename.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file, sheet_name=0)
    raise ValueError("Unsupported load import file type. Please upload .xlsx or .csv.")


def prepare_imported_load_table(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize imported load rows for the editable load table.

    This function is shared by UI code and tests. It preserves the canonical
    editor columns and keeps Pu/Mux/Muy as text so thousands separators or unit
    suffixes remain paste/import friendly until validation parses them.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=EDITOR_COLUMNS)

    # Determine blank rows before normalization. Normalization intentionally
    # defaults blank Limit State to ULS and Active to True, which would make
    # purely blank Excel-formatting rows look non-blank if checked afterwards.
    raw_keep_mask = [not _row_is_blank(row) for _, row in df.iterrows()]
    if not any(raw_keep_mask):
        return pd.DataFrame(columns=EDITOR_COLUMNS)

    raw_nonblank = df.loc[raw_keep_mask].copy()
    normalized = _normalize_editor_dataframe(raw_nonblank)
    return normalized[EDITOR_COLUMNS].reset_index(drop=True)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _row_is_blank(row: pd.Series) -> bool:
    columns = [
        "Case Name",
        "Combo Name",
        "Pu",
        "Pu_kN",
        "Pu_N",
        "Mux",
        "Mux_kNm",
        "Mux_Nmm",
        "Muy",
        "Muy_kNm",
        "Muy_Nmm",
        "Mx",
        "My",
        "Limit State",
        "Load Type",
        "Note",
        "Description",
        "Remarks",
    ]
    return all(_is_blank(row.get(column)) for column in columns)


def _clean_number_text(value: Any) -> str:
    text = str(value).strip()
    # Common Excel exports may include thousands separators, non-breaking spaces,
    # or unit suffixes copied with the value. Keep this conservative so invalid
    # engineering inputs are still caught by validation.
    text = text.replace("\u00a0", "").replace(" ", "").replace(",", "")
    for suffix in ("kN-m", "kNm", "N-mm", "Nmm", "tonf-m", "tonfm", "kN", "N", "tonf"):
        if text.lower().endswith(suffix.lower()):
            text = text[: -len(suffix)]
            break
    return text


def _to_float(value: Any) -> float | None:
    if _is_blank(value):
        return 0.0
    try:
        return float(_clean_number_text(value))
    except (TypeError, ValueError):
        return None


def _to_bool(value: Any, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if _is_blank(value):
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "active", "ใช้", "ใช่"}:
        return True
    if text in {"false", "0", "no", "n", "inactive", "ไม่ใช้", "ไม่"}:
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


def _load_value(row: pd.Series, candidates: list[str]) -> Any:
    for column in candidates:
        if column in row.index and not _is_blank(row.get(column)):
            return row.get(column)
    return None


def _normalize_limit_state(value: Any) -> str | None:
    if _is_blank(value):
        return "ULS"
    text = str(value).strip()
    if text in LOAD_TYPE_OPTIONS:
        return text
    return LOAD_TYPE_ALIASES.get(text.lower())


def _normalize_editor_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Return a paste-friendly editor table with current column names.

    This keeps old session-state tables working after the UI rename from
    ``Combo Name``/``Load Type`` to ``Case Name``/``Limit State``.
    """
    if df is None or df.empty:
        return _default_load_table()

    normalized = df.copy()
    for old_name, new_name in LEGACY_COLUMN_RENAMES.items():
        if old_name in normalized.columns and new_name not in normalized.columns:
            normalized[new_name] = normalized[old_name]

    for column in EDITOR_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = True if column == "Active" else ""

    normalized = normalized[EDITOR_COLUMNS].copy()
    normalized["Active"] = normalized["Active"].map(lambda value: _to_bool(value, default=True)).astype(bool)
    normalized["Case Name"] = normalized["Case Name"].map(lambda value: "" if _is_blank(value) else str(value))
    normalized["Limit State"] = normalized["Limit State"].map(lambda value: _normalize_limit_state(value) or str(value).strip())
    # Pu/Mux/Muy intentionally use TextColumn in st.data_editor so pasted Excel
    # values such as "1,250" or "2500 kN" can be accepted and validated
    # by the parser. Streamlit requires TextColumn to receive string/object dtype,
    # so coerce numeric defaults/session-state values before rendering.
    for numeric_column in ("Pu", "Mux", "Muy"):
        normalized[numeric_column] = normalized[numeric_column].map(lambda value: "" if _is_blank(value) else str(value))
    normalized["Note"] = normalized["Note"].map(lambda value: "" if _is_blank(value) else str(value))
    return normalized


def _load_case_summary(load_cases: list[LoadCase], errors: list[str], total_rows: int) -> LoadCaseSummary:
    active_rows = sum(1 for load_case in load_cases if load_case.active)
    active_uls_rows = sum(1 for load_case in load_cases if load_case.active and load_case.load_type == "ULS")
    active_sls_rows = sum(1 for load_case in load_cases if load_case.active and load_case.load_type == "SLS")
    inactive_rows = sum(1 for load_case in load_cases if not load_case.active)
    excluded_rows = len({error.split(":", 1)[0] for error in errors if error.startswith("Row ")})
    return LoadCaseSummary(
        total_rows=total_rows,
        valid_rows=len(load_cases),
        active_rows=active_rows,
        active_uls_rows=active_uls_rows,
        active_sls_rows=active_sls_rows,
        inactive_rows=inactive_rows,
        excluded_rows=excluded_rows,
    )


def parse_load_cases_from_dataframe(df: pd.DataFrame, force_unit: str, moment_unit: str) -> LoadParseResult:
    errors: list[str] = []
    warnings: list[str] = []
    load_cases: list[LoadCase] = []
    seen_names: set[str] = set()
    nonblank_rows = 0

    for index, row in df.iterrows():
        row_number = int(index) + 1
        if _row_is_blank(row):
            continue
        nonblank_rows += 1

        name_value = _load_value(row, ["Case Name", "Combo Name", "Name"])
        if _is_blank(name_value):
            errors.append(f"Row {row_number}: Case Name cannot be blank.")
            continue
        name = str(name_value).strip()
        name_key = name.lower()
        if name_key in seen_names:
            errors.append(f"Row {row_number}: Duplicate Case Name = {name}.")
            continue
        seen_names.add(name_key)

        numeric_sources = {
            "Pu": ["Pu", "Pu_kN", "Pu_N", "P", "Axial"],
            "Mux": ["Mux", "Mux_kNm", "Mux_Nmm", "Mx", "Mx_kNm", "Mx_Nmm"],
            "Muy": ["Muy", "Muy_kNm", "Muy_Nmm", "My", "My_kNm", "My_Nmm"],
        }
        numeric_values: dict[str, float] = {}
        for column, candidates in numeric_sources.items():
            raw_value = _load_value(row, candidates)
            parsed = _to_float(raw_value)
            if parsed is None:
                errors.append(f"Row {row_number}: {column} must be numeric.")
                numeric_values[column] = 0.0
            else:
                numeric_values[column] = parsed

        limit_state_value = _load_value(row, ["Limit State", "Load Type", "Type"])
        load_type = _normalize_limit_state(limit_state_value)
        if load_type is None:
            errors.append(f"Row {row_number}: Limit State must be one of {', '.join(LOAD_TYPE_OPTIONS)}.")
            load_type = "Other"

        active = _to_bool(row.get("Active"), default=True)
        note_value = _load_value(row, ["Note", "Description", "Remarks"])
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

    active_count = sum(1 for load_case in load_cases if load_case.active)
    active_uls_count = sum(1 for load_case in load_cases if load_case.active and load_case.load_type == "ULS")
    active_sls_count = sum(1 for load_case in load_cases if load_case.active and load_case.load_type == "SLS")
    if load_cases and active_count == 0:
        warnings.append("No active load case is selected.")
    if load_cases and active_uls_count == 0:
        warnings.append("No active ULS load case is available for PMM strength demand/capacity checks.")

    info = [
        f"{active_count} active load case(s).",
        f"{active_uls_count} active ULS case(s) used by strength checks; {active_sls_count} active SLS case(s) stored for service checks.",
    ]
    if errors:
        info.append("Rows with validation errors are excluded from analysis until corrected.")
    if nonblank_rows == 0:
        info.append("No non-blank load rows found.")
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
                "Case Name": load_case.name,
                "Pu_N": load_case.Pu_N,
                "Mux_Nmm": load_case.Mux_Nmm,
                "Muy_Nmm": load_case.Muy_Nmm,
                "Limit State": load_case.load_type,
                "Active": load_case.active,
            }
            for load_case in load_cases
        ]
    )


def _valid_load_cases_dataframe(load_cases: list[LoadCase], force_unit: str, moment_unit: str) -> pd.DataFrame:
    def from_internal_force(value_n: float) -> float:
        if force_unit == "kN":
            return value_n / 1000.0
        if force_unit == "N":
            return value_n
        if force_unit == "tonf":
            return value_n / 9806.65
        return value_n

    def from_internal_moment(value_nmm: float) -> float:
        if moment_unit == "kN-m":
            return value_nmm / 1_000_000.0
        if moment_unit == "N-mm":
            return value_nmm
        if moment_unit == "tonf-m":
            return value_nmm / 9_806_650.0
        return value_nmm

    return pd.DataFrame(
        [
            {
                "Active": load_case.active,
                "Case Name": load_case.name,
                "Limit State": load_case.load_type,
                f"Pu ({force_unit})": from_internal_force(load_case.Pu_N),
                f"Mux ({moment_unit})": from_internal_moment(load_case.Mux_Nmm),
                f"Muy ({moment_unit})": from_internal_moment(load_case.Muy_Nmm),
                "Note": load_case.note or "",
            }
            for load_case in load_cases
        ]
    )


def _render_summary_metrics(result: LoadParseResult, total_rows: int) -> None:
    summary = _load_case_summary(result.load_cases, result.errors, total_rows)
    cols = st.columns(5)
    cols[0].metric("Valid cases", summary.valid_rows, help="Valid load cases after validation.")
    cols[1].metric("Active ULS", summary.active_uls_rows, help="Active ULS cases used by PMM strength demand/capacity checks.")
    cols[2].metric("Active SLS", summary.active_sls_rows, help="Active SLS cases stored for serviceability checks.")
    cols[3].metric("Inactive", summary.inactive_rows, help="Valid rows with Active unchecked.")
    cols[4].metric("Excluded", summary.excluded_rows, help="Non-blank rows excluded due to validation errors.")


def _render_validation_panel(result: LoadParseResult) -> None:
    st.subheader("Load Validation")
    st.caption("Only valid active load cases are used by analysis. Invalid or inactive rows are excluded.")
    if result.errors:
        with st.expander("Rows Excluded from Analysis", expanded=True):
            for error in result.errors:
                st.error(error)
    else:
        st.success("No validation errors")

    if result.warnings:
        for warning in result.warnings:
            st.warning(warning)

    for info in result.info:
        st.info(info)


def _render_load_template_downloads() -> None:
    st.markdown("**Recommended workflow: Download template → fill in Excel → upload → preview → apply**")
    st.caption(
        "Use this workflow for reliable load import from Excel, CSiBridge, ETABS, or post-processing spreadsheets. "
        "The table editor below remains available for final manual edits."
    )
    template = _excel_template_dataframe()
    st.dataframe(template, use_container_width=True, hide_index=True)

    cols = st.columns(2)
    with cols[0]:
        st.download_button(
            "Download Excel load template",
            data=_excel_template_bytes(),
            file_name="concrete_pmm_load_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with cols[1]:
        st.download_button(
            "Download CSV load template",
            data=template.to_csv(index=False).encode("utf-8"),
            file_name="concrete_pmm_load_template.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _render_load_import_workflow(force_unit: str, moment_unit: str) -> None:
    st.markdown("**Import Load Cases from Excel / CSV**")
    st.caption(
        "Upload a completed template or compatible load table, preview validation, then apply it to the editable load table. "
        "Applying replaces the current load table so accidental partial paste errors are avoided."
    )
    uploaded_file = st.file_uploader(
        "Upload completed load template",
        type=IMPORT_FILE_TYPES,
        help="Supported files: .xlsx or .csv. The first sheet is read for Excel files.",
        key="loads_import_file",
    )
    if uploaded_file is None:
        return

    try:
        imported_raw = _read_uploaded_load_table(uploaded_file)
        imported_editor = prepare_imported_load_table(imported_raw)
    except Exception as exc:  # pragma: no cover - UI guardrail
        st.error(f"Could not read load import file: {exc}")
        return

    if imported_editor.empty:
        st.warning("The uploaded file does not contain any non-blank load rows.")
        return

    result = parse_load_cases_from_dataframe(imported_editor, force_unit, moment_unit)
    st.markdown("**Import Preview**")
    st.caption("Preview of rows that will be applied to the Load Case Input Table after normalization.")
    st.dataframe(imported_editor, use_container_width=True, hide_index=True)
    _render_summary_metrics(result, total_rows=len(imported_editor))

    if result.errors:
        with st.expander("Import Rows Excluded from Analysis", expanded=True):
            for error in result.errors:
                st.error(error)
        st.warning("Fix the highlighted import errors before applying this file to the load table.")
        apply_disabled = True
    else:
        st.success("Import validation passed. You can apply these rows to the load table.")
        apply_disabled = False

    if st.button("Apply imported loads to table", type="primary", use_container_width=True, disabled=apply_disabled):
        st.session_state["loads_table"] = imported_editor.copy()
        st.session_state.pop("loads_data_editor", None)
        st.success("Imported load cases applied to the editable load table.")
        st.rerun()


def _render_column_load_tables(force_unit: str, moment_unit: str) -> None:
    st.markdown("### Column / Pier / Wall / Pylon Loads")
    st.caption(
        "ULS and SLS loads are separated so PMM strength, shear demand, and service stress resultants are not mixed. "
        "Only Pu/Mux/Muy from active ULS rows are passed to the existing PMM demand/capacity workflow."
    )

    with st.expander("Excel / CSV load template", expanded=False):
        st.caption("The current import template maps to the Column/Pier PMM workflow and will be split into ULS/SLS tables.")
        _render_load_template_downloads()

    with st.expander("Import Column/Pier Load Cases from Excel / CSV", expanded=False):
        st.caption("Imported Pu/Mux/Muy rows are split by Limit State into the workflow-specific ULS and SLS tables.")
        uploaded_file = st.file_uploader(
            "Upload completed Column/Pier load template",
            type=IMPORT_FILE_TYPES,
            help="Supported files: .xlsx or .csv. The first sheet is read for Excel files.",
            key="column_loads_import_file",
        )
        if uploaded_file is not None:
            try:
                imported_raw = _read_uploaded_load_table(uploaded_file)
                imported_editor = prepare_imported_load_table(imported_raw)
                imported_uls, imported_sls = _split_mixed_editor_table_to_column_tables(imported_editor)
            except Exception as exc:  # pragma: no cover - UI guardrail
                st.error(f"Could not read load import file: {exc}")
            else:
                result = parse_load_cases_from_dataframe(imported_editor, force_unit, moment_unit)
                st.dataframe(imported_editor, use_container_width=True, hide_index=True)
                _render_summary_metrics(result, total_rows=len(imported_editor))
                if result.errors:
                    st.warning("Fix import validation errors before applying this file.")
                    with st.expander("Import Rows Excluded from Analysis", expanded=True):
                        for error in result.errors:
                            st.error(error)
                elif st.button("Apply imported loads to Column/Pier ULS/SLS tables", type="primary", use_container_width=True):
                    st.session_state["column_uls_loads_table"] = imported_uls
                    st.session_state["column_sls_loads_table"] = imported_sls
                    st.session_state.pop("column_uls_loads_editor", None)
                    st.session_state.pop("column_sls_loads_editor", None)
                    st.success("Imported loads applied to workflow-specific Column/Pier tables.")
                    st.rerun()

    st.markdown("#### ULS PMM / Shear Loads")
    st.caption(
        "Use factored loads. PMM checks use Pu, Mux, and Muy. Vux, Vuy, and Tu are stored for future shear/torsion design."
    )
    uls_df = _stringify_table(pd.DataFrame(st.session_state.get("column_uls_loads_table")), COLUMN_ULS_LOAD_COLUMNS)
    edited_uls = st.data_editor(
        uls_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active"),
            "Case Name": st.column_config.TextColumn("Case Name"),
            "Pu": st.column_config.TextColumn(f"Pu ({force_unit}, compression +)", help="Factored axial force for PMM. Compression is positive."),
            "Mux": st.column_config.TextColumn(f"Mux ({moment_unit})", help="Factored moment about x-axis for PMM."),
            "Muy": st.column_config.TextColumn(f"Muy ({moment_unit})", help="Factored moment about y-axis for PMM."),
            "Vux": st.column_config.TextColumn(f"Vux ({force_unit})", help="Factored shear in x-direction for future shear design."),
            "Vuy": st.column_config.TextColumn(f"Vuy ({force_unit})", help="Factored shear in y-direction for future shear design."),
            "Tu": st.column_config.TextColumn(f"Tu ({moment_unit})", help="Factored torsion about member longitudinal axis. Future design use."),
            "Note": st.column_config.TextColumn("Note"),
        },
        key="column_uls_loads_editor",
    )
    edited_uls = _stringify_table(edited_uls, COLUMN_ULS_LOAD_COLUMNS)
    st.session_state["column_uls_loads_table"] = edited_uls

    st.markdown("#### SLS Stress Loads")
    st.caption("Use service-level resultants for elastic SLS stress checks. Do not enter live load separately if this SLS case already includes it.")
    sls_df = _stringify_table(pd.DataFrame(st.session_state.get("column_sls_loads_table")), COLUMN_SLS_LOAD_COLUMNS)
    edited_sls = st.data_editor(
        sls_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active"),
            "Case Name": st.column_config.TextColumn("Case Name"),
            "P": st.column_config.TextColumn(f"P ({force_unit}, compression +)", help="Service axial force. Compression is positive."),
            "Mx": st.column_config.TextColumn(f"Mx ({moment_unit})", help="Service moment about x-axis."),
            "My": st.column_config.TextColumn(f"My ({moment_unit})", help="Service moment about y-axis."),
            "Note": st.column_config.TextColumn("Note"),
        },
        key="column_sls_loads_editor",
    )
    edited_sls = _stringify_table(edited_sls, COLUMN_SLS_LOAD_COLUMNS)
    st.session_state["column_sls_loads_table"] = edited_sls

    legacy_editor = _column_workflow_tables_to_legacy_editor_table(edited_uls, edited_sls)
    st.session_state["loads_table"] = legacy_editor
    result = parse_load_cases_from_dataframe(legacy_editor, force_unit, moment_unit)
    st.session_state["load_cases"] = result.load_cases
    _sync_workflow_load_tables_metadata()

    nonblank_count = sum(0 if _row_is_blank(row) else 1 for _, row in legacy_editor.iterrows())
    _render_summary_metrics(result, total_rows=nonblank_count)
    _render_validation_panel(result)

    with st.expander("Valid Column/Pier Load Cases Used by Analysis", expanded=True):
        st.caption("Existing PMM/SLS analysis still receives valid active rows converted to Pu/Mux/Muy internal resultants.")
        st.dataframe(_valid_load_cases_dataframe(result.load_cases, force_unit, moment_unit), use_container_width=True, hide_index=True)

    with st.expander("Internal Units Preview", expanded=False):
        st.caption("Internal solver units are N and N-mm. Shear/torsion columns are stored for future design but not passed to PMM yet.")
        st.dataframe(_preview_dataframe(st.session_state["load_cases"]), use_container_width=True, hide_index=True)


def _render_beam_girder_load_tables(force_unit: str, moment_unit: str) -> None:
    st.markdown("### Beam / Girder Loads")
    st.caption(
        "Beam/Girder load tables use explicit section-axis names: Mux is main vertical bending for typical girders and Vuy is vertical shear. "
        "SLS rows can be selected in Analysis for quick preview checks; ULS rows and full staged summation remain future final-design workflows."
    )
    status_cols = st.columns(4)
    status_cols[0].metric("Workflow", "Beam/Girder")
    status_cols[1].metric("Load model", "ULS + SLS")
    status_cols[2].metric("SLS Analysis", "Preview selectable")
    status_cols[3].metric("Final staged check", "Future")

    st.markdown("#### ULS Girder Design Loads")
    st.caption("Use factored resultants for future flexural, shear, and torsion design. Mux, Vuy, and Tu are the primary girder ULS actions.")
    uls_df = _stringify_table(pd.DataFrame(st.session_state.get("beam_uls_loads_table")), BEAM_ULS_LOAD_COLUMNS)
    edited_uls = st.data_editor(
        uls_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active"),
            "Case Name": st.column_config.TextColumn("Case Name"),
            "Mux": st.column_config.TextColumn(f"Mux ({moment_unit})", help="Factored main bending about x-axis."),
            "Vuy": st.column_config.TextColumn(f"Vuy ({force_unit})", help="Factored vertical shear in y-direction."),
            "Tu": st.column_config.TextColumn(f"Tu ({moment_unit})", help="Factored torsion about member longitudinal axis."),
            "Muy": st.column_config.TextColumn(f"Muy ({moment_unit})", help="Optional lateral/minor bending about y-axis."),
            "Vux": st.column_config.TextColumn(f"Vux ({force_unit})", help="Optional lateral shear in x-direction."),
            "Nu": st.column_config.TextColumn(f"Nu ({force_unit})", help="Optional axial force for special girder/frame action."),
            "Note": st.column_config.TextColumn("Note"),
        },
        key="beam_uls_loads_editor",
    )
    edited_uls = _stringify_table(edited_uls, BEAM_ULS_LOAD_COLUMNS)
    st.session_state["beam_uls_loads_table"] = edited_uls

    st.markdown("#### SLS Girder Service Loads")
    st.caption(
        "LOADS.SLS2C aligns this input area with Analysis: enter service actions by stage, not by detailed load-component dropdown. "
        "N and Mx are currently the primary elastic stress inputs; My, Vy, Vx, and T are stored for future checks."
    )
    st.info(
        "Stage meaning: Transfer = precast girder self-weight + Pe_transfer in Analysis; "
        "Construction = precast girder + wet deck/topping; Service = total SLS resultant including SDL and LL+IM. "
        "Do not include prestress in the Loads resultant when Pe is added separately in Analysis."
    )

    stage_tabs = st.tabs([spec["title"] for spec in _beam_sls_stage_input_specs()])
    for spec, tab in zip(_beam_sls_stage_input_specs(), stage_tabs, strict=False):
        stage_label = spec["stage"]
        stage_key = _beam_sls_stage_key(stage_label)
        with tab:
            stage_cols = st.columns(3)
            stage_cols[0].metric("Check stage", spec["title"])
            stage_cols[0].caption(spec["action"])
            stage_cols[1].metric("Recommended section basis", spec["basis"])
            stage_cols[1].caption("Analysis tab uses the same stage routing.")
            stage_cols[2].metric("Prestress handling", "Added in Analysis")
            stage_cols[2].caption("Do not include prestress in the external load resultant when Pe is added separately.")
            st.caption(spec["note"])
            current_sls_table = _normalize_beam_sls_load_table(pd.DataFrame(st.session_state.get("beam_sls_loads_table")))
            stage_editor_df = _beam_sls_stage_editor_rows(current_sls_table, stage_label)
            edited_stage = st.data_editor(
                stage_editor_df,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Active": st.column_config.CheckboxColumn("Active"),
                    "Case Name": st.column_config.TextColumn("Case Name"),
                    "Section Basis": st.column_config.SelectboxColumn(
                        "Section Basis",
                        options=BEAM_SECTION_BASIS_OPTIONS,
                        help="Recommended: Precast gross for Transfer/Construction; Composite transformed for Service.",
                    ),
                    "N": st.column_config.TextColumn(f"N ({force_unit}, compression +)", help="Service axial force. Compression is positive."),
                    "Mx": st.column_config.TextColumn(f"Mx ({moment_unit})", help="Service moment about x-axis. Sagging positive in girder SLS convention."),
                    "My": st.column_config.TextColumn(f"My ({moment_unit})", help="Optional service moment about y-axis."),
                    "Vy": st.column_config.TextColumn(f"Vy ({force_unit})", help="Optional vertical shear for future service shear/principal stress checks."),
                    "Vx": st.column_config.TextColumn(f"Vx ({force_unit})", help="Optional lateral shear in x-direction for future checks."),
                    "T": st.column_config.TextColumn(f"T ({moment_unit})", help="Optional service torsion for future torsion cracking checks."),
                    "Note": st.column_config.TextColumn("Note"),
                },
                key=f"beam_sls_{stage_key}_loads_editor",
            )
            merged_sls_table = _beam_sls_table_after_stage_edit(current_sls_table, stage_label, edited_stage)
            _store_editor_table_and_rerun_on_change(
                "beam_sls_loads_table",
                merged_sls_table,
                current_sls_table,
                BEAM_SLS_LOAD_COLUMNS,
            )

    edited_sls = _normalize_beam_sls_load_table(pd.DataFrame(st.session_state.get("beam_sls_loads_table")))

    with st.expander("Combined SLS backend table used by Analysis", expanded=False):
        st.caption(
            "The UI is split into Transfer, Construction, and Service tabs, but Analysis and project save/load still use one normalized backend table."
        )
        st.dataframe(edited_sls, use_container_width=True, hide_index=True)

    stage_basis_warnings = _beam_sls_stage_basis_warnings(edited_sls)
    if stage_basis_warnings:
        with st.expander("SLS stage / section-basis guidance", expanded=True):
            for warning in stage_basis_warnings:
                st.warning(warning)

    uls_result = _workflow_table_result(edited_uls, table_name="Beam/Girder ULS", numeric_columns=["Mux", "Vuy", "Tu", "Muy", "Vux", "Nu"])
    sls_result = _workflow_table_result(edited_sls, table_name="Beam/Girder SLS", numeric_columns=["N", "Mx", "My", "Vy", "Vx", "T"])
    cols = st.columns(4)
    cols[0].metric("ULS rows", len(uls_result.load_cases))
    cols[1].metric("SLS rows", len(sls_result.load_cases))
    cols[2].metric("ULS errors", len(uls_result.errors))
    cols[3].metric("SLS errors", len(sls_result.errors))
    for result in (uls_result, sls_result):
        if result.errors:
            for error in result.errors:
                st.error(error)
        for warning in result.warnings:
            st.warning(warning)
        for info in result.info:
            st.info(info)

    with st.expander("Beam/Girder load table scope", expanded=False):
        st.write("- ULS table prepares actions for future flexure, shear, and torsion design.")
        st.write("- SLS table uses three engineer-facing stages instead of a detailed Load Component dropdown.")
        st.write("- Transfer stage: external action is precast girder self-weight; Analysis must include Pe_transfer/initial prestress for a meaningful transfer check.")
        st.write("- Construction stage: external action is precast girder plus wet deck/topping before composite action.")
        st.write("- Service stage: external action is the Total SLS resultant including SDL and LL+IM; do not include prestress again if Analysis adds Pe separately.")
        st.write("- ULS rows and full staged summation are not yet connected to final code-certified girder design.")

def render_loads_page() -> None:
    st.subheader("Loads")
    st.caption("Workflow-based ULS/SLS load input for PMM and future Beam/Girder design workflows.")

    _ensure_workflow_load_tables_initialized()
    _render_load_workflow_notice()

    unit_cols = st.columns(2)
    with unit_cols[0]:
        force_unit = st.selectbox(
            "Force unit",
            FORCE_UNIT_OPTIONS,
            index=0,
            help="Unit used by axial and shear columns in the active load tables.",
        )
    with unit_cols[1]:
        moment_unit = st.selectbox(
            "Moment unit",
            MOMENT_UNIT_OPTIONS,
            index=0,
            help="Unit used by moment and torsion columns in the active load tables.",
        )

    with st.expander("Axis convention for load input", expanded=True):
        _render_axis_convention_panel()

    settings = _analysis_mode_from_session_state()
    if settings.member_type == "beam_girder":
        _render_beam_girder_load_tables(force_unit, moment_unit)
    else:
        _render_column_load_tables(force_unit, moment_unit)
