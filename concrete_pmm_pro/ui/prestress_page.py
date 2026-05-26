"""Prestress tab UI and parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

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
    list_tendon_products,
    make_custom_tendon_product,
    tendon_product_options,
)
from concrete_pmm_pro.geometry.summary import to_shapely_polygon
from concrete_pmm_pro.visualization import create_section_preview

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESTRESS_DB_PATH = REPO_ROOT / "data" / "prestress_steel_database.csv"

STEEL_TYPE_OPTIONS = ["wire", "strand", "prestressing_bar", "tendon_group", "custom"]
INPUT_MODE_OPTIONS = ["Passive", "Effective Force Pe", "Effective Stress fpe", "Jacking Stress + Losses"]
TENDON_PRODUCT_CREATION_MODES = ["Standard tendon product", "Custom tendon"]

# Internal editor bookkeeping columns.  They are kept out of the visible
# Streamlit table, but let us detect a true Product change so automatic
# product defaults do not overwrite deliberate user overrides on every rerun.
_INTERNAL_PRESTRESS_COLUMNS = ["_last_product"]



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


def _looks_like_15_2mm_tendon_group(row: pd.Series) -> bool:
    steel_type = "" if _is_blank(row.get("Steel Type")) else str(row.get("Steel Type")).strip()
    if steel_type != "tendon_group":
        return False
    product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
    if get_tendon_product(product) is not None or product.startswith("6-"):
        return True
    strand_count = _to_float(row.get("Strand Count"))
    strand_diameter = _to_float(row.get("Strand Diameter_mm"))
    if strand_count is None:
        return False
    return strand_diameter is None or abs(strand_diameter - DEFAULT_STRAND_DIAMETER_MM) < 1e-6


def _normalize_prestress_table_for_display(table: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.DataFrame(table).copy()
    if normalized.empty:
        return normalized
    for column in ("Diameter_mm", "fpy_MPa", "fpu_MPa", "Ep_MPa", "Strand Count", "Strand Diameter_mm", "Strand Area_mm2", "Breaking Load_kN", "Duct Type", "Duct ID_mm"):
        if column not in normalized.columns:
            normalized[column] = None
    normalized["Diameter_mm"] = normalized["Diameter_mm"].astype("object")
    if "Eq Steel Dia_mm" not in normalized.columns:
        insert_at = normalized.columns.get_loc("Diameter_mm") + 1 if "Diameter_mm" in normalized.columns else len(normalized.columns)
        normalized.insert(insert_at, "Eq Steel Dia_mm", None)
    for index, row in normalized.iterrows():
        product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
        tendon_product = get_tendon_product(product)
        is_tendon_group = str(row.get("Steel Type") or "").strip() == "tendon_group" or tendon_product is not None
        if is_tendon_group:
            normalized.at[index, "Steel Type"] = "tendon_group"
            normalized.at[index, "Diameter_mm"] = None
            if tendon_product is not None:
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
        area_mm2 = _to_float(normalized.at[index, "Area_mm2"] if "Area_mm2" in normalized.columns else None)
        normalized.at[index, "Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(area_mm2) if is_tendon_group else None
    return normalized


_PRESTRESS_EDITOR_COLUMNS = [
    "Active",
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
    "fpe_MPa",
    "fpj_ratio",
    "loss_percent",
    "Bonded",
    "Count",
    "Strand Count",
    "Breaking Load_kN",
    "Duct Type",
    "Duct ID_mm",
    "Note",
]


def _ensure_prestress_editor_columns(table: pd.DataFrame) -> pd.DataFrame:
    """Return a table with all user-facing and internal editor columns present.

    Streamlit's data editor reruns after each edit.  Keeping a stable column set
    avoids columns appearing/disappearing between reruns and lets us hide the
    internal Product-tracking column without losing it from session state.
    """
    normalized = pd.DataFrame(table).copy()
    for column in _PRESTRESS_EDITOR_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None
    for column in _INTERNAL_PRESTRESS_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = None
    ordered = [column for column in [*_PRESTRESS_EDITOR_COLUMNS, *_INTERNAL_PRESTRESS_COLUMNS] if column in normalized.columns]
    extra = [column for column in normalized.columns if column not in ordered]
    return normalized[[*ordered, *extra]]


def _fill_from_database_product(
    normalized: pd.DataFrame,
    index: Any,
    database_row: pd.Series,
    *,
    force: bool,
) -> None:
    """Populate row fields from a catalog prestress product.

    Product changes should fill the dependent fields immediately.  When the
    Product is unchanged, blanks may still be backfilled, but deliberate user
    overrides are preserved.
    """
    defaults = {
        "Steel Type": str(database_row["type"]),
        "Area_mm2": float(database_row["area_mm2"]),
        "Diameter_mm": None if pd.isna(database_row["diameter_mm"]) else float(database_row["diameter_mm"]),
        "fpy_MPa": None if pd.isna(database_row["fpy_MPa"]) else float(database_row["fpy_MPa"]),
        "fpu_MPa": None if pd.isna(database_row["fpu_MPa"]) else float(database_row["fpu_MPa"]),
        "Ep_MPa": float(database_row["Ep_MPa"]),
    }
    for column, value in defaults.items():
        if force or _is_blank(normalized.at[index, column]):
            normalized.at[index, column] = value
    normalized.at[index, "Eq Steel Dia_mm"] = None


def _fill_from_tendon_product(
    normalized: pd.DataFrame,
    index: Any,
    product: TendonProduct,
    *,
    force: bool,
) -> None:
    """Populate a tendon_group row from standard/custom tendon reference data.

    Duct ID and breaking load are reference metadata only.  Pe_eff/fpe are not
    touched here; they remain user-controlled engineering inputs.
    """
    defaults = {
        "Steel Type": "tendon_group",
        "Area_mm2": product.tendon_area_mm2,
        "Diameter_mm": None,
        "fpy_MPa": product.fpy_MPa,
        "fpu_MPa": product.fpu_MPa,
        "Ep_MPa": product.Ep_MPa,
        "Strand Count": product.strand_count,
        "Strand Diameter_mm": product.strand_diameter_mm,
        "Strand Area_mm2": product.strand_area_mm2,
        "Breaking Load_kN": product.breaking_load_kN,
        "Duct Type": product.duct_type or "",
        "Duct ID_mm": product.duct_id_mm,
    }
    for column, value in defaults.items():
        if column == "Diameter_mm" or force or _is_blank(normalized.at[index, column]):
            normalized.at[index, column] = value
    normalized.at[index, "Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(_to_float(normalized.at[index, "Area_mm2"]))


def _normalize_prestress_table_for_editor(table: pd.DataFrame, prestress_db: pd.DataFrame) -> pd.DataFrame:
    """Normalize the Advanced Prestress Table for immediate UI feedback.

    The critical Streamlit detail is timing: if a user changes Product in
    st.data_editor, dependent columns (Area, Diameter, material strengths, duct
    metadata) must be pushed back into session_state and rerun immediately.
    This function is intentionally UI/data-normalization only.  It does not
    compute Pe_eff from breaking load and does not change solver behavior.
    """
    normalized = _ensure_prestress_editor_columns(table)
    normalized["Diameter_mm"] = normalized["Diameter_mm"].astype("object")

    for index, row in normalized.iterrows():
        product = "" if _is_blank(row.get("Product")) else str(row.get("Product")).strip()
        last_product = "" if _is_blank(row.get("_last_product")) else str(row.get("_last_product")).strip()
        product_changed = product != last_product
        tendon_product = get_tendon_product(product)
        database_row = _product_row(product, prestress_db)

        if tendon_product is not None:
            _fill_from_tendon_product(normalized, index, tendon_product, force=product_changed)
        elif database_row is not None:
            _fill_from_database_product(normalized, index, database_row, force=product_changed)
        else:
            steel_type = "" if _is_blank(normalized.at[index, "Steel Type"]) else str(normalized.at[index, "Steel Type"]).strip()
            is_tendon_group = steel_type == "tendon_group" or _looks_like_15_2mm_tendon_group(normalized.loc[index])
            if is_tendon_group:
                normalized.at[index, "Steel Type"] = "tendon_group"
                normalized.at[index, "Diameter_mm"] = None
                if _is_blank(normalized.at[index, "fpy_MPa"]):
                    normalized.at[index, "fpy_MPa"] = DEFAULT_STRAND_FPY_MPA
                if _is_blank(normalized.at[index, "fpu_MPa"]):
                    normalized.at[index, "fpu_MPa"] = DEFAULT_STRAND_FPU_MPA
                if _is_blank(normalized.at[index, "Ep_MPa"]):
                    normalized.at[index, "Ep_MPa"] = DEFAULT_STRAND_EP_MPA
                normalized.at[index, "Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(_to_float(normalized.at[index, "Area_mm2"]))
            else:
                normalized.at[index, "Eq Steel Dia_mm"] = None

        # Keep internal tracking after all product-driven defaults are applied.
        normalized.at[index, "_last_product"] = product

    return normalized


def _visible_prestress_table_changed(before: pd.DataFrame, after: pd.DataFrame) -> bool:
    """Return True when the user-visible editor values changed after sync.

    Hidden bookkeeping columns should not trigger reruns by themselves.  This
    avoids infinite rerun loops while still refreshing the table immediately
    when Product selection fills dependent visible fields.
    """
    before_visible = _ensure_prestress_editor_columns(before)[_PRESTRESS_EDITOR_COLUMNS].reset_index(drop=True)
    after_visible = _ensure_prestress_editor_columns(after)[_PRESTRESS_EDITOR_COLUMNS].reset_index(drop=True)
    return not before_visible.astype("object").where(pd.notna(before_visible), None).equals(
        after_visible.astype("object").where(pd.notna(after_visible), None)
    )


def _tendon_product_summary_dataframe(products: list[TendonProduct]) -> pd.DataFrame:
    return pd.DataFrame([product.as_dict() for product in products])


def _product_from_row_label(product: str) -> TendonProduct | None:
    return get_tendon_product(product)


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
    input_mode = str(row.get("Input Mode") or "Passive").strip()

    if input_mode not in INPUT_MODE_OPTIONS:
        errors.append(f"Row {row_number}: Input Mode must be one of {', '.join(INPUT_MODE_OPTIONS)}.")
        return 0.0, 0.0, 0.0, errors, warnings, info

    if input_mode == "Passive":
        return 0.0, 0.0, 0.0, errors, warnings, info

    if input_mode == "Effective Force Pe":
        pe_kn = _pe_eff_kn_from_row(row)
        if pe_kn is None:
            errors.append(f"Row {row_number}: Pe_eff_kN must be numeric for Effective Force Pe mode.")
            return 0.0, 0.0, 0.0, errors, warnings, info
        if pe_kn < 0:
            errors.append(f"Row {row_number}: Pe_eff_kN must be greater than or equal to zero.")
            return 0.0, 0.0, 0.0, errors, warnings, info
        pe_eff_n = kN_to_N(pe_kn)
        initial_stress_mpa = pe_eff_n / area_mm2
        if fpu_mpa is not None:
            fpu_value = float(fpu_mpa)
            if initial_stress_mpa > fpu_value:
                errors.append(f"Row {row_number}: Initial prestress stress from Pe_eff exceeds fpu_MPa.")
                return 0.0, 0.0, 0.0, errors, warnings, info
            if initial_stress_mpa > 0.85 * fpu_value:
                warnings.append(
                    f"Row {row_number}: Initial prestress stress is high relative to fpu_MPa. "
                    "Please verify jacking and loss assumptions."
                )
        if pe_eff_n == 0:
            info.append(f"Row {row_number}: Pe_eff is zero; element is effectively passive.")
        return pe_eff_n, initial_stress_mpa, initial_stress_mpa / ep_mpa, errors, warnings, info

    if input_mode == "Effective Stress fpe":
        fpe_mpa = _to_float(row.get("fpe_MPa"))
        if fpe_mpa is None:
            errors.append(f"Row {row_number}: fpe_MPa must be numeric for Effective Stress fpe mode.")
            return 0.0, 0.0, 0.0, errors, warnings, info
        if fpe_mpa < 0:
            errors.append(f"Row {row_number}: fpe_MPa must be greater than or equal to zero.")
        if fpu_mpa is not None and fpe_mpa > float(fpu_mpa):
            errors.append(f"Row {row_number}: fpe_MPa must not exceed fpu_MPa.")
        if errors:
            return 0.0, 0.0, 0.0, errors, warnings, info
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
        "Pe_eff and fpe are user-entered effective prestress inputs; product breaking load is reference data only.",
        "Duct ID is duct reference information and is not steel diameter.",
        "For tendon_group rows, Area_mm2 controls steel area; Eq Steel Dia_mm is display and preview information only.",
        "Prestress is treated as internal section action, not external Pu demand.",
    ]
    items = "".join(f'<div class="cpmm-prestress-note-item">{escape(note)}</div>' for note in notes)
    return f'<div class="cpmm-prestress-note-panel">{items}</div>'


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
        PrestressMetric("Active elements", f"{len(result.elements):,}", status="info"),
        PrestressMetric("Total Aps", f"{total_aps:,.1f} mm2"),
        PrestressMetric("Total Pe_eff", f"{total_pe_kn:,.1f} kN"),
        PrestressMetric("Analysis readiness", "Yes" if valid_for_analysis else "No", status="ready" if valid_for_analysis else "danger", strong=True),
        PrestressMetric("Tendon groups", f"{tendon_group_count:,}", detail=f"Strand/PT bars: {strand_pt_count:,}"),
        PrestressMetric("Bonded state", f"{bonded_count:,} / {unbonded_count:,}", detail="bonded / unbonded", status="warning" if unbonded_count else "neutral"),
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
        PrestressMetric("Active elements", f"{len(result.elements):,}"),
        PrestressMetric("Total Aps", f"{total_aps:,.1f} mm2"),
        PrestressMetric("Total Pe_eff", f"{total_pe_kn:,.1f} kN"),
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
        product_label = st.selectbox("Standard tendon product", tendon_product_options(), index=tendon_product_options().index("6-12") if "6-12" in tendon_product_options() else 0)
        product = get_tendon_product(product_label)
        assert product is not None
        st.dataframe(_tendon_product_summary_dataframe([product]), use_container_width=True, hide_index=True)
        row = apply_tendon_product_to_row(base_row, product)
        if st.button("Add standard tendon to table", use_container_width=True):
            st.session_state["prestress_table"] = _normalize_prestress_table_for_editor(
                _append_prestress_row(pd.DataFrame(current_table), row),
                _combined_prestress_database(load_prestress_steel_database(), st.session_state.get("prestress_materials", [])),
            )
            st.session_state["prestress_editor_revision"] = int(st.session_state.get("prestress_editor_revision", 0)) + 1
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
        st.session_state["prestress_table"] = _normalize_prestress_table_for_editor(
            _append_prestress_row(pd.DataFrame(current_table), row),
            _combined_prestress_database(load_prestress_steel_database(), st.session_state.get("prestress_materials", [])),
        )
        st.session_state["prestress_editor_revision"] = int(st.session_state.get("prestress_editor_revision", 0)) + 1
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
    if "prestress_editor_revision" not in st.session_state:
        st.session_state["prestress_editor_revision"] = 0
    st.session_state["prestress_table"] = _normalize_prestress_table_for_editor(
        pd.DataFrame(st.session_state["prestress_table"]),
        prestress_db,
    )

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
            "Review and edit prestress element locations, effective prestress, bonded flag, material values, and notes. "
            "Product selection only helps populate product geometry and material reference data."
            "</div>",
            unsafe_allow_html=True,
        )
        product_options = _product_options_for_table(prestress_db, pd.DataFrame(st.session_state["prestress_table"]))
        editor_key = f"prestress_data_editor_{st.session_state.get('prestress_editor_revision', 0)}"
        edited_df = st.data_editor(
            st.session_state["prestress_table"],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_order=_PRESTRESS_EDITOR_COLUMNS,
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
                "Input Mode": st.column_config.SelectboxColumn("Input Mode", options=INPUT_MODE_OPTIONS),
                "Pe_eff_kN": st.column_config.NumberColumn("Pe_eff_kN"),
                "fpe_MPa": st.column_config.NumberColumn("fpe_MPa"),
                "fpj_ratio": st.column_config.NumberColumn("fpj_ratio"),
                "loss_percent": st.column_config.NumberColumn("loss_percent"),
                "Bonded": st.column_config.CheckboxColumn("Bonded"),
                "Count": st.column_config.NumberColumn("Count", min_value=1, step=1),
                "Strand Count": st.column_config.NumberColumn("Strand Count", disabled=True),
                "Breaking Load_kN": st.column_config.NumberColumn("Breaking Load_kN", disabled=True),
                "Duct Type": st.column_config.TextColumn("Duct Type", disabled=True),
                "Duct ID_mm": st.column_config.NumberColumn("Duct ID_mm", disabled=True),
                "Note": st.column_config.TextColumn("Note"),
                "_last_product": None,
            },
            key=editor_key,
        )
        synced_df = _normalize_prestress_table_for_editor(edited_df, prestress_db)
        if _visible_prestress_table_changed(edited_df, synced_df):
            st.session_state["prestress_table"] = synced_df
            st.session_state["prestress_editor_revision"] = int(st.session_state.get("prestress_editor_revision", 0)) + 1
            st.rerun()
        edited_df = synced_df
        st.session_state["prestress_table"] = edited_df

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

    st.markdown("#### Prestress Summary")
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
