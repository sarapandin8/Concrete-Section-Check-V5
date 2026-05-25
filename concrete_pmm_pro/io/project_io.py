"""Project JSON serialization helpers."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from typing import Any

import pandas as pd
from pydantic import ValidationError

from concrete_pmm_pro.core.analysis import AnalysisModeSettings, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar
from concrete_pmm_pro.core.project import ProjectModel
from concrete_pmm_pro.core.units import N_to_kN, Nmm_to_kNm
from concrete_pmm_pro.data.prestress_tendon_products import (
    DEFAULT_STRAND_DIAMETER_MM,
    DEFAULT_STRAND_EP_MPA,
    DEFAULT_STRAND_FPU_MPA,
    DEFAULT_STRAND_FPY_MPA,
    equivalent_steel_diameter_mm,
    get_tendon_product,
)
from concrete_pmm_pro.serviceability.models import ServiceabilitySettings
from concrete_pmm_pro.serviceability.points import stress_check_points_to_dataframe


class ProjectIOError(ValueError):
    """Raised when project JSON cannot be parsed or validated."""


def _get_session_value(session_state: Any, key: str, default: Any = None) -> Any:
    if hasattr(session_state, "get"):
        return session_state.get(key, default)
    return getattr(session_state, key, default)


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == ""


def _clean_table_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _prestress_table_metadata_from_session(session_state: Any) -> list[dict[str, Any]]:
    table = _get_session_value(session_state, "prestress_table", None)
    if table is None:
        return []
    df = pd.DataFrame(table)
    if df.empty:
        return []
    metadata_columns = [
        "Label",
        "Steel Type",
        "Product",
        "Area_mm2",
        "Diameter_mm",
        "Eq Steel Dia_mm",
        "fpy_MPa",
        "fpu_MPa",
        "Ep_MPa",
        "Strand Count",
        "Strand Diameter_mm",
        "Strand Area_mm2",
        "Breaking Load_kN",
        "Duct Type",
        "Duct ID_mm",
        "Tendon Description",
        "Typical Use",
        "Note",
    ]
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        entry = {column: _clean_table_value(row.get(column)) for column in metadata_columns if column in df.columns}
        if any(not _is_blank(value) for value in entry.values()):
            rows.append(entry)
    return rows


def project_from_session_state(session_state: Any) -> ProjectModel:
    metadata = dict(_get_session_value(session_state, "project_metadata", {}) or {})
    for flag_name in ("rebars_valid_for_analysis", "prestress_valid_for_analysis"):
        flag_value = _get_session_value(session_state, flag_name, None)
        if flag_value is not None:
            metadata[flag_name] = flag_value
    prestress_table_metadata = _prestress_table_metadata_from_session(session_state)
    if prestress_table_metadata:
        metadata["prestress_table_metadata"] = prestress_table_metadata

    return ProjectModel(
        project_name=_get_session_value(session_state, "project_name", "Untitled Project") or "Untitled Project",
        designer=_get_session_value(session_state, "designer", None),
        description=_get_session_value(session_state, "description", None),
        code=_get_session_value(session_state, "design_code", _get_session_value(session_state, "code", "ACI 318")) or "ACI 318",
        section_preset_key=_get_session_value(session_state, "section_preset_key", None),
        section_preset_name=_get_session_value(session_state, "section_preset_name", None),
        section_parameters=dict(_get_session_value(session_state, "section_parameters", {}) or {}),
        section_geometry=_get_session_value(session_state, "section_geometry", None),
        concrete_material=_get_session_value(session_state, "concrete_material", ConcreteMaterial()),
        concrete_materials=_coerce_list(_get_session_value(session_state, "concrete_materials", [])),
        rebar_materials=_coerce_list(_get_session_value(session_state, "rebar_materials", [])),
        prestress_materials=_coerce_list(_get_session_value(session_state, "prestress_materials", [])),
        active_rebar_material_name=_get_session_value(session_state, "active_rebar_material_name", None),
        active_prestress_material_name=_get_session_value(session_state, "active_prestress_material_name", None),
        loads=_coerce_list(_get_session_value(session_state, "load_cases", [])),
        rebars=_coerce_list(_get_session_value(session_state, "rebars", [])),
        prestress_elements=_coerce_list(_get_session_value(session_state, "prestress_elements", [])),
        analysis_mode_settings=_get_session_value(session_state, "analysis_mode_settings", AnalysisModeSettings()),
        analysis_settings=_get_session_value(session_state, "analysis_settings", AnalysisSettings()),
        serviceability_settings=_get_session_value(session_state, "serviceability_settings", ServiceabilitySettings()),
        custom_stress_check_points=_coerce_list(_get_session_value(session_state, "custom_stress_check_points", [])),
        include_default_stress_check_points=bool(
            _get_session_value(session_state, "include_default_stress_check_points", True)
        ),
        metadata=metadata,
    )


def project_to_json(project: ProjectModel) -> str:
    return project.model_dump_json(indent=2)


def _migrate_legacy_data(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    legacy_project_fields = {
        "load_cases": "loads",
        "prestress": "prestress_elements",
        "tendons": "prestress_elements",
        "geometry": "section_geometry",
        "preset_key": "section_preset_key",
        "preset_name": "section_preset_name",
        "parameters": "section_parameters",
        "design_code": "code",
    }
    for old_name, new_name in legacy_project_fields.items():
        if old_name in migrated and new_name not in migrated:
            migrated[new_name] = migrated.pop(old_name)

    prestress_items = migrated.get("prestress_elements")
    if isinstance(prestress_items, list):
        for item in prestress_items:
            if not isinstance(item, dict):
                continue
            if "Pe_eff_N" in item and "pe_eff_n" not in item:
                item["pe_eff_n"] = item.pop("Pe_eff_N")
            if "Ep_MPa" in item and "ep_mpa" not in item:
                item["ep_mpa"] = item.pop("Ep_MPa")
            if "fpy_MPa" in item and "fpy_mpa" not in item:
                item["fpy_mpa"] = item.pop("fpy_MPa")
            if "fpu_MPa" in item and "fpu_mpa" not in item:
                item["fpu_mpa"] = item.pop("fpu_MPa")

    return migrated


def project_from_json(json_text: str) -> ProjectModel:
    try:
        raw_data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ProjectIOError(f"Invalid project JSON: {exc.msg}") from exc

    if not isinstance(raw_data, dict):
        raise ProjectIOError("Invalid project JSON: root value must be an object.")

    try:
        return ProjectModel.model_validate(_migrate_legacy_data(raw_data))
    except ValidationError as exc:
        first_error = exc.errors()[0]
        location = ".".join(str(part) for part in first_error.get("loc", ())) or "project"
        raise ProjectIOError(f"Invalid project data at {location}: {first_error.get('msg', 'validation failed')}") from exc


def _loads_to_table(loads: list[LoadCase]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": load_case.active,
                "Combo Name": load_case.name,
                "Pu": N_to_kN(load_case.Pu_N),
                "Mux": Nmm_to_kNm(load_case.Mux_Nmm),
                "Muy": Nmm_to_kNm(load_case.Muy_Nmm),
                "Load Type": load_case.load_type,
                "Note": load_case.note or "",
            }
            for load_case in loads
        ]
    )


def _rebars_to_table(rebars: list[Rebar]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": True,
                "Label": rebar.label or f"B{index}",
                "x_mm": rebar.x_mm,
                "y_mm": rebar.y_mm,
                "Bar Size": "Custom",
                "Diameter_mm": rebar.diameter_mm,
                "Material": rebar.material_name,
                "Count": 1,
                "Note": "",
            }
            for index, rebar in enumerate(rebars, start=1)
        ]
    )


def _prestress_metadata_for_row(
    table_metadata: list[dict[str, Any]],
    index: int,
    label: str,
) -> dict[str, Any]:
    for row in table_metadata:
        if str(row.get("Label") or "").strip() == label:
            return row
    if index - 1 < len(table_metadata):
        return table_metadata[index - 1]
    return {}


def _restore_tendon_product_metadata(row: dict[str, Any]) -> dict[str, Any]:
    product = str(row.get("Product") or "").strip()
    tendon_product = get_tendon_product(product)
    if tendon_product is None:
        return row
    restored = dict(row)
    restored["Steel Type"] = "tendon_group"
    restored["Area_mm2"] = tendon_product.tendon_area_mm2
    restored["Diameter_mm"] = None
    restored["Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(tendon_product.tendon_area_mm2)
    restored["fpy_MPa"] = tendon_product.fpy_MPa
    restored["fpu_MPa"] = tendon_product.fpu_MPa
    restored["Ep_MPa"] = tendon_product.Ep_MPa
    restored["Strand Count"] = tendon_product.strand_count
    restored["Strand Diameter_mm"] = tendon_product.strand_diameter_mm
    restored["Strand Area_mm2"] = tendon_product.strand_area_mm2
    restored["Breaking Load_kN"] = tendon_product.breaking_load_kN
    restored["Duct Type"] = tendon_product.duct_type or ""
    restored["Duct ID_mm"] = tendon_product.duct_id_mm
    restored["Tendon Description"] = tendon_product.description
    restored["Typical Use"] = tendon_product.typical_use or ""
    return restored


def _looks_like_15_2mm_tendon_group(row: dict[str, Any]) -> bool:
    if str(row.get("Steel Type") or "").strip() != "tendon_group":
        return False
    product = str(row.get("Product") or "").strip()
    if get_tendon_product(product) is not None or product.startswith("6-"):
        return True
    strand_count = row.get("Strand Count")
    if _is_blank(strand_count):
        return False
    strand_diameter = row.get("Strand Diameter_mm")
    if _is_blank(strand_diameter):
        return True
    try:
        return abs(float(strand_diameter) - DEFAULT_STRAND_DIAMETER_MM) < 1e-6
    except (TypeError, ValueError):
        return False


def _normalize_tendon_group_table_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if str(normalized.get("Steel Type") or "").strip() != "tendon_group":
        return normalized
    normalized["Diameter_mm"] = None
    area = normalized.get("Area_mm2")
    try:
        normalized["Eq Steel Dia_mm"] = equivalent_steel_diameter_mm(float(area)) if not _is_blank(area) else None
    except (TypeError, ValueError):
        normalized["Eq Steel Dia_mm"] = None
    if _looks_like_15_2mm_tendon_group(normalized):
        if _is_blank(normalized.get("fpy_MPa")):
            normalized["fpy_MPa"] = DEFAULT_STRAND_FPY_MPA
        if _is_blank(normalized.get("fpu_MPa")):
            normalized["fpu_MPa"] = DEFAULT_STRAND_FPU_MPA
        if _is_blank(normalized.get("Ep_MPa")):
            normalized["Ep_MPa"] = DEFAULT_STRAND_EP_MPA
    return normalized


def _prestress_to_table(elements: list[PrestressElement], table_metadata: list[dict[str, Any]] | None = None) -> pd.DataFrame:
    metadata_rows = table_metadata or []
    rows: list[dict[str, Any]] = []
    for index, element in enumerate(elements, start=1):
        label = element.label or f"PS{index}"
        row = {
            "Active": True,
            "Label": label,
            "Steel Type": element.steel_type,
            "Product": element.material_name or "Custom",
            "x_mm": element.x_mm,
            "y_mm": element.y_mm,
            "Area_mm2": element.area_mm2,
            "Diameter_mm": element.diameter_mm,
            "Eq Steel Dia_mm": None,
            "fpy_MPa": element.fpy_mpa,
            "fpu_MPa": element.fpu_mpa,
            "Ep_MPa": element.ep_mpa,
            "Input Mode": "Effective Force Pe" if element.pe_eff_n > 0 else "Passive",
            "Pe_eff_kN": N_to_kN(element.pe_eff_n),
            "fpe_MPa": element.initial_stress_mpa or 0.0,
            "fpj_ratio": 0.75,
            "loss_percent": 15.0,
            "Bonded": element.bonded,
            "Count": element.count,
            "Strand Count": None,
            "Strand Diameter_mm": None,
            "Strand Area_mm2": None,
            "Breaking Load_kN": None,
            "Duct Type": "",
            "Duct ID_mm": None,
            "Tendon Description": "",
            "Typical Use": "",
            "Note": "",
        }
        row = _restore_tendon_product_metadata(row)
        metadata = _prestress_metadata_for_row(metadata_rows, index, label)
        for column in (
            "Product",
            "Steel Type",
            "fpy_MPa",
            "fpu_MPa",
            "Ep_MPa",
            "Strand Count",
            "Strand Diameter_mm",
            "Strand Area_mm2",
            "Breaking Load_kN",
            "Duct Type",
            "Duct ID_mm",
            "Tendon Description",
            "Typical Use",
            "Note",
        ):
            value = metadata.get(column)
            if not _is_blank(value):
                row[column] = value
        rows.append(_normalize_tendon_group_table_row(row))
    return pd.DataFrame(rows)


def apply_project_to_session_state(project: ProjectModel, session_state: MutableMapping[str, Any]) -> None:
    session_state["project_name"] = project.project_name
    session_state["designer"] = project.designer or ""
    session_state["description"] = project.description or ""
    session_state["design_code"] = project.code

    session_state["section_preset_key"] = project.section_preset_key
    session_state["section_preset_name"] = project.section_preset_name
    session_state["section_parameters"] = dict(project.section_parameters)
    session_state["section_geometry"] = project.section_geometry
    session_state["section_dimensions"] = []
    if project.section_preset_key:
        for name, value in project.section_parameters.items():
            session_state[f"{project.section_preset_key}_{name}"] = value

    session_state["concrete_material"] = project.concrete_material
    session_state["concrete_materials"] = list(project.concrete_materials)
    session_state["rebar_materials"] = list(project.rebar_materials)
    session_state["prestress_materials"] = list(project.prestress_materials)
    session_state["active_rebar_material_name"] = project.active_rebar_material_name
    session_state["active_prestress_material_name"] = project.active_prestress_material_name

    session_state["load_cases"] = list(project.loads)
    session_state["rebars"] = list(project.rebars)
    session_state["prestress_elements"] = list(project.prestress_elements)
    session_state["analysis_mode_settings"] = project.analysis_mode_settings or AnalysisModeSettings()
    session_state["analysis_settings"] = project.analysis_settings or AnalysisSettings()
    session_state["serviceability_settings"] = project.serviceability_settings or ServiceabilitySettings()
    session_state["custom_stress_check_points"] = list(project.custom_stress_check_points)
    session_state["include_default_stress_check_points"] = project.include_default_stress_check_points

    session_state["loads_table"] = _loads_to_table(project.loads)
    session_state["rebar_table"] = _rebars_to_table(project.rebars)
    session_state["prestress_table"] = _prestress_to_table(
        project.prestress_elements,
        _coerce_list(project.metadata.get("prestress_table_metadata")),
    )
    session_state["custom_stress_check_points_table"] = stress_check_points_to_dataframe(project.custom_stress_check_points)

    for flag_name in ("rebars_valid_for_analysis", "prestress_valid_for_analysis"):
        if flag_name in project.metadata:
            session_state[flag_name] = bool(project.metadata[flag_name])
    session_state["project_metadata"] = dict(project.metadata)
