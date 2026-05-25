"""Analysis preflight checks.

This module prepares inputs for future PMM solver milestones only. It does not
run strain compatibility or capacity calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from concrete_pmm_pro.code_checks import aci_beta1
from concrete_pmm_pro.core.analysis import AnalysisInput, AnalysisSettings
from concrete_pmm_pro.core.models import ConcreteMaterial, LoadCase, PrestressElement, Rebar


@dataclass(frozen=True)
class AnalysisReadinessResult:
    ready: bool
    errors: list[str]
    warnings: list[str]
    info: list[str]


def _get_session_value(session_state: Any, key: str, default: Any = None) -> Any:
    if hasattr(session_state, "get"):
        return session_state.get(key, default)
    return getattr(session_state, key, default)


def _analysis_settings_from_session_state(session_state: Any) -> AnalysisSettings:
    value = _get_session_value(session_state, "analysis_settings", None)
    if isinstance(value, AnalysisSettings):
        return value
    if isinstance(value, dict):
        return AnalysisSettings.model_validate(value)
    return AnalysisSettings()


def _active_strength_load_cases(load_cases: list[LoadCase], settings: AnalysisSettings) -> list[LoadCase]:
    return [load_case for load_case in load_cases if load_case.active and load_case.load_type == settings.strength_load_type]


def _total_as(rebars: list[Rebar]) -> float:
    return sum(rebar.area_mm2 for rebar in rebars)


def _total_aps(elements: list[PrestressElement]) -> float:
    return sum(element.total_area_mm2 for element in elements)


def _total_pe_eff(elements: list[PrestressElement]) -> float:
    return sum(element.pe_eff_n * element.count for element in elements)


def check_analysis_readiness(session_state: Any) -> AnalysisReadinessResult:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    settings = _analysis_settings_from_session_state(session_state)
    section_geometry = _get_session_value(session_state, "section_geometry", None)
    concrete_material = _get_session_value(session_state, "concrete_material", None)
    rebar_materials = list(_get_session_value(session_state, "rebar_materials", []) or [])
    prestress_materials = list(_get_session_value(session_state, "prestress_materials", []) or [])
    rebars = list(_get_session_value(session_state, "rebars", []) or [])
    prestress_elements = list(_get_session_value(session_state, "prestress_elements", []) or [])
    load_cases = list(_get_session_value(session_state, "load_cases", []) or [])

    if section_geometry is None:
        errors.append("Section geometry is missing.")
    if concrete_material is None:
        errors.append("Concrete material is missing.")

    strength_load_cases = _active_strength_load_cases(load_cases, settings)
    if not strength_load_cases:
        errors.append(f"No active {settings.strength_load_type} load cases are available.")

    if settings.include_rebars and not rebars:
        errors.append("Rebars are missing while Include rebars is enabled.")

    rebars_valid = _get_session_value(session_state, "rebars_valid_for_analysis", None)
    if rebars_valid is False and (settings.include_rebars or rebars):
        errors.append("Rebars are not valid for analysis.")

    prestress_valid = _get_session_value(session_state, "prestress_valid_for_analysis", None)
    if settings.include_prestress and prestress_elements and prestress_valid is False:
        errors.append("Prestress elements are not valid for analysis.")

    if not rebars:
        warnings.append("No rebars are defined.")
    if not prestress_elements:
        warnings.append("No prestress elements are defined.")
    if any(load_case.load_type == "SLS" for load_case in load_cases):
        warnings.append("SLS load cases are present, but serviceability checks are not implemented yet.")
    if any(not element.bonded for element in prestress_elements):
        warnings.append("Unbonded prestress elements are present; unbonded prestress modeling is future work.")
    if not rebar_materials:
        warnings.append("Project-defined rebar material list is empty.")
    if not prestress_materials:
        warnings.append("Project-defined prestress material list is empty.")

    uls_count = sum(1 for load_case in load_cases if load_case.active and load_case.load_type == "ULS")
    sls_count = sum(1 for load_case in load_cases if load_case.load_type == "SLS")
    info.extend(
        [
            f"Active ULS load cases: {uls_count}.",
            f"SLS load cases stored: {sls_count}.",
            f"Rebars: {len(rebars)}.",
            f"Total As = {_total_as(rebars):,.1f} mm^2.",
            f"Prestress elements: {len(prestress_elements)}.",
            f"Total Aps = {_total_aps(prestress_elements):,.1f} mm^2.",
            f"Total Pe_eff = {_total_pe_eff(prestress_elements):,.1f} N.",
        ]
    )
    if isinstance(concrete_material, ConcreteMaterial):
        beta1 = concrete_material.beta1 if concrete_material.beta1 is not None else aci_beta1(concrete_material.fc_MPa)
        info.append(f"Concrete f'c = {concrete_material.fc_MPa:g} MPa.")
        info.append(f"beta1 = {beta1:.3g}.")

    return AnalysisReadinessResult(ready=not errors, errors=errors, warnings=warnings, info=info)


def build_analysis_input_from_session_state(session_state: Any) -> AnalysisInput | None:
    readiness = check_analysis_readiness(session_state)
    if not readiness.ready:
        return None

    settings = _analysis_settings_from_session_state(session_state)
    load_cases = _active_strength_load_cases(list(_get_session_value(session_state, "load_cases", []) or []), settings)
    return AnalysisInput(
        section_geometry=_get_session_value(session_state, "section_geometry"),
        concrete_material=_get_session_value(session_state, "concrete_material"),
        rebar_materials=list(_get_session_value(session_state, "rebar_materials", []) or []),
        prestress_materials=list(_get_session_value(session_state, "prestress_materials", []) or []),
        rebars=list(_get_session_value(session_state, "rebars", []) or []),
        prestress_elements=list(_get_session_value(session_state, "prestress_elements", []) or []),
        load_cases=load_cases,
        settings=settings,
    )
