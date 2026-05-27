"""Prestress tab UI and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
import re

import pandas as pd
import streamlit as st
from pydantic import ValidationError
from shapely.geometry import Point, Polygon

from concrete_pmm_pro.core.models import PrestressElement, SectionGeometry
from concrete_pmm_pro.core.units import kN_to_N
from concrete_pmm_pro.data.prestress_tendon_products import (
    DEFAULT_STRAND_DIAMETER_MM,
    DEFAULT_STRAND_EP_MPA,
    DEFAULT_STRAND_FPY_MPA,
    DEFAULT_STRAND_FPU_MPA,
    TendonProduct,
    apply_tendon_product_to_row,
    equivalent_steel_diameter_mm,
    get_tendon_product,
    is_tendon_6n_label,
    list_tendon_products,
    make_custom_tendon_product,
    standard_tendon_label,
    tendon_product_options,
)
from concrete_pmm_pro.geometry.summary import to_shapely_polygon
from concrete_pmm_pro.visualization import create_section_preview

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESTRESS_DB_PATH = REPO_ROOT / "data" / "prestress_steel_database.csv"

STEEL_TYPE_OPTIONS = ["wire", "strand", "prestressing_bar", "tendon_group", "custom"]
INPUT_MODE_OPTIONS = ["Passive", "Pe_eff", "fpe"]
INPUT_MODE_DISPLAY_LABELS = {
    "Passive": "Passive — no prestress force",
    "Pe_eff": "Pe_eff — enter effective force after losses (kN)",
    "fpe": "fpe — enter effective stress after losses (MPa)",
}
INPUT_MODE_EDITOR_OPTIONS = list(INPUT_MODE_DISPLAY_LABELS.values())
LEGACY_INPUT_MODE_ALIASES = {
    "Effective Force Pe": "Pe_eff",
    "Effective Stress fpe": "fpe",
    **{display_label: value for value, display_label in INPUT_MODE_DISPLAY_LABELS.items()},
}
LEGACY_INPUT_MODE_OPTIONS = ["Jacking Stress + Losses"]
TENDON_PRODUCT_CREATION_MODES = ["Standard tendon product", "Custom tendon"]

PRESTRESS_COMPACT_EDITOR_COLUMNS = [
    "Active",
    "Label",
    "Product",
    "x_mm",
    "y_mm",
    "Area_mm2",
    "Input Mode",
    "Pe_eff_kN",
    "fpe_MPa",
    "Bonded",
    "Count",
]
PRESTRESS_REFERENCE_DETAIL_COLUMNS = [
    "Label",
    "Steel Type",
    "Product",
    "Diameter_mm",
    "Eq Steel Dia_mm",
    "fpy_MPa",
    "fpu_MPa",
    "Ep_MPa",
    "fpj_ratio",
    "loss_percent",
    "Strand Count",
    "Strand Diameter_mm",
    "Strand Area_mm2",
    "Breaking Load_kN",
    "Duct Type",
    "Duct ID_mm",
]


@dataclass(frozen=True)
class PrestressParseResult:
    elements: list[PrestressElement]
    errors: list[str]
    warnings: list[str]
    info: list[str]


@dataclass(frozen=True)
class PrestressMetric:
    title: str
    value: str
    detail: str = ""
    status: str = "neutral"
    strong: bool = False


_PRESTRESS_PAGE_CSS = """
<style>
.cpmm-prestress-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.55rem;
  margin-bottom: 0.75rem;
}
.cpmm-prestress-chip {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.58rem 0.7rem;
  min-height: 76px;
}
.cpmm-prestress-chip-label {
  color: #667085;
  font-size: 0.74rem;
  font-weight: 650;
  letter-spacing: 0;
  margin-bottom: 0.18rem;
}
.cpmm-prestress-chip-value {
  color: #101828;
  font-size: 0.96rem;
  font-weight: 720;
  line-height: 1.22;
  overflow-wrap: anywhere;
}
.cpmm-prestress-chip-detail {
  color: #667085;
  font-size: 0.74rem;
  line-height: 1.25;
  margin-top: 0.16rem;
}
.cpmm-prestress-badge {
  display: inline-block;
  border-radius: 999px;
  padding: 0.12rem 0.5rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0;
}
.cpmm-prestress-badge.ready { color: #1f5f2a; background: #e7f5e8; }
.cpmm-prestress-badge.warning { color: #7a4b00; background: #fff4d6; }
.cpmm-prestress-badge.danger { color: #9f1f17; background: #fde8e7; }
.cpmm-prestress-badge.info { color: #1849a9; background: #e8f1ff; }
.cpmm-prestress-badge.neutral { color: #475467; background: #eef1f5; }
.cpmm-prestress-kv-panel {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.64rem 0.84rem;
}
.cpmm-prestress-kv-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 0.8rem;
  border-bottom: 1px solid #edf0f5;
  padding: 0.32rem 0;
}
.cpmm-prestress-kv-row:last-child { border-bottom: 0; }
.cpmm-prestress-kv-label {
  color: #667085;
  font-size: 0.82rem;
  font-weight: 600;
}
.cpmm-prestress-kv-value {
  color: #101828;
  font-size: 0.88rem;
  font-weight: 650;
  text-align: right;
  overflow-wrap: anywhere;
}
.cpmm-prestress-note-panel {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 0.68rem 0.84rem;
}
.cpmm-prestress-note-item {
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.35;
  padding: 0.2rem 0;
}
.cpmm-prestress-message-list {
  border: 1px solid #edf0f5;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 0.62rem 0.78rem;
  margin-top: 0.55rem;
}
.cpmm-prestress-message-item {
  color: #475467;
  font-size: 0.82rem;
  line-height: 1.35;
  padding: 0.18rem 0;
}
.cpmm-prestress-quiet-note {
  color: #667085;
  font-size: 0.82rem;
  line-height: 1.35;
}

.cpmm-prestress-table-note {
  border: 1px solid #edf0f5;
  border-radius: 8px;
  background: #fbfcfe;
  padding: 0.52rem 0.7rem;
  margin: 0.42rem 0 0.65rem 0;
  color: #667085;
  font-size: 0.80rem;
  line-height: 1.35;
}
.cpmm-prestress-mode-guide {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.55rem 0 0.65rem 0;
}
.cpmm-prestress-mode-card {
  border: 1px solid #d9dee7;
  border-radius: 8px;
  background: #ffffff;
  padding: 0.52rem 0.65rem;
}
.cpmm-prestress-mode-title {
  color: #101828;
  font-size: 0.82rem;
  font-weight: 720;
  margin-bottom: 0.16rem;
}
.cpmm-prestress-mode-text {
  color: #667085;
  font-size: 0.78rem;
  line-height: 1.32;
}
@media (max-width: 980px) {
  .cpmm-prestress-mode-guide { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 1320px) {
  .cpmm-prestress-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .cpmm-prestress-strip { grid-template-columns: minmax(0, 1fr); }
}
</style>
"""


def load_prestress_steel_database(path: Path | str = DEFAULT_PRESTRESS_DB_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def _project_prestress_materials_dataframe(materials: list[Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for material in materials:
        rows.append(
            {
                "name": material.name,
                "type": material.steel_type,
                "diameter_mm": material.diameter_mm,
                "area_mm2": material.area_mm2,
                "grade": material.grade,
                "fpy_MPa": material.fpy_MPa,
                "fpu_MPa": material.fpu_MPa,
                "Ep_MPa": material.Ep_MPa,
                "source": material.source or "project_material",
                "area_source": material.area_source or "project_material",
                "is_catalog_verified": material.is_catalog_verified,
            }
        )
    return pd.DataFrame(rows)


def _combined_prestress_database(database: pd.DataFrame, project_materials: list[Any]) -> pd.DataFrame:
    project_df = _project_prestress_materials_dataframe(project_materials)
    if project_df.empty:
        return database
    return pd.concat([database, project_df], ignore_index=True).drop_duplicates(subset=["name"], keep="last")


def _default_prestress_table(prestress_db: pd.DataFrame) -> pd.DataFrame:
    first_product = str(prestress_db.iloc[0]["name"])
    second_product = "PS Bar 32 - 1080/1230" if "PS Bar 32 - 1080/1230" in set(prestress_db["name"]) else first_product
    first = prestress_db.loc[prestress_db["name"] == first_product].iloc[0]
    second = prestress_db.loc[prestress_db["name"] == second_product].iloc[0]
    return pd.DataFrame(
        [
            {
                "Active": True,
                "Label": "PS1",
                "Steel Type": first["type"],
                "Product": first_product,
                "x_mm": -100.0,
                "y_mm": -250.0,
                "Area_mm2": float(first["area_mm2"]),
                "Diameter_mm": float(first["diameter_mm"]),
                "Eq Steel Dia_mm": None,
                "fpy_MPa": float(first["fpy_MPa"]),
                "fpu_MPa": float(first["fpu_MPa"]),
                "Ep_MPa": float(first["Ep_MPa"]),
                "Input Mode": "Passive",
                "Pe_eff_kN": 0.0,
                "fpe_MPa": 0.0,
                "fpj_ratio": 0.75,
                "loss_percent": 15.0,
                "Bonded": True,
                "Count": 1,
                "Strand Count": None,
                "Breaking Load_kN": None,
                "Duct Type": "",
                "Duct ID_mm": None,
                "Note": "",
            },
            {
                "Active": True,
                "Label": "PS2",
                "Steel Type": second["type"],
                "Product": second_product,
                "x_mm": 100.0,
                "y_mm": -250.0,
                "Area_mm2": float(second["area_mm2"]),
                "Diameter_mm": float(second["diameter_mm"]),
                "Eq Steel Dia_mm": None,
                "fpy_MPa": float(second["fpy_MPa"]),
                "fpu_MPa": float(second["fpu_MPa"]),
                "Ep_MPa": float(second["Ep_MPa"]),
                "Input Mode": "Passive",
                "Pe_eff_kN": 0.0,
                "fpe_MPa": 0.0,
                "fpj_ratio": 0.75,
                "loss_percent": 15.0,
                "Bonded": True,
                "Count": 1,
                "Strand Count": None,
                "Breaking Load_kN": None,
                "Duct Type": "",
                "Duct ID_mm": None,
                "Note": "",
            },
        ]
    )


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _row_is_blank(row: pd.Series) -> bool:
    columns = [
        "Label",
        "Steel Type",
        "Product",
        "x_mm",
        "y_mm",
        "Area_mm2",
        "Diameter_mm",
        "Eq Steel Dia_mm",
        "fpy_MPa",
        "fpu_MPa",
        "Ep_MPa",
        "Input Mode",
        "Pe_eff_kN",
        "Pe_eff",
        "fpe_MPa",
        "fpj_ratio",
        "loss_percent",
        "Count",
        "Note",
    ]
    return all(_is_blank(row.get(column)) for column in columns)


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


def _to_bool_default_true(value: Any) -> bool:
    if _is_blank(value):
        return True
    return _to_bool(value)


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


def _normalize_input_mode_label(value: Any) -> str:
    mode = "Passive" if _is_blank(value) else str(value).strip()
    return LEGACY_INPUT_MODE_ALIASES.get(mode, mode)


def _input_mode_display_label(value: Any) -> str:
    """Return the user-facing editor label for a stored input mode value."""

    mode = _normalize_input_mode_label(value)
    return INPUT_MODE_DISPLAY_LABELS.get(mode, INPUT_MODE_DISPLAY_LABELS["Passive"])


def _prestress_table_for_editor(table: pd.DataFrame) -> pd.DataFrame:
    """Create a display-only editor copy with clear input-mode labels.

    The backing table intentionally stores compact canonical values
    (Passive/Pe_eff/fpe) so analysis, project I/O, and tests remain stable.
    Only the Streamlit editor copy uses the longer explanatory dropdown labels.
    """

    editor_table = pd.DataFrame(table).copy()
    if "Input Mode" in editor_table.columns:
        editor_table["Input Mode"] = editor_table["Input Mode"].map(_input_mode_display_label)
    return editor_table


def _effective_prestress_columns() -> list[str]:
    return ["Input Mode", "Pe_eff_kN", "fpe_MPa"]


def _product_row(product: str, prestress_db: pd.DataFrame) -> pd.Series | None:
    if _is_blank(product) or product == "Custom":
        return None
    matches = prestress_db.loc[prestress_db["name"] == product]
    if matches.empty:
        return None
    return matches.iloc[0]


def _blank_prestress_row(label: str = "PS") -> dict[str, Any]:
    return {
        "Active": True,
        "Label": label,
        "Steel Type": "custom",
        "Product": "Custom",
        "x_mm": 0.0,
        "y_mm": 0.0,
        "Area_mm2": None,
        "Diameter_mm": None,
        "Eq Steel Dia_mm": None,
        "fpy_MPa": None,
        "fpu_MPa": DEFAULT_STRAND_FPU_MPA,
        "Ep_MPa": DEFAULT_STRAND_EP_MPA,
        "Input Mode": "Passive",
        "Pe_eff_kN": 0.0,
        "fpe_MPa": 0.0,
        "fpj_ratio": 0.75,
        "loss_percent": 15.0,
        "Bonded": True,
        "Count": 1,
        "Strand Count": None,
        "Breaking Load_kN": None,
        "Duct Type": "",
        "Duct ID_mm": None,
        "Note": "",
    }


def _append_prestress_row(table: pd.DataFrame, row: dict[str, Any]) -> pd.DataFrame:
    table_columns = list(table.columns)
    row_columns = [column for column in row if column not in table_columns]
    columns = [*table_columns, *row_columns]
    if table.empty:
        return pd.DataFrame([row], columns=columns)
    expanded = table.copy()
    for column in row_columns:
        expanded[column] = None
    return pd.concat([expanded, pd.DataFrame([row], columns=columns)], ignore_index=True)


def _product_options_for_table(prestress_db: pd.DataFrame, prestress_table: pd.DataFrame | None) -> list[str]:
    options: list[str] = ["", "Custom"]
    if "name" in prestress_db.columns:
        options.extend(str(name).strip() for name in prestress_db["name"].tolist() if not _is_blank(name))
    options.extend(tendon_product_options())
    if prestress_table is not None and "Product" in prestress_table.columns:
        options.extend(str(product).strip() for product in prestress_table["Product"].tolist() if not _is_blank(product))
    return list(dict.fromkeys(options))


def _custom_tendon_product_from_label(product: str, row: pd.Series | None = None) -> TendonProduct | None:
    label = str(product).strip()
    parse_label = label.split(None, 1)[1].strip() if label.lower().startswith("tendon ") else label
    if not parse_label.startswith("6-"):
        return None
    try:
        strand_count = int(parse_label.split("-", 1)[1])
    except (TypeError, ValueError):
        return None
    if strand_count < 1:
        return None
    duct_id = _to_float(row.get("Duct ID_mm")) if row is not None else None
    duct_type = None if row is None or _is_blank(row.get("Duct Type")) else str(row.get("Duct Type")).strip()
    return make_custom_tendon_product(strand_count, label=label, duct_id_mm=duct_id, duct_type=duct_type)


def _apply_database_product_to_display_row(normalized: pd.DataFrame, index: Any, database_row: pd.Series) -> None:
    normalized.at[index, "Steel Type"] = str(database_row["type"])
    normalized.at[index, "Area_mm2"] = float(database_row["area_mm2"])
    normalized.at[index, "Diameter_mm"] = None if pd.isna(database_row["diameter_mm"]) else float(database_row["diameter_mm"])
    normalized.at[index, "Eq Steel Dia_mm"] = None
    normalized.at[index, "fpy_MPa"] = None if pd.isna(database_row["fpy_MPa"]) else float(database_row["fpy_MPa"])
    normalized.at[index, "fpu_MPa"] = None if pd.isna(database_row["fpu_MPa"]) else float(database_row["fpu_MPa"])
    normalized.at[index, "Ep_MPa"] = float(database_row["Ep_MPa"])
    normalized.at[index, "Strand Count"] = None
    normalized.at[index, "Strand Diameter_mm"] = None
    normalized.at[index, "Strand Area_mm2"] = None
    normalized.at[index, "Breaking Load_kN"] = None
    normalized.at[index, "Duct Type"] = ""
    normalized.at[index, "Duct ID_mm"] = None


def _looks_like_15_2mm_tendon_group(row: pd.Series) -> bool:
    steel_type = "" if _is_blank(row.get("Steel Type")) else str(row.get("Steel Type")).strip()
    if steel_type != "tendon_group":
        return False
    product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
    if get_tendon_product(product) is not None or is_tendon_6n_label(product):
        return True
    strand_count = _to_float(row.get("Strand Count"))
    strand_diameter = _to_float(row.get("Strand Diameter_mm"))
    if strand_count is None:
        return False
    return strand_diameter is None or abs(strand_diameter - DEFAULT_STRAND_DIAMETER_MM) < 1e-6


def _sync_effective_inputs_for_row(normalized: pd.DataFrame, index: Any) -> None:
    mode = _normalize_input_mode_label(normalized.at[index, "Input Mode"] if "Input Mode" in normalized.columns else "Passive")
    if mode not in INPUT_MODE_OPTIONS and mode not in LEGACY_INPUT_MODE_OPTIONS:
        return
    if mode in INPUT_MODE_OPTIONS:
        normalized.at[index, "Input Mode"] = mode
    area_mm2 = _to_float(normalized.at[index, "Area_mm2"] if "Area_mm2" in normalized.columns else None)
    pe_kn = _pe_eff_kn_from_row(normalized.loc[index])
    fpe_mpa = _to_float(normalized.at[index, "fpe_MPa"] if "fpe_MPa" in normalized.columns else None)

    if mode == "Passive":
        normalized.at[index, "Pe_eff_kN"] = 0.0
        normalized.at[index, "fpe_MPa"] = 0.0
        return

    if mode == "Pe_eff":
        pe_kn = pe_kn if pe_kn is not None else 0.0
        normalized.at[index, "Pe_eff_kN"] = pe_kn
        normalized.at[index, "fpe_MPa"] = (pe_kn * 1000.0 / area_mm2) if area_mm2 and area_mm2 > 0 else None
        return

    if mode == "fpe":
        fpe_mpa = fpe_mpa if fpe_mpa is not None else 0.0
        normalized.at[index, "fpe_MPa"] = fpe_mpa
        normalized.at[index, "Pe_eff_kN"] = (area_mm2 * fpe_mpa / 1000.0) if area_mm2 and area_mm2 > 0 else None


def _normalize_prestress_table_for_display(table: pd.DataFrame, prestress_db: pd.DataFrame | None = None) -> pd.DataFrame:
    normalized = pd.DataFrame(table).copy()
    if normalized.empty:
        return normalized
    for column in (
        "Diameter_mm",
        "fpy_MPa",
        "fpu_MPa",
        "Ep_MPa",
        "Input Mode",
        "Pe_eff_kN",
        "fpe_MPa",
        "Strand Count",
        "Strand Diameter_mm",
        "Strand Area_mm2",
        "Breaking Load_kN",
        "Duct Type",
        "Duct ID_mm",
        "Count",
        "Note",
    ):
        if column not in normalized.columns:
            normalized[column] = None
    if "Pe_eff_kN" in normalized.columns and "Pe_eff" in normalized.columns:
        missing_pe = normalized["Pe_eff_kN"].map(_is_blank)
        normalized.loc[missing_pe, "Pe_eff_kN"] = normalized.loc[missing_pe, "Pe_eff"]
    normalized["Diameter_mm"] = normalized["Diameter_mm"].astype("object")
    if "Eq Steel Dia_mm" not in normalized.columns:
        insert_at = normalized.columns.get_loc("Diameter_mm") + 1 if "Diameter_mm" in normalized.columns else len(normalized.columns)
        normalized.insert(insert_at, "Eq Steel Dia_mm", None)
    for index, row in normalized.iterrows():
        normalized.at[index, "Input Mode"] = _normalize_input_mode_label(row.get("Input Mode"))
        count = _to_count(row.get("Count"))
        normalized.at[index, "Count"] = 1 if count is None else count
        normalized.at[index, "Note"] = "" if _is_blank(row.get("Note")) else str(row.get("Note")).strip()
        product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
        tendon_product = get_tendon_product(product) or _custom_tendon_product_from_label(product, row)
        database_row = _product_row(product, prestress_db) if prestress_db is not None else None
        is_tendon_group = str(row.get("Steel Type") or "").strip() == "tendon_group" or tendon_product is not None
        if is_tendon_group:
            normalized.at[index, "Steel Type"] = "tendon_group"
            normalized.at[index, "Diameter_mm"] = None
            if tendon_product is not None:
                normalized.at[index, "Product"] = tendon_product.label
                normalized.at[index, "Area_mm2"] = tendon_product.tendon_area_mm2
                normalized.at[index, "fpy_MPa"] = tendon_product.fpy_MPa
                normalized.at[index, "fpu_MPa"] = tendon_product.fpu_MPa
                normalized.at[index, "Ep_MPa"] = tendon_product.Ep_MPa
                normalized.at[index, "Strand Count"] = tendon_product.strand_count
                normalized.at[index, "Strand Diameter_mm"] = tendon_product.strand_diameter_mm
                normalized.at[index, "Strand Area_mm2"] = tendon_product.strand_area_mm2
                normalized.at[index, "Breaking Load_kN"] = tendon_product.breaking_load_kN
                normalized.at[index, "Duct Type"] = tendon_product.duct_type or ""
                normalized.at[index, "Duct ID_mm"] = tendon_product.duct_id_mm
            elif _looks_like_15_2mm_tendon_group(normalized.loc[index]):
                if _is_blank(normalized.at[index, "fpy_MPa"]):
                    normalized.at[index, "fpy_MPa"] = DEFAULT_STRAND_FPY_MPA
                if _is_blank(normalized.at[index, "fpu_MPa"]):
                    normalized.at[index, "fpu_MPa"] = DEFAULT_STRAND_FPU_MPA
                if _is_blank(normalized.at[index, "Ep_MPa"]):
                    normalized.at[index, "Ep_MPa"] = DEFAULT_STRAND_EP_MPA
        elif database_row is not None:
            _apply_database_product_to_display_row(normalized, index, database_row)
        area_mm2 = _to_float(normalized.at[index, "Area_mm2"] if "Area_mm2" in normalized.columns else None)
        normalized.at[index, "Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(area_mm2) if is_tendon_group else None
        _sync_effective_inputs_for_row(normalized, index)
    return normalized


def normalize_prestress_table_for_effective_input_sync(table: pd.DataFrame, prestress_db: pd.DataFrame) -> pd.DataFrame:
    """Synchronize product defaults and effective prestress display fields.

    Product data controls area/material reference values. Input Mode controls
    only the dependent Pe_eff/fpe display value; it never derives prestress
    from product breaking load.
    """

    return _normalize_prestress_table_for_display(table, prestress_db)




def _compact_column_order_for_table(table: pd.DataFrame) -> list[str]:
    """Return visible editor columns without dropping hidden engineering data.

    Streamlit's ``column_order`` is used only to keep the Advanced Prestress
    editor readable. The backing session-state table still carries the full
    prestress product/material metadata required by product sync, validation,
    analysis, report export, and section preview.
    """

    available = set(pd.DataFrame(table).columns)
    return [column for column in PRESTRESS_COMPACT_EDITOR_COLUMNS if column in available]


def _prestress_reference_detail_dataframe(table: pd.DataFrame) -> pd.DataFrame:
    """Build a read-only detail view for product/material reference columns."""

    detail = pd.DataFrame(table).copy()
    if detail.empty:
        return detail
    columns = [column for column in PRESTRESS_REFERENCE_DETAIL_COLUMNS if column in detail.columns]
    return detail.loc[:, columns]

def _dataframes_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    left_norm = pd.DataFrame(left).reset_index(drop=True).astype("object")
    right_norm = pd.DataFrame(right).reset_index(drop=True).astype("object")
    left_norm = left_norm.where(pd.notna(left_norm), None)
    right_norm = right_norm.where(pd.notna(right_norm), None)
    if list(left_norm.columns) != list(right_norm.columns):
        return False
    return left_norm.equals(right_norm)


def _tendon_product_summary_dataframe(products: list[TendonProduct]) -> pd.DataFrame:
    return pd.DataFrame([product.as_dict() for product in products])


def _product_from_row_label(product: str) -> TendonProduct | None:
    return get_tendon_product(product) or _custom_tendon_product_from_label(product)


def _pe_eff_kn_from_row(row: pd.Series) -> float | None:
    if "Pe_eff_kN" in row.index and not _is_blank(row.get("Pe_eff_kN")):
        return _to_float(row.get("Pe_eff_kN"))
    return _to_float(row.get("Pe_eff"))


def _resolve_product_values(row: pd.Series, prestress_db: pd.DataFrame, row_number: int) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
    tendon_product = _product_from_row_label(product)
    database_row = _product_row(product, prestress_db)

    requested_steel_type = "" if _is_blank(row.get("Steel Type")) else str(row.get("Steel Type")).strip()
    values: dict[str, Any] = {
        "material_name": None if _is_blank(product) or product == "Custom" else product,
        "steel_type": requested_steel_type or "custom",
        "area_mm2": _to_float(row.get("Area_mm2")),
        "diameter_mm": _to_float(row.get("Diameter_mm")),
        "fpy_mpa": _to_float(row.get("fpy_MPa")),
        "fpu_mpa": _to_float(row.get("fpu_MPa")),
        "ep_mpa": _to_float(row.get("Ep_MPa")) or 195000.0,
    }

    if tendon_product is not None:
        if requested_steel_type and requested_steel_type != "tendon_group":
            warnings.append(f"Row {row_number}: Steel Type differs from tendon product type; using tendon_group.")
        values.update(
            {
                "material_name": tendon_product.label,
                "steel_type": "tendon_group",
                "area_mm2": tendon_product.tendon_area_mm2,
                "diameter_mm": None,
                "fpy_mpa": tendon_product.fpy_MPa,
                "fpu_mpa": tendon_product.fpu_MPa,
                "ep_mpa": tendon_product.Ep_MPa,
            }
        )
        return values, errors, warnings

    if database_row is not None:
        database_type = str(database_row["type"])
        if not requested_steel_type:
            values["steel_type"] = database_type
        elif requested_steel_type != database_type:
            warnings.append(f"Row {row_number}: Steel Type differs from database product type; using user-selected Steel Type.")
        values.update(
            {
                "material_name": product,
                "area_mm2": float(database_row["area_mm2"]),
                "diameter_mm": None if pd.isna(database_row["diameter_mm"]) else float(database_row["diameter_mm"]),
                "fpy_mpa": None if pd.isna(database_row["fpy_MPa"]) else float(database_row["fpy_MPa"]),
                "fpu_mpa": None if pd.isna(database_row["fpu_MPa"]) else float(database_row["fpu_MPa"]),
                "ep_mpa": float(database_row["Ep_MPa"]),
            }
        )
        return values, errors, warnings

    if product and product != "Custom":
        if values["area_mm2"] is not None:
            values["material_name"] = product
            if values["steel_type"] == "tendon_group" and not _is_blank(row.get("Strand Count")):
                values["diameter_mm"] = None
                if _looks_like_15_2mm_tendon_group(row):
                    if values["fpy_mpa"] is None:
                        values["fpy_mpa"] = DEFAULT_STRAND_FPY_MPA
                    if values["fpu_mpa"] is None:
                        values["fpu_mpa"] = DEFAULT_STRAND_FPU_MPA
                    values["ep_mpa"] = values["ep_mpa"] or DEFAULT_STRAND_EP_MPA
                return values, errors, warnings
            warnings.append(f"Row {row_number}: Product '{product}' is not in the database; using manual values as custom prestress steel.")
        else:
            errors.append(f"Row {row_number}: Product '{product}' is not in the database and Area_mm2 is blank.")
    elif values["area_mm2"] is None:
        errors.append(f"Row {row_number}: Product or Area_mm2 is required.")

    return values, errors, warnings


def _resolve_initial_state(
    row: pd.Series,
    values: dict[str, Any],
    row_number: int,
) -> tuple[float, float, float, list[str], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    area_mm2 = float(values["area_mm2"] or 0.0)
    ep_mpa = float(values["ep_mpa"] or 195000.0)
    fpu_mpa = values.get("fpu_mpa")
    input_mode = _normalize_input_mode_label(row.get("Input Mode"))

    if input_mode not in INPUT_MODE_OPTIONS and input_mode not in LEGACY_INPUT_MODE_OPTIONS:
        errors.append(f"Row {row_number}: Input Mode must be one of {', '.join(INPUT_MODE_OPTIONS)}.")
        return 0.0, 0.0, 0.0, errors, warnings, info

    if input_mode == "Passive":
        return 0.0, 0.0, 0.0, errors, warnings, info

    if input_mode == "Pe_eff":
        pe_kn = _pe_eff_kn_from_row(row)
        if pe_kn is None:
            warnings.append(f"Row {row_number}: Pe_eff mode has blank Pe_eff_kN; using zero effective prestress.")
            pe_kn = 0.0
        if pe_kn < 0:
            errors.append(f"Row {row_number}: Pe_eff_kN must be greater than or equal to zero.")
            return 0.0, 0.0, 0.0, errors, warnings, info
        if area_mm2 <= 0:
            errors.append(f"Row {row_number}: Area_mm2 must be positive for Pe_eff mode.")
            return 0.0, 0.0, 0.0, errors, warnings, info
        pe_eff_n = kN_to_N(pe_kn)
        initial_stress_mpa = pe_eff_n / area_mm2
        if fpu_mpa is not None:
            fpu_value = float(fpu_mpa)
            if initial_stress_mpa > fpu_value:
                max_pe_eff_kn = area_mm2 * fpu_value / 1000.0
                errors.append(
                    f"Row {row_number}: Initial prestress stress from Pe_eff exceeds fpu_MPa "
                    f"({initial_stress_mpa:,.1f} > {fpu_value:,.1f} MPa). "
                    f"Maximum Pe_eff for Area_mm2 and fpu_MPa is {max_pe_eff_kn:,.1f} kN; "
                    "this row is excluded from the analysis summary until corrected."
                )
                return 0.0, 0.0, 0.0, errors, warnings, info
            if initial_stress_mpa > 0.75 * fpu_value:
                warnings.append(
                    f"Row {row_number}: Effective prestress stress is greater than 0.75 x fpu_MPa; "
                    "high relative to fpu_MPa; verify effective prestress and loss assumptions."
                )
        if pe_eff_n == 0:
            warnings.append(f"Row {row_number}: Pe_eff mode has zero Pe_eff_kN.")
        return pe_eff_n, initial_stress_mpa, initial_stress_mpa / ep_mpa, errors, warnings, info

    if input_mode == "fpe":
        fpe_mpa = _to_float(row.get("fpe_MPa"))
        if fpe_mpa is None:
            warnings.append(f"Row {row_number}: fpe mode has blank fpe_MPa; using zero effective prestress.")
            fpe_mpa = 0.0
        if fpe_mpa < 0:
            errors.append(f"Row {row_number}: fpe_MPa must be greater than or equal to zero.")
        if area_mm2 <= 0:
            errors.append(f"Row {row_number}: Area_mm2 must be positive for fpe mode.")
        if fpu_mpa is not None and fpe_mpa > float(fpu_mpa):
            errors.append(f"Row {row_number}: fpe_MPa must not exceed fpu_MPa.")
        if fpu_mpa is not None and fpe_mpa > 0.75 * float(fpu_mpa):
            warnings.append(
                f"Row {row_number}: fpe_MPa is greater than 0.75 x fpu_MPa; "
                "verify effective prestress and loss assumptions."
            )
        if errors:
            return 0.0, 0.0, 0.0, errors, warnings, info
        if fpe_mpa == 0:
            warnings.append(f"Row {row_number}: fpe mode has zero fpe_MPa.")
        return area_mm2 * fpe_mpa, fpe_mpa, fpe_mpa / ep_mpa, errors, warnings, info

    fpj_ratio = _to_float(row.get("fpj_ratio"))
    loss_percent = _to_float(row.get("loss_percent"))
    if fpu_mpa is None:
        errors.append(f"Row {row_number}: fpu_MPa is required for Jacking Stress + Losses mode.")
    if fpj_ratio is None:
        errors.append(f"Row {row_number}: fpj_ratio must be numeric.")
    elif fpj_ratio < 0:
        errors.append(f"Row {row_number}: fpj_ratio must be greater than or equal to zero.")
    elif fpj_ratio > 1.10:
        errors.append(f"Row {row_number}: fpj_ratio is too high.")
    if loss_percent is None:
        errors.append(f"Row {row_number}: loss_percent must be numeric.")
    elif loss_percent < 0 or loss_percent > 100:
        errors.append(f"Row {row_number}: loss_percent must be between 0 and 100.")
    if errors:
        return 0.0, 0.0, 0.0, errors, warnings, info

    fpu_value = float(fpu_mpa)
    assert fpj_ratio is not None
    assert loss_percent is not None
    fpj_mpa = fpj_ratio * fpu_value
    fpe_mpa = fpj_mpa * (1.0 - loss_percent / 100.0)
    if fpj_ratio > 1.0:
        info.append(f"Row {row_number}: fpj_ratio is greater than 1.0; review jacking stress assumptions.")
    if fpe_mpa > fpu_value:
        errors.append(f"Row {row_number}: effective stress after losses must not exceed fpu_MPa.")
        return 0.0, 0.0, 0.0, errors, warnings, info
    return area_mm2 * fpe_mpa, fpe_mpa, fpe_mpa / float(values["ep_mpa"]), errors, warnings, info


def prestress_elements_from_dataframe(df: pd.DataFrame, prestress_db: pd.DataFrame) -> PrestressParseResult:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    elements: list[PrestressElement] = []

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

        count = _to_count(row.get("Count"))
        if count is None:
            errors.append(f"Row {row_number}: Count must be an integer greater than or equal to 1.")
            count = 1

        values, value_errors, value_warnings = _resolve_product_values(row, prestress_db, row_number)
        errors.extend(value_errors)
        warnings.extend(value_warnings)

        steel_type = str(values.get("steel_type") or "").strip()
        if steel_type not in STEEL_TYPE_OPTIONS:
            errors.append(f"Row {row_number}: Steel Type must be one of {', '.join(STEEL_TYPE_OPTIONS)}.")

        area_mm2 = values.get("area_mm2")
        ep_mpa = values.get("ep_mpa")
        if area_mm2 is None or float(area_mm2) <= 0:
            errors.append(f"Row {row_number}: Area_mm2 must be positive.")
        if ep_mpa is None or float(ep_mpa) <= 0:
            errors.append(f"Row {row_number}: Ep_MPa must be positive.")
            values["ep_mpa"] = 195000.0
        if values.get("fpy_mpa") is not None and values.get("fpu_mpa") is not None and float(values["fpy_mpa"]) >= float(values["fpu_mpa"]):
            errors.append(f"Row {row_number}: fpy_MPa must be less than fpu_MPa.")

        if any(error.startswith(f"Row {row_number}:") for error in errors):
            continue

        pe_eff_n, initial_stress_mpa, initial_strain, state_errors, state_warnings, state_info = _resolve_initial_state(row, values, row_number)
        errors.extend(state_errors)
        warnings.extend(state_warnings)
        info.extend(state_info)
        if state_errors:
            continue

        base_label = str(row.get("Label")).strip() if not _is_blank(row.get("Label")) else f"PS{len(elements) + 1}"
        try:
            elements.append(
                PrestressElement(
                    x_mm=float(x_mm),
                    y_mm=float(y_mm),
                    area_mm2=float(values["area_mm2"]),
                    diameter_mm=None if values.get("diameter_mm") is None else float(values["diameter_mm"]),
                    material_name=values.get("material_name"),
                    steel_type=steel_type,
                    fpy_mpa=None if values.get("fpy_mpa") is None else float(values["fpy_mpa"]),
                    fpu_mpa=None if values.get("fpu_mpa") is None else float(values["fpu_mpa"]),
                    ep_mpa=float(values["ep_mpa"]),
                    pe_eff_n=pe_eff_n,
                    initial_stress_mpa=initial_stress_mpa,
                    initial_strain=initial_strain,
                    bonded=_to_bool_default_true(row.get("Bonded")),
                    count=count,
                    label=base_label,
                )
            )
        except ValidationError as exc:
            errors.append(f"Row {row_number}: {exc.errors()[0]['msg']}")

    active_count = len(elements)
    total_aps = sum(element.total_area_mm2 for element in elements)
    total_pe = sum(element.pe_eff_n * element.count for element in elements)
    info.extend([f"{active_count} active prestress element(s).", f"Total Aps = {total_aps:,.1f} mm^2.", f"Total Pe_eff = {total_pe:,.1f} N."])
    if not elements:
        warnings.append("No active prestress elements are defined.")
    return PrestressParseResult(elements=elements, errors=errors, warnings=warnings, info=info)


def validate_prestress_against_geometry(elements: list[PrestressElement], geometry: SectionGeometry | None) -> list[str]:
    if geometry is None:
        return []
    section = to_shapely_polygon(geometry)
    hole_polygons = [Polygon([point.as_tuple() for point in hole]) for hole in geometry.holes]
    errors: list[str] = []
    for index, element in enumerate(elements, start=1):
        label = element.label or f"Prestress {index}"
        point = Point(element.x_mm, element.y_mm)
        if any(hole.covers(point) for hole in hole_polygons):
            errors.append(f"{label}: prestress element is inside a void/hole.")
        elif not section.covers(point):
            errors.append(f"{label}: prestress element is outside concrete.")
    return errors


def prestress_valid_for_analysis(parse_result: PrestressParseResult, geometry_errors: list[str]) -> bool:
    return not parse_result.errors and not geometry_errors


def prestress_summary_dataframe(elements: list[PrestressElement]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Label": element.label,
                "material_name": element.material_name,
                "steel_type": element.steel_type,
                "x_mm": element.x_mm,
                "y_mm": element.y_mm,
                "area_mm2": element.area_mm2,
                "diameter_mm": element.diameter_mm,
                "fpy_mpa": element.fpy_mpa,
                "fpu_mpa": element.fpu_mpa,
                "ep_mpa": element.ep_mpa,
                "pe_eff_n": element.pe_eff_n,
                "total_area_mm2": element.total_area_mm2,
                "total_pe_eff_n": element.pe_eff_n * element.count,
                "initial_stress_mpa": element.initial_stress_mpa,
                "initial_strain": element.initial_strain,
                "bonded": element.bonded,
                "count": element.count,
            }
            for element in elements
        ]
    )


def _safe_status(status: str) -> str:
    return status if status in {"ready", "warning", "danger", "info", "neutral"} else "neutral"


def _badge_html(value: str, status: str) -> str:
    return f'<span class="cpmm-prestress-badge {_safe_status(status)}">{escape(value)}</span>'


def _metric_strip_html(metrics: list[PrestressMetric]) -> str:
    chips: list[str] = []
    for metric in metrics:
        status = _safe_status(metric.status)
        value_html = _badge_html(metric.value, status) if metric.strong else escape(metric.value)
        detail_html = f'<div class="cpmm-prestress-chip-detail">{escape(metric.detail)}</div>' if metric.detail else ""
        chips.append(
            '<div class="cpmm-prestress-chip">'
            f'<div class="cpmm-prestress-chip-label">{escape(metric.title)}</div>'
            f'<div class="cpmm-prestress-chip-value">{value_html}</div>'
            f"{detail_html}"
            "</div>"
        )
    return '<div class="cpmm-prestress-strip">' + "".join(chips) + "</div>"


def _status_panel_html(rows: list[PrestressMetric]) -> str:
    row_html: list[str] = []
    for row in rows:
        value_html = _badge_html(row.value, row.status) if row.strong else escape(row.value)
        row_html.append(
            '<div class="cpmm-prestress-kv-row">'
            f'<div class="cpmm-prestress-kv-label">{escape(row.title)}</div>'
            f'<div class="cpmm-prestress-kv-value">{value_html}</div>'
            "</div>"
        )
    return '<div class="cpmm-prestress-kv-panel">' + "".join(row_html) + "</div>"


def _message_list_html(messages: list[str]) -> str:
    if not messages:
        return ""
    items = "".join(f'<div class="cpmm-prestress-message-item">{escape(message)}</div>' for message in messages)
    return f'<div class="cpmm-prestress-message-list">{items}</div>'


def _engineering_notes_html() -> str:
    notes = [
        "Choose Passive for non-prestressed steel contribution. Choose Pe_eff to enter effective force directly.",
        "Choose fpe to enter effective stress and compute Pe_eff from Area_mm2; Pe_eff is after selected losses.",
        "Product breaking load is reference data only and is never used as Pe_eff.",
        "Duct ID is duct reference information and is not steel diameter.",
        "For tendon_group rows, Area_mm2 controls steel area; Eq Steel Dia_mm is display and preview information only.",
        "Prestress is treated as internal section action, not external Pu demand.",
    ]
    items = "".join(f'<div class="cpmm-prestress-note-item">{escape(note)}</div>' for note in notes)
    return f'<div class="cpmm-prestress-note-panel">{items}</div>'


def _input_mode_guide_html() -> str:
    cards = [
        ("Passive", "No effective prestress force. The steel is included as passive high-strength steel only."),
        ("Pe_eff", "Enter effective prestress force in kN after losses. fpe is computed from Pe_eff / Area."),
        ("fpe", "Enter effective prestress stress in MPa after losses. Pe_eff is computed from Area x fpe."),
    ]
    card_html = "".join(
        '<div class="cpmm-prestress-mode-card">'
        f'<div class="cpmm-prestress-mode-title">{escape(title)}</div>'
        f'<div class="cpmm-prestress-mode-text">{escape(text)}</div>'
        '</div>'
        for title, text in cards
    )
    return f'<div class="cpmm-prestress-mode-guide">{card_html}</div>'


def _row_numbers_from_errors(errors: list[str]) -> set[int]:
    row_numbers: set[int] = set()
    for message in errors:
        match = re.match(r"Row\s+(\d+):", message)
        if match:
            row_numbers.add(int(match.group(1)))
    return row_numbers


def _invalid_prestress_rows_dataframe(table: pd.DataFrame, errors: list[str]) -> pd.DataFrame:
    """Return user-facing rows excluded from analysis because of validation errors."""

    row_numbers = _row_numbers_from_errors(errors)
    if not row_numbers:
        return pd.DataFrame()
    source = pd.DataFrame(table).reset_index(drop=True)
    rows: list[dict[str, Any]] = []
    for row_number in sorted(row_numbers):
        if row_number < 1 or row_number > len(source):
            continue
        row = source.iloc[row_number - 1]
        reasons = [message for message in errors if message.startswith(f"Row {row_number}:")]
        rows.append(
            {
                "Row": row_number,
                "Label": row.get("Label"),
                "Product": row.get("Product"),
                "Input Mode": row.get("Input Mode"),
                "Area_mm2": row.get("Area_mm2"),
                "Pe_eff_kN": row.get("Pe_eff_kN"),
                "fpe_MPa": row.get("fpe_MPa"),
                "Reason excluded": " | ".join(reasons),
            }
        )
    return pd.DataFrame(rows)


def _build_prestress_summary_metrics(result: PrestressParseResult, geometry_errors: list[str], valid_for_analysis: bool) -> list[PrestressMetric]:
    total_aps = sum(element.total_area_mm2 for element in result.elements)
    total_pe_kn = sum(element.pe_eff_n * element.count for element in result.elements) / 1000.0
    tendon_group_count = sum(1 for element in result.elements if element.steel_type == "tendon_group")
    strand_pt_count = sum(1 for element in result.elements if element.steel_type in {"strand", "prestressing_bar"})
    bonded_count = sum(1 for element in result.elements if element.bonded)
    unbonded_count = sum(1 for element in result.elements if not element.bonded)
    error_count = len(result.errors) + len(geometry_errors)
    warning_count = len(result.warnings)
    return [
        PrestressMetric("Valid elements", f"{len(result.elements):,}", detail="used in analysis", status="info"),
        PrestressMetric("Total Aps", f"{total_aps:,.1f} mm2"),
        PrestressMetric("Total Pe_eff", f"{total_pe_kn:,.1f} kN", detail="valid rows only"),
        PrestressMetric("Analysis readiness", "Yes" if valid_for_analysis else "No", status="ready" if valid_for_analysis else "danger", strong=True),
        PrestressMetric("Tendon groups", f"{tendon_group_count:,}", detail=f"Strand/PT bars: {strand_pt_count:,}"),
        PrestressMetric("Bonded state", f"{bonded_count:,} / {unbonded_count:,}", detail="bonded / unbonded", status="warning" if unbonded_count else "neutral"),
        PrestressMetric("Input modes", "See table", detail="Passive / Pe_eff / fpe"),
        PrestressMetric("Validation", f"{error_count:,} error(s)", detail=f"{warning_count:,} warning(s)", status="danger" if error_count else ("warning" if warning_count else "ready"), strong=bool(error_count)),
    ]


def _build_prestress_status_rows(
    result: PrestressParseResult,
    geometry_errors: list[str],
    geometry_available: bool,
    valid_for_analysis: bool,
) -> list[PrestressMetric]:
    all_errors = [*result.errors, *geometry_errors]
    warnings = list(result.warnings)
    if not geometry_available:
        warnings.append("Section geometry is not available yet.")
    total_aps = sum(element.total_area_mm2 for element in result.elements)
    total_pe_kn = sum(element.pe_eff_n * element.count for element in result.elements) / 1000.0
    tendon_group_count = sum(1 for element in result.elements if element.steel_type == "tendon_group")
    bonded_count = sum(1 for element in result.elements if element.bonded)
    unbonded_count = sum(1 for element in result.elements if not element.bonded)
    return [
        PrestressMetric("Overall readiness", "Ready" if valid_for_analysis else "Not ready", status="ready" if valid_for_analysis else "danger", strong=True),
        PrestressMetric("Validation errors", f"{len(all_errors):,}", status="danger" if all_errors else "ready", strong=bool(all_errors)),
        PrestressMetric("Warnings", f"{len(warnings):,}", status="warning" if warnings else "ready", strong=bool(warnings)),
        PrestressMetric("Valid elements", f"{len(result.elements):,}"),
        PrestressMetric("Total Aps", f"{total_aps:,.1f} mm2"),
        PrestressMetric("Valid Pe_eff", f"{total_pe_kn:,.1f} kN"),
        PrestressMetric("Tendon groups", f"{tendon_group_count:,}"),
        PrestressMetric("Bonded / unbonded", f"{bonded_count:,} / {unbonded_count:,}"),
    ]


def _render_prestress_summary_strip(result: PrestressParseResult, geometry_errors: list[str], valid_for_analysis: bool) -> None:
    st.markdown(_metric_strip_html(_build_prestress_summary_metrics(result, geometry_errors, valid_for_analysis)), unsafe_allow_html=True)


def _render_tendon_product_tools() -> None:
    st.markdown("#### Tendon Product Creation")
    st.markdown(
        '<div class="cpmm-prestress-quiet-note">'
        "Select a standard or custom 15.2 mm tendon product to populate product metadata and total tendon steel area. "
        "Effective prestress remains controlled in the Advanced Prestress Table."
        "</div>",
        unsafe_allow_html=True,
    )
    mode = st.radio(
        "Product creation mode",
        TENDON_PRODUCT_CREATION_MODES,
        horizontal=True,
        key="prestress_tendon_product_mode",
    )
    products = list_tendon_products()
    with st.expander("Standard tendon product database", expanded=False):
        st.dataframe(_tendon_product_summary_dataframe(products), use_container_width=True, hide_index=True)

    current_table = st.session_state.get("prestress_table")
    if current_table is None:
        current_table = pd.DataFrame()
    next_label = f"PS{len(current_table) + 1}"
    base_row = _blank_prestress_row(next_label)

    if mode == "Standard tendon product":
        product_options = tendon_product_options()
        default_product = standard_tendon_label(12)
        product_label = st.selectbox(
            "Standard tendon product",
            product_options,
            index=product_options.index(default_product) if default_product in product_options else 0,
        )
        product = get_tendon_product(product_label)
        assert product is not None
        st.dataframe(_tendon_product_summary_dataframe([product]), use_container_width=True, hide_index=True)
        row = apply_tendon_product_to_row(base_row, product)
        if st.button("Add standard tendon to table", use_container_width=True):
            st.session_state["prestress_table"] = _normalize_prestress_table_for_display(_append_prestress_row(pd.DataFrame(current_table), row))
            st.success(f"Added tendon product {product.label}. Pe_eff remains user-controlled.")
        return

    custom_label = st.text_input("Custom label", value="", placeholder="6-25")
    custom_cols = st.columns(3)
    strand_count = int(custom_cols[0].number_input("Strand count", min_value=1, value=25, step=1))
    strand_area = float(custom_cols[1].number_input("Strand area (mm2)", min_value=1.0, value=140.0, step=1.0))
    strand_diameter = float(custom_cols[2].number_input("Strand diameter (mm)", min_value=1.0, value=15.2, step=0.1))
    ref_cols = st.columns(3)
    breaking_load_per_strand = float(ref_cols[0].number_input("Breaking load per strand (kN)", min_value=1.0, value=260.0, step=1.0))
    duct_id = ref_cols[1].number_input("Duct ID reference (mm)", min_value=0.0, value=0.0, step=1.0)
    duct_type = ref_cols[2].text_input("Duct type reference", value="")
    product = make_custom_tendon_product(
        strand_count=strand_count,
        label=custom_label or None,
        strand_area_mm2=strand_area,
        breaking_load_per_strand_kN=breaking_load_per_strand,
        strand_diameter_mm=strand_diameter,
        duct_id_mm=None if duct_id <= 0 else float(duct_id),
        duct_type=duct_type or None,
    )
    st.dataframe(_tendon_product_summary_dataframe([product]), use_container_width=True, hide_index=True)
    row = apply_tendon_product_to_row(base_row, product)
    if st.button("Add custom tendon to table", use_container_width=True):
        st.session_state["prestress_table"] = _normalize_prestress_table_for_display(_append_prestress_row(pd.DataFrame(current_table), row))
        st.success(f"Added custom tendon {product.label}. Pe_eff remains user-controlled.")


def _render_validation(result: PrestressParseResult, geometry_errors: list[str], geometry_available: bool, valid_for_analysis: bool) -> None:
    st.markdown("#### Prestress Status")
    all_errors = [*result.errors, *geometry_errors]
    warnings = list(result.warnings)
    if not geometry_available:
        warnings.append("Section geometry is not available yet; geometry validation will run after a valid section is generated.")
    st.markdown(_status_panel_html(_build_prestress_status_rows(result, geometry_errors, geometry_available, valid_for_analysis)), unsafe_allow_html=True)
    messages = [f"ERROR: {error}" for error in all_errors] or ["No validation errors."]
    messages.extend(f"WARNING: {warning}" for warning in warnings)
    messages.extend(f"INFO: {item}" for item in result.info)
    st.markdown(_message_list_html(messages), unsafe_allow_html=True)


def _render_engineering_notes() -> None:
    st.markdown("#### Engineering Notes")
    st.markdown(_engineering_notes_html(), unsafe_allow_html=True)


def render_prestress_page() -> None:
    st.subheader("Prestress")
    st.markdown(_PRESTRESS_PAGE_CSS, unsafe_allow_html=True)
    prestress_db = _combined_prestress_database(load_prestress_steel_database(), st.session_state.get("prestress_materials", []))

    if "prestress_table" not in st.session_state:
        st.session_state["prestress_table"] = _default_prestress_table(prestress_db)
    st.session_state["prestress_table"] = normalize_prestress_table_for_effective_input_sync(pd.DataFrame(st.session_state["prestress_table"]), prestress_db)
    st.session_state.setdefault("prestress_editor_revision", 0)

    summary_slot = st.empty()
    main_col, side_col = st.columns([0.68, 0.32], gap="large")

    with main_col:
        st.markdown("#### Prestress Input Workflow")
        input_mode = st.selectbox("Prestress input mode", ["Manual table", "Linear layout", "Circular layout"])
        if input_mode != "Manual table":
            st.info("Linear and circular prestress layouts are planned for a later milestone. Use Manual table for now.")

        _render_tendon_product_tools()

        st.markdown("#### Advanced Prestress Table")
        st.markdown(
            '<div class="cpmm-prestress-quiet-note">'
            "Compact editor for the fields that normally control analysis: location, product, area, effective prestress, bonded state, and count. "
            "Product/material reference fields are preserved in the backing table and shown below as read-only details."
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="cpmm-prestress-table-note">'
            "Editing Product updates Area/material metadata through the existing product-sync logic. "
            "Breaking Load and Duct ID remain reference data only; they are not used as Pe_eff or steel diameter."
            "</div>",
            unsafe_allow_html=True,
        )
        st.markdown(_input_mode_guide_html(), unsafe_allow_html=True)
        product_options = _product_options_for_table(prestress_db, pd.DataFrame(st.session_state["prestress_table"]))
        show_full_engineering_columns = st.checkbox(
            "Show full engineering columns",
            value=False,
            help="Use only when editing catalog/material reference fields such as fpy, fpu, Ep, duct reference, or strand metadata.",
            key="prestress_show_full_engineering_columns",
        )
        editor_table = _prestress_table_for_editor(st.session_state["prestress_table"])
        editor_column_order = None if show_full_engineering_columns else _compact_column_order_for_table(editor_table)
        editor_key = f"prestress_data_editor_{st.session_state['prestress_editor_revision']}"
        edited_df = st.data_editor(
            editor_table,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_order=editor_column_order,
            column_config={
                "Active": st.column_config.CheckboxColumn("Active"),
                "Label": st.column_config.TextColumn("Label"),
                "Steel Type": st.column_config.SelectboxColumn("Steel Type", options=STEEL_TYPE_OPTIONS),
                "Product": st.column_config.SelectboxColumn("Product", options=product_options),
                "x_mm": st.column_config.NumberColumn("x_mm"),
                "y_mm": st.column_config.NumberColumn("y_mm"),
                "Area_mm2": st.column_config.NumberColumn("Area_mm2"),
                "Diameter_mm": st.column_config.NumberColumn("Diameter_mm"),
                "Eq Steel Dia_mm": st.column_config.NumberColumn("Eq Steel Dia_mm", disabled=True),
                "fpy_MPa": st.column_config.NumberColumn("fpy_MPa"),
                "fpu_MPa": st.column_config.NumberColumn("fpu_MPa"),
                "Ep_MPa": st.column_config.NumberColumn("Ep_MPa"),
                "Input Mode": st.column_config.SelectboxColumn(
                    "Input Mode",
                    options=INPUT_MODE_EDITOR_OPTIONS,
                    help="Choose how effective prestress is entered. The app stores a canonical mode internally and computes the dependent Pe_eff/fpe value after editing.",
                ),
                "Pe_eff_kN": st.column_config.NumberColumn(
                    "Pe_eff_kN",
                    help="Effective prestress force after losses. Used only when Input Mode = Pe_eff; fpe is then computed from Pe_eff / Area.",
                ),
                "fpe_MPa": st.column_config.NumberColumn(
                    "fpe_MPa",
                    help="Effective prestress stress after losses. Used only when Input Mode = fpe; Pe_eff is then computed from Area x fpe.",
                ),
                "fpj_ratio": st.column_config.NumberColumn("fpj_ratio"),
                "loss_percent": st.column_config.NumberColumn("loss_percent"),
                "Bonded": st.column_config.CheckboxColumn("Bonded"),
                "Count": st.column_config.NumberColumn("Count", min_value=1, step=1),
                "Strand Count": st.column_config.NumberColumn("Strand Count", disabled=True),
                "Breaking Load_kN": st.column_config.NumberColumn("Breaking Load_kN", disabled=True),
                "Duct Type": st.column_config.TextColumn("Duct Type", disabled=True),
                "Duct ID_mm": st.column_config.NumberColumn("Duct ID_mm", disabled=True),
                "Note": st.column_config.TextColumn(
                    "Remarks",
                    help="Optional engineering remark for this prestress row. It is not used in calculation.",
                ),
            },
            key=editor_key,
        )
        edited_df = normalize_prestress_table_for_effective_input_sync(edited_df, prestress_db)
        if not _dataframes_equal(edited_df, pd.DataFrame(st.session_state["prestress_table"])):
            st.session_state["prestress_table"] = edited_df
            st.session_state["prestress_editor_revision"] += 1
            st.rerun()
        st.session_state["prestress_table"] = edited_df

        if not show_full_engineering_columns:
            with st.expander("Product / material reference details", expanded=False):
                st.markdown(
                    '<div class="cpmm-prestress-quiet-note">'
                    "Read-only reference view for material/product fields hidden from the compact editor. "
                    "Turn on full engineering columns above only when you intentionally need to edit reference/material fields."
                    "</div>",
                    unsafe_allow_html=True,
                )
                st.dataframe(_prestress_reference_detail_dataframe(edited_df), use_container_width=True, hide_index=True)

    result = prestress_elements_from_dataframe(edited_df, prestress_db)
    geometry = st.session_state.get("section_geometry")
    geometry_errors = validate_prestress_against_geometry(result.elements, geometry)
    valid_for_analysis = prestress_valid_for_analysis(result, geometry_errors)
    st.session_state["prestress_elements"] = result.elements
    st.session_state["prestress_valid_for_analysis"] = valid_for_analysis

    with summary_slot.container():
        _render_prestress_summary_strip(result, geometry_errors, valid_for_analysis)

    with side_col:
        _render_validation(result, geometry_errors, geometry is not None, valid_for_analysis)
        _render_engineering_notes()

    invalid_rows_df = _invalid_prestress_rows_dataframe(edited_df, result.errors)
    if not invalid_rows_df.empty:
        st.markdown("#### Rows Excluded from Analysis")
        st.warning(
            "Rows listed below have validation errors and are not included in Valid elements, Total Aps, Total Pe_eff, Prestress Summary, or PMM/SLS analysis."
        )
        st.dataframe(invalid_rows_df, use_container_width=True, hide_index=True)

    st.markdown("#### Prestress Summary")
    st.caption("Only valid active prestress rows used by analysis are shown here. Rows with validation errors are excluded until corrected.")
    st.dataframe(prestress_summary_dataframe(result.elements), use_container_width=True, hide_index=True)

    if geometry is not None:
        st.markdown("#### Section Preview with Prestress")
        st.plotly_chart(
            create_section_preview(
                geometry,
                st.session_state.get("section_dimensions", []),
                "symbol_value",
                st.session_state.get("rebars", []),
                result.elements,
            ),
            use_container_width=True,
            key="prestress_section_preview",
        )
