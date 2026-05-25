"""Materials tab UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from concrete_pmm_pro.code_checks import aci_beta1
from concrete_pmm_pro.core.models import ConcreteMaterial, PrestressSteelMaterial, RebarMaterial

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PRESTRESS_DB_PATH = REPO_ROOT / "data" / "prestress_steel_database.csv"
STEEL_TYPE_OPTIONS = ["wire", "strand", "prestressing_bar", "tendon_group", "custom"]


def load_prestress_steel_database(path: Path | str = DEFAULT_PRESTRESS_DB_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def default_rebar_materials() -> list[RebarMaterial]:
    return [
        RebarMaterial(name="SD40", fy_MPa=400.0, Es_MPa=200000.0),
        RebarMaterial(name="SD50", fy_MPa=500.0, Es_MPa=200000.0),
    ]


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _optional_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    parsed = float(value)
    return parsed if parsed > 0 else None


def _bool_from_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if _is_blank(value):
        return False
    return str(value).strip().lower() in {"true", "1", "yes"}


def prestress_material_from_database_row(row: pd.Series) -> PrestressSteelMaterial:
    return PrestressSteelMaterial(
        name=str(row["name"]),
        steel_type=str(row["type"]),
        diameter_mm=None if pd.isna(row["diameter_mm"]) else float(row["diameter_mm"]),
        area_mm2=None if pd.isna(row["area_mm2"]) else float(row["area_mm2"]),
        grade=None if pd.isna(row["grade"]) else str(row["grade"]),
        fpy_MPa=None if pd.isna(row["fpy_MPa"]) else float(row["fpy_MPa"]),
        fpu_MPa=float(row["fpu_MPa"]),
        Ep_MPa=float(row["Ep_MPa"]),
        relaxation_class=None,
        source=None if pd.isna(row["source"]) else str(row["source"]),
        area_source=None if pd.isna(row["area_source"]) else str(row["area_source"]),
        is_catalog_verified=_bool_from_value(row["is_catalog_verified"]),
    )


def _upsert_by_name(items: list[PrestressSteelMaterial], material: PrestressSteelMaterial) -> list[PrestressSteelMaterial]:
    return [item for item in items if item.name != material.name] + [material]


def _default_prestress_materials() -> list[PrestressSteelMaterial]:
    db = load_prestress_steel_database()
    names = set(db["name"])
    defaults = ["15.2mm strand"]
    if "PS Bar 32 - 1080/1230" in names:
        defaults.append("PS Bar 32 - 1080/1230")
    return [prestress_material_from_database_row(db.loc[db["name"] == name].iloc[0]) for name in defaults if name in names]


def _ensure_material_defaults() -> None:
    if "concrete_material" not in st.session_state:
        st.session_state["concrete_material"] = ConcreteMaterial(fc_MPa=35.0, beta1=aci_beta1(35.0))
    if "rebar_materials" not in st.session_state or not st.session_state["rebar_materials"]:
        st.session_state["rebar_materials"] = default_rebar_materials()
    if "prestress_materials" not in st.session_state or not st.session_state["prestress_materials"]:
        st.session_state["prestress_materials"] = _default_prestress_materials()
    st.session_state.setdefault("active_rebar_material_name", st.session_state["rebar_materials"][0].name)
    st.session_state.setdefault("active_prestress_material_name", st.session_state["prestress_materials"][0].name)


def _render_concrete_section() -> None:
    st.subheader("Concrete Material")
    current: ConcreteMaterial = st.session_state["concrete_material"]
    cols = st.columns(4)
    with cols[0]:
        name = st.text_input("Concrete name", value=current.name)
    with cols[1]:
        fc_MPa = st.number_input("f'c, MPa", min_value=0.1, value=float(current.fc_MPa), step=1.0)
    with cols[2]:
        ecu = st.number_input("ecu", min_value=0.0001, value=float(current.ecu), step=0.0001, format="%.4f")
    with cols[3]:
        density = st.number_input("density, kg/m3", min_value=1.0, value=float(current.density_kg_m3), step=10.0)

    beta1_mode = st.radio("beta1 mode", ["Auto by ACI", "Manual"], horizontal=True)
    beta1_value = aci_beta1(fc_MPa)
    if beta1_mode == "Manual":
        beta1_value = st.number_input("beta1 manual", min_value=0.01, max_value=1.0, value=float(current.beta1 or beta1_value), step=0.01)
    note = st.text_area("Concrete note", value=current.note or "", height=80)

    try:
        material = ConcreteMaterial(name=name, fc_MPa=fc_MPa, ecu=ecu, density_kg_m3=density, beta1=beta1_value, note=note or None)
        st.session_state["concrete_material"] = material
        st.success("Concrete material is valid.")
    except ValidationError as exc:
        st.error(f"Concrete material error: {exc.errors()[0]['msg']}")


def _rebar_materials_dataframe(materials: list[RebarMaterial]) -> pd.DataFrame:
    return pd.DataFrame([material.model_dump() for material in materials])


def _parse_rebar_materials(df: pd.DataFrame) -> tuple[list[RebarMaterial], list[str]]:
    materials: list[RebarMaterial] = []
    errors: list[str] = []
    for index, row in df.iterrows():
        row_number = int(index) + 1
        if all(_is_blank(row.get(column)) for column in ["name", "fy_MPa", "Es_MPa", "note"]):
            continue
        try:
            materials.append(
                RebarMaterial(
                    name=str(row.get("name")).strip(),
                    fy_MPa=float(row.get("fy_MPa")),
                    Es_MPa=float(row.get("Es_MPa")),
                    note=None if _is_blank(row.get("note")) else str(row.get("note")),
                )
            )
        except (TypeError, ValueError, ValidationError) as exc:
            errors.append(f"Row {row_number}: invalid rebar material ({exc}).")
    return materials, errors


def _render_rebar_section() -> None:
    st.subheader("Rebar Material")
    edited_df = st.data_editor(
        _rebar_materials_dataframe(st.session_state["rebar_materials"]),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Material name"),
            "fy_MPa": st.column_config.NumberColumn("fy, MPa", min_value=0.1),
            "Es_MPa": st.column_config.NumberColumn("Es, MPa", min_value=0.1),
            "note": st.column_config.TextColumn("Note"),
        },
        key="rebar_materials_editor",
    )
    materials, errors = _parse_rebar_materials(edited_df)
    if errors:
        for error in errors:
            st.error(error)
    elif materials:
        st.session_state["rebar_materials"] = materials
        active_names = [material.name for material in materials]
        active_name = st.session_state.get("active_rebar_material_name")
        active_index = active_names.index(active_name) if active_name in active_names else 0
        st.session_state["active_rebar_material_name"] = st.selectbox("Active rebar material", active_names, index=active_index)
        st.success("Rebar materials are valid.")


def _render_prestress_section() -> None:
    st.subheader("Prestressing Steel Material")
    st.info(
        "PT Bar / Prestressing Bar material properties must include fpu, Ep, and preferably fpy or proof stress. "
        "Effective prestress force is defined later in the Prestress tab."
    )

    db = load_prestress_steel_database()
    mode = st.radio("Prestressing steel material input", ["Select from prestress_steel_database.csv", "Custom material"], horizontal=True)

    if mode == "Select from prestress_steel_database.csv":
        product = st.selectbox("Database product", [str(name) for name in db["name"].tolist()])
        row = db.loc[db["name"] == product].iloc[0]
        selected_material = prestress_material_from_database_row(row)
        st.dataframe(pd.DataFrame([selected_material.model_dump()]), use_container_width=True, hide_index=True)
        if st.button("Add selected product to project materials", use_container_width=True):
            st.session_state["prestress_materials"] = _upsert_by_name(st.session_state["prestress_materials"], selected_material)
            st.session_state["active_prestress_material_name"] = selected_material.name
            st.success(f"Added {selected_material.name}.")

    else:
        cols = st.columns(3)
        with cols[0]:
            name = st.text_input("Material name", value="Custom PT Bar")
            steel_type = st.selectbox("Steel type", STEEL_TYPE_OPTIONS, index=STEEL_TYPE_OPTIONS.index("prestressing_bar"))
            diameter_mm = _optional_float(st.number_input("Diameter, mm", min_value=0.0, value=32.0, step=1.0))
        with cols[1]:
            area_mm2 = _optional_float(st.number_input("Area, mm2", min_value=0.0, value=804.2, step=1.0))
            grade = st.text_input("Grade", value="1080/1230")
            fpy_MPa = _optional_float(st.number_input("fpy, MPa", min_value=0.0, value=1080.0, step=10.0))
        with cols[2]:
            fpu_MPa = st.number_input("fpu, MPa", min_value=0.1, value=1230.0, step=10.0)
            Ep_MPa = st.number_input("Ep, MPa", min_value=0.1, value=200000.0, step=1000.0)
            relaxation_class = st.text_input("Relaxation class", value="")

        source = st.text_input("Source", value="project_custom")
        area_source = st.text_input("Area source", value="manual")
        is_catalog_verified = st.checkbox("Catalog verified", value=False)
        note = st.text_area("Prestress material note", value="")

        if st.button("Add / Update Custom Prestress Material", use_container_width=True):
            try:
                material = PrestressSteelMaterial(
                    name=name,
                    steel_type=steel_type,
                    diameter_mm=diameter_mm,
                    area_mm2=area_mm2,
                    grade=grade or None,
                    fpy_MPa=fpy_MPa,
                    fpu_MPa=fpu_MPa,
                    Ep_MPa=Ep_MPa,
                    relaxation_class=relaxation_class or None,
                    source=source or None,
                    area_source=area_source or None,
                    is_catalog_verified=is_catalog_verified,
                    note=note or None,
                )
                st.session_state["prestress_materials"] = _upsert_by_name(st.session_state["prestress_materials"], material)
                st.session_state["active_prestress_material_name"] = material.name
                st.success(f"Added {material.name}.")
            except ValidationError as exc:
                st.error(f"Prestressing steel material error: {exc.errors()[0]['msg']}")

    materials: list[PrestressSteelMaterial] = st.session_state["prestress_materials"]
    active_names = [material.name for material in materials]
    active_name = st.session_state.get("active_prestress_material_name")
    active_index = active_names.index(active_name) if active_name in active_names else 0
    st.session_state["active_prestress_material_name"] = st.selectbox("Active prestress material", active_names, index=active_index)


def _render_summary() -> None:
    st.subheader("Material Summary")
    concrete: ConcreteMaterial = st.session_state["concrete_material"]
    cols = st.columns(3)
    cols[0].metric("Concrete f'c", f"{concrete.fc_MPa:g} MPa")
    cols[1].metric("Concrete beta1", f"{(concrete.beta1 or aci_beta1(concrete.fc_MPa)):.3g}")
    cols[2].metric("Concrete ecu", f"{concrete.ecu:g}")

    st.markdown("**Rebar materials**")
    st.dataframe(_rebar_materials_dataframe(st.session_state["rebar_materials"]), use_container_width=True, hide_index=True)

    st.markdown("**Prestressing steel materials**")
    prestress_rows = []
    for material in st.session_state["prestress_materials"]:
        row = material.model_dump()
        row["PT Bar / Prestressing Bar"] = material.steel_type == "prestressing_bar"
        prestress_rows.append(row)
    st.dataframe(pd.DataFrame(prestress_rows), use_container_width=True, hide_index=True)


def render_materials_page() -> None:
    st.subheader("Materials")
    _ensure_material_defaults()
    _render_concrete_section()
    st.divider()
    _render_rebar_section()
    st.divider()
    _render_prestress_section()
    st.divider()
    _render_summary()
