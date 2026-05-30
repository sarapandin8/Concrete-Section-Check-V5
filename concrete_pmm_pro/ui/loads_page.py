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
        "The current load table stores Pu, Mux, and Muy for PMM/SLS section workflows."
    )
    if settings.member_type == "beam_girder":
        st.warning(
            "Beam/Girder design load tables for Mu, Vu, Tu, transfer stage, service stage, and prestress effects "
            "are future work. Do not treat the current Pu/Mux/Muy PMM table as a completed bridge girder design workflow."
        )

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


def render_loads_page() -> None:
    st.subheader("Loads")
    st.caption("Paste-friendly load case input for PMM strength and serviceability workflows.")

    _render_load_workflow_notice()

    st.info(
        "PMM strength checks currently use active ULS demand values: Pu, Mux, and Muy. "
        "Active SLS cases are stored and used by available serviceability checks."
    )

    unit_cols = st.columns(2)
    with unit_cols[0]:
        force_unit = st.selectbox("Force unit", FORCE_UNIT_OPTIONS, index=0, help="Unit used in the Pu column of the input table.")
    with unit_cols[1]:
        moment_unit = st.selectbox("Moment unit", MOMENT_UNIT_OPTIONS, index=0, help="Unit used in the Mux and Muy columns of the input table.")

    with st.expander("Excel / CSV load template", expanded=False):
        _render_load_template_downloads()

    with st.expander("Import Load Cases from Excel / CSV", expanded=True):
        _render_load_import_workflow(force_unit, moment_unit)

    with st.expander("Sign convention", expanded=False):
        st.write("- Pu is axial force demand. Compression is positive.")
        st.write("- Mux is moment demand about the x-axis.")
        st.write("- Muy is moment demand about the y-axis.")
        st.write("- x-axis is positive to the right in the section preview.")
        st.write("- y-axis is positive upward in the section preview.")
        st.write("- Positive moments follow the right-hand rule.")
        st.write("- For PMM strength checks, use active ULS load combinations.")
        st.write("- SLS load cases are stored and used by serviceability checks where available.")

    if "loads_table" not in st.session_state:
        st.session_state["loads_table"] = _default_load_table()

    editor_df = _normalize_editor_dataframe(st.session_state["loads_table"])
    st.markdown("**Load Case Input Table**")
    st.caption("Edit imported rows here if needed. Rows with blank case names are excluded; duplicate names are rejected.")
    edited_df = st.data_editor(
        editor_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Active": st.column_config.CheckboxColumn("Active", help="Only active and valid rows are used by analysis."),
            "Case Name": st.column_config.TextColumn("Case Name", help="Unique load case or combination name."),
            "Limit State": st.column_config.SelectboxColumn("Limit State", options=LOAD_TYPE_OPTIONS, help="ULS is used for strength checks; SLS is stored for service checks."),
            "Pu": st.column_config.TextColumn(f"Pu ({force_unit}, compression +)", help="Axial demand. Compression is positive."),
            "Mux": st.column_config.TextColumn(f"Mux ({moment_unit})", help="Moment demand about the x-axis."),
            "Muy": st.column_config.TextColumn(f"Muy ({moment_unit})", help="Moment demand about the y-axis."),
            "Note": st.column_config.TextColumn("Note", help="Optional engineering note. Not used in calculation."),
        },
        key="loads_data_editor",
    )
    edited_df = _normalize_editor_dataframe(edited_df)
    st.session_state["loads_table"] = edited_df

    result = parse_load_cases_from_dataframe(edited_df, force_unit, moment_unit)
    # Keep valid rows available even when other pasted rows are invalid.
    # Invalid rows are reported in the validation panel and excluded from analysis.
    st.session_state["load_cases"] = result.load_cases

    nonblank_count = sum(0 if _row_is_blank(row) else 1 for _, row in edited_df.iterrows())
    _render_summary_metrics(result, total_rows=nonblank_count)
    _render_validation_panel(result)

    with st.expander("Valid Load Cases Used by Analysis", expanded=True):
        st.caption("This table shows validated rows converted back to the selected input units for review.")
        st.dataframe(_valid_load_cases_dataframe(result.load_cases, force_unit, moment_unit), use_container_width=True, hide_index=True)

    with st.expander("Internal Units Preview", expanded=False):
        st.caption("Internal solver units are N and N-mm.")
        st.dataframe(_preview_dataframe(st.session_state["load_cases"]), use_container_width=True, hide_index=True)
