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


def project_from_session_state(session_state: Any) -> ProjectModel:
    metadata = dict(_get_session_value(session_state, "project_metadata", {}) or {})
    for flag_name in ("rebars_valid_for_analysis", "prestress_valid_for_analysis"):
        flag_value = _get_session_value(session_state, flag_name, None)
        if flag_value is not None:
            metadata[flag_name] = flag_value

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


def _prestress_to_table(elements: list[PrestressElement]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Active": True,
                "Label": element.label or f"PS{index}",
                "Steel Type": element.steel_type,
                "Product": element.material_name or "Custom",
                "x_mm": element.x_mm,
                "y_mm": element.y_mm,
                "Area_mm2": element.area_mm2,
                "Diameter_mm": element.diameter_mm,
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
                "Note": "",
            }
            for index, element in enumerate(elements, start=1)
        ]
    )


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
    session_state["prestress_table"] = _prestress_to_table(project.prestress_elements)
    session_state["custom_stress_check_points_table"] = stress_check_points_to_dataframe(project.custom_stress_check_points)

    for flag_name in ("rebars_valid_for_analysis", "prestress_valid_for_analysis"):
        if flag_name in project.metadata:
            session_state[flag_name] = bool(project.metadata[flag_name])
    session_state["project_metadata"] = dict(project.metadata)
